from __future__ import annotations

import numpy as np

from goatlab.rankings.interval_native import (
    apply_rank_band_offsets,
    crossfit_rank_bands,
    deterministic_ranks,
    pairwise_matrix,
    quantile_rank_bands,
    rank_draw_matrix,
)


def test_rank_simulation_is_deterministic() -> None:
    draws = np.asarray([[9.0, 7.0], [8.0, 10.0], [7.0, 8.0]])
    expected = np.asarray([[1, 3], [2, 1], [3, 2]], dtype=np.int32)
    assert np.array_equal(rank_draw_matrix(draws), expected)
    assert np.array_equal(rank_draw_matrix(draws), rank_draw_matrix(draws))


def test_deterministic_ranks_use_player_id_for_ties() -> None:
    ranks = deterministic_ranks([5.0, 5.0, 4.0], ["b", "a", "c"], descending=True)
    assert ranks.tolist() == [2, 1, 3]


def test_pairwise_probabilities_are_complementary_without_ties() -> None:
    draws = np.asarray([[3.0, 1.0, 4.0], [2.0, 5.0, 0.0]])
    probabilities = pairwise_matrix(draws, np.asarray([0, 1]))
    assert probabilities[0, 1] + probabilities[1, 0] == 1.0
    assert probabilities[0, 0] == 0.5


def test_crossfit_rank_bands_are_nested_and_deterministic() -> None:
    players = [f"player_{index}" for index in range(20)]
    draws = np.tile(np.arange(1, 21, dtype=float)[:, None], (1, 100))
    raw = quantile_rank_bands(draws)
    reference = np.arange(1, 21)
    first, offsets = crossfit_rank_bands(players, reference, raw, 20)
    second, second_offsets = crossfit_rank_bands(players, reference, raw, 20)
    assert offsets == second_offsets
    for level in (50, 80, 90, 95):
        assert np.array_equal(first[level][0], second[level][0])
        assert np.array_equal(first[level][1], second[level][1])
    for inner, outer in ((50, 80), (80, 90), (90, 95)):
        assert np.all(first[outer][0] <= first[inner][0])
        assert np.all(first[inner][1] <= first[outer][1])


def test_signed_deployment_offsets_never_invert_or_unorder_bands() -> None:
    raw = {
        50: (np.asarray([4.0]), np.asarray([6.0])),
        80: (np.asarray([3.0]), np.asarray([7.0])),
        90: (np.asarray([2.0]), np.asarray([8.0])),
        95: (np.asarray([1.0]), np.asarray([9.0])),
    }
    calibrated = apply_rank_band_offsets(raw, {50: -0.02, 80: -0.01, 90: 0.0, 95: 0.01}, 10)
    for lower, upper in calibrated.values():
        assert np.all(lower <= upper)
    for inner, outer in ((50, 80), (80, 90), (90, 95)):
        assert np.all(calibrated[outer][0] <= calibrated[inner][0])
        assert np.all(calibrated[inner][1] <= calibrated[outer][1])
