#!/usr/bin/env python3
"""Build deterministic coverage-aware Gold era-normalized player-season features."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from goatlab.data.canonical import canonical_id
from goatlab.features.era_normalization import (
    CORPUS_FINGERPRINT,
    CORPUS_ID,
    FEATURE_DEFINITIONS,
    METHODOLOGY_VERSION,
    EligibilityStatus,
    NormalizationMethod,
    QualificationStatus,
    candidate_thresholds,
    derive_feature_value,
    distribution,
    empirical_percentile,
    feature_registry,
    file_sha256,
    fingerprint_partitions,
    league_reference,
    partition_coverage_status,
    qualify_player_season,
    relative_index,
    robust_z_score,
    standard_z_score,
)

ROOT = Path(__file__).resolve().parents[2]
REPRESENTATIVE_SEASONS = (1961, 1971, 1984, 1990, 1999, 2008, 2012, 2015, 2021, 2023)
CASE_STUDIES = (
    ("Wilt Chamberlain", "76375", 1961),
    ("Kareem Abdul-Jabbar", "76003", 1971),
    ("Michael Jordan", "893", 1990),
    ("Shaquille O'Neal", "406", 1999),
    ("LeBron James", "2544", 2012),
    ("Stephen Curry", "201939", 2015),
    ("Nikola Jokic", "203999", 2021),
)
CASE_METRICS = ("ppg", "rpg", "apg", "ts_pct", "points_per_36", "points_per_75")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True, help="Fixed report timestamp")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=ROOT / "docs/data/historical-corpus-v1-manifest.json",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        default=ROOT / "docs/data/full-metric-coverage.json",
    )
    parser.add_argument(
        "--quality",
        type=Path,
        default=ROOT / "docs/data/full-data-quality-report.json",
    )
    return parser.parse_args()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _stable_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _verify_input_corpus(manifest_path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("corpus_id") != CORPUS_ID:
        raise ValueError("unexpected input corpus identifier")
    if manifest.get("corpus_fingerprint") != CORPUS_FINGERPRINT:
        raise ValueError("unexpected input corpus fingerprint")
    if manifest.get("season_end") != "2025-26" or not manifest.get("future_seasons_excluded"):
        raise ValueError("frozen corpus cutoff is not intact")
    mismatches: list[str] = []
    for item in manifest["silver_partitions"]:
        path = ROOT / str(item["path"])
        if not path.is_file() or file_sha256(path) != item["sha256"]:
            mismatches.append(str(item["path"]))
    if mismatches:
        raise ValueError(f"{len(mismatches)} frozen Silver partition hashes differ")
    return manifest


def _partition_path(root: Path, entity: str, season: int, season_type: str) -> Path:
    return root / entity / f"season={season}" / f"season_type={season_type}" / "part-00000.parquet"


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], pq.read_table(path).to_pylist())


def _write_parquet(
    rows: list[dict[str, Any]],
    path: Path,
    schema: pa.Schema,
    *,
    sort_fields: tuple[str, ...],
) -> dict[str, Any]:
    rows.sort(key=lambda row: tuple(str(row.get(field) or "") for field in sort_fields))
    table = pa.Table.from_pylist(rows, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=9,
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
    )
    temporary.replace(path)
    return {
        "path": _relative(path),
        "rows": table.num_rows,
        "columns": table.num_columns,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError("non-finite Gold feature value")
    return round(value, 12)


def _coverage_lookup(path: Path) -> dict[tuple[int, str], dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("corpus_id") != CORPUS_ID:
        raise ValueError("coverage matrix belongs to another corpus")
    output: dict[tuple[int, str], dict[str, str]] = defaultdict(dict)
    for item in raw["matrix"]:
        output[(int(item["season_id"]), str(item["season_type"]))][
            str(item["canonical_metric"])
        ] = str(item["classification"])
    return dict(output)


def _quality_lookup(path: Path) -> dict[tuple[int, str], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        (int(item["season"].split("-")[0]), str(item["season_type"])): item
        for item in raw["partitions"]
    }


def _team_game_environment(game_rows: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    games_by_team: dict[str, set[str]] = defaultdict(set)
    points_by_team_game: dict[tuple[str, str], float] = defaultdict(float)
    for row in game_rows:
        games_by_team[str(row["team_id"])].add(str(row["game_id"]))
        if row.get("points") is not None:
            points_by_team_game[(str(row["game_id"]), str(row["team_id"]))] += float(row["points"])
    opportunity = max((len(games) for games in games_by_team.values()), default=0)
    by_game: dict[str, list[float]] = defaultdict(list)
    for (game_id, _team_id), points in points_by_team_game.items():
        by_game[game_id].append(points)
    combined = [sum(points) for points in by_game.values() if len(points) == 2]
    return opportunity, {
        "team_game_count": len(points_by_team_game),
        "two_team_game_count": len(combined),
        "average_team_points_per_game": (
            sum(points_by_team_game.values()) / len(points_by_team_game)
            if points_by_team_game
            else None
        ),
        "average_combined_game_points": sum(combined) / len(combined) if combined else None,
    }


def _advanced_context(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], bool, float | None]:
    by_player = {str(row["player_id"]): row for row in rows}
    if not rows:
        return by_player, False, None
    positive_possessions = sum(
        row.get("possessions") is not None and float(row["possessions"]) > 0 for row in rows
    )
    possessions_qualified = positive_possessions / len(rows) >= 0.99
    exposures: list[tuple[float, float]] = []
    for row in rows:
        pace = row.get("pace")
        minutes = row.get("minutes")
        games = row.get("games_played")
        if pace is None or minutes is None or games is None:
            continue
        exposure = float(minutes) * float(games)
        if exposure > 0 and float(pace) > 0:
            exposures.append((float(pace), exposure))
    pace = (
        sum(value * weight for value, weight in exposures) / sum(weight for _, weight in exposures)
        if len(exposures) / len(rows) >= 0.99 and exposures
        else None
    )
    return by_player, possessions_qualified, pace


def _minute_context(rows: list[dict[str, Any]]) -> tuple[bool, float]:
    if not rows:
        return False, 0.0
    positive = sum(row.get("minutes") is not None and float(row["minutes"]) > 0 for row in rows)
    ratio = positive / len(rows)
    return ratio >= 0.99, ratio


def _method_status(
    method: NormalizationMethod,
    *,
    partition_available: bool,
    partition_reason: str,
    count: int,
    std: float | None,
    mad: float | None,
    reference: float | None,
    relative_supported: bool,
) -> str:
    if not partition_available:
        return partition_reason
    if count == 0:
        return EligibilityStatus.UNAVAILABLE_NO_POPULATION.value
    if method is NormalizationMethod.STANDARD_Z and (std is None or std <= 0):
        return EligibilityStatus.UNAVAILABLE_ZERO_VARIANCE.value
    if method is NormalizationMethod.ROBUST_Z and (mad is None or mad <= 0):
        return EligibilityStatus.UNAVAILABLE_ZERO_MAD.value
    if method is NormalizationMethod.RELATIVE_INDEX:
        if not relative_supported:
            return EligibilityStatus.UNAVAILABLE_METHOD.value
        if reference is None or reference <= 0:
            return EligibilityStatus.UNAVAILABLE_INVALID_REFERENCE.value
    return EligibilityStatus.AVAILABLE.value


def _context_metric_fields(prefix: str, stats: Any) -> dict[str, Any]:
    return {
        f"{prefix}_count": stats.count,
        f"{prefix}_mean": _finite(stats.mean),
        f"{prefix}_median": _finite(stats.median),
        f"{prefix}_std": _finite(stats.std),
        f"{prefix}_q1": _finite(stats.q1),
        f"{prefix}_q3": _finite(stats.q3),
    }


def _schemas() -> tuple[pa.Schema, pa.Schema, pa.Schema]:
    context_fields: list[tuple[str, pa.DataType]] = [
        ("season_id", pa.int64()),
        ("season_label", pa.string()),
        ("season_type", pa.string()),
        ("player_count", pa.int64()),
        ("qualified_player_count", pa.int64()),
        ("season_opportunity_games", pa.int64()),
        ("qualification_games_threshold", pa.int64()),
    ]
    for prefix in ("games", "minutes", "ppg", "rpg", "apg", "spg", "bpg"):
        context_fields.extend(
            [
                (f"{prefix}_count", pa.int64()),
                (f"{prefix}_mean", pa.float64()),
                (f"{prefix}_median", pa.float64()),
                (f"{prefix}_std", pa.float64()),
                (f"{prefix}_q1", pa.float64()),
                (f"{prefix}_q3", pa.float64()),
            ]
        )
    context_fields.extend(
        [
            ("league_fg_pct", pa.float64()),
            ("league_ft_pct", pa.float64()),
            ("league_fg3_pct", pa.float64()),
            ("league_efg_pct", pa.float64()),
            ("league_ts_pct", pa.float64()),
            ("average_team_points_per_game", pa.float64()),
            ("average_combined_game_points", pa.float64()),
            ("team_scoring_status", pa.string()),
            ("average_team_possessions", pa.float64()),
            ("team_possessions_status", pa.string()),
            ("league_pace", pa.float64()),
            ("league_pace_status", pa.string()),
            ("advanced_possessions_qualified", pa.bool_()),
            ("positive_minutes_percentage", pa.float64()),
            ("minutes_empirical_status", pa.string()),
            ("corpus_id", pa.string()),
            ("corpus_fingerprint", pa.string()),
            ("methodology_version", pa.string()),
        ]
    )
    long_schema = pa.schema(
        [
            ("player_id", pa.string()),
            ("season_id", pa.int64()),
            ("season_type", pa.string()),
            ("metric_name", pa.string()),
            ("rate_basis", pa.string()),
            ("raw_value", pa.float64()),
            ("comparison_value", pa.float64()),
            ("qualified_population_size", pa.int64()),
            ("league_mean", pa.float64()),
            ("league_median", pa.float64()),
            ("league_std", pa.float64()),
            ("league_mad", pa.float64()),
            ("league_reference", pa.float64()),
            ("z_score", pa.float64()),
            ("robust_z_score", pa.float64()),
            ("percentile", pa.float64()),
            ("relative_index", pa.float64()),
            ("coverage_status", pa.string()),
            ("qualification_status", pa.string()),
            ("qualification_reason", pa.string()),
            ("sample_size_games", pa.int64()),
            ("opportunity_minutes", pa.float64()),
            ("source_metrics", pa.string()),
            ("formula", pa.string()),
            ("methodology_version", pa.string()),
            ("corpus_id", pa.string()),
            ("corpus_fingerprint", pa.string()),
        ]
    )
    wide_fields: list[tuple[str, pa.DataType]] = [
        ("player_id", pa.string()),
        ("season_id", pa.int64()),
        ("season_type", pa.string()),
        ("qualification_status", pa.string()),
        ("qualification_reason", pa.string()),
        ("games_played", pa.int64()),
        ("minutes_total", pa.float64()),
    ]
    for name in ("ppg", "rpg", "apg", "spg", "bpg", "ts_pct", "efg_pct"):
        wide_fields.extend(
            [
                (name, pa.float64()),
                (f"{name}_z", pa.float64()),
                (f"{name}_robust_z", pa.float64()),
                (f"{name}_percentile", pa.float64()),
                (f"{name}_relative_index", pa.float64()),
            ]
        )
    wide_fields.extend(
        [
            ("methodology_version", pa.string()),
            ("corpus_id", pa.string()),
            ("corpus_fingerprint", pa.string()),
        ]
    )
    return pa.schema(context_fields), long_schema, pa.schema(wide_fields)


def _sensitivity_rows(
    rows: list[dict[str, Any]],
    *,
    season: int,
    season_type: str,
    opportunity_games: int,
    coverage: dict[str, str],
    minutes_qualified: bool,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    candidates = candidate_thresholds(season_type, opportunity_games)
    selected_threshold = (
        candidates["REG_GAMES_20PCT_SELECTED"]
        if season_type == "REGULAR"
        else candidates["PO_GAMES_10PCT_SELECTED"]
    )
    for candidate, threshold in candidates.items():
        qualified = [row for row in rows if int(row["games_played"]) >= threshold]
        values = [
            value for row in qualified if (value := derive_feature_value("ppg", row)) is not None
        ]
        stats = distribution(values if coverage.get("points") == "RELIABLE" else [])
        output.append(
            {
                "season_id": season,
                "season_label": f"{season}-{str(season + 1)[-2:]}",
                "season_type": season_type,
                "candidate": candidate,
                "games_threshold": threshold,
                "season_opportunity_games": opportunity_games,
                "player_count": len(rows),
                "qualified_count": len(qualified),
                "qualified_share": round(len(qualified) / len(rows), 8),
                "ppg_population_count": stats.count,
                "ppg_mean": _finite(stats.mean),
                "ppg_median": _finite(stats.median),
                "selected": threshold == selected_threshold and "SELECTED" in candidate,
                "minutes_required": False,
            }
        )
    minutes = [float(row["minutes_total"]) for row in rows if row.get("minutes_total") is not None]
    if coverage.get("minutes") == "RELIABLE" and minutes_qualified and len(minutes) == len(rows):
        minimum_minutes = 0.10 * max(minutes)
        qualified = [
            row
            for row in rows
            if int(row["games_played"]) >= selected_threshold
            and float(row["minutes_total"]) >= minimum_minutes
        ]
        values = [
            value for row in qualified if (value := derive_feature_value("ppg", row)) is not None
        ]
        stats = distribution(values)
        output.append(
            {
                "season_id": season,
                "season_label": f"{season}-{str(season + 1)[-2:]}",
                "season_type": season_type,
                "candidate": "SELECTED_GAMES_PLUS_10PCT_MAX_MINUTES",
                "games_threshold": selected_threshold,
                "season_opportunity_games": opportunity_games,
                "player_count": len(rows),
                "qualified_count": len(qualified),
                "qualified_share": round(len(qualified) / len(rows), 8),
                "ppg_population_count": stats.count,
                "ppg_mean": _finite(stats.mean),
                "ppg_median": _finite(stats.median),
                "selected": False,
                "minutes_required": True,
                "minimum_minutes": _finite(minimum_minutes),
            }
        )
    return output


def _build_partition(
    args: argparse.Namespace,
    *,
    season: int,
    season_type: str,
    coverage: dict[str, str],
    quality: dict[str, Any],
    schemas: tuple[pa.Schema, pa.Schema, pa.Schema],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, int],
]:
    all_season_rows = _read_rows(
        _partition_path(args.silver_root, "player_season_stats", season, season_type)
    )
    season_rows = [
        row for row in all_season_rows if row["row_scope"] == "TOTAL" and row["team_id"] is None
    ]
    if len({str(row["player_id"]) for row in season_rows}) != len(season_rows):
        raise ValueError(f"duplicate TOTAL player rows in {season} {season_type}")
    game_rows = _read_rows(
        _partition_path(args.silver_root, "player_game_stats", season, season_type)
    )
    minutes_qualified, positive_minutes_percentage = _minute_context(game_rows)
    opportunity_games, scoring = _team_game_environment(game_rows)
    if opportunity_games <= 0:
        raise ValueError(f"no season opportunity in {season} {season_type}")
    advanced_path = _partition_path(args.silver_root, "player_season_advanced", season, season_type)
    advanced_rows = _read_rows(advanced_path) if advanced_path.is_file() else []
    advanced_by_player, possessions_qualified, league_pace = _advanced_context(advanced_rows)
    qualifications = {
        str(row["player_id"]): qualify_player_season(
            int(row["games_played"]),
            season_type=season_type,
            season_opportunity_games=opportunity_games,
        )
        for row in season_rows
    }
    qualified_rows = [
        row
        for row in season_rows
        if qualifications[str(row["player_id"])].status is QualificationStatus.QUALIFIED
    ]

    feature_context: dict[str, dict[str, Any]] = {}
    eligibility: list[dict[str, Any]] = []
    for feature in FEATURE_DEFINITIONS:
        available, reason = partition_coverage_status(
            feature,
            coverage,
            possessions_qualified=possessions_qualified,
            minutes_qualified=minutes_qualified,
        )
        population = (
            [
                value
                for row in qualified_rows
                if (
                    value := derive_feature_value(
                        feature.name, row, advanced_by_player.get(str(row["player_id"]))
                    )
                )
                is not None
            ]
            if available
            else []
        )
        stats = distribution(population)
        reference = (
            league_reference(feature.name, qualified_rows, advanced_by_player)
            if available
            else None
        )
        feature_context[feature.name] = {
            "available": available,
            "reason": reason,
            "population": population,
            "stats": stats,
            "reference": reference,
        }
        for method in NormalizationMethod:
            eligibility.append(
                {
                    "season_id": season,
                    "season_label": f"{season}-{str(season + 1)[-2:]}",
                    "season_type": season_type,
                    "metric_name": feature.name,
                    "rate_basis": feature.rate_basis.value,
                    "normalization_method": method.value,
                    "status": _method_status(
                        method,
                        partition_available=available,
                        partition_reason=reason,
                        count=stats.count,
                        std=stats.std,
                        mad=stats.mad,
                        reference=reference,
                        relative_supported=feature.relative_index_supported,
                    ),
                    "qualified_population_size": stats.count,
                    "required_coverage": list(feature.required_coverage),
                    "observed_coverage": {
                        metric: coverage.get(metric, "MISSING")
                        for metric in feature.required_coverage
                    },
                    "possessions_qualified": possessions_qualified,
                    "methodology_version": METHODOLOGY_VERSION,
                    "corpus_id": CORPUS_ID,
                }
            )

    long_rows: list[dict[str, Any]] = []
    wide_rows: list[dict[str, Any]] = []
    wide_metrics = {"ppg", "rpg", "apg", "spg", "bpg", "ts_pct", "efg_pct"}
    for row in season_rows:
        player_id = str(row["player_id"])
        qualification = qualifications[player_id]
        wide: dict[str, Any] = {
            "player_id": player_id,
            "season_id": season,
            "season_type": season_type,
            "qualification_status": qualification.status.value,
            "qualification_reason": qualification.reason,
            "games_played": int(row["games_played"]),
            "minutes_total": row.get("minutes_total"),
            "methodology_version": METHODOLOGY_VERSION,
            "corpus_id": CORPUS_ID,
            "corpus_fingerprint": CORPUS_FINGERPRINT,
        }
        for feature in FEATURE_DEFINITIONS:
            context = feature_context[feature.name]
            stats = context["stats"]
            value = (
                derive_feature_value(feature.name, row, advanced_by_player.get(player_id))
                if context["available"]
                else None
            )
            coverage_status = str(context["reason"])
            if context["available"] and value is None:
                coverage_status = EligibilityStatus.AVAILABLE_PLAYER_INPUT_NULL.value
            z_value = standard_z_score(value, stats.mean, stats.std)
            robust_value = robust_z_score(value, stats.median, stats.mad)
            percentile_value = empirical_percentile(value, context["population"])
            relative_value = (
                relative_index(value, context["reference"])
                if feature.relative_index_supported
                else None
            )
            long_rows.append(
                {
                    "player_id": player_id,
                    "season_id": season,
                    "season_type": season_type,
                    "metric_name": feature.name,
                    "rate_basis": feature.rate_basis.value,
                    "raw_value": _finite(value),
                    "comparison_value": _finite(value),
                    "qualified_population_size": stats.count,
                    "league_mean": _finite(stats.mean),
                    "league_median": _finite(stats.median),
                    "league_std": _finite(stats.std),
                    "league_mad": _finite(stats.mad),
                    "league_reference": _finite(context["reference"]),
                    "z_score": _finite(z_value),
                    "robust_z_score": _finite(robust_value),
                    "percentile": _finite(percentile_value),
                    "relative_index": _finite(relative_value),
                    "coverage_status": coverage_status,
                    "qualification_status": qualification.status.value,
                    "qualification_reason": qualification.reason,
                    "sample_size_games": int(row["games_played"]),
                    "opportunity_minutes": row.get("minutes_total"),
                    "source_metrics": json.dumps(
                        list(feature.source_metrics), separators=(",", ":")
                    ),
                    "formula": feature.formula,
                    "methodology_version": METHODOLOGY_VERSION,
                    "corpus_id": CORPUS_ID,
                    "corpus_fingerprint": CORPUS_FINGERPRINT,
                }
            )
            if feature.name in wide_metrics:
                wide[feature.name] = _finite(value)
                wide[f"{feature.name}_z"] = _finite(z_value)
                wide[f"{feature.name}_robust_z"] = _finite(robust_value)
                wide[f"{feature.name}_percentile"] = _finite(percentile_value)
                wide[f"{feature.name}_relative_index"] = _finite(relative_value)
        wide_rows.append(wide)

    games_stats = distribution([float(row["games_played"]) for row in qualified_rows])
    context_row: dict[str, Any] = {
        "season_id": season,
        "season_label": f"{season}-{str(season + 1)[-2:]}",
        "season_type": season_type,
        "player_count": len(season_rows),
        "qualified_player_count": len(qualified_rows),
        "season_opportunity_games": opportunity_games,
        "qualification_games_threshold": next(iter(qualifications.values())).games_threshold,
        **_context_metric_fields("games", games_stats),
    }
    for prefix, feature_name in (
        ("minutes", "minutes_total"),
        ("ppg", "ppg"),
        ("rpg", "rpg"),
        ("apg", "apg"),
        ("spg", "spg"),
        ("bpg", "bpg"),
    ):
        context_row.update(_context_metric_fields(prefix, feature_context[feature_name]["stats"]))
    points_complete = coverage.get("points") == "RELIABLE" and int(quality["source_rows"]) == int(
        quality["silver_rows"]
    )
    context_row.update(
        {
            "league_fg_pct": _finite(feature_context["fg_pct"]["reference"]),
            "league_ft_pct": _finite(feature_context["ft_pct"]["reference"]),
            "league_fg3_pct": _finite(feature_context["fg3_pct"]["reference"]),
            "league_efg_pct": _finite(feature_context["efg_pct"]["reference"]),
            "league_ts_pct": _finite(feature_context["ts_pct"]["reference"]),
            "average_team_points_per_game": (
                _finite(scoring["average_team_points_per_game"]) if points_complete else None
            ),
            "average_combined_game_points": (
                _finite(scoring["average_combined_game_points"]) if points_complete else None
            ),
            "team_scoring_status": (
                "AVAILABLE_ACCEPTED_PLAYER_POINT_SUMS"
                if points_complete
                else "UNAVAILABLE_SOURCE_QUARANTINE_OR_COVERAGE"
            ),
            "average_team_possessions": None,
            "team_possessions_status": "UNAVAILABLE_NO_CANONICAL_TEAM_POSSESSION_FACT",
            "league_pace": _finite(league_pace),
            "league_pace_status": (
                "AVAILABLE_OFFICIAL_PLAYER_MINUTES_WEIGHTED"
                if league_pace is not None
                else "UNAVAILABLE_OFFICIAL_ADVANCED_COVERAGE"
            ),
            "advanced_possessions_qualified": possessions_qualified,
            "positive_minutes_percentage": _finite(positive_minutes_percentage),
            "minutes_empirical_status": (
                "RELIABLE_POSITIVE_SHARE"
                if minutes_qualified
                else "UNAVAILABLE_OR_PLACEHOLDER_ZERO_MINUTES"
            ),
            "corpus_id": CORPUS_ID,
            "corpus_fingerprint": CORPUS_FINGERPRINT,
            "methodology_version": METHODOLOGY_VERSION,
        }
    )

    context_schema, long_schema, wide_schema = schemas
    partitions = [
        _write_parquet(
            [context_row],
            _partition_path(args.gold_root, "league_season_context", season, season_type),
            context_schema,
            sort_fields=("season_id", "season_type"),
        ),
        _write_parquet(
            long_rows,
            _partition_path(args.gold_root, "player_season_feature_long", season, season_type),
            long_schema,
            sort_fields=("player_id", "metric_name"),
        ),
        _write_parquet(
            wide_rows,
            _partition_path(args.gold_root, "player_season_normalized", season, season_type),
            wide_schema,
            sort_fields=("player_id",),
        ),
    ]
    sensitivity = _sensitivity_rows(
        season_rows,
        season=season,
        season_type=season_type,
        opportunity_games=opportunity_games,
        coverage=coverage,
        minutes_qualified=minutes_qualified,
    )
    source_player_ids = {str(row["player_id"]) for row in season_rows}
    long_keys = [
        (
            str(row["player_id"]),
            int(row["season_id"]),
            str(row["season_type"]),
            str(row["metric_name"]),
        )
        for row in long_rows
    ]
    wide_keys = [
        (str(row["player_id"]), int(row["season_id"]), str(row["season_type"])) for row in wide_rows
    ]
    local_quality = {
        "duplicate_long_keys": len(long_keys) - len(set(long_keys)),
        "duplicate_wide_keys": len(wide_keys) - len(set(wide_keys)),
        "orphan_player_ids": sum(
            str(row["player_id"]) not in source_player_ids for row in long_rows
        ),
        "orphan_season_ids": sum(int(row["season_id"]) != season for row in long_rows),
        "team_rows_consumed": sum(
            row["row_scope"] != "TOTAL" or row["team_id"] is not None for row in season_rows
        ),
        "season_type_mixing": sum(str(row["season_type"]) != season_type for row in long_rows),
        "non_finite_values": sum(
            value is not None and not math.isfinite(float(value))
            for row in long_rows
            for value in (
                row["raw_value"],
                row["z_score"],
                row["robust_z_score"],
                row["percentile"],
                row["relative_index"],
            )
        ),
        "percentile_bounds_violations": sum(
            row["percentile"] is not None and not 0.0 <= float(row["percentile"]) <= 1.0
            for row in long_rows
        ),
        "unavailable_metric_non_null_leakage": sum(
            not str(row["coverage_status"]).startswith("AVAILABLE") and row["raw_value"] is not None
            for row in long_rows
        ),
        "null_to_zero_conversions": sum(
            not str(row["coverage_status"]).startswith("AVAILABLE") and row["raw_value"] == 0
            for row in long_rows
        ),
        "incorrect_total_source_rows": len(all_season_rows)
        - len(season_rows)
        - sum(row["row_scope"] == "TEAM" for row in all_season_rows),
    }
    return (
        long_rows,
        wide_rows,
        context_row,
        eligibility,
        sensitivity,
        partitions,
        local_quality,
    )


def _case_study_report(case_records: dict[tuple[str, int], list[dict[str, Any]]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for display_name, nba_player_id, season in CASE_STUDIES:
        player_id = canonical_id("player", "nba", nba_player_id)
        records = case_records.get((player_id, season), [])
        by_metric = {record["metric_name"]: record for record in records}
        cases.append(
            {
                "display_name": display_name,
                "nba_player_id": nba_player_id,
                "player_id": player_id,
                "season": f"{season}-{str(season + 1)[-2:]}",
                "season_type": "REGULAR",
                "qualification_status": (
                    records[0]["qualification_status"] if records else "NOT_FOUND"
                ),
                "metrics": {
                    metric: {
                        key: by_metric[metric].get(key)
                        for key in (
                            "raw_value",
                            "league_mean",
                            "z_score",
                            "robust_z_score",
                            "percentile",
                            "relative_index",
                            "coverage_status",
                            "sample_size_games",
                        )
                    }
                    for metric in CASE_METRICS
                    if metric in by_metric
                },
            }
        )
    return {
        "step": "STEP-0007",
        "purpose": "diagnostic primitive-feature interpretation; no composite or ranking",
        "corpus_id": CORPUS_ID,
        "methodology_version": METHODOLOGY_VERSION,
        "cases": cases,
    }


def _validation_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if int(record["season_id"]) in REPRESENTATIVE_SEASONS:
            grouped[(record["season_id"], record["season_type"], record["metric_name"])].append(
                record
            )
    checked = z_failures = percentile_failures = mixing_failures = 0
    maximum_abs_z_mean = 0.0
    maximum_abs_z_std_error = 0.0
    for (_season, _season_type, _metric), values in grouped.items():
        qualified = [
            item
            for item in values
            if item["qualification_status"] == "QUALIFIED" and item["z_score"] is not None
        ]
        if qualified:
            z_values = [float(item["z_score"]) for item in qualified]
            z_mean = sum(z_values) / len(z_values)
            z_std = math.sqrt(sum((value - z_mean) ** 2 for value in z_values) / len(z_values))
            maximum_abs_z_mean = max(maximum_abs_z_mean, abs(z_mean))
            maximum_abs_z_std_error = max(maximum_abs_z_std_error, abs(z_std - 1.0))
            z_failures += abs(z_mean) > 1e-9 or abs(z_std - 1.0) > 1e-9
            checked += 1
        ordered = sorted(
            (
                float(item["raw_value"]),
                float(item["percentile"]),
            )
            for item in values
            if item["raw_value"] is not None and item["percentile"] is not None
        )
        percentile_failures += any(
            left[0] < right[0] and left[1] > right[1] for left, right in pairwise(ordered)
        )
        mixing_failures += len({item["season_type"] for item in values}) != 1
    return {
        "representative_seasons": [
            f"{season}-{str(season + 1)[-2:]}" for season in REPRESENTATIVE_SEASONS
        ],
        "z_distribution_groups_checked": checked,
        "maximum_absolute_qualified_z_mean": round(maximum_abs_z_mean, 12),
        "maximum_absolute_qualified_z_std_error": round(maximum_abs_z_std_error, 12),
        "z_distribution_failures": z_failures,
        "percentile_ordering_failures": percentile_failures,
        "season_type_mixing_failures": mixing_failures,
    }


def main() -> int:
    args = _args()
    started = time.perf_counter()
    manifest = _verify_input_corpus(args.corpus_manifest)
    coverage_lookup = _coverage_lookup(args.coverage)
    quality_lookup = _quality_lookup(args.quality)
    schemas = _schemas()
    partitions: list[dict[str, Any]] = []
    all_eligibility: list[dict[str, Any]] = []
    all_sensitivity: list[dict[str, Any]] = []
    all_representative_records: list[dict[str, Any]] = []
    case_records: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    context_rows: list[dict[str, Any]] = []
    long_count = wide_count = 0
    quality_counts: Counter[str] = Counter()

    for season in range(1946, 2026):
        for season_type in ("REGULAR", "PLAYOFF"):
            result = _build_partition(
                args,
                season=season,
                season_type=season_type,
                coverage=coverage_lookup[(season, season_type)],
                quality=quality_lookup[(season, season_type)],
                schemas=schemas,
            )
            long_rows, wide_rows, context, eligibility, sensitivity, output, local_quality = result
            quality_counts.update(local_quality)
            partitions.extend(output)
            all_eligibility.extend(eligibility)
            all_sensitivity.extend(sensitivity)
            context_rows.append(context)
            long_count += len(long_rows)
            wide_count += len(wide_rows)
            if season in REPRESENTATIVE_SEASONS:
                all_representative_records.extend(long_rows)
            if season in {item[2] for item in CASE_STUDIES} and season_type == "REGULAR":
                for row in long_rows:
                    case_records[(str(row["player_id"]), season)].append(row)
            print(
                f"{season}-{str(season + 1)[-2:]} {season_type}: "
                f"players={len(wide_rows)} features={len(long_rows)}"
            )

    fingerprint = fingerprint_partitions(partitions)
    reproducible = args.expected_fingerprint is None or fingerprint == args.expected_fingerprint
    if not reproducible:
        raise ValueError(
            f"Gold fingerprint {fingerprint} differs from expected {args.expected_fingerprint}"
        )
    elapsed = round(time.perf_counter() - started, 6)
    gold_bytes = sum(int(item["size_bytes"]) for item in partitions)
    eligibility_counts = Counter(
        item["status"].split(":", maxsplit=1)[0] for item in all_eligibility
    )
    feature_available_partitions: dict[str, int] = Counter(
        item["metric_name"]
        for item in all_eligibility
        if item["normalization_method"] == "PERCENTILE" and item["status"] == "AVAILABLE"
    )
    qualification_counts = Counter(
        row["qualification_status"] for row in all_representative_records
    )
    validation = _validation_summary(all_representative_records)
    quality_checks = dict(sorted(quality_counts.items()))
    quality_checks["representative_validation_season_type_mixing"] = validation[
        "season_type_mixing_failures"
    ]
    pass_conditions = {
        "all_160_contexts_written": len(context_rows) == 160,
        "qualification_sensitivity_complete": len(all_sensitivity) >= 480,
        "normalization_properties_valid": (
            validation["z_distribution_failures"] == 0
            and validation["percentile_ordering_failures"] == 0
        ),
        "coverage_gating_complete": len(all_eligibility) == 160 * len(FEATURE_DEFINITIONS) * 4,
        "regular_playoff_isolated": validation["season_type_mixing_failures"] == 0,
        "no_quality_gate_failure": not any(quality_checks.values()),
        "frozen_input_verified": manifest["corpus_fingerprint"] == CORPUS_FINGERPRINT,
        "gold_reproducible_when_expected": reproducible,
        "no_network_required": True,
    }
    decision = "PASS" if all(pass_conditions.values()) else "FAIL"

    sensitivity_by_candidate: dict[str, dict[str, Any]] = {}
    for candidate in sorted({str(item["candidate"]) for item in all_sensitivity}):
        items = [item for item in all_sensitivity if item["candidate"] == candidate]
        sensitivity_by_candidate[candidate] = {
            "partitions": len(items),
            "mean_qualified_share": round(
                sum(float(item["qualified_share"]) for item in items) / len(items), 8
            ),
            "minimum_qualified_share": min(float(item["qualified_share"]) for item in items),
            "maximum_qualified_share": max(float(item["qualified_share"]) for item in items),
            "mean_qualified_count": round(
                sum(int(item["qualified_count"]) for item in items) / len(items), 4
            ),
        }
    sensitivity_report = {
        "step": "STEP-0007",
        "corpus_id": CORPUS_ID,
        "methodology_version": METHODOLOGY_VERSION,
        "selected_rule": feature_registry()["comparison_population"],
        "selection_rationale": [
            "Scale games to observed maximum team opportunities, not a fixed 82-game assumption.",
            "Exclude one-game playoff observations while retaining short early-round series.",
            "Do not require minutes because early seasons lack reliable minutes.",
            "Keep every non-qualified player-season in Gold with an explicit status and reason.",
        ],
        "candidate_summary": sensitivity_by_candidate,
        "partitions": all_sensitivity,
    }
    eligibility_report = {
        "step": "STEP-0007",
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "methodology_version": METHODOLOGY_VERSION,
        "records": len(all_eligibility),
        "status_counts": dict(sorted(eligibility_counts.items())),
        "available_partition_counts_by_feature": dict(sorted(feature_available_partitions.items())),
        "matrix": all_eligibility,
    }
    case_report = _case_study_report(case_records)
    summary = {
        "step": "STEP-0007",
        "run_at": args.run_at,
        "decision": decision,
        "feature_methodology_version": METHODOLOGY_VERSION,
        "input": {
            "corpus_id": CORPUS_ID,
            "corpus_fingerprint": CORPUS_FINGERPRINT,
            "silver_partitions_verified": len(manifest["silver_partitions"]),
            "network_requests": 0,
        },
        "outputs": {
            "league_context_rows": len(context_rows),
            "normalized_wide_rows": wide_count,
            "feature_long_rows": long_count,
            "eligibility_records": len(all_eligibility),
            "gold_partitions": len(partitions),
            "gold_size_bytes": gold_bytes,
            "gold_fingerprint": fingerprint,
        },
        "qualification": {
            "regular_rule": "games >= max(5, ceil(20% * maximum team games))",
            "playoff_rule": "games >= max(2, ceil(10% * maximum team games))",
            "representative_record_status_counts": dict(sorted(qualification_counts.items())),
            "sensitivity_candidates": len(sensitivity_by_candidate),
        },
        "eligibility": eligibility_report["status_counts"],
        "available_partition_counts_by_feature": dict(sorted(feature_available_partitions.items())),
        "validation": validation,
        "quality_checks": quality_checks,
        "pass_conditions": pass_conditions,
        "reproducibility": {
            "expected_fingerprint": args.expected_fingerprint,
            "observed_fingerprint": fingerprint,
            "pass": reproducible,
        },
        "performance": {"runtime_seconds": elapsed, "gold_size_bytes": gold_bytes},
    }
    gold_manifest = {
        "manifest_version": 1,
        "step": "STEP-0007",
        "run_at": args.run_at,
        "corpus_id": CORPUS_ID,
        "input_corpus_fingerprint": CORPUS_FINGERPRINT,
        "methodology_version": METHODOLOGY_VERSION,
        "output_fingerprint": fingerprint,
        "partition_count": len(partitions),
        "size_bytes": gold_bytes,
        "partitions": partitions,
        "reproducibility": summary["reproducibility"],
    }

    _stable_json(args.docs_root / "era-normalization-summary.json", summary)
    _stable_json(args.docs_root / "feature-eligibility-matrix.json", eligibility_report)
    _stable_json(args.docs_root / "normalization-case-studies.json", case_report)
    _stable_json(args.docs_root / "qualification-sensitivity-analysis.json", sensitivity_report)
    _stable_json(args.docs_root / "era-normalization-gold-manifest.json", gold_manifest)
    registry_path = args.docs_root / "era-normalized-feature-definitions.yaml"
    registry_path.write_text(
        yaml.safe_dump(feature_registry(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if decision == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
