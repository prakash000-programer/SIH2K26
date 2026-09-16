"""
IntelliSales -- Cross-Camera Person Re-Identification (Re-ID) Engine

Lightweight appearance-based Re-ID for hackathon demo:
  1. AppearanceFeatureExtractor: extracts a ~400-dim feature vector from a
     person crop using HSV color histograms + body proportions (no GPU needed).
  2. GlobalTrackRegistry: thread-safe gallery that matches new local tracks
     against known global identities using cosine similarity.

Privacy:
  - Feature vectors are ephemeral numerical arrays, NOT face templates or
    biometric data.  They cannot reconstruct the original image.
  - All data is volatile (in-memory only) and discarded on shutdown.

Hardware-agnostic: runs on any CPU (laptop, QCS6490 edge board, etc.).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    REID_SIMILARITY_THRESHOLD,
    REID_HANDOFF_WINDOW_S,
    REID_GALLERY_TIMEOUT_S,
)

logger = logging.getLogger("intellisales.cv.reid")


# ---------------------------------------------------------------------------
# Feature Extraction
# ---------------------------------------------------------------------------

class AppearanceFeatureExtractor:
    """Extracts a lightweight appearance feature vector from a person crop.

    Feature composition (~400-dim float32):
      - Upper-body HSV color histogram (3 × 8 × 8 = 192 bins, normalised)
      - Lower-body HSV color histogram (192 bins)
      - Body aspect ratio (1 value)
      - Upper/lower mean colour (6 values: 3 + 3, HSV means)

    All pure OpenCV -- no GPU, no neural network.
    """

    H_BINS = 8
    S_BINS = 8
    V_BINS = 3  # coarser on value channel
    HIST_SIZE = H_BINS * S_BINS * V_BINS  # 192

    def extract(self, person_crop: np.ndarray) -> Optional[np.ndarray]:
        """Extract feature vector from a BGR person crop.

        Args:
            person_crop: BGR numpy array of the person bounding box region.

        Returns:
            Normalised float32 feature vector, or None if crop is too small.
        """
        if person_crop is None:
            return None
        h, w = person_crop.shape[:2]
        if h < 20 or w < 10:
            return None

        hsv = cv2.cvtColor(person_crop, cv2.COLOR_BGR2HSV)

        # Split upper body (top 45%) and lower body (bottom 55%)
        split_y = int(h * 0.45)
        upper = hsv[:split_y, :]
        lower = hsv[split_y:, :]

        upper_hist = self._compute_hist(upper)
        lower_hist = self._compute_hist(lower)

        # Body proportions
        aspect_ratio = np.array([h / max(w, 1)], dtype=np.float32)

        # Mean colour features (HSV) for upper and lower
        upper_mean = np.mean(upper.reshape(-1, 3), axis=0).astype(np.float32) / 255.0
        lower_mean = np.mean(lower.reshape(-1, 3), axis=0).astype(np.float32) / 255.0

        # Concatenate all features
        feature = np.concatenate([
            upper_hist,       # 192
            lower_hist,       # 192
            aspect_ratio,     # 1
            upper_mean,       # 3
            lower_mean,       # 3
        ])  # total ~391

        # L2 normalise the full vector for cosine similarity later
        norm = np.linalg.norm(feature)
        if norm > 1e-6:
            feature = feature / norm

        return feature

    def _compute_hist(self, hsv_region: np.ndarray) -> np.ndarray:
        """Compute a flattened, normalised HSV histogram."""
        if hsv_region.size == 0:
            return np.zeros(self.HIST_SIZE, dtype=np.float32)

        hist = cv2.calcHist(
            [hsv_region], [0, 1, 2],
            None,
            [self.H_BINS, self.S_BINS, self.V_BINS],
            [0, 180, 0, 256, 0, 256],
        )
        hist = hist.flatten().astype(np.float32)
        total = hist.sum()
        if total > 0:
            hist /= total
        return hist


# ---------------------------------------------------------------------------
# Global Track Entry
# ---------------------------------------------------------------------------

@dataclass
class GlobalTrack:
    """A globally-identified person tracked across cameras."""
    global_id: int
    feature: np.ndarray                         # appearance feature vector
    camera_id: str                              # last seen camera
    last_seen_time: float                       # epoch timestamp
    first_seen_time: float                      # epoch timestamp
    gender: str = "Unknown"
    gender_confidence: float = 0.0
    dwell_time_s: float = 0.0
    cameras_visited: list = field(default_factory=list)  # list of camera_ids
    local_track_id: int = -1                    # current local track id on last_seen camera
    feature_samples: list = field(default_factory=list)  # running feature buffer for averaging
    _max_samples: int = 10

    def update_feature(self, new_feature: np.ndarray) -> None:
        """Update appearance feature with exponential moving average."""
        self.feature_samples.append(new_feature)
        if len(self.feature_samples) > self._max_samples:
            self.feature_samples.pop(0)

        # Average all stored feature samples
        stacked = np.stack(self.feature_samples)
        avg = np.mean(stacked, axis=0)
        norm = np.linalg.norm(avg)
        if norm > 1e-6:
            avg = avg / norm
        self.feature = avg


# ---------------------------------------------------------------------------
# Global Track Registry
# ---------------------------------------------------------------------------

class GlobalTrackRegistry:
    """Thread-safe registry mapping local per-camera tracks to global IDs.

    Algorithm:
      1. For each local track on a camera frame, extract appearance features.
      2. Compare against gallery using cosine similarity.
      3. If similarity >= threshold AND the person was recently seen on another
         camera (within handoff window), assign the existing global_id.
      4. Otherwise if similarity >= threshold on same camera, it's likely the
         same person re-entering — assign same global_id.
      5. Else: create a new global_id.
    """

    def __init__(
        self,
        similarity_threshold: float = REID_SIMILARITY_THRESHOLD,
        handoff_window_s: float = REID_HANDOFF_WINDOW_S,
        gallery_timeout_s: float = REID_GALLERY_TIMEOUT_S,
    ):
        self._threshold = similarity_threshold
        self._handoff_window = handoff_window_s
        self._gallery_timeout = gallery_timeout_s

        self._gallery: Dict[int, GlobalTrack] = {}  # global_id -> GlobalTrack
        self._next_global_id = 1
        self._lock = threading.Lock()

        # Mapping: (camera_id, local_track_id) -> global_id
        # Avoids re-matching every frame for already-associated tracks
        self._local_to_global: Dict[Tuple[str, int], int] = {}

        self._feature_extractor = AppearanceFeatureExtractor()

    @property
    def feature_extractor(self) -> AppearanceFeatureExtractor:
        return self._feature_extractor

    def match_or_create(
        self,
        camera_id: str,
        local_track_id: int,
        person_crop: np.ndarray,
        gender: str = "Unknown",
        gender_confidence: float = 0.0,
        dwell_time_s: float = 0.0,
        current_time: Optional[float] = None,
    ) -> int:
        """Match a local track to a global identity, or create a new one.

        Args:
            camera_id: Identifier of the camera that detected this person.
            local_track_id: ByteTrack local ID on this camera.
            person_crop: BGR numpy crop of the person bounding box.
            gender: Classified gender string.
            gender_confidence: Gender classification confidence.
            dwell_time_s: How long this person has been tracked on this camera.
            current_time: Current epoch time (defaults to time.time()).

        Returns:
            The global track ID assigned to this person.
        """
        now = current_time or time.time()

        with self._lock:
            # Fast path: already associated
            key = (camera_id, local_track_id)
            if key in self._local_to_global:
                gid = self._local_to_global[key]
                if gid in self._gallery:
                    gt = self._gallery[gid]
                    gt.last_seen_time = now
                    gt.camera_id = camera_id
                    gt.local_track_id = local_track_id
                    gt.gender = gender
                    gt.gender_confidence = gender_confidence
                    gt.dwell_time_s = dwell_time_s
                    if camera_id not in gt.cameras_visited:
                        gt.cameras_visited.append(camera_id)

                    # Only extract additional appearance samples if we have fewer than 3 samples
                    if len(gt.feature_samples) < 3:
                        feature = self._feature_extractor.extract(person_crop)
                        if feature is not None:
                            gt.update_feature(feature)

                    return gid

            # Extract appearance feature
            feature = self._feature_extractor.extract(person_crop)
            if feature is None:
                # Can't extract features -- create a new track with dummy feature
                gid = self._create_new_track(
                    camera_id, local_track_id, np.zeros(391, dtype=np.float32),
                    gender, gender_confidence, dwell_time_s, now
                )
                return gid

            # Search gallery for best match
            best_gid = -1
            best_sim = -1.0
            best_is_handoff = False

            for gid, gt in self._gallery.items():
                if gt.feature is None or np.linalg.norm(gt.feature) < 1e-6:
                    continue

                sim = float(np.dot(feature, gt.feature))  # cosine sim (both L2-normed)

                # Boost similarity for cross-camera handoff scenario
                is_handoff = (
                    gt.camera_id != camera_id and
                    (now - gt.last_seen_time) < self._handoff_window
                )

                effective_sim = sim
                if is_handoff:
                    # Slightly lower threshold for handoffs
                    effective_sim += 0.05

                if effective_sim > best_sim:
                    best_sim = effective_sim
                    best_gid = gid
                    best_is_handoff = is_handoff

            if best_sim >= self._threshold and best_gid > 0:
                # Match found
                gt = self._gallery[best_gid]
                gt.last_seen_time = now
                gt.local_track_id = local_track_id
                gt.gender = gender
                gt.gender_confidence = gender_confidence
                gt.dwell_time_s = dwell_time_s
                gt.update_feature(feature)

                if camera_id != gt.camera_id:
                    if camera_id not in gt.cameras_visited:
                        gt.cameras_visited.append(camera_id)
                    logger.info(
                        f"[Re-ID] Cross-camera handoff: Global #{best_gid} "
                        f"moved from {gt.camera_id} -> {camera_id} "
                        f"(sim={best_sim:.3f})"
                    )
                gt.camera_id = camera_id

                self._local_to_global[key] = best_gid
                return best_gid
            else:
                # No match -- create new global track
                gid = self._create_new_track(
                    camera_id, local_track_id, feature,
                    gender, gender_confidence, dwell_time_s, now
                )
                return gid

    def _create_new_track(
        self,
        camera_id: str,
        local_track_id: int,
        feature: np.ndarray,
        gender: str,
        gender_confidence: float,
        dwell_time_s: float,
        now: float,
    ) -> int:
        """Create a new global track entry (must be called with lock held)."""
        gid = self._next_global_id
        self._next_global_id += 1

        self._gallery[gid] = GlobalTrack(
            global_id=gid,
            feature=feature,
            camera_id=camera_id,
            last_seen_time=now,
            first_seen_time=now,
            gender=gender,
            gender_confidence=gender_confidence,
            dwell_time_s=dwell_time_s,
            cameras_visited=[camera_id],
            local_track_id=local_track_id,
            feature_samples=[feature],
        )
        self._local_to_global[(camera_id, local_track_id)] = gid
        return gid

    def cleanup_stale(self, current_time: Optional[float] = None) -> List[int]:
        """Remove global tracks not seen within the gallery timeout.

        Returns list of removed global IDs.
        """
        now = current_time or time.time()
        removed = []

        with self._lock:
            stale_ids = [
                gid for gid, gt in self._gallery.items()
                if (now - gt.last_seen_time) > self._gallery_timeout
            ]
            for gid in stale_ids:
                del self._gallery[gid]
                removed.append(gid)

            # Clean local-to-global mappings
            stale_keys = [
                k for k, v in self._local_to_global.items()
                if v in stale_ids
            ]
            for k in stale_keys:
                del self._local_to_global[k]

        if removed:
            logger.debug(f"[Re-ID] Cleaned {len(removed)} stale global tracks: {removed}")

        return removed

    def remove_local_track(self, camera_id: str, local_track_id: int) -> None:
        """Called when a local track exits a camera (ByteTrack lost it)."""
        with self._lock:
            key = (camera_id, local_track_id)
            self._local_to_global.pop(key, None)

    def get_all_global_tracks(self) -> List[Dict]:
        """Return snapshot of all active global tracks for API/WebSocket broadcast."""
        with self._lock:
            result = []
            for gid, gt in self._gallery.items():
                result.append({
                    "global_id": gt.global_id,
                    "camera_id": gt.camera_id,
                    "local_track_id": gt.local_track_id,
                    "gender": gt.gender,
                    "gender_confidence": round(gt.gender_confidence, 2),
                    "dwell_time_s": round(gt.dwell_time_s, 1),
                    "first_seen_time": gt.first_seen_time,
                    "last_seen_time": gt.last_seen_time,
                    "cameras_visited": list(gt.cameras_visited),
                    "total_cameras": len(gt.cameras_visited),
                })
            return result

    def get_global_id_for_local(self, camera_id: str, local_track_id: int) -> Optional[int]:
        """Look up the global ID for a given (camera_id, local_track_id)."""
        with self._lock:
            return self._local_to_global.get((camera_id, local_track_id))

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._gallery)


# Module-level singleton for cross-camera Re-ID
global_registry = GlobalTrackRegistry()
