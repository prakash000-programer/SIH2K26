# IntelliSales — Privacy-First Retail Intelligence Platform
> **Smart India Hackathon (Problem Statement: SIH26179)**  
> Edge AI Shopper Analytics • Predictive Queue Dispatch • Zero-Storage Shelf Inventory • Executive ROI

---

## 🌟 Executive Summary

**IntelliSales** is a production-grade edge retail intelligence platform engineered for physical retail environments. Designed from the ground up to be **hardware-agnostic** and deployable on the **Qualcomm® QCS6490** edge AI processor, it provides physical store managers, floor staff, and retail owners with actionable intelligence without ever storing raw video footage.

### Core Architectural Tenets
1. **Privacy-by-Design**: Absolute zero raw video or image frames are saved to disk. All CV models perform single-pass in-memory edge inference; only derived numeric metrics (coordinates, timestamps, zone dwell seconds, counts) enter the local SQLite database.
2. **Hardware Agnostic**: Decoupled video source abstraction supporting USB webcams, RTSP streams, pre-recorded video files, and MIPI-CSI camera sensors.
3. **Qualcomm QCS6490 Edge Target**: Structured for immediate porting to Qualcomm Neural Processing SDK (SNPE/QNN) with INT8 quantization.
4. **Proactive Queue Dispatch**: Uses an upstream arrival velocity predictive formula chain with exponential smoothing to recommend opening checkout counters *before* queues form.
5. **Resilient Inventory Monitoring**: Zero-image frame differencing with 3-consecutive consensus verification to eliminate false alarms from transient customer occlusions.

---

## 🏛️ System Architecture

```
                                  CAMERA INPUT
                     (Webcam / RTSP / Video File Fallback)
                                       │
                                       ▼
                     ┌──────────────────────────────────┐
                     │    Edge Inference (In-Memory)    │
                     │  - YOLOv8n Person Detection      │
                     │  - ByteTrack Tracker (Ephemeral) │
                     │  - Perspective Homography        │
                     └──────────────────────────────────┘
                                       │
                       Derived Metrics & Events ONLY
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────┐                             ┌───────────────────────┐
│     FastAPI Core      │                             │   SQLite Event DB     │
│  - WebSocket Hub      │                             │  - Heatmap & Dwell    │
│  - Analytics Router   │                             │  - Footfall In/Out    │
│  - Queue Predictor    │                             │  - Inventory Slots    │
│  - ROI Financials     │                             │  - 7-Day Retention    │
└───────────────────────┘                             └───────────────────────┘
            │
            ▼ WebSocket Live Stream
┌─────────────────────────────────────────────────────────────────────────────┐
│                       React + TypeScript Dashboard                          │
│  🏢 Store Manager       🚨 Floor Staff         💼 Executive ROI             │
│  (Heatmap, Footfall)   (Live Action Feed)     (Payback & Revenue Model)     │
│  ⏱️ Queue Intel         📦 Shelf Stock         📐 Camera Calibration        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (Local Run)

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**

### Option A: Single Command Launcher (Recommended)
Clone the repository and run:
```bash
# Install backend dependencies
pip install -r backend/requirements.txt

# Install frontend dependencies
cd frontend && npm install && cd ..

# Launch both backend (port 8000) and frontend (port 3000)
python run.py
```

Open your browser:
- **Dashboard UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **WebSocket Endpoint**: `ws://localhost:8000/ws`

---

### Option B: Run Services Separately

**1. Start Backend:**
```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**2. Start Frontend:**
```bash
cd frontend
npm run dev
```

---

### Option C: Run with Docker Compose
```bash
docker-compose up --build
```

---

## 🧩 Deep Dive: Core Modules

### 1. Module 1 — Spatial Shopper Analytics
- **Camera Calibration (`backend/cv/calibration.py`)**: Computes a 3×3 homography matrix from 4 clicked camera pixel coordinates to real-world floor meters ($W_x, W_y$).
- **Person Detection & Tracking (`backend/cv/detector.py`, `tracker.py`)**: Ephemeral ByteTrack assigns short-lived IDs that are never stored long-term.
- **Two-Layer Dwell Logic (`backend/cv/dwell.py`)**:
  - *Cell Layer*: Tracks time spent in individual 0.5m × 0.5m grid cells. Filters out walkers with a `< 2.0s` pass-through threshold.
  - *Zone Layer*: Accumulates dwell across multiple cells in a zone (e.g. 3 pauses of 3s each in Apparel = 9s zone dwell), firing a single event once the qualifying threshold (5.0s) is reached.
- **Directional Footfall Counter (`backend/cv/footfall.py`)**: Vector cross-product line-crossing algorithm tracking IN vs OUT traffic.

### 2. Module 2 — Queue Intelligence & Predictive Dispatch
Implements the exact predictive formula chain:
$$\mu = \frac{1}{\text{avg\_service\_time}}$$
$$\text{Total Capacity} = C \times \mu$$
$$\text{Demand} = \text{Footfall Rate} \times \text{Conversion Rate}$$
$$\Delta_{\text{congestion}} = \text{Demand} - \text{Total Capacity}$$
$$\text{Predicted Queue} = Q_{\text{current}} + \Delta_{\text{congestion}} \times \text{avg\_shopping\_time}$$
$$\text{Max Acceptable Queue} = C \times \frac{\text{max\_wait\_time}}{\text{avg\_service\_time}}$$

If $\text{Predicted Queue} > \text{Max Acceptable Queue}$, an alert triggers on the Floor Staff action feed with the exact number of additional counters to dispatch.
Exponential smoothing ($\alpha = 0.3$) is applied to filter transient spikes:
$$\bar{x}_t = 0.7 \bar{x}_{t-1} + 0.3 x_t$$

### 3. Module 3 — Shelf Inventory & Stock Monitoring
- **Stock Model**: $\text{Available} = \text{Total} - \text{Sold}$.
- **Frame Differencing (`backend/inventory/frame_diff.py`)**: Fast in-memory grayscale comparison using `cv2.absdiff()` against an in-memory reference snapshot. No images stored.
- **3-Consecutive Consensus**: Requires 3 successive empty scans before firing a restock alert, eliminating false alarms when customers briefly reach in front of shelves.

### 4. Module 4 — Executive Financial ROI Model
Dynamic ROI calculator evaluating:
- **Revenue Uplift**: $\text{Live Footfall} \times \text{Conversion Rate} \times \text{Average Basket Value} - \text{Baseline Revenue}$
- **Stockouts Prevented Value**: Quantified inventory replenishment recovery
- **Total Monthly Benefit**: Revenue Uplift + Prevented Stockouts
- **Monthly ROI %**: $\frac{\text{Total Benefit} - \text{System Cost}}{\text{System Cost}} \times 100$
- **Payback Period**: Exact month where cumulative benefit outstrips edge hardware and operating cost.

---

## 🧪 Verification & Test Suite

Run the automated test suite locally to verify all subsystems:

```bash
# 1. Test Homography Mathematical Transformation
python scripts/test_calibration.py

# 2. Test Dwell Time Pass-Through Filter & Footfall Line Crossing
python scripts/test_dwell.py

# 3. Test Full Backend REST API & Database Integration
python scripts/test_backend_api.py

# 4. Test Frontend Compilation & Type Integrity
cd frontend && npm run build
```

---

## 🛡️ Privacy & Security Guarantees

| Data Type | Storage Policy | Reason |
| :--- | :--- | :--- |
| **Raw Video Frames** | ❌ Never Saved | In-memory RAM buffer only; discarded immediately after inference |
| **Customer Facial/Biometric Data** | ❌ Never Captured | YOLOv8 person class detects centroids and bounding boxes only |
| **Track IDs** | ⚠️ Ephemeral Session | Discarded as soon as shopper exits camera field |
| **Numeric Heatmap Coordinates** | ✅ 7-Day Rolling Retention | Auto-summarized into hourly density totals by background retention job |
| **Shelf Reference Images** | ❌ Hashes Only | Raw shelf photos stay in volatile memory; only SHA-256 hash stored in DB |

---

## 🏁 Qualcomm QCS6490 Porting Roadmap

The detection and tracking pipelines are written with strict hardware-agnostic design principles:
1. **Model Swap**: `MODEL_PATH` in `backend/config.py` can be pointed to an exported ONNX or Qualcomm DLC (Deep Learning Container) model.
2. **Inference Engine**: Decoupled `PersonDetector` class can swap `ultralytics` for `snpe-net-run` or QNN execution provider with zero changes to downstream tracking or analytics logic.
3. **Low Power Profile**: Minimal memory footprint designed to run comfortably within the 8GB LPDDR4x unified memory profile of the QCS6490 board.
