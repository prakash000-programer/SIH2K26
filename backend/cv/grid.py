"""
IntelliSales -- Floor Grid Mapping

Maps real-world (metre) coordinates to a configurable grid of cells,
and maps cells to named zones.

Grid layout:
  - Origin (0, 0) is at the calibrated floor's reference corner.
  - x increases rightward, y increases downward (matching typical camera view).
  - Cell (row, col) where row = floor(wy / cell_size), col = floor(wx / cell_size).

Zone definitions are loaded from the config JSON file.  Each zone is a named
group of grid cells (e.g., "electronics": cells [[0,0], [0,1], [1,0], [1,1]]).

Hardware-agnostic: pure coordinate math, no camera code.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import CELL_SIZE_M, FLOOR_WIDTH_M, FLOOR_HEIGHT_M, load_zones


class FloorGrid:
    """Maps world coordinates to grid cells and named zones."""

    def __init__(
        self,
        floor_width_m: float = FLOOR_WIDTH_M,
        floor_height_m: float = FLOOR_HEIGHT_M,
        cell_size_m: float = CELL_SIZE_M,
    ):
        self.floor_width_m = floor_width_m
        self.floor_height_m = floor_height_m
        self.cell_size_m = cell_size_m

        # Grid dimensions
        self.num_cols = math.ceil(floor_width_m / cell_size_m)
        self.num_rows = math.ceil(floor_height_m / cell_size_m)

        # Zone lookup: cell (row, col) -> zone_id
        self._cell_to_zone: Dict[Tuple[int, int], str] = {}
        self._zones: Dict[str, dict] = {}
        self._load_zones()

    def _load_zones(self) -> None:
        """Load zone definitions from config and build the cell->zone lookup."""
        self._zones = load_zones()
        self._cell_to_zone = {}
        for zone_id, zone_def in self._zones.items():
            for cell in zone_def.get("cells", []):
                row, col = int(cell[0]), int(cell[1])
                self._cell_to_zone[(row, col)] = zone_id

    def reload_zones(self) -> None:
        """Reload zone definitions from disk (e.g., after config change)."""
        self._load_zones()

    def get_cell(self, wx: float, wy: float) -> Tuple[int, int]:
        """Convert world coordinates (metres) to a grid cell (row, col).

        Args:
            wx: world x in metres.
            wy: world y in metres.

        Returns:
            (row, col) tuple. Values are clamped to valid grid range.
        """
        col = int(math.floor(wx / self.cell_size_m))
        row = int(math.floor(wy / self.cell_size_m))
        # Clamp to grid bounds
        col = max(0, min(col, self.num_cols - 1))
        row = max(0, min(row, self.num_rows - 1))
        return (row, col)

    def get_zone(self, row: int, col: int) -> Optional[str]:
        """Look up the zone ID for a given grid cell.

        Args:
            row: Grid row index.
            col: Grid column index.

        Returns:
            Zone ID string, or None if the cell is not assigned to any zone.
        """
        return self._cell_to_zone.get((row, col))

    def get_zone_for_world(self, wx: float, wy: float) -> Optional[str]:
        """Convenience: world coords -> zone ID."""
        row, col = self.get_cell(wx, wy)
        return self.get_zone(row, col)

    def get_cell_center_world(self, row: int, col: int) -> Tuple[float, float]:
        """Return the world-coordinate centre of a grid cell.

        Useful for heatmap rendering.
        """
        wx = (col + 0.5) * self.cell_size_m
        wy = (row + 0.5) * self.cell_size_m
        return (wx, wy)

    def get_zone_info(self, zone_id: str) -> Optional[dict]:
        """Return the full zone definition dict for a zone ID."""
        return self._zones.get(zone_id)

    @property
    def all_zone_ids(self) -> List[str]:
        return list(self._zones.keys())

    @property
    def grid_shape(self) -> Tuple[int, int]:
        """(num_rows, num_cols)."""
        return (self.num_rows, self.num_cols)

    def __repr__(self) -> str:
        return (
            f"FloorGrid({self.floor_width_m}m x {self.floor_height_m}m, "
            f"cell={self.cell_size_m}m, grid={self.num_rows}x{self.num_cols}, "
            f"zones={len(self._zones)})"
        )
