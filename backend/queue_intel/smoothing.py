"""
IntelliSales -- Exponential Smoothing

Simple exponential smoothing as specified:
    running_average = (1 - alpha) * previous_average + alpha * latest_reading

Default alpha = 0.3, so:
    running_average = 0.7 * previous + 0.3 * latest
"""


def exponential_smooth(previous: float, latest: float, alpha: float = 0.3) -> float:
    """Apply exponential smoothing.

    Args:
        previous: Previous smoothed value.
        latest: Latest raw reading.
        alpha: Smoothing factor (0 < alpha < 1). Higher = more reactive.
               Default 0.3 as specified.

    Returns:
        New smoothed value.
    """
    return (1.0 - alpha) * previous + alpha * latest
