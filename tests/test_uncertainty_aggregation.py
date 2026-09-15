from __future__ import annotations

import numpy as np

from goatlab.rankings.uncertainty_aggregation import (
    LONGEVITY_WEIGHTS,
    PEAK_THREE_YEAR_WEIGHT,
    contiguous_three_year_windows,
    fixed_midrank_ecdf,
    longest_run_scalar,
    longevity_components,
    peak_draws,
    quantile_interval,
)


def test_peak_reselects_complete_contiguous_window_per_draw() -> None:
    seasons = np.asarray([2000, 2001, 2002, 2004, 2005, 2006])
    values = np.asarray(
        [
            [99.0, 99.0, 99.0, 80.0, 80.0, 80.0],
            [80.0, 80.0, 80.0, 99.0, 99.0, 99.0],
        ]
    )
    result = peak_draws(values, seasons)
    assert contiguous_three_year_windows(seasons) == ((0, 1, 2), (3, 4, 5))
    assert result.window_indices.tolist() == [0, 1]
    assert np.allclose(result.values, [99.0, 99.0])


def test_peak_architecture_remains_70_30_and_ties_choose_earliest() -> None:
    seasons = np.asarray([2000, 2001, 2002, 2003])
    values = np.asarray([[100.0, 90.0, 90.0, 80.0]])
    result = peak_draws(values, seasons)
    expected_three = (100.0 + 90.0 + 90.0) / 3.0
    assert PEAK_THREE_YEAR_WEIGHT == 0.70
    assert np.isclose(result.values[0], 0.70 * expected_three + 0.30 * 100.0)
    tied = peak_draws(np.asarray([[90.0, 90.0, 90.0, 90.0]]), seasons)
    assert tied.window_indices[0] == 0


def test_incomplete_peak_window_is_not_created() -> None:
    seasons = np.asarray([2000, 2001, 2003])
    result = peak_draws(np.asarray([[99.0, 99.0, 99.0]]), seasons)
    assert result.values.size == 0


def test_longevity_components_use_fixed_threshold_cap_and_exact_run() -> None:
    seasons = np.asarray([2000, 2001, 2002, 2004, 2005])
    values = np.asarray([[79.0, 80.0, 85.0, 95.0, 90.0]])
    result = longevity_components(values, seasons)
    assert result.breadth.tolist() == [4.0]
    assert result.capped_area.tolist() == [2.5]
    assert result.longest_run.tolist() == [2.0]
    assert longest_run_scalar([True, True, True, False, True], [1, 2, 4, 5, 6]) == 2
    assert LONGEVITY_WEIGHTS == (0.35, 0.40, 0.25)


def test_fixed_ecdf_does_not_redraw_reference() -> None:
    reference = np.asarray([10.0, 20.0, 20.0, 40.0])
    first = fixed_midrank_ecdf(reference, np.asarray([20.0, 30.0]))
    second = fixed_midrank_ecdf(reference, np.asarray([20.0, 30.0]))
    assert np.array_equal(first, second)
    assert first[0] < first[1]


def test_empirical_intervals_are_nested() -> None:
    values = np.arange(101, dtype=float)
    lower80, upper80 = quantile_interval(values, 0.80)
    lower90, upper90 = quantile_interval(values, 0.90)
    lower95, upper95 = quantile_interval(values, 0.95)
    assert lower95 <= lower90 <= lower80 <= upper80 <= upper90 <= upper95
