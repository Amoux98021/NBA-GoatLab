"""Coverage-aware canonicalization for official NBA PlayerAwards events."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from goatlab.data.canonical import canonical_id
from goatlab.schemas import AwardScope, AwardTaxonomyStatus, AwardType, PlayerAward

AWARDS_METHODOLOGY_VERSION = "official-player-awards-canonical-v1"
NBA_AWARDS_SOURCE_ID = "nba_stats:playerawards:nba_api:1.11.4"


class AwardAcquisitionStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS_WITH_ROWS = "SUCCESS_WITH_ROWS"
    SUCCESS_EMPTY = "SUCCESS_EMPTY"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    NOT_QUERIED = "NOT_QUERIED"


@dataclass(frozen=True)
class AwardMapping:
    award_type: AwardType
    taxonomy_status: AwardTaxonomyStatus
    award_scope: AwardScope = AwardScope.LEAGUE
    notes: str = ""


RAW_AWARD_MAPPING: dict[str, AwardMapping] = {
    "NBA Most Valuable Player": AwardMapping(AwardType.MVP, AwardTaxonomyStatus.CANONICAL_CORE),
    "NBA Finals Most Valuable Player": AwardMapping(
        AwardType.FINALS_MVP, AwardTaxonomyStatus.CANONICAL_CORE
    ),
    "Eastern Conference Finals Most Valuable Player": AwardMapping(
        AwardType.CONFERENCE_FINALS_MVP, AwardTaxonomyStatus.CANONICAL_CORE, AwardScope.CONFERENCE
    ),
    "Western Conference Finals Most Valuable Player": AwardMapping(
        AwardType.CONFERENCE_FINALS_MVP, AwardTaxonomyStatus.CANONICAL_CORE, AwardScope.CONFERENCE
    ),
    "NBA Defensive Player of the Year": AwardMapping(
        AwardType.DPOY, AwardTaxonomyStatus.CANONICAL_CORE
    ),
    "All-NBA": AwardMapping(AwardType.ALL_NBA, AwardTaxonomyStatus.CANONICAL_CORE),
    "All-Defensive Team": AwardMapping(AwardType.ALL_DEFENSE, AwardTaxonomyStatus.CANONICAL_CORE),
    "NBA Rookie of the Year": AwardMapping(AwardType.ROY, AwardTaxonomyStatus.CANONICAL_SECONDARY),
    "NBA Most Improved Player": AwardMapping(
        AwardType.MIP, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "NBA Sixth Man of the Year": AwardMapping(
        AwardType.SIXTH_MAN, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "NBA Clutch Player of the Year": AwardMapping(
        AwardType.CLUTCH_PLAYER, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "NBA Comeback Player of the Year": AwardMapping(
        AwardType.COMEBACK_PLAYER, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "All-Rookie Team": AwardMapping(AwardType.ALL_ROOKIE, AwardTaxonomyStatus.CANONICAL_SECONDARY),
    "NBA All-Star": AwardMapping(AwardType.ALL_STAR, AwardTaxonomyStatus.CANONICAL_SECONDARY),
    "NBA All-Star Selection": AwardMapping(
        AwardType.ALL_STAR,
        AwardTaxonomyStatus.CANONICAL_SECONDARY,
        notes="observed source-string variant; roster semantics remain partial",
    ),
    "NBA All-Star Most Valuable Player": AwardMapping(
        AwardType.ALL_STAR_MVP, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "NBA Cup Most Valuable Player": AwardMapping(
        AwardType.NBA_CUP_MVP, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "NBA Cup All-Tournament Team": AwardMapping(
        AwardType.NBA_CUP_ALL_TOURNAMENT, AwardTaxonomyStatus.CANONICAL_SECONDARY
    ),
    "NBA Champion": AwardMapping(
        AwardType.NBA_CHAMPION, AwardTaxonomyStatus.CANONICAL_SECONDARY, AwardScope.TEAM
    ),
    "NBA Player of the Month": AwardMapping(
        AwardType.PLAYER_OF_MONTH, AwardTaxonomyStatus.MINOR_RECURRING
    ),
    "NBA Player of the Week": AwardMapping(
        AwardType.PLAYER_OF_WEEK, AwardTaxonomyStatus.MINOR_RECURRING
    ),
    "NBA Rookie of the Month": AwardMapping(
        AwardType.ROOKIE_OF_MONTH, AwardTaxonomyStatus.MINOR_RECURRING
    ),
    "NBA Defensive Player of the Month": AwardMapping(
        AwardType.DEFENSIVE_PLAYER_OF_MONTH, AwardTaxonomyStatus.MINOR_RECURRING
    ),
    "Hall of Fame Inductee": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
    "IBM Award": AwardMapping(AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE),
    "J. Walter Kennedy Citizenship": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE
    ),
    "NBA Sportsmanship": AwardMapping(AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE),
    "NBA Sporting News Most Valuable Player of the Year": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
    "NBA Sporting News Rookie of the Year": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
    "Olympic Gold Medal": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
    "Olympic Silver Medal": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
    "Olympic Bronze Medal": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
    "Olympic Appearance": AwardMapping(
        AwardType.OTHER, AwardTaxonomyStatus.NON_PLAYER_COMPETITIVE, AwardScope.EXTERNAL
    ),
}

STATISTICAL_TITLE_MAPPING = {
    "NBA Scoring Champion": AwardType.SCORING_TITLE,
    "NBA Rebounding Champion": AwardType.REBOUND_TITLE,
    "NBA Assists Leader": AwardType.ASSIST_TITLE,
    "NBA Steals Leader": AwardType.STEAL_TITLE,
    "NBA Blocks Leader": AwardType.BLOCK_TITLE,
}

KNOWN_INTRODUCTION_SEASONS: dict[AwardType, int] = {
    AwardType.MVP: 1955,
    AwardType.FINALS_MVP: 1968,
    AwardType.CONFERENCE_FINALS_MVP: 2021,
    AwardType.DPOY: 1982,
    AwardType.ROY: 1952,
    AwardType.MIP: 1985,
    AwardType.SIXTH_MAN: 1982,
    AwardType.CLUTCH_PLAYER: 2022,
    AwardType.COMEBACK_PLAYER: 1980,
    AwardType.ALL_NBA: 1946,
    AwardType.ALL_DEFENSE: 1968,
    AwardType.ALL_ROOKIE: 1962,
    AwardType.ALL_STAR: 1950,
    AwardType.ALL_STAR_MVP: 1950,
    AwardType.NBA_CUP_MVP: 2023,
    AwardType.NBA_CUP_ALL_TOURNAMENT: 2023,
}

_SEASON = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{2})$")


def clean_source_value(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def normalize_nba_player_id(value: object) -> str | None:
    """Normalize an NBA numeric business key without accepting names as identity."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else None
    cleaned = clean_source_value(value)
    if cleaned is None:
        return None
    if cleaned.isdigit():
        return cleaned
    if cleaned.endswith(".0") and cleaned[:-2].isdigit():
        return cleaned[:-2]
    return None


def parse_player_awards_payload(
    payload: Mapping[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    raw_sets = payload.get("resultSets", payload.get("resultSet", []))
    result_sets = [raw_sets] if isinstance(raw_sets, Mapping) else raw_sets
    if not isinstance(result_sets, list):
        raise ValueError("PlayerAwards payload result sets are malformed")
    selected: Mapping[str, Any] | None = None
    for item in result_sets:
        if not isinstance(item, Mapping):
            continue
        if item.get("name") == "PlayerAwards" or "PERSON_ID" in item.get("headers", []):
            selected = item
            break
    if selected is None:
        if result_sets:
            raise ValueError("PlayerAwards result set is absent")
        return [], []
    headers = [str(value) for value in selected.get("headers", [])]
    row_set = selected.get("rowSet", [])
    if not isinstance(row_set, list):
        raise ValueError("PlayerAwards rowSet is malformed")
    rows: list[dict[str, Any]] = []
    for raw_row in row_set:
        if not isinstance(raw_row, list) or len(raw_row) != len(headers):
            raise ValueError("PlayerAwards row width differs from headers")
        rows.append(dict(zip(headers, raw_row, strict=True)))
    return headers, rows


def normalize_award_season(raw: object) -> tuple[int | None, str | None, str]:
    label = clean_source_value(raw)
    if label is None:
        return None, None, "SEASON_MAPPING_UNKNOWN"
    match = _SEASON.fullmatch(label)
    if match is None:
        return None, label, "SEASON_MAPPING_UNKNOWN"
    start = int(match.group("start"))
    end = int(match.group("end"))
    if end != (start + 1) % 100:
        return None, label, "SEASON_MAPPING_UNKNOWN"
    return start, label, "MAPPED"


def mapping_for_description(description: object) -> AwardMapping:
    normalized = clean_source_value(description) or ""
    if normalized in RAW_AWARD_MAPPING:
        return RAW_AWARD_MAPPING[normalized]
    if normalized in STATISTICAL_TITLE_MAPPING:
        return AwardMapping(
            STATISTICAL_TITLE_MAPPING[normalized], AwardTaxonomyStatus.CANONICAL_SECONDARY
        )
    return AwardMapping(AwardType.OTHER, AwardTaxonomyStatus.UNKNOWN, AwardScope.UNKNOWN)


def normalize_team_level(award_type: AwardType, raw: object) -> tuple[int | None, str | None]:
    value = clean_source_value(raw)
    if award_type not in {
        AwardType.ALL_NBA,
        AwardType.ALL_DEFENSE,
        AwardType.ALL_ROOKIE,
        AwardType.NBA_CUP_ALL_TOURNAMENT,
    }:
        return None, None
    if value not in {"1", "2", "3"}:
        return None, None
    number = int(value)
    return number, {1: "FIRST", 2: "SECOND", 3: "THIRD"}[number]


def raw_event_fingerprint(row: Mapping[str, Any]) -> str:
    stable = {key: row.get(key) for key in sorted(row)}
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonicalize_award_row(
    row: Mapping[str, Any], *, player_id: str, expected_nba_player_id: str, retrieved_at: datetime
) -> PlayerAward:
    nba_player_id = normalize_nba_player_id(row.get("PERSON_ID"))
    if nba_player_id != expected_nba_player_id:
        raise ValueError(
            "PlayerAwards PERSON_ID "
            f"{nba_player_id!r} differs from request {expected_nba_player_id!r}"
        )
    mapping = mapping_for_description(row.get("DESCRIPTION"))
    season_id, season_label_raw, season_status = normalize_award_season(row.get("SEASON"))
    team_number, award_level = normalize_team_level(
        mapping.award_type, row.get("ALL_NBA_TEAM_NUMBER")
    )
    fingerprint = raw_event_fingerprint(row)
    return PlayerAward(
        award_id=canonical_id("award_event", "nba_playerawards", fingerprint),
        player_id=player_id,
        nba_player_id=nba_player_id,
        season_id=season_id,
        season_label_raw=season_label_raw,
        season_mapping_status=season_status,
        award_type=mapping.award_type,
        award_level=award_level,
        award_scope=mapping.award_scope,
        team_number=team_number,
        conference=clean_source_value(row.get("CONFERENCE")),
        month=clean_source_value(row.get("MONTH")),
        week=clean_source_value(row.get("WEEK")),
        source_description=clean_source_value(row.get("DESCRIPTION")) or "",
        source_type=clean_source_value(row.get("TYPE")),
        source_subtype1=clean_source_value(row.get("SUBTYPE1")),
        source_subtype2=clean_source_value(row.get("SUBTYPE2")),
        source_subtype3=clean_source_value(row.get("SUBTYPE3")),
        source_team=clean_source_value(row.get("TEAM")),
        taxonomy_status=mapping.taxonomy_status,
        source_event_fingerprint=fingerprint,
        source_id=NBA_AWARDS_SOURCE_ID,
        retrieved_at=retrieved_at,
        methodology_version=AWARDS_METHODOLOGY_VERSION,
        updated_at=retrieved_at,
    )


def canonicalize_player_awards(
    rows: Sequence[Mapping[str, Any]], *, player_id: str, nba_player_id: str, retrieved_at: datetime
) -> tuple[list[PlayerAward], list[dict[str, Any]]]:
    events_by_id: dict[str, PlayerAward] = {}
    quarantine: list[dict[str, Any]] = []
    for row in rows:
        try:
            event = canonicalize_award_row(
                row,
                player_id=player_id,
                expected_nba_player_id=nba_player_id,
                retrieved_at=retrieved_at,
            )
        except ValueError as error:
            quarantine.append(
                {"reason": "IDENTITY_OR_SCHEMA_CONFLICT", "error": str(error), "row": dict(row)}
            )
            continue
        prior = events_by_id.get(event.award_id)
        if prior is None:
            events_by_id[event.award_id] = event
        elif prior != event:
            quarantine.append(
                {
                    "reason": "AMBIGUOUS_DUPLICATE_EVENT",
                    "award_id": event.award_id,
                    "row": dict(row),
                }
            )
    events = sorted(
        events_by_id.values(),
        key=lambda event: (
            event.player_id,
            event.season_id if event.season_id is not None else 9999,
            event.season_label_raw or "",
            event.award_type.value,
            event.award_level or "",
            event.month or "",
            event.week or "",
            event.award_id,
        ),
    )
    return events, quarantine


def taxonomy_inventory(events: Sequence[PlayerAward]) -> list[dict[str, Any]]:
    groups: dict[
        tuple[str, str | None, str | None, str | None, str | None, int | None], list[PlayerAward]
    ] = defaultdict(list)
    for event in events:
        key = (
            event.source_description,
            event.source_type,
            event.source_subtype1,
            event.source_subtype2,
            event.source_subtype3,
            event.team_number,
        )
        groups[key].append(event)
    inventory: list[dict[str, Any]] = []
    for key, values in sorted(
        groups.items(), key=lambda item: tuple(str(value or "") for value in item[0])
    ):
        mapped = mapping_for_description(key[0])
        seasons = [event.season_id for event in values if event.season_id is not None]
        inventory.append(
            {
                "description": key[0],
                "source_type": key[1],
                "source_subtype1": key[2],
                "source_subtype2": key[3],
                "source_subtype3": key[4],
                "all_nba_team_number": key[5],
                "occurrence_count": len(values),
                "distinct_player_count": len({event.player_id for event in values}),
                "earliest_observed_season": min(seasons) if seasons else None,
                "latest_observed_season": max(seasons) if seasons else None,
                "canonical_award_type": mapped.award_type.value,
                "taxonomy_status": mapped.taxonomy_status.value,
                "mapping_confidence": "EXACT_OBSERVED_STRING"
                if mapped.taxonomy_status is not AwardTaxonomyStatus.UNKNOWN
                else "UNMAPPED",
                "notes": mapped.notes,
            }
        )
    return inventory


COUNT_FIELDS: dict[str, tuple[AwardType, str | None]] = {
    "mvp_count": (AwardType.MVP, None),
    "finals_mvp_count": (AwardType.FINALS_MVP, None),
    "conference_finals_mvp_count": (AwardType.CONFERENCE_FINALS_MVP, None),
    "dpoy_count": (AwardType.DPOY, None),
    "roy_count": (AwardType.ROY, None),
    "mip_count": (AwardType.MIP, None),
    "sixth_man_count": (AwardType.SIXTH_MAN, None),
    "clutch_player_count": (AwardType.CLUTCH_PLAYER, None),
    "comeback_player_count": (AwardType.COMEBACK_PLAYER, None),
    "all_nba_first_count": (AwardType.ALL_NBA, "FIRST"),
    "all_nba_second_count": (AwardType.ALL_NBA, "SECOND"),
    "all_nba_third_count": (AwardType.ALL_NBA, "THIRD"),
    "all_nba_total_count": (AwardType.ALL_NBA, None),
    "all_defense_first_count": (AwardType.ALL_DEFENSE, "FIRST"),
    "all_defense_second_count": (AwardType.ALL_DEFENSE, "SECOND"),
    "all_defense_total_count": (AwardType.ALL_DEFENSE, None),
    "all_rookie_first_count": (AwardType.ALL_ROOKIE, "FIRST"),
    "all_rookie_second_count": (AwardType.ALL_ROOKIE, "SECOND"),
    "all_rookie_total_count": (AwardType.ALL_ROOKIE, None),
    "all_star_count": (AwardType.ALL_STAR, None),
    "all_star_mvp_count": (AwardType.ALL_STAR_MVP, None),
    "nba_cup_mvp_count": (AwardType.NBA_CUP_MVP, None),
    "nba_cup_all_tournament_count": (AwardType.NBA_CUP_ALL_TOURNAMENT, None),
    "nba_champion_count": (AwardType.NBA_CHAMPION, None),
    "player_of_month_count": (AwardType.PLAYER_OF_MONTH, None),
    "player_of_week_count": (AwardType.PLAYER_OF_WEEK, None),
    "rookie_of_month_count": (AwardType.ROOKIE_OF_MONTH, None),
    "defensive_player_of_month_count": (AwardType.DEFENSIVE_PLAYER_OF_MONTH, None),
    "scoring_title_count": (AwardType.SCORING_TITLE, None),
    "rebound_title_count": (AwardType.REBOUND_TITLE, None),
    "assist_title_count": (AwardType.ASSIST_TITLE, None),
    "steal_title_count": (AwardType.STEAL_TITLE, None),
    "block_title_count": (AwardType.BLOCK_TITLE, None),
}


def career_accolade_counts(
    player: Mapping[str, Any], status: AwardAcquisitionStatus, events: Sequence[PlayerAward]
) -> dict[str, Any]:
    queried = status in {
        AwardAcquisitionStatus.SUCCESS_WITH_ROWS,
        AwardAcquisitionStatus.SUCCESS_EMPTY,
    }
    result: dict[str, Any] = {
        "player_id": str(player["player_id"]),
        "nba_player_id": str(player["nba_player_id"]),
        "display_name": str(player["display_name"]),
        "candidate_rule": "union_q5_or_p90_recommended",
        "is_award_candidate": bool(player["union_q5_or_p90_recommended"]),
        "award_acquisition_status": status.value,
        "source_event_count": len(events) if queried else None,
        "unknown_event_count": sum(
            event.taxonomy_status is AwardTaxonomyStatus.UNKNOWN for event in events
        )
        if queried
        else None,
        "first_event_season": min(
            (event.season_id for event in events if event.season_id is not None), default=None
        ),
        "last_event_season": max(
            (event.season_id for event in events if event.season_id is not None), default=None
        ),
        "awards_methodology_version": AWARDS_METHODOLOGY_VERSION,
    }
    for field, (award_type, level) in COUNT_FIELDS.items():
        result[field] = (
            sum(
                event.award_type is award_type and (level is None or event.award_level == level)
                for event in events
            )
            if queried
            else None
        )
    return result


def award_coverage(events: Sequence[PlayerAward]) -> list[dict[str, Any]]:
    by_type: dict[AwardType, list[PlayerAward]] = defaultdict(list)
    for event in events:
        by_type[event.award_type].append(event)
    output: list[dict[str, Any]] = []
    title_types = {
        AwardType.SCORING_TITLE,
        AwardType.REBOUND_TITLE,
        AwardType.ASSIST_TITLE,
        AwardType.STEAL_TITLE,
        AwardType.BLOCK_TITLE,
    }
    for award_type in AwardType:
        values = by_type[award_type]
        seasons = [event.season_id for event in values if event.season_id is not None]
        status = (
            "REQUIRES_SEPARATE_SOURCE"
            if award_type in title_types and not values
            else "UNKNOWN"
            if not values
            else "UNKNOWN"
            if any(event.taxonomy_status is AwardTaxonomyStatus.UNKNOWN for event in values)
            else "PARTIAL"
            if award_type is AwardType.ALL_STAR
            else "RELIABLE"
        )
        output.append(
            {
                "award_type": award_type.value,
                "first_observed_season": min(seasons) if seasons else None,
                "last_observed_season": max(seasons) if seasons else None,
                "known_introduction_season": KNOWN_INTRODUCTION_SEASONS.get(award_type),
                "source_coverage_status": status,
                "event_count": len(values),
                "player_count": len({event.player_id for event in values}),
                "zero_semantics": (
                    "no event is a non-selection only for successfully queried players "
                    "during applicable seasons"
                ),
            }
        )
    return output


def duplicate_event_ids(events: Iterable[PlayerAward]) -> list[str]:
    counts = Counter(event.award_id for event in events)
    return sorted(key for key, count in counts.items() if count > 1)


def stable_json_fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def model_rows(events: Sequence[PlayerAward]) -> list[dict[str, Any]]:
    return [event.model_dump(mode="json") for event in events]
