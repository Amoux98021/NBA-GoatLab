"""Factual historical player-season recovery helpers for STEP-0015F."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from nba_api.stats.endpoints import playercareerstats  # type: ignore[import-untyped]

from goatlab.data.nba_api_client import RequestSpec

HISTORICAL_RECOVERY_VERSION = "goatlab-historical-player-season-facts-v2-research"


class MissingReason(StrEnum):
    HISTORICALLY_NOT_RECORDED = "HISTORICALLY_NOT_RECORDED"
    SOURCE_NOT_INGESTED = "SOURCE_NOT_INGESTED"
    DERIVABLE_FROM_OBSERVED_FACTS = "DERIVABLE_FROM_OBSERVED_FACTS"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PIPELINE_BUG = "PIPELINE_BUG"


INTRODUCTION_SEASONS: dict[str, int] = {
    "GP": 1946,
    "PTS": 1946,
    "FGM": 1946,
    "FGA": 1946,
    "FG_PCT": 1946,
    "FTM": 1946,
    "FTA": 1946,
    "FT_PCT": 1946,
    "AST": 1946,
    "PF": 1946,
    "REB": 1950,
    "MIN": 1951,
    "OREB": 1973,
    "DREB": 1973,
    "STL": 1973,
    "BLK": 1973,
    "TOV": 1977,
}

CAREER_FIELDS = (
    "GP",
    "MIN",
    "PTS",
    "FGM",
    "FGA",
    "FG_PCT",
    "FTM",
    "FTA",
    "FT_PCT",
    "OREB",
    "DREB",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "PF",
)


def player_career_stats_spec(nba_player_id: str) -> RequestSpec:
    endpoint = playercareerstats.PlayerCareerStats(
        player_id=nba_player_id,
        per_mode36="Totals",
        get_request=False,
    )
    return RequestSpec(endpoint.endpoint, endpoint.parameters, contract_version=1)


def named_result_rows(payload: Mapping[str, Any] | None, name: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    raw_sets = payload.get("resultSets", [])
    if not isinstance(raw_sets, list):
        return []
    for result in raw_sets:
        if not isinstance(result, Mapping) or result.get("name") != name:
            continue
        headers, rows = result.get("headers"), result.get("rowSet")
        if not isinstance(headers, list) or not isinstance(rows, list):
            return []
        names = [str(field) for field in headers]
        return [dict(zip(names, row, strict=True)) for row in rows]
    return []


def canonical_regular_season_rows(
    rows: Sequence[Mapping[str, Any]], *, nba_player_id: str
) -> list[dict[str, Any]]:
    """Select one exact NBA/BAA total row per season, preserving trade semantics."""
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("PLAYER_ID")) != nba_player_id:
            raise ValueError("PlayerCareerStats identity differs from requested PlayerID")
        if str(row.get("LEAGUE_ID")) != "00" or not row.get("SEASON_ID"):
            continue
        groups[str(row["SEASON_ID"])].append(row)
    output: list[dict[str, Any]] = []
    for season, members in sorted(groups.items()):
        total = [
            row
            for row in members
            if str(row.get("TEAM_ID")) == "0" or str(row.get("TEAM_ABBREVIATION")) == "TOT"
        ]
        if len(total) > 1:
            raise ValueError(f"multiple total rows for {nba_player_id} {season}")
        if total:
            chosen = total[0]
            method = "AUTHORITATIVE_TOTAL_ROW"
        elif len(members) == 1:
            chosen = members[0]
            method = "SINGLE_TEAM_ROW"
        else:
            # The endpoint normally supplies a TOTAL row for traded seasons. Refuse to sum an
            # unexpected contract because doing so could double count an already aggregated row.
            raise ValueError(f"ambiguous traded season without total row: {nba_player_id} {season}")
        item = {field: chosen.get(field) for field in CAREER_FIELDS}
        item.update(
            {
                "PLAYER_ID": nba_player_id,
                "SEASON_ID": season,
                "selection_method": method,
                "source_team_id": chosen.get("TEAM_ID"),
                "source_team_abbreviation": chosen.get("TEAM_ABBREVIATION"),
            }
        )
        output.append(item)
    return output


def safe_rate(total: int | float | None, games: int | float | None) -> float | None:
    if total is None or games is None or float(games) <= 0:
        return None
    return float(total) / float(games)


def safe_percentage(made: int | float | None, attempted: int | float | None) -> float | None:
    if made is None or attempted is None or float(attempted) <= 0:
        return None
    return float(made) / float(attempted)


def true_shooting_pct(
    points: int | float | None,
    fga: int | float | None,
    fta: int | float | None,
    *,
    free_throw_factor: float = 0.44,
) -> float | None:
    """Return the documented GOATLab/NBA-style TS estimate from observed totals."""
    if points is None or fga is None or fta is None:
        return None
    denominator = 2.0 * (float(fga) + free_throw_factor * float(fta))
    if denominator <= 0:
        return None
    value = float(points) / denominator
    return value if math.isfinite(value) else None


def missing_reason(field: str, season_id: int, source_value: object) -> MissingReason | None:
    introduced = INTRODUCTION_SEASONS[field]
    if season_id < introduced:
        return MissingReason.HISTORICALLY_NOT_RECORDED
    if source_value is None:
        return MissingReason.SOURCE_UNAVAILABLE
    return None


def reconcile_number(left: Any, right: Any, *, tolerance: float = 0.0) -> str:
    if left is None or right is None:
        return "NOT_COMPARED"
    return "MATCH" if abs(float(left) - float(right)) <= tolerance else "CONFLICT"
