import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from goatlab.data.canonical import canonical_id
from goatlab.data.nba_api_client import RequestOutcome, RequestResult
from goatlab.data.player_fact_ingestion import (
    PLAYER_GAME_SCHEMA,
    CoverageClass,
    CoverageThresholds,
    aggregate_player_seasons,
    build_team_crosswalk,
    classify_coverage,
    empirical_metric_coverage,
    map_player_game_row,
    normalized_bronze_artifact,
    quality_gates,
    reconcile_base_totals,
    resolve_player_identities,
    write_deterministic_parquet,
)
from goatlab.schemas import SeasonRowScope

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 8, 27, 15, tzinfo=UTC)


def _fixture_record(index: int = 0) -> dict[str, Any]:
    fixture = json.loads(
        (ROOT / "data/fixtures/nba_api_player_fact_probe_sample.json").read_text(
            encoding="utf-8"
        )
    )
    return fixture["records"][index]


def _result(record: dict[str, Any]) -> RequestResult:
    payload = {
        "resultSets": [{
            "headers": list(record["row"]),
            "rowSet": [list(record["row"].values())],
        }]
    }
    return RequestResult(
        outcome=RequestOutcome.SUCCESS_WITH_ROWS,
        cache_key=record["cache_key"],
        endpoint=record["endpoint"],
        parameters={"Season": record["season"], "SeasonType": record["season_type"]},
        attempts=1,
        elapsed_seconds=0.1,
        status_code=200,
        response_sha256=record["response_sha256"],
        payload=payload,
        error_type=None,
        error_message=None,
        request_url="fixture",
        from_cache=True,
    )


def _modern_rows() -> list[dict[str, Any]]:
    base = {
        "SEASON_YEAR": "2022-23",
        "PLAYER_ID": 1,
        "PLAYER_NAME": "Fixture Player",
        "TEAM_ID": 10,
        "TEAM_NAME": "Fixture Team",
        "TEAM_ABBREVIATION": "FIX",
        "GAME_DATE": "2022-10-18",
        "MIN": 30.5,
        "FGM": 4,
        "FGA": 8,
        "FG3M": 1,
        "FG3A": 2,
        "FTM": 2,
        "FTA": 2,
        "OREB": 1,
        "DREB": 4,
        "REB": 5,
        "AST": 3,
        "STL": 1,
        "BLK": 0,
        "TOV": 2,
        "PF": 2,
        "PTS": 11,
        "PLUS_MINUS": -3.0,
    }
    return [
        {**base, "GAME_ID": "g1"},
        {
            **base,
            "GAME_ID": "g2",
            "GAME_DATE": "2022-10-20",
            "MIN": 20.0,
            "FGM": 2,
            "FGA": 4,
            "FG3M": 0,
            "FG3A": 1,
            "FTM": 0,
            "FTA": 0,
            "OREB": 0,
            "DREB": 2,
            "REB": 2,
            "AST": 1,
            "STL": 0,
            "BLK": 1,
            "TOV": 1,
            "PF": 1,
            "PTS": 4,
            "PLUS_MINUS": 2.0,
        },
    ]


def _mapped_modern() -> tuple[
    list[dict[str, Any]], list[Any], dict[str, Any], dict[tuple[str, str], Any]
]:
    rows = _modern_rows()
    identities, _ = resolve_player_identities(rows, {"1"}, source_id="fixture:identity")
    teams, _ = build_team_crosswalk(
        rows, {"10"}, {"10": [(2022, None)]}, source_id="fixture:team"
    )
    result = _result(_fixture_record())
    mapped = [
        map_player_game_row(
            row,
            result,
            identities,
            teams,
            season="2022-23",
            season_type="Regular Season",
            updated_at=STAMP,
        )
        for row in rows
    ]
    return rows, mapped, identities, teams


def test_bronze_normalization_preserves_contract_and_provenance() -> None:
    record = _fixture_record()
    artifact = normalized_bronze_artifact(
        _result(record),
        season=record["season"],
        season_type=record["season_type"],
        retrieved_at=STAMP,
    )
    assert artifact["row_count"] == 1
    assert artifact["source_status"] == "SUCCESS_WITH_ROWS"
    assert artifact["content_sha256"] == record["response_sha256"]
    assert artifact["retrieval_timestamp"] == "2026-08-27T15:00:00Z"


def test_player_and_team_resolvers_use_official_ids_not_names() -> None:
    rows = _modern_rows()
    identities, identity_report = resolve_player_identities(
        rows, set(), source_id="fixture:identity"
    )
    teams, team_report = build_team_crosswalk(
        rows, {"10"}, {"10": [(1946, 2019)]}, source_id="fixture:team"
    )
    assert identities["1"].player_id == canonical_id("player", "nba", "1")
    assert identities["1"].resolution == "NBA_API_PROVISIONAL"
    assert identity_report["unresolved"] == 0
    assert teams[("10", "Fixture Team")].nba_team_id == "10"
    assert team_report["stale_window_conflicts"]


def test_player_resolver_retains_official_id_when_name_is_missing() -> None:
    identities, report = resolve_player_identities(
        [{"PLAYER_ID": 999, "PLAYER_NAME": None}],
        set(),
        source_id="fixture:identity",
    )
    assert identities["999"].player_id == canonical_id("player", "nba", "999")
    assert identities["999"].diagnostic_name is None
    assert report["unresolved"] == 0


def test_player_game_mapping_preserves_historical_null_and_observed_zero() -> None:
    record = _fixture_record()
    row = {**record["row"], "SEASON_YEAR": "1946-47", "TEAM_NAME": "St. Louis Bombers"}
    identities, _ = resolve_player_identities([row], {"77403"}, source_id="fixture:identity")
    teams, _ = build_team_crosswalk(
        [row], set(), {}, source_id="fixture:team"
    )
    mapped = map_player_game_row(
        row,
        _result(record),
        identities,
        teams,
        season="1946-47",
        season_type="Regular Season",
        updated_at=STAMP,
    )
    assert mapped.minutes is None
    assert mapped.fg3m is None
    assert mapped.points == 11
    assert mapped.did_play is True
    assert mapped.started is None


def test_coverage_and_null_safe_season_aggregation() -> None:
    _, mapped, _, _ = _mapped_modern()
    coverage = empirical_metric_coverage(
        mapped,
        season="2022-23",
        season_type="Regular Season",
        thresholds=CoverageThresholds(),
    )
    aggregates = aggregate_player_seasons(mapped, coverage, updated_at=STAMP)
    team = next(row for row in aggregates if row.row_scope is SeasonRowScope.TEAM)
    total = next(row for row in aggregates if row.row_scope is SeasonRowScope.TOTAL)
    assert len(aggregates) == 2
    assert total.games_played == 2
    assert total.points_total == 15
    assert total.fgm_total == 6
    assert total.fga_total == 12
    assert total.fg_pct == 0.5
    assert total.fg3_pct == round(1 / 3, 12)
    assert total.ft_pct == 1.0
    assert team.team_id is not None
    assert total.team_id is None

    partial = [dict(item) for item in coverage]
    next(item for item in partial if item["canonical_metric"] == "assists")[
        "classification"
    ] = CoverageClass.SPARSE.value
    sparse_total = next(
        row
        for row in aggregate_player_seasons(mapped, partial, updated_at=STAMP)
        if row.row_scope is SeasonRowScope.TOTAL
    )
    assert sparse_total.assists_total is None
    assert sparse_total.assists_per_game is None


def test_coverage_classification_thresholds_are_conservative() -> None:
    thresholds = CoverageThresholds()
    assert classify_coverage(
        row_count=100,
        non_null_count=99,
        historically_available=True,
        source_supported=True,
        thresholds=thresholds,
    ) is CoverageClass.RELIABLE
    assert classify_coverage(
        row_count=100,
        non_null_count=80,
        historically_available=True,
        source_supported=True,
        thresholds=thresholds,
    ) is CoverageClass.PARTIAL
    assert classify_coverage(
        row_count=100,
        non_null_count=1,
        historically_available=True,
        source_supported=True,
        thresholds=thresholds,
    ) is CoverageClass.SPARSE
    assert classify_coverage(
        row_count=100,
        non_null_count=0,
        historically_available=False,
        source_supported=True,
        thresholds=thresholds,
    ) is CoverageClass.UNAVAILABLE


def test_integrity_gates_detect_duplicates_without_repairing() -> None:
    raw, mapped, identities, teams = _mapped_modern()
    coverage = empirical_metric_coverage(
        mapped,
        season="2022-23",
        season_type="Regular Season",
        thresholds=CoverageThresholds(),
    )
    report = quality_gates(
        [*raw, raw[0]],
        [*mapped, mapped[0]],
        identities,
        teams,
        coverage,
        season="2022-23",
        season_type="Regular Season",
    )
    assert report["duplicate_player_game_keys"] == 1
    assert report["orphan_player_ids"] == 0
    assert report["orphan_team_ids"] == 0
    assert report["null_to_zero_violations"] == 0


def test_base_reconciliation_supports_exact_and_tolerance_matches() -> None:
    _, mapped, _, _ = _mapped_modern()
    coverage = empirical_metric_coverage(
        mapped,
        season="2022-23",
        season_type="Regular Season",
        thresholds=CoverageThresholds(),
    )
    totals = aggregate_player_seasons(mapped, coverage, updated_at=STAMP)
    official = [{
        "PLAYER_ID": 1,
        "GP": 2,
        "MIN": 50.5,
        "PTS": 15,
        "FGM": 6,
        "FGA": 12,
        "FG_PCT": 0.5,
        "FG3M": 1,
        "FG3A": 3,
        "FG3_PCT": 0.333,
        "FTM": 2,
        "FTA": 2,
        "FT_PCT": 1.0,
        "OREB": 1,
        "DREB": 6,
        "REB": 7,
        "AST": 4,
        "STL": 1,
        "BLK": 1,
        "TOV": 3,
        "PF": 3,
    }]
    report = reconcile_base_totals(totals, official)
    assert report["shared_players"] == 1
    assert report["mismatches"] == 0
    assert report["tolerance_matches"] >= 1
    assert report["passes_v1_gate"] is True


def test_parquet_generation_is_deterministic(tmp_path: Path) -> None:
    _, mapped, _, _ = _mapped_modern()
    first = write_deterministic_parquet(
        mapped,
        tmp_path / "first.parquet",
        PLAYER_GAME_SCHEMA,
        sort_fields=("game_id", "player_id", "team_id"),
    )
    second = write_deterministic_parquet(
        list(reversed(mapped)),
        tmp_path / "second.parquet",
        PLAYER_GAME_SCHEMA,
        sort_fields=("game_id", "player_id", "team_id"),
    )
    assert first["sha256"] == second["sha256"]
    assert (tmp_path / "first.parquet").read_bytes() == (
        tmp_path / "second.parquet"
    ).read_bytes()
