"""
IntelliSales -- Directional Line-Crossing Footfall Counter

Counts IN and OUT crossings of a defined entry/exit line using
world-coordinate positions of tracked persons.

How it works:
  1. A "counting line" is defined by two world-coordinate endpoints (A, B).
  2. An "inward direction" vector is provided (pointing into the store).
  3. For each tracked person, we monitor their world-coordinate position
     across consecutive frames.
  4. When a person's position crosses from one side of the line to the other:
     - If the movement direction dot-products positively with the inward
       vector -> IN crossing
     - If negatively -> OUT crossing
  5. Each track ID can only trigger one crossing event (to avoid duplicate
     counts from jitter near the line).

Hardware-agnostic: pure geometry on world coordinates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np


@dataclass
class FootfallEvent:
    """Emitted when a tracked person crosses the counting line."""
    track_id: int
    direction: str          # "in" or "out"
    timestamp: float        # time.time()
    world_position: Tuple[float, float]  # where the crossing happened


class LineCounter:
    """Directional line-crossing footfall counter.

    Usage:
        counter = LineCounter(
            point_a=(2.0, 0.0),    # line endpoint A in world metres
            point_b=(2.0, 4.0),    # line endpoint B in world metres
            inward_direction=(1.0, 0.0),  # unit vector pointing "into" the store
        )
        # Call update() every frame:
        events = counter.update([(track_id, (wx, wy)), ...])
    """

    def __init__(
        self,
        point_a: Tuple[float, float],
        point_b: Tuple[float, float],
        inward_direction: Tuple[float, float],
    ):
        self.point_a = np.array(point_a, dtype=np.float64)
        self.point_b = np.array(point_b, dtype=np.float64)

        # Normalise the inward direction vector
        inward = np.array(inward_direction, dtype=np.float64)
        norm = np.linalg.norm(inward)
        if norm < 1e-10:
            raise ValueError("Inward direction vector cannot be zero-length.")
        self.inward = inward / norm

        # Compute the line's normal vector (perpendicular to A->B)
        line_vec = self.point_b - self.point_a
        # 2D perpendicular: rotate 90 degrees
        self.line_normal = np.array([-line_vec[1], line_vec[0]], dtype=np.float64)
        norm_n = np.linalg.norm(self.line_normal)
        if norm_n > 1e-10:
            self.line_normal /= norm_n

        # Ensure the normal points in the same general direction as "inward"
        if np.dot(self.line_normal, self.inward) < 0:
            self.line_normal = -self.line_normal

        # Previous frame positions: track_id -> (wx, wy)
        self._prev_positions: Dict[int, np.ndarray] = {}

        # Track IDs that have already crossed (prevent double-counting)
        self._crossed_tracks: Set[int] = set()

        # Running counts
        self.count_in: int = 0
        self.count_out: int = 0

    def update(
        self,
        track_positions: List[Tuple[int, Tuple[float, float]]],
        current_time: Optional[float] = None,
    ) -> List[FootfallEvent]:
        """Process one frame of track positions.

        Args:
            track_positions: List of (track_id, (world_x, world_y)).
            current_time: Override for testing; defaults to time.time().

        Returns:
            List of FootfallEvent for any new crossings.
        """
        now = current_time if current_time is not None else time.time()
        events: List[FootfallEvent] = []
        current_ids = set()

        for track_id, (wx, wy) in track_positions:
            current_ids.add(track_id)
            pos = np.array([wx, wy], dtype=np.float64)

            if track_id in self._crossed_tracks:
                # Already counted this track -- skip
                self._prev_positions[track_id] = pos
                continue

            if track_id in self._prev_positions:
                prev_pos = self._prev_positions[track_id]
                # Check if the line was crossed between prev and current
                crossed, direction = self._check_crossing(prev_pos, pos)
                if crossed:
                    self._crossed_tracks.add(track_id)
                    if direction == "in":
                        self.count_in += 1
                    else:
                        self.count_out += 1
                    events.append(FootfallEvent(
                        track_id=track_id,
                        direction=direction,
                        timestamp=now,
                        world_position=(wx, wy),
                    ))

            self._prev_positions[track_id] = pos

        # Clean up tracks that have left the scene
        gone_ids = set(self._prev_positions.keys()) - current_ids
        for tid in gone_ids:
            del self._prev_positions[tid]
            self._crossed_tracks.discard(tid)

        return events

    def _check_crossing(
        self, prev: np.ndarray, curr: np.ndarray
    ) -> Tuple[bool, str]:
        """Check if movement from prev to curr crosses the counting line.

        Uses the signed distance from the line (via dot product with normal)
        to detect sign changes.

        Returns:
            (crossed: bool, direction: "in" | "out")
        """
        # Signed distances from point A along the line normal
        d_prev = np.dot(prev - self.point_a, self.line_normal)
        d_curr = np.dot(curr - self.point_a, self.line_normal)

        if d_prev * d_curr < 0:
            # Sign changed -> line was crossed
            # Movement vector
            movement = curr - prev
            # Direction: dot with inward vector
            dot = np.dot(movement, self.inward)
            direction = "in" if dot > 0 else "out"
            return True, direction

        return False, ""

    def reset(self) -> None:
        """Reset all counters and state."""
        self._prev_positions.clear()
        self._crossed_tracks.clear()
        self.count_in = 0
        self.count_out = 0

    @property
    def total_footfall(self) -> int:
        return self.count_in + self.count_out

    def __repr__(self) -> str:
        return f"LineCounter(in={self.count_in}, out={self.count_out})"
