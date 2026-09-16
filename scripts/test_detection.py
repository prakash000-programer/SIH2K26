"""
IntelliSales -- Detection + Tracking Console Test

Runs the full CV pipeline against a webcam or video file, printing
real-time tracking data to the console.  No UI/dashboard needed.

Usage:
    python scripts/test_detection.py                     # default webcam
    python scripts/test_detection.py --source video.mp4  # video file
    python scripts/test_detection.py --source 0 --preview  # with OpenCV preview window

Output (console, every frame):
    Track IDs, pixel centroids, world coords (if calibrated), cell assignments,
    dwell timers, footfall counts, density flags.

Press 'q' in the preview window (if --preview) or Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.cv.calibration import CameraCalibrator
from backend.cv.tracker import PersonTracker
from backend.cv.grid import FloorGrid
from backend.cv.dwell import DwellTracker
from backend.cv.footfall import LineCounter
from backend.cv.density import DensityMonitor
from backend.cv.pipeline import AnalyticsPipeline, WebcamSource, FrameResult
from backend.config import CALIBRATION_DIR, load_footfall_line


def load_calibrator() -> CameraCalibrator | None:
    """Try to load an existing calibration."""
    cal_path = CALIBRATION_DIR / "cam0.json"
    if cal_path.exists():
        cal = CameraCalibrator.load(cal_path)
        print(f"  Loaded calibration from {cal_path}")
        print(f"  Reprojection error: {cal.reprojection_error:.4f}m")
        return cal
    else:
        print(f"  No calibration found at {cal_path}")
        print(f"  Running without calibration (pixel coords only)")
        return None


def on_frame(result: FrameResult) -> None:
    """Console output callback for each processed frame."""
    n = len(result.tracked_persons)
    if n == 0:
        return  # skip empty frames to reduce noise

    lines = []
    lines.append(f"\n--- Frame @ {time.strftime('%H:%M:%S')} | {n} person(s) ---")

    if result.is_high_density:
        lines.append(f"  !! HIGH DENSITY ({n} persons) -- dwell attribution skipped")
        if result.density_snapshot:
            for cell, count in sorted(result.density_snapshot.cell_counts.items()):
                lines.append(f"     Cell {cell}: {count} person(s) [confidence: low]")
    else:
        for p in result.tracked_persons:
            line = f"  Track #{p.track_id}: px=({p.centroid_px[0]:.0f},{p.centroid_px[1]:.0f})"
            if p.centroid_world:
                wx, wy = p.centroid_world
                line += f"  world=({wx:.2f},{wy:.2f})m"
            lines.append(line)

    for ev in result.dwell_events:
        lines.append(
            f"  ** DWELL EVENT: Track #{ev.track_id} in zone '{ev.zone_id}' "
            f"({ev.total_qualifying_time_s:.1f}s)"
        )

    for ev in result.footfall_events:
        lines.append(
            f"  ** FOOTFALL: Track #{ev.track_id} crossed {ev.direction.upper()}"
        )

    if result.heatmap_cells:
        cells_str = ", ".join(
            f"{cell}:{count}" for cell, count in sorted(result.heatmap_cells.items())
        )
        lines.append(f"  Heatmap cells: {cells_str}")

    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="IntelliSales -- Detection Test")
    parser.add_argument("--source", default="0", help="Webcam index or video file path")
    parser.add_argument("--preview", action="store_true", help="Show OpenCV preview window")
    args = parser.parse_args()

    source_val = int(args.source) if args.source.isdigit() else args.source

    print("=" * 60)
    print("  IntelliSales -- Detection + Tracking Test")
    print("=" * 60)

    # Load calibration if available
    print("\nCalibration:")
    calibrator = load_calibrator()

    # Setup grid
    grid = FloorGrid()
    print(f"\nGrid: {grid}")

    # Setup footfall counter
    line_cfg = load_footfall_line()
    footfall_counter = None
    if line_cfg:
        footfall_counter = LineCounter(
            point_a=tuple(line_cfg["point_a"]),
            point_b=tuple(line_cfg["point_b"]),
            inward_direction=tuple(line_cfg["inward_direction"]),
        )
        print(f"Footfall line loaded: A={line_cfg['point_a']}, B={line_cfg['point_b']}")
    else:
        print("No footfall line configured -- footfall counting disabled")

    # Create pipeline
    pipeline = AnalyticsPipeline(
        calibrator=calibrator,
        grid=grid,
        footfall_counter=footfall_counter,
        on_frame_result=on_frame,
    )

    # Open source
    print(f"\nOpening source: {source_val}")
    source = WebcamSource(source_val)
    if not source.is_opened():
        print(f"ERROR: Could not open source {source_val}")
        sys.exit(1)

    print("Pipeline running. Press Ctrl+C (or 'q' in preview window) to stop.\n")

    try:
        pipeline.run_loop(source, show_preview=args.preview)
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        pipeline.stop()

    # Final stats
    print("\n" + "=" * 60)
    print("  Session Summary")
    print("=" * 60)
    if footfall_counter:
        print(f"  Footfall IN:  {footfall_counter.count_in}")
        print(f"  Footfall OUT: {footfall_counter.count_out}")
    print("  Done.")


if __name__ == "__main__":
    main()
