"""
IntelliSales -- Analytics API Router

REST endpoints for heatmap, dwell-time, and footfall data.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Query

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import db
from backend.config import CELL_SIZE_M, FLOOR_WIDTH_M, FLOOR_HEIGHT_M
from backend.cv.grid import FloorGrid

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_grid = FloorGrid()


@router.get("/heatmap")
async def get_heatmap(
    start: Optional[float] = Query(None, description="Start timestamp (epoch). Default: last 1 hour"),
    end: Optional[float] = Query(None, description="End timestamp (epoch). Default: now"),
):
    """Time-windowed heatmap grid data."""
    now = time.time()
    start_ts = start if start is not None else (now - 3600)
    end_ts = end if end is not None else now

    cells = await db.get_heatmap(start_ts, end_ts)
    return {
        "cells": cells,
        "grid_rows": _grid.num_rows,
        "grid_cols": _grid.num_cols,
        "cell_size_m": CELL_SIZE_M,
        "floor_width_m": FLOOR_WIDTH_M,
        "floor_height_m": FLOOR_HEIGHT_M,
        "start_ts": start_ts,
        "end_ts": end_ts,
    }


@router.get("/dwell")
async def get_dwell_events(
    start: Optional[float] = Query(None),
    end: Optional[float] = Query(None),
    zone: Optional[str] = Query(None, description="Filter by zone ID"),
):
    """Dwell events in a time window, optionally filtered by zone."""
    now = time.time()
    start_ts = start if start is not None else (now - 3600)
    end_ts = end if end is not None else now

    events = await db.get_dwell_events(start_ts, end_ts, zone_id=zone)
    return {"events": events, "start_ts": start_ts, "end_ts": end_ts}


@router.get("/footfall")
async def get_footfall(
    start: Optional[float] = Query(None),
    end: Optional[float] = Query(None),
):
    """Footfall in/out counts for a time window."""
    now = time.time()
    start_ts = start if start is not None else (now - 86400)  # default: last 24h
    end_ts = end if end is not None else now

    counts = await db.get_footfall(start_ts, end_ts)
    return {
        "count_in": counts["in"],
        "count_out": counts["out"],
        "total": counts["in"] + counts["out"],
        "start_ts": start_ts,
        "end_ts": end_ts,
    }


@router.get("/footfall/rate")
async def get_footfall_rate(
    window: float = Query(300.0, description="Window in seconds (default 5 min)"),
):
    """Current smoothed footfall rate (IN per minute)."""
    rate = await db.get_footfall_rate(window_seconds=window)
    return {"rate_per_minute": rate, "window_seconds": window}
