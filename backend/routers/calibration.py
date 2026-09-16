"""
IntelliSales -- Calibration API Router

Endpoints for camera calibration workflow.
"""

from __future__ import annotations

import base64
import time

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.cv.calibration import CameraCalibrator, CalibrationError
from backend.config import CALIBRATION_DIR, get_video_source
from backend.models.analytics import CalibrationPointsRequest, CalibrationStatus

router = APIRouter(prefix="/api/calibration", tags=["calibration"])

# Module-level calibrator instance
_calibrator: CameraCalibrator | None = None


def get_calibrator() -> CameraCalibrator | None:
    """Get the current calibrator instance."""
    global _calibrator
    if _calibrator is None:
        # Try to load from disk
        cal_path = CALIBRATION_DIR / "cam0.json"
        if cal_path.exists():
            _calibrator = CameraCalibrator.load(cal_path)
    return _calibrator


@router.post("/capture")
async def capture_frame():
    """Capture a single frame from the video source and return as base64.
    
    Privacy note: this frame is returned to the client for calibration only.
    It is NOT stored on disk or in the database.
    """
    source = get_video_source()
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Could not open video source")

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(status_code=500, detail="Could not capture frame")

    # Encode as JPEG and base64
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64_str = base64.b64encode(buffer).decode("utf-8")

    return {
        "image_base64": b64_str,
        "width": frame.shape[1],
        "height": frame.shape[0],
    }


@router.post("/set-points")
async def set_calibration_points(req: CalibrationPointsRequest):
    """Receive pixel and world point correspondences, compute homography."""
    global _calibrator

    try:
        cal = CameraCalibrator()
        cal.set_camera_id(req.camera_id)
        cal.set_reference_points(
            pixel_points=[tuple(p) for p in req.pixel_points],
            world_points=[tuple(p) for p in req.world_points],
        )
        H = cal.compute_homography()

        # Save to disk
        save_path = CALIBRATION_DIR / f"{req.camera_id}.json"
        cal.save(save_path)
        _calibrator = cal

        return {
            "success": True,
            "reprojection_error_m": cal.reprojection_error,
            "homography": H.tolist(),
            "save_path": str(save_path),
        }
    except CalibrationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def calibration_status():
    """Check current calibration state."""
    cal = get_calibrator()
    if cal and cal.is_calibrated:
        return CalibrationStatus(
            is_calibrated=True,
            camera_id=cal._camera_id,
            reprojection_error=cal.reprojection_error,
        )
    return CalibrationStatus(is_calibrated=False, camera_id="none")
