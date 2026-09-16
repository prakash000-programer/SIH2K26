"""
IntelliSales -- SQLite Database Layer

Schema, connection management, and CRUD helpers for local event storage.
Uses aiosqlite for async access from FastAPI.

Privacy:
  - No frame/image data is ever stored.
  - Only derived numeric/event data persists.
  - Track IDs in events are for analytics aggregation only --
    they are ephemeral session IDs, never linked to identities.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import DB_PATH

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Detection/heatmap events (raw, rolled up after 7 days)
CREATE TABLE IF NOT EXISTS detection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    cell_row INTEGER NOT NULL,
    cell_col INTEGER NOT NULL,
    person_count INTEGER NOT NULL DEFAULT 1,
    confidence TEXT NOT NULL DEFAULT 'normal',  -- 'normal' or 'low'
    created_at REAL NOT NULL
);

-- Dwell events (zone-level, one per track per zone per session)
CREATE TABLE IF NOT EXISTS dwell_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    zone_id TEXT NOT NULL,
    qualifying_time_s REAL NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'normal',
    created_at REAL NOT NULL
);

-- Footfall events
CREATE TABLE IF NOT EXISTS footfall_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    direction TEXT NOT NULL,  -- 'in' or 'out'
    created_at REAL NOT NULL
);

-- Density snapshots (high-crowd frames)
CREATE TABLE IF NOT EXISTS density_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    total_persons INTEGER NOT NULL,
    cell_counts_json TEXT NOT NULL,  -- JSON: {"(r,c)": count, ...}
    created_at REAL NOT NULL
);

-- Hourly summary (rolled up from raw events)
CREATE TABLE IF NOT EXISTS hourly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_start REAL NOT NULL,       -- epoch of the hour start
    metric_type TEXT NOT NULL,      -- 'heatmap', 'dwell', 'footfall', 'density'
    summary_json TEXT NOT NULL,     -- aggregated JSON data
    created_at REAL NOT NULL
);

-- Inventory shelf slots
CREATE TABLE IF NOT EXISTS inventory_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_name TEXT NOT NULL UNIQUE,
    total_stock INTEGER NOT NULL DEFAULT 0,
    sold INTEGER NOT NULL DEFAULT 0,
    consecutive_empty INTEGER NOT NULL DEFAULT 0,
    is_stocked_out INTEGER NOT NULL DEFAULT 0,
    reference_image_hash TEXT,      -- hash only, never the image itself
    created_at REAL NOT NULL
);

-- Inventory events (stock-out alerts)
CREATE TABLE IF NOT EXISTS inventory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,       -- 'stockout', 'restocked', 'sale'
    details_json TEXT,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (slot_id) REFERENCES inventory_slots(id)
);

-- Queue readings (from simulated sensors)
CREATE TABLE IF NOT EXISTS queue_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    counter_id TEXT NOT NULL,
    queue_size INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL
);

-- Queue alerts
CREATE TABLE IF NOT EXISTS queue_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    predicted_queue REAL NOT NULL,
    max_acceptable REAL NOT NULL,
    details_json TEXT,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL
);

-- Config overrides (dashboard-editable parameters)
CREATE TABLE IF NOT EXISTS config_overrides (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

-- Indexes for time-range queries
CREATE INDEX IF NOT EXISTS idx_detection_ts ON detection_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_dwell_ts ON dwell_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_footfall_ts ON footfall_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_density_ts ON density_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_queue_ts ON queue_readings(timestamp);
"""


# ---------------------------------------------------------------------------
# Database manager
# ---------------------------------------------------------------------------

class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open the database connection and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    # ------------------------------------------------------------------
    # Detection / Heatmap events
    # ------------------------------------------------------------------

    async def insert_detection_events(
        self, events: List[Dict[str, Any]]
    ) -> None:
        """Batch insert detection/heatmap events.
        
        Each dict: {timestamp, cell_row, cell_col, person_count, confidence}
        """
        now = time.time()
        await self.db.executemany(
            """INSERT INTO detection_events 
               (timestamp, cell_row, cell_col, person_count, confidence, created_at)
               VALUES (:timestamp, :cell_row, :cell_col, :person_count, :confidence, :created_at)""",
            [{**e, "created_at": now} for e in events],
        )
        await self.db.commit()

    async def get_heatmap(
        self, start_ts: float, end_ts: float
    ) -> List[Dict[str, Any]]:
        """Aggregate detection counts per cell in a time window."""
        cursor = await self.db.execute(
            """SELECT cell_row, cell_col, SUM(person_count) as total_count
               FROM detection_events
               WHERE timestamp >= ? AND timestamp <= ?
               GROUP BY cell_row, cell_col""",
            (start_ts, end_ts),
        )
        rows = await cursor.fetchall()
        return [{"row": r["cell_row"], "col": r["cell_col"], "count": r["total_count"]} for r in rows]

    # ------------------------------------------------------------------
    # Dwell events
    # ------------------------------------------------------------------

    async def insert_dwell_event(
        self, timestamp: float, zone_id: str, qualifying_time_s: float,
        confidence: str = "normal"
    ) -> None:
        now = time.time()
        await self.db.execute(
            """INSERT INTO dwell_events 
               (timestamp, zone_id, qualifying_time_s, confidence, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (timestamp, zone_id, qualifying_time_s, confidence, now),
        )
        await self.db.commit()

    async def get_dwell_events(
        self, start_ts: float, end_ts: float, zone_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if zone_id:
            cursor = await self.db.execute(
                """SELECT * FROM dwell_events
                   WHERE timestamp >= ? AND timestamp <= ? AND zone_id = ?
                   ORDER BY timestamp""",
                (start_ts, end_ts, zone_id),
            )
        else:
            cursor = await self.db.execute(
                """SELECT * FROM dwell_events
                   WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp""",
                (start_ts, end_ts),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Footfall events
    # ------------------------------------------------------------------

    async def insert_footfall_event(
        self, timestamp: float, direction: str
    ) -> None:
        now = time.time()
        await self.db.execute(
            """INSERT INTO footfall_events (timestamp, direction, created_at)
               VALUES (?, ?, ?)""",
            (timestamp, direction, now),
        )
        await self.db.commit()

    async def get_footfall(
        self, start_ts: float, end_ts: float
    ) -> Dict[str, int]:
        cursor = await self.db.execute(
            """SELECT direction, COUNT(*) as cnt FROM footfall_events
               WHERE timestamp >= ? AND timestamp <= ?
               GROUP BY direction""",
            (start_ts, end_ts),
        )
        rows = await cursor.fetchall()
        result = {"in": 0, "out": 0}
        for r in rows:
            result[r["direction"]] = r["cnt"]
        return result

    async def get_footfall_rate(self, window_seconds: float = 300.0) -> float:
        """Footfall IN rate over the last window (per minute)."""
        now = time.time()
        cursor = await self.db.execute(
            """SELECT COUNT(*) as cnt FROM footfall_events
               WHERE timestamp >= ? AND direction = 'in'""",
            (now - window_seconds,),
        )
        row = await cursor.fetchone()
        count = row["cnt"] if row else 0
        minutes = window_seconds / 60.0
        return count / minutes if minutes > 0 else 0.0

    # ------------------------------------------------------------------
    # Density snapshots
    # ------------------------------------------------------------------

    async def insert_density_snapshot(
        self, timestamp: float, total_persons: int, cell_counts_json: str
    ) -> None:
        now = time.time()
        await self.db.execute(
            """INSERT INTO density_snapshots 
               (timestamp, total_persons, cell_counts_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (timestamp, total_persons, cell_counts_json, now),
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    async def upsert_inventory_slot(
        self, slot_name: str, total_stock: int = 0
    ) -> int:
        now = time.time()
        await self.db.execute(
            """INSERT INTO inventory_slots (slot_name, total_stock, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(slot_name) DO UPDATE SET total_stock = ?""",
            (slot_name, total_stock, now, total_stock),
        )
        await self.db.commit()
        cursor = await self.db.execute(
            "SELECT id FROM inventory_slots WHERE slot_name = ?", (slot_name,)
        )
        row = await cursor.fetchone()
        return row["id"]

    async def get_inventory_slots(self) -> List[Dict[str, Any]]:
        cursor = await self.db.execute(
            """SELECT id, slot_name, total_stock, sold,
                      total_stock - sold as available,
                      consecutive_empty, is_stocked_out
               FROM inventory_slots"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def record_sale(self, slot_name: str, qty: int = 1) -> None:
        """Record a sale -- structured so a POS webhook can call this directly."""
        now = time.time()
        await self.db.execute(
            "UPDATE inventory_slots SET sold = sold + ? WHERE slot_name = ?",
            (qty, slot_name),
        )
        # Get slot id for the event
        cursor = await self.db.execute(
            "SELECT id FROM inventory_slots WHERE slot_name = ?", (slot_name,)
        )
        row = await cursor.fetchone()
        if row:
            await self.db.execute(
                """INSERT INTO inventory_events 
                   (slot_id, event_type, details_json, timestamp, created_at)
                   VALUES (?, 'sale', ?, ?, ?)""",
                (row["id"], f'{{"qty": {qty}}}', now, now),
            )
        await self.db.commit()

    async def update_slot_empty_count(
        self, slot_name: str, is_empty: bool
    ) -> bool:
        """Update consecutive empty count.  Returns True if stockout event should fire."""
        if is_empty:
            await self.db.execute(
                """UPDATE inventory_slots 
                   SET consecutive_empty = consecutive_empty + 1 
                   WHERE slot_name = ?""",
                (slot_name,),
            )
        else:
            await self.db.execute(
                """UPDATE inventory_slots 
                   SET consecutive_empty = 0, is_stocked_out = 0 
                   WHERE slot_name = ?""",
                (slot_name,),
            )
        await self.db.commit()

        cursor = await self.db.execute(
            "SELECT consecutive_empty, is_stocked_out FROM inventory_slots WHERE slot_name = ?",
            (slot_name,),
        )
        row = await cursor.fetchone()
        if row and row["consecutive_empty"] >= 3 and not row["is_stocked_out"]:
            await self.db.execute(
                "UPDATE inventory_slots SET is_stocked_out = 1 WHERE slot_name = ?",
                (slot_name,),
            )
            await self.db.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    async def insert_queue_reading(
        self, counter_id: str, queue_size: int
    ) -> None:
        now = time.time()
        await self.db.execute(
            """INSERT INTO queue_readings (counter_id, queue_size, timestamp, created_at)
               VALUES (?, ?, ?, ?)""",
            (counter_id, queue_size, now, now),
        )
        await self.db.commit()

    async def get_queue_sizes(self) -> Dict[str, int]:
        """Get latest queue size per counter."""
        cursor = await self.db.execute(
            """SELECT counter_id, queue_size FROM queue_readings
               WHERE id IN (
                   SELECT MAX(id) FROM queue_readings GROUP BY counter_id
               )"""
        )
        rows = await cursor.fetchall()
        return {r["counter_id"]: r["queue_size"] for r in rows}

    async def insert_queue_alert(
        self, alert_type: str, predicted_queue: float,
        max_acceptable: float, details_json: str = "{}"
    ) -> None:
        now = time.time()
        await self.db.execute(
            """INSERT INTO queue_alerts 
               (alert_type, predicted_queue, max_acceptable, details_json, timestamp, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (alert_type, predicted_queue, max_acceptable, details_json, now, now),
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Config overrides
    # ------------------------------------------------------------------

    async def get_config(self, key: str, default: str = "") -> str:
        cursor = await self.db.execute(
            "SELECT value FROM config_overrides WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else default

    async def set_config(self, key: str, value: str) -> None:
        now = time.time()
        await self.db.execute(
            """INSERT INTO config_overrides (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
            (key, value, now, value, now),
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Retention (used by retention.py)
    # ------------------------------------------------------------------

    async def get_old_event_count(self, table: str, cutoff_ts: float) -> int:
        cursor = await self.db.execute(
            f"SELECT COUNT(*) as cnt FROM {table} WHERE created_at < ?",
            (cutoff_ts,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def delete_old_events(self, table: str, cutoff_ts: float) -> int:
        cursor = await self.db.execute(
            f"DELETE FROM {table} WHERE created_at < ?",
            (cutoff_ts,),
        )
        await self.db.commit()
        return cursor.rowcount


# Global singleton
db = Database()
