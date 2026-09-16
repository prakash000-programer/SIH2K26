"""
IntelliSales -- Inventory API Router

Mock/simulated inventory management with frame-differencing shelf checks.
"""

from __future__ import annotations

import io
import time

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import db
from backend.models.inventory import CreateSlotRequest, RecordSaleRequest, ShelfCheckResult
from backend.inventory.frame_diff import compare_shelf_images
from backend.routers.ws import ws_manager

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

# TODO [ROADMAP]: Planogram/SKU-level compliance checking is explicitly
# out of scope for this prototype. When implementing, this module should
# be extended with SKU detection (fine-tuned YOLO or barcode scanning)
# and a planogram reference DB for position compliance scoring.

# In-memory store for reference images (hashes only persisted to DB)
_reference_images: dict[str, np.ndarray] = {}


@router.post("/slots")
async def create_slot(req: CreateSlotRequest):
    """Create or update a shelf slot."""
    slot_id = await db.upsert_inventory_slot(req.slot_name, req.total_stock)
    return {"slot_id": slot_id, "slot_name": req.slot_name, "total_stock": req.total_stock}


@router.get("/slots")
async def list_slots():
    """Get all inventory slots with current status."""
    slots = await db.get_inventory_slots()
    return {"slots": slots}


@router.post("/slots/{slot_name}/reference")
async def upload_reference_image(slot_name: str, file: UploadFile = File(...)):
    """Upload the 'stocked' reference image for a shelf slot.
    
    Privacy: the image is held in memory only for comparison.
    Only a hash is persisted to the database.
    """
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    _reference_images[slot_name] = img
    return {"slot_name": slot_name, "status": "reference_uploaded", "shape": list(img.shape)}


@router.post("/slots/{slot_name}/check")
async def check_shelf_slot(slot_name: str, file: UploadFile = File(...)):
    """Upload a 'current' image and compare against the reference.
    
    Runs frame-differencing to detect empty/occupied status.
    Privacy: neither image is stored on disk -- only the numeric diff result.
    """
    if slot_name not in _reference_images:
        raise HTTPException(
            status_code=400,
            detail=f"No reference image for slot '{slot_name}'. Upload one first."
        )

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    current_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if current_img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    reference_img = _reference_images[slot_name]
    diff_ratio = compare_shelf_images(reference_img, current_img)
    is_empty = diff_ratio > 0.3  # 30% pixel change threshold

    # Update consecutive empty count (3-consecutive consensus check)
    stockout_fired = await db.update_slot_empty_count(slot_name, is_empty)

    if stockout_fired:
        # Fire stock-out alert via WebSocket
        now = time.time()
        await ws_manager.broadcast("stockout", {
            "slot_name": slot_name,
            "diff_ratio": diff_ratio,
            "timestamp": now,
        }, roles=["staff", "manager"])

    return ShelfCheckResult(
        slot_name=slot_name,
        diff_ratio=diff_ratio,
        is_empty=is_empty,
        stockout_fired=stockout_fired,
    )


@router.post("/sales")
async def record_sale(req: RecordSaleRequest):
    """Log a sale (mock POS input).
    
    Structured so a real POS webhook can replace this manual form
    later without changing the stock calculation logic.
    The stock calculation is: Available = Total - Sold
    """
    await db.record_sale(req.slot_name, req.quantity)
    return {"slot_name": req.slot_name, "quantity": req.quantity, "status": "recorded"}
