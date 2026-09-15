"""Longevity calibration primitives for STEP-0015J.

These helpers aggregate already measured player-season value. They never infer
missing basketball statistics and never use player identity as a feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np

from goatlab.rankings.uncertainty_aggregation import fixed_midrank_ecdf, longest_true_run


@dataclass(frozen=True)
class ThresholdComponents:
    """Raw threshold components for every simulation draw."""

    breadth: np.ndarray
    capped_area: np.ndarray
    longest_run: np.ndarray


@dataclass(frozen=True)
class LongevityScale:
    """Frozen component and final reference distributions."""

    breadth: np.ndarray
    area: np.ndarray
    run: np.ndarray
    final: np.ndarray
    p80: float
    p90: float
    weights: tuple[float, float, float]


def threshold_components(
    values: np.ndarray,
    seasons: np.ndarray,
    *,
    p80: float = 80.0,
    p90: float = 90.0,
) -> ThresholdComponents:
    """Compute breadth, capped area, and exact consecutive run by draw."""

    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("values must be a draws-by-seasons matrix")
    if p90 <= p80:
        raise ValueError("p90 must exceed p80")
    elite = matrix >= p80
    return ThresholdComponents(
        breadth=np.sum(elite, axis=1).astype(float),
        capped_area=np.sum(np.clip((matrix - p80) / (p90 - p80), 0.0, 1.0), axis=1),
        longest_run=longest_true_run(elite, seasons),
    )


def transformed_component_draws(
    components: ThresholdComponents, scale: LongevityScale
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Map raw component draws through their fixed reference ECDFs."""

    return (
        fixed_midrank_ecdf(scale.breadth, components.breadth),
        fixed_midrank_ecdf(scale.area, components.capped_area),
        fixed_midrank_ecdf(scale.run, components.longest_run),
    )


def final_score_draws(components: ThresholdComponents, scale: LongevityScale) -> np.ndarray:
    """Apply component ECDFs, frozen weights, and one fixed final ECDF."""

    breadth, area, run = transformed_component_draws(components, scale)
    raw = scale.weights[0] * breadth + scale.weights[1] * area + scale.weights[2] * run
    return fixed_midrank_ecdf(scale.final, raw)


def expected_raw_component_score(components: ThresholdComponents, scale: LongevityScale) -> float:
    """Transform posterior mean raw components and combine them."""

    breadth = fixed_midrank_ecdf(scale.breadth, np.asarray([np.mean(components.breadth)]))[0]
    area = fixed_midrank_ecdf(scale.area, np.asarray([np.mean(components.capped_area)]))[0]
    run = fixed_midrank_ecdf(scale.run, np.asarray([np.mean(components.longest_run)]))[0]
    raw = scale.weights[0] * breadth + scale.weights[1] * area + scale.weights[2] * run
    return float(fixed_midrank_ecdf(scale.final, np.asarray([raw]))[0])


def expected_transformed_component_score(
    components: ThresholdComponents, scale: LongevityScale
) -> float:
    """Combine posterior means on each transformed component scale."""

    breadth, area, run = transformed_component_draws(components, scale)
    raw = (
        scale.weights[0] * float(np.mean(breadth))
        + scale.weights[1] * float(np.mean(area))
        + scale.weights[2] * float(np.mean(run))
    )
    return float(fixed_midrank_ecdf(scale.final, np.asarray([raw]))[0])


def modal_run_component_score(components: ThresholdComponents, scale: LongevityScale) -> float:
    """Use expected breadth/area and the modal discrete run as a diagnostic."""

    run_values, counts = np.unique(components.longest_run, return_counts=True)
    modal_run = run_values[int(np.argmax(counts))]
    diagnostic = ThresholdComponents(
        breadth=np.asarray([np.mean(components.breadth)]),
        capped_area=np.asarray([np.mean(components.capped_area)]),
        longest_run=np.asarray([modal_run]),
    )
    return expected_raw_component_score(diagnostic, scale)


def conformal_radius(residuals: np.ndarray, level: float) -> float:
    """Return the finite-sample absolute-residual conformal radius."""

    values = np.sort(np.abs(np.asarray(residuals, dtype=float)))
    if values.size == 0:
        raise ValueError("conformal calibration requires residuals")
    rank = min(values.size, ceil((values.size + 1) * level))
    return float(values[rank - 1])


def run_bridge_candidates(
    p80_probability: np.ndarray,
    seasons: np.ndarray,
    *,
    uncertain_low: float = 0.25,
    uncertain_high: float = 0.75,
    credible: float = 0.50,
) -> list[tuple[int, int, int]]:
    """Return (index, left_run, right_run) uncertain P80 bridge events."""

    probability = np.asarray(p80_probability, dtype=float)
    ordered = np.asarray(seasons, dtype=int)
    events: list[tuple[int, int, int]] = []
    for index in range(1, len(ordered) - 1):
        if not uncertain_low < probability[index] < uncertain_high:
            continue
        if ordered[index - 1] + 1 != ordered[index] or ordered[index] + 1 != ordered[index + 1]:
            continue
        if probability[index - 1] < credible or probability[index + 1] < credible:
            continue
        left = 0
        cursor = index - 1
        while cursor >= 0 and probability[cursor] >= credible:
            if cursor < index - 1 and ordered[cursor] + 1 != ordered[cursor + 1]:
                break
            left += 1
            cursor -= 1
        right = 0
        cursor = index + 1
        while cursor < len(ordered) and probability[cursor] >= credible:
            if cursor > index + 1 and ordered[cursor - 1] + 1 != ordered[cursor]:
                break
            right += 1
            cursor += 1
        events.append((index, left, right))
    return events
