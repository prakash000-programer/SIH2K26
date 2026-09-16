"""
IntelliSales -- FastAPI Application Entry Point

Ties together all routers, database, CV pipeline, and background tasks.

Run:
    python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

Or simply:
    python backend/main.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    API_HOST, API_PORT, CORS_ORIGINS, CALIBRATION_DIR, get_video_source,
)
from backend.database import db
from backend.retention import retention_loop
from backend.routers import ws, analytics, calibration, queue, inventory, dashboard, video
from backend.routers.ws import ws_manager

# CV pipeline imports are lazy -- torch/ultralytics may not be available
# (e.g., DLL blocked by Application Control, or not installed on edge device)
_CV_AVAILABLE = False
CameraCalibrator = None
AnalyticsPipeline = None
WebcamSource = None
SyntheticStoreSource = None
FrameResult = None
FloorGrid = None
MultiCameraManager = None

try:
    from backend.cv.calibration import CameraCalibrator
    from backend.cv.pipeline import (
        AnalyticsPipeline, WebcamSource, SyntheticStoreSource, FrameResult,
        DynamicFrameSource, MobileBrowserFrameSource
    )
    from backend.cv.grid import FloorGrid
    from backend.cv.multi_pipeline import MultiCameraManager
    _CV_AVAILABLE = True
except (ImportError, OSError) as e:
    import logging as _log
    _log.getLogger("intellisales").warning(
        f"CV pipeline unavailable (torch/ultralytics load failed: {e}). "
        "API will run without live detection."
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("intellisales")

# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

_pipeline: Optional[AnalyticsPipeline] = None
_pipeline_thread: Optional[threading.Thread] = None
_event_loop: Optional[asyncio.AbstractEventLoop] = None
_multi_cam_mgr: Optional[MultiCameraManager] = None
_last_heatmap_db: float = 0.0
_last_global_broadcast: float = 0.0
_last_detections_broadcast: Dict[str, float] = {}


async def _persist_and_broadcast(result: FrameResult, camera_id: str = "cam0") -> None:
    """Persist events to DB and broadcast via WebSocket."""
    global _last_heatmap_db, _last_global_broadcast
    try:
        now = time.time()

        # Heatmap data (throttled to 2 Hz to avoid SQLite lock thrashing)
        if result.heatmap_cells and (now - _last_heatmap_db >= 0.5):
            _last_heatmap_db = now
            events = [
                {
                    "timestamp": result.timestamp,
                    "cell_row": cell[0],
                    "cell_col": cell[1],
                    "person_count": count,
                    "confidence": "low" if result.is_high_density else "normal",
                }
                for cell, count in result.heatmap_cells.items()
            ]
            await db.insert_detection_events(events)

        # Dwell events
        for ev in result.dwell_events:
            await db.insert_dwell_event(
                ev.timestamp, ev.zone_id, ev.total_qualifying_time_s,
                confidence="low" if result.is_high_density else "normal",
            )

        # Footfall events
        for ev in result.footfall_events:
            await db.insert_footfall_event(ev.timestamp, ev.direction)

        # Density snapshots
        if result.density_snapshot:
            cell_counts_json = json.dumps({
                f"({r},{c})": cnt
                for (r, c), cnt in result.density_snapshot.cell_counts.items()
            })
            await db.insert_density_snapshot(
                result.density_snapshot.timestamp,
                result.density_snapshot.total_persons,
                cell_counts_json,
            )

        # WebSocket broadcasts — include camera_id and global_id in real-time (throttled to 20 Hz per cam)
        last_det_time = _last_detections_broadcast.get(camera_id, 0.0)
        if result.tracked_persons and (now - last_det_time >= 0.05):
            _last_detections_broadcast[camera_id] = now
            detections_data = [
                {
                    "track_id": p.track_id,
                    "global_id": p.global_id if p.global_id > 0 else None,
                    "camera_id": camera_id,
                    "centroid_px": list(p.centroid_px),
                    "centroid_world": list(p.centroid_world) if p.centroid_world else None,
                    "confidence": p.confidence,
                    "gender": p.gender,
                    "gender_confidence": round(p.gender_confidence, 2),
                    "dwell_time_s": round(p.dwell_time_s, 1),
                }
                for p in result.tracked_persons
            ]
            await ws_manager.broadcast("detections", {
                "persons": detections_data,
                "count": len(detections_data),
                "is_high_density": result.is_high_density,
                "camera_id": camera_id,
            })

        # Broadcast global Re-ID tracks periodically (throttled to 2.5 Hz)
        if _multi_cam_mgr and (now - _last_global_broadcast >= 0.4):
            _last_global_broadcast = now
            global_tracks = _multi_cam_mgr.get_all_global_tracks()
            if global_tracks:
                await ws_manager.broadcast("global_tracks", {
                    "tracks": global_tracks,
                    "total": len(global_tracks),
                })

        for ev in result.dwell_events:
            await ws_manager.broadcast("dwell", {
                "zone_id": ev.zone_id,
                "qualifying_time_s": ev.total_qualifying_time_s,
                "timestamp": ev.timestamp,
                "camera_id": camera_id,
            }, roles=["manager", "owner"])

        for ev in result.footfall_events:
            await ws_manager.broadcast("footfall", {
                "direction": ev.direction,
                "timestamp": ev.timestamp,
                "camera_id": camera_id,
            })


    except Exception as e:
        logger.error(f"Error in persist/broadcast: {e}", exc_info=True)


def _on_frame_result_legacy(result: FrameResult) -> None:
    """Callback from the legacy single-camera pipeline thread."""
    if _event_loop and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            _persist_and_broadcast(result, "cam0"), _event_loop
        )


def _on_multi_cam_result(camera_id: str, result: FrameResult) -> None:
    """Callback from MultiCameraManager -- schedules async work on the event loop."""
    if _event_loop and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            _persist_and_broadcast(result, camera_id), _event_loop
        )


def _run_pipeline_with_multi_cam() -> None:
    """Start the multi-camera manager with cam0 as the default camera."""
    global _pipeline, _multi_cam_mgr

    # Create multi-camera manager
    _multi_cam_mgr = MultiCameraManager(
        on_frame_result=_on_multi_cam_result,
    )
    video.set_multi_camera_manager(_multi_cam_mgr)

    # Set up default camera (cam0)
    raw_source = WebcamSource(get_video_source())
    source_name = f"Laptop Webcam ({get_video_source()})"
    if not raw_source.is_opened():
        logger.warning(f"Could not open video source {get_video_source()} -- using synthetic store")
        raw_source = SyntheticStoreSource()
        source_name = "Synthetic Store (Demo)"
    else:
        logger.info(f"CV pipeline started on hardware source: {get_video_source()}")

    _multi_cam_mgr.add_camera(
        camera_id="cam0",
        source=raw_source,
        display_name=source_name,
        source_type="webcam",
    )

    # Set legacy references for backwards compatibility
    _pipeline = _multi_cam_mgr.get_camera_pipeline("cam0")
    video.set_pipeline(_pipeline)
    dynamic_source = _multi_cam_mgr.get_camera_dynamic_source("cam0")
    video.set_dynamic_source(dynamic_source)

    logger.info("Multi-camera manager started with cam0")
    # The manager runs camera threads internally, so this function returns
    # (no blocking run_loop needed)


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global _event_loop, _pipeline_thread

    # Store the event loop reference for the pipeline thread
    _event_loop = asyncio.get_event_loop()

    # Connect database
    await db.connect()
    logger.info(f"Database connected: {db.db_path}")

    # Start retention job
    retention_task = asyncio.create_task(retention_loop())
    logger.info("Retention job started")

    # Start multi-camera CV pipeline — only if torch is available
    if _CV_AVAILABLE:
        _pipeline_thread = threading.Thread(target=_run_pipeline_with_multi_cam, daemon=True)
        _pipeline_thread.start()
    else:
        logger.warning("CV pipeline skipped (torch/ultralytics not available)")

    yield

    # Shutdown
    if _multi_cam_mgr:
        _multi_cam_mgr.shutdown()
    elif _pipeline:
        _pipeline.stop()
    retention_task.cancel()
    await db.close()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IntelliSales",
    description="Privacy-first retail intelligence platform (SIH26179)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - Allow localhost, LAN/Wi-Fi IPs (mobile/tablets), and edge clients
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(ws.router)
app.include_router(analytics.router)
app.include_router(calibration.router)
app.include_router(queue.router)
app.include_router(inventory.router)
app.include_router(dashboard.router)
app.include_router(video.router)


@app.get("/")
async def root():
    return {
        "name": "IntelliSales",
        "version": "0.1.0",
        "status": "running",
        "modules": ["analytics", "inventory", "queue", "dashboard"],
    }


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "db_connected": db._db is not None,
        "pipeline_running": _pipeline is not None and _pipeline._running,
        "ws_connections": ws_manager.connection_count,
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
