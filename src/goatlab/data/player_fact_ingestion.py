"""Deterministic Bronze-to-Silver player-fact pilot helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from goatlab.data.canonical import canonical_id, normalize_season_type, parse_season_label
from goatlab.data.nba_api_client import RequestOutcome, RequestResult
from goatlab.data.nba_api_probe import INTRODUCTION_SEASON, nba_api_source_id, result_rows
from goatlab.schemas import (
    PlayerGameStats,
    PlayerSeasonAdvanced,
    PlayerSeasonStats,
    SeasonRowScope,
)

METRICS = {
    "minutes": "MIN", "points": "PTS", "fgm": "FGM", "fga": "FGA",
    "fg3m": "FG3M", "fg3a": "FG3A", "ftm": "FTM", "fta": "FTA",
    "oreb": "OREB", "dreb": "DREB", "rebounds": "REB", "assists": "AST",
    "steals": "STL", "blocks": "BLK", "turnovers": "TOV",
    "personal_fouls": "PF", "plus_minus": "PLUS_MINUS",
    "started": "STARTED", "did_play": "DID_PLAY",
}
INTRODUCED = {**INTRODUCTION_SEASON, "STARTED": 1970}
TOTALS = {
    "minutes": "minutes_total", "points": "points_total", "fgm": "fgm_total",
    "fga": "fga_total", "fg3m": "fg3m_total", "fg3a": "fg3a_total",
    "ftm": "ftm_total", "fta": "fta_total", "oreb": "oreb_total",
    "dreb": "dreb_total", "rebounds": "rebounds_total", "assists": "assists_total",
    "steals": "steals_total", "blocks": "blocks_total",
    "turnovers": "turnovers_total", "personal_fouls": "personal_fouls_total",
}


class CoverageClass(StrEnum):
    RELIABLE = "RELIABLE"
    PARTIAL = "PARTIAL"
    SPARSE = "SPARSE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CoverageThresholds:
    reliable_min: float = 0.99
    partial_min: float = 0.80

    def __post_init__(self) -> None:
        if not 0 <= self.partial_min <= self.reliable_min <= 1:
            raise ValueError("coverage thresholds must satisfy 0 <= partial <= reliable <= 1")


@dataclass(frozen=True)
class IdentityResolution:
    nba_player_id: str
    player_id: str
    diagnostic_name: str | None
    resolution: str
    source_id: str


@dataclass(frozen=True)
class TeamResolution:
    nba_team_id: str
    team_id: str
    franchise_id: str
    team_name: str
    abbreviation: str | None
    first_pilot_season: int
    last_pilot_season: int
    legacy_id_match: bool
    stale_window_conflict: bool
    source_id: str


def normalized_bronze_artifact(
    result: RequestResult,
    *,
    season: str,
    season_type: str,
    retrieved_at: datetime,
    measure_type: str | None = None,
    per_mode: str | None = None,
) -> dict[str, Any]:
    fields, rows = result_rows(result.payload)
    if result.outcome not in {
        RequestOutcome.SUCCESS_WITH_ROWS,
        RequestOutcome.SUCCESS_EMPTY,
    }:
        raise ValueError(f"cannot normalize unsuccessful acquisition: {result.outcome.value}")
    return {
        "endpoint": result.endpoint,
        "season": season,
        "season_type": season_type,
        "measure_type": measure_type,
        "per_mode": per_mode,
        "request_parameters": dict(sorted(result.parameters.items())),
        "retrieval_timestamp": retrieved_at.isoformat().replace("+00:00", "Z"),
        "source_status": result.outcome.value,
        "row_count": len(rows),
        "fields": fields,
        "cache_key": result.cache_key,
        "content_sha256": result.response_sha256,
        "source_id": nba_api_source_id(result),
    }


def resolve_player_identities(
    rows: Sequence[Mapping[str, Any]], legacy_ids: set[str], *, source_id: str
) -> tuple[dict[str, IdentityResolution], dict[str, Any]]:
    names: dict[str, set[str]] = defaultdict(set)
    missing = 0
    for row in rows:
        value = row.get("PLAYER_ID")
        if value is None or not str(value).strip():
            missing += 1
            continue
        nba_id = str(value)
        names.setdefault(nba_id, set())
        if row.get("PLAYER_NAME"):
            names[nba_id].add(str(row["PLAYER_NAME"]).strip())
    resolved: dict[str, IdentityResolution] = {}
    for nba_id, variants in sorted(names.items()):
        resolved[nba_id] = IdentityResolution(
            nba_player_id=nba_id,
            player_id=canonical_id("player", "nba", nba_id),
            diagnostic_name=sorted(variants)[0] if variants else None,
            resolution="LEGACY_MATCH" if nba_id in legacy_ids else "NBA_API_PROVISIONAL",
            source_id=source_id,
        )
    provisional = [value for value in resolved.values() if value.resolution != "LEGACY_MATCH"]
    return resolved, {
        "business_key": "official NBA PLAYER_ID",
        "source_rows": len(rows),
        "distinct_player_ids": len(resolved),
        "legacy_matches": len(resolved) - len(provisional),
        "legacy_match_rate": (
            round((len(resolved) - len(provisional)) / len(resolved), 8) if resolved else 0.0
        ),
        "nba_api_provisional": len(provisional),
        "missing_id_rows": missing,
        "unresolved": 0,
        "name_variant_conflicts": [
            {"nba_player_id": key, "diagnostic_names": sorted(value)}
            for key, value in sorted(names.items()) if len(value) > 1
        ],
        "provisional_identities": [asdict(value) for value in provisional],
    }


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not result:
        raise ValueError("team name must be non-empty")
    return result


def build_team_crosswalk(
    rows: Sequence[Mapping[str, Any]],
    legacy_ids: set[str],
    legacy_windows: Mapping[str, Sequence[tuple[int, int | None]]],
    *,
    source_id: str,
) -> tuple[dict[tuple[str, str], TeamResolution], dict[str, Any]]:
    observed: dict[tuple[str, str], dict[str, set[Any]]] = {}
    missing = 0
    for row in rows:
        if row.get("TEAM_ID") is None or row.get("TEAM_NAME") is None:
            missing += 1
            continue
        nba_id, name = str(row["TEAM_ID"]), str(row["TEAM_NAME"]).strip()
        season = parse_season_label(str(row["SEASON_YEAR"]))
        item = observed.setdefault((nba_id, name), {"seasons": set(), "abbreviations": set()})
        item["seasons"].add(season)
        if row.get("TEAM_ABBREVIATION"):
            item["abbreviations"].add(str(row["TEAM_ABBREVIATION"]))
    crosswalk: dict[tuple[str, str], TeamResolution] = {}
    conflicts: list[dict[str, Any]] = []
    for (nba_id, name), item in sorted(observed.items()):
        seasons = sorted(int(value) for value in item["seasons"])
        windows = legacy_windows.get(nba_id, ())
        uncovered = [
            year for year in seasons
            if not any(start <= year and (end is None or year <= end) for start, end in windows)
        ]
        abbreviations = sorted(str(value) for value in item["abbreviations"])
        resolution = TeamResolution(
            nba_team_id=nba_id,
            team_id=canonical_id("team", "nba", f"{nba_id}:{_slug(name)}"),
            franchise_id=canonical_id("franchise", "nba", nba_id),
            team_name=name,
            abbreviation=abbreviations[0] if len(abbreviations) == 1 else None,
            first_pilot_season=seasons[0],
            last_pilot_season=seasons[-1],
            legacy_id_match=nba_id in legacy_ids,
            stale_window_conflict=bool(windows and uncovered),
            source_id=source_id,
        )
        crosswalk[(nba_id, name)] = resolution
        if resolution.stale_window_conflict:
            conflicts.append({
                "nba_team_id": nba_id,
                "team_name": name,
                "official_seasons_outside_legacy_windows": uncovered,
                "legacy_windows": [list(window) for window in windows],
                "resolution": "official TEAM_ID and observed name version retained",
            })
    source_ids = {key[0] for key in crosswalk}
    return crosswalk, {
        "business_key": "official NBA TEAM_ID plus observed name-version evidence",
        "distinct_source_team_ids": len(source_ids),
        "canonical_team_versions": len(crosswalk),
        "legacy_id_matches": len(source_ids & legacy_ids),
        "unmatched_team_ids": sorted(source_ids - legacy_ids),
        "stale_window_conflicts": conflicts,
        "missing_identity_rows": missing,
        "unresolved": 0,
        "crosswalk": [asdict(value) for value in crosswalk.values()],
    }


def map_player_game_row(
    row: Mapping[str, Any],
    result: RequestResult,
    identities: Mapping[str, IdentityResolution],
    teams: Mapping[tuple[str, str], TeamResolution],
    *,
    season: str,
    season_type: str,
    updated_at: datetime,
) -> PlayerGameStats:
    season_id = parse_season_label(season)
    identity = identities.get(str(row["PLAYER_ID"]))
    team = teams.get((str(row["TEAM_ID"]), str(row["TEAM_NAME"])))
    if identity is None:
        raise ValueError(f"unresolved NBA player ID: {row['PLAYER_ID']}")
    if team is None:
        raise ValueError(f"unresolved NBA team version: {row['TEAM_ID']}")

    def value(field: str) -> Any:
        return row.get(field) if season_id >= INTRODUCED.get(field, 1946) else None

    return PlayerGameStats(
        game_id=canonical_id("game", "nba", str(row["GAME_ID"])),
        player_id=identity.player_id,
        team_id=team.team_id,
        season_id=season_id,
        season_type=normalize_season_type(season_type),
        minutes=value("MIN"), points=value("PTS"), fgm=value("FGM"), fga=value("FGA"),
        fg3m=value("FG3M"), fg3a=value("FG3A"), ftm=value("FTM"), fta=value("FTA"),
        oreb=value("OREB"), dreb=value("DREB"), rebounds=value("REB"),
        assists=value("AST"), steals=value("STL"), blocks=value("BLK"),
        turnovers=value("TOV"), personal_fouls=value("PF"),
        plus_minus=value("PLUS_MINUS"), started=None, did_play=True,
        source_id=nba_api_source_id(result), updated_at=updated_at,
    )


def classify_coverage(
    *, row_count: int, non_null_count: int, historically_available: bool,
    source_supported: bool, thresholds: CoverageThresholds,
) -> CoverageClass:
    if not source_supported or not historically_available:
        return CoverageClass.UNAVAILABLE
    if row_count == 0 or non_null_count == 0:
        return CoverageClass.UNKNOWN
    ratio = non_null_count / row_count
    if ratio >= thresholds.reliable_min:
        return CoverageClass.RELIABLE
    if ratio >= thresholds.partial_min:
        return CoverageClass.PARTIAL
    return CoverageClass.SPARSE


def empirical_metric_coverage(
    records: Sequence[PlayerGameStats], *, season: str, season_type: str,
    thresholds: CoverageThresholds,
) -> list[dict[str, Any]]:
    year = parse_season_label(season)
    output: list[dict[str, Any]] = []
    for metric, source_field in METRICS.items():
        values = [getattr(record, metric) for record in records]
        non_null = [value for value in values if value is not None]
        introduced = INTRODUCED.get(source_field)
        available = introduced is None or year >= introduced
        supported = source_field != "STARTED"
        classification = classify_coverage(
            row_count=len(records), non_null_count=len(non_null),
            historically_available=available, source_supported=supported,
            thresholds=thresholds,
        )
        zero_count = sum(value == 0 for value in non_null)
        players = {
            record.player_id for record, value in zip(records, values, strict=True)
            if value is not None
        }
        output.append({
            "season": season,
            "season_id": year,
            "season_type": normalize_season_type(season_type).value,
            "canonical_metric": metric,
            "source_field": source_field,
            "source_endpoint": "playergamelogs",
            "row_count": len(records),
            "non_null_count": len(non_null),
            "null_count": len(records) - len(non_null),
            "non_null_percentage": round(len(non_null) / len(records), 8) if records else None,
            "observed_zero_count": zero_count,
            "observed_zero_percentage": (
                round(zero_count / len(non_null), 8) if non_null else None
            ),
            "distinct_players_represented": len(players),
            "documented_introduction_season": introduced,
            "documented_historical_status": (
                "SOURCE_UNSUPPORTED" if not supported else
                "HISTORICALLY_UNAVAILABLE" if not available else "AVAILABLE_OR_UNSPECIFIED"
            ),
            "classification": classification.value,
        })
    return output


def _sum_complete(
    records: Sequence[PlayerGameStats], field: str, *, qualified: bool
) -> int | float | None:
    values = [getattr(record, field) for record in records]
    if not qualified or not values or any(value is None for value in values):
        return None
    return float(sum(float(value) for value in values if value is not None))


def _rate(total: int | float | None, games: int) -> float | None:
    return round(float(total) / games, 12) if total is not None and games else None


def _pct(made: int | None, attempted: int | None) -> float | None:
    if made is None or attempted is None or attempted == 0:
        return None
    return round(made / attempted, 12)


def aggregate_player_seasons(
    records: Sequence[PlayerGameStats], coverage: Sequence[Mapping[str, Any]],
    *, updated_at: datetime,
) -> list[PlayerSeasonStats]:
    if not records:
        return []
    year, kind = records[0].season_id, records[0].season_type
    if any(record.season_id != year or record.season_type != kind for record in records):
        raise ValueError("aggregation input must contain one season/type partition")
    reliable = {
        str(item["canonical_metric"]) for item in coverage
        if item["classification"] == CoverageClass.RELIABLE.value
    }
    team_groups: dict[tuple[str, str], list[PlayerGameStats]] = defaultdict(list)
    total_groups: dict[str, list[PlayerGameStats]] = defaultdict(list)
    for record in records:
        team_groups[(record.player_id, record.team_id)].append(record)
        total_groups[record.player_id].append(record)
    groups = [
        (player, team, SeasonRowScope.TEAM, values)
        for (player, team), values in sorted(team_groups.items())
    ] + [
        (player, None, SeasonRowScope.TOTAL, values)
        for player, values in sorted(total_groups.items())
    ]
    source_id = f"derived:nba_api:player_game_stats:v1:{year}:{kind.value}"
    output: list[PlayerSeasonStats] = []
    for player, team, scope, values in groups:
        games = len({record.game_id for record in values})
        totals = {
            target: _sum_complete(values, metric, qualified=metric in reliable)
            for metric, target in TOTALS.items()
        }
        integers = {
            key: int(value) if value is not None else None
            for key, value in totals.items() if key != "minutes_total"
        }
        minutes = float(totals["minutes_total"]) if totals["minutes_total"] is not None else None
        output.append(PlayerSeasonStats(
            player_id=player, season_id=year, season_type=kind, row_scope=scope, team_id=team,
            games_played=games, games_started=None, minutes_total=minutes,
            points_total=integers["points_total"], fgm_total=integers["fgm_total"],
            fga_total=integers["fga_total"], fg3m_total=integers["fg3m_total"],
            fg3a_total=integers["fg3a_total"], ftm_total=integers["ftm_total"],
            fta_total=integers["fta_total"], oreb_total=integers["oreb_total"],
            dreb_total=integers["dreb_total"], rebounds_total=integers["rebounds_total"],
            assists_total=integers["assists_total"], steals_total=integers["steals_total"],
            blocks_total=integers["blocks_total"], turnovers_total=integers["turnovers_total"],
            personal_fouls_total=integers["personal_fouls_total"],
            minutes_per_game=_rate(minutes, games),
            points_per_game=_rate(integers["points_total"], games),
            rebounds_per_game=_rate(integers["rebounds_total"], games),
            assists_per_game=_rate(integers["assists_total"], games),
            steals_per_game=_rate(integers["steals_total"], games),
            blocks_per_game=_rate(integers["blocks_total"], games),
            turnovers_per_game=_rate(integers["turnovers_total"], games),
            fg_pct=_pct(integers["fgm_total"], integers["fga_total"]),
            fg3_pct=_pct(integers["fg3m_total"], integers["fg3a_total"]),
            ft_pct=_pct(integers["ftm_total"], integers["fta_total"]),
            source_id=source_id, updated_at=updated_at,
        ))
    return output


RECON_FIELDS = {
    "GP": ("games_played", 0.0), "MIN": ("minutes_total", 0.01),
    "PTS": ("points_total", 0.0), "FGM": ("fgm_total", 0.0),
    "FGA": ("fga_total", 0.0), "FG3M": ("fg3m_total", 0.0),
    "FG3A": ("fg3a_total", 0.0), "FTM": ("ftm_total", 0.0),
    "FTA": ("fta_total", 0.0), "OREB": ("oreb_total", 0.0),
    "DREB": ("dreb_total", 0.0), "REB": ("rebounds_total", 0.0),
    "AST": ("assists_total", 0.0), "STL": ("steals_total", 0.0),
    "BLK": ("blocks_total", 0.0), "TOV": ("turnovers_total", 0.0),
    "PF": ("personal_fouls_total", 0.0), "FG_PCT": ("fg_pct", 0.0005),
    "FG3_PCT": ("fg3_pct", 0.0005), "FT_PCT": ("ft_pct", 0.0005),
}


def reconcile_base_totals(
    derived: Sequence[PlayerSeasonStats], raw_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    totals = {row.player_id: row for row in derived if row.row_scope is SeasonRowScope.TOTAL}
    official = {canonical_id("player", "nba", str(row["PLAYER_ID"])): row for row in raw_rows}
    fields: dict[str, dict[str, int]] = {}
    examples: list[dict[str, Any]] = []
    exact = tolerant = mismatched = compared = 0
    for source, (canonical, tolerance) in RECON_FIELDS.items():
        counts = {
            "compared": 0, "exact_matches": 0, "tolerance_matches": 0,
            "mismatches": 0, "missing_derived": 0, "missing_official": 0,
        }
        for player_id in sorted(set(totals) | set(official)):
            left = getattr(totals[player_id], canonical) if player_id in totals else None
            right = official.get(player_id, {}).get(source)
            if left is None:
                counts["missing_derived"] += 1
                continue
            if right is None:
                counts["missing_official"] += 1
                continue
            counts["compared"] += 1
            compared += 1
            difference = abs(float(left) - float(right))
            if difference == 0:
                counts["exact_matches"] += 1
                exact += 1
            elif difference <= tolerance + 1e-12:
                counts["tolerance_matches"] += 1
                tolerant += 1
            else:
                counts["mismatches"] += 1
                mismatched += 1
                if len(examples) < 25:
                    examples.append({
                        "player_id": player_id, "source_field": source,
                        "canonical_field": canonical, "derived": left, "official": right,
                        "absolute_difference": round(difference, 12), "tolerance": tolerance,
                    })
        fields[source] = counts
    rate = (exact + tolerant) / compared if compared else 0.0
    return {
        "derived_total_players": len(totals), "official_total_players": len(official),
        "shared_players": len(set(totals) & set(official)),
        "derived_only_players": sorted(set(totals) - set(official)),
        "official_only_players": sorted(set(official) - set(totals)),
        "compared_values": compared, "exact_matches": exact,
        "tolerance_matches": tolerant, "mismatches": mismatched,
        "match_rate": round(rate, 8), "passes_v1_gate": compared > 0 and rate >= 0.99,
        "fields": fields, "mismatch_examples": examples,
        "known_semantic_differences": [
            "NBA Base percentages are rounded; derived percentages use summed makes/attempts.",
            "NBA Base minutes may retain precision absent from older game logs.",
            "Fields without RELIABLE game-row coverage are intentionally not compared.",
        ],
    }


def quality_gates(
    raw_rows: Sequence[Mapping[str, Any]], records: Sequence[PlayerGameStats],
    identities: Mapping[str, IdentityResolution],
    teams: Mapping[tuple[str, str], TeamResolution],
    coverage: Sequence[Mapping[str, Any]], *, season: str, season_type: str,
) -> dict[str, Any]:
    keys = [(row.game_id, row.player_id, row.team_id) for row in records]
    player_ids = {item.player_id for item in identities.values()}
    team_ids = {item.team_id for item in teams.values()}
    game_ids = {canonical_id("game", "nba", str(row["GAME_ID"])) for row in raw_rows}
    counts = (
        "points", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb",
        "rebounds", "assists", "steals", "blocks", "turnovers", "personal_fouls",
    )
    negative = sum(
        1 for record in records for field in counts
        if (value := getattr(record, field)) is not None and value < 0
    )
    shooting = sum(
        1 for row in records for made, attempted in
        ((row.fgm, row.fga), (row.fg3m, row.fg3a), (row.ftm, row.fta))
        if made is not None and attempted is not None and made > attempted
    )
    reliable = {
        str(item["canonical_metric"]) for item in coverage
        if item["classification"] == CoverageClass.RELIABLE.value
    }
    rebound_errors = 0
    if {"oreb", "dreb", "rebounds"} <= reliable:
        rebound_errors = sum(
            1 for row in records
            if row.oreb is not None and row.dreb is not None and row.rebounds is not None
            and row.oreb + row.dreb != row.rebounds
        )
    year = parse_season_label(season)
    start, end = date(year, 7, 1), date(year + 1, 6, 30)
    outside = sum(
        not (start <= datetime.fromisoformat(str(row["GAME_DATE"])).date() <= end)
        for row in raw_rows
    )
    by_key = {(row.game_id, row.player_id, row.team_id): row for row in records}
    null_to_zero = 0
    for raw in raw_rows:
        identity = identities.get(str(raw["PLAYER_ID"]))
        team = teams.get((str(raw["TEAM_ID"]), str(raw["TEAM_NAME"])))
        if identity is None or team is None:
            continue
        mapped = by_key.get((
            canonical_id("game", "nba", str(raw["GAME_ID"])), identity.player_id, team.team_id
        ))
        if mapped is None:
            continue
        for metric, source in METRICS.items():
            if source in {"STARTED", "DID_PLAY"}:
                continue
            unavailable = raw.get(source) is None or year < INTRODUCED.get(source, 1946)
            if unavailable and getattr(mapped, metric) == 0:
                null_to_zero += 1
    return {
        "season": season, "season_type": normalize_season_type(season_type).value,
        "source_rows": len(raw_rows), "silver_rows": len(records),
        "duplicate_player_game_keys": sum(
            count - 1 for count in Counter(keys).values() if count > 1
        ),
        "orphan_player_ids": sum(row.player_id not in player_ids for row in records),
        "orphan_team_ids": sum(row.team_id not in team_ids for row in records),
        "orphan_game_ids": sum(row.game_id not in game_ids for row in records),
        "invalid_season_labels": 0, "invalid_season_types": 0,
        "negative_box_score_counts": negative,
        "impossible_shooting_relationships": shooting,
        "rebound_inconsistencies_under_reliable_coverage": rebound_errors,
        "game_dates_outside_expected_window": outside,
        "null_to_zero_violations": null_to_zero,
        "missing_source_provenance": sum(not row.source_id for row in records),
    }


PLAYER_GAME_SCHEMA = pa.schema([
    ("game_id", pa.string()), ("player_id", pa.string()), ("team_id", pa.string()),
    ("season_id", pa.int64()), ("season_type", pa.string()), ("minutes", pa.float64()),
    ("points", pa.int64()), ("fgm", pa.int64()), ("fga", pa.int64()),
    ("fg3m", pa.int64()), ("fg3a", pa.int64()), ("ftm", pa.int64()),
    ("fta", pa.int64()), ("oreb", pa.int64()), ("dreb", pa.int64()),
    ("rebounds", pa.int64()), ("assists", pa.int64()), ("steals", pa.int64()),
    ("blocks", pa.int64()), ("turnovers", pa.int64()), ("personal_fouls", pa.int64()),
    ("plus_minus", pa.float64()), ("started", pa.bool_()), ("did_play", pa.bool_()),
    ("source_id", pa.string()), ("updated_at", pa.timestamp("us", tz="UTC")),
])
PLAYER_SEASON_SCHEMA = pa.schema([
    ("player_id", pa.string()), ("season_id", pa.int64()), ("season_type", pa.string()),
    ("row_scope", pa.string()), ("team_id", pa.string()), ("games_played", pa.int64()),
    ("games_started", pa.int64()), ("minutes_total", pa.float64()),
    ("points_total", pa.int64()), ("fgm_total", pa.int64()), ("fga_total", pa.int64()),
    ("fg3m_total", pa.int64()), ("fg3a_total", pa.int64()), ("ftm_total", pa.int64()),
    ("fta_total", pa.int64()), ("oreb_total", pa.int64()), ("dreb_total", pa.int64()),
    ("rebounds_total", pa.int64()), ("assists_total", pa.int64()),
    ("steals_total", pa.int64()), ("blocks_total", pa.int64()),
    ("turnovers_total", pa.int64()), ("personal_fouls_total", pa.int64()),
    ("minutes_per_game", pa.float64()), ("points_per_game", pa.float64()),
    ("rebounds_per_game", pa.float64()), ("assists_per_game", pa.float64()),
    ("steals_per_game", pa.float64()), ("blocks_per_game", pa.float64()),
    ("turnovers_per_game", pa.float64()), ("fg_pct", pa.float64()),
    ("fg3_pct", pa.float64()), ("ft_pct", pa.float64()), ("source_id", pa.string()),
    ("updated_at", pa.timestamp("us", tz="UTC")),
])
PLAYER_ADVANCED_SCHEMA = pa.schema([
    ("player_id", pa.string()), ("season_id", pa.int64()), ("season_type", pa.string()),
    ("row_scope", pa.string()), ("team_id", pa.string()), ("games_played", pa.int64()),
    ("minutes", pa.float64()), ("offensive_rating", pa.float64()),
    ("defensive_rating", pa.float64()), ("net_rating", pa.float64()),
    ("pace", pa.float64()), ("usage_pct", pa.float64()),
    ("true_shooting_pct", pa.float64()), ("effective_fg_pct", pa.float64()),
    ("assist_pct", pa.float64()), ("oreb_pct", pa.float64()), ("dreb_pct", pa.float64()),
    ("rebound_pct", pa.float64()), ("turnover_pct", pa.float64()), ("pie", pa.float64()),
    ("possessions", pa.float64()), ("source_id", pa.string()),
    ("updated_at", pa.timestamp("us", tz="UTC")),
])


def write_deterministic_parquet(
    records: Sequence[PlayerGameStats | PlayerSeasonStats | PlayerSeasonAdvanced],
    path: Path, schema: pa.Schema, *, sort_fields: Sequence[str],
) -> dict[str, Any]:
    rows = [record.model_dump(mode="python") for record in records]
    rows.sort(key=lambda row: tuple(str(row.get(field) or "") for field in sort_fields))
    table = pa.Table.from_pylist(rows, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(
        table, temporary, compression="zstd", compression_level=9,
        use_dictionary=False, write_statistics=True, data_page_version="1.0",
    )
    temporary.replace(path)
    return {
        "path": str(path), "rows": table.num_rows, "columns": table.num_columns,
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def write_stable_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
