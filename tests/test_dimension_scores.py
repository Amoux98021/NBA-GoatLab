from __future__ import annotations

import pytest

from goatlab.rankings.dimension_scores import (
    EvidenceConfidence,
    best_contiguous_window,
    confidence_from_coverage,
    joint_scoring_value,
    longevity_evidence,
    midrank_percentile_scores,
    peak_hybrid,
    playoff_hybrid,
    recognition_bundle,
    weighted_observed,
    winning_outcome_tier,
)


def test_midrank_score_is_bounded_tie_aware_and_preserves_null() -> None:
    values = {"low": 1.0, "tie_a": 2.0, "tie_b": 2.0, "high": 4.0, "missing": None}
    scores = midrank_percentile_scores(values, {"low", "tie_a", "tie_b", "high"})
    assert scores["low"] == 0.0
    assert scores["tie_a"] == scores["tie_b"] == pytest.approx(50.0)
    assert scores["high"] == 100.0
    assert scores["missing"] is None


def test_weighted_evidence_never_turns_missing_into_zero() -> None:
    missing_required = weighted_observed(
        {"required": None, "optional": 100.0},
        {"required": 0.7, "optional": 0.3},
        required=("required",),
    )
    assert missing_required.value is None
    assert missing_required.weight_coverage == 0.0
    observed_zero = weighted_observed({"x": 0.0}, {"x": 1.0})
    assert observed_zero.value == 0.0


def test_peak_requires_complete_contiguous_three_year_window() -> None:
    seasons = {1990: 75.0, 1991: 90.0, 1993: 100.0, 1994: 95.0, 1995: 85.0}
    window = best_contiguous_window(seasons, 3)
    assert (window.start_season, window.end_season) == (1993, 1995)
    assert window.value == pytest.approx(280.0 / 3.0)
    assert best_contiguous_window({1990: 100.0, 1992: 100.0, 1993: 100.0}, 3).value is None
    assert peak_hybrid(window.value, 100.0, 0.70) == pytest.approx(95.3333333333)
    with pytest.raises(ValueError, match="majority"):
        peak_hybrid(90.0, 100.0, 0.50)


def test_longevity_caps_extreme_height_and_breaks_missed_season_runs() -> None:
    evidence = longevity_evidence(
        {2000: 0.80, 2001: 0.90, 2003: 0.99, 2004: None}, threshold=0.80, cap=0.95
    )
    assert evidence.breadth == 3
    assert evidence.longest_run == 2
    assert evidence.capped_area == pytest.approx(5.0 / 3.0)
    more_extreme = longevity_evidence({2000: 0.95}, threshold=0.80, cap=0.95)
    beyond_cap = longevity_evidence({2000: 0.999}, threshold=0.80, cap=0.95)
    assert more_extreme.capped_area == beyond_cap.capped_area == 1.0


def test_offense_keeps_scoring_joint_and_playmaking_optional() -> None:
    joint = joint_scoring_value(90.0, 70.0, volume_weight=0.65)
    assert joint.value == pytest.approx(83.0)
    volume_only = joint_scoring_value(90.0, None)
    assert volume_only.value == 90.0
    assert volume_only.weight_coverage == 0.65
    assert joint_scoring_value(None, 100.0).value is None


def test_playoff_absolute_quality_is_required_and_dominant() -> None:
    result = playoff_hybrid(90.0, 100.0, 100.0)
    assert result.value == pytest.approx(93.5)
    assert playoff_hybrid(None, 100.0, 100.0).value is None
    with pytest.raises(ValueError, match="dominate"):
        playoff_hybrid(90.0, 100.0, 100.0, weights=(0.40, 0.40, 0.20))


def test_recognition_bundle_caps_same_season_stacking() -> None:
    bundled = recognition_bundle([1.0, 1.0, 1.0], cap=1.15)
    assert bundled == 1.15
    assert bundled < 3.0


def test_winning_returns_one_highest_outcome_tier() -> None:
    assert winning_outcome_tier(
        champion_finals_participant=True,
        finalist_participant=True,
        playoff_participant=True,
        series_won=4,
    ) == ("CHAMPION_FINALS_PARTICIPANT", 1.0)
    assert winning_outcome_tier(
        champion_finals_participant=False,
        finalist_participant=False,
        playoff_participant=True,
        series_won=None,
    ) == ("PLAYOFF_PARTICIPANT", 0.20)


def test_confidence_is_metadata_not_a_quality_multiplier() -> None:
    assert confidence_from_coverage(1.0, relevant_seasons=5) is EvidenceConfidence.STRONG
    assert confidence_from_coverage(0.50, relevant_seasons=5) is EvidenceConfidence.LIMITED
    assert confidence_from_coverage(1.0, relevant_seasons=0) is EvidenceConfidence.UNAVAILABLE
