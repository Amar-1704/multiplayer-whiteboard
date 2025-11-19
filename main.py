from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
from pathlib import Path

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except WebSocketDisconnect:
                disconnected.append(ws)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

manager = ConnectionManager()

@app.get("/")
async def get():
    index = Path("static/index.html").read_text(encoding="utf-8")
    return HTMLResponse(index)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # notify about current client count
    await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))

    try:
        while True:
            data = await websocket.receive_text()
            # simply broadcast any message (draw, clear, graph, sticky, etc.) to all clients
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            # server controls client count broadcast
            if msg.get("type") == "clients-request":
                await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
                continue

            await manager.broadcast(json.dumps(msg))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
    except Exception:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
