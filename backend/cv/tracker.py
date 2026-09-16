"""
IntelliSales -- ByteTrack Tracker Wrapper

Uses Ultralytics' built-in ByteTrack integration via model.track()
to assign ephemeral track IDs to detected persons across frames.

Track IDs are:
  - Ephemeral: only valid for the current session (camera-on to camera-off)
  - Never persisted beyond the in-memory tracker state
  - Never linked to any stored identity

Hardware-agnostic: accepts a numpy frame, returns tracked persons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from ultralytics import YOLO

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import MODEL_PATH, PERSON_CLASS_ID, DETECTION_CONFIDENCE


import torch

# Limit PyTorch CPU threads per tracker to avoid thrashing, allowing 4 threads on modern multi-core CPUs
try:
    if torch.get_num_threads() > 4:
        torch.set_num_threads(4)
except Exception:
    pass


@dataclass
class TrackedPerson:
    """A person detection with an assigned ephemeral track ID."""
    track_id: int                                  # ephemeral, session-only
    bbox: tuple[float, float, float, float]        # (x1, y1, x2, y2) pixels
    confidence: float
    centroid_px: tuple[float, float]               # (cx, cy) pixels
    centroid_world: Optional[tuple[float, float]] = None  # (wx, wy) metres (set after calibration)
    gender: str = "Unknown"                        # "Male", "Female", or "Unknown"
    gender_confidence: float = 0.0
    dwell_time_s: float = 0.0                      # continuous dwell time in seconds
    global_id: int = -1                            # cross-camera Re-ID global ID (-1 = unassigned)



class PersonTracker:
    """ByteTrack-based person tracker via Ultralytics.

    Usage:
        tracker = PersonTracker()
        # Call update() once per frame, in sequence:
        tracked = tracker.update(frame)
    """

    def __init__(self, model_path: str = MODEL_PATH, confidence: float = DETECTION_CONFIDENCE):
        self._model = YOLO(model_path)
        self._confidence = confidence
        self._person_class_id = PERSON_CLASS_ID
        self._frame_count = 0
        self._last_tracked: List[TrackedPerson] = []

    def update(self, frame: np.ndarray) -> List[TrackedPerson]:
        """Run detection + tracking on one frame.

        Must be called sequentially on consecutive frames for tracking to work.

        Args:
            frame: BGR numpy array (H, W, 3).

        Returns:
            List of TrackedPerson with ephemeral track IDs.
        """
        self._frame_count += 1

        # Frame-stride: On alternate frames when tracks are active, reuse previous tracking
        # to double FPS throughput and eliminate CPU bottlenecks with multiple cameras
        if self._frame_count % 2 == 1 and self._last_tracked:
            return self._last_tracked

        with torch.inference_mode():
            results = self._model.track(
                frame,
                persist=True,           # maintain tracks across frames
                tracker="bytetrack.yaml",
                conf=self._confidence,
                classes=[self._person_class_id],
                verbose=False,
                imgsz=320,              # 320x320: 3x-4x faster than 640 on CPU while maintaining person tracking accuracy
            )

        tracked: List[TrackedPerson] = []
        for result in results:
            if result.boxes is None or result.boxes.id is None:
                continue
            for box, track_id_tensor in zip(result.boxes, result.boxes.id):
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                tid = int(track_id_tensor.cpu().numpy())
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                tracked.append(TrackedPerson(
                    track_id=tid,
                    bbox=(float(x1), float(y1), float(x2), float(y2)),
                    confidence=conf,
                    centroid_px=(float(cx), float(cy)),
                ))

        self._last_tracked = tracked
        return tracked

    def reset(self) -> None:
        """Reset the tracker state (e.g., when starting a new session)."""
        # Re-create the model to clear internal tracker state
        model_path = self._model.model_name if hasattr(self._model, 'model_name') else MODEL_PATH
        self._model = YOLO(model_path)
