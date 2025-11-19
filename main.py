from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import json
import pathlib

app = FastAPI()

# Serve files from the "static" directory
app.mount("/static", StaticFiles(directory="static"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        # Accept and add to active list, then broadcast client count to all
        await websocket.accept()
        self.active_connections.append(websocket)
        await self.broadcast(json.dumps({"type": "clients", "count": len(self.active_connections)}))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str, sender: WebSocket | None = None):
        # Broadcast message to all clients (including sender for some messages).
        for connection in list(self.active_connections):
            try:
                # We allow broadcasting to all except when explicitly excluded.
                if connection is not sender:
                    await connection.send_text(message)
            except Exception:
                # If sending fails, disconnect that client.
                self.disconnect(connection)

manager = ConnectionManager()

@app.get("/")
async def root():
    # Serve the main static index file
    index_path = pathlib.Path("static") / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # The server simply rebroadcasts message to other clients (stateless)
            # We also handle simple heartbeat/messages here if needed.
            await manager.broadcast(data, sender=websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # Notify remaining clients of updated client count
        await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
    except Exception:
        # Generic exception safety: ensure disconnect & notify
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
