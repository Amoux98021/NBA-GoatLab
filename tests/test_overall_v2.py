from __future__ import annotations

import numpy as np
import pytest

from goatlab.rankings.overall_v2 import (
    FROZEN_OVERALL_WEIGHTS,
    couple_defense_ranks,
    nearest_psd_correlation,
    overall_draws_v2,
    variance_decomposition,
)


def test_frozen_overall_weights_are_exact() -> None:
    assert sum(FROZEN_OVERALL_WEIGHTS.values()) == pytest.approx(1.0)
    assert FROZEN_OVERALL_WEIGHTS == {
        "PEAK": 0.17,
        "LONGEVITY": 0.14,
        "OFFENSE": 0.16,
        "DEFENSE": 0.14,
        "PLAYOFFS": 0.18,
        "ACCOLADES": 0.10,
        "WINNING": 0.11,
    }


def test_nearest_psd_correlation_is_symmetric_and_psd() -> None:
    invalid = np.asarray([[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]])
    corrected, report = nearest_psd_correlation(invalid)
    assert report["corrected"] is True
    assert np.allclose(corrected, corrected.T)
    assert np.allclose(np.diag(corrected), 1.0)
    assert float(np.min(np.linalg.eigvalsh(corrected))) >= -1e-10


def test_coupling_is_deterministic_and_preserves_every_marginal() -> None:
    peak = np.linspace(10.0, 90.0, 250)
    longevity = np.roll(peak, 31)
    defense = np.linspace(5.0, 99.0, 250) ** 0.98
    target = np.asarray([[1.0, 0.4, 0.5], [0.4, 1.0, 0.2], [0.5, 0.2, 1.0]])
    first, _ = couple_defense_ranks(peak, longevity, defense, target, seed=1515)
    second, _ = couple_defense_ranks(peak, longevity, defense, target, seed=1515)
    assert np.array_equal(first, second)
    assert np.array_equal(np.sort(first), np.sort(defense))
    assert np.array_equal(peak, np.linspace(10.0, 90.0, 250))
    assert np.array_equal(longevity, np.roll(peak, 31))


def test_overall_draws_do_not_renormalize_or_penalize_confidence() -> None:
    peak = np.asarray([80.0, 90.0])
    longevity = np.asarray([70.0, 75.0])
    defense = np.asarray([60.0, 65.0])
    result = overall_draws_v2(peak, longevity, defense, 40.0)
    expected = 0.17 * peak + 0.14 * longevity + 0.14 * defense + 40.0
    assert np.allclose(result, expected)


def test_variance_decomposition_matches_empirical_variance() -> None:
    peak = np.asarray([50.0, 60.0, 75.0, 90.0])
    longevity = np.asarray([40.0, 70.0, 65.0, 95.0])
    defense = np.asarray([55.0, 45.0, 80.0, 85.0])
    report = variance_decomposition(peak, longevity, defense)
    assert report["analytic_empirical_difference"] == pytest.approx(0.0, abs=1e-12)
