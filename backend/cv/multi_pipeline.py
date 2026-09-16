"""
IntelliSales -- Multi-Camera Pipeline Manager

Orchestrates N parallel AnalyticsPipeline instances, one per camera,
with a central GlobalTrackRegistry for cross-camera Re-ID.

Each camera pipeline runs in its own daemon thread.  The manager provides:
  - add_camera / remove_camera for dynamic camera management
  - Merged global track lists for API/WebSocket broadcast
  - Per-camera and composite grid MJPEG feeds
  - Periodic stale-track cleanup

Hardware-agnostic: works on laptop (multi-webcam/phone) or edge board farm.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import MAX_CAMERAS, CALIBRATION_DIR, get_video_source
from backend.cv.calibration import CameraCalibrator
from backend.cv.grid import FloorGrid
from backend.cv.pipeline import (
    AnalyticsPipeline, FrameResult, FrameSource,
    WebcamSource, SyntheticStoreSource, DynamicFrameSource,
    MobileBrowserFrameSource,
)
from backend.cv.reid import GlobalTrackRegistry, global_registry

logger = logging.getLogger("intellisales.cv.multi")


# ---------------------------------------------------------------------------
# Per-Camera State
# ---------------------------------------------------------------------------

@dataclass
class CameraState:
    """Internal bookkeeping for one active camera."""
    camera_id: str
    display_name: str
    source_type: str  # "webcam", "ip_camera", "mobile_browser"
    pipeline: AnalyticsPipeline
    dynamic_source: DynamicFrameSource
    mobile_source: Optional[MobileBrowserFrameSource]
    thread: Optional[threading.Thread] = None
    running: bool = False
    latest_jpeg: Optional[bytes] = None
    latest_annotated: Optional[np.ndarray] = None
    latest_result: Optional[FrameResult] = None
    tracks_count: int = 0
    fps: float = 0.0


# ---------------------------------------------------------------------------
# Multi-Camera Manager
# ---------------------------------------------------------------------------

class MultiCameraManager:
    """Manages N concurrent camera pipelines with cross-camera Re-ID.

    Usage:
        mgr = MultiCameraManager(on_frame_result=callback)
        mgr.add_camera("cam0", WebcamSource(0), "Laptop Webcam", "webcam")
        mgr.add_camera("cam1", WebcamSource("http://phone:8080/video"), "Phone", "ip_camera")
        # ... later
        mgr.remove_camera("cam1")
        mgr.shutdown()
    """

    def __init__(
        self,
        registry: Optional[GlobalTrackRegistry] = None,
        on_frame_result: Optional[Callable[[str, FrameResult], None]] = None,
    ):
        self._registry = registry or global_registry
        self._on_frame_result = on_frame_result  # (camera_id, result) callback
        self._cameras: Dict[str, CameraState] = {}
        self._lock = threading.Lock()

        # Cleanup thread for stale global tracks
        self._cleanup_running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="reid-cleanup"
        )
        self._cleanup_thread.start()

        # Grid composite frame cache
        self._grid_jpeg: Optional[bytes] = None
        self._last_grid_build: float = 0.0
        self._grid_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Camera lifecycle
    # ------------------------------------------------------------------

    def add_camera(
        self,
        camera_id: str,
        source: FrameSource,
        display_name: str = "",
        source_type: str = "webcam",
        mobile_source: Optional[MobileBrowserFrameSource] = None,
    ) -> bool:
        """Add and start a new camera pipeline.

        Returns True on success, False if camera_id already exists or max reached.
        """
        with self._lock:
            if camera_id in self._cameras:
                logger.warning(f"Camera '{camera_id}' already exists")
                return False
            if len(self._cameras) >= MAX_CAMERAS:
                logger.warning(f"Max cameras ({MAX_CAMERAS}) reached")
                return False

        if not display_name:
            display_name = f"Camera {camera_id}"

        # Load calibration if available
        cal = None
        cal_path = CALIBRATION_DIR / f"{camera_id}.json"
        if not cal_path.exists():
            cal_path = CALIBRATION_DIR / "cam0.json"
        if cal_path.exists():
            try:
                cal = CameraCalibrator.load(cal_path)
            except Exception:
                pass

        grid = FloorGrid()

        # Create per-camera pipeline with Re-ID registry wired directly
        pipeline = AnalyticsPipeline(
            calibrator=cal,
            grid=grid,
            on_frame_result=lambda result, cid=camera_id: self._handle_camera_result(cid, result),
            camera_id=camera_id,
            reid_registry=self._registry,
        )

        dynamic = DynamicFrameSource(source, name=display_name)

        state = CameraState(
            camera_id=camera_id,
            display_name=display_name,
            source_type=source_type,
            pipeline=pipeline,
            dynamic_source=dynamic,
            mobile_source=mobile_source,
            running=True,
        )

        with self._lock:
            self._cameras[camera_id] = state

        # Start pipeline thread
        thread = threading.Thread(
            target=self._run_camera,
            args=(state,),
            daemon=True,
            name=f"pipeline-{camera_id}",
        )
        state.thread = thread
        thread.start()

        logger.info(f"[MultiCam] Started camera '{camera_id}' ({display_name}, {source_type})")
        return True

    def remove_camera(self, camera_id: str) -> bool:
        """Stop and remove a camera pipeline."""
        with self._lock:
            state = self._cameras.pop(camera_id, None)

        if state is None:
            return False

        state.running = False
        state.pipeline.stop()
        if state.dynamic_source:
            try:
                state.dynamic_source.release()
            except Exception:
                pass

        logger.info(f"[MultiCam] Removed camera '{camera_id}'")
        return True

    def shutdown(self) -> None:
        """Stop all cameras and cleanup."""
        self._cleanup_running = False
        with self._lock:
            cam_ids = list(self._cameras.keys())
        for cid in cam_ids:
            self.remove_camera(cid)

    # ------------------------------------------------------------------
    # Camera pipeline thread
    # ------------------------------------------------------------------

    def _run_camera(self, state: CameraState) -> None:
        """Run a single camera's pipeline loop in its own thread."""
        try:
            while state.running:
                ret, frame = state.dynamic_source.read()
                if not ret or frame is None:
                    time.sleep(0.02)
                    continue

                result = state.pipeline.process_frame(frame)

                # Update state
                state.latest_result = result
                state.tracks_count = len(result.tracked_persons)
                state.latest_jpeg = state.pipeline.get_latest_jpeg()
                state.latest_annotated = state.pipeline.get_latest_annotated()

                fps_status = state.pipeline.get_status()
                state.fps = fps_status.get("fps", 0.0)

        except Exception as e:
            logger.error(f"[MultiCam] Camera '{state.camera_id}' error: {e}", exc_info=True)
        finally:
            state.running = False
            logger.info(f"[MultiCam] Camera '{state.camera_id}' loop ended")

    def _handle_camera_result(self, camera_id: str, result: FrameResult) -> None:
        """Called by each camera's pipeline after processing a frame."""
        if self._on_frame_result:
            self._on_frame_result(camera_id, result)

    # ------------------------------------------------------------------
    # Grid composite (on-demand, zero-imdecode)
    # ------------------------------------------------------------------

    def get_grid_jpeg(self) -> Optional[bytes]:
        """Get or dynamically generate composite grid JPEG without redundant decoding."""
        now = time.time()
        with self._grid_lock:
            if self._grid_jpeg is not None and (now - self._last_grid_build) < 0.04:
                return self._grid_jpeg

        with self._lock:
            camera_list = list(self._cameras.values())

        if not camera_list:
            return None

        n = len(camera_list)
        cols = min(n, 2)
        rows = math.ceil(n / cols)

        cell_w, cell_h = 480, 360
        grid_w = cols * cell_w
        grid_h = rows * cell_h

        grid = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
        grid[:] = (12, 16, 24)

        for idx, cam in enumerate(camera_list):
            r = idx // cols
            c = idx % cols
            y_off = r * cell_h
            x_off = c * cell_w

            # Fast path: use raw numpy frame directly -- ZERO imdecode overhead!
            img = cam.latest_annotated
            if img is not None:
                resized = cv2.resize(img, (cell_w, cell_h), interpolation=cv2.INTER_LINEAR)
                grid[y_off:y_off + cell_h, x_off:x_off + cell_w] = resized
            else:
                card_cx = x_off + cell_w // 2
                card_cy = y_off + cell_h // 2
                subtext = "WAITING FOR CAMERA INPUT..."
                if cam.source_type == "mobile_browser":
                    subtext = "WAITING FOR MOBILE STREAM"
                elif cam.source_type == "ip_camera":
                    subtext = "CONNECTING TO IP STREAM..."

                cv2.rectangle(grid, (x_off + 40, card_cy - 40), (x_off + cell_w - 40, card_cy + 40), (22, 28, 42), -1)
                cv2.rectangle(grid, (x_off + 40, card_cy - 40), (x_off + cell_w - 40, card_cy + 40), (0, 215, 255), 1)
                t1_size = cv2.getTextSize(subtext, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
                cv2.putText(grid, subtext, (card_cx - t1_size[0] // 2, card_cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1, cv2.LINE_AA)

            # Camera label overlay
            label = f"{cam.display_name} [{cam.camera_id}]"
            cv2.rectangle(grid, (x_off, y_off), (x_off + cell_w, y_off + 26), (10, 14, 22), -1)
            cv2.putText(grid, label, (x_off + 8, y_off + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 215, 255), 1, cv2.LINE_AA)

            count_text = f"Tracks: {cam.tracks_count} | FPS: {cam.fps:.0f}"
            cv2.putText(grid, count_text, (x_off + cell_w - 180, y_off + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 235, 120), 1, cv2.LINE_AA)
            cv2.rectangle(grid, (x_off, y_off), (x_off + cell_w - 1, y_off + cell_h - 1), (40, 50, 70), 1)

        _, buf = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 72])
        with self._grid_lock:
            self._grid_jpeg = buf.tobytes()
            self._last_grid_build = now
            return self._grid_jpeg


    # ------------------------------------------------------------------
    # Cleanup loop
    # ------------------------------------------------------------------

    def _cleanup_loop(self) -> None:
        """Periodically clean stale global tracks."""
        while self._cleanup_running:
            time.sleep(10.0)
            try:
                self._registry.cleanup_stale()
            except Exception as e:
                logger.debug(f"[Re-ID cleanup] Error: {e}")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_camera_jpeg(self, camera_id: str) -> Optional[bytes]:
        """Get latest JPEG for a specific camera."""
        with self._lock:
            state = self._cameras.get(camera_id)
        if state:
            return state.latest_jpeg
        return None


    def get_camera_dynamic_source(self, camera_id: str) -> Optional[DynamicFrameSource]:
        """Get the DynamicFrameSource for a camera (for hot-swapping)."""
        with self._lock:
            state = self._cameras.get(camera_id)
        return state.dynamic_source if state else None

    def get_camera_mobile_source(self, camera_id: str) -> Optional[MobileBrowserFrameSource]:
        """Get the MobileBrowserFrameSource for a camera."""
        with self._lock:
            state = self._cameras.get(camera_id)
        return state.mobile_source if state else None

    def set_camera_mobile_source(self, camera_id: str, mobile_source: MobileBrowserFrameSource) -> None:
        """Set the MobileBrowserFrameSource for a camera."""
        with self._lock:
            state = self._cameras.get(camera_id)
            if state:
                state.mobile_source = mobile_source
                state.source_type = "mobile_browser"

    def get_camera_pipeline(self, camera_id: str) -> Optional[AnalyticsPipeline]:
        """Get the pipeline instance for a specific camera."""
        with self._lock:
            state = self._cameras.get(camera_id)
        return state.pipeline if state else None

    def list_cameras(self) -> List[Dict[str, Any]]:
        """List all active cameras with status info."""
        with self._lock:
            cameras = list(self._cameras.values())
        return [
            {
                "camera_id": c.camera_id,
                "display_name": c.display_name,
                "source_type": c.source_type,
                "running": c.running,
                "tracks_count": c.tracks_count,
                "fps": round(c.fps, 1),
                "has_frame": c.latest_jpeg is not None,
            }
            for c in cameras
        ]

    def get_all_global_tracks(self) -> List[Dict]:
        """Return all globally-tracked persons across cameras."""
        return self._registry.get_all_global_tracks()

    def get_global_id_for_local(self, camera_id: str, local_track_id: int) -> Optional[int]:
        return self._registry.get_global_id_for_local(camera_id, local_track_id)

    @property
    def camera_count(self) -> int:
        with self._lock:
            return len(self._cameras)

    @property
    def global_track_count(self) -> int:
        return self._registry.active_count
