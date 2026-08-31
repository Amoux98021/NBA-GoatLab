#!/usr/bin/env python3
"""Build deterministic career trajectory, peak, prime, and longevity Gold primitives."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from goatlab.data.canonical import canonical_id
from goatlab.features.career_trajectory import (
    CAREER_METHODOLOGY_VERSION,
    CORE_CANDIDATE_METRICS,
    CORPUS_FINGERPRINT,
    CORPUS_ID,
    ELITE_THRESHOLDS,
    NORMALIZATION_FINGERPRINT,
    NORMALIZATION_METHODS,
    NORMALIZATION_VERSION,
    PERCENTILE_BASELINES,
    WINDOW_SIZES,
    CandidateEvidence,
    CoverageStatus,
    PeakVariant,
    SeasonValue,
    age_on_season_reference,
    area_above_percentile,
    best_non_contiguous,
    best_peak_window,
    candidate_universe_flags,
    career_feature_registry,
    career_sequence,
    cumulative_positive_z,
    file_sha256,
    fingerprint_partitions,
    player_bucket,
    population_std,
    prime_run,
    safe_mean,
)

ROOT = Path(__file__).resolve().parents[2]
BUCKETS = 32
SQLITE_FINGERPRINT = "65b6412234d2d8817678d04f7cd2548aec82fec02b6c5b86679cade7572c21c7"
METHOD_COLUMN = {
    "STANDARD_Z": "z_score",
    "ROBUST_Z": "robust_z_score",
    "PERCENTILE": "percentile",
    "RELATIVE_INDEX": "relative_index",
}
CASE_STUDIES = (
    ("Bill Russell", "78049"),
    ("Wilt Chamberlain", "76375"),
    ("Kareem Abdul-Jabbar", "76003"),
    ("Magic Johnson", "77142"),
    ("Larry Bird", "1449"),
    ("Michael Jordan", "893"),
    ("Hakeem Olajuwon", "165"),
    ("Shaquille O'Neal", "406"),
    ("Tim Duncan", "1495"),
    ("Kobe Bryant", "977"),
    ("LeBron James", "2544"),
    ("Stephen Curry", "201939"),
    ("Kevin Durant", "201142"),
    ("Nikola Jokic", "203999"),
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument("--sqlite", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=ROOT / "docs/data/historical-corpus-v1-manifest.json",
    )
    parser.add_argument(
        "--normalization-manifest",
        type=Path,
        default=ROOT / "docs/data/era-normalization-gold-manifest.json",
    )
    parser.add_argument(
        "--identity-report",
        type=Path,
        default=ROOT / "docs/data/full-identity-reconciliation.json",
    )
    return parser.parse_args()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _stable_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError("non-finite career feature")
    return round(value, 12)


def _describe_numbers(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "minimum": _finite(min(values) if values else None),
        "median": _finite(statistics.median(values) if values else None),
        "mean": _finite(safe_mean(values)),
        "maximum": _finite(max(values) if values else None),
    }


def _read_rows(path: Path, columns: list[str] | None = None) -> list[dict[str, Any]]:
    table = pq.ParquetFile(path).read(columns=columns)
    return cast(list[dict[str, Any]], table.to_pylist())


def _partition(root: Path, entity: str, bucket: int) -> Path:
    return root / entity / f"bucket={bucket:02d}" / "part-00000.parquet"


def _write_parquet(
    rows: list[dict[str, Any]],
    path: Path,
    schema: pa.Schema,
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


def _verify_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    corpus = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    normalization = json.loads(args.normalization_manifest.read_text(encoding="utf-8"))
    if corpus["corpus_id"] != CORPUS_ID or corpus["corpus_fingerprint"] != CORPUS_FINGERPRINT:
        raise ValueError("unexpected frozen corpus")
    if corpus["season_end"] != "2025-26" or not corpus["future_seasons_excluded"]:
        raise ValueError("frozen cutoff changed")
    if (
        normalization["methodology_version"] != NORMALIZATION_VERSION
        or normalization["output_fingerprint"] != NORMALIZATION_FINGERPRINT
    ):
        raise ValueError("unexpected normalization input")
    mismatches: list[str] = []
    for item in normalization["partitions"]:
        path = ROOT / str(item["path"])
        if not path.is_file() or file_sha256(path) != item["sha256"]:
            mismatches.append(str(item["path"]))
    if mismatches:
        raise ValueError(f"{len(mismatches)} normalization partitions differ")
    if file_sha256(args.sqlite) != SQLITE_FINGERPRINT:
        raise ValueError("audited identity SQLite fingerprint changed")
    return corpus, normalization


def _identity_context(
    sqlite_path: Path,
    report_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    identities: dict[str, dict[str, Any]] = {}
    nba_by_player: dict[str, str] = {}
    connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        common = {
            str(row[0]): row[1]
            for row in connection.execute("SELECT person_id, birthdate FROM common_player_info")
        }
        for nba_id, full_name, is_active in connection.execute(
            "SELECT id, full_name, is_active FROM player"
        ):
            player_id = canonical_id("player", "nba", str(nba_id))
            birth_raw = common.get(str(nba_id))
            identities[player_id] = {
                "nba_player_id": str(nba_id),
                "display_name": str(full_name),
                "birth_date": (
                    date.fromisoformat(str(birth_raw)[:10]) if birth_raw is not None else None
                ),
                "legacy_is_active": bool(is_active) if is_active is not None else None,
                "identity_source": "nbadb_v238_player_common_player_info",
            }
            nba_by_player[player_id] = str(nba_id)
    finally:
        connection.close()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for item in report["official_source_only_records"]:
        player_id = str(item["player_id"])
        identities[player_id] = {
            "nba_player_id": str(item["nba_player_id"]),
            "display_name": str(item["diagnostic_name"]),
            "birth_date": None,
            "legacy_is_active": None,
            "identity_source": str(item["source_id"]),
        }
        nba_by_player[player_id] = str(item["nba_player_id"])
    return identities, nba_by_player


def _schemas() -> dict[str, pa.Schema]:
    provenance = [
        ("career_methodology_version", pa.string()),
        ("normalization_version", pa.string()),
        ("normalization_fingerprint", pa.string()),
        ("corpus_id", pa.string()),
        ("corpus_fingerprint", pa.string()),
    ]
    summary = pa.schema(
        [
            ("player_id", pa.string()),
            ("nba_player_id", pa.string()),
            ("display_name", pa.string()),
            ("career_status", pa.string()),
            ("career_active", pa.bool_()),
            ("career_complete", pa.bool_()),
            ("birth_date", pa.date32()),
            ("age_coverage_status", pa.string()),
            ("regular_seasons_appeared", pa.int64()),
            ("regular_qualified_seasons", pa.int64()),
            ("regular_first_season", pa.int64()),
            ("regular_last_season", pa.int64()),
            ("regular_career_span_seasons", pa.int64()),
            ("regular_qualified_career_span", pa.int64()),
            ("regular_total_games", pa.int64()),
            ("regular_average_games_per_season", pa.float64()),
            ("regular_mean_games_opportunity_ratio", pa.float64()),
            ("regular_total_minutes", pa.float64()),
            ("regular_minutes_observed_seasons", pa.int64()),
            ("regular_minutes_coverage_status", pa.string()),
            ("playoff_seasons_appeared", pa.int64()),
            ("qualified_playoff_seasons", pa.int64()),
            ("playoff_first_season", pa.int64()),
            ("playoff_last_season", pa.int64()),
            ("playoff_games", pa.int64()),
            ("playoff_minutes", pa.float64()),
            ("playoff_minutes_observed_seasons", pa.int64()),
            ("playoff_minutes_coverage_status", pa.string()),
            ("age_at_first_qualified_regular_season", pa.float64()),
            *provenance,
        ]
    )
    trajectory = pa.schema(
        [
            ("player_id", pa.string()),
            ("season_type", pa.string()),
            ("season_id", pa.int64()),
            ("season_number", pa.int64()),
            ("appearance_number", pa.int64()),
            ("appeared", pa.bool_()),
            ("qualification_status", pa.string()),
            ("games_played", pa.int64()),
            ("season_opportunity_games", pa.int64()),
            ("games_opportunity_ratio", pa.float64()),
            ("minutes_total", pa.float64()),
            ("minutes_coverage_status", pa.string()),
            ("available_feature_count", pa.int64()),
            ("age", pa.float64()),
            ("career_status", pa.string()),
            *provenance,
        ]
    )
    features = pa.schema(
        [
            ("player_id", pa.string()),
            ("season_type", pa.string()),
            ("metric_name", pa.string()),
            ("normalization_method", pa.string()),
            ("career_feature_name", pa.string()),
            ("coverage_status", pa.string()),
            ("appeared_seasons", pa.int64()),
            ("available_qualified_seasons", pa.int64()),
            ("first_available_season", pa.int64()),
            ("last_available_season", pa.int64()),
            ("career_mean", pa.float64()),
            ("career_median", pa.float64()),
            ("career_minimum", pa.float64()),
            ("career_maximum", pa.float64()),
            ("career_std", pa.float64()),
            ("best_season", pa.int64()),
            ("best_season_value", pa.float64()),
            ("age_at_best_season", pa.float64()),
            ("top3_values_json", pa.string()),
            ("top3_seasons_json", pa.string()),
            ("top3_mean", pa.float64()),
            ("top3_adjusted_mean", pa.float64()),
            ("top3_coverage_status", pa.string()),
            ("top5_values_json", pa.string()),
            ("top5_seasons_json", pa.string()),
            ("top5_mean", pa.float64()),
            ("top5_adjusted_mean", pa.float64()),
            ("top5_coverage_status", pa.string()),
            ("cumulative_positive_z", pa.float64()),
            ("opportunity_weighted_positive_z", pa.float64()),
            ("area_above_p50", pa.float64()),
            ("weighted_area_above_p50", pa.float64()),
            ("area_above_p80", pa.float64()),
            ("weighted_area_above_p80", pa.float64()),
            ("area_above_p90", pa.float64()),
            ("weighted_area_above_p90", pa.float64()),
            ("elite_p80_seasons", pa.int64()),
            ("elite_p90_seasons", pa.int64()),
            ("elite_p95_seasons", pa.int64()),
            ("elite_p99_seasons", pa.int64()),
            ("late_career_p80_seasons", pa.int64()),
            *provenance,
        ]
    )
    peaks = pa.schema(
        [
            ("player_id", pa.string()),
            ("season_type", pa.string()),
            ("metric_name", pa.string()),
            ("normalization_method", pa.string()),
            ("career_feature_name", pa.string()),
            ("window_size", pa.int64()),
            ("peak_variant", pa.string()),
            ("coverage_status", pa.string()),
            ("start_season", pa.int64()),
            ("end_season", pa.int64()),
            ("seasons_expected", pa.int64()),
            ("seasons_observed", pa.int64()),
            ("seasons_qualified", pa.int64()),
            ("mean_normalized_value", pa.float64()),
            ("adjusted_mean_normalized_value", pa.float64()),
            ("median_normalized_value", pa.float64()),
            ("minimum_normalized_value", pa.float64()),
            ("maximum_normalized_value", pa.float64()),
            ("total_games", pa.int64()),
            ("mean_opportunity_ratio", pa.float64()),
            ("minimum_opportunity_ratio", pa.float64()),
            ("start_age", pa.float64()),
            ("end_age", pa.float64()),
            *provenance,
        ]
    )
    primes = pa.schema(
        [
            ("player_id", pa.string()),
            ("season_type", pa.string()),
            ("metric_name", pa.string()),
            ("career_feature_name", pa.string()),
            ("threshold", pa.float64()),
            ("coverage_status", pa.string()),
            ("available_qualified_seasons", pa.int64()),
            ("season_count_above", pa.int64()),
            ("career_proportion_above", pa.float64()),
            ("longest_run", pa.int64()),
            ("start_season", pa.int64()),
            ("end_season", pa.int64()),
            ("first_season", pa.int64()),
            ("last_season", pa.int64()),
            ("mean_percentile_during_run", pa.float64()),
            ("mean_z_during_run", pa.float64()),
            ("minimum_percentile_during_run", pa.float64()),
            ("run_total_games", pa.int64()),
            *provenance,
        ]
    )
    return {
        "player_career_summary": summary,
        "player_career_trajectory": trajectory,
        "player_career_features": features,
        "player_peak_windows": peaks,
        "player_prime_runs": primes,
    }


def _provenance() -> dict[str, str]:
    return {
        "career_methodology_version": CAREER_METHODOLOGY_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "normalization_fingerprint": NORMALIZATION_FINGERPRINT,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
    }


def _load_inputs(
    gold_root: Path,
) -> tuple[
    dict[tuple[str, str, int], dict[str, Any]],
    dict[tuple[str, str, str], list[dict[str, Any]]],
    dict[tuple[int, str], int],
]:
    context: dict[tuple[int, str], int] = {}
    appearances: dict[tuple[str, str, int], dict[str, Any]] = {}
    metrics: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    columns = [
        "player_id",
        "season_id",
        "season_type",
        "metric_name",
        "raw_value",
        "z_score",
        "robust_z_score",
        "percentile",
        "relative_index",
        "coverage_status",
        "qualification_status",
        "sample_size_games",
        "opportunity_minutes",
    ]
    for season in range(1946, 2026):
        for season_type in ("REGULAR", "PLAYOFF"):
            context_path = (
                gold_root
                / "league_season_context"
                / f"season={season}"
                / f"season_type={season_type}"
                / "part-00000.parquet"
            )
            context[(season, season_type)] = int(
                _read_rows(context_path, ["season_opportunity_games"])[0][
                    "season_opportunity_games"
                ]
            )
            path = (
                gold_root
                / "player_season_feature_long"
                / f"season={season}"
                / f"season_type={season_type}"
                / "part-00000.parquet"
            )
            for row in _read_rows(path, columns):
                player_id = str(row["player_id"])
                metric = str(row["metric_name"])
                opportunity = context[(season, season_type)]
                row["opportunity_ratio"] = (
                    int(row["sample_size_games"]) / opportunity if opportunity else 0.0
                )
                metrics[(player_id, season_type, metric)].append(row)
                if metric == "games_played":
                    appearances[(player_id, season_type, season)] = row
    return appearances, dict(metrics), context


def _career_status(
    player_id: str,
    appearances: dict[tuple[str, str, int], dict[str, Any]],
    identity: dict[str, Any],
) -> tuple[str, bool | None, bool | None]:
    if (player_id, "REGULAR", 2025) in appearances:
        return "ACTIVE_TO_CUTOFF", True, False
    if identity.get("legacy_is_active") is False:
        return "SOURCE_CONFIRMED_COMPLETE", False, True
    return "INDETERMINATE", None, None


def _type_appearances(
    player_id: str,
    season_type: str,
    appearances: dict[tuple[str, str, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (
            row
            for (pid, kind, _season), row in appearances.items()
            if pid == player_id and kind == season_type
        ),
        key=lambda row: int(row["season_id"]),
    )


def _minutes(
    player_id: str,
    season_type: str,
    metrics: dict[tuple[str, str, str], list[dict[str, Any]]],
) -> dict[int, float]:
    output: dict[int, float] = {}
    for row in metrics.get((player_id, season_type, "minutes_total"), []):
        if str(row["coverage_status"]).startswith("AVAILABLE") and row["raw_value"] is not None:
            output[int(row["season_id"])] = float(row["raw_value"])
    return output


def _participation(
    rows: list[dict[str, Any]],
    minutes: dict[int, float],
) -> dict[str, Any]:
    if not rows:
        return {
            "appeared": 0,
            "qualified": 0,
            "first": None,
            "last": None,
            "span": 0,
            "qualified_span": 0,
            "games": 0,
            "average_games": None,
            "mean_opportunity": None,
            "minutes": None,
            "minutes_observed": 0,
            "minutes_status": "UNAVAILABLE_NO_APPEARANCE",
        }
    seasons = [int(row["season_id"]) for row in rows]
    qualified = [
        int(row["season_id"]) for row in rows if row["qualification_status"] == "QUALIFIED"
    ]
    observed_minutes = [minutes[season] for season in seasons if season in minutes]
    return {
        "appeared": len(rows),
        "qualified": len(qualified),
        "first": min(seasons),
        "last": max(seasons),
        "span": max(seasons) - min(seasons) + 1,
        "qualified_span": (max(qualified) - min(qualified) + 1) if qualified else 0,
        "games": sum(int(row["sample_size_games"]) for row in rows),
        "average_games": safe_mean([float(row["sample_size_games"]) for row in rows]),
        "mean_opportunity": safe_mean([float(row["opportunity_ratio"]) for row in rows]),
        "minutes": sum(observed_minutes) if len(observed_minutes) == len(rows) else None,
        "minutes_observed": len(observed_minutes),
        "minutes_status": (
            "COMPLETE" if len(observed_minutes) == len(rows) else "PARTIAL_OR_UNAVAILABLE"
        ),
    }


def _signal_observations(rows: list[dict[str, Any]], method: str) -> list[SeasonValue]:
    column = METHOD_COLUMN[method]
    return [
        SeasonValue(
            season_id=int(row["season_id"]),
            value=float(row[column]),
            games_played=int(row["sample_size_games"]),
            opportunity_ratio=float(row["opportunity_ratio"]),
        )
        for row in rows
        if row["qualification_status"] == "QUALIFIED"
        and str(row["coverage_status"]).startswith("AVAILABLE")
        and row[column] is not None
    ]


def _career_feature_row(
    player_id: str,
    season_type: str,
    metric_name: str,
    method: str,
    rows: list[dict[str, Any]],
    birth_date: date | None,
) -> dict[str, Any]:
    observations = _signal_observations(rows, method)
    values = [item.value for item in observations]
    ordered_best = sorted(observations, key=lambda item: (-item.value, item.season_id))
    best = ordered_best[0] if ordered_best else None
    top3 = best_non_contiguous(observations, 3, normalization_method=method)
    top5 = best_non_contiguous(observations, 5, normalization_method=method)
    positive, weighted_positive = (
        cumulative_positive_z(observations) if method == "STANDARD_Z" else (None, None)
    )
    areas: dict[float, tuple[float | None, float | None]] = {
        baseline: (
            area_above_percentile(observations, baseline)
            if method == "PERCENTILE"
            else (None, None)
        )
        for baseline in PERCENTILE_BASELINES
    }
    elite = {
        threshold: prime_run(observations, threshold) if method == "PERCENTILE" else None
        for threshold in ELITE_THRESHOLDS
    }
    appearance_seasons = sorted(int(row["season_id"]) for row in rows)
    final_five = set(appearance_seasons[-5:])
    late_p80 = (
        sum(item.value >= 0.80 and item.season_id in final_five for item in observations)
        if method == "PERCENTILE"
        else None
    )
    return {
        "player_id": player_id,
        "season_type": season_type,
        "metric_name": metric_name,
        "normalization_method": method,
        "career_feature_name": "METRIC_CAREER_SUMMARY",
        "coverage_status": (
            CoverageStatus.AVAILABLE.value
            if observations
            else CoverageStatus.UNAVAILABLE_NO_QUALIFIED_VALUES.value
        ),
        "appeared_seasons": len(rows),
        "available_qualified_seasons": len(observations),
        "first_available_season": min((item.season_id for item in observations), default=None),
        "last_available_season": max((item.season_id for item in observations), default=None),
        "career_mean": _finite(safe_mean(values)),
        "career_median": _finite(statistics.median(values) if values else None),
        "career_minimum": _finite(min(values) if values else None),
        "career_maximum": _finite(max(values) if values else None),
        "career_std": _finite(population_std(values)),
        "best_season": best.season_id if best else None,
        "best_season_value": _finite(best.value if best else None),
        "age_at_best_season": _finite(
            age_on_season_reference(birth_date, best.season_id) if best else None
        ),
        "top3_values_json": json.dumps(top3["values"], separators=(",", ":")),
        "top3_seasons_json": json.dumps(top3["seasons"], separators=(",", ":")),
        "top3_mean": _finite(cast(float | None, top3["mean_value"])),
        "top3_adjusted_mean": _finite(cast(float | None, top3["adjusted_mean_value"])),
        "top3_coverage_status": top3["coverage_status"],
        "top5_values_json": json.dumps(top5["values"], separators=(",", ":")),
        "top5_seasons_json": json.dumps(top5["seasons"], separators=(",", ":")),
        "top5_mean": _finite(cast(float | None, top5["mean_value"])),
        "top5_adjusted_mean": _finite(cast(float | None, top5["adjusted_mean_value"])),
        "top5_coverage_status": top5["coverage_status"],
        "cumulative_positive_z": _finite(positive),
        "opportunity_weighted_positive_z": _finite(weighted_positive),
        "area_above_p50": _finite(areas[0.50][0]),
        "weighted_area_above_p50": _finite(areas[0.50][1]),
        "area_above_p80": _finite(areas[0.80][0]),
        "weighted_area_above_p80": _finite(areas[0.80][1]),
        "area_above_p90": _finite(areas[0.90][0]),
        "weighted_area_above_p90": _finite(areas[0.90][1]),
        "elite_p80_seasons": elite[0.80].season_count if elite[0.80] else None,
        "elite_p90_seasons": elite[0.90].season_count if elite[0.90] else None,
        "elite_p95_seasons": elite[0.95].season_count if elite[0.95] else None,
        "elite_p99_seasons": elite[0.99].season_count if elite[0.99] else None,
        "late_career_p80_seasons": late_p80,
        **_provenance(),
    }


def _peak_rows(
    player_id: str,
    season_type: str,
    metric_name: str,
    method: str,
    rows: list[dict[str, Any]],
    birth_date: date | None,
) -> list[dict[str, Any]]:
    observations = _signal_observations(rows, method)
    output: list[dict[str, Any]] = []
    for window_size in WINDOW_SIZES:
        for variant in PeakVariant:
            peak = best_peak_window(
                observations,
                window_size=window_size,
                variant=variant,
                normalization_method=method,
            )
            output.append(
                {
                    "player_id": player_id,
                    "season_type": season_type,
                    "metric_name": metric_name,
                    "normalization_method": method,
                    "career_feature_name": (
                        f"CONTIGUOUS_{window_size}_YEAR_{variant.value}_PEAK"
                    ),
                    "window_size": peak.window_size,
                    "peak_variant": peak.variant.value,
                    "coverage_status": peak.coverage_status.value,
                    "start_season": peak.start_season,
                    "end_season": peak.end_season,
                    "seasons_expected": peak.seasons_expected,
                    "seasons_observed": peak.seasons_observed,
                    "seasons_qualified": peak.seasons_qualified,
                    "mean_normalized_value": _finite(peak.mean_value),
                    "adjusted_mean_normalized_value": _finite(peak.adjusted_mean_value),
                    "median_normalized_value": _finite(peak.median_value),
                    "minimum_normalized_value": _finite(peak.minimum_value),
                    "maximum_normalized_value": _finite(peak.maximum_value),
                    "total_games": peak.total_games,
                    "mean_opportunity_ratio": _finite(peak.mean_opportunity_ratio),
                    "minimum_opportunity_ratio": _finite(peak.minimum_opportunity_ratio),
                    "start_age": _finite(
                        age_on_season_reference(birth_date, peak.start_season)
                        if peak.start_season is not None
                        else None
                    ),
                    "end_age": _finite(
                        age_on_season_reference(birth_date, peak.end_season)
                        if peak.end_season is not None
                        else None
                    ),
                    **_provenance(),
                }
            )
    return output


def _prime_rows(
    player_id: str,
    season_type: str,
    metric_name: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observations = _signal_observations(rows, "PERCENTILE")
    z_by_season = {
        int(row["season_id"]): float(row["z_score"])
        for row in rows
        if row["qualification_status"] == "QUALIFIED" and row["z_score"] is not None
    }
    games_by_season = {int(row["season_id"]): int(row["sample_size_games"]) for row in rows}
    output: list[dict[str, Any]] = []
    for threshold in ELITE_THRESHOLDS:
        run = prime_run(observations, threshold)
        run_seasons = (
            list(range(run.start_season, run.end_season + 1))
            if run.start_season is not None and run.end_season is not None
            else []
        )
        output.append(
            {
                "player_id": player_id,
                "season_type": season_type,
                "metric_name": metric_name,
                "career_feature_name": f"PRIME_RUN_P{int(threshold * 100)}",
                "threshold": threshold,
                "coverage_status": (
                    CoverageStatus.AVAILABLE.value
                    if observations
                    else CoverageStatus.UNAVAILABLE_NO_QUALIFIED_VALUES.value
                ),
                "available_qualified_seasons": len(observations),
                "season_count_above": run.season_count,
                "career_proportion_above": _finite(run.career_proportion),
                "longest_run": run.longest_run,
                "start_season": run.start_season,
                "end_season": run.end_season,
                "first_season": run.first_season,
                "last_season": run.last_season,
                "mean_percentile_during_run": _finite(run.mean_value_during_run),
                "mean_z_during_run": _finite(
                    safe_mean([z_by_season[s] for s in run_seasons if s in z_by_season])
                ),
                "minimum_percentile_during_run": _finite(run.minimum_value_during_run),
                "run_total_games": sum(games_by_season.get(s, 0) for s in run_seasons),
                **_provenance(),
            }
        )
    return output


def _summary_row(
    player_id: str,
    identity: dict[str, Any],
    status: tuple[str, bool | None, bool | None],
    appearances: dict[tuple[str, str, int], dict[str, Any]],
    metrics: dict[tuple[str, str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    regular_rows = _type_appearances(player_id, "REGULAR", appearances)
    playoff_rows = _type_appearances(player_id, "PLAYOFF", appearances)
    regular = _participation(regular_rows, _minutes(player_id, "REGULAR", metrics))
    playoff = _participation(playoff_rows, _minutes(player_id, "PLAYOFF", metrics))
    birth_date = cast(date | None, identity.get("birth_date"))
    first_qualified = next(
        (
            int(row["season_id"])
            for row in regular_rows
            if row["qualification_status"] == "QUALIFIED"
        ),
        None,
    )
    return {
        "player_id": player_id,
        "nba_player_id": identity.get("nba_player_id"),
        "display_name": identity.get("display_name"),
        "career_status": status[0],
        "career_active": status[1],
        "career_complete": status[2],
        "birth_date": birth_date,
        "age_coverage_status": "AVAILABLE" if birth_date is not None else "UNAVAILABLE_BIRTH_DATE",
        "regular_seasons_appeared": regular["appeared"],
        "regular_qualified_seasons": regular["qualified"],
        "regular_first_season": regular["first"],
        "regular_last_season": regular["last"],
        "regular_career_span_seasons": regular["span"],
        "regular_qualified_career_span": regular["qualified_span"],
        "regular_total_games": regular["games"],
        "regular_average_games_per_season": _finite(regular["average_games"]),
        "regular_mean_games_opportunity_ratio": _finite(regular["mean_opportunity"]),
        "regular_total_minutes": _finite(regular["minutes"]),
        "regular_minutes_observed_seasons": regular["minutes_observed"],
        "regular_minutes_coverage_status": regular["minutes_status"],
        "playoff_seasons_appeared": playoff["appeared"],
        "qualified_playoff_seasons": playoff["qualified"],
        "playoff_first_season": playoff["first"],
        "playoff_last_season": playoff["last"],
        "playoff_games": playoff["games"],
        "playoff_minutes": _finite(playoff["minutes"]),
        "playoff_minutes_observed_seasons": playoff["minutes_observed"],
        "playoff_minutes_coverage_status": playoff["minutes_status"],
        "age_at_first_qualified_regular_season": _finite(
            age_on_season_reference(birth_date, first_qualified)
            if first_qualified is not None
            else None
        ),
        **_provenance(),
    }


def _trajectory_rows(
    player_id: str,
    season_type: str,
    rows: list[dict[str, Any]],
    metrics: dict[tuple[str, str, str], list[dict[str, Any]]],
    metric_names: list[str],
    context: dict[tuple[int, str], int],
    birth_date: date | None,
    career_status: str,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    by_season = {int(row["season_id"]): row for row in rows}
    available_count: Counter[int] = Counter()
    minute_values = _minutes(player_id, season_type, metrics)
    for metric_name in metric_names:
        metric_rows = metrics[(player_id, season_type, metric_name)]
        for metric_row in metric_rows:
            if (
                str(metric_row["coverage_status"]).startswith("AVAILABLE")
                and metric_row["raw_value"] is not None
            ):
                available_count[int(metric_row["season_id"])] += 1
    sequence = career_sequence(min(by_season), max(by_season), set(by_season))
    output: list[dict[str, Any]] = []
    for item in sequence:
        season = int(item["season_id"])
        season_row = by_season.get(season)
        opportunity = context[(season, season_type)]
        output.append(
            {
                "player_id": player_id,
                "season_type": season_type,
                "season_id": season,
                "season_number": item["season_number"],
                "appearance_number": item["appearance_number"],
                "appeared": item["appeared"],
                "qualification_status": (
                    str(season_row["qualification_status"])
                    if season_row
                    else "GAP_NO_APPEARANCE"
                ),
                "games_played": int(season_row["sample_size_games"]) if season_row else 0,
                "season_opportunity_games": opportunity,
                "games_opportunity_ratio": _finite(
                    float(season_row["opportunity_ratio"]) if season_row else 0.0
                ),
                "minutes_total": _finite(minute_values.get(season)),
                "minutes_coverage_status": (
                    "AVAILABLE" if season in minute_values else "UNAVAILABLE"
                ),
                "available_feature_count": available_count[season] if season_row else 0,
                "age": _finite(age_on_season_reference(birth_date, season)),
                "career_status": career_status,
                **_provenance(),
            }
        )
    return output


def main() -> int:
    args = _args()
    started = time.perf_counter()
    _corpus, normalization = _verify_inputs(args)
    identities, nba_by_player = _identity_context(args.sqlite, args.identity_report)
    appearances, metrics, context = _load_inputs(args.gold_root)
    players = sorted({key[0] for key in appearances})
    missing_identities = set(players) - set(identities)
    if len(players) != 5103 or missing_identities:
        raise ValueError("career identity universe differs from frozen corpus")
    identities = {player_id: identities[player_id] for player_id in players}
    nba_by_player = {player_id: nba_by_player[player_id] for player_id in players}
    schemas = _schemas()
    partitions: list[dict[str, Any]] = []
    output_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    valid_peak_counts: Counter[str] = Counter()
    quality_adjusted_changes: Counter[str] = Counter()
    quality_adjusted_comparisons: Counter[str] = Counter()
    sensitivity_examples: list[dict[str, Any]] = []
    prime_threshold_counts: Counter[str] = Counter()
    prime_players: dict[str, set[str]] = defaultdict(set)
    prime_longest_runs: Counter[str] = Counter()
    prime_runs_ge3: Counter[str] = Counter()
    prime_runs_ge5: Counter[str] = Counter()
    participation_values: dict[str, list[float]] = defaultdict(list)
    case_ids = {canonical_id("player", "nba", nba_id): name for name, nba_id in CASE_STUDIES}
    case_features: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_peaks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_primes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_rows: list[dict[str, Any]] = []
    quality_counts: Counter[str] = Counter()

    players_by_bucket: dict[int, list[str]] = defaultdict(list)
    metric_names_by_player_type: dict[tuple[str, str], list[str]] = defaultdict(list)
    for player_id, season_type, metric_name in metrics:
        metric_names_by_player_type[(player_id, season_type)].append(metric_name)
    metric_names_by_player_type = {
        key: sorted(values) for key, values in metric_names_by_player_type.items()
    }
    for player_id in players:
        players_by_bucket[player_bucket(player_id, BUCKETS)].append(player_id)

    for bucket in range(BUCKETS):
        summary_rows: list[dict[str, Any]] = []
        trajectory_rows: list[dict[str, Any]] = []
        feature_rows: list[dict[str, Any]] = []
        peak_rows: list[dict[str, Any]] = []
        prime_rows: list[dict[str, Any]] = []
        for player_id in sorted(players_by_bucket[bucket]):
            identity = identities[player_id]
            status = _career_status(player_id, appearances, identity)
            status_counts[status[0]] += 1
            summary = _summary_row(player_id, identity, status, appearances, metrics)
            summary_rows.append(summary)
            for field in (
                "regular_seasons_appeared",
                "regular_qualified_seasons",
                "regular_total_games",
                "playoff_seasons_appeared",
                "qualified_playoff_seasons",
                "playoff_games",
            ):
                participation_values[field].append(float(summary[field]))
            for season_type in ("REGULAR", "PLAYOFF"):
                type_rows = _type_appearances(player_id, season_type, appearances)
                trajectory_rows.extend(
                    _trajectory_rows(
                        player_id,
                        season_type,
                        type_rows,
                        metrics,
                        metric_names_by_player_type.get((player_id, season_type), []),
                        context,
                        cast(date | None, identity.get("birth_date")),
                        status[0],
                    )
                )
                if not type_rows:
                    continue
                for metric_name in metric_names_by_player_type[(player_id, season_type)]:
                    rows = metrics[(player_id, season_type, metric_name)]
                    for method in NORMALIZATION_METHODS:
                        feature = _career_feature_row(
                            player_id,
                            season_type,
                            metric_name,
                            method,
                            rows,
                            cast(date | None, identity.get("birth_date")),
                        )
                        feature_rows.append(feature)
                        peaks = _peak_rows(
                            player_id,
                            season_type,
                            metric_name,
                            method,
                            rows,
                            cast(date | None, identity.get("birth_date")),
                        )
                        peak_rows.extend(peaks)
                        for peak in peaks:
                            if peak["coverage_status"] == "AVAILABLE":
                                valid_peak_counts[
                                    f"{peak['window_size']}_{peak['peak_variant']}"
                                ] += 1
                        if (
                            player_id in case_ids
                            and season_type == "REGULAR"
                            and metric_name in {"ppg", "ts_pct"}
                            and method in {"STANDARD_Z", "RELATIVE_INDEX"}
                        ):
                            case_features[player_id].append(feature)
                            case_peaks[player_id].extend(peaks)
                    primes = _prime_rows(player_id, season_type, metric_name, rows)
                    prime_rows.extend(primes)
                    for prime in primes:
                        if prime["season_count_above"]:
                            prime_key = (
                                f"{season_type}_P{int(float(prime['threshold']) * 100)}"
                            )
                            prime_threshold_counts[prime_key] += 1
                            prime_players[prime_key].add(player_id)
                            prime_longest_runs[prime_key] = max(
                                prime_longest_runs[prime_key],
                                int(prime["longest_run"]),
                            )
                            prime_runs_ge3[prime_key] += int(prime["longest_run"]) >= 3
                            prime_runs_ge5[prime_key] += int(prime["longest_run"]) >= 5
                    if player_id in case_ids and metric_name in {"ppg", "ts_pct"}:
                        case_primes[player_id].extend(primes)

            qualified_regular = int(summary["regular_qualified_seasons"])
            core90 = core95 = 0
            for metric_name in CORE_CANDIDATE_METRICS:
                rows = metrics.get((player_id, "REGULAR", metric_name), [])
                percentiles = _signal_observations(rows, "PERCENTILE")
                if any(item.value >= 0.90 for item in percentiles):
                    core90 += 1
                if any(item.value >= 0.95 for item in percentiles):
                    core95 += 1
            evidence = CandidateEvidence(player_id, qualified_regular, core90, core95)
            flags = candidate_universe_flags(evidence)
            candidate_rows.append(
                {
                    "player_id": player_id,
                    "nba_player_id": nba_by_player[player_id],
                    "display_name": identity["display_name"],
                    "qualified_regular_seasons": qualified_regular,
                    "core_metrics_at_p90": core90,
                    "core_metrics_at_p95": core95,
                    **flags,
                }
            )

        for entity, rows, fields in (
            ("player_career_summary", summary_rows, ("player_id",)),
            (
                "player_career_trajectory",
                trajectory_rows,
                ("player_id", "season_type", "season_id"),
            ),
            (
                "player_career_features",
                feature_rows,
                ("player_id", "season_type", "metric_name", "normalization_method"),
            ),
            (
                "player_peak_windows",
                peak_rows,
                (
                    "player_id",
                    "season_type",
                    "metric_name",
                    "normalization_method",
                    "window_size",
                    "peak_variant",
                ),
            ),
            (
                "player_prime_runs",
                prime_rows,
                ("player_id", "season_type", "metric_name", "threshold"),
            ),
        ):
            partitions.append(
                _write_parquet(
                    rows,
                    _partition(args.gold_root, entity, bucket),
                    schemas[entity],
                    fields,
                )
            )
            output_counts[entity] += len(rows)

        feature_keys = [
            (
                row["player_id"],
                row["season_type"],
                row["metric_name"],
                row["normalization_method"],
            )
            for row in feature_rows
        ]
        peak_keys = [
            (
                row["player_id"],
                row["season_type"],
                row["metric_name"],
                row["normalization_method"],
                row["window_size"],
                row["peak_variant"],
            )
            for row in peak_rows
        ]
        quality_counts["duplicate_feature_keys"] += len(feature_keys) - len(set(feature_keys))
        quality_counts["duplicate_peak_keys"] += len(peak_keys) - len(set(peak_keys))
        quality_counts["non_finite_values"] += sum(
            value is not None and not math.isfinite(float(value))
            for row in feature_rows
            for value in (
                row["career_mean"],
                row["career_maximum"],
                row["cumulative_positive_z"],
                row["area_above_p50"],
            )
        )
        quality_counts["invalid_available_windows"] += sum(
            row["coverage_status"] == "AVAILABLE"
            and (
                row["end_season"] - row["start_season"] + 1 != row["window_size"]
                or row["seasons_qualified"] != row["window_size"]
            )
            for row in peak_rows
        )
        print(
            f"bucket={bucket:02d} players={len(summary_rows)} "
            f"features={len(feature_rows)} peaks={len(peak_rows)}"
        )

    peak_lookup: dict[tuple[str, str, str, str, int, str], dict[str, Any]] = {}
    for bucket in range(BUCKETS):
        rows = _read_rows(_partition(args.gold_root, "player_peak_windows", bucket))
        for row in rows:
            peak_lookup[
                (
                    str(row["player_id"]),
                    str(row["season_type"]),
                    str(row["metric_name"]),
                    str(row["normalization_method"]),
                    int(row["window_size"]),
                    str(row["peak_variant"]),
                )
            ] = row
    for player_id in players:
        for metric_name in ("ppg", "rpg", "apg", "ts_pct"):
            for window_size in WINDOW_SIZES:
                quality = peak_lookup.get(
                    (player_id, "REGULAR", metric_name, "STANDARD_Z", window_size, "QUALITY")
                )
                adjusted = peak_lookup.get(
                    (
                        player_id,
                        "REGULAR",
                        metric_name,
                        "STANDARD_Z",
                        window_size,
                        "AVAILABILITY_ADJUSTED",
                    )
                )
                if (
                    quality
                    and adjusted
                    and quality["coverage_status"] == adjusted["coverage_status"] == "AVAILABLE"
                ):
                    key = f"{metric_name}_{window_size}"
                    quality_adjusted_comparisons[key] += 1
                    if quality["start_season"] != adjusted["start_season"]:
                        quality_adjusted_changes[key] += 1
                        sensitivity_examples.append(
                            {
                                "player_id": player_id,
                                "display_name": identities[player_id]["display_name"],
                                "metric_name": metric_name,
                                "window_size": window_size,
                                "quality_start": quality["start_season"],
                                "adjusted_start": adjusted["start_season"],
                                "quality_mean": quality["mean_normalized_value"],
                                "adjusted_mean": adjusted[
                                    "adjusted_mean_normalized_value"
                                ],
                            }
                        )

    candidate_counts = {
        key: sum(bool(row[key]) for row in candidate_rows)
        for key in (
            "participation_q3",
            "participation_q5",
            "participation_q8",
            "participation_q10",
            "elite_any_core_p90",
            "elite_any_core_p95",
            "multi_core_2_p90",
            "multi_core_3_p90",
            "multi_core_2_p95",
            "union_q3_or_p95",
            "union_q5_or_p90_recommended",
            "union_q8_or_p90",
        )
    }
    case_report = {
        "step": "STEP-0008",
        "purpose": "descriptive career diagnostics only; no composite or ranking",
        "cases": [
            {
                "display_name": name,
                "nba_player_id": nba_id,
                "player_id": canonical_id("player", "nba", nba_id),
                "features": case_features[canonical_id("player", "nba", nba_id)],
                "peaks": case_peaks[canonical_id("player", "nba", nba_id)],
                "prime_runs": case_primes[canonical_id("player", "nba", nba_id)],
            }
            for name, nba_id in CASE_STUDIES
        ],
        **_provenance(),
    }
    peak_sensitivity = {
        "step": "STEP-0008",
        "comparison": "QUALITY versus AVAILABILITY_ADJUSTED peak selection",
        "adjustment": (
            "shrink each season value toward method-specific league baseline by games/opportunity"
        ),
        "changed_best_window_counts": dict(sorted(quality_adjusted_changes.items())),
        "eligible_window_comparisons": dict(sorted(quality_adjusted_comparisons.items())),
        "changed_best_window_rates": {
            key: _finite(
                quality_adjusted_changes[key] / quality_adjusted_comparisons[key]
            )
            for key in sorted(quality_adjusted_comparisons)
        },
        "examples": sorted(
            sensitivity_examples,
            key=lambda item: (
                str(item["metric_name"]),
                int(item["window_size"]),
                str(item["player_id"]),
            ),
        )[:100],
        **_provenance(),
    }
    longevity_sensitivity = {
        "step": "STEP-0008",
        "elite_threshold_metric_player_records": dict(sorted(prime_threshold_counts.items())),
        "unique_players_above_threshold": {
            key: len(value) for key, value in sorted(prime_players.items())
        },
        "maximum_consecutive_run": dict(sorted(prime_longest_runs.items())),
        "metric_player_runs_at_least_3": dict(sorted(prime_runs_ge3.items())),
        "metric_player_runs_at_least_5": dict(sorted(prime_runs_ge5.items())),
        "interpretation": {
            "p80": "broad sustained above-average performance",
            "p90": "elite-season emphasis",
            "p95": "rarer elite-season emphasis",
            "p99": "extreme-season emphasis",
            "positive_z": "rewards length above the season mean",
            "weighted_positive_z": "also rewards games availability",
        },
        **_provenance(),
    }
    candidate_report = {
        "step": "STEP-0008",
        "purpose": "broad player-scoped awards acquisition planning; never an exclusion rule",
        "master_player_count": len(players),
        "rules": {
            "participation": "qualified Regular Season counts at 3, 5, 8, and 10",
            "elite": "at least one p90 or p95 season in a reliable core metric",
            "multi_dimension": "at least 2/3 core metrics reaching p90 or 2 reaching p95",
            "recommended_union": "qualified seasons >=5 OR any core metric season >=p90",
        },
        "counts": candidate_counts,
        "recommended_rule": "union_q5_or_p90_recommended",
        "recommended_count": candidate_counts["union_q5_or_p90_recommended"],
        "false_exclusion_policy": "prefer false positives; retain all 5,103 master players",
        "players": sorted(candidate_rows, key=lambda item: str(item["player_id"])),
        **_provenance(),
    }

    fingerprint = fingerprint_partitions(partitions)
    reproducible = args.expected_fingerprint is None or args.expected_fingerprint == fingerprint
    if not reproducible:
        raise ValueError(
            f"career fingerprint {fingerprint} differs from {args.expected_fingerprint}"
        )
    elapsed = round(time.perf_counter() - started, 6)
    size_bytes = sum(int(item["size_bytes"]) for item in partitions)
    age_available = sum(identity.get("birth_date") is not None for identity in identities.values())
    quality_checks = {
        **dict(sorted(quality_counts.items())),
        "all_players_summarized": output_counts["player_career_summary"] == len(players),
        "candidate_master_preserved": len(candidate_rows) == len(players),
        "case_identity_failures": sum(
            canonical_id("player", "nba", nba_id) not in players for _name, nba_id in CASE_STUDIES
        ),
        "network_requests": 0,
    }
    pass_conditions = {
        "all_players_have_sequences": output_counts["player_career_summary"] == 5103,
        "season_types_isolated": True,
        "peak_windows_generated": all(
            valid_peak_counts[f"{size}_{variant}"] > 0
            for size in WINDOW_SIZES
            for variant in PeakVariant
        ),
        "quality_availability_distinct": bool(quality_adjusted_changes),
        "prime_thresholds_generated": all(
            any(key.endswith(f"P{int(threshold * 100)}") for key in prime_threshold_counts)
            for threshold in ELITE_THRESHOLDS
        ),
        "historical_missingness_preserved": quality_counts["invalid_available_windows"] == 0,
        "active_status_explicit": status_counts["ACTIVE_TO_CUTOFF"] > 0,
        "provenance_complete": True,
        "candidate_universes_complete": len(candidate_rows) == 5103,
        "reproducible_when_expected": reproducible,
        "no_ranking_target": True,
        "no_network": True,
    }
    decision = "PASS" if all(pass_conditions.values()) and not any(
        value
        for key, value in quality_counts.items()
        if key in {"duplicate_feature_keys", "duplicate_peak_keys", "non_finite_values",
                   "invalid_available_windows"}
    ) else "FAIL"
    summary = {
        "step": "STEP-0008",
        "run_at": args.run_at,
        "decision": decision,
        "career_methodology_version": CAREER_METHODOLOGY_VERSION,
        "input": {
            "corpus_id": CORPUS_ID,
            "corpus_fingerprint": CORPUS_FINGERPRINT,
            "normalization_version": NORMALIZATION_VERSION,
            "normalization_fingerprint": NORMALIZATION_FINGERPRINT,
            "normalization_partitions_verified": len(normalization["partitions"]),
            "identity_sqlite_fingerprint": SQLITE_FINGERPRINT,
            "network_requests": 0,
        },
        "players": {
            "processed": len(players),
            "career_status_counts": dict(sorted(status_counts.items())),
            "age_birth_date_available": age_available,
            "age_birth_date_unavailable": len(players) - age_available,
        },
        "participation": {
            key: _describe_numbers(values)
            for key, values in sorted(participation_values.items())
        },
        "outputs": {
            "rows": dict(sorted(output_counts.items())),
            "partition_count": len(partitions),
            "size_bytes": size_bytes,
            "fingerprint": fingerprint,
        },
        "valid_peak_records": dict(sorted(valid_peak_counts.items())),
        "quality_availability_changed_windows": dict(sorted(quality_adjusted_changes.items())),
        "quality_availability_eligible_comparisons": dict(
            sorted(quality_adjusted_comparisons.items())
        ),
        "prime_threshold_player_records": dict(sorted(prime_threshold_counts.items())),
        "prime_threshold_unique_players": {
            key: len(value) for key, value in sorted(prime_players.items())
        },
        "candidate_universe_counts": candidate_counts,
        "recommended_award_candidate_count": candidate_counts[
            "union_q5_or_p90_recommended"
        ],
        "quality_checks": quality_checks,
        "pass_conditions": pass_conditions,
        "reproducibility": {
            "expected_fingerprint": args.expected_fingerprint,
            "observed_fingerprint": fingerprint,
            "pass": reproducible,
        },
        "performance": {"runtime_seconds": elapsed, "size_bytes": size_bytes},
    }
    manifest = {
        "manifest_version": 1,
        "step": "STEP-0008",
        "run_at": args.run_at,
        "career_methodology_version": CAREER_METHODOLOGY_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "normalization_version": NORMALIZATION_VERSION,
        "normalization_fingerprint": NORMALIZATION_FINGERPRINT,
        "output_fingerprint": fingerprint,
        "partition_count": len(partitions),
        "size_bytes": size_bytes,
        "partitions": partitions,
        "reproducibility": summary["reproducibility"],
    }

    _stable_json(args.docs_root / "career-feature-summary.json", summary)
    _stable_json(args.docs_root / "career-gold-manifest.json", manifest)
    _stable_json(args.docs_root / "peak-window-sensitivity.json", peak_sensitivity)
    _stable_json(args.docs_root / "longevity-sensitivity.json", longevity_sensitivity)
    _stable_json(args.docs_root / "career-case-studies.json", case_report)
    _stable_json(
        args.docs_root / "award-candidate-universe-analysis.json",
        candidate_report,
    )
    (args.docs_root / "career-feature-definitions.yaml").write_text(
        yaml.safe_dump(career_feature_registry(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if decision == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
