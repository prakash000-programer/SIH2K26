"""
IntelliSales -- Stock Calculation Logic

Available Stock = Total Stock - Sold

Where 'Sold' is entered via a mock POS input (a form that logs a sale,
decrementing stock).  Structured so a real POS webhook can replace the
manual form later without changing this calculation logic.

TODO [ROADMAP]: Planogram/SKU-level compliance checking is explicitly
out of scope for this prototype. When implementing, this module should
be extended with:
  - SKU detection (fine-tuned YOLO or barcode scanning)
  - Planogram reference DB for position compliance scoring
  - Per-SKU stock tracking instead of per-slot
"""

from __future__ import annotations


def calculate_available_stock(total_stock: int, sold: int) -> int:
    """Available = Total - Sold.

    This is deliberately simple.  The function exists so that:
    1. The formula is documented in one place.
    2. A POS webhook integration can call the same path as the mock form.
    """
    return max(0, total_stock - sold)


def check_consensus(consecutive_empty: int, threshold: int = 3) -> bool:
    """Return True if enough consecutive empty readings have occurred.

    Requires 3 consecutive "empty" readings before confirming a stock-out.
    This consensus check reduces false positives from transient occlusions
    (e.g., a customer's hand in front of the shelf camera).
    """
    return consecutive_empty >= threshold
