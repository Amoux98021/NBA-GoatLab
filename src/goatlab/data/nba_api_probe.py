"""Deterministic analysis helpers for the bounded NBA player-fact probe."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from nba_api.stats.endpoints import (  # type: ignore[import-untyped]
    leaguedashplayerstats,
    playergamelogs,
)

from goatlab.data.canonical import canonical_id, normalize_season_type, parse_season_label
from goatlab.data.nba_api_client import RequestOutcome, RequestResult, RequestSpec
from goatlab.schemas import (
    PlayerGameStats,
    PlayerSeasonAdvanced,
    PlayerSeasonStats,
    SeasonRowScope,
    SeasonType,
)

PLAYER_GAME_FIELDS = (
    "PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "GAME_ID",
    "GAME_DATE", "MATCHUP", "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A",
    "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB", "REB", "AST", "TOV",
    "STL", "BLK", "PF", "PTS", "PLUS_MINUS",
)
BASE_FIELDS = (
    "PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "GP", "GS", "MIN",
    "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
    "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK", "PF", "PTS",
)
ADVANCED_FIELDS = (
    "PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "GP", "MIN",
    "OFF_RATING", "DEF_RATING", "NET_RATING", "PACE", "USG_PCT", "TS_PCT", "EFG_PCT",
    "AST_PCT", "OREB_PCT", "DREB_PCT", "REB_PCT", "TM_TOV_PCT", "PIE", "POSS",
)

# NBA Stats FAQ documented introduction seasons. The probe evaluates source responses separately.
INTRODUCTION_SEASON = {
    "REB": 1950,
    "MIN": 1951,
    "GS": 1970,
    "OREB": 1973,
    "DREB": 1973,
    "STL": 1973,
    "BLK": 1973,
    "TOV": 1977,
    "FG3M": 1979,
    "FG3A": 1979,
    "FG3_PCT": 1979,
}
ADVANCED_INTRODUCTION_SEASON = 1996


def player_game_logs_spec(season: str, season_type: str) -> RequestSpec:
    endpoint = playergamelogs.PlayerGameLogs(
        player_id_nullable="",
        season_nullable=season,
        season_type_nullable=season_type,
        get_request=False,
    )
    return RequestSpec(endpoint=endpoint.endpoint, parameters=endpoint.parameters)


def league_dash_player_stats_spec(
    season: str, season_type: str, *, measure_type: str = "Base", per_mode: str = "Totals"
) -> RequestSpec:
    endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star=season_type,
        measure_type_detailed_defense=measure_type,
        per_mode_detailed=per_mode,
        get_request=False,
    )
    return RequestSpec(endpoint=endpoint.endpoint, parameters=endpoint.parameters)


def result_rows(payload: Mapping[str, Any] | None) -> tuple[list[str], list[dict[str, Any]]]:
    """Return the first NBA result set as named rows."""
    if payload is None:
        return [], []
    raw_sets = payload.get("resultSets", payload.get("resultSet", []))
    sets = [raw_sets] if isinstance(raw_sets, dict) else raw_sets
    if not isinstance(sets, list):
        return [], []
    for raw_set in sets:
        if not isinstance(raw_set, dict):
            continue
        headers, raw_rows = raw_set.get("headers"), raw_set.get("rowSet")
        if not isinstance(headers, list) or not isinstance(raw_rows, list):
            continue
        field_names = [str(field) for field in headers]
        rows = [dict(zip(field_names, row, strict=True)) for row in raw_rows]
        return field_names, rows
    return [], []


def duplicate_summary(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> dict[str, Any]:
    counts = Counter(tuple(row.get(key) for key in keys) for row in rows)
    duplicate_groups = sum(count > 1 for count in counts.values())
    duplicate_rows = sum(count - 1 for count in counts.values() if count > 1)
    return {
        "candidate_key": list(keys),
        "duplicate_groups": duplicate_groups,
        "duplicate_rows": duplicate_rows,
        "duplicate_row_rate": round(duplicate_rows / len(rows), 8) if rows else 0.0,
    }


def null_rates(
    rows: Sequence[Mapping[str, Any]], expected_fields: Sequence[str]
) -> dict[str, float | None]:
    fields = {field for row in rows for field in row}
    return {
        field: (
            round(sum(row.get(field) is None for row in rows) / len(rows), 8)
            if rows and field in fields
            else None
        )
        for field in expected_fields
    }


def summarize_probe(
    result: RequestResult,
    *,
    probe_kind: str,
    season: str,
    season_type: str,
    measure_type: str | None = None,
    per_mode: str | None = None,
) -> dict[str, Any]:
    fields, rows = result_rows(result.payload)
    expected = (
        PLAYER_GAME_FIELDS
        if probe_kind == "PLAYER_GAME_LOGS"
        else ADVANCED_FIELDS
        if measure_type == "Advanced"
        else BASE_FIELDS
    )
    keys = (
        ("PLAYER_ID", "GAME_ID", "TEAM_ID")
        if probe_kind == "PLAYER_GAME_LOGS"
        else ("PLAYER_ID", "TEAM_ID")
    )
    dates = sorted(str(row["GAME_DATE"]) for row in rows if row.get("GAME_DATE"))
    duplicates = duplicate_summary(rows, keys)
    plausible_reasons: list[str] = []
    if result.outcome is not RequestOutcome.SUCCESS_WITH_ROWS:
        plausible_reasons.append(f"outcome={result.outcome.value}")
    if rows and any(key not in fields for key in keys):
        plausible_reasons.append("candidate key field absent")
    if duplicates["duplicate_rows"]:
        plausible_reasons.append("duplicate candidate keys")
    implausible_zero_fields = {
        field: sum(row.get(field) == 0 for row in rows)
        for field, introduced in INTRODUCTION_SEASON.items()
        if parse_season_label(season) < introduced and field in fields
    }
    return {
        "endpoint": result.endpoint,
        "probe_kind": probe_kind,
        "season": season,
        "season_type": season_type,
        "measure_type": measure_type,
        "per_mode": per_mode,
        "outcome": result.outcome.value,
        "http_status": result.status_code,
        "row_count": len(rows),
        "distinct_players": len({row.get("PLAYER_ID") for row in rows}),
        "distinct_games": len({row.get("GAME_ID") for row in rows if row.get("GAME_ID")}),
        "min_game_date": dates[0] if dates else None,
        "max_game_date": dates[-1] if dates else None,
        "fields": fields,
        "important_null_rates": null_rates(rows, expected),
        "duplicates": duplicates,
        "response_time_seconds": result.elapsed_seconds,
        "retry_count": result.retry_count,
        "plausible": not plausible_reasons,
        "plausibility_notes": plausible_reasons,
        "pre_introduction_zero_counts": implausible_zero_fields,
        "request": {
            "cache_key": result.cache_key,
            "parameters": dict(sorted(result.parameters.items())),
            "response_sha256": result.response_sha256,
            "error_type": result.error_type,
            "error_message": result.error_message,
        },
    }


def _historically_observed(field: str, season_id: int) -> bool:
    return season_id >= INTRODUCTION_SEASON.get(field, 1946)


def _nullable_number(row: Mapping[str, Any], field: str, season_id: int) -> Any:
    return row.get(field) if _historically_observed(field, season_id) else None


def nba_api_source_id(result: RequestResult) -> str:
    return f"nba_api:{metadata.version('nba_api')}:{result.endpoint}:{result.cache_key}"


def map_player_game_log(
    row: Mapping[str, Any], result: RequestResult, team_id_by_nba_id: Mapping[str, str],
    *, season: str, season_type: str,
    updated_at: datetime,
) -> PlayerGameStats:
    season_id = parse_season_label(season)
    nba_team_id = str(row["TEAM_ID"])
    try:
        team_id = team_id_by_nba_id[nba_team_id]
    except KeyError as error:
        raise ValueError(f"unresolved NBA team ID: {nba_team_id}") from error
    return PlayerGameStats(
        game_id=canonical_id("game", "nba", str(row["GAME_ID"])),
        player_id=canonical_id("player", "nba", str(row["PLAYER_ID"])),
        team_id=team_id,
        season_id=season_id,
        season_type=normalize_season_type(season_type),
        minutes=_nullable_number(row, "MIN", season_id),
        points=row.get("PTS"), fgm=row.get("FGM"), fga=row.get("FGA"),
        fg3m=_nullable_number(row, "FG3M", season_id),
        fg3a=_nullable_number(row, "FG3A", season_id),
        ftm=row.get("FTM"), fta=row.get("FTA"),
        oreb=_nullable_number(row, "OREB", season_id),
        dreb=_nullable_number(row, "DREB", season_id),
        rebounds=_nullable_number(row, "REB", season_id),
        assists=row.get("AST"), steals=_nullable_number(row, "STL", season_id),
        blocks=_nullable_number(row, "BLK", season_id),
        turnovers=_nullable_number(row, "TOV", season_id),
        personal_fouls=row.get("PF"), plus_minus=row.get("PLUS_MINUS"),
        started=None, did_play=True if _historically_observed("MIN", season_id) else None,
        source_id=nba_api_source_id(result), updated_at=updated_at,
    )


def map_player_season_base(
    row: Mapping[str, Any], result: RequestResult, *, season: str, season_type: str,
    updated_at: datetime,
) -> PlayerSeasonStats:
    season_id = parse_season_label(season)
    return PlayerSeasonStats(
        player_id=canonical_id("player", "nba", str(row["PLAYER_ID"])), season_id=season_id,
        season_type=normalize_season_type(season_type), row_scope=SeasonRowScope.TOTAL,
        team_id=None, games_played=row.get("GP"),
        games_started=_nullable_number(row, "GS", season_id),
        minutes_total=_nullable_number(row, "MIN", season_id), points_total=row.get("PTS"),
        fgm_total=row.get("FGM"), fga_total=row.get("FGA"),
        fg3m_total=_nullable_number(row, "FG3M", season_id),
        fg3a_total=_nullable_number(row, "FG3A", season_id),
        ftm_total=row.get("FTM"), fta_total=row.get("FTA"),
        oreb_total=_nullable_number(row, "OREB", season_id),
        dreb_total=_nullable_number(row, "DREB", season_id),
        rebounds_total=_nullable_number(row, "REB", season_id), assists_total=row.get("AST"),
        steals_total=_nullable_number(row, "STL", season_id),
        blocks_total=_nullable_number(row, "BLK", season_id),
        turnovers_total=_nullable_number(row, "TOV", season_id),
        personal_fouls_total=row.get("PF"), minutes_per_game=None, points_per_game=None,
        rebounds_per_game=None, assists_per_game=None, steals_per_game=None,
        blocks_per_game=None, turnovers_per_game=None,
        fg_pct=row.get("FG_PCT"), fg3_pct=_nullable_number(row, "FG3_PCT", season_id),
        ft_pct=row.get("FT_PCT"), source_id=nba_api_source_id(result), updated_at=updated_at,
    )


def map_player_season_advanced(
    row: Mapping[str, Any], result: RequestResult, *, season: str, season_type: str,
    updated_at: datetime,
) -> PlayerSeasonAdvanced:
    season_id = parse_season_label(season)
    available = season_id >= ADVANCED_INTRODUCTION_SEASON
    def value(field: str) -> Any:
        return row.get(field) if available else None

    return PlayerSeasonAdvanced(
        player_id=canonical_id("player", "nba", str(row["PLAYER_ID"])), season_id=season_id,
        season_type=normalize_season_type(season_type), row_scope=SeasonRowScope.TOTAL,
        team_id=None, games_played=row.get("GP"), minutes=value("MIN"),
        offensive_rating=value("OFF_RATING"), defensive_rating=value("DEF_RATING"),
        net_rating=value("NET_RATING"), pace=value("PACE"), usage_pct=value("USG_PCT"),
        true_shooting_pct=value("TS_PCT"), effective_fg_pct=value("EFG_PCT"),
        assist_pct=value("AST_PCT"), oreb_pct=value("OREB_PCT"),
        dreb_pct=value("DREB_PCT"), rebound_pct=value("REB_PCT"),
        turnover_pct=value("TM_TOV_PCT"), pie=value("PIE"), possessions=value("POSS"),
        source_id=nba_api_source_id(result), updated_at=updated_at,
    )


def reconcile_2022_23(
    rows_by_type: Mapping[str, Sequence[Mapping[str, Any]]], sqlite_path: Path
) -> dict[str, Any]:
    """Reconcile NBA API player-game facts to audited legacy game IDs; retain conflicts."""
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    conflicts: list[dict[str, Any]] = []
    types: dict[str, Any] = {}
    try:
        for nba_type, rows in sorted(rows_by_type.items()):
            canonical_type = normalize_season_type(nba_type)
            season_prefix = "2" if canonical_type is SeasonType.REGULAR else "4"
            source_rows = connection.execute(
                "SELECT game_id, date(game_date) game_date, team_id_home, team_id_away, "
                "matchup_home, matchup_away FROM game WHERE season_id = ?",
                (f"{season_prefix}2022",),
            ).fetchall()
            games = {str(row["game_id"]): dict(row) for row in source_rows}
            api_games: dict[str, list[Mapping[str, Any]]] = {}
            for row in rows:
                api_games.setdefault(str(row["GAME_ID"]), []).append(row)
            shared = sorted(set(api_games) & set(games))
            date_matches = team_matches = matchup_matches = 0
            for game_id in shared:
                source = games[game_id]
                api_rows = api_games[game_id]
                dates = {str(row.get("GAME_DATE"))[:10] for row in api_rows}
                teams = {str(row.get("TEAM_ID")) for row in api_rows}
                expected_teams = {str(source["team_id_home"]), str(source["team_id_away"])}
                date_ok = dates == {str(source["game_date"])}
                team_ok = teams == expected_teams
                home_rows = [
                    row
                    for row in api_rows
                    if str(row.get("TEAM_ID")) == str(source["team_id_home"])
                ]
                away_rows = [
                    row
                    for row in api_rows
                    if str(row.get("TEAM_ID")) == str(source["team_id_away"])
                ]
                matchup_ok = bool(home_rows and away_rows) and all(
                    "vs." in str(row.get("MATCHUP")) for row in home_rows
                ) and all("@" in str(row.get("MATCHUP")) for row in away_rows)
                date_matches += date_ok
                team_matches += team_ok
                matchup_matches += matchup_ok
                if not (date_ok and team_ok and matchup_ok):
                    conflicts.append({
                        "season_type": nba_type, "game_id": game_id, "date_match": date_ok,
                        "team_ids_match": team_ok, "matchup_interpretation_match": matchup_ok,
                        "source": source, "api_dates": sorted(dates), "api_team_ids": sorted(teams),
                    })
            types[nba_type] = {
                "nba_api_distinct_games": len(api_games), "kaggle_distinct_games": len(games),
                "shared_games": len(shared),
                "nba_api_only_games": sorted(set(api_games) - set(games)),
                "kaggle_only_games": sorted(set(games) - set(api_games)),
                "date_matches": date_matches, "team_id_matches": team_matches,
                "matchup_interpretation_matches": matchup_matches,
            }
        all_star = connection.execute(
            "SELECT season_type, COUNT(*) count FROM game "
            "WHERE season_id='32022' GROUP BY season_type"
        ).fetchall()
    finally:
        connection.close()
    return {
        "season": "2022-23", "join_key": "NBA GAME_ID", "source_precedence_changed": False,
        "season_types": types, "all_star_artifacts": [dict(row) for row in all_star],
        "conflict_quarantine": conflicts,
    }


def identity_coverage(
    rows: Iterable[Mapping[str, Any]], sqlite_path: Path, fixture_path: Path
) -> dict[str, Any]:
    identities = {str(row["PLAYER_ID"]): str(row.get("PLAYER_NAME") or "") for row in rows}
    connection = sqlite3.connect(sqlite_path)
    try:
        legacy = {str(row[0]) for row in connection.execute("SELECT id FROM player")}
        common = {
            str(row[0])
            for row in connection.execute("SELECT person_id FROM common_player_info")
        }
    finally:
        connection.close()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_ids = {str(fixture["player"]["id"])}
    ids = set(identities)
    return {
        "business_key": "nba_player_id (official PLAYER_ID)",
        "returned_player_ids": len(ids),
        "legacy_player_matches": len(ids & legacy),
        "legacy_player_match_rate": round(len(ids & legacy) / len(ids), 8) if ids else 0.0,
        "common_player_info_matches": len(ids & common),
        "common_player_info_match_rate": round(len(ids & common) / len(ids), 8) if ids else 0.0,
        "canonical_fixture_player_ids": len(fixture_ids),
        "canonical_fixture_matches": len(ids & fixture_ids),
        "unmatched_legacy_player": [
            {"nba_player_id": player_id, "diagnostic_name": identities[player_id]}
            for player_id in sorted(ids - legacy)
        ],
        "unmatched_common_player_info": [
            {"nba_player_id": player_id, "diagnostic_name": identities[player_id]}
            for player_id in sorted(ids - common)
        ],
        "canonical_id_examples": [
            {"nba_player_id": player_id, "player_id": canonical_id("player", "nba", player_id)}
            for player_id in sorted(ids)[:5]
        ],
    }


def stable_json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json_report(path: Path, data: object) -> None:
    path.write_text(stable_json(data), encoding="utf-8")


def rows_from_result(result: RequestResult) -> list[dict[str, Any]]:
    return result_rows(result.payload)[1]
