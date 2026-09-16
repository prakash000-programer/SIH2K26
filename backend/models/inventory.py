"""
IntelliSales -- Pydantic Models for Inventory
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class InventorySlot(BaseModel):
    id: int
    slot_name: str
    total_stock: int
    sold: int
    available: int
    consecutive_empty: int
    is_stocked_out: bool


class CreateSlotRequest(BaseModel):
    slot_name: str
    total_stock: int = 0


class RecordSaleRequest(BaseModel):
    """Mock POS input.  Structured so a real POS webhook can replace
    this form later without changing the stock calculation logic."""
    slot_name: str
    quantity: int = 1


class ShelfCheckResult(BaseModel):
    slot_name: str
    diff_ratio: float
    is_empty: bool
    stockout_fired: bool
