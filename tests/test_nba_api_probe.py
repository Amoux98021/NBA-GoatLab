import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from goatlab.data.canonical import canonical_id
from goatlab.data.nba_api_client import RequestOutcome, RequestResult
from goatlab.data.nba_api_probe import (
    duplicate_summary,
    identity_coverage,
    map_player_game_log,
    map_player_season_advanced,
    map_player_season_base,
    reconcile_2022_23,
    stable_json,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/fixtures/nba_api_player_fact_probe_sample.json"
STAMP = datetime(2026, 8, 19, 16, tzinfo=UTC)


def _records() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]


def _result(record: dict[str, Any]) -> RequestResult:
    return RequestResult(
        outcome=RequestOutcome.SUCCESS_WITH_ROWS, cache_key=record["cache_key"],
        endpoint=record["endpoint"], parameters={"Season": record["season"]}, attempts=1,
        elapsed_seconds=0.1, status_code=200, response_sha256=record["response_sha256"],
        payload=None, error_type=None, error_message=None, request_url="fixture", from_cache=False,
    )


def test_player_game_mapping_preserves_historical_nulls_and_identity() -> None:
    record = _records()[0]
    row = record["row"]
    team_id = canonical_id("team", "nba", "1610610034:1946")
    mapped = map_player_game_log(
        row, _result(record), {"1610610034": team_id}, season="1946-47",
        season_type="Regular Season", updated_at=STAMP,
    )
    assert mapped.player_id == canonical_id("player", "nba", "77403")
    assert mapped.team_id == team_id
    assert mapped.points == 11
    assert mapped.minutes is None
    assert mapped.rebounds is None
    assert mapped.fg3m is None
    assert mapped.source_id.startswith("nba_api:1.11.4:playergamelogs:")


def test_league_dash_base_and_advanced_mapping() -> None:
    base, advanced = _records()[1:]
    base_row = map_player_season_base(
        base["row"], _result(base), season="2022-23", season_type="Regular Season",
        updated_at=STAMP,
    )
    advanced_row = map_player_season_advanced(
        advanced["row"], _result(advanced), season="1996-97",
        season_type="Regular Season", updated_at=STAMP,
    )
    assert base_row.points_total == 56
    assert base_row.team_id is None
    assert advanced_row.offensive_rating == 97.4
    assert advanced_row.possessions == 4699


def test_duplicate_detection() -> None:
    rows = [
        {"PLAYER_ID": 1, "GAME_ID": "1", "TEAM_ID": 10},
        {"PLAYER_ID": 1, "GAME_ID": "1", "TEAM_ID": 10},
        {"PLAYER_ID": 2, "GAME_ID": "1", "TEAM_ID": 10},
    ]
    result = duplicate_summary(rows, ("PLAYER_ID", "GAME_ID", "TEAM_ID"))
    assert result["duplicate_groups"] == 1
    assert result["duplicate_rows"] == 1


def _sqlite(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE game (season_id TEXT, game_id TEXT, game_date TEXT, "
        "team_id_home TEXT, team_id_away TEXT, matchup_home TEXT, matchup_away TEXT, "
        "season_type TEXT);"
        "CREATE TABLE player (id TEXT); CREATE TABLE common_player_info (person_id TEXT);"
        "INSERT INTO player VALUES ('1'); INSERT INTO common_player_info VALUES ('1');"
        "INSERT INTO game VALUES ('22022','g1','2022-10-18','10','20',"
        "'AAA vs. BBB','BBB @ AAA','Regular Season');"
        "INSERT INTO game VALUES ('32022','a1','2023-02-19','10','20','','','All Star');"
    )
    connection.commit()
    connection.close()


def test_reconciliation_quarantines_conflicts(tmp_path: Path) -> None:
    database = tmp_path / "fixture.sqlite"
    _sqlite(database)
    rows = {
        "Regular Season": [
            {"GAME_ID": "g1", "GAME_DATE": "2022-10-19", "TEAM_ID": 10,
             "MATCHUP": "AAA vs. BBB"},
            {"GAME_ID": "g1", "GAME_DATE": "2022-10-19", "TEAM_ID": 20,
             "MATCHUP": "BBB @ AAA"},
        ],
        "Playoffs": [],
    }
    report = reconcile_2022_23(rows, database)
    assert report["source_precedence_changed"] is False
    assert len(report["conflict_quarantine"]) == 1
    assert report["conflict_quarantine"][0]["date_match"] is False


def test_player_id_mapping_and_report_generation_are_deterministic(tmp_path: Path) -> None:
    database = tmp_path / "fixture.sqlite"
    _sqlite(database)
    rows = [{"PLAYER_ID": 1, "PLAYER_NAME": "Diagnostic"},
            {"PLAYER_ID": 2, "PLAYER_NAME": "Unmatched"}]
    coverage = identity_coverage(rows, database, ROOT / "data/fixtures/nbadb_v238_sample.json")
    assert coverage["legacy_player_matches"] == 1
    assert coverage["unmatched_legacy_player"][0]["nba_player_id"] == "2"
    assert stable_json(coverage) == stable_json(coverage)

