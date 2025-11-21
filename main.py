from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
from pathlib import Path

# Create FastAPI app (This is our backend server)
app = FastAPI()

# Serve frontend files (index.html, JS, CSS) from the "static" folder
app.mount("/static", StaticFiles(directory="static"), name="static")


# ------------------ MANAGES ACTIVE USERS ------------------

class ConnectionManager:
    def __init__(self):
        # List to store all connected WebSocket clients
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        # Accept client's WebSocket connection
        await websocket.accept()
        # Add this client to connected users list
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        # Remove client when they disconnect/leave
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # Send message to all connected users
        disconnected = []
        for ws in self.active_connections:
            try:
                # Send text message to that client
                await ws.send_text(message)
            except WebSocketDisconnect:
                # If connection breaks, remove the client
                disconnected.append(ws)
            except Exception:
                disconnected.append(ws)
        # Final cleanup for clients who disconnected
        for ws in disconnected:
            self.disconnect(ws)


# Create object to manage all connections
manager = ConnectionManager()


# ------------------ SERVE FRONTEND PAGE ------------------

@app.get("/")
async def get():
    # Read and return index.html when website opens
    index = Path("static/index.html").read_text(encoding="utf-8")
    return HTMLResponse(index)


# ------------------ HANDLE REAL-TIME WEBSOCKET ------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # When user connects, add to connection list
    await manager.connect(websocket)

    # Send update about how many users are online
    await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))

    try:
        while True:
            # Receive message from a client
            data = await websocket.receive_text()

            # Convert string into JSON dictionary
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue  # ignore invalid data

            # If user asks for client count, send count
            if msg.get("type") == "clients-request":
                await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
                continue

            # Send the message to every connected client
            # (This includes drawings, notes, graphs, etc.)
            await manager.broadcast(json.dumps(msg))

    # ------------ HANDLE DISCONNECTS ------------
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))

    except Exception:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({"type": "clients", "count": len(manager.active_connections)}))
