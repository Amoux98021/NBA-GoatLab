"""Constitutional Overall uncertainty mechanics for STEP-0015L.

The functions preserve all seven nominal weights. They never replace an
interval-valued dimension with an exact midpoint, renormalize around a missing
dimension, or use confidence as a quality multiplier.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from goatlab.rankings.overall import validate_weights

OVERALL_UNCERTAINTY_VERSION = "goatlab-v1-overall-v2-uncertainty-research"
DEFENSE_CAVEAT = "DEFENSE_V1_FROZEN_PENDING_REVISION"
FROZEN_WEIGHTS: dict[str, float] = {
    "PEAK": 0.17,
    "LONGEVITY": 0.14,
    "OFFENSE": 0.16,
    "DEFENSE": 0.14,
    "PLAYOFFS": 0.18,
    "ACCOLADES": 0.10,
    "WINNING": 0.11,
}


def validate_frozen_weights() -> tuple[float, ...]:
    """Return the fixed STEP-0015 weights after exact validation."""

    return validate_weights(FROZEN_WEIGHTS)


def fixed_other_contribution(profile: Mapping[str, float | None]) -> float | None:
    """Return the fixed five-dimension contribution or NULL if one is absent."""

    total = 0.0
    for dimension in ("OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"):
        value = profile.get(dimension)
        if value is None or not math.isfinite(float(value)):
            return None
        number = float(value)
        if not 0.0 <= number <= 100.0:
            raise ValueError("dimension scores must be in [0, 100]")
        total += FROZEN_WEIGHTS[dimension] * number
    return total


def overall_draws(
    peak_draws: np.ndarray,
    longevity_draws: np.ndarray,
    fixed_contribution: float,
) -> np.ndarray:
    """Combine paired Peak/Longevity draws without changing any weight."""

    peak = np.asarray(peak_draws, dtype=float)
    longevity = np.asarray(longevity_draws, dtype=float)
    if peak.shape != longevity.shape or peak.ndim != 1 or peak.size == 0:
        raise ValueError("Peak and Longevity draws must be paired non-empty vectors")
    if not np.isfinite(peak).all() or not np.isfinite(longevity).all():
        raise ValueError("dimension draws must be finite")
    if not np.all((peak >= 0.0) & (peak <= 100.0)) or not np.all(
        (longevity >= 0.0) & (longevity <= 100.0)
    ):
        raise ValueError("dimension draws must be in [0, 100]")
    result = (
        FROZEN_WEIGHTS["PEAK"] * peak
        + FROZEN_WEIGHTS["LONGEVITY"] * longevity
        + float(fixed_contribution)
    )
    return np.clip(result, 0.0, 100.0)


def uncertainty_decomposition(
    peak_draws: np.ndarray, longevity_draws: np.ndarray
) -> dict[str, float]:
    """Decompose modeled Overall variance into Peak, Longevity, and covariance."""

    peak = np.asarray(peak_draws, dtype=float)
    longevity = np.asarray(longevity_draws, dtype=float)
    if peak.shape != longevity.shape or peak.ndim != 1 or peak.size < 2:
        raise ValueError("paired draw vectors must contain at least two observations")
    peak_part = FROZEN_WEIGHTS["PEAK"] ** 2 * float(np.var(peak, ddof=0))
    longevity_part = FROZEN_WEIGHTS["LONGEVITY"] ** 2 * float(np.var(longevity, ddof=0))
    covariance_part = (
        2.0
        * FROZEN_WEIGHTS["PEAK"]
        * FROZEN_WEIGHTS["LONGEVITY"]
        * float(np.cov(peak, longevity, ddof=0)[0, 1])
    )
    total = peak_part + longevity_part + covariance_part
    empirical = float(
        np.var(
            FROZEN_WEIGHTS["PEAK"] * peak + FROZEN_WEIGHTS["LONGEVITY"] * longevity,
            ddof=0,
        )
    )
    return {
        "peak_variance_contribution": peak_part,
        "longevity_variance_contribution": longevity_part,
        "covariance_contribution": covariance_part,
        "analytic_total": total,
        "empirical_total": empirical,
        "analytic_empirical_difference": total - empirical,
    }


def overall_status(
    *,
    peak_status: str,
    longevity_status: str,
    other_dimensions_available: bool,
    evidence_pattern_point_eligible: bool,
) -> str:
    """Assign Overall status from evidence—not identity, reputation, or confidence."""

    if (
        not other_dimensions_available
        or peak_status == "PEAK_UNAVAILABLE"
        or longevity_status == "LONGEVITY_UNAVAILABLE"
    ):
        return "OVERALL_UNAVAILABLE"
    if peak_status == "OFFICIAL_PEAK_POINT" and longevity_status == "OFFICIAL_LONGEVITY_POINT":
        return "OFFICIAL_OVERALL_POINT"
    if evidence_pattern_point_eligible:
        return "PROVISIONAL_OVERALL_POINT"
    return "OVERALL_INTERVAL_ONLY"


def robust_order_label(probability_a_above_b: float) -> str:
    """Classify pairwise evidence symmetrically around an uncertain center."""

    probability = float(probability_a_above_b)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("ordering probability must be in [0, 1]")
    if probability >= 0.90:
        return "ROBUST_ORDER"
    if probability >= 0.65:
        return "LEAN_ORDER"
    if probability <= 0.10:
        return "ROBUST_REVERSE"
    if probability <= 0.35:
        return "LEAN_REVERSE"
    return "UNCERTAIN_ORDER"


validate_frozen_weights()
