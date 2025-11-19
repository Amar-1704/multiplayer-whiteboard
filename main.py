from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json, asyncio, pathlib, uuid

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # server-side authoritative state so new clients get current view
        self.history = []  # list of drawing/clear/graph commands
        self.stickies = {}  # id -> {x,y,html,z}
        self.next_z = 1

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # send initial sync state: history and stickies and current client count
        try:
            await websocket.send_text(json.dumps({"type":"sync", "history": self.history, "stickies": list(self.stickies.values()), "clients": len(self.active_connections)}))
        except Exception:
            pass
        # notify others about new client count
        await self.broadcast(json.dumps({"type":"clients", "count": len(self.active_connections)}))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # send to all active connections (best-effort)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

@app.get("/")
async def root():
    index_path = pathlib.Path("static") / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # basic validation/parsing
            try:
                msg = json.loads(data)
            except Exception:
                continue

            # Handle sticky actions server-side to maintain authoritative state
            if msg.get("type") == "sticky":
                action = msg.get("action")
                if action == "create":
                    # ensure id present
                    sid = msg.get("id") or str(uuid.uuid4())
                    sticky = {"type":"sticky", "action":"create", "id": sid, "x": msg.get("x",50), "y": msg.get("y",50), "html": msg.get("html",""), "z": manager.next_z}
                    manager.next_z += 1
                    manager.stickies[sid] = sticky
                    manager.history.append(sticky)
                    await manager.broadcast(json.dumps(sticky))
                elif action == "edit":
                    sid = msg.get("id")
                    if sid in manager.stickies:
                        manager.stickies[sid]["html"] = msg.get("html","")
                        manager.history.append({"type":"sticky","action":"edit","id":sid,"html":manager.stickies[sid]["html"]})
                        await manager.broadcast(json.dumps({"type":"sticky","action":"edit","id":sid,"html":manager.stickies[sid]["html"]}))
                elif action == "move":
                    sid = msg.get("id")
                    if sid in manager.stickies:
                        manager.stickies[sid]["x"] = msg.get("x", manager.stickies[sid]["x"])
                        manager.stickies[sid]["y"] = msg.get("y", manager.stickies[sid]["y"])
                        manager.history.append({"type":"sticky","action":"move","id":sid,"x":manager.stickies[sid]["x"],"y":manager.stickies[sid]["y"]})
                        await manager.broadcast(json.dumps({"type":"sticky","action":"move","id":sid,"x":manager.stickies[sid]["x"],"y":manager.stickies[sid]["y"]}))
                elif action == "delete":
                    sid = msg.get("id")
                    if sid in manager.stickies:
                        del manager.stickies[sid]
                        manager.history.append({"type":"sticky","action":"delete","id":sid})
                        await manager.broadcast(json.dumps({"type":"sticky","action":"delete","id":sid}))
                continue

            # For drawing/graph/clear messages: append to history and broadcast
            if msg.get("type") in ("draw","clear","graph","voice"):
                manager.history.append(msg)
                await manager.broadcast(json.dumps(msg))
                continue

            # handle other types like client heartbeat etc
            if msg.get("type") == "clients":
                await manager.broadcast(json.dumps({"type":"clients", "count": len(manager.active_connections)}))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type":"clients", "count": len(manager.active_connections)}))
    except Exception:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type":"clients", "count": len(manager.active_connections)}))