"""Transparent Overall-rating mechanics for GOATLab V1.

The official path requires all seven frozen V1 dimensions. Missing values never
trigger weight redistribution. Functions here are deterministic and contain no
player-specific adjustments or external-ranking targets.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

OVERALL_METHODOLOGY_VERSION = "goatlab-v1-overall-v1"
OVERALL_RANDOM_SEED = 150015

DIMENSIONS = (
    "PEAK",
    "LONGEVITY",
    "OFFENSE",
    "DEFENSE",
    "PLAYOFFS",
    "ACCOLADES",
    "WINNING",
)


@dataclass(frozen=True)
class RankedScore:
    player_id: str
    score: float
    rank: int
    tie_group_size: int


@dataclass(frozen=True)
class VarianceInfluence:
    overall_variance: float
    contributions: tuple[float, ...]
    shares: tuple[float, ...]


def validate_weights(weights: Mapping[str, float]) -> tuple[float, ...]:
    """Validate and return weights in the frozen dimension order."""
    if set(weights) != set(DIMENSIONS):
        raise ValueError("weights must contain exactly the seven V1 dimensions")
    ordered = tuple(float(weights[name]) for name in DIMENSIONS)
    if any(not math.isfinite(value) or value < 0.0 for value in ordered):
        raise ValueError("weights must be finite and non-negative")
    if not math.isclose(sum(ordered), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("weights must sum to one")
    return ordered


def overall_score(
    profile: Mapping[str, float | None], weights: Mapping[str, float]
) -> float | None:
    """Return the weighted arithmetic score only for a complete profile."""
    ordered = validate_weights(weights)
    values: list[float] = []
    for dimension in DIMENSIONS:
        value = profile.get(dimension)
        if value is None or not math.isfinite(float(value)):
            return None
        number = float(value)
        if not 0.0 <= number <= 100.0:
            raise ValueError("dimension scores must be in [0, 100]")
        values.append(number)
    return float(sum(weight * value for weight, value in zip(ordered, values, strict=True)))


def rank_scores(scores: Mapping[str, float | None]) -> list[RankedScore]:
    """Rank finite scores descending; canonical player ID deterministically breaks ties."""
    ordered = sorted(
        (
            (player_id, float(value))
            for player_id, value in scores.items()
            if value is not None and math.isfinite(float(value))
        ),
        key=lambda item: (-item[1], item[0]),
    )
    tie_sizes: dict[float, int] = {}
    for _, value in ordered:
        tie_sizes[value] = tie_sizes.get(value, 0) + 1
    return [
        RankedScore(player_id, value, index, tie_sizes[value])
        for index, (player_id, value) in enumerate(ordered, start=1)
    ]


def proportional_perturbation(
    weights: Mapping[str, float], dimension: str, delta: float
) -> dict[str, float]:
    """Change one weight and proportionally rescale the other six."""
    ordered = dict(zip(DIMENSIONS, validate_weights(weights), strict=True))
    if dimension not in ordered:
        raise ValueError("unknown dimension")
    target = ordered[dimension] + float(delta)
    if not 0.0 <= target <= 1.0:
        raise ValueError("perturbed weight must remain in [0, 1]")
    old_remainder = 1.0 - ordered[dimension]
    new_remainder = 1.0 - target
    if old_remainder <= 0.0:
        raise ValueError("cannot proportionally adjust a degenerate vector")
    result = {
        name: target if name == dimension else value * new_remainder / old_remainder
        for name, value in ordered.items()
    }
    # Assign floating residue deterministically to the final non-target dimension.
    residue = 1.0 - sum(result.values())
    receiver = next(name for name in reversed(DIMENSIONS) if name != dimension)
    result[receiver] += residue
    validate_weights(result)
    return result


def shapley_variance_influence(
    matrix: np.ndarray, weights: Mapping[str, float]
) -> VarianceInfluence:
    """Exact Shapley allocation for variance of a linear weighted sum.

    For v(S)=Var(sum_{i in S} w_i X_i), the Shapley contribution is
    w_i Cov(X_i, Y). This gives each pairwise covariance half to each party.
    """
    if matrix.ndim != 2 or matrix.shape[1] != len(DIMENSIONS) or matrix.shape[0] < 2:
        raise ValueError("matrix must contain at least two complete seven-dimension rows")
    if not np.isfinite(matrix).all():
        raise ValueError("matrix must be finite")
    vector = np.asarray(validate_weights(weights), dtype=np.float64)
    covariance = np.cov(matrix, rowvar=False, ddof=0)
    contributions = vector * (covariance @ vector)
    overall_variance = float(vector @ covariance @ vector)
    if overall_variance <= 0.0:
        raise ValueError("overall variance must be positive")
    shares = contributions / overall_variance
    if not math.isclose(float(shares.sum()), 1.0, abs_tol=1e-10):
        raise AssertionError("Shapley contributions do not sum to total variance")
    return VarianceInfluence(
        overall_variance,
        tuple(float(value) for value in contributions),
        tuple(float(value) for value in shares),
    )


def top_n_overlap(left: Sequence[str], right: Sequence[str], n: int) -> float:
    if n <= 0:
        raise ValueError("n must be positive")
    actual = min(n, len(left), len(right))
    if actual == 0:
        return 0.0
    return len(set(left[:actual]) & set(right[:actual])) / actual


def kendall_tau_for_unique_orders(left: Sequence[str], right: Sequence[str]) -> float:
    """Compute Kendall tau-a through inversion counting for two unique orders."""
    if len(left) != len(right) or set(left) != set(right):
        raise ValueError("orders must contain the same unique identifiers")
    n = len(left)
    if n < 2:
        return 1.0
    right_position = {player_id: index for index, player_id in enumerate(right)}
    sequence = [right_position[player_id] for player_id in left]
    tree = [0] * (n + 1)

    def prefix(index: int) -> int:
        total = 0
        while index > 0:
            total += tree[index]
            index -= index & -index
        return total

    inversions = 0
    for seen, value in enumerate(sequence):
        index = value + 1
        inversions += seen - prefix(index)
        while index <= n:
            tree[index] += 1
            index += index & -index
    pairs = n * (n - 1) / 2
    return float(1.0 - 2.0 * inversions / pairs)


def classify_rank_stability(top100_probability: float, interval_width: int) -> str:
    """Describe ranking sensitivity, never player quality."""
    if top100_probability >= 0.90 and interval_width <= 25:
        return "HIGH"
    if top100_probability >= 0.50 or interval_width <= 75:
        return "MODERATE"
    return "LOW"
