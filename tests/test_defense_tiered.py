from __future__ import annotations

import pytest

from goatlab.rankings.defense_tiered import (
    career_defense_status,
    classify_defense_form,
    defense_weights,
    observed_defense_score,
    point_eligibility,
)


def test_selected_weights_are_bounded_and_sum_to_one() -> None:
    team, action, presence = defense_weights(0.10)
    assert (team, action, presence) == pytest.approx((0.10, 27 / 70, 36 / 70))
    assert team + action + presence == pytest.approx(1.0)
    assert team <= 0.10


def test_missing_presence_is_not_zero_or_redistributed() -> None:
    full, full_coverage = observed_defense_score(
        team=0.8,
        action=0.6,
        presence=0.9,
        presence_reliability=1.0,
    )
    missing, missing_coverage = observed_defense_score(
        team=0.8,
        action=0.6,
        presence=None,
        presence_reliability=0.0,
    )
    assert full == pytest.approx(0.10 * 0.8 + (27 / 70) * 0.6 + (36 / 70) * 0.9)
    assert missing == pytest.approx(0.10 * 0.8 + (27 / 70) * 0.6)
    assert full_coverage == pytest.approx(1.0)
    assert missing_coverage == pytest.approx(34 / 70)
    assert missing != pytest.approx(0.50 * 0.8 + 0.50 * 0.6)


def test_presence_reliability_leaves_uncertainty_unallocated() -> None:
    value, coverage = observed_defense_score(
        team=0.5,
        action=0.5,
        presence=1.0,
        presence_reliability=0.4,
    )
    assert value == pytest.approx(0.10 * 0.5 + (27 / 70) * 0.5 + (36 / 70) * 0.4)
    assert coverage == pytest.approx(0.10 + 27 / 70 + (36 / 70) * 0.4)


@pytest.mark.parametrize(
    ("team", "rebound", "stocks", "presence", "reliability", "expected"),
    [
        (True, True, True, True, 1.0, "DEF_FULL"),
        (False, True, True, True, 1.0, "DEF_ACTION_PRESENCE_NO_CONTEXT"),
        (True, True, True, True, 0.6, "DEF_ACTION_PARTIAL_PRESENCE"),
        (True, True, True, False, 0.0, "DEF_ACTION_NO_PRESENCE"),
        (True, True, False, True, 1.0, "DEF_TRADITIONAL_PRESENCE"),
        (True, True, False, False, 0.0, "DEF_TRADITIONAL"),
        (False, True, False, False, 0.0, "DEF_REBOUND_ONLY"),
        (True, False, False, False, 0.0, "DEF_CONTEXT_ONLY"),
        (False, False, False, False, 0.0, "DEF_UNAVAILABLE"),
    ],
)
def test_form_reason_codes_are_evidence_based(
    team: bool,
    rebound: bool,
    stocks: bool,
    presence: bool,
    reliability: float,
    expected: str,
) -> None:
    assert (
        classify_defense_form(
            team_available=team,
            rebound_available=rebound,
            stocks_available=stocks,
            presence_available=presence,
            presence_reliability=reliability,
        )
        == expected
    )


def test_point_gates_require_role_and_interval_calibration() -> None:
    metrics = {
        "point": {"mae": 4.0, "spearman": 0.97, "bias": 0.2, "gt_10": 0.10},
        "intervals": {"90": {"coverage": 0.90}},
        "roles": {
            "GUARD": {"n": 200, "bias": -1.0},
            "BIG": {"n": 200, "bias": 1.5},
        },
    }
    passed, gates = point_eligibility(metrics)
    assert passed
    assert all(gates.values())
    metrics["roles"]["GUARD"]["bias"] = -3.1
    assert not point_eligibility(metrics)[0]


def test_interval_only_career_center_is_not_an_official_point() -> None:
    assert (
        career_defense_status(
            usable_seasons=10,
            official_seasons=5,
            point_eligible_seasons=7,
            career_pattern_passed=False,
        )
        == "DEFENSE_INTERVAL_ONLY"
    )
    assert (
        career_defense_status(
            usable_seasons=10,
            official_seasons=10,
            point_eligible_seasons=10,
            career_pattern_passed=True,
        )
        == "OFFICIAL_DEFENSE_POINT"
    )
