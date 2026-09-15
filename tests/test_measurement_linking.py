from __future__ import annotations

import numpy as np
import pytest

from goatlab.rankings.measurement_linking import (
    conformal_radius,
    cross_fitted_predictions,
    deterministic_fold,
    fit_linker,
    interval_bounds,
    predict_linker,
)


def test_isotonic_linker_is_monotone_and_bounded() -> None:
    raw = np.asarray([0.0, 10.0, 20.0, 30.0, 40.0])
    reference = np.asarray([5.0, 30.0, 20.0, 80.0, 95.0])
    model = fit_linker("isotonic", raw, reference)
    predicted = predict_linker(model, np.linspace(-10.0, 50.0, 121))
    assert np.all(np.diff(predicted) >= -1e-12)
    assert float(np.min(predicted)) >= 0.0
    assert float(np.max(predicted)) <= 100.0


@pytest.mark.parametrize("method", ["identity", "linear", "quantile", "isotonic"])
def test_cross_fitting_is_deterministic(method: str) -> None:
    raw = np.linspace(0.0, 100.0, 250)
    reference = np.clip(4.0 + 0.91 * raw + 2.0 * np.sin(raw), 0.0, 100.0)
    folds = np.asarray([deterministic_fold(f"player-{index // 2}") for index in range(250)])
    first = cross_fitted_predictions(method, raw, reference, folds)  # type: ignore[arg-type]
    second = cross_fitted_predictions(method, raw, reference, folds)  # type: ignore[arg-type]
    assert np.array_equal(first, second)
    assert np.all(np.isfinite(first))


def test_grouped_fold_keeps_player_together() -> None:
    assert deterministic_fold("player-a") == deterministic_fold("player-a")
    assert deterministic_fold("player-a", seed=7) == deterministic_fold("player-a", seed=7)


def test_conformal_intervals_are_nested_and_contain_point() -> None:
    residuals = np.arange(1.0, 101.0)
    radii = {
        80: conformal_radius(residuals, 0.80),
        90: conformal_radius(residuals, 0.90),
        95: conformal_radius(residuals, 0.95),
    }
    bounds = interval_bounds(50.0, radii)
    assert bounds["lower_95"] <= bounds["lower_90"] <= bounds["lower_80"] <= 50.0
    assert 50.0 <= bounds["upper_80"] <= bounds["upper_90"] <= bounds["upper_95"]


def test_role_linker_uses_only_declared_role_not_player_identity() -> None:
    raw = np.tile(np.linspace(0.0, 100.0, 120), 2)
    roles = np.asarray(["GUARD"] * 120 + ["BIG"] * 120)
    reference = np.concatenate((0.8 * raw[:120] + 5.0, 0.9 * raw[120:] + 2.0))
    model = fit_linker("role_isotonic", raw, reference, roles)
    same_role = predict_linker(model, np.asarray([40.0, 40.0]), np.asarray(["GUARD", "GUARD"]))
    assert same_role[0] == same_role[1]
