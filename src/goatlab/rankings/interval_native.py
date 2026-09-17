"""Deterministic rank-distribution utilities for interval-native GOATLab research."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import numpy as np
import numpy.typing as npt

RANKING_POLICY_VERSION = "goatlab-v1-ranking-policy-v2-uncertainty-research"
RANKING_POLICY_AUDIT_VERSION = "goatlab-step-0015o-ranking-policy-audit-v1"
RANK_LEVELS = (0.50, 0.80, 0.90, 0.95)


def deterministic_ranks(
    values: npt.ArrayLike, player_ids: Sequence[str], *, descending: bool
) -> npt.NDArray[np.int32]:
    """Return one-based ordinal ranks with canonical player-id tie breaking."""

    scores: npt.NDArray[np.float64] = np.asarray(values, dtype=float)
    identifiers: npt.NDArray[np.str_] = np.asarray(player_ids, dtype=str)
    primary = -scores if descending else scores
    order = np.lexsort((identifiers, primary))
    ranks: npt.NDArray[np.int32] = np.empty(len(scores), dtype=np.int32)
    ranks[order] = np.arange(1, len(scores) + 1, dtype=np.int32)
    return ranks


def rank_draw_matrix(draws: np.ndarray) -> npt.NDArray[np.int32]:
    """Rank player rows within every simulation column."""

    matrix = np.asarray(draws, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("draw matrix must be two-dimensional")
    order = np.argsort(-matrix, axis=0, kind="stable")
    ranks: npt.NDArray[np.int32] = np.empty_like(order, dtype=np.int32)
    columns = np.arange(matrix.shape[1])
    ranks[order, columns] = np.arange(1, matrix.shape[0] + 1, dtype=np.int32)[:, None]
    return ranks


def spearman_from_ranks(left: np.ndarray, right: np.ndarray) -> float:
    """Pearson correlation of complete ordinal ranks."""

    return float(np.corrcoef(np.asarray(left, dtype=float), np.asarray(right, dtype=float))[0, 1])


def _inversion_count(values: list[int]) -> int:
    def sort_count(items: list[int]) -> tuple[list[int], int]:
        if len(items) <= 1:
            return items, 0
        midpoint = len(items) // 2
        left, left_count = sort_count(items[:midpoint])
        right, right_count = sort_count(items[midpoint:])
        merged: list[int] = []
        i = j = cross = 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                cross += len(left) - i
                j += 1
        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged, left_count + right_count + cross

    return sort_count(values)[1]


def kendall_tau_from_ranks(reference: np.ndarray, candidate: np.ndarray) -> float:
    """Kendall tau-a for deterministic complete rankings without ties."""

    reference_values = np.asarray(reference, dtype=int)
    candidate_values = np.asarray(candidate, dtype=int)
    order = np.argsort(reference_values, kind="stable")
    inversions = _inversion_count(candidate_values[order].tolist())
    pairs = len(order) * (len(order) - 1) // 2
    return 1.0 if pairs == 0 else 1.0 - 2.0 * inversions / pairs


def ranking_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    """Summarize a candidate complete ranking against a reference ordering."""

    reference_values = np.asarray(reference, dtype=int)
    candidate_values = np.asarray(candidate, dtype=int)
    differences = candidate_values - reference_values
    output = {
        "spearman": spearman_from_ranks(reference_values, candidate_values),
        "kendall_tau": kendall_tau_from_ranks(reference_values, candidate_values),
        "rank_bias": float(np.mean(differences)),
        "rank_mae": float(np.mean(np.abs(differences))),
        "median_absolute_rank_error": float(np.median(np.abs(differences))),
    }
    for n in (10, 25, 50, 100):
        reference_top = set(np.flatnonzero(reference_values <= n).tolist())
        candidate_top = set(np.flatnonzero(candidate_values <= n).tolist())
        output[f"top_{n}_overlap"] = len(reference_top & candidate_top) / n
    return output


def quantile_rank_bands(rank_draws: np.ndarray) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Return central empirical rank bands for the frozen levels."""

    ranks = np.asarray(rank_draws, dtype=float)
    output: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for level in RANK_LEVELS:
        alpha = (1.0 - level) / 2.0
        output[int(level * 100)] = (
            np.quantile(ranks, alpha, axis=1),
            np.quantile(ranks, 1.0 - alpha, axis=1),
        )
    return output


def stable_fold(player_id: str, folds: int = 5) -> int:
    """Assign a deterministic player-grouped fold."""

    digest = hashlib.sha256(player_id.encode()).hexdigest()
    return int(digest[:8], 16) % folds


def conformal_quantile(values: np.ndarray, coverage: float) -> float:
    """Finite-sample conservative split-conformal quantile."""

    array = np.sort(np.asarray(values, dtype=float))
    if array.size == 0:
        return 0.0
    index = min(math.ceil((array.size + 1) * coverage) - 1, array.size - 1)
    return float(array[max(index, 0)])


def crossfit_rank_bands(
    player_ids: Sequence[str],
    reference_ranks: np.ndarray,
    raw_bands: dict[int, tuple[np.ndarray, np.ndarray]],
    population: int,
    centers: npt.ArrayLike | None = None,
) -> tuple[dict[int, tuple[np.ndarray, np.ndarray]], dict[int, float]]:
    """Cross-fit signed conformalized-quantile bands and deployment offsets."""

    reference = np.asarray(reference_ranks, dtype=float) / population
    folds = np.asarray([stable_fold(player_id) for player_id in player_ids])
    calibrated: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    deployment: dict[int, float] = {}
    for level, (raw_lower, raw_upper) in raw_bands.items():
        lower = np.asarray(raw_lower, dtype=float) / population
        upper = np.asarray(raw_upper, dtype=float) / population
        # Signed CQR scores allow held-out calibration to contract a conservative
        # raw band as well as expand an under-covering one. No score/rank center is
        # changed; only the uncertainty envelope is calibrated.
        scores = np.maximum(lower - reference, reference - upper)
        adjusted_lower: npt.NDArray[np.float64] = np.empty(len(reference), dtype=float)
        adjusted_upper: npt.NDArray[np.float64] = np.empty(len(reference), dtype=float)
        for fold in range(5):
            held_out = folds == fold
            calibration = ~held_out
            offset = conformal_quantile(scores[calibration], level / 100.0)
            adjusted_lower[held_out] = np.maximum(1.0 / population, lower[held_out] - offset)
            adjusted_upper[held_out] = np.minimum(1.0, upper[held_out] + offset)
        deployment[level] = conformal_quantile(scores, level / 100.0)
        calibrated[level] = (adjusted_lower * population, adjusted_upper * population)
    point = (
        np.asarray(centers, dtype=float)
        if centers is not None
        else (np.asarray(raw_bands[50][0]) + np.asarray(raw_bands[50][1])) / 2.0
    )
    previous_lower: np.ndarray | None = None
    previous_upper: np.ndarray | None = None
    for level in sorted(calibrated):
        lower, upper = calibrated[level]
        lower = np.minimum(lower, point)
        upper = np.maximum(upper, point)
        if previous_lower is not None and previous_upper is not None:
            lower = np.minimum(lower, previous_lower)
            upper = np.maximum(upper, previous_upper)
        calibrated[level] = (lower, upper)
        previous_lower, previous_upper = lower, upper
    return calibrated, deployment


def apply_rank_band_offsets(
    raw_bands: dict[int, tuple[np.ndarray, np.ndarray]],
    offsets: dict[int, float],
    population: int,
    centers: npt.ArrayLike | None = None,
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Apply validation-derived signed percentile offsets to a deployment population."""

    output: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    point = (
        np.asarray(centers, dtype=float)
        if centers is not None
        else (np.asarray(raw_bands[50][0]) + np.asarray(raw_bands[50][1])) / 2.0
    )
    previous_lower: np.ndarray | None = None
    previous_upper: np.ndarray | None = None
    for level in sorted(raw_bands):
        lower, upper = raw_bands[level]
        expansion = offsets[level] * population
        adjusted_lower = np.maximum(1.0, np.asarray(lower) - expansion)
        adjusted_upper = np.minimum(float(population), np.asarray(upper) + expansion)
        adjusted_lower = np.minimum(adjusted_lower, point)
        adjusted_upper = np.maximum(adjusted_upper, point)
        if previous_lower is not None and previous_upper is not None:
            adjusted_lower = np.minimum(adjusted_lower, previous_lower)
            adjusted_upper = np.maximum(adjusted_upper, previous_upper)
        output[level] = (adjusted_lower, adjusted_upper)
        previous_lower, previous_upper = adjusted_lower, adjusted_upper
    return output


def band_report(
    reference_ranks: np.ndarray,
    bands: dict[int, tuple[np.ndarray, np.ndarray]],
) -> dict[str, dict[str, float]]:
    """Report coverage and width of rank bands."""

    reference = np.asarray(reference_ranks, dtype=float)
    return {
        str(level): {
            "coverage": float(np.mean((lower <= reference) & (reference <= upper))),
            "mean_width": float(np.mean(upper - lower)),
            "median_width": float(np.median(upper - lower)),
        }
        for level, (lower, upper) in bands.items()
    }


def probability_bins(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
    edges: Sequence[float],
) -> list[dict[str, float | int | list[float]]]:
    """Return reliability-bin summaries with a closed final interval."""

    probability = np.asarray(probabilities, dtype=float)
    outcome = np.asarray(outcomes, dtype=float)
    output: list[dict[str, float | int | list[float]]] = []
    for index, (lower, upper) in enumerate(pairwise(edges)):
        selected = (probability >= lower) & (
            (probability <= upper) if index == len(edges) - 2 else (probability < upper)
        )
        if not np.any(selected):
            continue
        output.append(
            {
                "probability_range": [float(lower), float(upper)],
                "n": int(np.sum(selected)),
                "mean_predicted": float(np.mean(probability[selected])),
                "observed_rate": float(np.mean(outcome[selected])),
            }
        )
    return output


def expected_calibration_error(bins: list[dict[str, Any]]) -> float:
    """Return count-weighted absolute calibration error across reliability bins."""

    total = sum(int(item["n"]) for item in bins)
    if total == 0:
        return 0.0
    return float(
        sum(
            int(item["n"]) * abs(float(item["mean_predicted"]) - float(item["observed_rate"]))
            for item in bins
        )
        / total
    )


def topn_probability_report(
    reference_ranks: np.ndarray, rank_draws: np.ndarray
) -> dict[str, dict[str, Any]]:
    """Validate Top-N probabilities and deterministic central membership."""

    reference = np.asarray(reference_ranks, dtype=int)
    ranks = np.asarray(rank_draws, dtype=int)
    output: dict[str, dict[str, Any]] = {}
    for n in (10, 25, 50, 100):
        probabilities = np.mean(ranks <= n, axis=1)
        outcomes = (reference <= n).astype(float)
        bins = probability_bins(probabilities, outcomes, (0.0, 0.2, 0.4, 0.6, 0.8, 1.0))
        output[f"top_{n}"] = {
            "brier_score": float(np.mean((probabilities - outcomes) ** 2)),
            "expected_calibration_error": expected_calibration_error(bins),
            "calibration_bins": bins,
        }
    return output


def pairwise_probability_report(
    reference_scores: np.ndarray,
    draws: np.ndarray,
    *,
    seed: int,
    pairs: int = 20_000,
) -> dict[str, Any]:
    """Validate confidence in the favored direction on deterministic sampled pairs."""

    scores = np.asarray(reference_scores, dtype=float)
    matrix = np.asarray(draws, dtype=float)
    rng = np.random.default_rng(seed)
    left: list[int] = []
    right: list[int] = []
    seen: set[tuple[int, int]] = set()
    maximum = len(scores) * (len(scores) - 1) // 2
    target = min(pairs, maximum)
    while len(left) < target:
        candidates = rng.integers(0, len(scores), size=(target - len(left), 2))
        for first, second in candidates:
            if first == second:
                continue
            pair = (int(min(first, second)), int(max(first, second)))
            if pair in seen:
                continue
            seen.add(pair)
            left.append(pair[0])
            right.append(pair[1])
            if len(left) == target:
                break
    left_array: npt.NDArray[np.int_] = np.asarray(left, dtype=int)
    right_array: npt.NDArray[np.int_] = np.asarray(right, dtype=int)
    probability_left = np.mean(matrix[left_array] > matrix[right_array], axis=1)
    favor_left = probability_left >= 0.5
    confidence = np.maximum(probability_left, 1.0 - probability_left)
    reference_left = scores[left_array] > scores[right_array]
    correct = np.where(favor_left, reference_left, ~reference_left).astype(float)
    bins = probability_bins(confidence, correct, (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0))
    return {
        "pairs": target,
        "brier_score_directional": float(np.mean((confidence - correct) ** 2)),
        "expected_calibration_error": expected_calibration_error(bins),
        "calibration_bins": bins,
        "strong_threshold": 0.90,
        "lean_threshold": 0.65,
    }


def strongly_connected_components(adjacency: np.ndarray) -> list[list[int]]:
    """Tarjan strongly connected components for a directed comparison graph."""

    graph = np.asarray(adjacency, dtype=bool)
    index = 0
    stack: list[int] = []
    indices = [-1] * len(graph)
    lowlink = [0] * len(graph)
    on_stack = [False] * len(graph)
    components: list[list[int]] = []

    def visit(node: int) -> None:
        nonlocal index
        indices[node] = lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack[node] = True
        for neighbor in np.flatnonzero(graph[node]).tolist():
            if indices[neighbor] == -1:
                visit(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif on_stack[neighbor]:
                lowlink[node] = min(lowlink[node], indices[neighbor])
        if lowlink[node] == indices[node]:
            component: list[int] = []
            while True:
                member = stack.pop()
                on_stack[member] = False
                component.append(member)
                if member == node:
                    break
            components.append(component)

    for node in range(len(graph)):
        if indices[node] == -1:
            visit(node)
    return components


def pairwise_matrix(
    draws: np.ndarray, indexes: np.ndarray, block: int = 20
) -> npt.NDArray[np.float64]:
    """Build an exact pairwise probability matrix for a bounded audit subset."""

    selected = np.asarray(draws, dtype=float)[np.asarray(indexes, dtype=int)]
    output: npt.NDArray[np.float64] = np.empty((len(selected), len(selected)), dtype=float)
    for start in range(0, len(selected), block):
        stop = min(start + block, len(selected))
        output[start:stop] = np.mean(selected[start:stop, None, :] > selected[None, :, :], axis=2)
    np.fill_diagonal(output, 0.5)
    return output
