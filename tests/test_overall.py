from __future__ import annotations

import math

import numpy as np
import pytest

from goatlab.rankings.overall import (
    DIMENSIONS,
    classify_rank_stability,
    kendall_tau_for_unique_orders,
    overall_score,
    proportional_perturbation,
    rank_scores,
    shapley_variance_influence,
    top_n_overlap,
    validate_weights,
)


def equal_weights() -> dict[str, float]:
    return {name: 1.0 / 7.0 for name in DIMENSIONS}


def test_weights_are_exact_complete_nonnegative_simplex() -> None:
    assert math.isclose(sum(validate_weights(equal_weights())), 1.0)
    with pytest.raises(ValueError):
        validate_weights({name: 0.1 for name in DIMENSIONS})
    bad = equal_weights()
    bad["PEAK"] = -0.1
    with pytest.raises(ValueError):
        validate_weights(bad)


def test_overall_requires_all_dimensions_without_redistribution() -> None:
    complete = {name: 70.0 for name in DIMENSIONS}
    assert overall_score(complete, equal_weights()) == pytest.approx(70.0)
    complete["ACCOLADES"] = None
    assert overall_score(complete, equal_weights()) is None


def test_overall_range_validation() -> None:
    profile = {name: 50.0 for name in DIMENSIONS}
    profile["WINNING"] = 101.0
    with pytest.raises(ValueError):
        overall_score(profile, equal_weights())


def test_proportional_perturbation_preserves_simplex_and_direction() -> None:
    result = proportional_perturbation(equal_weights(), "DEFENSE", 0.05)
    assert result["DEFENSE"] == pytest.approx(1 / 7 + 0.05)
    assert sum(result.values()) == pytest.approx(1.0)
    assert all(result[name] < 1 / 7 for name in DIMENSIONS if name != "DEFENSE")


def test_exact_shapley_variance_decomposition_sums_to_one() -> None:
    matrix = np.asarray(
        [[10, 20, 30, 40, 50, 60, 70], [20, 25, 35, 50, 45, 65, 60], [40, 30, 50, 60, 70, 55, 80]],
        dtype=float,
    )
    result = shapley_variance_influence(matrix, equal_weights())
    assert sum(result.shares) == pytest.approx(1.0)
    assert sum(result.contributions) == pytest.approx(result.overall_variance)


def test_deterministic_tie_handling_uses_canonical_id() -> None:
    ranked = rank_scores({"player_b": 80.0, "player_a": 80.0, "player_c": None})
    assert [row.player_id for row in ranked] == ["player_a", "player_b"]
    assert [row.rank for row in ranked] == [1, 2]
    assert all(row.tie_group_size == 2 for row in ranked)


def test_rank_diagnostics() -> None:
    assert kendall_tau_for_unique_orders(["a", "b", "c"], ["a", "c", "b"]) == pytest.approx(1 / 3)
    assert top_n_overlap(["a", "b", "c"], ["a", "c", "b"], 2) == 0.5
    assert classify_rank_stability(0.95, 20) == "HIGH"
    assert classify_rank_stability(0.6, 100) == "MODERATE"
    assert classify_rank_stability(0.1, 100) == "LOW"
