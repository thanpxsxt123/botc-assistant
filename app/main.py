import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from config.config import Config
from app.api.routes import router as api_router
from app.api.websocket import manager

app = FastAPI(title=Config.APP_NAME, version=Config.VERSION)

# ใช้แอดเดรสสัมบูรณ์ชี้ไปยังโฟลเดอร์ templates
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")
env = Environment(loader=FileSystemLoader(template_dir))

@app.get("/")
async def get_index(request: Request):
    try:
        template = env.get_template("index.html")
        content = template.render(request=request)
        return HTMLResponse(content=content)
    except Exception as e:
        import traceback
        print(f"Template Error: {e}")
        traceback.print_exc()
        raise e

@app.get("/player")
async def get_player(request: Request):
    try:
        # 🟢 เพิ่มหน้าจอสำหรับผู้เล่นเข้ามาเล่นในห้อง
        template = env.get_template("botc-player.html")
        content = template.render(request=request)
        return HTMLResponse(content=content)
    except Exception as e:
        import traceback
        print(f"Template Error: {e}")
        traceback.print_exc()
        raise e

@app.get("/storyteller")
async def get_storyteller(request: Request):
    try:
        # 👑 ลิงก์ไปยังไฟล์บอร์ดควบคุมของ Storyteller
        template = env.get_template("botc-storyteller.html")
        content = template.render(request=request)
        return HTMLResponse(content=content)
    except Exception as e:
        import traceback
        print(f"Template Error: {e}")
        traceback.print_exc()
        raise e

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    room_upper = room_code.upper()
    await manager.connect(room_upper, websocket)
    try:
        while True:
            # 🔄 รับข้อความจากไคลเอนต์ (เช่น ข้อความการส่งอัปเดตสเตท หรือคำสั่งโหวต)
            data = await websocket.receive_text()
            try:
                # ทำหน้าที่เป็นสถานีกลาง: ได้รับอัปเดตอะไรมา ส่งกระจายตัวนั้นหาทุกคนในห้องเดียวกันทันที
                message_data = json.loads(data)
                await manager.broadcast_to_room(room_upper, message_data)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(room_upper, websocket)

app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=Config.HOST, port=Config.PORT, reload=Config.DEBUG)
