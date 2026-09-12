"""Pure, deterministic primitives for the STEP-0015A Defense forensic audit.

The functions in this module are analytical diagnostics.  They do not mutate the
frozen V1 Defense score or use awards/postseason evidence as scoring inputs.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

DEFENSE_AUDIT_METHODOLOGY_VERSION = "goatlab-v1-defense-forensic-audit-v1"
DEFENSE_V2_CANDIDATE_VERSION = "goatlab-v1-defense-v2"


class PresenceConfidence(StrEnum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    LIMITED = "LIMITED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


@dataclass(frozen=True)
class PresenceEstimate:
    raw_difference: float | None
    adjusted_difference: float | None
    standard_error: float | None
    lower_95: float | None
    upper_95: float | None
    games_with: int
    games_without: int
    effective_sample_size: float
    reliability: float
    confidence: PresenceConfidence


def finite(value: float | int | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def broad_role(position: str | None) -> str | None:
    """Map source position text to a conservative broad role.

    Ambiguous hybrid positions remain deterministic, but blank and unrecognized
    values stay unavailable rather than being inferred from height or name.
    """
    if position is None or not position.strip():
        return None
    normalized = position.strip().upper()
    mapping = {
        "GUARD": "GUARD",
        "FORWARD-GUARD": "WING",
        "GUARD-FORWARD": "WING",
        "FORWARD": "FORWARD",
        "FORWARD-CENTER": "BIG",
        "CENTER-FORWARD": "BIG",
        "CENTER": "BIG",
    }
    return mapping.get(normalized)


def opponent_adjusted_residual(
    *,
    expected_opponent_points: float,
    actual_opponent_points: float,
    home_adjustment: float = 0.0,
) -> float:
    """Return positive points prevented relative to opponent/context expectation."""
    values = (expected_opponent_points, actual_opponent_points, home_adjustment)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("presence residual inputs must be finite")
    return expected_opponent_points + home_adjustment - actual_opponent_points


def defensive_presence_estimate(
    with_player: Sequence[float],
    without_player: Sequence[float],
    *,
    minimum_with: int = 10,
    minimum_without: int = 5,
    prior_effective_games: float = 20.0,
) -> PresenceEstimate:
    """Estimate a stabilized game-level defensive presence contrast.

    Inputs are positive opponent-adjusted points-prevented residuals.  The
    stabilized estimate is the with-player minus without-player difference.
    Reliability depends on harmonic/effective sample size, so merely missing
    more games cannot magnify the estimate.  Insufficient samples remain NULL.
    """
    if minimum_with < 1 or minimum_without < 1 or prior_effective_games <= 0.0:
        raise ValueError("invalid presence-estimation configuration")
    left = [float(value) for value in with_player if math.isfinite(float(value))]
    right = [float(value) for value in without_player if math.isfinite(float(value))]
    n_with, n_without = len(left), len(right)
    effective = n_with * n_without / (n_with + n_without) if n_with + n_without else 0.0
    if n_with < minimum_with or n_without < minimum_without:
        return PresenceEstimate(
            None,
            None,
            None,
            None,
            None,
            n_with,
            n_without,
            effective,
            0.0,
            PresenceConfidence.INSUFFICIENT_SAMPLE,
        )
    raw = statistics.fmean(left) - statistics.fmean(right)
    left_var = statistics.variance(left) if n_with > 1 else 0.0
    right_var = statistics.variance(right) if n_without > 1 else 0.0
    standard_error = math.sqrt(left_var / n_with + right_var / n_without)
    reliability = effective / (effective + prior_effective_games)
    adjusted = raw * reliability
    interval = 1.96 * standard_error
    confidence = (
        PresenceConfidence.STRONG
        if effective >= 20.0 and n_without >= 20
        else PresenceConfidence.MODERATE
        if effective >= 10.0 and n_without >= 10
        else PresenceConfidence.LIMITED
    )
    return PresenceEstimate(
        raw,
        adjusted,
        standard_error,
        raw - interval,
        raw + interval,
        n_with,
        n_without,
        effective,
        reliability,
        confidence,
    )


def weighted_available(
    values: Mapping[str, float | None],
    weights: Mapping[str, float],
    *,
    required: Sequence[str] = (),
) -> tuple[float | None, float]:
    """Explicitly renormalize observed evidence while reporting weight coverage."""
    if set(values) != set(weights):
        raise ValueError("values and weights must have identical keys")
    if any(weight < 0.0 for weight in weights.values()) or sum(weights.values()) <= 0.0:
        raise ValueError("weights must be non-negative with positive sum")
    if any(finite(values[name]) is None for name in required):
        return None, 0.0
    observed: dict[str, float] = {}
    for name, source_value in values.items():
        number = finite(source_value)
        if number is not None and weights[name] > 0.0:
            observed[name] = number
    if not observed:
        return None, 0.0
    observed_weight = sum(weights[name] for name in observed)
    value = sum(observed[name] * weights[name] for name in observed) / observed_weight
    return value, observed_weight / sum(weights.values())


def current_action_context(
    rebound_percentile: float | None,
    steal_percentile: float | None,
    block_percentile: float | None,
) -> tuple[float | None, float]:
    """Recreate the V1 total-rebound/steal/block action bundle exactly."""
    return weighted_available(
        {"rebounds": rebound_percentile, "steals": steal_percentile, "blocks": block_percentile},
        {"rebounds": 0.50, "steals": 0.25, "blocks": 0.25},
    )


def role_aware_action_context(
    rebound_evidence: float | None,
    steal_evidence: float | None,
    block_evidence: float | None,
) -> tuple[float | None, float]:
    """Combine role-conditioned evidence without equating role-specific ceilings."""
    return weighted_available(
        {
            "rebounding": rebound_evidence,
            "disruption_steal": steal_evidence,
            "rim_block": block_evidence,
        },
        {"rebounding": 0.40, "disruption_steal": 0.30, "rim_block": 0.30},
    )


def defense_candidate(
    *,
    team_suppression: float | None,
    action_context: float | None,
    presence_impact: float | None = None,
    weights: tuple[float, float, float] = (0.30, 0.30, 0.40),
) -> tuple[float | None, float]:
    """Triangulate team, action, and presence channels with explicit coverage.

    The tuple order is team, action, presence.  Team context is required because
    a score with actions alone would contradict the constitutional construct.
    """
    if len(weights) != 3:
        raise ValueError("expected team, action, and presence weights")
    return weighted_available(
        {
            "team_suppression": team_suppression,
            "action_context": action_context,
            "presence_impact": presence_impact,
        },
        dict(zip(("team_suppression", "action_context", "presence_impact"), weights, strict=True)),
        required=("team_suppression",),
    )
