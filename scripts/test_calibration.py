"""
IntelliSales — Calibration Unit Test (no GUI / no webcam needed)

Verifies that the CameraCalibrator correctly computes a homography from
known pixel ↔ world point correspondences and transforms points accurately.

Run:  python scripts/test_calibration.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tempfile
from backend.cv.calibration import CameraCalibrator, CalibrationError


def test_basic_homography():
    """Test with a simple known mapping (simulating a top-down camera)."""
    print("=" * 60)
    print("  Test: Basic Homography Computation")
    print("=" * 60)

    # Simulate a 640×480 frame where 4 floor corners are visible
    # Pixel coords (as if clicked on the frame)
    pixel_points = [
        (100, 80),    # top-left floor corner
        (540, 80),    # top-right
        (580, 420),   # bottom-right
        (60, 420),    # bottom-left
    ]

    # Corresponding real-world coords in metres
    world_points = [
        (0.0, 0.0),
        (6.0, 0.0),
        (6.0, 4.0),
        (0.0, 4.0),
    ]

    cal = CameraCalibrator()
    cal.set_camera_id("test_cam")
    cal.set_reference_points(pixel_points, world_points)
    H = cal.compute_homography()

    print(f"\nHomography matrix:")
    for row in H:
        print(f"  [{row[0]:12.6f}  {row[1]:12.6f}  {row[2]:12.6f}]")
    print(f"\nReprojection error: {cal.reprojection_error:.6f} metres")

    # Verify reference points map back correctly
    print("\nReference point verification:")
    all_pass = True
    for i, ((px, py), (wx_exp, wy_exp)) in enumerate(zip(pixel_points, world_points), 1):
        wx, wy = cal.pixel_to_world(px, py)
        err = ((wx - wx_exp) ** 2 + (wy - wy_exp) ** 2) ** 0.5
        status = "PASS" if err < 0.01 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  P{i}: pixel ({px},{py}) -> ({wx:.4f}, {wy:.4f})m  expected ({wx_exp}, {wy_exp})m  [{status}] err={err:.6f}m")

    # Test an interior point
    print("\nInterior point test:")
    # The centre of the pixel quadrilateral (roughly)
    cx, cy = 320, 250
    wx, wy = cal.pixel_to_world(cx, cy)
    print(f"  Pixel ({cx},{cy}) -> World ({wx:.3f}, {wy:.3f})m")
    print(f"  (Should be roughly in the center of the 6x4m floor: ~3.0, ~2.0)")

    return all_pass


def test_save_load():
    """Test persistence (save/load) round-trip."""
    print("\n" + "=" * 60)
    print("  Test: Save / Load Round-Trip")
    print("=" * 60)

    pixel_points = [(100, 80), (540, 80), (580, 420), (60, 420)]
    world_points = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]

    cal = CameraCalibrator()
    cal.set_camera_id("roundtrip_test")
    cal.set_reference_points(pixel_points, world_points)
    cal.compute_homography()

    # Save to a temp file
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name
    cal.save(tmp_path)
    print(f"  Saved to: {tmp_path}")

    # Load it back
    cal2 = CameraCalibrator.load(tmp_path)
    print(f"  Loaded camera_id: {cal2._camera_id}")
    print(f"  Loaded reprojection error: {cal2.reprojection_error:.6f}m")

    # Verify a point transforms the same way
    wx1, wy1 = cal.pixel_to_world(300, 200)
    wx2, wy2 = cal2.pixel_to_world(300, 200)
    err = ((wx1 - wx2) ** 2 + (wy1 - wy2) ** 2) ** 0.5
    status = "PASS" if err < 1e-10 else "FAIL"
    print(f"  Transform consistency: err={err:.2e}  [{status}]")

    # Clean up
    Path(tmp_path).unlink()
    return status == "PASS"


def test_error_handling():
    """Test that proper errors are raised for invalid inputs."""
    print("\n" + "=" * 60)
    print("  Test: Error Handling")
    print("=" * 60)

    cal = CameraCalibrator()

    # Test: too few points
    try:
        cal.set_reference_points([(0, 0), (1, 1)], [(0, 0), (1, 1)])
        print("  Too few points: FAIL (no error raised)")
        return False
    except CalibrationError:
        print("  Too few points: PASS (CalibrationError raised)")

    # Test: mismatched counts
    try:
        cal.set_reference_points([(0, 0)] * 4, [(0, 0)] * 5)
        print("  Mismatched counts: FAIL (no error raised)")
        return False
    except CalibrationError:
        print("  Mismatched counts: PASS (CalibrationError raised)")

    # Test: transform before calibration
    try:
        cal.pixel_to_world(100, 100)
        print("  No homography: FAIL (no error raised)")
        return False
    except CalibrationError:
        print("  No homography: PASS (CalibrationError raised)")

    return True


if __name__ == "__main__":
    results = []
    results.append(("Basic Homography", test_basic_homography()))
    results.append(("Save/Load", test_save_load()))
    results.append(("Error Handling", test_error_handling()))

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {name}: {status}")

    print(f"\n  Overall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    print("=" * 60)
    sys.exit(0 if all_pass else 1)
