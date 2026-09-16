"""
IntelliSales -- Inventory Frame Differencing

Compares a reference "stocked" image against a "current" image
to detect empty/occupied status for a shelf slot.

Method:
    1. Convert both images to grayscale.
    2. Resize current to match reference dimensions.
    3. cv2.absdiff() to compute pixel-level difference.
    4. Threshold the diff to get a binary mask.
    5. Count changed pixels / total pixels = diff_ratio.
    6. If diff_ratio > threshold -> potentially empty.

Privacy: images are processed in-memory only, never stored.
"""

from __future__ import annotations

import cv2
import numpy as np


def compare_shelf_images(
    reference: np.ndarray,
    current: np.ndarray,
    threshold: int = 50,
) -> float:
    """Compare a reference shelf image against a current image.

    Args:
        reference: BGR reference ("stocked") image.
        current: BGR current image.
        threshold: Pixel intensity difference threshold (0-255).

    Returns:
        diff_ratio: Fraction of pixels that differ significantly (0.0 - 1.0).
    """
    # Convert to grayscale
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    cur_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)

    # Resize current to match reference
    if ref_gray.shape != cur_gray.shape:
        cur_gray = cv2.resize(cur_gray, (ref_gray.shape[1], ref_gray.shape[0]))

    # Apply Gaussian blur to reduce noise
    ref_gray = cv2.GaussianBlur(ref_gray, (5, 5), 0)
    cur_gray = cv2.GaussianBlur(cur_gray, (5, 5), 0)

    # Compute absolute difference
    diff = cv2.absdiff(ref_gray, cur_gray)

    # Threshold to get binary mask of significant changes
    _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    # Calculate ratio of changed pixels
    total_pixels = binary.shape[0] * binary.shape[1]
    changed_pixels = np.count_nonzero(binary)
    diff_ratio = changed_pixels / total_pixels if total_pixels > 0 else 0.0

    return float(diff_ratio)
