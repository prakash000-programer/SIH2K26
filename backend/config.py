"""
IntelliSales — Central Configuration

All configurable parameters live here. For this prototype, values are set via
environment variables or this defaults file. No runtime UI mutation needed yet.

Hardware-agnostic: nothing in this file assumes a specific camera or board.
"""

import os
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # SIH2026/
DATA_DIR = PROJECT_ROOT / "data"
CALIBRATION_DIR = DATA_DIR / "calibration"
DB_PATH = DATA_DIR / "intellisales.db"

# Ensure runtime directories exist
DATA_DIR.mkdir(exist_ok=True)
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Camera / Input Source
# ---------------------------------------------------------------------------
# 1 = external USB webcam, 0 = laptop built-in webcam.
VIDEO_SOURCE = os.getenv("INTELLISALES_VIDEO_SOURCE", "1")

# Convert "0", "1" etc. to int (webcam index); leave strings as file paths
def get_video_source():
    """Return the video source — int for webcam index, str for file path."""
    src = VIDEO_SOURCE
    if src.isdigit():
        return int(src)
    return src

# ---------------------------------------------------------------------------
# Detection Model
# ---------------------------------------------------------------------------
# YOLO model path.  Default: pretrained COCO yolov8n (ultra-fast edge inference).
# *** SWAP POINT: replace with a fine-tuned overhead-view model path here ***
MODEL_PATH = os.getenv("INTELLISALES_MODEL_PATH", "yolov8n.pt")

# Person class ID in COCO — used to filter detections
PERSON_CLASS_ID = 0

# Detection confidence threshold
DETECTION_CONFIDENCE = float(os.getenv("INTELLISALES_DET_CONF", "0.35"))

# ---------------------------------------------------------------------------
# Grid & Floor
# ---------------------------------------------------------------------------
# Cell size in metres
CELL_SIZE_M = float(os.getenv("INTELLISALES_CELL_SIZE", "0.5"))

# Floor dimensions in metres (width, height) — set after calibration
FLOOR_WIDTH_M = float(os.getenv("INTELLISALES_FLOOR_W", "10.0"))
FLOOR_HEIGHT_M = float(os.getenv("INTELLISALES_FLOOR_H", "8.0"))

# ---------------------------------------------------------------------------
# Zones — loaded from a JSON config file
# ---------------------------------------------------------------------------
# zones.json structure:
# {
#   "electronics": {"cells": [[0,0],[0,1],[1,0],[1,1]], "label": "Electronics"},
#   "entry":       {"cells": [[4,0],[4,1]], "label": "Main Entry"}
# }
ZONES_CONFIG_PATH = DATA_DIR / "zones.json"

def load_zones() -> dict:
    """Load zone definitions from JSON.  Returns empty dict if file missing."""
    if ZONES_CONFIG_PATH.exists():
        with open(ZONES_CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}

# ---------------------------------------------------------------------------
# Dwell-Time Thresholds (two-layer logic)
# ---------------------------------------------------------------------------
# Layer 1: minimum seconds in a single grid cell to count as a "browsing" segment
CELL_DWELL_THRESHOLD_S = float(os.getenv("INTELLISALES_CELL_DWELL", "2.0"))

# Layer 2: minimum summed qualifying-segment time in a zone to fire a dwell event
ZONE_DWELL_THRESHOLD_S = float(os.getenv("INTELLISALES_ZONE_DWELL", "7.0"))

# ---------------------------------------------------------------------------
# Footfall — Entry/Exit Line
# ---------------------------------------------------------------------------
# Defined as two world-coordinate endpoints: [[x1,y1], [x2,y2]]
# Direction vector points "inward" — crossing in that direction = IN
FOOTFALL_LINE_CONFIG_PATH = DATA_DIR / "footfall_line.json"

def load_footfall_line() -> dict | None:
    """Load the footfall entry/exit line definition.
    
    Expected JSON:
    {
        "point_a": [x1, y1],
        "point_b": [x2, y2],
        "inward_direction": [dx, dy]   // unit vector pointing "into" the store
    }
    """
    if FOOTFALL_LINE_CONFIG_PATH.exists():
        with open(FOOTFALL_LINE_CONFIG_PATH, "r") as f:
            return json.load(f)
    return None

# ---------------------------------------------------------------------------
# Crowd-Density Fallback
# ---------------------------------------------------------------------------
# If more than this many people in a single frame → stop per-track attribution
MAX_CROWD_SIZE = int(os.getenv("INTELLISALES_MAX_CROWD", "8"))

# ---------------------------------------------------------------------------
# Queue Intelligence
# ---------------------------------------------------------------------------
AVG_SERVICE_TIME_S = float(os.getenv("INTELLISALES_AVG_SVC_TIME", "120.0"))  # seconds
CONVERSION_RATE = float(os.getenv("INTELLISALES_CONV_RATE", "0.25"))  # fraction of footfall that buys
MAX_ACCEPTABLE_WAIT_TIME_S = float(os.getenv("INTELLISALES_MAX_WAIT", "300.0"))  # seconds
AVG_SHOPPING_TIME_S = float(os.getenv("INTELLISALES_AVG_SHOP_TIME", "900.0"))  # seconds
SMOOTHING_ALPHA = float(os.getenv("INTELLISALES_SMOOTH_ALPHA", "0.3"))

# ---------------------------------------------------------------------------
# ROI / Owner Dashboard
# ---------------------------------------------------------------------------
MONTHLY_SYSTEM_COST = float(os.getenv("INTELLISALES_SYS_COST", "50000.0"))  # INR
AVG_BASKET_VALUE = float(os.getenv("INTELLISALES_BASKET_VAL", "1500.0"))  # INR
STOCKOUT_PREVENTED_VALUE = float(os.getenv("INTELLISALES_STOCKOUT_VAL", "500.0"))  # INR per event

# ---------------------------------------------------------------------------
# Data Retention
# ---------------------------------------------------------------------------
DATA_RETENTION_DAYS = int(os.getenv("INTELLISALES_RETENTION_DAYS", "7"))

# ---------------------------------------------------------------------------
# Multi-Camera Re-ID
# ---------------------------------------------------------------------------
# Cosine similarity threshold to match a person across cameras
REID_SIMILARITY_THRESHOLD = float(os.getenv("INTELLISALES_REID_SIM", "0.72"))

# Max seconds between a track disappearing on camera A and appearing on camera B
# to be considered a "handoff" (boosts matching priority)
REID_HANDOFF_WINDOW_S = float(os.getenv("INTELLISALES_REID_HANDOFF", "30.0"))

# Seconds after which a global track with no detections is garbage-collected
REID_GALLERY_TIMEOUT_S = float(os.getenv("INTELLISALES_REID_TIMEOUT", "120.0"))

# Maximum simultaneous cameras supported
MAX_CAMERAS = int(os.getenv("INTELLISALES_MAX_CAMERAS", "8"))

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
API_HOST = os.getenv("INTELLISALES_HOST", "0.0.0.0")
API_PORT = int(os.getenv("INTELLISALES_PORT", "8000"))
CORS_ORIGINS = os.getenv("INTELLISALES_CORS", "http://localhost:5173").split(",")
