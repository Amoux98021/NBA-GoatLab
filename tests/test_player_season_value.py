from __future__ import annotations

from pathlib import Path

import pytest

from goatlab.rankings.player_season_value import (
    combine_player_value,
    confidence_from_evidence,
    defensive_axis,
    evidence_regime,
    offensive_axis,
)


def test_offense_candidates_are_deterministic_and_multi_path() -> None:
    assert offensive_axis(0.90, 0.70, architecture="O2_DIRECT_70_30") == pytest.approx(0.84)
    assert offensive_axis(0.90, 0.70, architecture="O3_MULTIPATH_60_40") == pytest.approx(0.82)
    assert offensive_axis(0.70, 0.90, architecture="O3_MULTIPATH_60_40") == pytest.approx(0.82)


def test_missing_evidence_is_unavailable_and_never_zero() -> None:
    defense, _, reasons = defensive_axis(None, 0.80, None, architecture="D4_RELIABILITY_55_10_35")
    assert defense is None
    assert "DEFENSIVE_ACTION_EVIDENCE_UNAVAILABLE" in reasons
    combined = combine_player_value(
        0.80,
        None,
        architecture="M4_BOUNDED_STRONGER_55_45",
        defense_team_weight=0.10,
    )
    assert combined.value is None
    assert combined.confidence == "UNAVAILABLE"


def test_observed_zero_is_preserved_as_observed_performance() -> None:
    defense, team_weight, _ = defensive_axis(
        0.0,
        0.50,
        None,
        architecture="D4_RELIABILITY_55_10_35",
    )
    assert defense == pytest.approx(0.05)
    assert team_weight == pytest.approx(0.10)


def test_reliability_blend_is_continuous_and_team_context_is_capped() -> None:
    low, local_team, _ = defensive_axis(
        0.40,
        0.80,
        1.0,
        architecture="D4_RELIABILITY_55_10_35",
        presence_reliability=0.20,
    )
    high, _, _ = defensive_axis(
        0.40,
        0.80,
        1.0,
        architecture="D4_RELIABILITY_55_10_35",
        presence_reliability=0.21,
    )
    assert low is not None and high is not None
    assert high - low == pytest.approx(0.0021)
    combined = combine_player_value(
        0.70,
        low,
        architecture="M4_BOUNDED_STRONGER_55_45",
        defense_team_weight=local_team,
    )
    assert combined.team_effective_weight <= 0.055


def test_confidence_does_not_change_quality() -> None:
    value = combine_player_value(
        0.80,
        0.60,
        architecture="M4_BOUNDED_STRONGER_55_45",
        defense_team_weight=0.10,
    ).value
    strong = confidence_from_evidence(
        regime="FULL_PORTABLE", presence_reliability=1.0, role_known=True, games=82
    )
    limited = confidence_from_evidence(
        regime="EARLY_LIMITED", presence_reliability=0.0, role_known=False, games=12
    )
    assert value == pytest.approx(0.71)
    assert strong[0] == "STRONG"
    assert limited[0] == "LIMITED"


def test_evidence_regimes_follow_observations_not_dates() -> None:
    assert (
        evidence_regime(
            ts_available=True,
            creation_available=True,
            rebound_available=True,
            steals_blocks_available=True,
            role_actions_available=True,
            presence_available=True,
        )
        == "FULL_PORTABLE"
    )
    assert (
        evidence_regime(
            ts_available=False,
            creation_available=False,
            rebound_available=True,
            steals_blocks_available=False,
            role_actions_available=False,
            presence_available=False,
        )
        == "EARLY_LIMITED"
    )


def test_scoring_implementation_has_no_forbidden_ownership_or_player_logic() -> None:
    implementation = __import__("goatlab.rankings.player_season_value", fromlist=["dummy"]).__file__
    assert implementation is not None
    source = Path(implementation).read_text(encoding="utf-8").lower()
    forbidden = (
        "player_name",
        "mvp",
        "all_nba",
        "championship",
        "playoff",
        "postseason",
    )
    assert all(term not in source for term in forbidden)
