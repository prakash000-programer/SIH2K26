"""
IntelliSales — Interactive Camera Calibration Script

Usage:
    python scripts/calibrate.py                     # use default webcam
    python scripts/calibrate.py --source video.mp4  # use a video file
    python scripts/calibrate.py --source 1          # use webcam index 1

Workflow:
    1. Opens the camera/video, captures a single frame, and displays it.
    2. User clicks exactly 4 reference points on the frame.
    3. For each point, user enters real-world (x, y) coordinates in metres
       via the console.
    4. Homography is computed and saved to data/calibration/cam0.json.
    5. The script enters a *verification mode*: click any point on the frame
       and the console prints its real-world coordinate.  Press 'q' to quit.

This script uses OpenCV's HighGUI for the interactive window.  The core
calibration math lives in backend.cv.calibration (hardware-agnostic).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so we can import backend modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

from backend.cv.calibration import CameraCalibrator
from backend.config import CALIBRATION_DIR


# ---------------------------------------------------------------------------
# Click handler state
# ---------------------------------------------------------------------------
clicked_points: list[tuple[int, int]] = []
current_frame: np.ndarray | None = None
display_frame: np.ndarray | None = None
calibrator: CameraCalibrator | None = None
mode: str = "calibration"  # "calibration" or "verification"

WINDOW_NAME = "IntelliSales — Camera Calibration"
POINT_COLOR = (0, 255, 0)        # green
VERIFY_COLOR = (255, 200, 0)     # cyan-ish
FONT = cv2.FONT_HERSHEY_SIMPLEX


def mouse_callback(event: int, x: int, y: int, flags: int, param) -> None:
    """Handle mouse clicks in both calibration and verification modes."""
    global clicked_points, display_frame, calibrator

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    if mode == "calibration":
        clicked_points.append((x, y))
        # Draw the point on the display frame
        assert display_frame is not None
        idx = len(clicked_points)
        cv2.circle(display_frame, (x, y), 6, POINT_COLOR, -1)
        cv2.putText(display_frame, f"P{idx}", (x + 10, y - 10), FONT, 0.6, POINT_COLOR, 2)
        cv2.imshow(WINDOW_NAME, display_frame)
        print(f"  [P{idx}] Pixel: ({x}, {y})")

    elif mode == "verification" and calibrator is not None:
        wx, wy = calibrator.pixel_to_world(x, y)
        assert display_frame is not None
        label = f"({wx:.2f}, {wy:.2f})m"
        cv2.circle(display_frame, (x, y), 5, VERIFY_COLOR, -1)
        cv2.putText(display_frame, label, (x + 10, y - 10), FONT, 0.5, VERIFY_COLOR, 1)
        cv2.imshow(WINDOW_NAME, display_frame)
        print(f"  Pixel ({x}, {y}) -> World ({wx:.3f}, {wy:.3f}) metres")


def capture_frame(source) -> np.ndarray:
    """Capture a single frame from the given source."""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"ERROR: Could not open video source: {source}")
        sys.exit(1)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("ERROR: Could not read a frame from the source.")
        sys.exit(1)

    return frame


def run_calibration(source) -> None:
    """Full interactive calibration flow."""
    global current_frame, display_frame, calibrator, mode, clicked_points

    NUM_POINTS = 4

    # --- Step 1: Capture frame ---
    print(f"\n{'='*60}")
    print("  IntelliSales — Camera Calibration Tool")
    print(f"{'='*60}")
    print(f"\nSource: {source}")
    print("Capturing a frame...")

    current_frame = capture_frame(source)
    display_frame = current_frame.copy()

    print(f"Frame size: {current_frame.shape[1]}×{current_frame.shape[0]} px")

    # --- Step 2: Collect pixel points ---
    mode = "calibration"
    clicked_points = []

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, min(current_frame.shape[1], 1280), min(current_frame.shape[0], 720))
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)
    cv2.imshow(WINDOW_NAME, display_frame)

    print(f"\nClick {NUM_POINTS} reference points on the frame.")
    print("(Points should form a quadrilateral covering the floor area.)\n")

    while len(clicked_points) < NUM_POINTS:
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q"):
            print("Calibration cancelled.")
            cv2.destroyAllWindows()
            return

    # --- Step 3: Collect world coordinates ---
    print(f"\nAll {NUM_POINTS} pixel points collected!")
    print("Now enter the real-world (x, y) coordinates in metres for each point.\n")

    world_points: list[tuple[float, float]] = []
    for i, (px, py) in enumerate(clicked_points, 1):
        while True:
            try:
                raw = input(f"  P{i} pixel=({px},{py}) -> world x,y (metres, comma-separated): ")
                parts = [float(v.strip()) for v in raw.split(",")]
                if len(parts) != 2:
                    raise ValueError
                world_points.append((parts[0], parts[1]))
                break
            except (ValueError, IndexError):
                print("    Invalid input. Enter two numbers separated by a comma, e.g.: 3.5, 2.0")

    # --- Step 4: Compute homography ---
    calibrator = CameraCalibrator()
    calibrator.set_camera_id("cam0")
    calibrator.set_reference_points(
        pixel_points=clicked_points,
        world_points=world_points,
    )
    H = calibrator.compute_homography()

    print(f"\n{'─'*60}")
    print("  Homography computed successfully!")
    print(f"  Reprojection error: {calibrator.reprojection_error:.4f} metres")
    print(f"{'─'*60}")
    print("\nHomography matrix H (pixel -> world):")
    for row in H:
        print(f"  [{row[0]:12.6f}  {row[1]:12.6f}  {row[2]:12.6f}]")

    # Verify reference points
    print("\nVerification of reference points:")
    for i, ((px, py), (wx_exp, wy_exp)) in enumerate(
        zip(clicked_points, world_points), 1
    ):
        wx, wy = calibrator.pixel_to_world(px, py)
        print(
            f"  P{i}: pixel ({px},{py}) -> world ({wx:.3f}, {wy:.3f})m  "
            f"[expected ({wx_exp:.3f}, {wy_exp:.3f})m]"
        )

    # --- Step 5: Save ---
    save_path = CALIBRATION_DIR / "cam0.json"
    calibrator.save(save_path)
    print(f"\nCalibration saved to: {save_path}")

    # --- Step 6: Verification mode ---
    mode = "verification"
    display_frame = current_frame.copy()

    # Draw the reference points on the verification frame
    for i, (px, py) in enumerate(clicked_points, 1):
        cv2.circle(display_frame, (px, py), 6, POINT_COLOR, -1)
        cv2.putText(display_frame, f"P{i}", (px + 10, py - 10), FONT, 0.6, POINT_COLOR, 2)

    cv2.imshow(WINDOW_NAME, display_frame)
    print("\n" + "=" * 60)
    print("  VERIFICATION MODE")
    print("  Click anywhere on the frame to see real-world coordinates.")
    print("  Press 'q' to quit.")
    print("=" * 60 + "\n")

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q"):
            break

    cv2.destroyAllWindows()
    print("Calibration complete. Goodbye!")


def main():
    parser = argparse.ArgumentParser(
        description="IntelliSales — Interactive Camera Calibration"
    )
    parser.add_argument(
        "--source",
        default="0",
        help="Video source: webcam index (0, 1, ...) or path to a video file",
    )
    args = parser.parse_args()

    # Convert "0", "1" to int (webcam index), leave file paths as strings
    source = int(args.source) if args.source.isdigit() else args.source
    run_calibration(source)


if __name__ == "__main__":
    main()
