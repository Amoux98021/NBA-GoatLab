"""Deterministic primitives for the STEP-0015E historical bridge audit."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.defense_promotion import RidgeModel, fit_ridge, predict_ridge

HISTORICAL_BRIDGE_AUDIT_VERSION = "goatlab-v1-historical-evidence-bridge-audit-v1"
HISTORICAL_BRIDGE_RESEARCH_VERSION = "goatlab-v1-player-season-value-bridge-research-v1"
BRIDGE_RANDOM_SEED = 15001505


@dataclass(frozen=True)
class LatentMeasurement:
    """One-factor measurement parameters fit to already era-relative channels."""

    means: tuple[float, ...]
    scales: tuple[float, ...]
    loadings: tuple[float, ...]
    explained_variance_ratio: float


@dataclass(frozen=True)
class PredictionInterval:
    central: float
    lower: float
    upper: float
    confidence: float


def deterministic_fold(key: str, *, folds: int = 5, salt: str = "player") -> int:
    if folds < 2:
        raise ValueError("folds must be at least two")
    digest = hashlib.sha256(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % folds


def polynomial_features(values: Sequence[float]) -> tuple[float, ...]:
    """Return an interpretable linear/quadratic feature set with no identity signal."""
    numbers = tuple(float(value) for value in values)
    if not numbers or not all(math.isfinite(value) for value in numbers):
        raise ValueError("finite features required")
    output = list(numbers)
    output.extend(value * value for value in numbers)
    for left in range(len(numbers)):
        for right in range(left + 1, len(numbers)):
            output.append(numbers[left] * numbers[right])
    return tuple(output)


def grouped_oof_ridge(
    features: npt.NDArray[np.float64],
    target: npt.NDArray[np.float64],
    groups: Sequence[str],
    *,
    alpha: float = 1.0,
    folds: int = 5,
    salt: str = "player",
) -> npt.NDArray[np.float64]:
    """Generate deterministic out-of-fold predictions with whole groups held out."""
    if features.ndim != 2 or target.ndim != 1 or len(features) != len(target):
        raise ValueError("invalid grouped ridge shapes")
    if len(groups) != len(target) or len(target) == 0:
        raise ValueError("one non-empty group per row is required")
    assignments = np.asarray(
        [deterministic_fold(str(group), folds=folds, salt=salt) for group in groups], dtype=int
    )
    predictions = np.empty(len(target), dtype=np.float64)
    for fold in range(folds):
        train = assignments != fold
        test = assignments == fold
        if not np.any(train) or not np.any(test):
            raise ValueError("every deterministic fold must have train and test rows")
        model = fit_ridge(features[train], target[train], alpha=alpha)
        predictions[test] = predict_ridge(model, features[test])
    return predictions


def era_block_predictions(
    features: npt.NDArray[np.float64],
    target: npt.NDArray[np.float64],
    seasons: Sequence[int],
    *,
    alpha: float = 1.0,
    width: int = 10,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Leave an entire season block out when fitting each prediction."""
    if len(features) != len(target) or len(seasons) != len(target):
        raise ValueError("era-block inputs must align")
    blocks = np.asarray([int(season) // width for season in seasons], dtype=int)
    predictions = np.full(len(target), np.nan, dtype=np.float64)
    eligible = np.zeros(len(target), dtype=bool)
    for block in sorted(set(blocks.tolist())):
        train = blocks != block
        test = blocks == block
        if np.sum(train) < features.shape[1] + 2 or not np.any(test):
            continue
        model = fit_ridge(features[train], target[train], alpha=alpha)
        predictions[test] = predict_ridge(model, features[test])
        eligible[test] = True
    return predictions, eligible


def regression_metrics(
    actual: Sequence[float], predicted: Sequence[float], *, scale: float = 100.0
) -> dict[str, float | int | None]:
    if len(actual) != len(predicted) or not actual:
        return {"observations": 0}
    left = np.asarray(actual, dtype=float)
    right = np.asarray(predicted, dtype=float)
    errors = (right - left) * scale
    centered = left - np.mean(left)
    denominator = float(np.sum(centered**2))
    slope, intercept = np.linalg.lstsq(
        np.column_stack([left, np.ones(len(left))]), right, rcond=None
    )[0]
    return {
        "observations": len(left),
        "r_squared": (
            1.0 - float(np.sum((right - left) ** 2)) / denominator if denominator > 0 else 0.0
        ),
        "spearman": spearman(left.tolist(), right.tolist()),
        "pearson": float(np.corrcoef(left, right)[0, 1]),
        "mean_signed_error": float(np.mean(errors)),
        "mean_absolute_error": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "calibration_slope": float(slope),
        "calibration_intercept": float(intercept * scale),
        "p10_error": float(np.quantile(errors, 0.10)),
        "p50_error": float(np.quantile(errors, 0.50)),
        "p90_error": float(np.quantile(errors, 0.90)),
        "more_than_5_points": float(np.mean(np.abs(errors) > 5.0)),
        "more_than_10_points": float(np.mean(np.abs(errors) > 10.0)),
        "more_than_15_points": float(np.mean(np.abs(errors) > 15.0)),
    }


def fit_latent_measurement(values: npt.NDArray[np.float64]) -> LatentMeasurement:
    """Fit an interpretable one-factor PCA measurement model."""
    if values.ndim != 2 or len(values) < 2 or values.shape[1] < 2:
        raise ValueError("latent measurement requires a non-empty matrix with two channels")
    means = np.mean(values, axis=0)
    scales = np.std(values, axis=0)
    scales = np.where(scales > 1e-12, scales, 1.0)
    standardized = (values - means) / scales
    covariance = np.cov(standardized, rowvar=False, ddof=0)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    vector = eigenvectors[:, order[0]]
    if float(np.sum(vector)) < 0.0:
        vector = -vector
    return LatentMeasurement(
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        loadings=tuple(float(value) for value in vector),
        explained_variance_ratio=float(eigenvalues[order[0]] / np.sum(eigenvalues)),
    )


def latent_scores(
    model: LatentMeasurement,
    values: npt.NDArray[np.float64],
    observed: npt.NDArray[np.bool_] | None = None,
) -> npt.NDArray[np.float64]:
    """Estimate factor scores from observed channels without filling missing values with zero."""
    if values.ndim != 2 or values.shape[1] != len(model.loadings):
        raise ValueError("latent score shape mismatch")
    mask = np.isfinite(values) if observed is None else observed & np.isfinite(values)
    means = np.asarray(model.means)
    scales = np.asarray(model.scales)
    loadings = np.asarray(model.loadings)
    standardized = np.where(mask, (values - means) / scales, 0.0)
    numerator = np.sum(standardized * loadings * mask, axis=1)
    denominator = np.sum((loadings**2) * mask, axis=1)
    output = np.full(len(values), np.nan, dtype=np.float64)
    valid = denominator > 1e-12
    output[valid] = numerator[valid] / denominator[valid]
    return output


def clipped_interval(central: float, radius: float, *, confidence: float) -> PredictionInterval:
    if not 0.0 < confidence < 1.0 or radius < 0.0:
        raise ValueError("invalid interval parameters")
    if not math.isfinite(central):
        raise ValueError("finite central estimate required")
    return PredictionInterval(
        central=min(1.0, max(0.0, central)),
        lower=min(1.0, max(0.0, central - radius)),
        upper=min(1.0, max(0.0, central + radius)),
        confidence=confidence,
    )


def interval_metrics(
    actual: Sequence[float], intervals: Sequence[PredictionInterval]
) -> dict[str, float | int]:
    if len(actual) != len(intervals) or not actual:
        return {"observations": 0}
    coverage = [
        item.lower <= value <= item.upper for value, item in zip(actual, intervals, strict=True)
    ]
    widths = [(item.upper - item.lower) * 100.0 for item in intervals]
    return {
        "observations": len(actual),
        "nominal_coverage": intervals[0].confidence,
        "empirical_coverage": sum(coverage) / len(coverage),
        "mean_width_points": float(np.mean(widths)),
        "median_width_points": float(np.median(widths)),
        "p90_width_points": float(np.quantile(widths, 0.90)),
    }


def practical_gate(metrics: dict[str, float | int]) -> dict[str, bool]:
    """Apply the predeclared STEP-0015E point-bridge research gates."""
    if int(metrics.get("observations", 0)) == 0:
        return {
            "mae_at_most_5": False,
            "spearman_at_least_0_95": False,
            "absolute_bias_at_most_2": False,
            "over_10_at_most_15_pct": False,
            "passes": False,
        }
    gates = {
        "mae_at_most_5": float(metrics["mean_absolute_error"]) <= 5.0,
        "spearman_at_least_0_95": float(metrics["spearman"]) >= 0.95,
        "absolute_bias_at_most_2": abs(float(metrics["mean_signed_error"])) <= 2.0,
        "over_10_at_most_15_pct": float(metrics["more_than_10_points"]) <= 0.15,
    }
    gates["passes"] = all(gates.values())
    return gates


def fit_full_ridge(
    features: npt.NDArray[np.float64], target: npt.NDArray[np.float64], *, alpha: float = 1.0
) -> RidgeModel:
    """Named wrapper used by the audit after all validation predictions are frozen."""
    return fit_ridge(features, target, alpha=alpha)
