"""Constitutional primitives for the seven GOATLab V1 dimension scores.

This module contains normative scoring mechanics.  It never reads source data,
never mutates Silver, and never combines the seven dimensions into an Overall
rating.  The pipeline supplies already canonical, era-normalized evidence.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

DIMENSION_SCORE_METHODOLOGY_VERSION = "goatlab-v1-dimension-scores-v1"
DIMENSION_SCORE_RANDOM_SEED = 140014


class Dimension(StrEnum):
    PEAK = "PEAK"
    LONGEVITY = "LONGEVITY"
    OFFENSE = "OFFENSE"
    DEFENSE = "DEFENSE"
    PLAYOFFS = "PLAYOFFS"
    ACCOLADES = "ACCOLADES"
    WINNING = "WINNING"


class EvidenceConfidence(StrEnum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


class ScoreCoverage(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_QUERIED = "NOT_QUERIED"


@dataclass(frozen=True)
class WeightedEvidence:
    value: float | None
    available: int
    expected: int
    weight_coverage: float


@dataclass(frozen=True)
class PeakWindow:
    value: float | None
    start_season: int | None
    end_season: int | None
    seasons: int


@dataclass(frozen=True)
class LongevityEvidence:
    breadth: int
    capped_area: float
    longest_run: int
    first_elite_season: int | None
    last_elite_season: int | None


def finite(value: float | int | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def weighted_observed(
    values: Mapping[str, float | None],
    weights: Mapping[str, float],
    *,
    required: Sequence[str] = (),
) -> WeightedEvidence:
    """Combine observed evidence without converting a missing value to zero.

    Available weights are explicitly renormalized.  Callers retain coverage so
    that the evidence bundle is never silent.  Required components block the
    result when absent.
    """
    if set(values) != set(weights):
        raise ValueError("values and weights must have identical keys")
    if any(weight < 0.0 for weight in weights.values()) or sum(weights.values()) <= 0.0:
        raise ValueError("weights must be non-negative with a positive sum")
    if any(finite(values.get(name)) is None for name in required):
        return WeightedEvidence(None, 0, len(values), 0.0)
    observed = {
        name: number
        for name, value in values.items()
        if (number := finite(value)) is not None and weights[name] > 0.0
    }
    available_weight = sum(weights[name] for name in observed)
    total_weight = sum(weights.values())
    if not observed or available_weight <= 0.0:
        return WeightedEvidence(None, 0, len(values), 0.0)
    result = sum(observed[name] * weights[name] for name in observed) / available_weight
    return WeightedEvidence(result, len(observed), len(values), available_weight / total_weight)


def midrank_percentile_scores(
    values: Mapping[str, float | None], reference_players: set[str]
) -> dict[str, float | None]:
    """Map values onto a 0--100 midrank ECDF scale without raw min-max compression."""
    reference = sorted(
        number
        for player_id, value in values.items()
        if player_id in reference_players and (number := finite(value)) is not None
    )
    result: dict[str, float | None] = dict.fromkeys(values)
    if not reference:
        return result
    denominator = max(len(reference) - 1, 1)
    for player_id, value in values.items():
        number = finite(value)
        if number is None:
            continue
        below = sum(item < number for item in reference)
        equal = sum(item == number for item in reference)
        midrank = below + (equal - 1) / 2.0
        score = 100.0 * midrank / denominator
        result[player_id] = min(100.0, max(0.0, score))
    return result


def joint_scoring_value(
    volume: float | None,
    efficiency: float | None,
    *,
    volume_weight: float = 0.65,
) -> WeightedEvidence:
    """Combine volume and efficiency before scoring enters Offense."""
    if not 0.5 <= volume_weight <= 1.0:
        raise ValueError("volume_weight must be between 0.5 and 1")
    return weighted_observed(
        {"volume": volume, "efficiency": efficiency},
        {"volume": volume_weight, "efficiency": 1.0 - volume_weight},
        required=("volume",),
    )


def stronger_secondary_value(
    primary_axis: float | None,
    secondary_axis: float | None,
    *,
    stronger_weight: float = 0.65,
) -> WeightedEvidence:
    """Reward either elite pathway while preserving meaningful second-axis credit."""
    if not 0.5 < stronger_weight < 1.0:
        raise ValueError("stronger_weight must exceed one half and remain below one")
    left = finite(primary_axis)
    right = finite(secondary_axis)
    if left is None and right is None:
        return WeightedEvidence(None, 0, 2, 0.0)
    if left is None:
        return WeightedEvidence(right, 1, 2, 1.0 - stronger_weight)
    if right is None:
        return WeightedEvidence(left, 1, 2, stronger_weight)
    stronger = max(left, right)
    weaker = min(left, right)
    return WeightedEvidence(
        stronger_weight * stronger + (1.0 - stronger_weight) * weaker,
        2,
        2,
        1.0,
    )


def best_contiguous_window(season_values: Mapping[int, float | None], window: int) -> PeakWindow:
    """Return the best complete consecutive-season window; gaps invalidate it."""
    if window < 1:
        raise ValueError("window must be positive")
    observed = sorted(season_values)
    best: tuple[float, int, int] | None = None
    for start in observed:
        seasons = list(range(start, start + window))
        values = [finite(season_values.get(season)) for season in seasons]
        if any(value is None for value in values):
            continue
        mean = statistics.fmean(value for value in values if value is not None)
        candidate = (mean, -start, start + window - 1)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return PeakWindow(None, None, None, window)
    return PeakWindow(best[0], -best[1], best[2], window)


def peak_hybrid(three_year: float | None, apex: float | None, weight_three: float) -> float | None:
    """Constitutional Peak: contiguous three-year primary, apex secondary."""
    if not 0.5 < weight_three < 1.0:
        raise ValueError("three-year Peak must have majority weight")
    left = finite(three_year)
    right = finite(apex)
    if left is None or right is None:
        return None
    return weight_three * left + (1.0 - weight_three) * right


def longevity_evidence(
    season_percentiles: Mapping[int, float | None],
    *,
    threshold: float,
    cap: float,
) -> LongevityEvidence:
    """Threshold and cap season credit so Longevity measures duration, not apex height."""
    if not 0.0 <= threshold < cap <= 1.0:
        raise ValueError("expected 0 <= threshold < cap <= 1")
    elite: list[int] = []
    area = 0.0
    for season in sorted(season_percentiles):
        value = finite(season_percentiles[season])
        if value is None or value < threshold:
            continue
        elite.append(season)
        area += min(1.0, (value - threshold) / (cap - threshold))
    longest = current = 0
    previous: int | None = None
    for season in elite:
        current = current + 1 if previous is not None and season == previous + 1 else 1
        longest = max(longest, current)
        previous = season
    return LongevityEvidence(
        breadth=len(elite),
        capped_area=area,
        longest_run=longest,
        first_elite_season=elite[0] if elite else None,
        last_elite_season=elite[-1] if elite else None,
    )


def playoff_hybrid(
    absolute: float | None,
    resilience: float | None,
    repeated: float | None,
    *,
    weights: tuple[float, float, float] = (0.65, 0.20, 0.15),
) -> WeightedEvidence:
    """Combine playoff evidence while requiring absolute quality as the primary signal."""
    if len(weights) != 3 or weights[0] <= sum(weights[1:]):
        raise ValueError("absolute postseason excellence must dominate")
    return weighted_observed(
        {"absolute": absolute, "resilience": resilience, "repeated": repeated},
        dict(zip(("absolute", "resilience", "repeated"), weights, strict=True)),
        required=("absolute",),
    )


def recognition_bundle(values: Sequence[float], *, cap: float = 1.15) -> float:
    """Bundle same-season recognition: strongest signal plus bounded distinct support."""
    observed = sorted((max(0.0, float(value)) for value in values), reverse=True)
    if not observed:
        return 0.0
    secondary = 0.25 * sum(observed[1:])
    return min(cap, observed[0] + secondary)


def winning_outcome_tier(
    *,
    champion_finals_participant: bool,
    finalist_participant: bool,
    playoff_participant: bool,
    series_won: int | None,
) -> tuple[str, float]:
    """Return one mutually exclusive highest postseason outcome tier."""
    if champion_finals_participant:
        return "CHAMPION_FINALS_PARTICIPANT", 1.0
    if finalist_participant:
        return "FINALIST_PARTICIPANT", 0.75
    if playoff_participant and series_won is not None and series_won >= 2:
        return "MULTI_SERIES_ADVANCEMENT", 0.50
    if playoff_participant and series_won is not None and series_won == 1:
        return "SERIES_ADVANCEMENT", 0.35
    if playoff_participant:
        return "PLAYOFF_PARTICIPANT", 0.20
    return "NO_POSTSEASON_PARTICIPATION", 0.0


def confidence_from_coverage(
    available_weight: float,
    *,
    relevant_seasons: int,
    strong_seasons: int = 5,
    moderate_seasons: int = 3,
) -> EvidenceConfidence:
    """Describe evidence only; callers must never multiply confidence into quality."""
    if available_weight <= 0.0 or relevant_seasons <= 0:
        return EvidenceConfidence.UNAVAILABLE
    if available_weight >= 0.99 and relevant_seasons >= strong_seasons:
        return EvidenceConfidence.STRONG
    if available_weight >= 0.66 and relevant_seasons >= moderate_seasons:
        return EvidenceConfidence.MODERATE
    return EvidenceConfidence.LIMITED
