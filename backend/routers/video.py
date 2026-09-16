"""
IntelliSales -- Live Video Streaming & Multi-Camera Management Router

Provides:
- MJPEG HTTP video stream endpoint (/api/video/feed) for the web dashboard.
- Per-camera and grid composite MJPEG feeds.
- Multi-camera CRUD: add, remove, list cameras dynamically.
- Live Mobile Camera Ingestion (via WebSocket or HTTP POST) directly from a mobile browser.
- Network IP Camera (RTSP / HTTP MJPEG) / WebCam dynamic hot-swapping.
- Global Re-ID track listing across all cameras.
- In-memory privacy processing: zero frames are saved to disk.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.cv.pipeline import MobileBrowserFrameSource, DynamicFrameSource, WebcamSource

logger = logging.getLogger("intellisales.video")

router = APIRouter(prefix="/api/video", tags=["video"])

# Module references — set by main.py at startup
_pipeline_ref = None                        # Legacy single pipeline (cam0)
_dynamic_source_ref: Optional[DynamicFrameSource] = None
_mobile_source = MobileBrowserFrameSource()
_multi_camera_mgr = None                    # MultiCameraManager instance


def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline


def get_pipeline():
    global _pipeline_ref
    return _pipeline_ref


def set_dynamic_source(dynamic_source: DynamicFrameSource):
    global _dynamic_source_ref
    _dynamic_source_ref = dynamic_source


def get_dynamic_source() -> Optional[DynamicFrameSource]:
    global _dynamic_source_ref
    return _dynamic_source_ref


def set_multi_camera_manager(mgr):
    global _multi_camera_mgr
    _multi_camera_mgr = mgr


def get_multi_camera_manager():
    global _multi_camera_mgr
    return _multi_camera_mgr


def _generate_standby_frame(msg: str = "INITIALIZING LIVE CAMERA FEED...") -> bytes:
    """Generate a high-tech placeholder frame if camera is initializing or switching."""
    w, h = 640, 480
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = (20, 26, 38)  # dark navy

    # Draw grid lines
    for y in range(0, h, 40):
        cv2.line(frame, (0, y), (w, y), (30, 40, 56), 1)
    for x in range(0, w, 40):
        cv2.line(frame, (x, 0), (x, h), (30, 40, 56), 1)

    # Status box
    cv2.rectangle(frame, (50, 150), (w - 50, 310), (14, 18, 26), -1)
    cv2.rectangle(frame, (50, 150), (w - 50, 310), (0, 215, 255), 1)

    cv2.putText(frame, "INTELLISALES  •  EDGE VISION HUB", (80, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 215, 255), 2)
    cv2.putText(frame, msg, (80, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)
    time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(frame, f"EDGE CLOCK: {time_str}", (80, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 180, 200), 1)
    cv2.putText(frame, "PRIVACY GUARANTEE: ZERO DISK STORAGE - VOLATILE RAM ONLY", (70, 445), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 235, 120), 1)

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpeg.tobytes()


# ---------------------------------------------------------------------------
# MJPEG Streaming Endpoints
# ---------------------------------------------------------------------------

@router.get("/feed")
async def video_feed(camera_id: Optional[str] = None):
    """Stream live annotated camera frames as MJPEG.

    If camera_id is provided and multi-camera is active, streams that specific camera.
    Otherwise streams the primary camera (cam0).

    Privacy Guarantee: Frames exist only in volatile RAM as transient numpy arrays
    and are discarded after streaming.
    """
    async def frame_generator():
        last_sent = None
        while True:
            jpeg_bytes = None

            if camera_id and _multi_camera_mgr:
                jpeg_bytes = _multi_camera_mgr.get_camera_jpeg(camera_id)
            elif _pipeline_ref is not None:
                jpeg_bytes = _pipeline_ref.get_latest_jpeg()

            if jpeg_bytes is None:
                src_name = "Camera"
                if camera_id and _multi_camera_mgr:
                    cams = _multi_camera_mgr.list_cameras()
                    cam_info = next((c for c in cams if c["camera_id"] == camera_id), None)
                    src_name = cam_info["display_name"] if cam_info else camera_id
                elif _dynamic_source_ref:
                    src_name = _dynamic_source_ref.source_name
                msg = f"WAITING FOR FRAMES FROM: {src_name.upper()}"
                jpeg_bytes = _generate_standby_frame(msg)

            if jpeg_bytes is not last_sent:
                last_sent = jpeg_bytes
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
                )
            await asyncio.sleep(0.018)  # Up to 55 FPS streaming capacity

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/feed/grid")
async def video_feed_grid():
    """Stream a composite grid of all active camera feeds as MJPEG."""
    async def grid_generator():
        last_sent = None
        while True:
            jpeg_bytes = None
            if _multi_camera_mgr:
                jpeg_bytes = _multi_camera_mgr.get_grid_jpeg()

            if jpeg_bytes is None:
                jpeg_bytes = _generate_standby_frame("NO CAMERAS ACTIVE — ADD A CAMERA TO START")

            if jpeg_bytes is not last_sent:
                last_sent = jpeg_bytes
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
                )
            await asyncio.sleep(0.025)  # Up to 40 FPS grid streaming capacity


    return StreamingResponse(
        grid_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
async def video_status():
    """Get live camera feed and pipeline performance metrics."""
    status = _pipeline_ref.get_status() if _pipeline_ref else {}
    src_name = _dynamic_source_ref.source_name if _dynamic_source_ref else "Default Webcam"
    src_type = _dynamic_source_ref.source_type if _dynamic_source_ref else "webcam"

    # Multi-camera info
    multi_info = {}
    if _multi_camera_mgr:
        multi_info = {
            "multi_camera_active": True,
            "camera_count": _multi_camera_mgr.camera_count,
            "global_track_count": _multi_camera_mgr.global_track_count,
        }

    return {
        "active": status.get("running", False),
        "fps": status.get("fps", 0.0),
        "tracks_count": status.get("tracks_count", 0),
        "is_high_density": status.get("is_high_density", False),
        "has_frame": status.get("has_frame", False),
        "source_name": src_name,
        "source_type": src_type,
        **multi_info,
    }


@router.get("/snapshot")
async def video_snapshot(camera_id: Optional[str] = None):
    """Fetch the latest single annotated JPEG frame."""
    jpeg_bytes = None
    if camera_id and _multi_camera_mgr:
        jpeg_bytes = _multi_camera_mgr.get_camera_jpeg(camera_id)
    elif _pipeline_ref:
        jpeg_bytes = _pipeline_ref.get_latest_jpeg()
    if jpeg_bytes is None:
        jpeg_bytes = _generate_standby_frame()
    return Response(content=jpeg_bytes, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Multi-Camera CRUD
# ---------------------------------------------------------------------------

class AddCameraPayload(BaseModel):
    camera_id: str
    source_type: str  # "webcam", "ip_camera", "mobile_browser"
    display_name: Optional[str] = None
    url: Optional[str] = None
    device_index: Optional[int] = 0


@router.post("/cameras")
async def add_camera(payload: AddCameraPayload):
    """Register and start a new camera source."""
    if not _multi_camera_mgr:
        return {"success": False, "error": "Multi-camera manager not initialized"}

    camera_id = payload.camera_id.strip()
    display_name = payload.display_name or f"Camera {camera_id}"

    source = None
    mobile_src = None

    if payload.source_type == "webcam":
        idx = payload.device_index if payload.device_index is not None else 0
        source = WebcamSource(idx)
        if not source.is_opened():
            return {"success": False, "error": f"Cannot open webcam at index {idx}"}

    elif payload.source_type == "ip_camera":
        if not payload.url or not payload.url.strip():
            return {"success": False, "error": "URL required for IP camera"}
        source = WebcamSource(payload.url.strip())
        if not source.is_opened():
            return {"success": False, "error": f"Cannot connect to {payload.url}"}

    elif payload.source_type == "mobile_browser":
        mobile_src = MobileBrowserFrameSource()
        source = mobile_src
    else:
        return {"success": False, "error": f"Unknown source type: {payload.source_type}"}

    ok = _multi_camera_mgr.add_camera(
        camera_id=camera_id,
        source=source,
        display_name=display_name,
        source_type=payload.source_type,
        mobile_source=mobile_src,
    )

    if ok:
        return {
            "success": True,
            "camera_id": camera_id,
            "display_name": display_name,
            "source_type": payload.source_type,
        }
    return {"success": False, "error": "Camera ID already exists or max cameras reached"}


@router.delete("/cameras/{camera_id}")
async def remove_camera(camera_id: str):
    """Stop and remove a camera."""
    if not _multi_camera_mgr:
        return {"success": False, "error": "Multi-camera manager not initialized"}

    ok = _multi_camera_mgr.remove_camera(camera_id)
    return {"success": ok, "camera_id": camera_id}


@router.get("/cameras")
async def list_cameras():
    """List all active cameras with status info."""
    if not _multi_camera_mgr:
        return {"cameras": [], "total": 0}

    cameras = _multi_camera_mgr.list_cameras()
    return {"cameras": cameras, "total": len(cameras)}


@router.get("/global-tracks")
async def get_global_tracks():
    """Return all globally-tracked persons across all cameras (Re-ID)."""
    if not _multi_camera_mgr:
        return {"tracks": [], "total": 0}

    tracks = _multi_camera_mgr.get_all_global_tracks()
    return {"tracks": tracks, "total": len(tracks)}


# ---------------------------------------------------------------------------
# Mobile Camera Ingestion (Browser -> Edge Hub)
# ---------------------------------------------------------------------------

@router.post("/ingest-frame")
async def ingest_frame(request: Request, camera_id: Optional[str] = None):
    """Receive a raw JPEG frame uploaded from a mobile browser.

    If camera_id is specified and multi-cam is active, routes to that camera's
    mobile source. Otherwise routes to the default mobile source.
    """
    body = await request.body()
    if len(body) == 0:
        return {"success": False, "error": "Empty frame"}

    # Multi-camera mode: route to specific camera's mobile source
    if camera_id and _multi_camera_mgr:
        mob = _multi_camera_mgr.get_camera_mobile_source(camera_id)
        if mob:
            ok = mob.push_frame_bytes(body)
            return {"success": ok, "camera_id": camera_id}

    # Legacy single-camera fallback
    ok = _mobile_source.push_frame_bytes(body)
    if ok and _dynamic_source_ref is not None:
        if _dynamic_source_ref.source_type != "mobile_browser":
            _dynamic_source_ref.switch_source(
                _mobile_source,
                name="Mobile Phone Camera (Live Browser Stream)",
                source_type="mobile_browser",
            )
            logger.info("Auto-switched CV pipeline source to Mobile Phone Camera (HTTP stream)")
    return {"success": ok}


@router.websocket("/ws-stream-in")
async def ws_camera_stream_in(websocket: WebSocket):
    """Low-latency WebSocket channel for mobile browsers streaming video frames."""
    await websocket.accept()

    # Check if a camera_id was specified
    camera_id = websocket.query_params.get("camera_id", None)
    logger.info(f"Mobile camera WebSocket connected (camera_id={camera_id})")

    target_mobile = _mobile_source  # default

    if camera_id and _multi_camera_mgr:
        mob = _multi_camera_mgr.get_camera_mobile_source(camera_id)
        if not mob:
            mob = MobileBrowserFrameSource()
            _multi_camera_mgr.set_camera_mobile_source(camera_id, mob)
        dyn = _multi_camera_mgr.get_camera_dynamic_source(camera_id)
        if dyn and dyn.source_type != "mobile_browser":
            dyn.switch_source(mob, name=f"Mobile Phone Camera ({camera_id})", source_type="mobile_browser")
            logger.info(f"Auto-switched camera '{camera_id}' source to Mobile Phone Camera (WebSocket)")
        target_mobile = mob
    elif _dynamic_source_ref is not None:
        if _dynamic_source_ref.source_type != "mobile_browser":
            _dynamic_source_ref.switch_source(
                _mobile_source,
                name="Mobile Phone Camera (Live Browser Stream)",
                source_type="mobile_browser",
            )
            logger.info("Switched pipeline to Mobile Phone Camera (WebSocket stream)")

    try:
        while True:
            frame_bytes = await websocket.receive_bytes()
            target_mobile.push_frame_bytes(frame_bytes)
    except WebSocketDisconnect:
        logger.info("Mobile camera stream disconnected")
    except Exception as e:
        logger.debug(f"Mobile camera WebSocket error: {e}")


# ---------------------------------------------------------------------------
# Camera Source Switching (Legacy single-camera API, still works)
# ---------------------------------------------------------------------------

class SwitchSourcePayload(BaseModel):
    source_type: str  # "webcam", "ip_camera", or "mobile_browser"
    url: Optional[str] = None
    device_index: Optional[int] = 0


@router.get("/detected-devices")
async def get_detected_devices():
    """List detected local webcam hardware devices."""
    devices = [
        {"index": 0, "name": "Laptop Built-in Webcam (Index 0)"},
        {"index": 1, "name": "External USB Webcam (Index 1)"},
    ]
    return {"devices": devices}


@router.post("/switch-source")
async def switch_camera_source(payload: SwitchSourcePayload):
    """Switch the active video input source dynamically without restarting."""
    if _dynamic_source_ref is None:
        return {"success": False, "error": "Dynamic source controller not initialized"}

    if payload.source_type == "webcam":
        idx = payload.device_index if payload.device_index is not None else 0
        name = "External USB Webcam (Index 1)" if idx == 1 else "Laptop Built-in Webcam (Index 0)" if idx == 0 else f"USB/Camera Device ({idx})"
        try:
            new_src = WebcamSource(idx)
            if not new_src.is_opened():
                return {"success": False, "error": f"Could not open local webcam at index {idx}"}
            _dynamic_source_ref.switch_source(new_src, name=name, source_type="webcam")
            logger.info(f"Switched pipeline source to {name}")
            return {"success": True, "source_name": name, "source_type": "webcam"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif payload.source_type == "ip_camera":
        if not payload.url or not payload.url.strip():
            return {"success": False, "error": "Please provide a valid IP camera stream URL (e.g. http://192.168.1.50:8080/video)"}
        clean_url = payload.url.strip()
        try:
            new_src = WebcamSource(clean_url)
            if not new_src.is_opened():
                return {
                    "success": False,
                    "error": f"Could not connect to stream at {clean_url}. Ensure your mobile app (e.g. IP Webcam) is broadcasting and your PC and phone are on the same Wi-Fi.",
                }
            _dynamic_source_ref.switch_source(new_src, name=f"Network Camera ({clean_url})", source_type="ip_camera")
            logger.info(f"Switched pipeline source to Network Camera: {clean_url}")
            return {"success": True, "source_name": clean_url, "source_type": "ip_camera"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif payload.source_type == "mobile_browser":
        _dynamic_source_ref.switch_source(
            _mobile_source,
            name="Mobile Phone Camera (Live Browser Stream)",
            source_type="mobile_browser",
        )
        logger.info("Switched pipeline source to Mobile Phone Camera (Browser)")
        return {"success": True, "source_name": "Mobile Phone Camera (Browser)", "source_type": "mobile_browser"}

    return {"success": False, "error": f"Unsupported source type: {payload.source_type}"}
