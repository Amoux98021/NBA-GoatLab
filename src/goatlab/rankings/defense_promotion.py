"""Deterministic primitives for the STEP-0015B Defense V2 promotion audit."""

from __future__ import annotations

import hashlib
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

DEFENSE_PROMOTION_AUDIT_VERSION = "goatlab-v1-defense-v2-promotion-audit-v1"
DEFENSE_V2_VERSION = "goatlab-v1-defense-v2"
OVERALL_V2_COUNTERFACTUAL_VERSION = "goatlab-v1-overall-defense-v2-counterfactual-v1"


@dataclass(frozen=True)
class ContinuousPresenceEstimate:
    """A non-causal, continuously shrunk game-presence contrast."""

    raw_difference: float | None
    shrunk_difference: float | None
    games_with: int
    games_without: int
    effective_sample_size: float
    shrinkage: float
    threshold_continuity: float


@dataclass(frozen=True)
class RidgeModel:
    """Small interpretable ridge model used only for missing-Presence fallback."""

    coefficients: tuple[float, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    alpha: float


def continuous_presence_estimate(
    with_player: Sequence[float],
    without_player: Sequence[float],
    *,
    prior_effective_games: float = 20.0,
    target_with: int = 10,
    target_without: int = 5,
) -> ContinuousPresenceEstimate:
    """Estimate Presence continuously with no eligibility cliff.

    Two observations on both sides are required so the contrast is more than a
    single-game comparison. The effect magnitude uses the same effective-sample
    shrinkage as Candidate B. ``threshold_continuity`` approaches one smoothly
    at Candidate B's former 10-with/five-without gate.
    """
    left = [float(value) for value in with_player if math.isfinite(float(value))]
    right = [float(value) for value in without_player if math.isfinite(float(value))]
    n_with, n_without = len(left), len(right)
    effective = n_with * n_without / (n_with + n_without) if n_with + n_without else 0.0
    if n_with < 2 or n_without < 2:
        return ContinuousPresenceEstimate(None, None, n_with, n_without, effective, 0.0, 0.0)
    raw = statistics.fmean(left) - statistics.fmean(right)
    shrinkage = effective / (effective + prior_effective_games)
    continuity = min(1.0, n_with / target_with) * min(1.0, n_without / target_without)
    return ContinuousPresenceEstimate(
        raw,
        raw * shrinkage,
        n_with,
        n_without,
        effective,
        shrinkage,
        continuity,
    )


def blended_presence(
    expected: float,
    observed: float | None,
    reliability: float,
) -> tuple[float, str]:
    """Blend observed Presence smoothly into a portable expected fallback."""
    if not 0.0 <= expected <= 1.0:
        raise ValueError("expected Presence must be in [0, 1]")
    if not 0.0 <= reliability <= 1.0:
        raise ValueError("Presence reliability must be in [0, 1]")
    if observed is None:
        return expected, "EXPECTED_PRESENCE"
    if not 0.0 <= observed <= 1.0:
        raise ValueError("observed Presence must be in [0, 1]")
    value = expected + reliability * (observed - expected)
    return value, "OBSERVED" if reliability >= 1.0 else "RELIABILITY_BLEND"


def deterministic_group_fold(group: str, folds: int = 5) -> int:
    if folds < 2:
        raise ValueError("folds must be at least two")
    digest = hashlib.sha256(group.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % folds


def fit_ridge(
    features: npt.NDArray[np.float64],
    target: npt.NDArray[np.float64],
    *,
    alpha: float,
) -> RidgeModel:
    """Fit standardized ridge while leaving the intercept unpenalized."""
    if features.ndim != 2 or target.ndim != 1 or len(features) != len(target):
        raise ValueError("invalid ridge shapes")
    if len(target) == 0 or alpha < 0.0:
        raise ValueError("ridge requires rows and non-negative alpha")
    means = np.mean(features, axis=0)
    scales = np.std(features, axis=0)
    scales = np.where(scales > 1e-12, scales, 1.0)
    standardized = (features - means) / scales
    design = np.column_stack([np.ones(len(features)), standardized])
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    return RidgeModel(
        tuple(float(value) for value in coefficients),
        tuple(float(value) for value in means),
        tuple(float(value) for value in scales),
        float(alpha),
    )


def predict_ridge(model: RidgeModel, features: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    if features.ndim != 2 or features.shape[1] != len(model.feature_means):
        raise ValueError("ridge prediction shape does not match model")
    means = np.asarray(model.feature_means)
    scales = np.asarray(model.feature_scales)
    standardized = (features - means) / scales
    design = np.column_stack([np.ones(len(features)), standardized])
    prediction = design @ np.asarray(model.coefficients)
    return np.asarray(np.clip(prediction, 0.0, 1.0), dtype=np.float64)


def error_summary(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    """Summarize 0--100-scale calibration errors deterministically."""
    if len(actual) != len(predicted) or not actual:
        raise ValueError("paired non-empty values required")
    left = np.asarray(actual, dtype=float)
    right = np.asarray(predicted, dtype=float)
    error = (right - left) * 100.0
    absolute = np.abs(error)
    return {
        "observations": float(len(left)),
        "mean_signed_error": float(np.mean(error)),
        "mean_absolute_error": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "pearson": float(np.corrcoef(left, right)[0, 1]),
        "p10_error": float(np.quantile(error, 0.10)),
        "p25_error": float(np.quantile(error, 0.25)),
        "p50_error": float(np.quantile(error, 0.50)),
        "p75_error": float(np.quantile(error, 0.75)),
        "p90_error": float(np.quantile(error, 0.90)),
        "more_than_5_points": float(np.mean(absolute > 5.0)),
        "more_than_10_points": float(np.mean(absolute > 10.0)),
        "more_than_15_points": float(np.mean(absolute > 15.0)),
    }


def confidence_from_channels(
    *,
    team_available: bool,
    action_coverage: float,
    presence_reliability: float,
    fallback_type: str,
) -> tuple[str, tuple[str, ...]]:
    """Return evidence confidence without changing the quality estimate."""
    reasons: list[str] = []
    if not team_available:
        return "UNAVAILABLE", ("TEAM_CONTEXT_UNAVAILABLE",)
    if action_coverage < 1.0:
        reasons.append("PARTIAL_ACTION_COVERAGE")
    if fallback_type == "EXPECTED_PRESENCE":
        reasons.append("PRESENCE_ESTIMATED_FROM_PORTABLE_EVIDENCE")
    elif fallback_type == "RELIABILITY_BLEND":
        reasons.append("PRESENCE_LOW_SAMPLE_BLEND")
    if fallback_type == "OBSERVED" and presence_reliability >= 1.0 and action_coverage >= 0.95:
        return "STRONG", tuple(reasons)
    if presence_reliability >= 0.60 and action_coverage >= 0.75:
        return "MODERATE", tuple(reasons)
    return "LIMITED", tuple(reasons)


def weighted_three_channel(team: float, action: float, presence: float) -> float:
    values = (team, action, presence)
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        raise ValueError("Defense channels must be finite values in [0, 1]")
    return 0.30 * team + 0.30 * action + 0.40 * presence


def expected_presence_features(
    *,
    team: float,
    action: float,
    role: str | None,
) -> tuple[float, ...]:
    """Portable, era-relative features for the expected-Presence fallback."""
    roles = ("GUARD", "WING", "FORWARD", "BIG")
    return (
        team,
        action,
        team * action,
        1.0 if role is not None else 0.0,
        *(1.0 if role == candidate else 0.0 for candidate in roles),
    )
