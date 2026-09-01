import json
from pathlib import Path

import yaml

from goatlab.data.accolade_completion import (
    all_star_applicability,
    all_star_reconciliation_class,
    career_count_rows,
    category_applicability,
    derive_leaders,
    parse_box_score_roster,
    reconcile_leader_sets,
    stable_id,
)


def test_all_star_applicability_and_no_game_season() -> None:
    assert all_star_applicability(1949) == "NOT_APPLICABLE"
    assert all_star_applicability(1950) == "APPLICABLE"
    assert all_star_applicability(1998) == "NO_GAME_HELD"


def test_box_score_roster_parsing_preserves_dnp_comment() -> None:
    payload = {
        "boxScoreTraditional": {
            "gameId": "0032400001",
            "homeTeam": {
                "teamCity": "Team",
                "teamName": "One",
                "players": [
                    {"personId": 7, "firstName": "A", "familyName": "Player", "comment": "DNP"}
                ],
            },
            "awayTeam": {"teamCity": "Team", "teamName": "Two", "players": []},
        }
    }
    assert parse_box_score_roster(payload)[0]["source_comment"] == "DNP"


def test_box_score_blank_person_placeholder_is_not_player_evidence() -> None:
    payload = {
        "boxScoreTraditional": {
            "gameId": "0039700001",
            "homeTeam": {
                "players": [{"personId": 1302, "firstName": "", "familyName": "", "statistics": {}}]
            },
            "awayTeam": {"players": []},
        }
    }
    assert parse_box_score_roster(payload) == []


def test_category_introductions_block_pre_stat_events() -> None:
    assert category_applicability(1972, "STL") == "NOT_APPLICABLE"
    assert category_applicability(1973, "STL") == "APPLICABLE"
    assert category_applicability(1949, "REB") == "NOT_APPLICABLE"


def test_derived_leaders_preserve_ties_and_coverage_gate() -> None:
    rows = [
        {"player_id": "a", "games_played": 80, "points_per_game": 20.0, "points_total": 1600},
        {"player_id": "b", "games_played": 70, "points_per_game": 20.0, "points_total": 1400},
        {"player_id": "c", "games_played": 2, "points_per_game": 30.0, "points_total": 60},
    ]
    leaders = derive_leaders(rows, "PTS", games_threshold=60, coverage_reliable=True)
    assert leaders.raw_per_game == frozenset({"c"})
    assert leaders.qualified == frozenset({"a", "b"})
    assert leaders.raw_total == frozenset({"a"})
    blocked = derive_leaders(rows, "PTS", games_threshold=60, coverage_reliable=False)
    assert not blocked.qualified


def test_leader_reconciliation_and_all_star_status_semantics() -> None:
    assert (
        reconcile_leader_sets(frozenset({"a"}), frozenset({"a"}), source_available=True)
        == "EXACT_MATCH"
    )
    assert (
        reconcile_leader_sets(frozenset({"a", "b"}), frozenset({"a", "b"}), source_available=True)
        == "TIE_MATCH"
    )
    assert (
        reconcile_leader_sets(frozenset(), frozenset({"a"}), source_available=False)
        == "SOURCE_COVERAGE_GAP"
    )
    assert all_star_reconciliation_class(award=None, roster=True, played=True).startswith(
        "NOT_QUERIED"
    )
    assert (
        all_star_reconciliation_class(award=False, roster=True, played=True)
        == "PLAYED + NO_AWARD_EVENT"
    )


def test_career_counts_keep_not_queried_awards_nullable() -> None:
    all_star, stats = career_count_rows(
        [
            {
                "player_id": "p",
                "nba_player_id": "1",
                "roster_evidence": True,
                "all_star_games_played": 1,
                "playerawards_evidence": None,
            }
        ],
        [
            {
                "player_id": "p",
                "nba_player_id": "1",
                "stat_category": "PTS",
                "official_source_rank": 1,
                "is_derived_qualified_leader": True,
            }
        ],
    )
    assert all_star[0]["all_star_playerawards_events"] is None
    assert stats[0]["pts_official_source_rank_one_count"] == 1
    assert stable_id("event", [1, "PTS"]) == stable_id("event", [1, "PTS"])


def test_step_0011_committed_reports_are_internally_consistent() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "docs/data/accolade-fact-completion-summary.json").read_text())
    reconciliation = json.loads((root / "docs/data/stat-leader-reconciliation.json").read_text())
    coverage = json.loads((root / "docs/data/accolade-coverage-complete.json").read_text())
    source_manifest = yaml.safe_load((root / "docs/data/source-manifest.yaml").read_text())
    assert summary["decision"] == "PASS"
    assert summary["requests"]["total"] == 615
    assert summary["requests"]["network"] == 0
    assert summary["output_fingerprint"] == (
        "e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880"
    )
    assert sum(reconciliation["status_counts"].values()) == 342
    assert coverage["all_star"]["no_game_seasons"] == [1998]
    assert (
        source_manifest["official_nba_accolade_fact_completion_v1"]["methodology_version"]
        == "all-star-stat-leader-facts-v1"
    )
