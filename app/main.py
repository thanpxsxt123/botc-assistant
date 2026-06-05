import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from config.config import Config
from app.api.routes import router as api_router
from app.api.websocket import manager  # ดึง manager ตัวจริงของคุณมาใช้งาน

app = FastAPI(title=Config.APP_NAME, version=Config.VERSION)

# Use absolute path for templates
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
        # เปิดหน้าจอสำหรับผู้เล่น (botc-player.html)
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
        # เปิดหน้าจอสำหรับ Storyteller (botc-storyteller.html)
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
    # ปรับให้เป็นตัวพิมพ์ใหญ่ตามมาตรฐานห้องในระบบ SQL DB ของคุณ
    room_upper = room_code.upper()
    await manager.connect(room_upper, websocket)
    try:
        while True:
            # รอรับข้อความในกรณีที่หน้าบ้านส่ง Event สดผ่านมาทาง WS
            data = await websocket.receive_text()
            
            # โค้ดส่วนนี้จะรับข้อความดิบจากหน้าบ้านแล้วแปลงส่งกระจายต่อ (Echo/Broadcast)
            import json
            try:
                message_json = json.loads(data)
                # เรียกใช้ .broadcast() ซึ่งเป็นเมธอดที่มีอยู่จริงใน websocket.py ของคุณ
                await manager.broadcast(room_upper, message_json)
            except Exception:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(room_upper, websocket)

app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    # ปรับทางเดินสคริปต์รัน uvicorn ให้ถูกต้องตามโครงสร้างโปรเจกต์
    uvicorn.run("app.main:app", host=Config.HOST, port=Config.PORT, reload=Config.DEBUG)
