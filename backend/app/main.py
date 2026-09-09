"""
OceanGuard — FastAPI Application Root
======================================
SIH PS 26143 | NTRO | Space Technology
"""

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router as api_router, ALERTS_STORE
from app.schemas.models import Alert

app = FastAPI(
    title="OceanGuard API — Maritime Oil Spill Intelligence Platform",
    description="SIH PS 26143 | AI-powered SAR oil spill detection & AIS vessel attribution engine.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS setup — allow frontend Vite dev server (http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits local React app + presentation deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(api_router)


# ─── WEBSOCKET ALERT BROADCASTER ─────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"📡 Client connected to alert stream. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"🔌 Client disconnected. Remaining active: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket endpoint for real-time live alert updates.
    Simulates continuous satellite pass telemetry & AIS gap detection alerts.
    """
    await manager.connect(websocket)
    try:
        # Send current alerts on initial connection
        await websocket.send_json({
            "event": "INIT",
            "alerts": [a.model_dump() for a in ALERTS_STORE]
        })

        # Periodic telemetry simulation loop
        alert_templates = [
            ("info", "Sentinel-1 SAR Pass Detected", "Auto-analysis queued for Bay of Bengal sector (Pass #144)."),
            ("high", "AIS Transponder Anomaly", "Vessel MV KALPANA CHAWLA reported 47m AIS silence near active spill."),
            ("medium", "Palk Strait Spill — Drift Update", "Estimated drift: 1.2 knots NE towards international waters.")
        ]

        while True:
            await asyncio.sleep(45)  # Broadcast new event every 45s in live mode
            template = random.choice(alert_templates)
            new_alert = Alert(
                id=f"ALT-{int(asyncio.get_event_loop().time() * 1000)}",
                type=template[0],
                title=template[1],
                message=template[2],
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            ALERTS_STORE.insert(0, new_alert)
            await manager.broadcast({
                "event": "NEW_ALERT",
                "alert": new_alert.model_dump()
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/")
async def root():
    return {
        "title": "OceanGuard Maritime Intelligence Platform",
        "problem_statement": "SIH PS 26143 — Oil Spill Detection & Vessel Attribution",
        "organization": "NTRO",
        "status": "Online",
        "api_docs": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
