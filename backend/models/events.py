"""
IntelliSales -- Pydantic Models for Events
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class LiveDetection(BaseModel):
    """WebSocket event for a tracked person."""
    track_id: int
    centroid_px: List[float]
    centroid_world: Optional[List[float]] = None
    cell: Optional[List[int]] = None
    zone: Optional[str] = None
    confidence: float


class LiveDwellEvent(BaseModel):
    """WebSocket event for zone dwell."""
    zone_id: str
    qualifying_time_s: float
    timestamp: float


class LiveFootfallEvent(BaseModel):
    """WebSocket event for footfall crossing."""
    direction: str
    timestamp: float
    count_in: int
    count_out: int


class LiveQueueAlert(BaseModel):
    """WebSocket event for queue alert."""
    alert_type: str
    predicted_queue: float
    max_acceptable: float
    details: Dict[str, Any] = {}
    timestamp: float


class LiveStockoutAlert(BaseModel):
    """WebSocket event for stock-out."""
    slot_name: str
    slot_id: int
    timestamp: float


class WebSocketMessage(BaseModel):
    """Envelope for all WebSocket messages."""
    event_type: str  # 'detections', 'dwell', 'footfall', 'queue_alert', 'stockout', 'density'
    data: Any
    timestamp: float
