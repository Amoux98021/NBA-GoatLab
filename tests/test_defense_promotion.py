from __future__ import annotations

import numpy as np
import pytest

from goatlab.rankings.defense_promotion import (
    blended_presence,
    confidence_from_channels,
    continuous_presence_estimate,
    deterministic_group_fold,
    expected_presence_features,
    fit_ridge,
    predict_ridge,
    weighted_three_channel,
)


def test_candidate_formula_is_exact_and_bounded() -> None:
    assert weighted_three_channel(0.8, 0.6, 0.4) == pytest.approx(0.58)
    with pytest.raises(ValueError):
        weighted_three_channel(0.5, -0.1, 0.5)


def test_continuous_presence_has_no_hard_ten_five_gate() -> None:
    nine_four = continuous_presence_estimate([1.0] * 9, [0.0] * 4)
    ten_five = continuous_presence_estimate([1.0] * 10, [0.0] * 5)
    assert nine_four.shrunk_difference is not None
    assert ten_five.shrunk_difference is not None
    assert 0.0 < nine_four.threshold_continuity < ten_five.threshold_continuity == 1.0


def test_tiny_presence_sample_remains_unavailable_not_zero() -> None:
    estimate = continuous_presence_estimate([1.0], [0.0] * 10)
    assert estimate.raw_difference is None
    assert estimate.shrunk_difference is None
    assert estimate.threshold_continuity == 0.0


def test_presence_blend_uses_expected_fallback_without_quality_penalty() -> None:
    fallback, fallback_type = blended_presence(0.62, None, 0.0)
    partial, partial_type = blended_presence(0.62, 0.82, 0.25)
    observed, observed_type = blended_presence(0.62, 0.82, 1.0)
    assert fallback == pytest.approx(0.62)
    assert fallback_type == "EXPECTED_PRESENCE"
    assert partial == pytest.approx(0.67)
    assert partial_type == "RELIABILITY_BLEND"
    assert observed == pytest.approx(0.82)
    assert observed_type == "OBSERVED"


def test_group_folds_and_ridge_are_deterministic() -> None:
    assert deterministic_group_fold("player_1") == deterministic_group_fold("player_1")
    features = np.asarray([[0.1, 0.2], [0.2, 0.4], [0.8, 0.7], [0.9, 0.8]])
    target = np.asarray([0.2, 0.3, 0.7, 0.8])
    first = fit_ridge(features, target, alpha=1.0)
    second = fit_ridge(features, target, alpha=1.0)
    assert first == second
    assert np.array_equal(predict_ridge(first, features), predict_ridge(second, features))


def test_expected_presence_features_exclude_awards_and_modern_metrics() -> None:
    features = expected_presence_features(team=0.6, action=0.7, role="GUARD")
    assert len(features) == 8
    assert features[:3] == pytest.approx((0.6, 0.7, 0.42))
    assert features[3:] == (1.0, 1.0, 0.0, 0.0, 0.0)


def test_confidence_does_not_modify_quality() -> None:
    score = weighted_three_channel(0.5, 0.5, 0.5)
    strong = confidence_from_channels(
        team_available=True,
        action_coverage=1.0,
        presence_reliability=1.0,
        fallback_type="OBSERVED",
    )
    limited = confidence_from_channels(
        team_available=True,
        action_coverage=0.5,
        presence_reliability=0.0,
        fallback_type="EXPECTED_PRESENCE",
    )
    assert score == 0.5
    assert strong[0] == "STRONG"
    assert limited[0] == "LIMITED"
