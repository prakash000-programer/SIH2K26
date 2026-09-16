"""
IntelliSales -- Queue Prediction Formula Chain

Implements the EXACT predictive formula chain as specified:
    service_rate_per_counter = 1 / avg_service_time
    total_capacity = counters_open * service_rate_per_counter
    predicted_checkout_demand = footfall_rate * conversion_rate
    congestion_gap = predicted_checkout_demand - total_capacity
    predicted_queue_size = current_queue_size + (congestion_gap * avg_shopping_time)
    max_acceptable_queue = counters_open * (max_acceptable_wait_time / avg_service_time)
    if predicted_queue_size > max_acceptable_queue: fire alert

Exponential smoothing:
    running_average = 0.7 * previous_average + 0.3 * latest_reading
"""

from __future__ import annotations

from typing import Dict

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    AVG_SERVICE_TIME_S, CONVERSION_RATE, MAX_ACCEPTABLE_WAIT_TIME_S,
    AVG_SHOPPING_TIME_S, SMOOTHING_ALPHA,
)
from backend.queue_intel.smoothing import exponential_smooth


class QueuePredictor:
    """Full predictive formula chain for queue intelligence."""

    def __init__(self):
        # Configurable parameters (can be updated via dashboard)
        self.avg_service_time = AVG_SERVICE_TIME_S        # seconds
        self.conversion_rate = CONVERSION_RATE            # fraction
        self.max_acceptable_wait_time = MAX_ACCEPTABLE_WAIT_TIME_S  # seconds
        self.avg_shopping_time = AVG_SHOPPING_TIME_S      # seconds
        self.smoothing_alpha = SMOOTHING_ALPHA            # 0.3

        # Smoothed values
        self._smoothed_footfall_rate: float | None = None
        self._smoothed_service_time: float | None = None

    def predict(
        self,
        footfall_rate: float,       # arrivals per minute
        current_queue_size: int,
        counters_open: int = 1,
    ) -> Dict:
        """Run the full prediction formula chain.

        Args:
            footfall_rate: Current footfall IN rate (per minute).
            current_queue_size: Total persons in all queues right now.
            counters_open: Number of checkout counters currently open.

        Returns:
            Dict with all formula outputs.
        """
        # Apply exponential smoothing to footfall rate
        if self._smoothed_footfall_rate is None:
            self._smoothed_footfall_rate = footfall_rate
        else:
            self._smoothed_footfall_rate = exponential_smooth(
                self._smoothed_footfall_rate, footfall_rate, self.smoothing_alpha
            )

        # Apply smoothing to service time
        if self._smoothed_service_time is None:
            self._smoothed_service_time = self.avg_service_time
        else:
            self._smoothed_service_time = exponential_smooth(
                self._smoothed_service_time, self.avg_service_time, self.smoothing_alpha
            )

        # --- Formula chain (exactly as specified) ---

        # Convert footfall rate from per-minute to per-second for consistency
        footfall_rate_per_s = self._smoothed_footfall_rate / 60.0

        service_rate_per_counter = 1.0 / self._smoothed_service_time if self._smoothed_service_time > 0 else 0.0
        total_capacity = counters_open * service_rate_per_counter

        predicted_checkout_demand = footfall_rate_per_s * self.conversion_rate
        congestion_gap = predicted_checkout_demand - total_capacity

        predicted_queue_size = current_queue_size + (congestion_gap * self.avg_shopping_time)
        predicted_queue_size = max(0.0, predicted_queue_size)  # can't be negative

        max_acceptable_queue = (
            counters_open * (self.max_acceptable_wait_time / self._smoothed_service_time)
            if self._smoothed_service_time > 0 else 0.0
        )

        should_open_counter = predicted_queue_size > max_acceptable_queue

        return {
            "service_rate_per_counter": service_rate_per_counter,
            "total_capacity": total_capacity,
            "predicted_checkout_demand": predicted_checkout_demand,
            "congestion_gap": congestion_gap,
            "predicted_queue_size": predicted_queue_size,
            "max_acceptable_queue": max_acceptable_queue,
            "should_open_counter": should_open_counter,
            "smoothed_footfall_rate": self._smoothed_footfall_rate,
            "smoothed_service_time": self._smoothed_service_time,
        }

    def reset_smoothing(self) -> None:
        """Reset smoothed values (e.g., at shift change)."""
        self._smoothed_footfall_rate = None
        self._smoothed_service_time = None
