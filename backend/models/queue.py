"""
IntelliSales -- Pydantic Models for Queue Intelligence
"""

from __future__ import annotations
from typing import Dict, Optional
from pydantic import BaseModel


class QueueConfig(BaseModel):
    avg_service_time_s: Optional[float] = None
    conversion_rate: Optional[float] = None
    max_acceptable_wait_time_s: Optional[float] = None
    avg_shopping_time_s: Optional[float] = None
    smoothing_alpha: Optional[float] = None


class QueuePrediction(BaseModel):
    service_rate_per_counter: float
    total_capacity: float
    predicted_checkout_demand: float
    congestion_gap: float
    predicted_queue_size: float
    max_acceptable_queue: float
    should_open_counter: bool
    counters_open: int
    current_total_queue: int
    footfall_rate: float
    queue_sizes: Dict[str, int]


class CounterAction(BaseModel):
    counter_id: str
