"""Offline fixture and artifact tests for STEP-0009 awards ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from goatlab.data.awards import (
    AWARDS_METHODOLOGY_VERSION,
    AwardAcquisitionStatus,
    canonicalize_player_awards,
    career_accolade_counts,
    duplicate_event_ids,
    mapping_for_description,
    normalize_award_season,
    normalize_nba_player_id,
    normalize_team_level,
    parse_player_awards_payload,
    stable_json_fingerprint,
)
from goatlab.schemas import AwardTaxonomyStatus, AwardType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/fixtures/nba_api_player_awards_sample.json"
PLAYER_ID = "player_fixture_lebron"
RETRIEVED_AT = datetime(2026, 8, 31, 20, 0, tzinfo=UTC)


def _rows() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    headers, rows = parse_player_awards_payload(payload)
    assert headers == payload["resultSets"][0]["headers"]
    return rows


def _events() -> list[object]:
    events, quarantine = canonicalize_player_awards(
        _rows(),
        player_id=PLAYER_ID,
        nba_player_id="2544",
        retrieved_at=RETRIEVED_AT,
    )
    assert not quarantine
    return events


def test_raw_player_awards_parsing_and_identity_mapping() -> None:
    rows = _rows()
    assert len(rows) == 5
    events, quarantine = canonicalize_player_awards(
        rows,
        player_id=PLAYER_ID,
        nba_player_id="2544",
        retrieved_at=RETRIEVED_AT,
    )
    assert not quarantine
    assert {event.player_id for event in events} == {PLAYER_ID}
    assert {event.nba_player_id for event in events} == {"2544"}
    assert all(event.methodology_version == AWARDS_METHODOLOGY_VERSION for event in events)
    assert normalize_nba_player_id(76127.0) == "76127"
    assert normalize_nba_player_id("76127.0") == "76127"
    assert normalize_nba_player_id(76127.5) is None


def test_taxonomy_mapping_preserves_unknown_description() -> None:
    known = mapping_for_description("NBA Most Valuable Player")
    unknown = mapping_for_description("Fixture Unknown Honor")
    assert known.award_type is AwardType.MVP
    assert known.taxonomy_status is AwardTaxonomyStatus.CANONICAL_CORE
    assert unknown.award_type is AwardType.OTHER
    assert unknown.taxonomy_status is AwardTaxonomyStatus.UNKNOWN
    assert any(
        event.source_description == "Fixture Unknown Honor"
        and event.taxonomy_status is AwardTaxonomyStatus.UNKNOWN
        for event in _events()
    )


def test_season_normalization_and_unknown_calendar_year() -> None:
    assert normalize_award_season("2005-06") == (2005, "2005-06", "MAPPED")
    assert normalize_award_season("2040") == (None, "2040", "SEASON_MAPPING_UNKNOWN")
    assert normalize_award_season("2005-08") == (
        None,
        "2005-08",
        "SEASON_MAPPING_UNKNOWN",
    )


def test_all_nba_team_number_is_structured() -> None:
    assert normalize_team_level(AwardType.ALL_NBA, "1") == (1, "FIRST")
    assert normalize_team_level(AwardType.ALL_DEFENSE, "2") == (2, "SECOND")
    assert normalize_team_level(AwardType.MVP, "1") == (None, None)


def test_repeated_weekly_events_are_preserved_and_exact_duplicates_deduplicate() -> None:
    rows = _rows()
    events, _ = canonicalize_player_awards(
        rows,
        player_id=PLAYER_ID,
        nba_player_id="2544",
        retrieved_at=RETRIEVED_AT,
    )
    weekly = [event for event in events if event.award_type is AwardType.PLAYER_OF_WEEK]
    assert len(weekly) == 2
    duplicated, quarantine = canonicalize_player_awards(
        [*rows, rows[1]],
        player_id=PLAYER_ID,
        nba_player_id="2544",
        retrieved_at=RETRIEVED_AT,
    )
    assert len(duplicated) == len(events)
    assert not quarantine
    assert not duplicate_event_ids(duplicated)


def test_identity_conflict_is_quarantined() -> None:
    row = dict(_rows()[0])
    row["PERSON_ID"] = 999
    events, quarantine = canonicalize_player_awards(
        [row],
        player_id=PLAYER_ID,
        nba_player_id="2544",
        retrieved_at=RETRIEVED_AT,
    )
    assert not events
    assert quarantine[0]["reason"] == "IDENTITY_OR_SCHEMA_CONFLICT"


def test_acquisition_status_controls_count_semantics() -> None:
    player = {
        "player_id": PLAYER_ID,
        "nba_player_id": "2544",
        "display_name": "LeBron James",
        "union_q5_or_p90_recommended": True,
    }
    events = _events()
    populated = career_accolade_counts(player, AwardAcquisitionStatus.SUCCESS_WITH_ROWS, events)
    empty = career_accolade_counts(player, AwardAcquisitionStatus.SUCCESS_EMPTY, [])
    not_queried = career_accolade_counts(player, AwardAcquisitionStatus.NOT_QUERIED, [])
    assert populated["all_nba_first_count"] == 1
    assert populated["player_of_week_count"] == 2
    assert empty["mvp_count"] == 0
    assert not_queried["mvp_count"] is None
    assert not_queried["source_event_count"] is None


def test_fingerprint_is_deterministic_and_order_sensitive_only_to_content() -> None:
    left = {"b": [2, 1], "a": 3}
    right = {"a": 3, "b": [2, 1]}
    assert stable_json_fingerprint(left) == stable_json_fingerprint(right)
    assert stable_json_fingerprint(left) != stable_json_fingerprint({"a": 3, "b": [1, 2]})


def test_committed_award_artifacts_when_present() -> None:
    summary_path = ROOT / "docs/data/award-canonicalization-summary.json"
    if not summary_path.exists():
        pytest.skip("STEP-0009 artifacts not built yet")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    acquisition = json.loads(
        (ROOT / "docs/data/award-acquisition-manifest.json").read_text(encoding="utf-8")
    )
    assert summary["result"] == "PASS"
    assert summary["request_summary"]["candidate_universe_size"] == 2140
    assert acquisition["success_with_rows"] + acquisition["success_empty"] == 2140
    assert acquisition["status_counts"]["NOT_QUERIED"] == 2963
    assert summary["non_candidate_null_count_semantics_valid"]
    assert summary["quality"]["no_award_weights_or_scores"]
