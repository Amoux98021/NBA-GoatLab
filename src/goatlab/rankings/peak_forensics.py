"""Pure primitives for the STEP-0015C Peak forensic audit.

The helpers reconstruct the frozen V1 season-quality chain and support
counterfactual masking without mutating any published dimension output.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from goatlab.rankings.dimension_scores import (
    PeakWindow,
    best_contiguous_window,
    joint_scoring_value,
    peak_hybrid,
    stronger_secondary_value,
    weighted_observed,
)

PEAK_AUDIT_METHODOLOGY_VERSION = "goatlab-v1-peak-forensic-audit-v1"
PEAK_V2_RESEARCH_VERSION = "goatlab-v1-peak-v2-research"
OVERALL_PEAK_V2_COUNTERFACTUAL_VERSION = "goatlab-v1-overall-peak-v2-counterfactual-v1"

PRIMITIVE_WEIGHTS = {
    "ppg": 0.65,
    "ts_pct": 0.35,
    "apg": 0.35,
    "team_suppression": 0.65,
    "rpg": 0.50,
    "spg": 0.25,
    "bpg": 0.25,
}


@dataclass(frozen=True)
class SeasonQuality:
    scoring: float | None
    offense: float | None
    actions: float | None
    defense: float | None
    quality: float | None
    scoring_coverage: float
    offense_coverage: float
    action_coverage: float
    defense_coverage: float
    quality_coverage: float
    effective_weights: dict[str, float]
    contributions: dict[str, float]


def finite(value: float | int | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _axis_weights(
    left: float | None, right: float | None, stronger: float = 0.65
) -> tuple[float, float]:
    """Return realized piecewise weights for a stronger/secondary combination."""
    first, second = finite(left), finite(right)
    if first is None and second is None:
        return 0.0, 0.0
    if first is None:
        return 0.0, 1.0
    if second is None:
        return 1.0, 0.0
    return (stronger, 1.0 - stronger) if first >= second else (1.0 - stronger, stronger)


def _available_weights(
    values: Mapping[str, float | None], weights: Mapping[str, float]
) -> dict[str, float]:
    observed = {
        name: finite(value)
        for name, value in values.items()
        if finite(value) is not None and weights[name] > 0.0
    }
    denominator = sum(weights[name] for name in observed)
    if denominator <= 0.0:
        return {name: 0.0 for name in values}
    return {name: weights[name] / denominator if name in observed else 0.0 for name in values}


def v1_season_quality(values: Mapping[str, float | None]) -> SeasonQuality:
    """Reconstruct the exact frozen V1 regular-season quality formula.

    Expected keys are PPG, TS, APG, RPG, SPG, BPG, and team suppression,
    each already expressed as an era-relative percentile in [0, 1].
    """
    scoring = joint_scoring_value(values.get("ppg"), values.get("ts_pct"), volume_weight=0.65)
    offense = stronger_secondary_value(scoring.value, values.get("apg"), stronger_weight=0.65)
    actions = weighted_observed(
        {name: values.get(name) for name in ("rpg", "spg", "bpg")},
        {"rpg": 0.50, "spg": 0.25, "bpg": 0.25},
    )
    defense = weighted_observed(
        {"team_suppression": values.get("team_suppression"), "actions": actions.value},
        {"team_suppression": 0.65, "actions": 0.35},
        required=("team_suppression",),
    )
    quality = stronger_secondary_value(offense.value, defense.value, stronger_weight=0.65)

    scoring_weights = _available_weights(
        {"ppg": values.get("ppg"), "ts_pct": values.get("ts_pct")},
        {"ppg": 0.65, "ts_pct": 0.35},
    )
    offense_scoring, offense_apg = _axis_weights(scoring.value, values.get("apg"))
    action_weights = _available_weights(
        {name: values.get(name) for name in ("rpg", "spg", "bpg")},
        {"rpg": 0.50, "spg": 0.25, "bpg": 0.25},
    )
    defense_weights = _available_weights(
        {"team_suppression": values.get("team_suppression"), "actions": actions.value},
        {"team_suppression": 0.65, "actions": 0.35},
    )
    quality_offense, quality_defense = _axis_weights(offense.value, defense.value)
    effective = {
        "ppg": quality_offense * offense_scoring * scoring_weights["ppg"],
        "ts_pct": quality_offense * offense_scoring * scoring_weights["ts_pct"],
        "apg": quality_offense * offense_apg,
        "team_suppression": quality_defense * defense_weights["team_suppression"],
        "rpg": quality_defense * defense_weights["actions"] * action_weights["rpg"],
        "spg": quality_defense * defense_weights["actions"] * action_weights["spg"],
        "bpg": quality_defense * defense_weights["actions"] * action_weights["bpg"],
    }
    contributions: dict[str, float] = {}
    for name, weight in effective.items():
        number = finite(values.get(name))
        if number is not None and weight > 0.0:
            contributions[name] = weight * number
    return SeasonQuality(
        scoring.value,
        offense.value,
        actions.value,
        defense.value,
        quality.value,
        scoring.weight_coverage,
        offense.weight_coverage,
        actions.weight_coverage,
        defense.weight_coverage,
        (offense.weight_coverage + defense.weight_coverage) / 2.0,
        effective,
        contributions,
    )


def individual_season_quality(
    offense: float | None,
    defensive_actions: float | None,
    *,
    architecture: str,
) -> float | None:
    """Research-only player-specific season-quality candidates."""
    left, right = finite(offense), finite(defensive_actions)
    if left is None or right is None:
        return None
    if architecture == "FIXED_60_40":
        return 0.60 * left + 0.40 * right
    if architecture == "MULTI_PATH_65_35":
        combined = stronger_secondary_value(left, right, stronger_weight=0.65)
        return combined.value
    raise ValueError(f"unknown Peak candidate architecture: {architecture}")


def player_peak(
    seasons: Mapping[int, float | None], three_year_weight: float = 0.70
) -> tuple[float | None, PeakWindow, float | None]:
    """Return raw Peak, best complete three-year window, and apex."""
    window = best_contiguous_window(seasons, 3)
    observed = [number for value in seasons.values() if (number := finite(value)) is not None]
    apex = max(observed) if observed else None
    return peak_hybrid(window.value, apex, three_year_weight), window, apex


def synthetic_window(values: Sequence[float | None]) -> dict[str, float | int | None]:
    """Evaluate a synthetic consecutive career with V1 window rules."""
    seasons = {2000 + index: value for index, value in enumerate(values)}
    raw, window, apex = player_peak(seasons)
    return {
        "raw_peak": raw,
        "three_year": window.value,
        "start_season": window.start_season,
        "end_season": window.end_season,
        "apex": apex,
    }


def correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(right) != len(left):
        return None
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((value - mean_left) ** 2 for value in left)
        * sum((value - mean_right) ** 2 for value in right)
    )
    return numerator / denominator if denominator > 0.0 else None
