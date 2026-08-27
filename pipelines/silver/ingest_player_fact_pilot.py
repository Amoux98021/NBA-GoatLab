#!/usr/bin/env python3
"""Execute the bounded STEP-0005 Bronze-to-Silver player-fact pilot."""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from goatlab.data.canonical import normalize_season_type, parse_season_label, utc_datetime
from goatlab.data.nba_api_client import NBAAPIClient, RequestOutcome, ResponseCache
from goatlab.data.nba_api_probe import (
    league_dash_player_stats_spec,
    map_player_season_advanced,
    player_game_logs_spec,
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
    normalized_bronze_artifact,
    quality_gates,
    reconcile_base_totals,
    resolve_player_identities,
    write_deterministic_parquet,
    write_stable_json,
)
from goatlab.schemas import PlayerGameStats, PlayerSeasonAdvanced, PlayerSeasonStats

ROOT = Path(__file__).resolve().parents[2]
PILOT_SEASONS = (
    "1946-47", "1961-62", "1973-74", "1979-80",
    "1984-85", "1996-97", "2022-23", "2025-26",
)
RECONCILIATION_SEASONS = ("1996-97", "2022-23", "2025-26")
SEASON_TYPES = ("Regular Season", "Playoffs")
RUN_SOURCE_ID = "nba_api:1.11.4:player-fact-pilot:step-0005"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True, help="Fixed deterministic ISO-8601 timestamp")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=ROOT / "data/bronze/nba_api")
    parser.add_argument("--sqlite", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    return parser.parse_args()


def _cached_or_acquire(
    client: NBAAPIClient, spec: Any, *, allow_network: bool
) -> Any:
    cached = client.cache.load(spec)
    if cached is not None:
        return cached
    if not allow_network:
        raise RuntimeError(f"required cache artifact missing: {spec.endpoint} {spec.parameters}")
    return client.execute(spec)


def _cache_timestamp(cache_root: Path, result: Any) -> datetime:
    path = cache_root / result.endpoint.lower() / f"{result.cache_key}.meta.json"
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _legacy_context(
    sqlite_path: Path,
) -> tuple[set[str], set[str], dict[str, list[tuple[int, int | None]]], set[str]]:
    connection = sqlite3.connect(sqlite_path)
    try:
        players = {str(row[0]) for row in connection.execute("SELECT id FROM player")}
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
    return players, teams, windows, games


def _relative_output(metadata_value: dict[str, Any]) -> dict[str, Any]:
    result = dict(metadata_value)
    result["path"] = str(Path(str(result["path"])).relative_to(ROOT))
    return result


def _partition_path(root: Path, entity: str, season: str, season_type: str) -> Path:
    kind = normalize_season_type(season_type).value
    return (
        root
        / entity
        / f"season={parse_season_label(season)}"
        / f"season_type={kind}"
        / "part-00000.parquet"
    )


def main() -> None:
    args = _args()
    run_at = utc_datetime(args.run_at)
    cache = ResponseCache(args.cache_root)
    client = NBAAPIClient(cache)
    bronze: list[dict[str, Any]] = []
    pgl_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    pgl_results: dict[tuple[str, str], Any] = {}
    base_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    base_results: dict[tuple[str, str], Any] = {}
    advanced_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    advanced_results: dict[tuple[str, str], Any] = {}

    requests_total = len(PILOT_SEASONS) * 2 + len(RECONCILIATION_SEASONS) * 4
    request_number = 0
    for season in PILOT_SEASONS:
        for season_type in SEASON_TYPES:
            request_number += 1
            print(f"[{request_number:02d}/{requests_total}] PlayerGameLogs {season} {season_type}")
            spec = player_game_logs_spec(season, season_type)
            result = _cached_or_acquire(client, spec, allow_network=args.allow_network)
            if result.outcome is not RequestOutcome.SUCCESS_WITH_ROWS:
                raise RuntimeError(f"player-game acquisition failed: {result.outcome.value}")
            rows = rows_from_result(result)
            decorated = [{**row, "SEASON_YEAR": season} for row in rows]
            pgl_rows[(season, season_type)] = decorated
            pgl_results[(season, season_type)] = result
            bronze.append(normalized_bronze_artifact(
                result, season=season, season_type=season_type,
                retrieved_at=_cache_timestamp(args.cache_root, result),
            ))

    for season in RECONCILIATION_SEASONS:
        for season_type in SEASON_TYPES:
            for measure in ("Base", "Advanced"):
                request_number += 1
                print(
                    f"[{request_number:02d}/{requests_total}] LeagueDashPlayerStats "
                    f"{measure} {season} {season_type}"
                )
                spec = league_dash_player_stats_spec(
                    season, season_type, measure_type=measure
                )
                result = _cached_or_acquire(client, spec, allow_network=args.allow_network)
                if result.outcome is not RequestOutcome.SUCCESS_WITH_ROWS:
                    raise RuntimeError(f"{measure} acquisition failed: {result.outcome.value}")
                rows = rows_from_result(result)
                target = base_rows if measure == "Base" else advanced_rows
                target[(season, season_type)] = rows
                if measure == "Base":
                    base_results[(season, season_type)] = result
                else:
                    advanced_results[(season, season_type)] = result
                bronze.append(normalized_bronze_artifact(
                    result, season=season, season_type=season_type,
                    measure_type=measure, per_mode="Totals",
                    retrieved_at=_cache_timestamp(args.cache_root, result),
                ))

    all_rows = [row for values in pgl_rows.values() for row in values]
    legacy_players, legacy_teams, legacy_windows, legacy_games = _legacy_context(args.sqlite)
    identities, identity_report = resolve_player_identities(
        all_rows, legacy_players, source_id=RUN_SOURCE_ID
    )
    teams, team_report = build_team_crosswalk(
        all_rows, legacy_teams, legacy_windows, source_id=RUN_SOURCE_ID
    )

    thresholds = CoverageThresholds()
    player_games: dict[tuple[str, str], list[PlayerGameStats]] = {}
    season_stats: dict[tuple[str, str], list[PlayerSeasonStats]] = {}
    advanced_stats: dict[tuple[str, str], list[PlayerSeasonAdvanced]] = {}
    coverage_matrix: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    parquet_outputs: list[dict[str, Any]] = []

    for key, rows in sorted(pgl_rows.items()):
        season, season_type = key
        mapped: list[PlayerGameStats] = []
        for row_number, row in enumerate(rows):
            try:
                mapped.append(map_player_game_row(
                    row, pgl_results[key], identities, teams,
                    season=season, season_type=season_type, updated_at=run_at,
                ))
            except (KeyError, TypeError, ValueError) as error:
                quarantined.append({
                    "season": season, "season_type": season_type,
                    "source_row_number": row_number, "error": str(error),
                    "nba_player_id": row.get("PLAYER_ID"),
                    "nba_game_id": row.get("GAME_ID"), "nba_team_id": row.get("TEAM_ID"),
                    "source_values": {
                        field: row.get(field)
                        for field in ("MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "PTS")
                    },
                })
        player_games[key] = mapped
        coverage = empirical_metric_coverage(
            mapped, season=season, season_type=season_type, thresholds=thresholds
        )
        coverage_matrix.extend(coverage)
        gates.append(quality_gates(
            rows, mapped, identities, teams, coverage,
            season=season, season_type=season_type,
        ))
        aggregates = aggregate_player_seasons(mapped, coverage, updated_at=run_at)
        season_stats[key] = aggregates
        game_path = _partition_path(
            args.silver_root, "player_game_stats", season, season_type
        )
        season_path = _partition_path(
            args.silver_root, "player_season_stats", season, season_type
        )
        parquet_outputs.append(_relative_output(write_deterministic_parquet(
            mapped, game_path, PLAYER_GAME_SCHEMA,
            sort_fields=("game_id", "player_id", "team_id"),
        )))
        parquet_outputs.append(_relative_output(write_deterministic_parquet(
            aggregates, season_path, PLAYER_SEASON_SCHEMA,
            sort_fields=("player_id", "row_scope", "team_id"),
        )))

    for key, rows in sorted(advanced_rows.items()):
        season, season_type = key
        result = advanced_results[key]
        advanced_mapped = [
            map_player_season_advanced(
                row, result, season=season, season_type=season_type, updated_at=run_at
            )
            for row in rows
        ]
        advanced_stats[key] = advanced_mapped
        path = _partition_path(
            args.silver_root, "player_season_advanced", season, season_type
        )
        parquet_outputs.append(_relative_output(write_deterministic_parquet(
            advanced_mapped, path, PLAYER_ADVANCED_SCHEMA,
            sort_fields=("player_id", "row_scope", "team_id"),
        )))

    reconciliations: dict[str, Any] = {}
    for key, rows in sorted(base_rows.items()):
        season, season_type = key
        reconciliations[f"{season}:{normalize_season_type(season_type).value}"] = (
            reconcile_base_totals(season_stats[key], rows)
        )

    duplicate_total_rows = 0
    for season_values in season_stats.values():
        total_keys = [
            (row.player_id, row.season_id, row.season_type)
            for row in season_values if row.row_scope.value == "TOTAL"
        ]
        duplicate_total_rows += sum(
            count - 1 for count in Counter(total_keys).values() if count > 1
        )
    official_game_ids = {
        str(row["GAME_ID"]) for values in pgl_rows.values() for row in values
    }
    legacy_game_matches = len(official_game_ids & legacy_games)
    quality_totals = {
        field: sum(int(gate[field]) for gate in gates)
        for field in (
            "duplicate_player_game_keys", "orphan_player_ids", "orphan_team_ids",
            "orphan_game_ids", "negative_box_score_counts",
            "impossible_shooting_relationships",
            "rebound_inconsistencies_under_reliable_coverage",
            "game_dates_outside_expected_window", "null_to_zero_violations",
            "missing_source_provenance",
        )
    }
    quality_totals["duplicate_total_season_rows"] = duplicate_total_rows
    critical_quality_issues = sum(quality_totals.values())
    reconciliation_pass = all(
        value["passes_v1_gate"] for value in reconciliations.values()
    )
    has_sparse_or_unavailable = any(
        item["classification"] in {"SPARSE", "UNAVAILABLE"} for item in coverage_matrix
    )
    pass_conditions = {
        "all_bulk_partitions_ingested": len(player_games) == 16,
        "identity_unresolved_zero": identity_report["unresolved"] == 0,
        "team_unresolved_zero": team_report["unresolved"] == 0,
        "transform_conflicts_explicitly_quarantined": all(
            item.get("error") and item.get("nba_game_id") for item in quarantined
        ),
        "no_critical_quality_issues": critical_quality_issues == 0,
        "season_aggregation_created": all(season_stats.values()),
        "base_reconciliation_sufficient": reconciliation_pass,
        "advanced_partitions_created": len(advanced_stats) == 6,
        "coverage_detects_sparse_or_unavailable": has_sparse_or_unavailable,
        "all_requests_resumed_from_cache": all(item.from_cache for item in pgl_results.values())
        and all(item.from_cache for item in base_results.values())
        and all(item.from_cache for item in advanced_results.values()),
    }
    decision = "PASS" if all(pass_conditions.values()) else "PARTIAL PASS"

    bronze_manifest = {
        "schema_version": 1, "step": "STEP-0005",
        "run_at": args.run_at, "nba_api_version": metadata.version("nba_api"),
        "resumable": True, "network_allowed": args.allow_network,
        "artifacts": sorted(
            bronze,
            key=lambda value: (
                value["endpoint"], value["measure_type"] or "",
                value["season"], value["season_type"],
            ),
        ),
    }
    write_stable_json(
        args.cache_root / "player-fact-pilot-manifest.json", bronze_manifest
    )
    docs = ROOT / "docs/data"
    identity_report.update({
        "schema_version": 1, "step": "STEP-0005", "run_at": args.run_at
    })
    team_report.update({
        "schema_version": 1, "step": "STEP-0005", "run_at": args.run_at
    })
    coverage_report = {
        "schema_version": 1, "step": "STEP-0005", "run_at": args.run_at,
        "thresholds": {
            "RELIABLE": "non-null percentage >= 0.99",
            "PARTIAL": "0.80 <= non-null percentage < 0.99",
            "SPARSE": "0 < non-null percentage < 0.80",
            "UNAVAILABLE": "documented historical unavailability or unsupported source field",
            "UNKNOWN": "no rows or no observations despite conceptual availability",
        },
        "observed_zero_denominator": "non-null observations",
        "matrix": coverage_matrix,
    }
    summary = {
        "schema_version": 1, "step": "STEP-0005", "run_at": args.run_at,
        "decision": decision, "pass_conditions": pass_conditions,
        "pilot_seasons": list(PILOT_SEASONS), "season_types": list(SEASON_TYPES),
        "bronze": {
            "request_artifacts": len(bronze),
            "player_game_rows": sum(len(rows) for rows in pgl_rows.values()),
            "base_rows": sum(len(rows) for rows in base_rows.values()),
            "advanced_rows": sum(len(rows) for rows in advanced_rows.values()),
        },
        "silver": {
            "player_game_rows": sum(len(rows) for rows in player_games.values()),
            "player_season_rows": sum(len(rows) for rows in season_stats.values()),
            "player_season_team_rows": sum(
                row.row_scope.value == "TEAM"
                for rows in season_stats.values() for row in rows
            ),
            "player_season_total_rows": sum(
                row.row_scope.value == "TOTAL"
                for rows in season_stats.values() for row in rows
            ),
            "advanced_rows": sum(len(rows) for rows in advanced_stats.values()),
            "partitions": parquet_outputs,
        },
        "identity": {
            key: identity_report[key] for key in (
                "distinct_player_ids", "legacy_matches", "legacy_match_rate",
                "nba_api_provisional", "unresolved",
            )
        },
        "teams": {
            key: team_report[key] for key in (
                "distinct_source_team_ids", "canonical_team_versions",
                "legacy_id_matches", "unmatched_team_ids", "unresolved",
            )
        },
        "games": {
            "distinct_official_game_ids": len(official_game_ids),
            "legacy_game_id_matches": legacy_game_matches,
            "official_only_game_ids": len(official_game_ids - legacy_games),
        },
        "quality_gates": gates, "quality_totals": quality_totals,
        "transform_quarantine": quarantined,
        "base_reconciliation": reconciliations,
    }
    write_stable_json(docs / "player-identity-reconciliation.json", identity_report)
    write_stable_json(docs / "team-crosswalk-report.json", team_report)
    write_stable_json(docs / "metric-coverage-pilot.json", coverage_report)
    write_stable_json(docs / "player-fact-pilot-summary.json", summary)
    print(json_summary(summary))


def json_summary(summary: dict[str, Any]) -> str:
    import json

    return json.dumps({
        "decision": summary["decision"],
        "bronze": summary["bronze"],
        "silver": {
            key: value for key, value in summary["silver"].items() if key != "partitions"
        },
        "quality_totals": summary["quality_totals"],
    }, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
