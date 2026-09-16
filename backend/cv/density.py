"""
IntelliSales -- Crowd-Density Fallback

When the number of detected people exceeds MAX_CROWD_SIZE in a single frame,
individual track-level dwell attribution becomes unreliable (occlusion,
ID switches, etc.).

In this mode:
  - Per-track dwell attribution is SKIPPED for the frame
  - Instead, a per-grid-cell density count is logged
  - All records from high-density frames are tagged with confidence: "low"

Hardware-agnostic: pure logic on detection counts and grid cells.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import MAX_CROWD_SIZE


@dataclass
class DensitySnapshot:
    """A per-cell density count for one high-density frame."""
    timestamp: float
    cell_counts: Dict[Tuple[int, int], int]  # (row, col) -> person count
    total_persons: int
    confidence: str = "low"  # always "low" for density fallback frames


class DensityMonitor:
    """Monitors crowd density and produces fallback snapshots.

    Usage:
        monitor = DensityMonitor()
        is_crowded, snapshot = monitor.check(detections_with_cells)
        if is_crowded:
            # skip dwell attribution, log the snapshot instead
    """

    def __init__(self, max_crowd_size: int = MAX_CROWD_SIZE):
        self.max_crowd_size = max_crowd_size

    def check(
        self,
        cell_assignments: List[Tuple[int, Tuple[int, int]]],
        current_time: Optional[float] = None,
    ) -> Tuple[bool, Optional[DensitySnapshot]]:
        """Check if the current frame is a high-density frame.

        Args:
            cell_assignments: List of (track_id, (row, col)) for every
                detection in the current frame.
            current_time: Override for testing.

        Returns:
            (is_high_density, snapshot_or_none)
        """
        now = current_time if current_time is not None else time.time()
        num_persons = len(cell_assignments)

        if num_persons <= self.max_crowd_size:
            return False, None

        # Build per-cell density counts
        cell_counts: Dict[Tuple[int, int], int] = {}
        for _, cell in cell_assignments:
            cell_counts[cell] = cell_counts.get(cell, 0) + 1

        snapshot = DensitySnapshot(
            timestamp=now,
            cell_counts=cell_counts,
            total_persons=num_persons,
            confidence="low",
        )
        return True, snapshot
