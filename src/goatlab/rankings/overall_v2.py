"""Deterministic uncertainty coupling primitives for GOATLab Overall V2."""

from __future__ import annotations

import math
from functools import lru_cache
from statistics import NormalDist
from typing import cast

import numpy as np

OVERALL_V2_VERSION = "goatlab-v1-overall-v2-tiered"
OVERALL_V2_AUDIT_VERSION = "goatlab-v1-overall-v2-promotion-audit-v1"

FROZEN_OVERALL_WEIGHTS = {
    "PEAK": 0.17,
    "LONGEVITY": 0.14,
    "OFFENSE": 0.16,
    "DEFENSE": 0.14,
    "PLAYOFFS": 0.18,
    "ACCOLADES": 0.10,
    "WINNING": 0.11,
}


def nearest_psd_correlation(matrix: np.ndarray) -> tuple[np.ndarray, dict[str, float | bool]]:
    """Return a symmetric PSD correlation matrix and an explicit correction report."""

    value = np.asarray(matrix, dtype=float)
    if value.shape != (3, 3):
        raise ValueError("Overall V2 correlation matrices must be 3x3")
    symmetric = (value + value.T) / 2.0
    np.fill_diagonal(symmetric, 1.0)
    before = np.linalg.eigvalsh(symmetric)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    clipped = np.maximum(eigenvalues, 1e-8)
    corrected = eigenvectors @ np.diag(clipped) @ eigenvectors.T
    scale = np.sqrt(np.diag(corrected))
    corrected = corrected / np.outer(scale, scale)
    corrected = (corrected + corrected.T) / 2.0
    np.fill_diagonal(corrected, 1.0)
    after = np.linalg.eigvalsh(corrected)
    return corrected, {
        "corrected": bool(float(np.min(before)) < -1e-10),
        "minimum_eigenvalue_before": float(np.min(before)),
        "minimum_eigenvalue_after": float(np.min(after)),
        "maximum_absolute_change": float(np.max(np.abs(corrected - symmetric))),
    }


@lru_cache(maxsize=8)
def _normal_quantiles(size: int) -> np.ndarray:
    normal = NormalDist()
    return np.asarray([normal.inv_cdf((index + 0.5) / size) for index in range(size)])


def _normal_scores(values: np.ndarray) -> np.ndarray:
    order = np.argsort(np.argsort(values, kind="stable"), kind="stable")
    return cast(np.ndarray, _normal_quantiles(values.size)[order])


def couple_defense_ranks(
    peak_draws: np.ndarray,
    longevity_draws: np.ndarray,
    defense_marginal: np.ndarray,
    target_correlation: np.ndarray,
    *,
    seed: int,
) -> tuple[np.ndarray, dict[str, float | bool]]:
    """Align Defense ranks while preserving exact P/L draws and Defense marginal values."""

    peak = np.asarray(peak_draws, dtype=float)
    longevity = np.asarray(longevity_draws, dtype=float)
    defense = np.asarray(defense_marginal, dtype=float)
    if not (peak.ndim == longevity.ndim == defense.ndim == 1):
        raise ValueError("draw arrays must be one-dimensional")
    if not (peak.size == longevity.size == defense.size and peak.size >= 10):
        raise ValueError("draw arrays must have the same non-trivial length")
    target, report = nearest_psd_correlation(target_correlation)
    z_peak = _normal_scores(peak)
    z_longevity = _normal_scores(longevity)
    predictors = np.column_stack([z_peak, z_longevity])
    predictor_correlation = np.corrcoef(predictors, rowvar=False)
    desired = np.asarray([target[0, 2], target[1, 2]])
    beta = np.linalg.pinv(predictor_correlation) @ desired
    explained = float(desired @ beta)
    if explained >= 0.995:
        scale = math.sqrt(0.995 / max(explained, 1e-12))
        desired *= scale
        beta = np.linalg.pinv(predictor_correlation) @ desired
        explained = float(desired @ beta)
        report["conditional_target_shrunk"] = True
    else:
        report["conditional_target_shrunk"] = False
    rng = np.random.default_rng(seed)
    latent = predictors @ beta + math.sqrt(max(1.0 - explained, 1e-8)) * rng.normal(size=peak.size)
    order = np.argsort(latent, kind="stable")
    coupled = np.empty_like(defense)
    coupled[order] = np.sort(defense)
    report.update(
        {
            "target_defense_peak": float(target[0, 2]),
            "target_defense_longevity": float(target[1, 2]),
            "reproduced_defense_peak": float(
                np.corrcoef(_normal_scores(peak), _normal_scores(coupled))[0, 1]
            ),
            "reproduced_defense_longevity": float(
                np.corrcoef(_normal_scores(longevity), _normal_scores(coupled))[0, 1]
            ),
        }
    )
    return coupled, report


def independent_defense_ranks(defense_marginal: np.ndarray, *, seed: int) -> np.ndarray:
    """Return the diagnostic independent-Defense baseline with the marginal unchanged."""

    rng = np.random.default_rng(seed)
    return cast(
        np.ndarray,
        np.asarray(defense_marginal, dtype=float)[rng.permutation(len(defense_marginal))],
    )


def overall_draws_v2(
    peak: np.ndarray,
    longevity: np.ndarray,
    defense: np.ndarray,
    fixed_without_defense: float,
) -> np.ndarray:
    """Apply frozen weights without renormalization or confidence penalties."""

    return cast(
        np.ndarray,
        FROZEN_OVERALL_WEIGHTS["PEAK"] * np.asarray(peak)
        + FROZEN_OVERALL_WEIGHTS["LONGEVITY"] * np.asarray(longevity)
        + FROZEN_OVERALL_WEIGHTS["DEFENSE"] * np.asarray(defense)
        + fixed_without_defense,
    )


def variance_decomposition(
    peak: np.ndarray, longevity: np.ndarray, defense: np.ndarray
) -> dict[str, float]:
    """Return the exact weighted variance/covariance expansion for uncertain dimensions."""

    matrix = np.vstack([peak, longevity, defense])
    covariance = np.cov(matrix, ddof=0)
    weights = np.asarray([0.17, 0.14, 0.14])
    components = {
        "peak_variance": float(weights[0] ** 2 * covariance[0, 0]),
        "longevity_variance": float(weights[1] ** 2 * covariance[1, 1]),
        "defense_variance": float(weights[2] ** 2 * covariance[2, 2]),
        "peak_longevity_covariance": float(2 * weights[0] * weights[1] * covariance[0, 1]),
        "peak_defense_covariance": float(2 * weights[0] * weights[2] * covariance[0, 2]),
        "longevity_defense_covariance": float(2 * weights[1] * weights[2] * covariance[1, 2]),
    }
    components["analytic_total"] = sum(components.values())
    combined = weights @ matrix
    components["empirical_total"] = float(np.var(combined))
    components["analytic_empirical_difference"] = (
        components["analytic_total"] - components["empirical_total"]
    )
    return components
