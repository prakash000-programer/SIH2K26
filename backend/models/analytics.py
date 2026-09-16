"""
IntelliSales -- Pydantic Models for Analytics
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel


class HeatmapCell(BaseModel):
    row: int
    col: int
    count: int


class HeatmapResponse(BaseModel):
    cells: List[HeatmapCell]
    grid_rows: int
    grid_cols: int
    cell_size_m: float
    start_ts: float
    end_ts: float


class DwellEventResponse(BaseModel):
    id: int
    timestamp: float
    zone_id: str
    qualifying_time_s: float
    confidence: str


class FootfallResponse(BaseModel):
    count_in: int
    count_out: int
    total: int
    start_ts: float
    end_ts: float


class FootfallRateResponse(BaseModel):
    rate_per_minute: float
    window_seconds: float


class CalibrationPointsRequest(BaseModel):
    pixel_points: List[List[float]]    # [[px1,py1], [px2,py2], ...]
    world_points: List[List[float]]    # [[wx1,wy1], [wx2,wy2], ...]
    camera_id: str = "cam0"


class CalibrationStatus(BaseModel):
    is_calibrated: bool
    camera_id: str
    reprojection_error: Optional[float] = None
