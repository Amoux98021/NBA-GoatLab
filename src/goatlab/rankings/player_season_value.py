"""Pure primitives for the STEP-0015D player-season value audit."""

from __future__ import annotations

import math
from dataclasses import dataclass

from goatlab.rankings.dimension_scores import stronger_secondary_value

PLAYER_SEASON_VALUE_AUDIT_VERSION = "goatlab-v1-player-season-value-audit-v1"
PLAYER_SEASON_VALUE_RESEARCH_VERSION = "goatlab-v1-player-season-value-v2-research"
PEAK_COUNTERFACTUAL_VERSION = "goatlab-v1-peak-player-season-value-counterfactual-v1"
LONGEVITY_COUNTERFACTUAL_VERSION = "goatlab-v1-longevity-player-season-value-counterfactual-v1"
OVERALL_COUNTERFACTUAL_VERSION = "goatlab-v1-overall-player-season-value-counterfactual-v1"


@dataclass(frozen=True)
class ValueEstimate:
    value: float | None
    confidence: str
    reason_codes: tuple[str, ...]
    team_effective_weight: float
    offense_effective_weight: float
    defense_effective_weight: float


def finite(value: float | int | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def offensive_axis(
    scoring: float | None,
    creation: float | None,
    *,
    architecture: str,
) -> float | None:
    """Build a season-level offensive axis from already-era-relative evidence."""
    left, right = finite(scoring), finite(creation)
    if left is None:
        return None
    if architecture == "O1_STRONGER_65_35":
        return stronger_secondary_value(left, right, stronger_weight=0.65).value
    if right is None:
        return None
    if architecture == "O2_DIRECT_70_30":
        return 0.70 * left + 0.30 * right
    if architecture == "O3_MULTIPATH_60_40":
        return stronger_secondary_value(left, right, stronger_weight=0.60).value
    raise ValueError(f"unknown offense architecture: {architecture}")


def defensive_axis(
    actions: float | None,
    team_context: float | None,
    presence: float | None,
    *,
    architecture: str,
    presence_reliability: float = 0.0,
) -> tuple[float | None, float, tuple[str, ...]]:
    """Combine defensive evidence without claiming unavailable evidence is zero."""
    action, team, observed = finite(actions), finite(team_context), finite(presence)
    if action is None:
        return None, 0.0, ("DEFENSIVE_ACTION_EVIDENCE_UNAVAILABLE",)
    if architecture == "D1_ACTIONS_ONLY":
        return action, 0.0, ()
    if team is None:
        return None, 0.0, ("TEAM_CONTEXT_UNAVAILABLE",)
    if architecture == "D2_ACTIONS_TEAM_75_25":
        return 0.75 * action + 0.25 * team, 0.25, ()
    if architecture == "D3_FULL_50_10_40":
        if observed is None:
            return None, 0.0, ("PRESENCE_UNAVAILABLE",)
        return 0.50 * action + 0.10 * team + 0.40 * observed, 0.10, ()
    if architecture == "D4_RELIABILITY_55_10_35":
        reliability = min(1.0, max(0.0, float(presence_reliability)))
        if observed is None or reliability <= 0.0:
            return 0.90 * action + 0.10 * team, 0.10, ("PRESENCE_NOT_OBSERVED",)
        # Reliability controls how much of the predeclared Presence channel is observed.
        # The unused share remains on the individual action channel, never on team context.
        presence_weight = 0.35 * reliability
        action_weight = 0.90 - presence_weight
        return (
            action_weight * action + 0.10 * team + presence_weight * observed,
            0.10,
            ("PRESENCE_RELIABILITY_BLEND",) if reliability < 1.0 else (),
        )
    raise ValueError(f"unknown defense architecture: {architecture}")


def combine_player_value(
    offense: float | None,
    defense: float | None,
    *,
    architecture: str,
    defense_team_weight: float,
) -> ValueEstimate:
    """Combine individual season offense and defensive evidence transparently."""
    left, right = finite(offense), finite(defense)
    if left is None or right is None:
        reasons = []
        if left is None:
            reasons.append("OFFENSE_UNAVAILABLE")
        if right is None:
            reasons.append("DEFENSE_EVIDENCE_UNAVAILABLE")
        return ValueEstimate(None, "UNAVAILABLE", tuple(reasons), 0.0, 0.0, 0.0)
    if architecture == "M2_STRONGER_60_40":
        offense_weight, defense_weight = (0.60, 0.40) if left >= right else (0.40, 0.60)
    elif architecture == "M3_OFFENSE_65_DEFENSE_35":
        offense_weight, defense_weight = 0.65, 0.35
    elif architecture == "M4_BOUNDED_STRONGER_55_45":
        offense_weight, defense_weight = (0.55, 0.45) if left >= right else (0.45, 0.55)
    else:
        raise ValueError(f"unknown player-value architecture: {architecture}")
    value = offense_weight * left + defense_weight * right
    team_weight = defense_weight * defense_team_weight
    confidence = "STRONG" if defense_team_weight <= 0.10 else "MODERATE"
    return ValueEstimate(value, confidence, (), team_weight, offense_weight, defense_weight)


def evidence_regime(
    *,
    ts_available: bool,
    creation_available: bool,
    rebound_available: bool,
    steals_blocks_available: bool,
    role_actions_available: bool,
    presence_available: bool,
) -> str:
    """Classify the row from observed coverage rather than a hard-coded season date."""
    if role_actions_available and presence_available and ts_available and creation_available:
        return "FULL_PORTABLE"
    if steals_blocks_available and ts_available and creation_available:
        return "EXPANDED_BOX_NO_PRESENCE"
    if rebound_available and creation_available:
        return "TRADITIONAL_BOX"
    return "EARLY_LIMITED"


def confidence_from_evidence(
    *,
    regime: str,
    presence_reliability: float,
    role_known: bool,
    games: int,
) -> tuple[str, tuple[str, ...]]:
    """Describe evidence strength without multiplying the quality estimate."""
    reasons: list[str] = []
    if regime != "FULL_PORTABLE":
        reasons.append(f"EVIDENCE_REGIME_{regime}")
    if not role_known:
        reasons.append("ROLE_METADATA_UNAVAILABLE")
    if presence_reliability < 1.0:
        reasons.append("PRESENCE_PARTIAL_OR_UNAVAILABLE")
    if games < 20:
        reasons.append("LIMITED_GAMES")
    if regime == "FULL_PORTABLE" and presence_reliability >= 0.75 and role_known and games >= 40:
        return "STRONG", tuple(reasons)
    if regime in {"FULL_PORTABLE", "EXPANDED_BOX_NO_PRESENCE"} and games >= 20:
        return "MODERATE", tuple(reasons)
    return "LIMITED", tuple(reasons)
