"""
IntelliSales -- WebSocket Hub

Central WebSocket endpoint that broadcasts live events to connected
dashboard clients.  Clients can optionally subscribe by role to receive
only relevant events.

All live data updates go through WebSocket, not polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("intellisales.ws")

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        # role -> set of connections
        self._connections: Dict[str, Set[WebSocket]] = {
            "staff": set(),
            "manager": set(),
            "owner": set(),
            "all": set(),  # connections that want everything
        }

    async def connect(self, websocket: WebSocket, role: str = "all") -> None:
        await websocket.accept()
        if role not in self._connections:
            role = "all"
        self._connections[role].add(websocket)
        self._connections["all"].add(websocket)
        logger.info(f"WebSocket connected: role={role}")

    def disconnect(self, websocket: WebSocket) -> None:
        for role_set in self._connections.values():
            role_set.discard(websocket)

    async def broadcast(self, event_type: str, data: Any, roles: list[str] | None = None) -> None:
        """Broadcast a message to connected clients.
        
        Args:
            event_type: Event type identifier.
            data: JSON-serializable data payload.
            roles: If specified, only broadcast to these roles. None = all.
        """
        message = json.dumps({
            "event_type": event_type,
            "data": data,
            "timestamp": time.time(),
        })

        targets: Set[WebSocket] = set()
        if roles is None:
            targets = self._connections["all"].copy()
        else:
            for role in roles:
                targets |= self._connections.get(role, set())

        disconnected = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections["all"])


# Global singleton
ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live dashboard updates.
    
    Query param `role` filters events: staff, manager, owner, or all (default).
    """
    role = websocket.query_params.get("role", "all")
    await ws_manager.connect(websocket, role)
    try:
        while True:
            # Keep the connection alive; client can send pings or config
            data = await websocket.receive_text()
            # Handle client messages if needed (e.g., subscription changes)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected: role={role}")
