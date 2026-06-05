import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from config.config import Config
from app.api.routes import router as api_router
from app.api.websocket import manager

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

@app.get("/storyteller")
async def get_storyteller(request: Request):
    try:
        template = env.get_template("storyteller.html")
        content = template.render(request=request)
        return HTMLResponse(content=content)
    except Exception as e:
        import traceback
        print(f"Template Error: {e}")
        traceback.print_exc()
        raise e

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    await manager.connect(room_code, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle incoming client messages if needed
    except WebSocketDisconnect:
        manager.disconnect(room_code, websocket)

app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=Config.HOST, port=Config.PORT, reload=Config.DEBUG)
