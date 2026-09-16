"""
IntelliSales -- Person Detector (YOLOv8n)

Wraps the Ultralytics YOLO model for person-only detection.
Hardware-agnostic: accepts a numpy frame, returns structured detections.
No camera/capture code here.

*** SWAP POINT ***
To use a fine-tuned overhead-view model instead of pretrained COCO:
  1. Place your .pt file in the project (e.g. models/overhead_person.pt)
  2. Set  MODEL_PATH = "models/overhead_person.pt"  in config.py
     (or env var INTELLISALES_MODEL_PATH)
  3. If your model uses a different class ID for "person", also update
     PERSON_CLASS_ID in config.py.
No other code changes needed -- the detector interface stays the same.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np
from ultralytics import YOLO

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import MODEL_PATH, PERSON_CLASS_ID, DETECTION_CONFIDENCE


@dataclass
class Detection:
    """A single person detection in one frame."""
    bbox: tuple[float, float, float, float]   # (x1, y1, x2, y2) pixel coords
    confidence: float
    centroid_px: tuple[float, float]           # (cx, cy) pixel centre of bbox
    class_id: int = 0                          # COCO person = 0


class PersonDetector:
    """YOLOv8-based person detector.

    Usage:
        detector = PersonDetector()
        detections = detector.detect(frame)   # frame is a numpy BGR image
    """

    def __init__(self, model_path: str = MODEL_PATH, confidence: float = DETECTION_CONFIDENCE):
        """
        Args:
            model_path: Path to the YOLO .pt weights file.
            confidence: Minimum confidence threshold for detections.
        """
        self._model = YOLO(model_path)
        self._confidence = confidence
        self._person_class_id = PERSON_CLASS_ID

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run person detection on a single frame.

        Args:
            frame: BGR numpy array (H, W, 3).

        Returns:
            List of Detection objects for persons only.
        """
        results = self._model(
            frame,
            conf=self._confidence,
            classes=[self._person_class_id],  # filter to person class only
            verbose=False,
        )

        detections: List[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls = int(box.cls[0].cpu().numpy())
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                detections.append(Detection(
                    bbox=(float(x1), float(y1), float(x2), float(y2)),
                    confidence=conf,
                    centroid_px=(float(cx), float(cy)),
                    class_id=cls,
                ))

        return detections

    @property
    def model_name(self) -> str:
        return self._model.model_name if hasattr(self._model, 'model_name') else MODEL_PATH
