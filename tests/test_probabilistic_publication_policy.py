from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from goatlab.rankings.publication_policy import (
    POLICY_VERSION,
    DimensionDisplay,
    PairwiseComparison,
    PairwiseOrder,
    PlayerLeaderboardRecord,
    RankingStatus,
    Top100Membership,
    UnrankedPlayerRecord,
    pairwise_order,
    ranking_status,
    top100_membership,
)

DIMENSIONS = ("peak", "longevity", "offense", "defense", "playoffs", "accolades", "winning")


def player_card() -> dict[str, object]:
    dimensions = {
        dimension: {
            "value": 85.0,
            "lower_90": 80.0,
            "upper_90": 90.0,
            "source_status": f"OFFICIAL_{dimension.upper()}_POINT",
            "value_is_official_point": True,
        }
        for dimension in DIMENSIONS
    }
    return {
        "player_id": "player_123",
        "player_name": "Example Player",
        "distribution_ref": "gold://overall-v2/player_123",
        "distribution_fingerprint": "a" * 64,
        "overall_center": 85.0,
        "overall_center_label": "DIAGNOSTIC_SUMMARY",
        "overall_lower_80": 82.0,
        "overall_upper_80": 88.0,
        "overall_lower_90": 80.0,
        "overall_upper_90": 90.0,
        "median_rank": 42.0,
        "rank_lower_50": 40.0,
        "rank_upper_50": 44.0,
        "rank_lower_80": 36.0,
        "rank_upper_80": 48.0,
        "rank_lower_90": 32.0,
        "rank_upper_90": 55.0,
        "rank_lower_95": 25.0,
        "rank_upper_95": 60.0,
        "top_10_probability": 0.0,
        "top_25_probability": 0.08,
        "top_50_probability": 0.72,
        "top_100_probability": 0.99,
        "ranking_status": "OFFICIAL",
        "overall_source_status": "OFFICIAL_OVERALL_POINT",
        "display_position": 42,
        "display_position_semantics": "NAVIGATIONAL_MEDIAN_RANK_SORT",
        **dimensions,
        "career_state": "ACTIVE",
        "active_career_policy": "TO_DATE_NO_PROJECTION",
        "cutoff_season": "2025-26",
        "ranking_policy_version": POLICY_VERSION,
        "overall_substrate_version": "goatlab-v1-overall-v2-tiered",
        "dimension_methodology_versions": {name: "frozen-version" for name in DIMENSIONS},
        "conditional_on_frozen_measurement_architecture": True,
        "shared_cross_player_calibration_uncertainty_modeled": False,
        "uncertainty_quality_penalty_applied": False,
        "overall_point_claimed_exact": False,
    }


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.0, Top100Membership.ROBUST_OUTSIDE_TOP100),
        (0.10, Top100Membership.LIKELY_OUTSIDE_TOP100),
        (0.35, Top100Membership.TOP100_BUBBLE),
        (0.65, Top100Membership.LIKELY_TOP100),
        (0.90, Top100Membership.ROBUST_TOP100),
        (1.0, Top100Membership.ROBUST_TOP100),
    ],
)
def test_top100_probability_boundaries(probability: float, expected: Top100Membership) -> None:
    assert top100_membership(probability) == expected


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.0, PairwiseOrder.STRONG_B_OVER_A),
        (0.10, PairwiseOrder.STRONG_B_OVER_A),
        (0.11, PairwiseOrder.LEAN_B_OVER_A),
        (0.35, PairwiseOrder.INDETERMINATE),
        (0.50, PairwiseOrder.INDETERMINATE),
        (0.65, PairwiseOrder.LEAN_A_OVER_B),
        (0.90, PairwiseOrder.STRONG_A_OVER_B),
    ],
)
def test_pairwise_probability_boundaries(probability: float, expected: PairwiseOrder) -> None:
    assert pairwise_order(probability) == expected


def test_status_mapping_never_penalizes_interval_quality() -> None:
    assert ranking_status("OFFICIAL_OVERALL_POINT", distribution_available=True) == "OFFICIAL"
    assert ranking_status("PROVISIONAL_OVERALL_POINT", distribution_available=True) == "PROVISIONAL"
    assert ranking_status("OVERALL_INTERVAL_ONLY", distribution_available=True) == "INTERVAL_NATIVE"
    assert ranking_status("OVERALL_UNAVAILABLE", distribution_available=False) == "UNAVAILABLE"
    card = player_card()
    interval = copy.deepcopy(card)
    interval["ranking_status"] = "INTERVAL_NATIVE"
    interval["overall_source_status"] = "OVERALL_INTERVAL_ONLY"
    assert PlayerLeaderboardRecord.model_validate(card).overall_center == (
        PlayerLeaderboardRecord.model_validate(interval).overall_center
    )
    with pytest.raises(ValueError, match="unavailable Overall"):
        ranking_status("OVERALL_UNAVAILABLE", distribution_available=True)


def test_unavailable_cannot_enter_leaderboard_but_retains_reason_codes() -> None:
    card = player_card()
    card["ranking_status"] = "UNAVAILABLE"
    card["overall_source_status"] = "OVERALL_UNAVAILABLE"
    with pytest.raises(ValidationError, match="unavailable player"):
        PlayerLeaderboardRecord.model_validate(card)
    unranked = UnrankedPlayerRecord(
        player_id="player_456",
        player_name="Other Player",
        ranking_status=RankingStatus.UNAVAILABLE,
        overall_source_status="OVERALL_UNAVAILABLE",
        reason_codes=("REQUIRED_DIMENSION_UNAVAILABLE",),
        ranking_policy_version=POLICY_VERSION,
    )
    assert unranked.reason_codes == ("REQUIRED_DIMENSION_UNAVAILABLE",)


def test_interval_center_and_navigation_require_explicit_labels() -> None:
    card = player_card()
    card["overall_center_label"] = None
    with pytest.raises(ValidationError, match="explicitly labeled"):
        PlayerLeaderboardRecord.model_validate(card)
    card = player_card()
    card["display_position_semantics"] = None
    with pytest.raises(ValidationError, match="navigational"):
        PlayerLeaderboardRecord.model_validate(card)


def test_probability_and_rank_bands_validate() -> None:
    card = player_card()
    card["top_25_probability"] = 0.9
    with pytest.raises(ValidationError, match="nondecreasing"):
        PlayerLeaderboardRecord.model_validate(card)
    card = player_card()
    card["rank_lower_95"] = 45.0
    with pytest.raises(ValidationError, match="nested"):
        PlayerLeaderboardRecord.model_validate(card)
    card = player_card()
    card["uncertainty_quality_penalty_applied"] = True
    with pytest.raises(ValidationError):
        PlayerLeaderboardRecord.model_validate(card)


def test_interval_dimension_is_never_labeled_official() -> None:
    with pytest.raises(ValidationError, match="no official point"):
        DimensionDisplay(
            value=80.0,
            lower_90=70.0,
            upper_90=90.0,
            source_status="LONGEVITY_INTERVAL_ONLY",
            value_is_official_point=True,
        )
    with pytest.raises(ValidationError, match="uncertainty range"):
        DimensionDisplay(
            value=80.0, source_status="LONGEVITY_INTERVAL_ONLY", value_is_official_point=False
        )
    with pytest.raises(ValidationError, match="requires a value"):
        DimensionDisplay(source_status="OFFICIAL_PEAK_POINT", value_is_official_point=True)


def test_pairwise_endpoint_requires_consistent_order_and_all_dimensions() -> None:
    dimension = DimensionDisplay(
        value=80.0, source_status="OFFICIAL_OFFENSE_POINT", value_is_official_point=True
    )
    comparison = {
        "player_a_id": "a",
        "player_b_id": "b",
        "player_a_ranking_status": "OFFICIAL",
        "player_b_ranking_status": "INTERVAL_NATIVE",
        "probability_a_above_b": 0.92,
        "ordering_label": "STRONG_A_OVER_B",
        "dimension_comparison": {name: (dimension, dimension) for name in DIMENSIONS},
        "uncertainty_context": "Conditional on frozen calibration; no exact-order claim.",
        "ranking_policy_version": POLICY_VERSION,
        "overall_substrate_version": "goatlab-v1-overall-v2-tiered",
        "conditional_on_frozen_measurement_architecture": True,
    }
    assert PairwiseComparison.model_validate(comparison).ordering_label == "STRONG_A_OVER_B"
    comparison["ordering_label"] = "INDETERMINATE"
    with pytest.raises(ValidationError, match="does not match probability"):
        PairwiseComparison.model_validate(comparison)
    comparison["ordering_label"] = "STRONG_A_OVER_B"
    comparison["player_b_id"] = "a"
    with pytest.raises(ValidationError, match="distinct players"):
        PairwiseComparison.model_validate(comparison)
    comparison["player_b_id"] = "b"
    comparison["player_b_ranking_status"] = "UNAVAILABLE"
    with pytest.raises(ValidationError, match="unavailable player"):
        PairwiseComparison.model_validate(comparison)
