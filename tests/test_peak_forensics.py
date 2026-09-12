from __future__ import annotations

from pathlib import Path

import pytest

from goatlab.rankings.peak_forensics import (
    individual_season_quality,
    player_peak,
    synthetic_window,
    v1_season_quality,
)


def test_v1_season_quality_reconstructs_the_frozen_chain() -> None:
    values = {
        "ppg": 0.90,
        "ts_pct": 0.70,
        "apg": 0.80,
        "team_suppression": 0.60,
        "rpg": 0.50,
        "spg": 0.40,
        "bpg": 0.30,
    }
    result = v1_season_quality(values)
    scoring = 0.65 * 0.90 + 0.35 * 0.70
    offense = 0.65 * scoring + 0.35 * 0.80
    actions = 0.50 * 0.50 + 0.25 * 0.40 + 0.25 * 0.30
    defense = 0.65 * 0.60 + 0.35 * actions
    expected = 0.65 * offense + 0.35 * defense
    assert result.quality == pytest.approx(expected)
    assert sum(result.effective_weights.values()) == pytest.approx(1.0)
    assert sum(result.contributions.values()) == pytest.approx(expected)


def test_missingness_is_renormalized_and_never_becomes_zero() -> None:
    values = {
        "ppg": 0.80,
        "ts_pct": None,
        "apg": None,
        "team_suppression": 0.70,
        "rpg": None,
        "spg": None,
        "bpg": None,
    }
    result = v1_season_quality(values)
    assert result.scoring == 0.80
    assert result.offense == 0.80
    assert result.actions is None
    assert result.defense == 0.70
    assert result.quality == pytest.approx(0.65 * 0.80 + 0.35 * 0.70)
    assert result.effective_weights["ts_pct"] == 0.0
    assert result.effective_weights["rpg"] == 0.0


def test_team_context_is_required_for_frozen_v1_defense() -> None:
    result = v1_season_quality(
        {
            "ppg": 0.80,
            "ts_pct": 0.70,
            "apg": 0.60,
            "team_suppression": None,
            "rpg": 0.90,
            "spg": 0.90,
            "bpg": 0.90,
        }
    )
    assert result.defense is None
    assert result.quality == result.offense
    assert result.effective_weights["team_suppression"] == 0.0


def test_peak_requires_a_complete_contiguous_three_year_window() -> None:
    raw, window, apex = player_peak({1990: 0.9, 1991: 0.8, 1993: 1.0})
    assert raw is None
    assert window.value is None
    assert apex == 1.0
    complete, selected, _ = player_peak({1990: 0.9, 1991: 0.8, 1992: 0.7})
    assert selected.start_season == 1990
    assert selected.end_season == 1992
    assert complete == pytest.approx(0.70 * 0.80 + 0.30 * 0.90)


def test_equal_windows_use_deterministic_earliest_tie_break() -> None:
    _, window, _ = player_peak({2000: 0.8, 2001: 0.8, 2002: 0.8, 2003: 0.8})
    assert (window.start_season, window.end_season) == (2000, 2002)


def test_synthetic_window_rejects_missing_or_nonqualified_season() -> None:
    missing = synthetic_window([1.0, 1.0, None])
    assert missing["three_year"] is None
    assert missing["raw_peak"] is None
    assert synthetic_window([0.99, 0.99, 0.99])["raw_peak"] == pytest.approx(0.99)


def test_research_candidate_requires_both_individual_axes() -> None:
    assert individual_season_quality(0.9, None, architecture="MULTI_PATH_65_35") is None
    assert individual_season_quality(None, 0.9, architecture="FIXED_60_40") is None
    assert individual_season_quality(0.9, 0.7, architecture="FIXED_60_40") == pytest.approx(0.82)
    assert individual_season_quality(0.9, 0.7, architecture="MULTI_PATH_65_35") == pytest.approx(
        0.83
    )


def test_peak_primitives_accept_only_explicit_numeric_evidence() -> None:
    forbidden = ("MVP", "DPOY", "All-NBA", "championship", "playoff")
    implementation = __import__("goatlab.rankings.peak_forensics", fromlist=["dummy"]).__file__
    assert implementation is not None
    implementation_source = Path(implementation).read_text(encoding="utf-8")
    assert all(term not in implementation_source for term in forbidden)
    assert "player_name" not in implementation_source
