"""Factual All-Star and statistical-leader completion primitives."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nba_api.stats.endpoints import (  # type: ignore[import-untyped]
    boxscoretraditionalv3,
    leagueleaders,
)

from goatlab.data.nba_api_client import RequestSpec

ACCOLADE_COMPLETION_METHODOLOGY_VERSION = "all-star-stat-leader-facts-v1"
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
NO_ALL_STAR_GAME_SEASONS = frozenset({1998})
CATEGORY_INTRODUCTION = {"PTS": 1946, "REB": 1950, "AST": 1946, "STL": 1973, "BLK": 1973}
CATEGORY_FIELDS = {
    "PTS": ("points_per_game", "points_total"),
    "REB": ("rebounds_per_game", "rebounds_total"),
    "AST": ("assists_per_game", "assists_total"),
    "STL": ("steals_per_game", "steals_total"),
    "BLK": ("blocks_per_game", "blocks_total"),
}


def season_label(season_id: int) -> str:
    return f"{season_id:04d}-{(season_id + 1) % 100:02d}"


def all_star_applicability(season_id: int) -> str:
    if season_id < 1950:
        return "NOT_APPLICABLE"
    if season_id in NO_ALL_STAR_GAME_SEASONS:
        return "NO_GAME_HELD"
    return "APPLICABLE"


def category_applicability(season_id: int, category: str) -> str:
    introduction = CATEGORY_INTRODUCTION[category]
    return "APPLICABLE" if season_id >= introduction else "NOT_APPLICABLE"


def stable_id(namespace: str, values: Sequence[object]) -> str:
    payload = json.dumps([namespace, *values], separators=(",", ":"), ensure_ascii=True)
    return f"{namespace}_{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def stable_fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def result_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    raw_sets = payload.get("resultSets", payload.get("resultSet", []))
    sets = [raw_sets] if isinstance(raw_sets, Mapping) else raw_sets
    if not isinstance(sets, list):
        return []
    for result in sets:
        if not isinstance(result, Mapping):
            continue
        headers, rows = result.get("headers"), result.get("rowSet")
        if isinstance(headers, list) and isinstance(rows, list):
            names = [str(field) for field in headers]
            return [dict(zip(names, row, strict=True)) for row in rows]
    return []


def box_score_v3_spec(game_id: str) -> RequestSpec:
    endpoint = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id, get_request=False)
    return RequestSpec(endpoint.endpoint, endpoint.parameters, contract_version=2)


def league_leaders_spec(season_id: int, category: str, per_mode: str = "PerGame") -> RequestSpec:
    endpoint = leagueleaders.LeagueLeaders(
        season=season_label(season_id),
        season_type_all_star="Regular Season",
        per_mode48=per_mode,
        scope="S",
        stat_category_abbreviation=category,
        get_request=False,
    )
    return RequestSpec(endpoint.endpoint, endpoint.parameters)


def parse_box_score_roster(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    box = payload.get("boxScoreTraditional")
    if not isinstance(box, Mapping):
        return []
    game_id = str(box.get("gameId") or "")
    output: list[dict[str, Any]] = []
    for team_key in ("homeTeam", "awayTeam"):
        team = box.get(team_key)
        if not isinstance(team, Mapping):
            continue
        roster_label = " ".join(
            str(team.get(field) or "").strip() for field in ("teamCity", "teamName")
        ).strip()
        players = team.get("players")
        if not isinstance(players, list):
            continue
        for player in players:
            if not isinstance(player, Mapping) or player.get("personId") is None:
                continue
            source_name = " ".join(
                str(player.get(field) or "").strip() for field in ("firstName", "familyName")
            ).strip()
            # Some legacy V3 box scores contain a blank, zero-stat placeholder
            # with a numeric personId. It is not defensible player evidence.
            if not source_name:
                continue
            output.append(
                {
                    "game_id": game_id,
                    "nba_player_id": str(player["personId"]),
                    "source_roster_label": roster_label,
                    "source_comment": str(player.get("comment") or "").strip() or None,
                    "source_name": source_name,
                }
            )
    return sorted(output, key=lambda row: (row["game_id"], row["nba_player_id"]))


def nullable_sum(values: Sequence[int | float | None]) -> int | float | None:
    observed = [value for value in values if value is not None]
    if not observed:
        return None
    return sum(observed)


def parse_minutes(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and ":" in value:
        minutes, seconds = value.split(":", 1)
        return int(minutes) + int(seconds) / 60
    if not isinstance(value, int | float | str):
        return None
    parsed = float(value)
    return parsed if parsed >= 0 else None


@dataclass(frozen=True)
class DerivedLeaderSet:
    raw_per_game: frozenset[str]
    raw_total: frozenset[str]
    qualified: frozenset[str]
    per_game_values: Mapping[str, float]
    total_values: Mapping[str, float]
    qualification_status: str


def _max_player_ids(rows: Sequence[Mapping[str, Any]], field: str) -> frozenset[str]:
    observed = [
        (str(row["player_id"]), float(row[field])) for row in rows if row.get(field) is not None
    ]
    if not observed:
        return frozenset()
    maximum = max(value for _, value in observed)
    return frozenset(player for player, value in observed if value == maximum)


def derive_leaders(
    rows: Sequence[Mapping[str, Any]],
    category: str,
    *,
    games_threshold: int,
    coverage_reliable: bool,
) -> DerivedLeaderSet:
    per_game_field, total_field = CATEGORY_FIELDS[category]
    raw_per_game = _max_player_ids(rows, per_game_field)
    raw_total = _max_player_ids(rows, total_field)
    qualified_rows = [row for row in rows if int(row.get("games_played") or 0) >= games_threshold]
    qualified = (
        _max_player_ids(qualified_rows, per_game_field) if coverage_reliable else frozenset()
    )
    return DerivedLeaderSet(
        raw_per_game=raw_per_game,
        raw_total=raw_total,
        qualified=qualified,
        per_game_values={
            str(row["player_id"]): float(row[per_game_field])
            for row in rows
            if row.get(per_game_field) is not None
        },
        total_values={
            str(row["player_id"]): float(row[total_field])
            for row in rows
            if row.get(total_field) is not None
        },
        qualification_status=(
            "PROJECT_QUALIFIED_POPULATION" if coverage_reliable else "DERIVED_COVERAGE_BLOCKED"
        ),
    )


def reconcile_leader_sets(
    source_ids: frozenset[str], derived_ids: frozenset[str], *, source_available: bool
) -> str:
    if not source_available:
        return "SOURCE_COVERAGE_GAP"
    if not derived_ids:
        return "DERIVED_COVERAGE_GAP"
    if source_ids == derived_ids:
        return "TIE_MATCH" if len(source_ids) > 1 else "EXACT_MATCH"
    if source_ids & derived_ids:
        return "VALUE_MATCH"
    return "QUALIFICATION_DIFFERENCE"


def all_star_reconciliation_class(*, award: bool | None, roster: bool, played: bool) -> str:
    if award is None:
        return "NOT_QUERIED + " + ("ROSTER + PLAYED" if played else "ROSTER")
    if award and roster and played:
        return "AWARD + ROSTER + PLAYED"
    if award and roster:
        return "AWARD + ROSTER + DID_NOT_PLAY"
    if award:
        return "AWARD + NO_ROSTER_EVIDENCE"
    if played:
        return "PLAYED + NO_AWARD_EVENT"
    return "ROSTER + NO_AWARD_EVENT"


def career_count_rows(
    all_star_rows: Sequence[Mapping[str, Any]],
    stat_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_star_by_player: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in all_star_rows:
        all_star_by_player[str(row["player_id"])].append(row)
    all_star = []
    for player_id, rows in sorted(all_star_by_player.items()):
        award_values = [row.get("playerawards_evidence") for row in rows]
        all_star.append(
            {
                "player_id": player_id,
                "nba_player_id": str(rows[0]["nba_player_id"]),
                "all_star_event_roster_seasons": sum(bool(row["roster_evidence"]) for row in rows),
                "all_star_games_participated": sum(
                    int(row["all_star_games_played"]) for row in rows
                ),
                "all_star_playerawards_events": (
                    None
                    if all(value is None for value in award_values)
                    else sum(value is True for value in award_values)
                ),
                "methodology_version": ACCOLADE_COMPLETION_METHODOLOGY_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    stat_by_player: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in stat_rows:
        stat_by_player[str(row["player_id"])].append(row)
    stat = []
    for player_id, rows in sorted(stat_by_player.items()):
        item: dict[str, Any] = {
            "player_id": player_id,
            "nba_player_id": str(rows[0]["nba_player_id"]),
            "methodology_version": ACCOLADE_COMPLETION_METHODOLOGY_VERSION,
            "corpus_id": CORPUS_ID,
        }
        for category in CATEGORY_FIELDS:
            selected = [row for row in rows if row["stat_category"] == category]
            item[f"{category.lower()}_official_source_rank_one_count"] = sum(
                row.get("official_source_rank") == 1 for row in selected
            )
            item[f"{category.lower()}_derived_qualified_leader_count"] = sum(
                bool(row.get("is_derived_qualified_leader")) for row in selected
            )
        stat.append(item)
    return all_star, stat
