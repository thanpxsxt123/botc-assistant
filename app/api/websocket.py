from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        # room_code -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, room_code: str, websocket: WebSocket):
        await websocket.accept()
        if room_code not in self.active_connections:
            self.active_connections[room_code] = []
        self.active_connections[room_code].append(websocket)

    def disconnect(self, room_code: str, websocket: WebSocket):
        if room_code in self.active_connections:
            self.active_connections[room_code].remove(websocket)
            if not self.active_connections[room_code]:
                del self.active_connections[room_code]

    async def broadcast(self, room_code: str, message: dict):
        if room_code in self.active_connections:
            # ใช้ list[:] เพื่อป้องกันการ error เมื่อมีการแก้ list ระหว่างลูป
            disconnected = []
            for connection in self.active_connections[room_code][:]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    disconnected.append(connection)
            
            # ล้างพวกที่หลุดไปแล้ว
            for conn in disconnected:
                self.disconnect(room_code, conn)

manager = ConnectionManager()
