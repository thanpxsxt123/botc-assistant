import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
import asyncio
from datetime import datetime
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

# Import ค่าจากโครงสร้างเดิมของโปรเจกต์คุณ
from config.config import Config
from app.api.routes import router as api_router
from app.api.websocket import manager  # ดึง ConnectionManager จาก websocket.py
from app.db.database import get_db, SessionLocal
from app.db.models import GameSession, Player, NightAction
from app.core.fsm import GameEngine
from app.db.migrations import run_migrations

app = FastAPI(title=Config.APP_NAME, version=Config.VERSION)

# ตรวจสอบและสร้างโฟลเดอร์ assets หากยังไม่มี (ป้องกัน Error บน Render)
assets_path = os.path.join(os.getcwd(), "assets")
if not os.path.exists(assets_path):
    os.makedirs(assets_path)
    os.makedirs(os.path.join(assets_path, "narration"), exist_ok=True)

# เสิร์ฟไฟล์จากโฟลเดอร์ assets (สำหรับเสียง Thai Narration)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# --- [Background Task: Automated Phase Advancement] ---

async def automated_game_loop():
    while True:
        await asyncio.sleep(5) # เช็คทุก 5 วินาที
        db = SessionLocal()
        try:
            # หาห้องที่ระบบเป็นแบบ Automated และ Timer หมดเวลาแล้ว
            expired_sessions = db.query(GameSession).filter(
                GameSession.is_automated == True,
                GameSession.timer_expires_at <= datetime.utcnow(),
                GameSession.is_active == True
            ).all()

            for session in expired_sessions:
                engine = GameEngine(db)
                success = engine.next_phase(session.id)
                if success:
                    db.refresh(session)
                    # 🚀 บรอดแคสต์ Full State Update เพื่อให้หน้าจอทุกคนซิงค์ตรงกัน
                    players = db.query(Player).filter(Player.session_id == session.id).all()
                    player_list = [{
                        "id": p.id, "name": p.name, "is_alive": p.is_alive,
                        "is_poisoned": p.is_poisoned, "is_drunk": p.is_drunk,
                        "character_name": p.character.name if p.character else "Unknown",
                        "alignment": p.character.alignment.value if p.character else "Unknown"
                    } for p in players]

                    await manager.broadcast(session.room_code, {
                        "event": "state_update",
                        "data": {
                            "phase": session.current_phase.value,
                            "round": session.day_number,
                            "players": player_list,
                            "timer_expires": session.timer_expires_at.isoformat() + "Z" if session.timer_expires_at else None
                        }
                    })

                    # เช็คเงื่อนไขชนะ
                    winner = engine.check_win_conditions(session.id)
                    if winner:
                        await manager.broadcast(session.room_code, {
                            "event": "game_over",
                            "data": { "winner": winner }
                        })
        except Exception as e:
            print(f"⏰ Auto Loop Error: {e}")
        finally:
            db.close()

@app.on_event("startup")
async def startup_event():
    # อัปเดตโครงสร้าง Database ทันทีที่รัน (แก้ปัญหา column missing บน Render)
    run_migrations()
    asyncio.create_task(automated_game_loop())

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")
env = Environment(loader=FileSystemLoader(template_dir))

# --- [ระบบ Routing หน้าจอ HTML] ---

@app.get("/")
async def get_index(request: Request):
    template = env.get_template("index.html")
    return HTMLResponse(template.render(request=request))

@app.get("/player")
async def get_player(request: Request):
    template = env.get_template("botc-player.html")
    return HTMLResponse(template.render(request=request))

@app.get("/storyteller")
async def get_storyteller(request: Request):
    template = env.get_template("botc-storyteller.html")
    return HTMLResponse(template.render(request=request))


# --- [ท่อสื่อสารอัจฉริยะ WebSocket ดักจับสกิลตัวละคร] ---

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    room_upper = room_code.upper()
    await manager.connect(room_upper, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_json = json.loads(data)
                event_type = message_json.get("event")
                
                # ดักจับเมื่อมีคนกดใช้สกิลผ่านหน้าจอ (เช่น วางยาพิษ, โจมตีโดย Imp)
                if event_type == "player_action_submit":
                    action_data = message_json.get("data", {})
                    
                    # 🚀 บรอดแคสต์ส่งต่อให้ทุกคนในห้อง เพื่อแสดงข้อความและสเตตบนจอคนคุมและผู้เล่นอื่น
                    await manager.broadcast(room_upper, {
                        "event": "player_action_triggered",
                        "data": {
                            "player_name": action_data.get("player_name"),
                            "target_name": action_data.get("target_name"),
                            "action_type": action_data.get("action_type") # 'poison' หรือ 'kill'
                        }
                    })
                else:
                    # กระจายข้อความทั่วไป (state_update, vote_updated, nomination)
                    await manager.broadcast(room_upper, message_json)
                    
            except json.JSONDecodeError:
                await manager.broadcast(room_upper, {"event": "raw_message", "data": data})
            except Exception as e:
                print(f"📡 WebSocket Logic Error: {e}")
                
    except WebSocketDisconnect:
        manager.disconnect(room_upper, websocket)

app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=Config.HOST, port=Config.PORT, reload=Config.DEBUG)