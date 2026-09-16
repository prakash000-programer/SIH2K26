"""
IntelliSales -- Dashboard API Router

Aggregated data endpoints for role-based views + ROI calculations.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import db
from backend.config import (
    MONTHLY_SYSTEM_COST, AVG_BASKET_VALUE, STOCKOUT_PREVENTED_VALUE,
    CONVERSION_RATE,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class ROIInput(BaseModel):
    baseline_monthly_revenue: float


class ROIResponse(BaseModel):
    baseline_monthly_revenue: float
    current_monthly_revenue: float
    revenue_uplift: float
    stockouts_prevented_value: float
    total_monthly_benefit: float
    monthly_system_cost: float
    monthly_roi_percent: float
    payback_month: int
    live_footfall: int
    conversion_rate: float
    avg_basket_value: float


@router.get("/summary")
async def dashboard_summary():
    """Aggregated summary for the manager view."""
    now = time.time()
    today_start = now - (now % 86400)  # approx start of UTC day

    footfall = await db.get_footfall(today_start, now)
    footfall_rate = await db.get_footfall_rate(300)
    dwell_events = await db.get_dwell_events(today_start, now)

    # Aggregate dwell by zone
    zone_dwell = {}
    for ev in dwell_events:
        zid = ev["zone_id"]
        if zid not in zone_dwell:
            zone_dwell[zid] = {"count": 0, "total_time_s": 0.0}
        zone_dwell[zid]["count"] += 1
        zone_dwell[zid]["total_time_s"] += ev["qualifying_time_s"]

    return {
        "footfall": footfall,
        "footfall_rate_per_min": footfall_rate,
        "dwell_by_zone": zone_dwell,
        "dwell_event_count": len(dwell_events),
        "timestamp": now,
    }


@router.post("/roi")
async def calculate_roi(roi_input: ROIInput):
    """Compute monthly ROI exactly as specified:

    current_monthly_revenue = live_footfall * conversion_rate * avg_basket_value
    revenue_uplift = current_monthly_revenue - baseline_monthly_revenue
    total_monthly_benefit = revenue_uplift + stockouts_prevented_value
    monthly_roi_percent = (total_monthly_benefit - monthly_system_cost) / monthly_system_cost * 100
    payback_month = month where cumulative benefit exceeds cumulative cost
    """
    now = time.time()
    # Get total footfall for the current month (approx 30 days)
    month_start = now - (30 * 86400)
    footfall = await db.get_footfall(month_start, now)
    live_footfall = footfall["in"]

    # Load conversion rate from config or use default
    conv_rate_str = await db.get_config("conversion_rate", str(CONVERSION_RATE))
    conversion_rate = float(conv_rate_str)

    avg_basket = AVG_BASKET_VALUE

    # Calculate
    current_monthly_revenue = live_footfall * conversion_rate * avg_basket
    revenue_uplift = current_monthly_revenue - roi_input.baseline_monthly_revenue
    stockouts_prevented_value = STOCKOUT_PREVENTED_VALUE * 10  # estimate ~10 prevented stockouts/month
    total_monthly_benefit = revenue_uplift + stockouts_prevented_value
    monthly_system_cost = MONTHLY_SYSTEM_COST

    if monthly_system_cost > 0:
        monthly_roi_percent = (total_monthly_benefit - monthly_system_cost) / monthly_system_cost * 100
    else:
        monthly_roi_percent = 0.0

    # Payback month: when cumulative benefit exceeds cumulative cost
    payback_month = 0
    if total_monthly_benefit > 0:
        cumulative_benefit = 0.0
        cumulative_cost = 0.0
        for month in range(1, 37):  # max 3 years
            cumulative_benefit += total_monthly_benefit
            cumulative_cost += monthly_system_cost
            if cumulative_benefit >= cumulative_cost:
                payback_month = month
                break
        if payback_month == 0:
            payback_month = -1  # not achievable in 3 years

    return ROIResponse(
        baseline_monthly_revenue=roi_input.baseline_monthly_revenue,
        current_monthly_revenue=current_monthly_revenue,
        revenue_uplift=revenue_uplift,
        stockouts_prevented_value=stockouts_prevented_value,
        total_monthly_benefit=total_monthly_benefit,
        monthly_system_cost=monthly_system_cost,
        monthly_roi_percent=monthly_roi_percent,
        payback_month=payback_month,
        live_footfall=live_footfall,
        conversion_rate=conversion_rate,
        avg_basket_value=avg_basket,
    )
