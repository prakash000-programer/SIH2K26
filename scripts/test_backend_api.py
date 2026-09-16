"""
IntelliSales -- Backend API Integration Test
Tests all REST endpoints and database functionality.
"""

import asyncio
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import db


async def run_tests():
    print("=" * 60)
    print("IntelliSales Backend API & Database Test")
    print("=" * 60)

    # 1. Initialize DB
    print("[1/7] Testing Database initialization...")
    await db.connect()
    print("  ✓ Database connected and tables verified")

    now = time.time()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. Test Root & Health
        print("[2/7] Testing Root & Health endpoints...")
        resp = await client.get("/")
        assert resp.status_code == 200, f"Root failed: {resp.status_code}"
        data = resp.json()
        print(f"  ✓ Root status: {data.get('status')}, CV available: {data.get('cv_available')}")

        resp = await client.get("/api/health")
        assert resp.status_code == 200
        print(f"  ✓ Health check passed: {resp.json().get('status')}")

        # 3. Test Queue Intelligence
        print("[3/7] Testing Queue Intelligence endpoints...")
        # Increment queue counter 1
        resp = await client.post("/api/queue/increment", json={"counter_id": "counter_1"})
        assert resp.status_code == 200
        assert resp.json()["queue_size"] == 1
        print("  ✓ Queue increment counter_1 -> size 1")

        # Increment again
        resp = await client.post("/api/queue/increment", json={"counter_id": "counter_1"})
        assert resp.json()["queue_size"] == 2
        print("  ✓ Queue increment counter_1 -> size 2")

        # Status
        resp = await client.get("/api/queue/status")
        assert resp.status_code == 200
        assert resp.json()["queues"].get("counter_1") == 2
        print(f"  ✓ Queue status verified: {resp.json()}")

        # Prediction
        resp = await client.get("/api/queue/prediction")
        assert resp.status_code == 200
        pred = resp.json()
        print(f"  ✓ Queue prediction computed: predicted_queue={pred.get('predicted_queue_size')}, should_open={pred.get('should_open_counter')}")

        # Decrement
        resp = await client.post("/api/queue/decrement", json={"counter_id": "counter_1"})
        assert resp.status_code == 200
        assert resp.json()["queue_size"] == 1
        print("  ✓ Queue decrement counter_1 -> size 1")

        # 4. Test Analytics Endpoints
        print("[4/7] Testing Analytics endpoints...")
        # Insert sample detection and footfall for testing
        await db.insert_detection_events([{
            "timestamp": now,
            "cell_row": 2,
            "cell_col": 4,
            "person_count": 1,
            "confidence": "normal"
        }])
        await db.insert_footfall_event(now, "in")
        await db.insert_footfall_event(now, "out")
        await db.insert_dwell_event(now, "apparel", 8.5, "normal")

        resp = await client.get(f"/api/analytics/heatmap?start={now - 300}&end={now + 300}")
        assert resp.status_code == 200
        hm = resp.json()
        assert "cells" in hm and len(hm["cells"]) > 0
        print(f"  ✓ Heatmap returned {len(hm['cells'])} active cell(s)")

        resp = await client.get(f"/api/analytics/dwell?start={now - 300}&end={now + 300}")
        assert resp.status_code == 200
        dwell = resp.json()
        assert len(dwell.get("events", [])) > 0
        print(f"  ✓ Dwell events returned {len(dwell['events'])} event(s)")

        resp = await client.get(f"/api/analytics/footfall?start={now - 300}&end={now + 300}")
        assert resp.status_code == 200
        ff = resp.json()
        assert ff["count_in"] >= 1 and ff["count_out"] >= 1
        print(f"  ✓ Footfall count: IN={ff['count_in']}, OUT={ff['count_out']}")

        # 5. Test Inventory Endpoints
        print("[5/7] Testing Inventory endpoints...")
        await db.upsert_inventory_slot("Slot A - Soft Drinks", total_stock=24)
        resp = await client.get("/api/inventory/slots")
        assert resp.status_code == 200
        data = resp.json()
        slots = data["slots"]
        assert len(slots) > 0
        slot_name = slots[0]["slot_name"]
        print(f"  ✓ Inventory slots returned: {len(slots)} slot(s), slot_name={slot_name}")

        # Record a mock POS sale
        resp = await client.post("/api/inventory/sales", json={"slot_name": slot_name, "quantity": 2})
        assert resp.status_code == 200
        sale_res = resp.json()
        print(f"  ✓ POS sale processed: status={sale_res.get('status')}, quantity={sale_res.get('quantity')}")

        # 6. Test Dashboard Summary & ROI
        print("[6/7] Testing Dashboard & ROI endpoints...")
        resp = await client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        summary = resp.json()
        print(f"  ✓ Manager summary: footfall IN={summary['footfall']['in']}, dwell zones={list(summary['dwell_by_zone'].keys())}")

        resp = await client.post("/api/dashboard/roi", json={"baseline_monthly_revenue": 50000.0})
        assert resp.status_code == 200
        roi = resp.json()
        print(f"  ✓ ROI calculated: total_benefit=${roi['total_monthly_benefit']:.2f}, ROI={roi['monthly_roi_percent']:.1f}%, payback={roi['payback_month']}mo")

        # 7. Test Calibration API
        print("[7/7] Testing Calibration endpoints...")
        resp = await client.get("/api/calibration/status")
        assert resp.status_code == 200
        calib_status = resp.json()
        print(f"  ✓ Calibration status: calibrated={calib_status.get('calibrated')}")

    await db.close()
    print("=" * 60)
    print("ALL API TESTS PASSED SUCCESSFULLY! ✓✓✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
