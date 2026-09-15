"""Uncertainty-aware Peak and Longevity primitives for STEP-0015I.

This module aggregates factual/link-calibrated player-season measurements.  It
does not predict a missing basketball statistic, and confidence never changes
the quality estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PEAK_THREE_YEAR_WEIGHT = 0.70
LONGEVITY_WEIGHTS = (0.35, 0.40, 0.25)
P80 = 80.0
P90 = 90.0


@dataclass(frozen=True)
class PeakAggregation:
    """Peak draws and the selected window/apex indices for every draw."""

    values: np.ndarray
    window_indices: np.ndarray
    apex_indices: np.ndarray
    windows: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class LongevityComponents:
    """The three constitutional Longevity components for every draw."""

    breadth: np.ndarray
    capped_area: np.ndarray
    longest_run: np.ndarray


def contiguous_three_year_windows(seasons: np.ndarray) -> tuple[tuple[int, int, int], ...]:
    """Return complete three-season windows as column indices."""

    ordered = np.asarray(seasons, dtype=int)
    windows: list[tuple[int, int, int]] = []
    for index in range(max(0, ordered.size - 2)):
        if ordered[index + 1] == ordered[index] + 1 and ordered[index + 2] == ordered[index] + 2:
            windows.append((index, index + 1, index + 2))
    return tuple(windows)


def peak_draws(values: np.ndarray, seasons: np.ndarray) -> PeakAggregation:
    """Re-select the best complete window and apex inside every draw."""

    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("Peak values must be a draws-by-seasons matrix")
    windows = contiguous_three_year_windows(seasons)
    if not windows:
        return PeakAggregation(
            np.asarray([], dtype=float),
            np.asarray([], dtype=int),
            np.asarray([], dtype=int),
            windows,
        )
    window_values = np.column_stack(
        [np.mean(matrix[:, list(window)], axis=1) for window in windows]
    )
    # np.argmax deterministically selects the earliest window on an exact tie.
    selected = np.argmax(window_values, axis=1)
    three_year = window_values[np.arange(matrix.shape[0]), selected]
    apex_indices = np.argmax(matrix, axis=1)
    apex = matrix[np.arange(matrix.shape[0]), apex_indices]
    peak = PEAK_THREE_YEAR_WEIGHT * three_year + (1.0 - PEAK_THREE_YEAR_WEIGHT) * apex
    return PeakAggregation(peak, selected, apex_indices, windows)


def longest_true_run(indicators: np.ndarray, seasons: np.ndarray) -> np.ndarray:
    """Calculate exact longest consecutive true run for every simulation draw."""

    matrix = np.asarray(indicators, dtype=bool)
    ordered = np.asarray(seasons, dtype=int)
    if matrix.ndim != 2 or matrix.shape[1] != ordered.size:
        raise ValueError("indicator matrix and seasons are inconsistent")
    current = np.zeros(matrix.shape[0], dtype=int)
    longest = np.zeros(matrix.shape[0], dtype=int)
    previous: int | None = None
    for column, season in enumerate(ordered.tolist()):
        if previous is None or season != previous + 1:
            current.fill(0)
        current = np.where(matrix[:, column], current + 1, 0)
        longest = np.maximum(longest, current)
        previous = season
    return longest.astype(float)


def longevity_components(values: np.ndarray, seasons: np.ndarray) -> LongevityComponents:
    """Calculate frozen P80 breadth, capped P80-P90 area, and longest run."""

    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("Longevity values must be a draws-by-seasons matrix")
    elite = matrix >= P80
    breadth = np.sum(elite, axis=1).astype(float)
    capped_area = np.sum(np.clip((matrix - P80) / (P90 - P80), 0.0, 1.0), axis=1)
    longest = longest_true_run(elite, seasons)
    return LongevityComponents(breadth, capped_area, longest)


def fixed_midrank_ecdf(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Map values through one frozen midrank ECDF reference distribution."""

    ref = np.sort(np.asarray(reference, dtype=float))
    if ref.size == 0:
        raise ValueError("ECDF reference must be non-empty")
    target = np.asarray(values, dtype=float)
    below = np.searchsorted(ref, target, side="left")
    above = np.searchsorted(ref, target, side="right")
    equal = above - below
    midrank = below + (equal - 1.0) / 2.0
    denominator = max(ref.size - 1, 1)
    return np.clip(100.0 * midrank / denominator, 0.0, 100.0)


def longevity_score_draws(
    components: LongevityComponents,
    breadth_reference: np.ndarray,
    area_reference: np.ndarray,
    run_reference: np.ndarray,
    final_reference: np.ndarray,
) -> np.ndarray:
    """Apply frozen component ECDFs, 35/40/25, and one fixed final ECDF."""

    breadth = fixed_midrank_ecdf(breadth_reference, components.breadth)
    area = fixed_midrank_ecdf(area_reference, components.capped_area)
    run = fixed_midrank_ecdf(run_reference, components.longest_run)
    raw = LONGEVITY_WEIGHTS[0] * breadth + LONGEVITY_WEIGHTS[1] * area + LONGEVITY_WEIGHTS[2] * run
    return fixed_midrank_ecdf(final_reference, raw)


def quantile_interval(values: np.ndarray, level: float) -> tuple[float, float]:
    """Return a central empirical interval without a distributional assumption."""

    if not 0.0 < level < 1.0:
        raise ValueError("interval level must be between zero and one")
    tail = (1.0 - level) / 2.0
    data = np.asarray(values, dtype=float)
    return float(np.quantile(data, tail)), float(np.quantile(data, 1.0 - tail))


def longest_run_scalar(values: list[bool], seasons: list[int]) -> int:
    """Small scalar helper used by deterministic unit tests and reports."""

    matrix = np.asarray([values], dtype=bool)
    return int(longest_true_run(matrix, np.asarray(seasons, dtype=int))[0])
