"""Coverage-aware league context and era-normalization primitives."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
METHODOLOGY_VERSION = "era-normalized-player-season-v1"
FEATURE_REGISTRY_VERSION = 1
ROBUST_Z_SCALE = 0.6744897501960817


class QualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class EligibilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    AVAILABLE_PLAYER_INPUT_NULL = "AVAILABLE_PLAYER_INPUT_NULL"
    UNAVAILABLE_COVERAGE = "UNAVAILABLE_COVERAGE"
    UNAVAILABLE_POSSESSIONS = "UNAVAILABLE_POSSESSIONS"
    UNAVAILABLE_NO_POPULATION = "UNAVAILABLE_NO_POPULATION"
    UNAVAILABLE_ZERO_VARIANCE = "UNAVAILABLE_ZERO_VARIANCE"
    UNAVAILABLE_ZERO_MAD = "UNAVAILABLE_ZERO_MAD"
    UNAVAILABLE_INVALID_REFERENCE = "UNAVAILABLE_INVALID_REFERENCE"
    UNAVAILABLE_METHOD = "UNAVAILABLE_METHOD"


class RateBasis(StrEnum):
    TOTAL = "TOTAL"
    PER_GAME = "PER_GAME"
    PER_36 = "PER_36"
    PER_75 = "PER_75"
    PERCENTAGE = "PERCENTAGE"


class NormalizationMethod(StrEnum):
    STANDARD_Z = "STANDARD_Z"
    ROBUST_Z = "ROBUST_Z"
    PERCENTILE = "PERCENTILE"
    RELATIVE_INDEX = "RELATIVE_INDEX"


@dataclass(frozen=True)
class Qualification:
    status: QualificationStatus
    reason: str
    games_threshold: int
    season_opportunity_games: int


@dataclass(frozen=True)
class Distribution:
    count: int
    mean: float | None
    median: float | None
    std: float | None
    mad: float | None
    q1: float | None
    q3: float | None
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    description: str
    rate_basis: RateBasis
    source_metrics: tuple[str, ...]
    required_coverage: tuple[str, ...]
    formula: str
    relative_index_supported: bool
    possession_required: bool = False
    known_start_season: int | None = None
    limitations: str = ""


FEATURE_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        "games_played",
        "Official distinct game appearances in the season/type.",
        RateBasis.TOTAL,
        ("games_played",),
        (),
        "games_played",
        True,
    ),
    FeatureDefinition(
        "minutes_total",
        "Qualified observed minutes across the season/type.",
        RateBasis.TOTAL,
        ("minutes_total",),
        ("minutes",),
        "sum(minutes)",
        True,
        known_start_season=1951,
    ),
    FeatureDefinition(
        "ppg",
        "Points per game.",
        RateBasis.PER_GAME,
        ("points_total", "games_played"),
        ("points",),
        "points_total / games_played",
        True,
    ),
    FeatureDefinition(
        "points_per_36",
        "Points per 36 observed minutes.",
        RateBasis.PER_36,
        ("points_total", "minutes_total"),
        ("points", "minutes"),
        "36 * points_total / minutes_total",
        True,
        known_start_season=1951,
    ),
    FeatureDefinition(
        "points_per_75",
        "Points per 75 official player possessions.",
        RateBasis.PER_75,
        ("points_total", "possessions"),
        ("points",),
        "75 * points_total / official_advanced_possessions",
        True,
        possession_required=True,
        known_start_season=1996,
        limitations="Available only when official Advanced/Totals possessions qualify.",
    ),
    FeatureDefinition(
        "rpg",
        "Rebounds per game.",
        RateBasis.PER_GAME,
        ("rebounds_total", "games_played"),
        ("rebounds",),
        "rebounds_total / games_played",
        True,
        known_start_season=1950,
    ),
    FeatureDefinition(
        "rebounds_per_36",
        "Rebounds per 36 observed minutes.",
        RateBasis.PER_36,
        ("rebounds_total", "minutes_total"),
        ("rebounds", "minutes"),
        "36 * rebounds_total / minutes_total",
        True,
        known_start_season=1951,
    ),
    FeatureDefinition(
        "apg",
        "Assists per game.",
        RateBasis.PER_GAME,
        ("assists_total", "games_played"),
        ("assists",),
        "assists_total / games_played",
        True,
    ),
    FeatureDefinition(
        "assists_per_36",
        "Assists per 36 observed minutes.",
        RateBasis.PER_36,
        ("assists_total", "minutes_total"),
        ("assists", "minutes"),
        "36 * assists_total / minutes_total",
        True,
        known_start_season=1951,
    ),
    FeatureDefinition(
        "spg",
        "Steals per game.",
        RateBasis.PER_GAME,
        ("steals_total", "games_played"),
        ("steals",),
        "steals_total / games_played",
        True,
        known_start_season=1973,
    ),
    FeatureDefinition(
        "bpg",
        "Blocks per game.",
        RateBasis.PER_GAME,
        ("blocks_total", "games_played"),
        ("blocks",),
        "blocks_total / games_played",
        True,
        known_start_season=1973,
    ),
    FeatureDefinition(
        "fg_pct",
        "Field goals made divided by field goals attempted.",
        RateBasis.PERCENTAGE,
        ("fgm_total", "fga_total"),
        ("fgm", "fga"),
        "fgm_total / fga_total",
        True,
    ),
    FeatureDefinition(
        "ft_pct",
        "Free throws made divided by free throws attempted.",
        RateBasis.PERCENTAGE,
        ("ftm_total", "fta_total"),
        ("ftm", "fta"),
        "ftm_total / fta_total",
        True,
    ),
    FeatureDefinition(
        "fg3_pct",
        "Three-point field goals made divided by attempts.",
        RateBasis.PERCENTAGE,
        ("fg3m_total", "fg3a_total"),
        ("fg3m", "fg3a"),
        "fg3m_total / fg3a_total",
        True,
        known_start_season=1979,
    ),
    FeatureDefinition(
        "efg_pct",
        "Effective field-goal percentage.",
        RateBasis.PERCENTAGE,
        ("fgm_total", "fg3m_total", "fga_total"),
        ("fgm", "fg3m", "fga"),
        "(fgm_total + 0.5 * fg3m_total) / fga_total",
        True,
        known_start_season=1979,
        limitations="Not fabricated for seasons before the three-point field goal existed.",
    ),
    FeatureDefinition(
        "ts_pct",
        "True shooting percentage using the consistent 0.44 free-throw factor.",
        RateBasis.PERCENTAGE,
        ("points_total", "fga_total", "fta_total"),
        ("points", "fga", "fta"),
        "points_total / (2 * (fga_total + 0.44 * fta_total))",
        True,
        limitations=(
            "The 0.44 factor is a documented estimate and is not possession reconstruction."
        ),
    ),
)

FEATURES_BY_NAME = {feature.name: feature for feature in FEATURE_DEFINITIONS}


def safe_ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator is None or float(denominator) <= 0:
        return None
    return float(numerator) / float(denominator)


def true_shooting_pct(
    points: int | float | None,
    field_goal_attempts: int | float | None,
    free_throw_attempts: int | float | None,
) -> float | None:
    if points is None or field_goal_attempts is None or free_throw_attempts is None:
        return None
    denominator = 2.0 * (float(field_goal_attempts) + 0.44 * float(free_throw_attempts))
    return safe_ratio(points, denominator)


def effective_fg_pct(
    field_goals_made: int | float | None,
    three_point_made: int | float | None,
    field_goal_attempts: int | float | None,
) -> float | None:
    if field_goals_made is None or three_point_made is None:
        return None
    return safe_ratio(float(field_goals_made) + 0.5 * float(three_point_made), field_goal_attempts)


def per_game(total: int | float | None, games: int | float | None) -> float | None:
    return safe_ratio(total, games)


def per_36(total: int | float | None, minutes: int | float | None) -> float | None:
    value = safe_ratio(total, minutes)
    return None if value is None else 36.0 * value


def per_75(total: int | float | None, possessions: int | float | None) -> float | None:
    value = safe_ratio(total, possessions)
    return None if value is None else 75.0 * value


def quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def distribution(values: Sequence[float]) -> Distribution:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return Distribution(0, None, None, None, None, None, None, None, None)
    median = statistics.median(finite)
    deviations = [abs(value - median) for value in finite]
    return Distribution(
        count=len(finite),
        mean=statistics.fmean(finite),
        median=median,
        std=statistics.pstdev(finite),
        mad=statistics.median(deviations),
        q1=quantile(finite, 0.25),
        q3=quantile(finite, 0.75),
        minimum=min(finite),
        maximum=max(finite),
    )


def standard_z_score(value: float | None, mean: float | None, std: float | None) -> float | None:
    if value is None or mean is None or std is None or std <= 0:
        return None
    return (value - mean) / std


def robust_z_score(value: float | None, median: float | None, mad: float | None) -> float | None:
    if value is None or median is None or mad is None or mad <= 0:
        return None
    return ROBUST_Z_SCALE * (value - median) / mad


def empirical_percentile(value: float | None, population: Sequence[float]) -> float | None:
    """Return a midrank percentile in (0, 1), assigning tied values the same percentile."""
    if value is None or not population:
        return None
    ordered = sorted(float(item) for item in population)
    lower = bisect.bisect_left(ordered, value)
    upper = bisect.bisect_right(ordered, value)
    return (lower + 0.5 * (upper - lower)) / len(ordered)


def relative_index(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference <= 0:
        return None
    return 100.0 * value / reference


def qualification_threshold(season_type: str, season_opportunity_games: int) -> int:
    if season_opportunity_games <= 0:
        raise ValueError("season opportunity must be positive")
    if season_type == "REGULAR":
        return max(5, math.ceil(0.20 * season_opportunity_games))
    if season_type == "PLAYOFF":
        return max(2, math.ceil(0.10 * season_opportunity_games))
    raise ValueError(f"unsupported season type: {season_type}")


def qualify_player_season(
    games_played: int,
    *,
    season_type: str,
    season_opportunity_games: int,
) -> Qualification:
    threshold = qualification_threshold(season_type, season_opportunity_games)
    status = (
        QualificationStatus.QUALIFIED
        if games_played >= threshold
        else QualificationStatus.NOT_QUALIFIED
    )
    comparator = ">=" if status is QualificationStatus.QUALIFIED else "<"
    reason = (
        f"GAMES_SCALED_{season_type}:games={games_played}{comparator}threshold={threshold};"
        f"opportunity_games={season_opportunity_games}"
    )
    return Qualification(status, reason, threshold, season_opportunity_games)


def candidate_thresholds(season_type: str, opportunity_games: int) -> dict[str, int]:
    if season_type == "REGULAR":
        return {
            "REG_GAMES_10PCT": max(5, math.ceil(0.10 * opportunity_games)),
            "REG_GAMES_20PCT_SELECTED": qualification_threshold(season_type, opportunity_games),
            "REG_GAMES_30PCT": max(5, math.ceil(0.30 * opportunity_games)),
        }
    if season_type == "PLAYOFF":
        return {
            "PO_ALL_APPEARANCES": 1,
            "PO_GAMES_10PCT_SELECTED": qualification_threshold(season_type, opportunity_games),
            "PO_GAMES_20PCT": max(2, math.ceil(0.20 * opportunity_games)),
        }
    raise ValueError(f"unsupported season type: {season_type}")


def partition_coverage_status(
    feature: FeatureDefinition,
    coverage: Mapping[str, str],
    *,
    possessions_qualified: bool,
    minutes_qualified: bool = True,
) -> tuple[bool, str]:
    failures = [
        f"{metric}={coverage.get(metric, 'MISSING')}"
        for metric in feature.required_coverage
        if coverage.get(metric) != "RELIABLE"
    ]
    if failures:
        return False, f"{EligibilityStatus.UNAVAILABLE_COVERAGE.value}:" + ",".join(failures)
    if "minutes" in feature.required_coverage and not minutes_qualified:
        return False, f"{EligibilityStatus.UNAVAILABLE_COVERAGE.value}:minutes_positive_share<0.99"
    if feature.possession_required and not possessions_qualified:
        return False, EligibilityStatus.UNAVAILABLE_POSSESSIONS.value
    return True, EligibilityStatus.AVAILABLE.value


def derive_feature_value(
    feature_name: str,
    row: Mapping[str, Any],
    advanced: Mapping[str, Any] | None = None,
) -> float | None:
    advanced = advanced or {}
    if feature_name == "games_played":
        return float(row["games_played"])
    if feature_name == "minutes_total":
        value = row.get("minutes_total")
        return None if value is None else float(value)
    if feature_name == "ppg":
        return per_game(row.get("points_total"), row.get("games_played"))
    if feature_name == "points_per_36":
        return per_36(row.get("points_total"), row.get("minutes_total"))
    if feature_name == "points_per_75":
        return per_75(row.get("points_total"), advanced.get("possessions"))
    if feature_name == "rpg":
        return per_game(row.get("rebounds_total"), row.get("games_played"))
    if feature_name == "rebounds_per_36":
        return per_36(row.get("rebounds_total"), row.get("minutes_total"))
    if feature_name == "apg":
        return per_game(row.get("assists_total"), row.get("games_played"))
    if feature_name == "assists_per_36":
        return per_36(row.get("assists_total"), row.get("minutes_total"))
    if feature_name == "spg":
        return per_game(row.get("steals_total"), row.get("games_played"))
    if feature_name == "bpg":
        return per_game(row.get("blocks_total"), row.get("games_played"))
    if feature_name == "fg_pct":
        return safe_ratio(row.get("fgm_total"), row.get("fga_total"))
    if feature_name == "ft_pct":
        return safe_ratio(row.get("ftm_total"), row.get("fta_total"))
    if feature_name == "fg3_pct":
        return safe_ratio(row.get("fg3m_total"), row.get("fg3a_total"))
    if feature_name == "efg_pct":
        return effective_fg_pct(row.get("fgm_total"), row.get("fg3m_total"), row.get("fga_total"))
    if feature_name == "ts_pct":
        return true_shooting_pct(
            row.get("points_total"), row.get("fga_total"), row.get("fta_total")
        )
    raise KeyError(f"unknown feature: {feature_name}")


def league_reference(
    feature_name: str,
    qualified_rows: Sequence[Mapping[str, Any]],
    advanced_by_player: Mapping[str, Mapping[str, Any]],
) -> float | None:
    if feature_name == "fg_pct":
        complete = [
            row
            for row in qualified_rows
            if row.get("fgm_total") is not None and row.get("fga_total") is not None
        ]
        return safe_ratio(
            sum(float(row["fgm_total"]) for row in complete),
            sum(float(row["fga_total"]) for row in complete),
        )
    if feature_name == "ft_pct":
        complete = [
            row
            for row in qualified_rows
            if row.get("ftm_total") is not None and row.get("fta_total") is not None
        ]
        return safe_ratio(
            sum(float(row["ftm_total"]) for row in complete),
            sum(float(row["fta_total"]) for row in complete),
        )
    if feature_name == "fg3_pct":
        complete = [
            row
            for row in qualified_rows
            if row.get("fg3m_total") is not None and row.get("fg3a_total") is not None
        ]
        return safe_ratio(
            sum(float(row["fg3m_total"]) for row in complete),
            sum(float(row["fg3a_total"]) for row in complete),
        )
    if feature_name == "efg_pct":
        complete = [
            row
            for row in qualified_rows
            if row.get("fgm_total") is not None
            and row.get("fg3m_total") is not None
            and row.get("fga_total") is not None
        ]
        made = sum(float(row["fgm_total"]) for row in complete)
        threes = sum(float(row["fg3m_total"]) for row in complete)
        attempts = sum(float(row["fga_total"]) for row in complete)
        return safe_ratio(made + 0.5 * threes, attempts)
    if feature_name == "ts_pct":
        complete = [
            row
            for row in qualified_rows
            if row.get("points_total") is not None
            and row.get("fga_total") is not None
            and row.get("fta_total") is not None
        ]
        points = sum(float(row["points_total"]) for row in complete)
        field_attempts = sum(float(row["fga_total"]) for row in complete)
        free_attempts = sum(float(row["fta_total"]) for row in complete)
        return true_shooting_pct(points, field_attempts, free_attempts)
    values = [
        value
        for row in qualified_rows
        if (
            value := derive_feature_value(
                feature_name, row, advanced_by_player.get(str(row["player_id"]))
            )
        )
        is not None
    ]
    return statistics.fmean(values) if values else None


def fingerprint_partitions(partitions: Sequence[Mapping[str, Any]]) -> str:
    stable = [
        {
            "path": str(item["path"]),
            "rows": int(item["rows"]),
            "columns": int(item["columns"]),
            "size_bytes": int(item["size_bytes"]),
            "sha256": str(item["sha256"]),
        }
        for item in sorted(partitions, key=lambda value: str(value["path"]))
    ]
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature_registry() -> dict[str, Any]:
    return {
        "registry_version": FEATURE_REGISTRY_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "normalization": {
            "standard_z": (
                "(value - qualified population mean) / population standard deviation (ddof=0)"
            ),
            "robust_z": f"{ROBUST_Z_SCALE} * (value - median) / median_absolute_deviation",
            "percentile": "midrank empirical percentile: (count_less + 0.5 * count_equal) / N",
            "relative_index": (
                "100 * value / metric-specific league reference; positive denominators only"
            ),
        },
        "comparison_population": {
            "regular": "games >= max(5, ceil(0.20 * maximum team games))",
            "playoff": "games >= max(2, ceil(0.10 * maximum team games))",
            "minutes": (
                "reported as opportunity metadata; not required because early seasons lack minutes"
            ),
            "team_rows": "excluded; only canonical TOTAL player-season rows define populations",
        },
        "rate_eligibility": {
            "per_game": "numerator coverage RELIABLE and games_played positive",
            "per_36": (
                "numerator/minutes RELIABLE and at least 99% of player-game minutes positive"
            ),
            "per_75": (
                "post-1996 official Advanced/Totals possessions with at least 99% positive coverage"
            ),
        },
        "features": [
            {
                **asdict(feature),
                "rate_basis": feature.rate_basis.value,
                "source_metrics": list(feature.source_metrics),
                "required_coverage": list(feature.required_coverage),
                "comparison_population": "qualified players in the same season and season_type",
            }
            for feature in FEATURE_DEFINITIONS
        ],
    }
