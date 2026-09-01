"""Offline tests for STEP-0010 team-success and postseason primitives."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from goatlab.data.team_success import (
    CORPUS_ID,
    TEAM_SUCCESS_METHODOLOGY_VERSION,
    CanonicalGameEvidence,
    TeamIdentity,
    build_player_team_participation,
    career_team_context,
    derive_team_season_results,
    identify_finals_games,
    infer_finals_outcome,
    minutes_are_eligible,
    postseason_format_for_season,
    stable_json_fingerprint,
)
from goatlab.schemas import PostseasonFormatStatus

ROOT = Path(__file__).resolve().parents[1]
UPDATED_AT = datetime(2026, 9, 1, 12, tzinfo=UTC)


def game(
    game_id: str,
    game_date: date,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    *,
    season_type: str,
) -> CanonicalGameEvidence:
    return CanonicalGameEvidence(
        game_id=game_id,
        nba_game_id=game_id,
        season_id=2022,
        season_type=season_type,
        game_date=game_date,
        home_team_id=home,
        away_team_id=away,
        home_score=home_score,
        away_score=away_score,
        winner_team_id=home if home_score > away_score else away,
        venue_assignment_status="OBSERVED_HOME_AWAY",
        score_reliable=True,
        source_id="fixture",
    )


def sample_games() -> tuple[list[CanonicalGameEvidence], list[CanonicalGameEvidence]]:
    regular = [
        game("r1", date(2022, 10, 1), "A", "B", 110, 100, season_type="REGULAR"),
        game("r2", date(2022, 10, 2), "C", "D", 90, 95, season_type="REGULAR"),
        game("r3", date(2022, 10, 3), "A", "C", 120, 90, season_type="REGULAR"),
        game("r4", date(2022, 10, 4), "B", "D", 100, 105, season_type="REGULAR"),
    ]
    playoff = [
        game("p1", date(2023, 4, 1), "A", "C", 100, 90, season_type="PLAYOFF"),
        game("p2", date(2023, 4, 2), "B", "D", 100, 90, season_type="PLAYOFF"),
        game("f1", date(2023, 6, 1), "A", "B", 105, 99, season_type="PLAYOFF"),
    ]
    return regular, playoff


def identities() -> dict[str, TeamIdentity]:
    return {
        team: TeamIdentity(team, f"nba-{team}", f"franchise-{team}", f"Team {team}")
        for team in "ABCD"
    }


def test_team_records_point_differential_and_context() -> None:
    regular, playoff = sample_games()
    outcome = infer_finals_outcome(playoff)
    results = derive_team_season_results(
        regular, playoff, identities(), outcome, updated_at=UPDATED_AT
    )
    keyed = {row.team_id: row for row in results}
    assert keyed["A"].regular_wins == 2
    assert keyed["A"].regular_losses == 0
    assert keyed["A"].regular_point_diff == 40
    assert keyed["A"].regular_point_diff_per_game == pytest.approx(20)
    assert keyed["A"].win_pct_rank == 1
    assert 0 <= keyed["A"].win_pct_percentile <= 1
    assert sum(row.champion for row in results) == 1
    assert sum(row.finalist for row in results) == 1
    assert keyed["A"].champion and not keyed["A"].finalist
    assert keyed["B"].finalist and not keyed["B"].champion


def test_champion_finalist_and_finals_games_are_deterministic() -> None:
    _, playoff = sample_games()
    outcome = infer_finals_outcome(playoff)
    assert (outcome.champion_team_id, outcome.finalist_team_id) == ("A", "B")
    finals = identify_finals_games(playoff, outcome, updated_at=UPDATED_AT)
    assert [row.game_id for row in finals] == ["f1"]
    assert finals[0].finals_game_number == 1
    assert finals[0].winner_team_id == "A"


def test_postseason_format_policy_blocks_only_mixed_round_robin() -> None:
    status, series_allowed, modern_labels = postseason_format_for_season(1953)
    assert status is PostseasonFormatStatus.ROUND_ROBIN_OR_MIXED
    assert not series_allowed and not modern_labels
    status, series_allowed, modern_labels = postseason_format_for_season(1976)
    assert status is PostseasonFormatStatus.NONSTANDARD_SERIES_FORMAT
    assert series_allowed and not modern_labels
    status, series_allowed, modern_labels = postseason_format_for_season(1983)
    assert status is PostseasonFormatStatus.STANDARD_SERIES_BRACKET
    assert series_allowed and modern_labels


def test_traded_player_outcomes_do_not_leak_across_team_rows() -> None:
    regular, playoff = sample_games()
    outcome = infer_finals_outcome(playoff)
    results = derive_team_season_results(
        regular, playoff, identities(), outcome, updated_at=UPDATED_AT
    )
    regular_rows = [
        {"player_id": "traded", "team_id": "A", "game_id": "r1", "minutes": 10.0},
        {"player_id": "traded", "team_id": "C", "game_id": "r2", "minutes": 20.0},
        {"player_id": "champ", "team_id": "A", "game_id": "r3", "minutes": 30.0},
    ]
    playoff_rows = [
        {"player_id": "traded", "team_id": "C", "game_id": "p1", "minutes": 20.0},
        {"player_id": "champ", "team_id": "A", "game_id": "p1", "minutes": 30.0},
        {"player_id": "champ", "team_id": "A", "game_id": "f1", "minutes": 35.0},
        {"player_id": "runner", "team_id": "B", "game_id": "f1", "minutes": 35.0},
    ]
    rows = build_player_team_participation(
        regular_rows,
        playoff_rows,
        results,
        {"f1"},
        {row.game_id: row.winner_team_id for row in playoff},
        {"traded": "NOT_QUERIED", "champ": "SUCCESS_WITH_ROWS", "runner": "SUCCESS_EMPTY"},
        {("champ", 2022)},
        regular_minutes_eligible=True,
        playoff_minutes_eligible=True,
        updated_at=UPDATED_AT,
    )
    keyed = {(row.player_id, row.team_id): row for row in rows}
    champion_membership = keyed[("traded", "A")]
    traded_playoff_team = keyed[("traded", "C")]
    assert champion_membership.regular_season_member_of_champion_team
    assert not champion_membership.played_playoffs_for_champion_team
    assert not traded_playoff_team.team_champion
    assert not traded_playoff_team.played_playoffs_for_champion_team
    assert keyed[("champ", "A")].played_finals_for_champion_team
    assert keyed[("champ", "A")].official_nba_champion_award_event is True
    assert champion_membership.official_nba_champion_award_event is None


def test_minutes_gate_preserves_unavailable_values() -> None:
    assert minutes_are_eligible(
        [{"minutes": 12.0}, {"minutes": 8.0}], empirical_classification="RELIABLE"
    )
    assert not minutes_are_eligible(
        [{"minutes": 0.0}, {"minutes": 0.0}], empirical_classification="RELIABLE"
    )
    assert not minutes_are_eligible(
        [{"minutes": 12.0}], empirical_classification="PARTIAL"
    )


def test_career_context_keeps_factual_variants_separate() -> None:
    team_result = {
        ("A", 2022): {"win_pct_percentile": 0.95},
        ("B", 2022): {"win_pct_percentile": 0.75},
    }
    participation = [
        {
            "player_id": "p1",
            "team_id": "A",
            "season_id": 2022,
            "regular_games": 1,
            "playoff_games": 1,
            "playoff_wins_while_participating": 1,
            "finals_games": 1,
            "team_finalist": False,
            "regular_season_member_of_champion_team": True,
            "played_playoffs_for_champion_team": True,
            "played_finals_for_champion_team": True,
            "regular_minutes_coverage": "RELIABLE",
            "playoff_minutes_coverage": "RELIABLE",
            "finals_minutes_coverage": "RELIABLE",
        }
    ]
    output = career_team_context(
        [{"player_id": "p1", "nba_player_id": "1", "display_name": "Player One"}],
        participation,
        team_result,
        {"p1": {"nba_champion_count": 1, "award_acquisition_status": "SUCCESS_WITH_ROWS"}},
    )[0]
    assert output["playoff_seasons"] == 1
    assert output["finals_seasons"] == 1
    assert output["seasons_on_champion_teams_regular"] == 1
    assert output["seasons_played_finals_for_champion"] == 1
    assert output["official_nba_champion_award_count"] == 1
    assert "team_success_score" not in output


def test_official_reference_and_committed_artifacts_cover_all_seasons() -> None:
    official = json.loads(
        (ROOT / "data/fixtures/official_nba_championships.json").read_text(encoding="utf-8")
    )
    reconciliation = json.loads(
        (ROOT / "docs/data/championship-reconciliation.json").read_text(encoding="utf-8")
    )
    summary = json.loads((ROOT / "docs/data/team-success-summary.json").read_text())
    assert len(official["records"]) == 80
    assert len(reconciliation["seasons"]) == 80
    assert all(row["champion_match"] for row in reconciliation["seasons"])
    assert all(row["finalist_match"] for row in reconciliation["seasons"])
    assert all(row["series_result_match"] for row in reconciliation["seasons"])
    assert summary["season_count"] == 80
    assert summary["quality"]["duplicate_player_team_season_keys"] == 0
    assert summary["subjective_scores_created"] == 0


def test_stable_fingerprint_is_order_independent_for_mapping_keys() -> None:
    first = {"corpus": CORPUS_ID, "methodology": TEAM_SUCCESS_METHODOLOGY_VERSION}
    second = {"methodology": TEAM_SUCCESS_METHODOLOGY_VERSION, "corpus": CORPUS_ID}
    assert stable_json_fingerprint(first) == stable_json_fingerprint(second)


def test_generated_partition_manifest_matches_local_outputs_when_present() -> None:
    manifest = json.loads(
        (ROOT / "docs/data/team-success-output-manifest.json").read_text(encoding="utf-8")
    )
    partitions = manifest["partitions"]
    assert len(partitions) == 304
    if not (ROOT / partitions[0]["path"]).exists():
        pytest.skip("STEP-0010 generated outputs not built locally")
    for record in partitions:
        path = ROOT / record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        metadata = pq.read_metadata(path)
        assert metadata.num_rows == record["rows"]
        assert metadata.num_columns == record["columns"]
        assert path.stat().st_size == record["size_bytes"]
    stable = [
        {key: row[key] for key in ("path", "rows", "columns", "size_bytes", "sha256")}
        for row in sorted(partitions, key=lambda item: item["path"])
    ]
    assert stable_json_fingerprint(stable) == manifest["output_fingerprint"]
