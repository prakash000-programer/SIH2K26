"""
IntelliSales -- Analytics Pipeline Orchestrator

Connects all CV modules into a single frame-processing pipeline:
    frame (numpy) -> detect -> track -> calibrate -> grid -> dwell -> footfall -> density

Hardware-agnostic design:
  - The pipeline accepts frames as numpy arrays -- it does NOT own the capture
    device. A separate FrameSource abstraction handles webcam, video file,
    or future QCS6490 camera input.
  - All modules are injected via constructor, so any component can be swapped
    without changing this file.

Privacy:
  - Raw video frames are NEVER written to disk or persistently stored.
  - An in-memory annotated JPEG buffer is kept in RAM solely for real-time
    operator streaming (HTTP MJPEG feed) and discarded immediately when overwritten.
"""

from __future__ import annotations

import math
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import load_footfall_line
from backend.cv.calibration import CameraCalibrator
from backend.cv.density import DensityMonitor, DensitySnapshot
from backend.cv.dwell import DwellEvent, DwellTracker
from backend.cv.footfall import FootfallEvent, LineCounter
from backend.cv.grid import FloorGrid
from backend.cv.tracker import PersonTracker, TrackedPerson
from backend.cv.gender import GenderClassifier



# ---------------------------------------------------------------------------
# Frame source abstraction
# ---------------------------------------------------------------------------

class FrameSource(Protocol):
    """Abstract frame source. Implementations provide frames from any input."""
    def read(self) -> Tuple[bool, Optional[np.ndarray]]: ...
    def release(self) -> None: ...
    def is_opened(self) -> bool: ...


class WebcamSource:
    """High-performance frame source for webcams and IP cameras with background thread grabbing.

    Uses an independent daemon grabber thread to bypass OpenCV's internal 30+ frame buffer,
    ensuring read() always returns the immediate real-time frame with 0ms delay and zero lag.
    """

    def __init__(self, source: int | str = 0):
        self._source = source
        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._running = True
        self._lock = threading.Lock()
        self._opened = False
        self._is_network = isinstance(source, str) and (
            "://" in source or source.endswith(".mjpg") or source.endswith(".mjpeg")
        )

        self._init_capture(source)

        # Background frame grabber thread for zero-latency streaming
        self._thread = threading.Thread(
            target=self._grab_loop,
            daemon=True,
            name=f"cam-grab-{source}",
        )
        self._thread.start()

    def _init_capture(self, source: int | str):
        if self._is_network:
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|max_delay;0"

        # On Windows, use CAP_DSHOW for local USB webcams to avoid MSMF errors
        if isinstance(source, int) and sys.platform == "win32":
            cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self._cap = cap
                self._opened = True
                return

        cap = cv2.VideoCapture(source)
        if cap and cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if isinstance(source, int):
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._cap = cap
            self._opened = True

    def _grab_loop(self):
        """Continuously grab the latest camera frame into memory, discarding stale queue frames."""
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                time.sleep(0.05)
                continue

            ret, frame = self._cap.read()
            if ret and frame is not None:
                # Downsample large 1080p/4K network streams to 640px for ultra-high FPS edge inference
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640.0 / w
                    frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_LINEAR)
                with self._lock:
                    self._latest_frame = frame
            else:
                time.sleep(0.01)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self._lock:
            if self._latest_frame is not None:
                return True, self._latest_frame
        return False, None

    def release(self) -> None:
        self._running = False
        cap = self._cap
        self._cap = None
        self._opened = False

        def _async_release(c):
            if c:
                try:
                    c.release()
                except Exception:
                    pass

        # Release capture device in background thread to avoid freezing the caller for 2-5s
        threading.Thread(target=_async_release, args=(cap,), daemon=True).start()

    def is_opened(self) -> bool:
        return self._opened

    @property
    def fps(self) -> float:
        if self._cap:
            val = self._cap.get(cv2.CAP_PROP_FPS)
            if val and val > 0:
                return val
        return 30.0


class MobileBrowserFrameSource:
    """Frame source receiving real-time video frames streamed from a mobile device browser."""

    def __init__(self):
        self._latest_frame: Optional[np.ndarray] = None
        self._last_received_time: float = 0.0
        self._new_frame_event = threading.Event()
        self._lock = threading.Lock()

    def push_frame_bytes(self, frame_bytes: bytes) -> bool:
        """Decode and buffer JPEG bytes received from mobile WebSocket / HTTP."""
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            # Downsample if mobile device sent a full-res 1080p frame
            h, w = img.shape[:2]
            if w > 640:
                scale = 640.0 / w
                img = cv2.resize(img, (640, int(h * scale)), interpolation=cv2.INTER_LINEAR)
            with self._lock:
                self._latest_frame = img
                self._last_received_time = time.time()
                self._new_frame_event.set()
            return True
        return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        # Check if fresh frame arrived or recent frame is available
        with self._lock:
            if self._latest_frame is not None and (time.time() - self._last_received_time) < 3.0:
                self._new_frame_event.clear()
                return True, self._latest_frame
        # Short wait if waiting for initial stream start
        if self._new_frame_event.wait(timeout=0.02):
            with self._lock:
                self._new_frame_event.clear()
                if self._latest_frame is not None and (time.time() - self._last_received_time) < 3.0:
                    return True, self._latest_frame
        return False, None

    def release(self) -> None:
        with self._lock:
            self._latest_frame = None
            self._new_frame_event.clear()

    def is_opened(self) -> bool:
        with self._lock:
            return (time.time() - self._last_received_time) < 5.0

    @property
    def fps(self) -> float:
        return 30.0


class DynamicFrameSource:
    """Thread-safe dynamic wrapper that allows hot-swapping the active camera input
    (e.g., switching from PC webcam -> Mobile Phone Camera -> IP Camera URL)
    without restarting the CV pipeline loop.
    """

    def __init__(self, initial_source: FrameSource, name: str = "Webcam 0"):
        self._current_source = initial_source
        self._source_name = name
        self._source_type = "webcam"
        self._lock = threading.Lock()

    def switch_source(self, new_source: FrameSource, name: str, source_type: str = "webcam") -> None:
        with self._lock:
            old = self._current_source
            self._current_source = new_source
            self._source_name = name
            self._source_type = source_type

        # Asynchronously release old source in background thread -- ZERO lag on camera switch!
        if old is not None and old is not new_source:
            def _safe_release(s):
                try:
                    s.release()
                except Exception:
                    pass
            threading.Thread(target=_safe_release, args=(old,), daemon=True).start()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self._lock:
            if self._current_source is not None:
                return self._current_source.read()
            return False, None

    def release(self) -> None:
        with self._lock:
            if self._current_source is not None:
                self._current_source.release()

    def is_opened(self) -> bool:
        with self._lock:
            if self._current_source is not None:
                return self._current_source.is_opened()
            return False

    @property
    def source_name(self) -> str:
        with self._lock:
            return self._source_name

    @property
    def source_type(self) -> str:
        with self._lock:
            return self._source_type

    @property
    def fps(self) -> float:
        with self._lock:
            if hasattr(self._current_source, "fps"):
                return self._current_source.fps
            return 30.0


class SyntheticStoreSource:
    """Fallback frame source: generates a simulated retail store camera feed
    with simulated shoppers walking across aisles when no physical camera is attached.
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._step = 0
        self._start_time = time.time()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        self._step += 1
        elapsed = time.time() - self._start_time

        # Create floor/aisle background
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Store floor tone
        frame[:] = (35, 42, 54)  # BGR dark navy slate

        # Draw retail tile grid lines
        for y in range(0, self.height, 40):
            cv2.line(frame, (0, y), (self.width, y), (45, 55, 70), 1)
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height), (45, 55, 70), 1)

        # Draw shelf sections
        # Left Aisle: Apparel
        cv2.rectangle(frame, (20, 60), (160, 360), (60, 50, 40), -1)
        cv2.putText(frame, "APPAREL ZONE", (35, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 200), 1)

        # Right Aisle: Grocery
        cv2.rectangle(frame, (480, 60), (620, 360), (40, 55, 45), -1)
        cv2.putText(frame, "GROCERY ZONE", (495, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 200, 180), 1)

        # Draw simulated shoppers moving realistically
        # Person 1: browsing apparel
        p1_x = int(220 + 30 * math.sin(elapsed * 0.8))
        p1_y = int(180 + 20 * math.cos(elapsed * 0.8))
        self._draw_simulated_person(frame, p1_x, p1_y, color=(200, 140, 60))

        # Person 2: walking through center towards checkout
        p2_x = int(320 + 60 * math.sin(elapsed * 0.4))
        p2_y = int(100 + (elapsed * 35) % 320)
        self._draw_simulated_person(frame, p2_x, p2_y, color=(80, 160, 220))

        # Person 3: browsing grocery
        p3_x = int(430 + 15 * math.cos(elapsed * 0.5))
        p3_y = int(240 + 40 * math.sin(elapsed * 0.5))
        self._draw_simulated_person(frame, p3_x, p3_y, color=(140, 200, 100))

        time.sleep(0.033)  # ~30 FPS
        return True, frame

    def _draw_simulated_person(self, frame: np.ndarray, cx: int, cy: int, color=(180, 180, 180)):
        # Person silhouette: head + torso + legs
        cv2.circle(frame, (cx, cy - 35), 14, color, -1)  # Head
        cv2.ellipse(frame, (cx, cy), (18, 28), 0, 0, 360, color, -1)  # Torso
        cv2.rectangle(frame, (cx - 14, cy + 24), (cx + 14, cy + 50), color, -1)  # Legs

    def release(self) -> None:
        pass

    def is_opened(self) -> bool:
        return True

    @property
    def fps(self) -> float:
        return 30.0


# ---------------------------------------------------------------------------
# Pipeline output events
# ---------------------------------------------------------------------------

@dataclass
class FrameResult:
    """Aggregated result from processing one frame."""
    timestamp: float
    tracked_persons: List[TrackedPerson]
    dwell_events: List[DwellEvent]
    footfall_events: List[FootfallEvent]
    density_snapshot: Optional[DensitySnapshot]
    is_high_density: bool
    heatmap_cells: Dict[Tuple[int, int], int]  # cell -> detection count this frame
    camera_id: str = "cam0"                    # which camera produced this result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class AnalyticsPipeline:
    """Orchestrates the full CV analytics pipeline with live HUD annotation."""

    def __init__(
        self,
        calibrator: Optional[CameraCalibrator] = None,
        grid: Optional[FloorGrid] = None,
        tracker: Optional[PersonTracker] = None,
        dwell_tracker: Optional[DwellTracker] = None,
        footfall_counter: Optional[LineCounter] = None,
        density_monitor: Optional[DensityMonitor] = None,
        on_frame_result: Optional[Callable[[FrameResult], None]] = None,
        camera_id: str = "cam0",
        reid_registry: Optional[Any] = None,
    ):
        self._calibrator = calibrator
        self._grid = grid or FloorGrid()
        self._tracker = tracker or PersonTracker()
        self._dwell_tracker = dwell_tracker or DwellTracker()
        self._density_monitor = density_monitor or DensityMonitor()
        self._camera_id = camera_id
        self._reid_registry = reid_registry

        if footfall_counter is None:
            line_cfg = load_footfall_line()
            if line_cfg:
                self._footfall_counter = LineCounter(
                    point_a=tuple(line_cfg["point_a"]),
                    point_b=tuple(line_cfg["point_b"]),
                    inward_direction=tuple(line_cfg["inward_direction"]),
                )
            else:
                self._footfall_counter = None
        else:
            self._footfall_counter = footfall_counter

        self._on_frame_result = on_frame_result
        self._running = False

        # Edge Gender Classifier & Dwell Time Tracker
        self._gender_classifier = GenderClassifier()
        self._track_first_seen: Dict[int, float] = {}

        # Live streaming frame buffer (in-memory only)
        self._latest_jpeg: Optional[bytes] = None
        self._latest_annotated: Optional[np.ndarray] = None
        self._latest_result: Optional[FrameResult] = None
        self._frame_lock = threading.Lock()
        self._frame_count = 0
        self._start_time = time.time()
        self._current_fps = 0.0

    def process_frame(self, frame: np.ndarray, current_time: Optional[float] = None) -> FrameResult:
        """Process a single frame through the full pipeline with maximized FPS."""
        now = current_time if current_time is not None else time.time()

        # Update FPS calculation
        self._frame_count += 1
        elapsed = now - self._start_time
        if elapsed >= 1.0:
            self._current_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._start_time = now

        # Normalize frame dimensions to max 640px width for 3x faster detection throughput
        h, w = frame.shape[:2]
        if w > 640:
            scale = 640.0 / w
            frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_LINEAR)
            h, w = frame.shape[:2]

        # 1. Detection + Tracking
        tracked_persons = self._tracker.update(frame)

        # 1b. Live Continuous Dwell Time, Edge Gender Classification & Global Re-ID
        current_track_ids = set()
        for person in tracked_persons:
            current_track_ids.add(person.track_id)
            if person.track_id not in self._track_first_seen:
                self._track_first_seen[person.track_id] = now
            person.dwell_time_s = max(0.0, now - self._track_first_seen[person.track_id])

            gender, g_conf = self._gender_classifier.predict(frame, person.bbox, person.track_id)
            person.gender = gender
            person.gender_confidence = g_conf

            # Direct Re-ID association before HUD annotation
            if self._reid_registry is not None:
                x1, y1, x2, y2 = [int(v) for v in person.bbox]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                if x2 > x1 and y2 > y1:
                    crop = frame[y1:y2, x1:x2]
                    person.global_id = self._reid_registry.match_or_create(
                        camera_id=self._camera_id,
                        local_track_id=person.track_id,
                        person_crop=crop,
                        gender=person.gender,
                        gender_confidence=person.gender_confidence,
                        dwell_time_s=person.dwell_time_s,
                        current_time=now,
                    )

        # Clean up tracks that have exited for > 15s
        stale_tracks = [
            tid for tid in list(self._track_first_seen.keys())
            if tid not in current_track_ids and (now - self._track_first_seen[tid]) > 15.0
        ]
        for tid in stale_tracks:
            self._track_first_seen.pop(tid, None)
            self._gender_classifier.cleanup_track(tid)

        # 2. Calibrate: pixel -> world coordinates
        if self._calibrator and self._calibrator.is_calibrated:
            for person in tracked_persons:
                px, py = person.centroid_px
                wx, wy = self._calibrator.pixel_to_world(px, py)
                person.centroid_world = (wx, wy)

        # 3. Grid assignment
        cell_assignments: List[Tuple[int, Tuple[int, int]]] = []
        track_positions_for_dwell: List[Tuple[int, Tuple[int, int], Optional[str]]] = []
        track_positions_for_footfall: List[Tuple[int, Tuple[float, float]]] = []
        heatmap_cells: Dict[Tuple[int, int], int] = {}

        for person in tracked_persons:
            if person.centroid_world is not None:
                wx, wy = person.centroid_world
                cell = self._grid.get_cell(wx, wy)
                zone = self._grid.get_zone(*cell)

                cell_assignments.append((person.track_id, cell))
                track_positions_for_dwell.append((person.track_id, cell, zone))
                track_positions_for_footfall.append((person.track_id, (wx, wy)))
                heatmap_cells[cell] = heatmap_cells.get(cell, 0) + 1

        # 4. Crowd density check
        is_high_density, density_snapshot = self._density_monitor.check(
            cell_assignments, current_time=now
        )

        # 5. Dwell-time update
        dwell_events: List[DwellEvent] = []
        if not is_high_density:
            dwell_events = self._dwell_tracker.update(
                track_positions_for_dwell, current_time=now
            )

        # 6. Footfall check
        footfall_events: List[FootfallEvent] = []
        if self._footfall_counter and track_positions_for_footfall:
            footfall_events = self._footfall_counter.update(
                track_positions_for_footfall, current_time=now
            )

        result = FrameResult(
            timestamp=now,
            tracked_persons=tracked_persons,
            dwell_events=dwell_events,
            footfall_events=footfall_events,
            density_snapshot=density_snapshot,
            is_high_density=is_high_density,
            heatmap_cells=heatmap_cells,
            camera_id=self._camera_id,
        )

        # 7. Render live HUD annotation and encode to JPEG for web streaming
        annotated = self.annotate_frame(frame, result)
        ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 68])
        if ret:
            with self._frame_lock:
                self._latest_jpeg = jpeg.tobytes()
                self._latest_annotated = annotated
                self._latest_result = result

        # Callback for async persistence & websocket broadcast
        if self._on_frame_result:
            self._on_frame_result(result)

        return result

    def annotate_frame(self, frame: np.ndarray, result: FrameResult) -> np.ndarray:
        """Render high-tech surveillance HUD with bounding boxes and tracking metrics."""
        annotated = frame.copy()
        h, w, _ = annotated.shape

        # 1. Footfall Entry/Exit Line if present
        pt_y = int(h * 0.78)
        cv2.line(annotated, (int(w * 0.05), pt_y), (int(w * 0.95), pt_y), (0, 215, 255), 2, cv2.LINE_AA)
        cv2.putText(
            annotated,
            "[ STORE ENTRY / EXIT THRESHOLD LINE ]",
            (int(w * 0.22), pt_y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 215, 255),
            1,
            cv2.LINE_AA,
        )

        # 2. Draw Tracked Shoppers
        for person in result.tracked_persons:
            x1, y1, x2, y2 = [int(v) for v in person.bbox]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            box_color = (0, 0, 255) if result.is_high_density else (0, 235, 120)  # Vibrant green/red

            # Main Bounding Box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)

            # High-tech corner accents
            corner = min(12, (x2 - x1) // 3, (y2 - y1) // 3)
            if corner > 3:
                cv2.line(annotated, (x1, y1), (x1 + corner, y1), (255, 255, 255), 2)
                cv2.line(annotated, (x1, y1), (x1, y1 + corner), (255, 255, 255), 2)
                cv2.line(annotated, (x2, y2), (x2 - corner, y2), (255, 255, 255), 2)
                cv2.line(annotated, (x2, y2), (x2, y2 - corner), (255, 255, 255), 2)

            # Centroid point
            cx, cy = int(person.centroid_px[0]), int(person.centroid_px[1])
            cv2.circle(annotated, (cx, cy), 4, (0, 255, 255), -1)

            # Header tag: ID | Gender | Dwell Time
            dwell_str = f"{person.dwell_time_s:.1f}s"
            gid_str = f"G#{person.global_id}" if person.global_id > 0 else ""
            label = f"{gid_str} ID#{person.track_id} | {person.gender} | {dwell_str}"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            tag_y1 = max(0, y1 - th - 9)
            tag_y2 = y1
            cv2.rectangle(annotated, (x1, tag_y1), (x1 + tw + 12, tag_y2), (15, 20, 30), -1)
            cv2.rectangle(annotated, (x1, tag_y1), (x1 + tw + 12, tag_y2), box_color, 1)
            cv2.putText(
                annotated,
                label,
                (x1 + 6, tag_y2 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        # 3. Top Status HUD Bar (fast direct filled rect instead of heavy addWeighted)
        cv2.rectangle(annotated, (0, 0), (w, 28), (14, 18, 26), -1)

        # Pulsing Live indicator
        cv2.circle(annotated, (12, 16), 5, (0, 235, 120), -1)
        cam_label = f"CAM:{self._camera_id.upper()} • " if self._camera_id != "cam0" else ""
        hud_text = f"LIVE {cam_label}QUALCOMM QCS6490 EDGE • TRACKS: {len(result.tracked_persons)}"
        cv2.putText(
            annotated,
            hud_text,
            (24, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        time_str = time.strftime("%H:%M:%S")
        fps_text = f"FPS: {self._current_fps:.1f} | {time_str}"
        (fw, _), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.putText(
            annotated,
            fps_text,
            (w - fw - 10, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 215, 255),
            1,
            cv2.LINE_AA,
        )

        # 4. Bottom Qualcomm Edge Target Watermark (matches SIH prototype UI)
        bottom_badge = "QUALCOMM QCS6490 TARGET • Zero Disk Storage"
        (bw, bh), _ = cv2.getTextSize(bottom_badge, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
        bx1, by1 = 12, h - 34
        bx2, by2 = bx1 + bw + 18, h - 10
        cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (16, 20, 28), -1)
        cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (45, 55, 75), 1)
        cv2.circle(annotated, (bx1 + 10, by1 + (by2 - by1) // 2), 3, (0, 215, 255), -1)
        cv2.putText(
            annotated,
            bottom_badge,
            (bx1 + 20, by2 - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            (230, 230, 240),
            1,
            cv2.LINE_AA,
        )

        return annotated

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Return the latest annotated frame as JPEG bytes (thread-safe)."""
        with self._frame_lock:
            return self._latest_jpeg

    def get_latest_annotated(self) -> Optional[np.ndarray]:
        """Return the latest annotated frame as a raw numpy array (thread-safe)."""
        with self._frame_lock:
            return self._latest_annotated.copy() if self._latest_annotated is not None else None

    def get_status(self) -> Dict[str, Any]:
        """Return pipeline operational status."""
        with self._frame_lock:
            tracks_count = len(self._latest_result.tracked_persons) if self._latest_result else 0
            is_high = self._latest_result.is_high_density if self._latest_result else False
        return {
            "running": self._running,
            "fps": round(self._current_fps, 1),
            "tracks_count": tracks_count,
            "is_high_density": is_high,
            "has_frame": self._latest_jpeg is not None,
        }

    def run_loop(self, source: FrameSource, show_preview: bool = False) -> None:
        """Run the pipeline continuously on a FrameSource."""
        self._running = True

        try:
            while self._running:
                ret, frame = source.read()
                if not ret or frame is None:
                    # Frame source waiting or switching (e.g. mobile reconnecting)
                    time.sleep(0.04)
                    continue

                result = self.process_frame(frame)

                if show_preview:
                    self._draw_preview(frame, result)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
        finally:
            source.release()
            if show_preview:
                cv2.destroyAllWindows()
            self._running = False

    def stop(self) -> None:
        self._running = False

    def _draw_preview(self, frame: np.ndarray, result: FrameResult) -> None:
        cv2.imshow("IntelliSales - Pipeline Preview", self.annotate_frame(frame, result))
