"""Deterministic career trajectory, peak-window, and longevity primitives."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Any

CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
NORMALIZATION_VERSION = "era-normalized-player-season-v1"
NORMALIZATION_FINGERPRINT = "a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852"
CAREER_METHODOLOGY_VERSION = "career-trajectory-peak-longevity-v1"
REGISTRY_VERSION = 1
WINDOW_SIZES = (1, 3, 5)
ELITE_THRESHOLDS = (0.80, 0.90, 0.95, 0.99)
PERCENTILE_BASELINES = (0.50, 0.80, 0.90)
NORMALIZATION_METHODS = ("STANDARD_Z", "ROBUST_Z", "PERCENTILE", "RELATIVE_INDEX")
CORE_CANDIDATE_METRICS = ("ppg", "rpg", "apg", "spg", "bpg", "ts_pct")


class CoverageStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_NO_APPEARANCE = "UNAVAILABLE_NO_APPEARANCE"
    UNAVAILABLE_NO_QUALIFIED_VALUES = "UNAVAILABLE_NO_QUALIFIED_VALUES"
    INSUFFICIENT_CONTIGUOUS_COVERAGE = "INSUFFICIENT_CONTIGUOUS_COVERAGE"
    INSUFFICIENT_QUALIFIED_SEASONS = "INSUFFICIENT_QUALIFIED_SEASONS"


class PeakVariant(StrEnum):
    QUALITY = "QUALITY"
    AVAILABILITY_ADJUSTED = "AVAILABILITY_ADJUSTED"


@dataclass(frozen=True)
class SeasonValue:
    season_id: int
    value: float
    games_played: int
    opportunity_ratio: float


@dataclass(frozen=True)
class PeakWindow:
    window_size: int
    variant: PeakVariant
    coverage_status: CoverageStatus
    start_season: int | None
    end_season: int | None
    seasons_expected: int
    seasons_observed: int
    seasons_qualified: int
    mean_value: float | None
    adjusted_mean_value: float | None
    median_value: float | None
    minimum_value: float | None
    maximum_value: float | None
    total_games: int
    mean_opportunity_ratio: float | None
    minimum_opportunity_ratio: float | None


@dataclass(frozen=True)
class PrimeRun:
    threshold: float
    season_count: int
    career_proportion: float | None
    longest_run: int
    start_season: int | None
    end_season: int | None
    first_season: int | None
    last_season: int | None
    mean_value_during_run: float | None
    minimum_value_during_run: float | None


@dataclass(frozen=True)
class CandidateEvidence:
    player_id: str
    qualified_regular_seasons: int
    core_metrics_at_90: int
    core_metrics_at_95: int


def safe_mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def population_std(values: Sequence[float]) -> float | None:
    return statistics.pstdev(values) if values else None


def opportunity_adjusted_value(
    value: float,
    opportunity_ratio: float,
    normalization_method: str,
) -> float:
    """Shrink toward the normalization-specific league baseline."""
    ratio = min(max(float(opportunity_ratio), 0.0), 1.0)
    baseline = {
        "STANDARD_Z": 0.0,
        "ROBUST_Z": 0.0,
        "PERCENTILE": 0.5,
        "RELATIVE_INDEX": 100.0,
    }.get(normalization_method)
    if baseline is None:
        raise ValueError(f"unsupported normalization method: {normalization_method}")
    return baseline + (float(value) - baseline) * ratio


def career_sequence(
    first_season: int,
    last_season: int,
    appeared: set[int],
) -> list[dict[str, Any]]:
    if last_season < first_season:
        raise ValueError("career end precedes career start")
    appearance_number = 0
    output: list[dict[str, Any]] = []
    for index, season_id in enumerate(range(first_season, last_season + 1), start=1):
        did_appear = season_id in appeared
        if did_appear:
            appearance_number += 1
        output.append(
            {
                "season_id": season_id,
                "season_number": index,
                "appeared": did_appear,
                "appearance_number": appearance_number if did_appear else None,
            }
        )
    return output


def contiguous_windows(
    observations: Sequence[SeasonValue],
    window_size: int,
) -> list[tuple[SeasonValue, ...]]:
    if window_size <= 0:
        raise ValueError("window size must be positive")
    ordered = sorted(observations, key=lambda item: item.season_id)
    windows: list[tuple[SeasonValue, ...]] = []
    for start in range(0, len(ordered) - window_size + 1):
        candidate = tuple(ordered[start : start + window_size])
        if all(right.season_id == left.season_id + 1 for left, right in pairwise(candidate)):
            windows.append(candidate)
    return windows


def _window_record(
    window: Sequence[SeasonValue],
    *,
    window_size: int,
    variant: PeakVariant,
    normalization_method: str,
) -> PeakWindow:
    values = [item.value for item in window]
    adjusted = [
        opportunity_adjusted_value(item.value, item.opportunity_ratio, normalization_method)
        for item in window
    ]
    ratios = [item.opportunity_ratio for item in window]
    return PeakWindow(
        window_size=window_size,
        variant=variant,
        coverage_status=CoverageStatus.AVAILABLE,
        start_season=window[0].season_id,
        end_season=window[-1].season_id,
        seasons_expected=window_size,
        seasons_observed=len(window),
        seasons_qualified=len(window),
        mean_value=safe_mean(values),
        adjusted_mean_value=safe_mean(adjusted),
        median_value=statistics.median(values),
        minimum_value=min(values),
        maximum_value=max(values),
        total_games=sum(item.games_played for item in window),
        mean_opportunity_ratio=safe_mean(ratios),
        minimum_opportunity_ratio=min(ratios),
    )


def best_peak_window(
    observations: Sequence[SeasonValue],
    *,
    window_size: int,
    variant: PeakVariant,
    normalization_method: str,
) -> PeakWindow:
    windows = contiguous_windows(observations, window_size)
    if not windows:
        status = (
            CoverageStatus.UNAVAILABLE_NO_QUALIFIED_VALUES
            if not observations
            else CoverageStatus.INSUFFICIENT_CONTIGUOUS_COVERAGE
        )
        return PeakWindow(
            window_size,
            variant,
            status,
            None,
            None,
            window_size,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            0,
            None,
            None,
        )

    def key(window: tuple[SeasonValue, ...]) -> tuple[float, float, int]:
        quality = statistics.fmean(item.value for item in window)
        adjusted = statistics.fmean(
            opportunity_adjusted_value(
                item.value, item.opportunity_ratio, normalization_method
            )
            for item in window
        )
        primary = quality if variant is PeakVariant.QUALITY else adjusted
        return primary, quality, -window[0].season_id

    selected = max(windows, key=key)
    return _window_record(
        selected,
        window_size=window_size,
        variant=variant,
        normalization_method=normalization_method,
    )


def best_non_contiguous(
    observations: Sequence[SeasonValue],
    count: int,
    *,
    normalization_method: str,
) -> dict[str, Any]:
    if count <= 0:
        raise ValueError("count must be positive")
    if len(observations) < count:
        return {
            "coverage_status": CoverageStatus.INSUFFICIENT_QUALIFIED_SEASONS.value,
            "season_count": count,
            "seasons": [],
            "values": [],
            "mean_value": None,
            "adjusted_mean_value": None,
        }
    selected = sorted(observations, key=lambda item: (-item.value, item.season_id))[:count]
    return {
        "coverage_status": CoverageStatus.AVAILABLE.value,
        "season_count": count,
        "seasons": [item.season_id for item in selected],
        "values": [item.value for item in selected],
        "mean_value": statistics.fmean(item.value for item in selected),
        "adjusted_mean_value": statistics.fmean(
            opportunity_adjusted_value(
                item.value, item.opportunity_ratio, normalization_method
            )
            for item in selected
        ),
    }


def prime_run(
    observations: Sequence[SeasonValue],
    threshold: float,
) -> PrimeRun:
    ordered = sorted(observations, key=lambda item: item.season_id)
    above = [item for item in ordered if item.value >= threshold]
    best: list[SeasonValue] = []
    current: list[SeasonValue] = []
    prior_season: int | None = None
    for item in ordered:
        if item.value < threshold:
            current = []
            prior_season = item.season_id
            continue
        if prior_season is None or item.season_id != prior_season + 1:
            current = []
        current.append(item)
        prior_season = item.season_id
        if len(current) > len(best) or (
            len(current) == len(best)
            and current
            and (not best or current[0].season_id < best[0].season_id)
        ):
            best = list(current)
    return PrimeRun(
        threshold=threshold,
        season_count=len(above),
        career_proportion=(len(above) / len(ordered)) if ordered else None,
        longest_run=len(best),
        start_season=best[0].season_id if best else None,
        end_season=best[-1].season_id if best else None,
        first_season=above[0].season_id if above else None,
        last_season=above[-1].season_id if above else None,
        mean_value_during_run=safe_mean([item.value for item in best]),
        minimum_value_during_run=min((item.value for item in best), default=None),
    )


def cumulative_positive_z(observations: Sequence[SeasonValue]) -> tuple[float, float]:
    positive = [max(item.value, 0.0) for item in observations]
    weighted = [
        max(item.value, 0.0) * min(max(item.opportunity_ratio, 0.0), 1.0)
        for item in observations
    ]
    return sum(positive), sum(weighted)


def area_above_percentile(
    observations: Sequence[SeasonValue],
    baseline: float,
) -> tuple[float, float]:
    area = [max(item.value - baseline, 0.0) for item in observations]
    weighted = [
        max(item.value - baseline, 0.0) * min(max(item.opportunity_ratio, 0.0), 1.0)
        for item in observations
    ]
    return sum(area), sum(weighted)


def age_on_season_reference(birth_date: date | None, season_id: int) -> float | None:
    """Age on February 1 of the season's ending calendar year."""
    if birth_date is None:
        return None
    reference = date(season_id + 1, 2, 1)
    days = (reference - birth_date).days
    if days <= 0:
        return None
    return days / 365.2425


def candidate_universe_flags(evidence: CandidateEvidence) -> dict[str, bool]:
    participation_3 = evidence.qualified_regular_seasons >= 3
    participation_5 = evidence.qualified_regular_seasons >= 5
    participation_8 = evidence.qualified_regular_seasons >= 8
    participation_10 = evidence.qualified_regular_seasons >= 10
    elite_90 = evidence.core_metrics_at_90 >= 1
    elite_95 = evidence.core_metrics_at_95 >= 1
    multi_2_90 = evidence.core_metrics_at_90 >= 2
    multi_3_90 = evidence.core_metrics_at_90 >= 3
    multi_2_95 = evidence.core_metrics_at_95 >= 2
    return {
        "participation_q3": participation_3,
        "participation_q5": participation_5,
        "participation_q8": participation_8,
        "participation_q10": participation_10,
        "elite_any_core_p90": elite_90,
        "elite_any_core_p95": elite_95,
        "multi_core_2_p90": multi_2_90,
        "multi_core_3_p90": multi_3_90,
        "multi_core_2_p95": multi_2_95,
        "union_q3_or_p95": participation_3 or elite_95,
        "union_q5_or_p90_recommended": participation_5 or elite_90,
        "union_q8_or_p90": participation_8 or elite_90,
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint_partitions(partitions: Sequence[Mapping[str, Any]]) -> str:
    stable = [
        {
            "path": str(item["path"]),
            "rows": int(item["rows"]),
            "columns": int(item["columns"]),
            "size_bytes": int(item["size_bytes"]),
            "sha256": str(item["sha256"]),
        }
        for item in sorted(partitions, key=lambda item: str(item["path"]))
    ]
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def player_bucket(player_id: str, bucket_count: int = 32) -> int:
    if bucket_count <= 0:
        raise ValueError("bucket count must be positive")
    return int(hashlib.sha256(player_id.encode()).hexdigest()[:8], 16) % bucket_count


def career_feature_registry() -> dict[str, Any]:
    definitions = [
        {
            "feature_name": "career_distribution_summary",
            "category": "METRIC_CAREER_SUMMARY",
            "formula": "count, mean, median, min, max, population std over qualified values",
            "window_definition": None,
            "threshold": None,
            "opportunity_weighting": "none",
        },
        {
            "feature_name": "best_non_contiguous_3_or_5",
            "category": "NON_CONTIGUOUS_BEST_SEASONS",
            "formula": "mean of top N qualified season values",
            "window_definition": "best N values; seasons need not be consecutive",
            "threshold": None,
            "opportunity_weighting": "quality and league-baseline shrinkage variants",
        },
        {
            "feature_name": "contiguous_peak_1_3_5",
            "category": "PEAK_WINDOW",
            "formula": "best mean across complete consecutive N-season windows",
            "window_definition": "all N consecutive NBA seasons observed, qualified, and available",
            "threshold": None,
            "opportunity_weighting": "QUALITY and AVAILABILITY_ADJUSTED retained separately",
        },
        {
            "feature_name": "elite_season_count_and_run",
            "category": "PRIME_AND_LONGEVITY",
            "formula": "count/proportion and longest consecutive percentile run",
            "window_definition": "missed or below-threshold season breaks run",
            "threshold": list(ELITE_THRESHOLDS),
            "opportunity_weighting": "none",
        },
        {
            "feature_name": "cumulative_positive_z",
            "category": "CUMULATIVE_DOMINANCE",
            "formula": "sum(max(standard_z, 0))",
            "window_definition": "qualified available career seasons",
            "threshold": 0.0,
            "opportunity_weighting": "unweighted and games/opportunity weighted",
        },
        {
            "feature_name": "area_above_percentile_baseline",
            "category": "CUMULATIVE_DOMINANCE",
            "formula": "sum(max(percentile - baseline, 0))",
            "window_definition": "qualified available career seasons",
            "threshold": list(PERCENTILE_BASELINES),
            "opportunity_weighting": "unweighted and games/opportunity weighted",
        },
        {
            "feature_name": "late_career_elite_p80",
            "category": "LONGEVITY",
            "formula": "count of >=80th percentile seasons among final five appearances",
            "window_definition": "final five observed seasons of the season-type career",
            "threshold": 0.80,
            "opportunity_weighting": "none",
        },
    ]
    return {
        "registry_version": REGISTRY_VERSION,
        "career_methodology_version": CAREER_METHODOLOGY_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "normalization_fingerprint": NORMALIZATION_FINGERPRINT,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "comparison_scope": "each player, metric, normalization method, and season type separately",
        "regular_playoff_policy": "never combined",
        "missingness_policy": "unavailable remains NULL with explicit coverage status",
        "age_policy": "age on February 1 of season end; only authoritative birth dates",
        "active_policy": (
            "ACTIVE_TO_CUTOFF for 2025-26 Regular Season appearances; "
            "SOURCE_CONFIRMED_COMPLETE only from inactive legacy evidence; otherwise INDETERMINATE"
        ),
        "definitions": definitions,
        "normalization_methods": list(NORMALIZATION_METHODS),
        "window_sizes": list(WINDOW_SIZES),
        "elite_thresholds": list(ELITE_THRESHOLDS),
        "percentile_area_baselines": list(PERCENTILE_BASELINES),
        "known_limitations": [
            "Qualification is inherited from STEP-0007 and is not an uncertainty model.",
            "Availability adjustment shrinks toward the method-specific league baseline.",
            "Age features are unavailable when the audited identity snapshot lacks birth date.",
            "No primitive combines unrelated basketball metrics or defines greatness.",
        ],
    }
