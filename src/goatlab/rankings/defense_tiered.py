"""Deterministic Defense V2 tiered-measurement primitives.

The module measures observed defensive evidence forms.  It never predicts a
missing Presence value and never treats an unavailable defensive statistic as
zero.  Score linking is performed separately by the STEP-0015M audit.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

DefenseForm = Literal[
    "DEF_FULL",
    "DEF_ACTION_PRESENCE_NO_CONTEXT",
    "DEF_ACTION_PARTIAL_PRESENCE",
    "DEF_ACTION_NO_PRESENCE",
    "DEF_TRADITIONAL_PRESENCE",
    "DEF_TRADITIONAL",
    "DEF_REBOUND_ONLY",
    "DEF_CONTEXT_PRESENCE",
    "DEF_CONTEXT_ONLY",
    "DEF_UNAVAILABLE",
]

DEFENSE_V2_TIERED_VERSION = "goatlab-v1-defense-v2-tiered"
DEFENSE_AUDIT_VERSION = "goatlab-v1-defense-v2-tiered-promotion-audit-v1"


def defense_weights(team_weight: float) -> tuple[float, float, float]:
    """Return team/action/Presence weights, preserving Candidate-B's 3:4 ratio."""

    if not math.isfinite(team_weight) or not 0.0 <= team_weight < 1.0:
        raise ValueError("team weight must be finite and in [0, 1)")
    remainder = 1.0 - team_weight
    return team_weight, remainder * 3.0 / 7.0, remainder * 4.0 / 7.0


def observed_defense_score(
    *,
    team: float | None,
    action: float | None,
    presence: float | None,
    presence_reliability: float,
    team_weight: float = 0.10,
) -> tuple[float | None, float]:
    """Score only observed channels without reallocating missing-channel weight.

    The returned coverage is nominal weight observed.  Reliability scales the
    observed Presence contribution; the unearned Presence weight remains
    uncertainty and is not redistributed into team or action evidence.
    """

    if not 0.0 <= presence_reliability <= 1.0:
        raise ValueError("Presence reliability must be in [0, 1]")
    weights = defense_weights(team_weight)
    values = (team, action, presence)
    for value in values:
        if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
            raise ValueError("Defense evidence must be in [0, 1]")
    contributions: list[float] = []
    coverage = 0.0
    if team is not None:
        contributions.append(weights[0] * team)
        coverage += weights[0]
    if action is not None:
        contributions.append(weights[1] * action)
        coverage += weights[1]
    if presence is not None and presence_reliability > 0.0:
        contributions.append(weights[2] * presence_reliability * presence)
        coverage += weights[2] * presence_reliability
    return (sum(contributions), coverage) if contributions else (None, 0.0)


def classify_defense_form(
    *,
    team_available: bool,
    rebound_available: bool,
    stocks_available: bool,
    presence_available: bool,
    presence_reliability: float,
) -> DefenseForm:
    """Classify the factual Defense measurement form without player identity."""

    if not 0.0 <= presence_reliability <= 1.0:
        raise ValueError("Presence reliability must be in [0, 1]")
    full_actions = rebound_available and stocks_available
    if full_actions and presence_available and presence_reliability >= 1.0:
        return "DEF_FULL" if team_available else "DEF_ACTION_PRESENCE_NO_CONTEXT"
    if full_actions and presence_available:
        return "DEF_ACTION_PARTIAL_PRESENCE"
    if full_actions:
        return "DEF_ACTION_NO_PRESENCE"
    if rebound_available and presence_available:
        return "DEF_TRADITIONAL_PRESENCE" if team_available else "DEF_CONTEXT_PRESENCE"
    if rebound_available:
        return "DEF_TRADITIONAL" if team_available else "DEF_REBOUND_ONLY"
    if presence_available:
        return "DEF_CONTEXT_PRESENCE"
    if team_available:
        return "DEF_CONTEXT_ONLY"
    return "DEF_UNAVAILABLE"


def point_eligibility(metrics: Mapping[str, object]) -> tuple[bool, dict[str, bool]]:
    """Apply the predeclared STEP-0015M point-calibration gates."""

    point = metrics["point"]
    intervals = metrics["intervals"]
    roles = metrics["roles"]
    if not isinstance(point, Mapping) or not isinstance(intervals, Mapping):
        raise ValueError("invalid calibration metrics")
    interval_90 = intervals["90"]
    if not isinstance(interval_90, Mapping) or not isinstance(roles, Mapping):
        raise ValueError("invalid calibration metrics")
    role_biases = [
        abs(float(value["bias"]))
        for value in roles.values()
        if isinstance(value, Mapping) and int(value.get("n", 0)) >= 100
    ]
    gates = {
        "mae_lte_5": float(point["mae"]) <= 5.0,
        "spearman_gte_095": float(point["spearman"]) >= 0.95,
        "absolute_bias_lte_2": abs(float(point["bias"])) <= 2.0,
        "major_role_bias_lte_3": max(role_biases, default=999.0) <= 3.0,
        "gt_10_lte_015": float(point["gt_10"]) <= 0.15,
        "interval_90_calibrated": 0.87 <= float(interval_90["coverage"]) <= 0.93,
    }
    return all(gates.values()), gates


def career_defense_status(
    *,
    usable_seasons: int,
    official_seasons: int,
    point_eligible_seasons: int,
    career_pattern_passed: bool,
) -> str:
    """Return the dimension status; central estimates never override failed gates."""

    if usable_seasons <= 0:
        return "DEFENSE_UNAVAILABLE"
    if official_seasons == usable_seasons:
        return "OFFICIAL_DEFENSE_POINT"
    if point_eligible_seasons == usable_seasons and career_pattern_passed:
        return "PROVISIONAL_DEFENSE_POINT"
    return "DEFENSE_INTERVAL_ONLY"
