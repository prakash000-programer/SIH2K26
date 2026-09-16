"""
IntelliSales -- Dwell-Time Logic Unit Test

Verifies the two-layer dwell-time state machine with synthetic data:
  - Layer 1 cell threshold (2s default)
  - Layer 2 zone threshold (7s default)
  - Pass-through filtering
  - Zone event fires exactly once per track per zone
  - Track cleanup on exit

Run:  python scripts/test_dwell.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.cv.dwell import DwellTracker, DwellEvent
from backend.cv.footfall import LineCounter, FootfallEvent


def test_cell_threshold():
    """A person staying in one cell should not fire until cell threshold is met."""
    print("=" * 60)
    print("  Test: Cell Dwell Threshold (2s)")
    print("=" * 60)

    tracker = DwellTracker(cell_threshold_s=2.0, zone_threshold_s=7.0)

    # Track 1 in cell (0,0), zone "A"
    t = 100.0

    # Frame 1: enter cell at t=100
    events = tracker.update([(1, (0, 0), "A")], current_time=t)
    assert len(events) == 0, "No event expected on entry"

    # Frame 2: still in cell at t=101 (1s -- below threshold)
    t = 101.0
    events = tracker.update([(1, (0, 0), "A")], current_time=t)
    assert len(events) == 0, "No event at 1s (below 2s cell threshold)"

    # Frame 3: still at t=102.5 (2.5s -- above cell threshold, but below zone)
    t = 102.5
    events = tracker.update([(1, (0, 0), "A")], current_time=t)
    assert len(events) == 0, "Cell qualifies, but zone time (2.5s) < zone threshold (7s)"

    # Frame 4-7: continue until zone threshold
    for dt in [103.0, 104.0, 105.0, 106.0]:
        events = tracker.update([(1, (0, 0), "A")], current_time=dt)

    # Frame 8: at t=107.5 (7.5s total)
    t = 107.5
    events = tracker.update([(1, (0, 0), "A")], current_time=t)
    if len(events) == 1:
        print(f"  PASS: Dwell event fired at {events[0].total_qualifying_time_s:.1f}s")
    else:
        print(f"  FAIL: Expected 1 event, got {len(events)}")
        return False

    # Frame 9: should NOT fire again
    t = 110.0
    events = tracker.update([(1, (0, 0), "A")], current_time=t)
    if len(events) == 0:
        print("  PASS: No duplicate event fired")
    else:
        print("  FAIL: Duplicate event fired")
        return False

    return True


def test_passthrough_filtering():
    """A person walking through a cell in < 2s should NOT contribute to zone dwell."""
    print("\n" + "=" * 60)
    print("  Test: Pass-Through Filtering")
    print("=" * 60)

    tracker = DwellTracker(cell_threshold_s=2.0, zone_threshold_s=7.0)

    # Track 1 passes through cell (0,0) in zone "A" in 1s
    events = tracker.update([(1, (0, 0), "A")], current_time=100.0)
    events = tracker.update([(1, (0, 0), "A")], current_time=100.5)
    # Moves to cell (0,1) also in zone "A"
    events = tracker.update([(1, (0, 1), "A")], current_time=101.0)
    events = tracker.update([(1, (0, 1), "A")], current_time=101.5)
    # Moves to cell (0,2) also in zone "A"
    events = tracker.update([(1, (0, 2), "A")], current_time=102.0)
    events = tracker.update([(1, (0, 2), "A")], current_time=102.5)

    # None of these cells had >= 2s dwell time, so no zone event should fire
    # even though total time in zone is 2.5s
    cell_times = tracker.get_active_cell_times()
    any_qualified = any(t >= 2.0 for t in cell_times.values())

    if not any_qualified:
        print("  PASS: No cell qualified (all < 2s) -- pass-through correctly filtered")
    else:
        print(f"  FAIL: Some cells qualified unexpectedly: {cell_times}")
        return False

    if len(events) == 0:
        print("  PASS: No zone dwell event (correct)")
    else:
        print("  FAIL: Unexpected zone event")
        return False

    return True


def test_multi_cell_zone_dwell():
    """Person pauses at 3 different cells in one zone, each > 2s, totalling > 7s."""
    print("\n" + "=" * 60)
    print("  Test: Multi-Cell Zone Dwell Accumulation")
    print("=" * 60)

    tracker = DwellTracker(cell_threshold_s=2.0, zone_threshold_s=7.0)
    t = 200.0

    all_events = []

    # Pause at cell (0,0) in zone "B" for 3s
    for dt in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        events = tracker.update([(1, (0, 0), "B")], current_time=t + dt)
        all_events.extend(events)
    print(f"  After 3s in cell (0,0): {len(all_events)} events")

    # Move to cell (0,1) in zone "B", pause 3s
    t2 = t + 3.5
    for dt in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        events = tracker.update([(1, (0, 1), "B")], current_time=t2 + dt)
        all_events.extend(events)
    print(f"  After 3s in cell (0,1): {len(all_events)} events total")

    # Move to cell (0,2) in zone "B", pause 3s (total qualifying time should exceed 7s)
    t3 = t2 + 3.5
    for dt in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        events = tracker.update([(1, (0, 2), "B")], current_time=t3 + dt)
        all_events.extend(events)
    print(f"  After 3s in cell (0,2): {len(all_events)} events total")

    if len(all_events) == 1:
        ev = all_events[0]
        print(f"  PASS: Exactly 1 zone dwell event fired")
        print(f"         Zone: '{ev.zone_id}', qualifying time: {ev.total_qualifying_time_s:.1f}s")
        return True
    else:
        print(f"  FAIL: Expected exactly 1 event, got {len(all_events)}")
        return False


def test_track_cleanup():
    """When a track leaves the scene, its state should be fully cleaned up."""
    print("\n" + "=" * 60)
    print("  Test: Track Cleanup on Exit")
    print("=" * 60)

    tracker = DwellTracker(cell_threshold_s=2.0, zone_threshold_s=7.0)

    # Track 1 enters
    tracker.update([(1, (0, 0), "A")], current_time=300.0)
    tracker.update([(1, (0, 0), "A")], current_time=303.0)

    # Track 1 leaves (empty update)
    tracker.update([], current_time=304.0)

    # Check internal state is cleaned up
    cell_times = tracker.get_active_cell_times()
    zone_times = tracker.get_zone_times()

    if len(cell_times) == 0 and len(zone_times) == 0:
        print("  PASS: All state cleaned up after track exit")
        return True
    else:
        print(f"  FAIL: Leftover state -- cells: {cell_times}, zones: {zone_times}")
        return False


def test_footfall_crossing():
    """Test directional line-crossing detection."""
    print("\n" + "=" * 60)
    print("  Test: Footfall Line Crossing")
    print("=" * 60)

    # Line at x=5.0, from y=0 to y=10.  Inward = rightward (+x)
    counter = LineCounter(
        point_a=(5.0, 0.0),
        point_b=(5.0, 10.0),
        inward_direction=(1.0, 0.0),
    )

    # Track 1 walks IN (left to right, crossing x=5)
    events = counter.update([(1, (3.0, 3.0))], current_time=400.0)  # left of line
    events = counter.update([(1, (7.0, 3.0))], current_time=401.0)  # right of line

    if len(events) == 1 and events[0].direction == "in":
        print(f"  PASS: Track 1 crossed IN")
    else:
        print(f"  FAIL: Expected 1 IN event, got {events}")
        return False

    # Track 2 walks OUT (right to left)
    events = counter.update([(1, (7.0, 3.0)), (2, (8.0, 5.0))], current_time=402.0)
    events = counter.update([(1, (7.0, 3.0)), (2, (2.0, 5.0))], current_time=403.0)

    out_events = [e for e in events if e.direction == "out"]
    if len(out_events) == 1 and out_events[0].track_id == 2:
        print(f"  PASS: Track 2 crossed OUT")
    else:
        print(f"  FAIL: Expected 1 OUT event for track 2, got {events}")
        return False

    if counter.count_in == 1 and counter.count_out == 1:
        print(f"  PASS: Totals correct (IN={counter.count_in}, OUT={counter.count_out})")
    else:
        print(f"  FAIL: Totals wrong (IN={counter.count_in}, OUT={counter.count_out})")
        return False

    return True


if __name__ == "__main__":
    results = []
    results.append(("Cell Threshold", test_cell_threshold()))
    results.append(("Pass-Through Filtering", test_passthrough_filtering()))
    results.append(("Multi-Cell Zone Dwell", test_multi_cell_zone_dwell()))
    results.append(("Track Cleanup", test_track_cleanup()))
    results.append(("Footfall Crossing", test_footfall_crossing()))

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
