"""
IntelliSales -- Queue Intelligence API Router

Simulated queue input + full predictive formula chain.
"""

from __future__ import annotations

import json
import time
from typing import Dict

from fastapi import APIRouter, HTTPException

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import db
from backend.models.queue import QueueConfig, QueuePrediction, CounterAction
from backend.routers.ws import ws_manager
from backend.queue_intel.predictor import QueuePredictor

router = APIRouter(prefix="/api/queue", tags=["queue"])

# Module-level predictor instance
_predictor = QueuePredictor()

# In-memory queue sizes (simulated sensor input)
_queue_sizes: Dict[str, int] = {}


@router.post("/increment")
async def increment_queue(action: CounterAction):
    """Simulate a break-beam sensor: someone joined the queue."""
    cid = action.counter_id
    _queue_sizes[cid] = _queue_sizes.get(cid, 0) + 1
    await db.insert_queue_reading(cid, _queue_sizes[cid])

    # Broadcast queue update
    await ws_manager.broadcast("queue_update", {
        "counter_id": cid,
        "queue_size": _queue_sizes[cid],
        "all_queues": dict(_queue_sizes),
    })

    return {"counter_id": cid, "queue_size": _queue_sizes[cid]}


@router.post("/decrement")
async def decrement_queue(action: CounterAction):
    """Simulate: someone left the queue (served or abandoned)."""
    cid = action.counter_id
    _queue_sizes[cid] = max(0, _queue_sizes.get(cid, 0) - 1)
    await db.insert_queue_reading(cid, _queue_sizes[cid])

    await ws_manager.broadcast("queue_update", {
        "counter_id": cid,
        "queue_size": _queue_sizes[cid],
        "all_queues": dict(_queue_sizes),
    })

    return {"counter_id": cid, "queue_size": _queue_sizes[cid]}


@router.get("/status")
async def queue_status():
    """Get current queue sizes for all counters."""
    return {"queues": dict(_queue_sizes)}


@router.get("/prediction")
async def get_prediction():
    """Run the full predictive formula chain and return results."""
    # Get current footfall rate
    footfall_rate = await db.get_footfall_rate(window_seconds=300)

    # Get current queue sizes
    current_total = sum(_queue_sizes.values())
    counters_open = len(_queue_sizes) if _queue_sizes else 1

    # Run prediction
    prediction = _predictor.predict(
        footfall_rate=footfall_rate,
        current_queue_size=current_total,
        counters_open=counters_open,
    )

    result = {
        **prediction,
        "queue_sizes": dict(_queue_sizes),
        "counters_open": counters_open,
        "current_total_queue": current_total,
        "footfall_rate": footfall_rate,
    }

    # Check if we need to fire an alert
    if prediction["should_open_counter"]:
        alert_data = {
            "alert_type": "open_counter",
            "predicted_queue": prediction["predicted_queue_size"],
            "max_acceptable": prediction["max_acceptable_queue"],
            "details": result,
        }
        await db.insert_queue_alert(
            "open_counter",
            prediction["predicted_queue_size"],
            prediction["max_acceptable_queue"],
            json.dumps(result),
        )
        await ws_manager.broadcast("queue_alert", alert_data, roles=["staff", "manager", "owner"])

    return result


@router.put("/config")
async def update_queue_config(config: QueueConfig):
    """Update queue prediction parameters from the dashboard."""
    if config.avg_service_time_s is not None:
        _predictor.avg_service_time = config.avg_service_time_s
        await db.set_config("avg_service_time_s", str(config.avg_service_time_s))

    if config.conversion_rate is not None:
        _predictor.conversion_rate = config.conversion_rate
        await db.set_config("conversion_rate", str(config.conversion_rate))

    if config.max_acceptable_wait_time_s is not None:
        _predictor.max_acceptable_wait_time = config.max_acceptable_wait_time_s
        await db.set_config("max_acceptable_wait_time_s", str(config.max_acceptable_wait_time_s))

    if config.avg_shopping_time_s is not None:
        _predictor.avg_shopping_time = config.avg_shopping_time_s
        await db.set_config("avg_shopping_time_s", str(config.avg_shopping_time_s))

    if config.smoothing_alpha is not None:
        _predictor.smoothing_alpha = config.smoothing_alpha
        await db.set_config("smoothing_alpha", str(config.smoothing_alpha))

    return {"success": True, "config": {
        "avg_service_time_s": _predictor.avg_service_time,
        "conversion_rate": _predictor.conversion_rate,
        "max_acceptable_wait_time_s": _predictor.max_acceptable_wait_time,
        "avg_shopping_time_s": _predictor.avg_shopping_time,
        "smoothing_alpha": _predictor.smoothing_alpha,
    }}
