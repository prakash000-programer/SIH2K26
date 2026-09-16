"""
IntelliSales — Camera Calibration (Homography)

Computes a perspective-transform (homography) matrix that maps pixel coordinates
in a camera frame to real-world floor coordinates in metres.

Hardware-agnostic: this module is pure math — it accepts point arrays and returns
a matrix.  No camera/capture code lives here.

Usage:
    cal = CameraCalibrator()
    cal.set_reference_points(
        pixel_points=[(100, 200), (400, 200), (400, 500), (100, 500)],
        world_points=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)],
    )
    cal.compute_homography()
    wx, wy = cal.pixel_to_world(250, 350)
    cal.save("data/calibration/cam0.json")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np


class CalibrationError(Exception):
    """Raised when calibration data is invalid or incomplete."""


class CameraCalibrator:
    """Computes and applies a pixel → world homography transform."""

    def __init__(self) -> None:
        self._pixel_points: np.ndarray | None = None   # shape (N, 2)
        self._world_points: np.ndarray | None = None    # shape (N, 2)
        self._homography: np.ndarray | None = None      # 3×3
        self._reprojection_error: float | None = None
        self._camera_id: str = "default"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_reference_points(
        self,
        pixel_points: List[Tuple[float, float]],
        world_points: List[Tuple[float, float]],
    ) -> None:
        """Store corresponding pixel ↔ world point pairs.

        Args:
            pixel_points: At least 4 (px_x, px_y) coordinates clicked on the frame.
            world_points: Matching (world_x_m, world_y_m) coordinates in metres.
        """
        if len(pixel_points) < 4 or len(world_points) < 4:
            raise CalibrationError("Need at least 4 point correspondences.")
        if len(pixel_points) != len(world_points):
            raise CalibrationError(
                f"Point count mismatch: {len(pixel_points)} pixel vs "
                f"{len(world_points)} world points."
            )
        self._pixel_points = np.array(pixel_points, dtype=np.float64)
        self._world_points = np.array(world_points, dtype=np.float64)
        self._homography = None  # invalidate any previous matrix

    def compute_homography(self) -> np.ndarray:
        """Compute the 3×3 homography matrix (pixel → world).

        Returns:
            The 3×3 homography matrix.

        Raises:
            CalibrationError: if reference points haven't been set yet.
        """
        if self._pixel_points is None or self._world_points is None:
            raise CalibrationError("Set reference points before computing homography.")

        # cv2.findHomography expects (src, dst) — we map pixel → world
        H, mask = cv2.findHomography(
            self._pixel_points, self._world_points, method=cv2.RANSAC
        )
        if H is None:
            raise CalibrationError(
                "Could not compute homography — points may be degenerate."
            )
        self._homography = H

        # Compute reprojection error for diagnostics
        self._reprojection_error = self._compute_reprojection_error()

        return H

    def pixel_to_world(self, px: float, py: float) -> Tuple[float, float]:
        """Convert a pixel coordinate to real-world metres using the homography.

        Args:
            px: x pixel coordinate.
            py: y pixel coordinate.

        Returns:
            (world_x, world_y) in metres.
        """
        if self._homography is None:
            raise CalibrationError("No homography computed yet — call compute_homography() first.")

        # Homogeneous coordinate
        pt = np.array([px, py, 1.0], dtype=np.float64)
        world_h = self._homography @ pt
        # Dehomogenise
        wx = world_h[0] / world_h[2]
        wy = world_h[1] / world_h[2]
        return float(wx), float(wy)

    def world_to_pixel(self, wx: float, wy: float) -> Tuple[float, float]:
        """Inverse transform: world metres → pixel coordinate.

        Useful for overlaying world-coordinate entities back onto a frame.
        """
        if self._homography is None:
            raise CalibrationError("No homography computed yet.")

        H_inv = np.linalg.inv(self._homography)
        pt = np.array([wx, wy, 1.0], dtype=np.float64)
        px_h = H_inv @ pt
        return float(px_h[0] / px_h[2]), float(px_h[1] / px_h[2])

    @property
    def reprojection_error(self) -> float | None:
        """Mean reprojection error in metres (lower is better)."""
        return self._reprojection_error

    @property
    def is_calibrated(self) -> bool:
        return self._homography is not None

    @property
    def homography_matrix(self) -> np.ndarray | None:
        return self._homography.copy() if self._homography is not None else None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Persist calibration data to a JSON file.

        Stores: homography matrix, reference points, reprojection error, camera ID.
        Does NOT store any image/frame data — privacy compliant.
        """
        if self._homography is None:
            raise CalibrationError("Nothing to save — compute homography first.")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "camera_id": self._camera_id,
            "homography": self._homography.tolist(),
            "pixel_points": self._pixel_points.tolist(),
            "world_points": self._world_points.tolist(),
            "reprojection_error_m": self._reprojection_error,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "CameraCalibrator":
        """Load a previously saved calibration from JSON."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Calibration file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        cal = cls()
        cal._camera_id = data.get("camera_id", "default")
        cal._pixel_points = np.array(data["pixel_points"], dtype=np.float64)
        cal._world_points = np.array(data["world_points"], dtype=np.float64)
        cal._homography = np.array(data["homography"], dtype=np.float64)
        cal._reprojection_error = data.get("reprojection_error_m")
        return cal

    def set_camera_id(self, camera_id: str) -> None:
        self._camera_id = camera_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_reprojection_error(self) -> float:
        """Mean Euclidean distance between expected world points and
        homography-projected world points (in metres)."""
        assert self._pixel_points is not None and self._world_points is not None
        assert self._homography is not None

        errors = []
        for (px, py), (wx_expected, wy_expected) in zip(
            self._pixel_points, self._world_points
        ):
            wx, wy = self.pixel_to_world(px, py)
            err = np.sqrt((wx - wx_expected) ** 2 + (wy - wy_expected) ** 2)
            errors.append(err)
        return float(np.mean(errors))
