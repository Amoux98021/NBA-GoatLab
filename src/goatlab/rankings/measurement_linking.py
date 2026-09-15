"""Deterministic score linking and uncertainty helpers for STEP-0015H.

The functions in this module calibrate *measurement-form scores*.  They never
predict a missing basketball statistic.  A fitted linker maps a score emitted
by a weaker factual evidence form onto the frozen FULL_PORTABLE Candidate-D
reference scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from typing import Literal, cast

import numpy as np

LinkMethod = Literal["identity", "linear", "quantile", "isotonic", "role_isotonic"]


@dataclass(frozen=True)
class LinkModel:
    """A monotone one-dimensional score linker."""

    method: LinkMethod
    x: tuple[float, ...]
    y: tuple[float, ...]
    role_models: tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...] = ()


def _collapse_x(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    ys = y[order]
    unique, starts, counts = np.unique(xs, return_index=True, return_counts=True)
    means = np.add.reduceat(ys, starts) / counts
    return unique.astype(float), means.astype(float), counts.astype(float)


def _pava(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit weighted isotonic means and return interpolation knots."""

    unique_x, means, weights = _collapse_x(x, y)
    block_y: list[float] = []
    block_w: list[float] = []
    block_xw: list[float] = []
    for xv, yv, weight in zip(unique_x, means, weights, strict=True):
        block_y.append(float(yv))
        block_w.append(float(weight))
        block_xw.append(float(xv * weight))
        while len(block_y) >= 2 and block_y[-2] > block_y[-1]:
            new_w = block_w[-2] + block_w[-1]
            new_y = (block_y[-2] * block_w[-2] + block_y[-1] * block_w[-1]) / new_w
            new_xw = block_xw[-2] + block_xw[-1]
            block_y[-2:] = [new_y]
            block_w[-2:] = [new_w]
            block_xw[-2:] = [new_xw]
    knots_x = np.asarray([xw / weight for xw, weight in zip(block_xw, block_w, strict=True)])
    knots_y = np.asarray(block_y)
    return knots_x, knots_y


def fit_linker(
    method: LinkMethod,
    raw_score: np.ndarray,
    reference_score: np.ndarray,
    roles: np.ndarray | None = None,
) -> LinkModel:
    """Fit one of the predeclared monotone linking candidates."""

    x = np.asarray(raw_score, dtype=float)
    y = np.asarray(reference_score, dtype=float)
    if x.size == 0 or x.size != y.size:
        raise ValueError("linker inputs must be non-empty and equally sized")
    if method == "identity":
        return LinkModel(method=method, x=(0.0, 100.0), y=(0.0, 100.0))
    if method == "linear":
        variance = float(np.var(x))
        slope = 0.0 if variance == 0.0 else max(0.0, float(np.cov(x, y, ddof=0)[0, 1] / variance))
        intercept = float(np.mean(y) - slope * np.mean(x))
        return LinkModel(method=method, x=(0.0, 100.0), y=(intercept, intercept + 100.0 * slope))
    if method == "quantile":
        grid = np.linspace(0.0, 1.0, 101)
        qx = np.quantile(x, grid)
        qy = np.maximum.accumulate(np.quantile(y, grid))
        knots_x, knots_y, _ = _collapse_x(qx, qy)
        return LinkModel(method=method, x=tuple(knots_x), y=tuple(knots_y))
    if method == "isotonic":
        knots_x, knots_y = _pava(x, y)
        return LinkModel(method=method, x=tuple(knots_x), y=tuple(knots_y))
    if method != "role_isotonic" or roles is None:
        raise ValueError("role_isotonic requires role labels")
    global_x, global_y = _pava(x, y)
    role_models: list[tuple[str, tuple[float, ...], tuple[float, ...]]] = []
    role_array = np.asarray(roles, dtype=str)
    for role in sorted(set(role_array.tolist())):
        mask = role_array == role
        if int(np.sum(mask)) < 100:
            continue
        role_x, role_y = _pava(x[mask], y[mask])
        role_models.append((role, tuple(role_x), tuple(role_y)))
    return LinkModel(
        method=method,
        x=tuple(global_x),
        y=tuple(global_y),
        role_models=tuple(role_models),
    )


def predict_linker(
    model: LinkModel,
    raw_score: np.ndarray,
    roles: np.ndarray | None = None,
) -> np.ndarray:
    """Apply a fitted linker, clipping only at the common score boundaries."""

    x = np.asarray(raw_score, dtype=float)
    base_x = np.asarray(model.x, dtype=float)
    base_y = np.asarray(model.y, dtype=float)
    predicted = np.interp(x, base_x, base_y, left=base_y[0], right=base_y[-1])
    if model.method == "role_isotonic" and roles is not None:
        role_array = np.asarray(roles, dtype=str)
        for role, role_x, role_y in model.role_models:
            mask = role_array == role
            if np.any(mask):
                predicted[mask] = np.interp(
                    x[mask],
                    np.asarray(role_x),
                    np.asarray(role_y),
                    left=role_y[0],
                    right=role_y[-1],
                )
    return cast(np.ndarray, np.clip(predicted, 0.0, 100.0))


def deterministic_fold(value: str, *, folds: int = 5, seed: int = 1515) -> int:
    """Return a stable fold assignment independent of Python hash randomization."""

    digest = sha256(f"{seed}|{value}".encode()).hexdigest()
    return int(digest[:16], 16) % folds


def cross_fitted_predictions(
    method: LinkMethod,
    raw_score: np.ndarray,
    reference_score: np.ndarray,
    fold_ids: np.ndarray,
    roles: np.ndarray | None = None,
) -> np.ndarray:
    """Produce out-of-fold predictions for arbitrary deterministic folds."""

    x = np.asarray(raw_score, dtype=float)
    y = np.asarray(reference_score, dtype=float)
    folds = np.asarray(fold_ids)
    role_array = None if roles is None else np.asarray(roles, dtype=str)
    result = np.full(x.shape, np.nan, dtype=float)
    for fold in sorted(set(folds.tolist())):
        test = folds == fold
        train = ~test
        if int(np.sum(train)) < 50 or int(np.sum(test)) == 0:
            continue
        model = fit_linker(
            method,
            x[train],
            y[train],
            None if role_array is None else role_array[train],
        )
        result[test] = predict_linker(
            model,
            x[test],
            None if role_array is None else role_array[test],
        )
    return result


def regression_metrics(reference: np.ndarray, estimate: np.ndarray) -> dict[str, float | int]:
    """Return the common STEP-0015H calibration metrics."""

    y = np.asarray(reference, dtype=float)
    p = np.asarray(estimate, dtype=float)
    valid = np.isfinite(y) & np.isfinite(p)
    y = y[valid]
    p = p[valid]
    if y.size < 2:
        return {"n": int(y.size)}
    residual = p - y
    pearson = float(np.corrcoef(y, p)[0, 1])
    yrank = _midranks(y)
    prank = _midranks(p)
    spearman = float(np.corrcoef(yrank, prank)[0, 1])
    slope = 0.0 if float(np.var(p)) == 0.0 else float(np.cov(p, y, ddof=0)[0, 1] / np.var(p))
    intercept = float(np.mean(y) - slope * np.mean(p))
    return {
        "n": int(y.size),
        "bias": float(np.mean(residual)),
        "median_bias": float(np.median(residual)),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "pearson": pearson,
        "spearman": spearman,
        "calibration_slope": slope,
        "calibration_intercept": intercept,
        "gt_5": float(np.mean(np.abs(residual) > 5.0)),
        "gt_10": float(np.mean(np.abs(residual) > 10.0)),
        "gt_15": float(np.mean(np.abs(residual) > 15.0)),
    }


def _midranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    sorted_values = values[order]
    start = 0
    while start < values.size:
        end = start + 1
        while end < values.size and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def conformal_radius(absolute_residuals: np.ndarray, level: float) -> float:
    """Finite-sample split-conformal absolute-residual radius."""

    residuals = np.sort(np.asarray(absolute_residuals, dtype=float))
    residuals = residuals[np.isfinite(residuals)]
    if residuals.size == 0:
        raise ValueError("at least one finite calibration residual is required")
    index = min(residuals.size - 1, max(0, ceil((residuals.size + 1) * level) - 1))
    return float(residuals[index])


def interval_bounds(point: float, radii: dict[int, float]) -> dict[str, float]:
    """Create clipped, nested 80/90/95 percent interval bounds."""

    ordered = {level: max(float(radii[level]), 0.0) for level in (80, 90, 95)}
    ordered[90] = max(ordered[90], ordered[80])
    ordered[95] = max(ordered[95], ordered[90])
    result: dict[str, float] = {}
    for level in (80, 90, 95):
        result[f"lower_{level}"] = max(0.0, point - ordered[level])
        result[f"upper_{level}"] = min(100.0, point + ordered[level])
    return result
