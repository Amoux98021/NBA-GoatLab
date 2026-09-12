from __future__ import annotations

import pytest

from goatlab.rankings.defense_forensics import (
    PresenceConfidence,
    broad_role,
    current_action_context,
    defense_candidate,
    defensive_presence_estimate,
    opponent_adjusted_residual,
    role_aware_action_context,
)


def test_v1_action_reconstruction_preserves_missingness() -> None:
    value, coverage = current_action_context(0.8, None, None)
    assert value == 0.8
    assert coverage == 0.5
    unavailable, missing_coverage = current_action_context(None, None, None)
    assert unavailable is None
    assert missing_coverage == 0.0


def test_presence_requires_real_with_and_without_samples() -> None:
    estimate = defensive_presence_estimate([1.0] * 80, [-1.0] * 2)
    assert estimate.adjusted_difference is None
    assert estimate.confidence is PresenceConfidence.INSUFFICIENT_SAMPLE
    assert estimate.games_without == 2


def test_presence_shrinkage_is_deterministic_and_not_an_injury_bonus() -> None:
    estimate = defensive_presence_estimate([2.0] * 20, [0.0] * 10)
    assert estimate.raw_difference == 2.0
    assert estimate.adjusted_difference is not None
    assert 0.0 < estimate.adjusted_difference < estimate.raw_difference
    assert estimate.reliability == pytest.approx((200 / 30) / ((200 / 30) + 20))


def test_opponent_adjustment_has_defensive_direction() -> None:
    assert (
        opponent_adjusted_residual(
            expected_opponent_points=110.0,
            actual_opponent_points=100.0,
        )
        == 10.0
    )


def test_missing_presence_is_explicitly_reweighted_not_zeroed() -> None:
    value, coverage = defense_candidate(
        team_suppression=0.4,
        action_context=0.8,
        presence_impact=None,
        weights=(0.3, 0.3, 0.4),
    )
    assert value == pytest.approx(0.6)
    assert coverage == pytest.approx(0.6)
    assert defense_candidate(
        team_suppression=None,
        action_context=1.0,
        presence_impact=1.0,
    ) == (None, 0.0)


def test_role_evidence_does_not_force_equal_total_value() -> None:
    guard_actions, _ = role_aware_action_context(0.4, 0.9, 0.1)
    rim_actions, _ = role_aware_action_context(0.9, 0.3, 0.95)
    assert guard_actions is not None and rim_actions is not None
    assert rim_actions > guard_actions


def test_position_mapping_never_infers_unknown_role() -> None:
    assert broad_role("Guard") == "GUARD"
    assert broad_role("Forward-Guard") == "WING"
    assert broad_role("Center") == "BIG"
    assert broad_role("") is None
    assert broad_role("Unknown") is None
