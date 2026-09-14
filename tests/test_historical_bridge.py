from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from goatlab.rankings.historical_bridge import (
    clipped_interval,
    deterministic_fold,
    era_block_predictions,
    fit_latent_measurement,
    grouped_oof_ridge,
    interval_metrics,
    latent_scores,
    polynomial_features,
    practical_gate,
)


def test_grouped_folds_and_bridge_predictions_are_deterministic() -> None:
    assert deterministic_fold("player-a", salt="audit") == deterministic_fold(
        "player-a", salt="audit"
    )
    features = np.asarray([[value / 20.0] for value in range(20)])
    target = np.asarray([value / 20.0 for value in range(20)])
    groups = [f"group-{value}" for value in range(20)]
    first = grouped_oof_ridge(features, target, groups, folds=3, salt="test")
    second = grouped_oof_ridge(features, target, groups, folds=3, salt="test")
    assert np.array_equal(first, second)


def test_era_block_validation_holds_out_whole_blocks() -> None:
    features = np.asarray([[float(value)] for value in range(12)])
    target = np.asarray([value / 12.0 for value in range(12)])
    seasons = [1980 + value for value in range(12)]
    first, eligible = era_block_predictions(features, target, seasons, width=4)
    second, second_eligible = era_block_predictions(features, target, seasons, width=4)
    assert np.array_equal(eligible, second_eligible)
    assert np.array_equal(first, second)
    assert eligible.all()


def test_missing_measurement_is_not_replaced_with_observed_zero() -> None:
    values = np.asarray([[0.2, 0.8, 0.4], [0.8, 0.2, 0.6], [0.5, 0.5, 0.5]])
    model = fit_latent_measurement(values)
    masked = values.copy()
    masked[:, 2] = np.nan
    scores = latent_scores(model, masked)
    assert np.isfinite(scores).all()
    with pytest.raises(ValueError):
        polynomial_features([0.2, float("nan")])


def test_partial_identification_intervals_are_ordered_and_calibrated() -> None:
    intervals = [
        clipped_interval(0.05, 0.10, confidence=0.9),
        clipped_interval(0.50, 0.10, confidence=0.9),
        clipped_interval(0.95, 0.10, confidence=0.9),
    ]
    assert all(0.0 <= item.lower <= item.central <= item.upper <= 1.0 for item in intervals)
    metrics = interval_metrics([0.04, 0.55, 0.96], intervals)
    assert metrics["empirical_coverage"] == 1.0


def test_practical_gate_does_not_pass_partial_success() -> None:
    failed = practical_gate(
        {
            "observations": 100,
            "mean_absolute_error": 5.1,
            "spearman": 0.96,
            "mean_signed_error": 0.0,
            "more_than_10_points": 0.10,
        }
    )
    passed = practical_gate(
        {
            "observations": 100,
            "mean_absolute_error": 4.9,
            "spearman": 0.96,
            "mean_signed_error": 1.9,
            "more_than_10_points": 0.14,
        }
    )
    assert failed["passes"] is False
    assert passed["passes"] is True


def test_bridge_source_has_no_forbidden_targets_or_named_players() -> None:
    implementation = __import__("goatlab.rankings.historical_bridge", fromlist=["dummy"]).__file__
    assert implementation is not None
    source = Path(implementation).read_text(encoding="utf-8").lower()
    forbidden = (
        "mvp",
        "all_nba",
        "championship",
        "playoff",
        "postseason",
        "michael jordan",
        "lebron james",
    )
    assert all(term not in source for term in forbidden)
