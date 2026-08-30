#!/usr/bin/env python3
"""Build the frozen GOATLAB-HIST-V1 Bronze-to-Silver player-fact corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import sqlite3
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from goatlab.data.canonical import normalize_season_type, parse_season_label, utc_datetime
from goatlab.data.historical_corpus import (
    ADVANCED_START_YEAR,
    CORPUS_END_SEASON,
    CORPUS_END_YEAR,
    CORPUS_ID,
    SEASON_TYPES,
    AcquisitionScope,
    BackfillStatus,
    OutputPartitionStatus,
    acquisition_matrix,
    frozen_seasons,
    load_or_initialize_checkpoint,
    partition_fingerprint,
    reconciliation_summary,
    request_summary,
    set_output_status,
    update_request_checkpoint,
    write_atomic_json,
)
from goatlab.data.nba_api_client import (
    NBAAPIClient,
    RateLimiter,
    RequestResult,
    ResponseCache,
)
from goatlab.data.nba_api_probe import (
    INTRODUCTION_SEASON,
    map_player_season_advanced,
    rows_from_result,
)
from goatlab.data.player_fact_ingestion import (
    PLAYER_ADVANCED_SCHEMA,
    PLAYER_GAME_SCHEMA,
    PLAYER_SEASON_SCHEMA,
    CoverageThresholds,
    aggregate_player_seasons,
    build_team_crosswalk,
    empirical_metric_coverage,
    map_player_game_row,
    quality_gates,
    reconcile_base_totals,
    resolve_player_identities,
    write_deterministic_parquet,
)
from goatlab.schemas import PlayerGameStats, PlayerSeasonAdvanced

ROOT = Path(__file__).resolve().parents[2]
RUN_SOURCE_ID = "nba_api:1.11.4:historical-corpus-v1:step-0006"
METHODOLOGY_VERSION = "player-fact-qualification-v1"
SCHEMA_VERSION = "canonical-silver-v1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True, help="Frozen canonicalization timestamp")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--certify-cache-only", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=ROOT / "data/bronze/nba_api")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "data/bronze/nba_api/historical-corpus-v1-checkpoint.json",
    )
    parser.add_argument("--sqlite", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _cache_timestamp(cache_root: Path, result: RequestResult) -> str:
    path = cache_root / result.endpoint.lower() / f"{result.cache_key}.meta.json"
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _partition_path(root: Path, entity: str, season: str, season_type: str) -> Path:
    return (
        root
        / entity
        / f"season={parse_season_label(season)}"
        / f"season_type={normalize_season_type(season_type).value}"
        / "part-00000.parquet"
    )


def _relative_output(value: dict[str, Any]) -> dict[str, Any]:
    output = dict(value)
    output["path"] = _relative(Path(str(output["path"])))
    return output


def _legacy_context(
    sqlite_path: Path,
) -> tuple[
    set[str],
    set[str],
    set[str],
    dict[str, list[tuple[int, int | None]]],
    set[str],
]:
    connection = sqlite3.connect(sqlite_path)
    try:
        players = {str(row[0]) for row in connection.execute("SELECT id FROM player")}
        common = {
            str(row[0]) for row in connection.execute("SELECT person_id FROM common_player_info")
        }
        teams = {str(row[0]) for row in connection.execute("SELECT id FROM team")}
        windows: dict[str, list[tuple[int, int | None]]] = {}
        for team_id, start, end in connection.execute(
            "SELECT team_id, year_founded, year_active_till FROM team_history"
        ):
            windows.setdefault(str(team_id), []).append(
                (int(start), int(end) if end is not None else None)
            )
            teams.add(str(team_id))
        games = {str(row[0]) for row in connection.execute("SELECT DISTINCT game_id FROM game")}
    finally:
        connection.close()
    return players, common, teams, windows, games


def _load_result(cache: ResponseCache, scope: AcquisitionScope) -> RequestResult:
    result = cache.load(scope.request_spec())
    if result is None:
        raise RuntimeError(f"missing successful cache entry after acquisition: {scope.scope_id}")
    return result


def _selected_bronze_size(cache_root: Path, checkpoint: dict[str, Any]) -> dict[str, int]:
    payload = metadata_bytes = 0
    files = 0
    for item in checkpoint["requests"].values():
        key = item["cache_key"]
        if not key:
            continue
        directory = cache_root / str(item["endpoint"]).lower()
        raw = directory / f"{key}.json"
        meta = directory / f"{key}.meta.json"
        if raw.is_file():
            payload += raw.stat().st_size
            files += 1
        if meta.is_file():
            metadata_bytes += meta.stat().st_size
            files += 1
    return {
        "files": files,
        "payload_bytes": payload,
        "metadata_bytes": metadata_bytes,
        "total_bytes": payload + metadata_bytes,
    }


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _acquire(
    args: argparse.Namespace,
    checkpoint: dict[str, Any],
    cache: ResponseCache,
) -> dict[str, Any]:
    client = NBAAPIClient(
        cache,
        timeout_seconds=30.0,
        max_attempts=3,
        rate_limiter=RateLimiter(1.0),
        rng=random.Random(6006),
    )
    scopes = acquisition_matrix()
    network_requests = cache_hits = retries = 0
    network_response_seconds = 0.0
    run_started = _iso_now()
    monotonic_started = time.perf_counter()
    if args.allow_network and checkpoint["retrieval_started_utc"] is None:
        checkpoint["retrieval_started_utc"] = run_started
        write_atomic_json(args.checkpoint, checkpoint)

    for index, scope in enumerate(scopes, start=1):
        spec = scope.request_spec()
        result = cache.load(spec)
        if result is None:
            if not args.allow_network:
                raise RuntimeError(f"cache-only build is missing {scope.scope_id}")
            result = client.execute(spec)
            network_requests += 1
            retries += result.retry_count
            network_response_seconds += result.elapsed_seconds
        else:
            cache_hits += 1
        rows = rows_from_result(result)
        update_request_checkpoint(
            checkpoint,
            scope,
            result,
            row_count=len(rows),
            retrieval_timestamp=_cache_timestamp(args.cache_root, result),
        )
        write_atomic_json(args.checkpoint, checkpoint)
        print(
            f"[{index:03d}/{len(scopes)}] {scope.endpoint} "
            f"{scope.measure_type or 'PlayerGame'} {scope.season} {scope.season_type}: "
            f"{result.outcome.value} rows={len(rows)} cache={result.from_cache}"
        )

    failures = [
        item
        for item in checkpoint["requests"].values()
        if item["request_status"]
        not in {BackfillStatus.SUCCESS_WITH_ROWS.value, BackfillStatus.SUCCESS_EMPTY.value}
    ]
    if failures:
        raise RuntimeError(f"{len(failures)} acquisition scopes remain failed")
    if args.allow_network:
        checkpoint["retrieval_completed_utc"] = _iso_now()
    elapsed = round(time.perf_counter() - monotonic_started, 6)
    return {
        "run_started_utc": run_started,
        "run_completed_utc": _iso_now(),
        "wall_seconds": elapsed,
        "network_requests_made": network_requests,
        "cache_hits": cache_hits,
        "network_response_seconds": round(network_response_seconds, 6),
        "network_retries": retries,
        "all_requests_from_cache": network_requests == 0,
    }


def _identity_and_team_observations(
    cache: ResponseCache,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    identity: dict[tuple[str, str], dict[str, Any]] = {}
    teams: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    source_rows = 0
    for scope in acquisition_matrix():
        if scope.endpoint != "playergamelogs":
            continue
        rows = rows_from_result(_load_result(cache, scope))
        source_rows += len(rows)
        for row in rows:
            player_id = str(row.get("PLAYER_ID") or "")
            player_name = str(row.get("PLAYER_NAME") or "")
            identity[(player_id, player_name)] = {
                "PLAYER_ID": row.get("PLAYER_ID"),
                "PLAYER_NAME": row.get("PLAYER_NAME"),
            }
            team_id = str(row.get("TEAM_ID") or "")
            team_name = str(row.get("TEAM_NAME") or "")
            abbreviation = str(row.get("TEAM_ABBREVIATION") or "")
            teams[(team_id, team_name, scope.season, abbreviation)] = {
                "TEAM_ID": row.get("TEAM_ID"),
                "TEAM_NAME": row.get("TEAM_NAME"),
                "TEAM_ABBREVIATION": row.get("TEAM_ABBREVIATION"),
                "SEASON_YEAR": scope.season,
            }
    return list(identity.values()), list(teams.values()), source_rows


def _source_introduction_anomalies(
    rows: list[dict[str, Any]], season: str, season_type: str
) -> list[dict[str, Any]]:
    year = parse_season_label(season)
    output: list[dict[str, Any]] = []
    for field, introduced in sorted(INTRODUCTION_SEASON.items()):
        if year >= introduced:
            continue
        non_null = sum(row.get(field) is not None for row in rows)
        if non_null:
            output.append(
                {
                    "category": "SOURCE_ANOMALY",
                    "season": season,
                    "season_type": normalize_season_type(season_type).value,
                    "source_field": field,
                    "documented_introduction_season": introduced,
                    "pre_introduction_non_null_rows": non_null,
                    "source_rows": len(rows),
                    "resolution": "canonical mapping forced values to NULL",
                }
            )
    return output


def _report_hashes(paths: list[Path]) -> dict[str, str]:
    return {
        _relative(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)
    }


def main() -> None:
    args = _args()
    if args.allow_network and args.certify_cache_only:
        raise ValueError("network acquisition and cache-only certification are mutually exclusive")
    run_at = utc_datetime(args.run_at)
    total_started = time.perf_counter()
    checkpoint = load_or_initialize_checkpoint(args.checkpoint)
    cache = ResponseCache(args.cache_root)
    acquisition_performance = _acquire(args, checkpoint, cache)
    write_atomic_json(args.checkpoint, checkpoint)

    legacy_players, common_players, legacy_teams, legacy_windows, legacy_games = _legacy_context(
        args.sqlite
    )
    identity_rows, team_rows, total_source_player_game_rows = _identity_and_team_observations(cache)
    identities, identity_report = resolve_player_identities(
        identity_rows, legacy_players, source_id=RUN_SOURCE_ID
    )
    teams, team_report = build_team_crosswalk(
        team_rows, legacy_teams, legacy_windows, source_id=RUN_SOURCE_ID
    )

    prior_identity = json.loads(
        (args.docs_root / "player-identity-reconciliation.json").read_text(encoding="utf-8")
    )
    prior_team = json.loads(
        (args.docs_root / "team-crosswalk-report.json").read_text(encoding="utf-8")
    )
    prior_provisional = {
        str(item["nba_player_id"]): str(item["player_id"])
        for item in prior_identity["provisional_identities"]
    }
    identity_id_conflicts = [
        nba_id
        for nba_id, player_id in prior_provisional.items()
        if nba_id in identities and identities[nba_id].player_id != player_id
    ]
    prior_team_ids = {
        (str(item["nba_team_id"]), str(item["team_name"])): str(item["team_id"])
        for item in prior_team["crosswalk"]
    }
    team_id_conflicts = [
        list(key)
        for key, team_id in prior_team_ids.items()
        if key in teams and teams[key].team_id != team_id
    ]

    official_only = [
        item for item in identities.values() if item.nba_player_id not in legacy_players
    ]
    identity_report.update(
        {
            "schema_version": 1,
            "step": "STEP-0006",
            "corpus_id": CORPUS_ID,
            "run_at": args.run_at,
            "source_rows": total_source_player_game_rows,
            "common_player_info_matches": len(set(identities) & common_players),
            "official_source_only_identities": len(official_only),
            "provisional_identities": len(official_only),
            "official_source_only_records": [
                {
                    "nba_player_id": item.nba_player_id,
                    "player_id": item.player_id,
                    "diagnostic_name": item.diagnostic_name,
                    "source_id": item.source_id,
                }
                for item in official_only
            ],
            "step_0005_canonical_ids_checked": len(prior_provisional),
            "step_0005_canonical_id_conflicts": identity_id_conflicts,
        }
    )
    team_report.update(
        {
            "schema_version": 1,
            "step": "STEP-0006",
            "corpus_id": CORPUS_ID,
            "run_at": args.run_at,
            "canonical_team_identities": len({item.team_id for item in teams.values()}),
            "franchise_relationships": len({item.franchise_id for item in teams.values()}),
            "official_only_historical_clubs": len(team_report["unmatched_team_ids"]),
            "step_0005_versions_checked": len(prior_team_ids),
            "step_0005_canonical_id_conflicts": team_id_conflicts,
        }
    )
    for item in team_report["crosswalk"]:
        item["valid_from_year_observed"] = item.pop("first_pilot_season")
        item["valid_to_year_observed"] = item.pop("last_pilot_season")

    thresholds = CoverageThresholds()
    coverage_matrix: list[dict[str, Any]] = []
    quality_partitions: list[dict[str, Any]] = []
    source_introduction_anomalies: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    partitions: list[dict[str, Any]] = []
    reconciliations: dict[str, Any] = {}
    official_game_ids: set[str] = set()
    silver_game_rows = season_rows = team_season_rows = total_season_rows = 0
    advanced_rows_total = 0
    duplicate_total_rows = 0
    reconciliation_seconds = 0.0
    transformation_started = time.perf_counter()

    for season in frozen_seasons():
        for season_type in SEASON_TYPES:
            pgl_scope = AcquisitionScope("playergamelogs", season, season_type)
            pgl_result = _load_result(cache, pgl_scope)
            raw_rows = [{**row, "SEASON_YEAR": season} for row in rows_from_result(pgl_result)]
            source_introduction_anomalies.extend(
                _source_introduction_anomalies(raw_rows, season, season_type)
            )
            official_game_ids.update(str(row["GAME_ID"]) for row in raw_rows)
            mapped: list[PlayerGameStats] = []
            for row_number, row in enumerate(raw_rows):
                try:
                    mapped.append(
                        map_player_game_row(
                            row,
                            pgl_result,
                            identities,
                            teams,
                            season=season,
                            season_type=season_type,
                            updated_at=run_at,
                        )
                    )
                except (KeyError, TypeError, ValueError) as error:
                    message = str(error)
                    quarantine.append(
                        {
                            "category": (
                                "PIPELINE_ERROR" if "unresolved" in message else "SOURCE_ANOMALY"
                            ),
                            "entity": "player_game_stats",
                            "season": season,
                            "season_type": normalize_season_type(season_type).value,
                            "source_row_number": row_number,
                            "error": message,
                            "nba_player_id": row.get("PLAYER_ID"),
                            "nba_game_id": row.get("GAME_ID"),
                            "nba_team_id": row.get("TEAM_ID"),
                            "source_values": {
                                field: row.get(field)
                                for field in (
                                    "MIN",
                                    "FGM",
                                    "FGA",
                                    "FG3M",
                                    "FG3A",
                                    "FTM",
                                    "FTA",
                                    "PTS",
                                )
                            },
                        }
                    )
            coverage = empirical_metric_coverage(
                mapped,
                season=season,
                season_type=season_type,
                thresholds=thresholds,
            )
            for item in coverage:
                item["source_row_count"] = len(raw_rows)
                item["accepted_silver_row_count"] = len(mapped)
            coverage_matrix.extend(coverage)
            quality_partitions.append(
                quality_gates(
                    raw_rows,
                    mapped,
                    identities,
                    teams,
                    coverage,
                    season=season,
                    season_type=season_type,
                )
            )
            aggregates = aggregate_player_seasons(mapped, coverage, updated_at=run_at)
            total_keys = [
                (row.player_id, row.season_id, row.season_type)
                for row in aggregates
                if row.row_scope.value == "TOTAL"
            ]
            duplicate_total_rows += sum(
                count - 1 for count in Counter(total_keys).values() if count > 1
            )
            silver_game_rows += len(mapped)
            season_rows += len(aggregates)
            team_season_rows += sum(row.row_scope.value == "TEAM" for row in aggregates)
            total_season_rows += sum(row.row_scope.value == "TOTAL" for row in aggregates)

            game_path = _partition_path(args.silver_root, "player_game_stats", season, season_type)
            season_path = _partition_path(
                args.silver_root, "player_season_stats", season, season_type
            )
            game_output = _relative_output(
                write_deterministic_parquet(
                    mapped,
                    game_path,
                    PLAYER_GAME_SCHEMA,
                    sort_fields=("game_id", "player_id", "team_id"),
                )
            )
            season_output = _relative_output(
                write_deterministic_parquet(
                    aggregates,
                    season_path,
                    PLAYER_SEASON_SCHEMA,
                    sort_fields=("player_id", "row_scope", "team_id"),
                )
            )
            partitions.extend((game_output, season_output))
            set_output_status(
                checkpoint,
                pgl_scope,
                OutputPartitionStatus.WRITTEN,
                (game_output["path"], season_output["path"]),
            )

            if parse_season_label(season) >= ADVANCED_START_YEAR:
                base_scope = AcquisitionScope(
                    "leaguedashplayerstats",
                    season,
                    season_type,
                    measure_type="Base",
                    per_mode="Totals",
                )
                base_result = _load_result(cache, base_scope)
                reconciliation_started = time.perf_counter()
                reconciliations[f"{season}:{normalize_season_type(season_type).value}"] = (
                    reconcile_base_totals(aggregates, rows_from_result(base_result))
                )
                reconciliation_seconds += time.perf_counter() - reconciliation_started
                set_output_status(checkpoint, base_scope, OutputPartitionStatus.RECONCILED)

                advanced_scope = AcquisitionScope(
                    "leaguedashplayerstats",
                    season,
                    season_type,
                    measure_type="Advanced",
                    per_mode="Totals",
                )
                advanced_result = _load_result(cache, advanced_scope)
                advanced: list[PlayerSeasonAdvanced] = []
                for row_number, row in enumerate(rows_from_result(advanced_result)):
                    try:
                        advanced.append(
                            map_player_season_advanced(
                                row,
                                advanced_result,
                                season=season,
                                season_type=season_type,
                                updated_at=run_at,
                            )
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        quarantine.append(
                            {
                                "category": "SOURCE_ANOMALY",
                                "entity": "player_season_advanced",
                                "season": season,
                                "season_type": normalize_season_type(season_type).value,
                                "source_row_number": row_number,
                                "error": str(error),
                                "nba_player_id": row.get("PLAYER_ID"),
                            }
                        )
                advanced_path = _partition_path(
                    args.silver_root, "player_season_advanced", season, season_type
                )
                advanced_output = _relative_output(
                    write_deterministic_parquet(
                        advanced,
                        advanced_path,
                        PLAYER_ADVANCED_SCHEMA,
                        sort_fields=("player_id", "row_scope", "team_id"),
                    )
                )
                partitions.append(advanced_output)
                advanced_rows_total += len(advanced)
                set_output_status(
                    checkpoint,
                    advanced_scope,
                    OutputPartitionStatus.WRITTEN,
                    (advanced_output["path"],),
                )
            write_atomic_json(args.checkpoint, checkpoint)

    transformation_seconds = round(time.perf_counter() - transformation_started, 6)
    reconciliation_seconds = round(reconciliation_seconds, 6)
    partitions.sort(key=lambda item: str(item["path"]))
    corpus_fingerprint = partition_fingerprint(partitions)
    recon_summary = reconciliation_summary(reconciliations)
    coverage_counts = Counter(item["classification"] for item in coverage_matrix)
    coverage_summary = {
        "records": len(coverage_matrix),
        "classification_counts": dict(sorted(coverage_counts.items())),
        "thresholds": {
            "RELIABLE": "non-null percentage >= 0.99",
            "PARTIAL": "0.80 <= non-null percentage < 0.99",
            "SPARSE": "0 < non-null percentage < 0.80",
            "UNAVAILABLE": "documented historical unavailability or unsupported source field",
            "UNKNOWN": "no rows or no observations despite conceptual availability",
        },
    }
    quality_fields = (
        "duplicate_player_game_keys",
        "orphan_player_ids",
        "orphan_team_ids",
        "orphan_game_ids",
        "negative_box_score_counts",
        "impossible_shooting_relationships",
        "rebound_inconsistencies_under_reliable_coverage",
        "game_dates_outside_expected_window",
        "null_to_zero_violations",
        "missing_source_provenance",
    )
    quality_totals = {
        field: sum(int(item[field]) for item in quality_partitions) for field in quality_fields
    }
    quality_totals["duplicate_total_season_rows"] = duplicate_total_rows
    quality_totals["pipeline_error_quarantine_rows"] = sum(
        item["category"] == "PIPELINE_ERROR" for item in quarantine
    )
    quality_totals["source_anomaly_quarantine_rows"] = sum(
        item["category"] == "SOURCE_ANOMALY" for item in quarantine
    )

    bronze_sizes = _selected_bronze_size(args.cache_root, checkpoint)
    request_counts = request_summary(checkpoint)
    source_rows = {
        "player_game_rows": sum(
            int(item["row_count"] or 0)
            for item in checkpoint["requests"].values()
            if item["endpoint"] == "playergamelogs"
        ),
        "base_rows": sum(
            int(item["row_count"] or 0)
            for item in checkpoint["requests"].values()
            if item["measure_type"] == "Base"
        ),
        "advanced_rows": sum(
            int(item["row_count"] or 0)
            for item in checkpoint["requests"].values()
            if item["measure_type"] == "Advanced"
        ),
    }
    silver_size = sum(int(item["size_bytes"]) for item in partitions)
    output_statuses = Counter(
        item["output_partition_status"] for item in checkpoint["requests"].values()
    )
    systematic_fields = [
        field
        for field, mismatches in recon_summary["mismatches_by_field"].items()
        if mismatches
        and (
            mismatches
            / max(
                1,
                sum(
                    int(partition["fields"][field]["compared"])
                    for partition in reconciliations.values()
                ),
            )
            >= 0.01
            or sum(
                int(partition["fields"][field]["mismatches"]) > 0
                for partition in reconciliations.values()
            )
            >= 3
        )
    ]

    if args.allow_network and checkpoint["network_build_performance"] is None:
        checkpoint["network_build_performance"] = {
            **acquisition_performance,
            "transformation_seconds": transformation_seconds,
            "reconciliation_seconds": reconciliation_seconds,
            "total_build_seconds": round(time.perf_counter() - total_started, 6),
            "peak_rss_bytes": _peak_rss_bytes(),
            "selected_bronze_bytes": bronze_sizes["total_bytes"],
            "full_cache_bytes": _tree_size(args.cache_root),
            "silver_bytes": silver_size,
        }

    expected_manifest_path = args.docs_root / "historical-corpus-v1-manifest.json"
    if args.certify_cache_only:
        if not expected_manifest_path.is_file():
            raise RuntimeError("cache-only certification requires a prior network-built manifest")
        expected = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        expected_partitions = {
            str(item["path"]): str(item["sha256"]) for item in expected["silver_partitions"]
        }
        observed_partitions = {str(item["path"]): str(item["sha256"]) for item in partitions}
        mismatched = sorted(
            path
            for path in set(expected_partitions) | set(observed_partitions)
            if expected_partitions.get(path) != observed_partitions.get(path)
        )
        checkpoint["cache_only_reproducibility"] = {
            "certified_at": args.run_at,
            "network_requests_made": acquisition_performance["network_requests_made"],
            "all_requests_from_cache": acquisition_performance["all_requests_from_cache"],
            "expected_corpus_fingerprint": expected["corpus_fingerprint"],
            "observed_corpus_fingerprint": corpus_fingerprint,
            "expected_partitions": len(expected_partitions),
            "observed_partitions": len(observed_partitions),
            "mismatched_partitions": mismatched,
            "pass": (
                acquisition_performance["network_requests_made"] == 0
                and expected["corpus_fingerprint"] == corpus_fingerprint
                and not mismatched
            ),
        }

    reproducibility = checkpoint["cache_only_reproducibility"]
    pass_conditions = {
        "all_intended_scopes_accounted_for": request_counts["total"] == 280,
        "no_uncontrolled_api_failures": request_counts["failed"] == 0,
        "player_identities_resolved": identity_report["unresolved"] == 0,
        "teams_resolved": team_report["unresolved"] == 0,
        "player_game_keys_unique": quality_totals["duplicate_player_game_keys"] == 0,
        "historical_null_semantics_preserved": quality_totals["null_to_zero_violations"] == 0,
        "full_season_aggregation_complete": (
            season_rows > 0 and output_statuses[OutputPartitionStatus.WRITTEN.value] == 220
        ),
        "base_reconciliation_no_systematic_mismatch": (
            recon_summary["partitions"] == 60
            and recon_summary["partitions_passing_v1_gate"] == 60
            and not systematic_fields
        ),
        "advanced_partitions_complete": advanced_rows_total > 0
        and sum("player_season_advanced" in str(item["path"]) for item in partitions) == 60,
        "metric_coverage_complete": len(coverage_matrix) == 160 * 19,
        "quarantine_accounted": all(item.get("category") for item in quarantine),
        "cache_only_reproducible": bool(reproducibility and reproducibility["pass"]),
        "frozen_cutoff_enforced": (
            frozen_seasons()[-1] == CORPUS_END_SEASON
            and all(
                parse_season_label(scope.season) <= CORPUS_END_YEAR
                for scope in acquisition_matrix()
            )
        ),
        "no_pipeline_error_quarantine": quality_totals["pipeline_error_quarantine_rows"] == 0,
    }
    decision = "PASS" if all(pass_conditions.values()) else "PARTIAL PASS"

    full_identity = dict(identity_report)
    full_team = dict(team_report)
    coverage_report = {
        "schema_version": 1,
        "step": "STEP-0006",
        "corpus_id": CORPUS_ID,
        "run_at": args.run_at,
        "methodology_version": METHODOLOGY_VERSION,
        "observed_zero_denominator": "non-null observations",
        "summary": coverage_summary,
        "matrix": coverage_matrix,
    }
    base_report = {
        "schema_version": 1,
        "step": "STEP-0006",
        "corpus_id": CORPUS_ID,
        "run_at": args.run_at,
        "systematic_mismatch_rule": (
            "block when a field mismatch rate is at least 1% or appears in at least 3 partitions"
        ),
        "systematic_mismatch_fields": systematic_fields,
        "summary": recon_summary,
        "partitions": reconciliations,
    }
    quality_report = {
        "schema_version": 1,
        "step": "STEP-0006",
        "corpus_id": CORPUS_ID,
        "run_at": args.run_at,
        "totals": quality_totals,
        "source_anomaly_definition": "contradictory or historically implausible upstream fact",
        "pipeline_error_definition": (
            "identity, mapping, schema, or integrity failure introduced locally"
        ),
        "source_introduction_anomalies": source_introduction_anomalies,
        "quarantine": quarantine,
        "partitions": quality_partitions,
    }
    summary = {
        "schema_version": 1,
        "step": "STEP-0006",
        "corpus_id": CORPUS_ID,
        "run_at": args.run_at,
        "decision": decision,
        "pass_conditions": pass_conditions,
        "season_start": frozen_seasons()[0],
        "season_end": frozen_seasons()[-1],
        "season_count": len(frozen_seasons()),
        "season_types": list(SEASON_TYPES),
        "requests": request_counts,
        "acquisition_performance": checkpoint["network_build_performance"],
        "bronze": {**source_rows, **bronze_sizes},
        "silver": {
            "player_game_rows": silver_game_rows,
            "player_season_rows": season_rows,
            "player_season_team_rows": team_season_rows,
            "player_season_total_rows": total_season_rows,
            "advanced_rows": advanced_rows_total,
            "partition_files": len(partitions),
            "size_bytes": silver_size,
            "corpus_fingerprint": corpus_fingerprint,
        },
        "identity": {
            "distinct_player_ids": identity_report["distinct_player_ids"],
            "legacy_matches": identity_report["legacy_matches"],
            "official_source_only": identity_report["official_source_only_identities"],
            "provisional": identity_report["provisional_identities"],
            "unresolved": identity_report["unresolved"],
        },
        "teams": {
            "distinct_official_team_ids": team_report["distinct_source_team_ids"],
            "canonical_team_identities": team_report["canonical_team_identities"],
            "historical_name_versions": team_report["canonical_team_versions"],
            "legacy_matches": team_report["legacy_id_matches"],
            "official_only_historical_clubs": team_report["official_only_historical_clubs"],
            "conflicts": len(team_report["stale_window_conflicts"]),
            "unresolved": team_report["unresolved"],
        },
        "games": {
            "distinct_official_game_ids": len(official_game_ids),
            "legacy_matches": len(official_game_ids & legacy_games),
            "official_only": len(official_game_ids - legacy_games),
        },
        "base_reconciliation": recon_summary,
        "coverage": coverage_summary,
        "quality": quality_totals,
        "quarantined_rows": len(quarantine),
        "reproducibility": reproducibility,
    }
    corpus_manifest = {
        "manifest_version": 1,
        "corpus_id": CORPUS_ID,
        "corpus_name": "GOAT Lab frozen historical player-fact corpus",
        "historical_corpus_end_season": CORPUS_END_SEASON,
        "season_start": frozen_seasons()[0],
        "season_end": frozen_seasons()[-1],
        "season_count": len(frozen_seasons()),
        "included_season_types": ["REGULAR", "PLAYOFF"],
        "future_seasons_excluded": True,
        "schema_version": SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "source_versions": {
            "nba_api": metadata.version("nba_api"),
            "nbadb": "4.0.0@48abd9825ed6933b57dbac3f50f058523367b1f5",
            "legacy_kaggle_dataset": "wyattowalsh/basketball:v238",
        },
        "retrieval_started_utc": checkpoint["retrieval_started_utc"],
        "retrieval_completed_utc": checkpoint["retrieval_completed_utc"],
        "canonicalized_at": args.run_at,
        "requests": request_counts,
        "source_rows": source_rows,
        "silver_rows": {
            "player_game_stats": silver_game_rows,
            "player_season_stats": season_rows,
            "player_season_advanced": advanced_rows_total,
        },
        "distinct_players": identity_report["distinct_player_ids"],
        "distinct_teams": team_report["distinct_source_team_ids"],
        "historical_team_versions": team_report["canonical_team_versions"],
        "distinct_games": len(official_game_ids),
        "quarantined_rows": len(quarantine),
        "coverage_summary": coverage_summary,
        "corpus_fingerprint": corpus_fingerprint,
        "reproducibility": reproducibility,
        "silver_partitions": partitions,
    }

    report_values = {
        args.docs_root / "full-identity-reconciliation.json": full_identity,
        args.docs_root / "full-team-crosswalk.json": full_team,
        args.docs_root / "full-metric-coverage.json": coverage_report,
        args.docs_root / "full-base-reconciliation.json": base_report,
        args.docs_root / "full-data-quality-report.json": quality_report,
        args.docs_root / "full-backfill-summary.json": summary,
        expected_manifest_path: corpus_manifest,
    }
    for path, value in report_values.items():
        write_atomic_json(path, value)
    report_hashes = _report_hashes(list(report_values))
    checkpoint["last_derived_report_hashes"] = report_hashes
    write_atomic_json(args.checkpoint, checkpoint)
    print(
        json.dumps(
            {
                "decision": decision,
                "corpus_id": CORPUS_ID,
                "requests": request_counts,
                "source_rows": source_rows,
                "silver": summary["silver"],
                "quality": quality_totals,
                "reproducibility": reproducibility,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
