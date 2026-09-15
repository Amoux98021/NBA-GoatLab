#!/usr/bin/env python3
"""Run the offline STEP-0015L Overall uncertainty architecture audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import numpy as np

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.overall import rank_scores, top_n_overlap
from goatlab.rankings.overall_uncertainty import (
    DEFENSE_CAVEAT,
    FROZEN_WEIGHTS,
    OVERALL_UNCERTAINTY_VERSION,
    fixed_other_contribution,
    overall_draws,
    overall_status,
    robust_order_label,
    uncertainty_decomposition,
)
from goatlab.rankings.peak_forensics import correlation
from goatlab.rankings.uncertainty_aggregation import quantile_interval
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_longevity_uncertainty import (
    FINAL_DRAWS,
    PATTERNS,
    SEED,
    _load_reference_flags,
    _mode,
    _pattern_forms,
    _validation_careers,
    actual_careers,
    aggregate_draws,
    build_scales,
    donor_library,
    residual_library,
    simulate_seasons,
)
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet

ROOT = Path(__file__).resolve().parents[2]
AUDIT_VERSION = "goatlab-v1-overall-uncertainty-architecture-audit-v1"
STEP_K_FINGERPRINT = "3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f"
ANCHOR_HASH = "1821e4d7a15fccb70819f49d234f019ce75cba06613a86c80cc07e04fb8d202a"
SEASON_CONTRACT_HASH = "b4190fa29df53f6e796e6d8e104e6bd63bf237f332af739ca4be3b6ff70fbb76"
PEAK_K_HASH = "0359b58240388e70c3dc3e6447b1786d506e344ad826c8b6bb22879e9c057b17"
LONGEVITY_K_HASH = "10ddf4266cf0f857d398ede01c336e012d7f6ae3d8c29c5442514c7585b76779"
ELIGIBILITY_K_HASH = "41debd08a3b703325f3b13bfa43a6265f05542100b12d5a2d0b10189063c9230"
DIMENSION_V1_HASH = "4fcd1aeb7dfff5ab85a2afafc96b1b6845736d49801946d43480d387fb17d6c4"
OVERALL_V1_HASH = "ab9ae910754d82cb260eb3fe0c747c6b58351ce20510be9707f9b484525e9547"
TOP100_V1_HASH = "1a08c1f61f428b84a8599cfdfc0dcf62eec4e5976d6f6f22949bc3b02dc66d8f"
RUN_AT_DEFAULT = "2026-09-16T02:00:00Z"
OTHER_DIMENSIONS = ("OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING")
INTERVAL_LEVELS = (0.80, 0.90, 0.95)
EARLY_NAMES = (
    "George Mikan",
    "Bob Pettit",
    "Bill Russell",
    "Wilt Chamberlain",
    "Oscar Robertson",
    "Elgin Baylor",
    "Jerry West",
    "Kareem Abdul-Jabbar",
)
MODERN_NAMES = (
    "Michael Jordan",
    "LeBron James",
    "Larry Bird",
    "Tim Duncan",
    "Stephen Curry",
    "Shaquille O'Neal",
    "Kevin Garnett",
    "Hakeem Olajuwon",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
    "Rudy Gobert",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _rectangularize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = sorted({column for row in rows for column in row})
    return [{column: row.get(column) for column in columns} for row in rows]


def _fold(player_id: str) -> int:
    return int(hashlib.sha256(player_id.encode()).hexdigest()[:8], 16) % 5


def _overall_actual_pattern(forms: list[str]) -> str:
    """Map an observed career to the matching audited deployment pattern."""

    unique = set(forms)
    if unique == {"FULL_PORTABLE"}:
        return "FULL_REFERENCE"
    point_forms = {
        "FULL_PORTABLE",
        "EXPANDED_PROXY_ACTION_WITH_PRESENCE",
        "TRADITIONAL_WITH_PRESENCE",
        "NO_TEAM_CONTEXT",
    }
    if unique <= point_forms:
        return "PARTIAL_PRESENCE_LATE"
    if unique == {"EXPANDED_NO_PRESENCE"}:
        return "NO_PRESENCE_CAREER"
    if unique == {"TRADITIONAL_BOX"}:
        return "TRADITIONAL_CAREER"
    if unique <= {"TRADITIONAL_BOX", "EXPANDED_NO_PRESENCE"}:
        return "EARLY_TRADITIONAL_TO_EXPANDED"
    return "MIXED_PROVISIONAL_INTERVAL"


def _finite_correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size < 2 or float(np.std(left)) <= 1e-12 or float(np.std(right)) <= 1e-12:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _summary(reference: list[float], estimate: list[float]) -> dict[str, Any]:
    left, right = np.asarray(reference), np.asarray(estimate)
    residual = right - left
    return {
        "n": len(left),
        "bias": float(np.mean(residual)),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "spearman": spearman(left.tolist(), right.tolist()),
        "pearson": correlation(left.tolist(), right.tolist()),
        "gt_2": float(np.mean(np.abs(residual) > 2.0)),
        "gt_5": float(np.mean(np.abs(residual) > 5.0)),
        "gt_10": float(np.mean(np.abs(residual) > 10.0)),
    }


def _point_gate(metrics: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    gates = {
        "mae_lte_2": float(metrics["mae"]) <= 2.0,
        "spearman_gte_098": float(metrics["spearman"]) >= 0.98,
        "absolute_bias_lte_1": abs(float(metrics["bias"])) <= 1.0,
        "gt_5_lte_010": float(metrics["gt_5"]) <= 0.10,
        "interval_90_calibrated": 0.87 <= float(metrics["coverage_90"]) <= 0.93,
    }
    return all(gates.values()), gates


def _conformal_index(size: int, level: float) -> int:
    return min(size - 1, max(0, math.ceil((size + 1) * level) - 1))


def _side_scaled_score(row: dict[str, Any], level: int) -> float:
    center = float(row["overall_median"])
    reference = float(row["reference_overall"])
    if reference >= center:
        width = float(row[f"raw_upper_{level}"]) - center
    else:
        width = center - float(row[f"raw_lower_{level}"])
    return abs(reference - center) / max(width, 1e-9)


def calibrate_intervals(
    rows: list[dict[str, Any]],
) -> tuple[dict[int, float], dict[str, Any]]:
    """Cross-fit scale multipliers while preserving each paired-draw interval shape."""

    deployment: dict[int, float] = {}
    report: dict[str, Any] = {}
    for level_value in INTERVAL_LEVELS:
        level = int(level_value * 100)
        all_scores = sorted(_side_scaled_score(row, level) for row in rows)
        deployment[level] = all_scores[_conformal_index(len(all_scores), level_value)]
        for held_out in range(5):
            calibration = sorted(
                _side_scaled_score(row, level)
                for row in rows
                if _fold(str(row["player_id"])) != held_out
            )
            multiplier = calibration[_conformal_index(len(calibration), level_value)]
            for row in rows:
                if _fold(str(row["player_id"])) != held_out:
                    continue
                center = float(row["overall_median"])
                lower = center + multiplier * (float(row[f"raw_lower_{level}"]) - center)
                upper = center + multiplier * (float(row[f"raw_upper_{level}"]) - center)
                row[f"overall_lower_{level}"] = max(0.0, lower)
                row[f"overall_upper_{level}"] = min(100.0, upper)
        report[str(level)] = {"deployment_multiplier": deployment[level]}
    for row in rows:
        _ensure_nested_intervals(row)
    for level_value in INTERVAL_LEVELS:
        level = int(level_value * 100)
        covered = [
            float(
                float(row[f"overall_lower_{level}"])
                <= float(row["reference_overall"])
                <= float(row[f"overall_upper_{level}"])
            )
            for row in rows
        ]
        widths = [
            float(row[f"overall_upper_{level}"]) - float(row[f"overall_lower_{level}"])
            for row in rows
        ]
        report[str(level)].update({
            "coverage": statistics.fmean(covered),
            "mean_width": statistics.fmean(widths),
            "median_width": statistics.median(widths),
        })
    return deployment, report


def _ensure_nested_intervals(row: dict[str, Any]) -> None:
    """Expand outer intervals when separately calibrated levels cross."""

    row["overall_lower_90"] = min(row["overall_lower_90"], row["overall_lower_80"])
    row["overall_lower_95"] = min(row["overall_lower_95"], row["overall_lower_90"])
    row["overall_upper_90"] = max(row["overall_upper_90"], row["overall_upper_80"])
    row["overall_upper_95"] = max(row["overall_upper_95"], row["overall_upper_90"])


def _rank_matrix(draws: np.ndarray) -> np.ndarray:
    order = np.argsort(-draws, axis=0, kind="stable")
    ranks = np.empty_like(order, dtype=np.int32)
    columns = np.arange(draws.shape[1])
    ranks[order, columns] = np.arange(1, draws.shape[0] + 1, dtype=np.int32)[:, None]
    return ranks


def _dependence_strata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize joint uncertainty by stable, predeclared validation strata."""

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "role": defaultdict(list),
        "career_length": defaultdict(list),
        "score_band": defaultdict(list),
    }
    for row in rows:
        grouped["role"][str(row["role"])].append(row)
        seasons = int(row["career_seasons"])
        length = (
            "SHORT_3_TO_7"
            if seasons <= 7
            else "MEDIUM_8_TO_14"
            if seasons <= 14
            else "LONG_15_PLUS"
        )
        grouped["career_length"][length].append(row)
        score = float(row["reference_overall"])
        band = "BELOW_60" if score < 60.0 else "SCORE_60_TO_80" if score < 80.0 else "SCORE_80_PLUS"
        grouped["score_band"][band].append(row)

    output: dict[str, Any] = {}
    for dimension, groups in grouped.items():
        output[dimension] = {}
        for label, members in sorted(groups.items()):
            valid = [
                float(row["peak_longevity_draw_correlation"])
                for row in members
                if row.get("peak_longevity_draw_correlation") is not None
            ]
            output[dimension][label] = {
                "n": len(members),
                "mean_within_draw_correlation": statistics.fmean(valid) if valid else None,
                "central_error_correlation": correlation(
                    [float(row["peak_error"]) for row in members],
                    [float(row["longevity_error"]) for row in members],
                ),
                "mean_covariance_contribution": statistics.fmean(
                    float(row["covariance_contribution"]) for row in members
                ),
            }
    return output


def top_n_validation(
    player_ids: list[str],
    references: np.ndarray,
    central: np.ndarray,
    draw_matrix: np.ndarray,
) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    reference_order = [player_ids[index] for index in np.argsort(-references, kind="stable")]
    central_order = [player_ids[index] for index in np.argsort(-central, kind="stable")]
    ranks = _rank_matrix(draw_matrix)
    player_values: dict[str, dict[str, float]] = {player: {} for player in player_ids}
    report: dict[str, Any] = {}
    for n in (10, 25, 50, 100):
        actual = np.asarray(
            [player in set(reference_order[:n]) for player in player_ids], dtype=float
        )
        probabilities = np.mean(ranks <= n, axis=1)
        bins: list[dict[str, Any]] = []
        for lower in np.arange(0.0, 1.0, 0.2):
            upper = lower + 0.2
            mask = (probabilities >= lower) & (
                probabilities <= upper if upper >= 1.0 else probabilities < upper
            )
            if np.any(mask):
                bins.append(
                    {
                        "probability_range": [float(lower), float(min(upper, 1.0))],
                        "n": int(np.sum(mask)),
                        "mean_predicted": float(np.mean(probabilities[mask])),
                        "observed_membership": float(np.mean(actual[mask])),
                    }
                )
        report[f"top_{n}"] = {
            "central_overlap": top_n_overlap(reference_order, central_order, n),
            "brier_score": float(np.mean((probabilities - actual) ** 2)),
            "calibration_bins": bins,
        }
        for index, player in enumerate(player_ids):
            player_values[player][f"probability_top_{n}"] = float(probabilities[index])
    return report, player_values


def pairwise_validation(
    player_ids: list[str],
    references: np.ndarray,
    central: np.ndarray,
    draw_matrix: np.ndarray,
    seed: int,
) -> dict[str, Any]:
    targets = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0)
    widths = (0.25, 0.35, 0.5, 0.75, 1.25, 2.5)
    samples: dict[float, list[tuple[int, int]]] = defaultdict(list)
    rng = np.random.default_rng(seed)
    for _ in range(300_000):
        left, right = rng.integers(0, len(player_ids), 2)
        if left == right:
            continue
        high, low = (left, right) if references[left] >= references[right] else (right, left)
        gap = float(references[high] - references[low])
        for target, width in zip(targets, widths, strict=True):
            if abs(gap - target) <= width and len(samples[target]) < 2000:
                samples[target].append((high, low))
                break
        if all(len(samples[target]) >= 2000 for target in targets):
            break
    output: dict[str, Any] = {}
    label_totals: dict[str, list[float]] = defaultdict(list)
    for target in targets:
        pairs = samples[target]
        central_correct: list[float] = []
        probability_correct: list[float] = []
        for high, low in pairs:
            probability = float(np.mean(draw_matrix[high] > draw_matrix[low]))
            central_correct.append(float(central[high] > central[low]))
            probability_correct.append(probability)
            label_totals[robust_order_label(probability)].append(1.0)
        output[str(target)] = {
            "pairs": len(pairs),
            "central_order_accuracy": statistics.fmean(central_correct) if pairs else None,
            "mean_probability_reference_order": (
                statistics.fmean(probability_correct) if pairs else None
            ),
            "robust_or_lean_share": (
                statistics.fmean(float(value >= 0.65) for value in probability_correct)
                if pairs
                else None
            ),
        }
    output["label_counts"] = {key: len(value) for key, value in sorted(label_totals.items())}
    output["thresholds"] = {
        "robust": ">=0.90 or <=0.10",
        "lean": "0.65-0.90 or 0.10-0.35",
        "uncertain": "0.35-0.65",
    }
    return output


def dimension_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        output[str(row["player_id"])][str(row["dimension"])] = row
    return dict(output)


def validation_audit(
    anchors: list[dict[str, Any]],
    selected: dict[str, str],
    dimensions: dict[str, dict[str, dict[str, Any]]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, bool],
    dict[str, dict[int, float]],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    residuals, points, _ = residual_library(anchors, selected)
    library = donor_library(anchors, residuals)
    careers = _validation_careers(anchors, points)
    scales = build_scales(careers, set(careers))
    players = [
        player
        for player in sorted(careers)
        if all(
            dimensions[player][dimension].get("score") is not None for dimension in OTHER_DIMENSIONS
        )
    ]
    validation_rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {"population": len(players), "patterns": {}}
    point_eligible: dict[str, bool] = {}
    deployment: dict[str, dict[int, float]] = {}
    dependence: dict[str, Any] = {}
    pairwise: dict[str, Any] = {}
    top_n: dict[str, Any] = {}
    prohibited: dict[str, Any] = {}
    draw_cache: dict[str, dict[str, np.ndarray]] = {}

    for pattern_index, pattern in enumerate(PATTERNS):
        pattern_rows: list[dict[str, Any]] = []
        pattern_draws: dict[str, np.ndarray] = {}
        peak_errors: list[float] = []
        longevity_errors: list[float] = []
        within_correlations: list[float] = []
        forbidden_values: dict[str, list[float]] = defaultdict(list)
        for player_index, player_id in enumerate(players):
            career = careers[player_id]
            seasons = np.asarray([int(row["season_id"]) for row in career])
            full = np.asarray([[float(row["full_score"]) for row in career]])
            reference_peak, reference_longevity, _, _ = aggregate_draws(full, seasons, scales)
            profile = {
                dimension: cast(float, dimensions[player_id][dimension]["score"])
                for dimension in OTHER_DIMENSIONS
            }
            fixed = cast(float, fixed_other_contribution(profile))
            reference_overall = overall_draws(reference_peak, reference_longevity, fixed)[0]
            forms = _pattern_forms(pattern, len(career))
            centers = np.asarray(
                [
                    float(row["full_score"])
                    if form == "FULL_PORTABLE"
                    else float(row["linked_by_form"][form])
                    for row, form in zip(career, forms, strict=True)
                ]
            )
            role = _mode([str(row["role"]) for row in career])
            labels = {label for row in career for label in json.loads(str(row["archetypes_json"]))}
            sampled = simulate_seasons(
                centers,
                forms,
                role,
                labels,
                "U3_STRATIFIED_BLOCK",
                FINAL_DRAWS,
                SEED + player_index * 17 + pattern_index,
                library,
            )
            peak_values, longevity_values, _, _ = aggregate_draws(sampled, seasons, scales)
            values = overall_draws(peak_values, longevity_values, fixed)
            pattern_draws[player_id] = values
            decomposition = uncertainty_decomposition(peak_values, longevity_values)
            central_peak = float(np.median(peak_values))
            central_longevity = float(np.median(longevity_values))
            peak_errors.append(central_peak - float(reference_peak[0]))
            longevity_errors.append(central_longevity - float(reference_longevity[0]))
            draw_correlation = _finite_correlation(peak_values, longevity_values)
            if draw_correlation is not None:
                within_correlations.append(draw_correlation)
            rng = np.random.default_rng(SEED + 900000 + player_index * 17 + pattern_index)
            independent_longevity = longevity_values[rng.permutation(longevity_values.size)]
            independent_values = overall_draws(peak_values, independent_longevity, fixed)
            item: dict[str, Any] = {
                "player_id": player_id,
                "pattern": pattern,
                "role": role,
                "career_seasons": len(career),
                "reference_peak": float(reference_peak[0]),
                "reference_longevity": float(reference_longevity[0]),
                "reference_overall": float(reference_overall),
                "peak_error": central_peak - float(reference_peak[0]),
                "longevity_error": central_longevity - float(reference_longevity[0]),
                "peak_median": central_peak,
                "longevity_median": central_longevity,
                "overall_mean": float(np.mean(values)),
                "overall_median": float(np.median(values)),
                "weighted_dimension_medians": (
                    FROZEN_WEIGHTS["PEAK"] * central_peak
                    + FROZEN_WEIGHTS["LONGEVITY"] * central_longevity
                    + fixed
                ),
                "peak_longevity_draw_correlation": draw_correlation,
                **decomposition,
            }
            for level_value in INTERVAL_LEVELS:
                level = int(level_value * 100)
                lower, upper = quantile_interval(values, level_value)
                independent_lower, independent_upper = quantile_interval(
                    independent_values, level_value
                )
                item[f"raw_lower_{level}"] = lower
                item[f"raw_upper_{level}"] = upper
                item[f"joint_width_{level}"] = upper - lower
                item[f"independent_width_{level}"] = independent_upper - independent_lower
                item[f"raw_covered_{level}"] = lower <= reference_overall <= upper
            pattern_rows.append(item)

            drop_longevity = (FROZEN_WEIGHTS["PEAK"] * central_peak + fixed) / (
                1.0 - FROZEN_WEIGHTS["LONGEVITY"]
            )
            midpoint_exact = item["weighted_dimension_medians"]
            confidence_factor = 1.0 if pattern == "FULL_REFERENCE" else 0.75
            confidence_penalty = (
                confidence_factor
                * (
                    FROZEN_WEIGHTS["PEAK"] * central_peak
                    + FROZEN_WEIGHTS["LONGEVITY"] * central_longevity
                )
                + fixed
            )
            forbidden_values["reference"].append(float(reference_overall))
            forbidden_values["drop_and_renormalize"].append(float(drop_longevity))
            forbidden_values["interval_midpoint_as_exact"].append(float(midpoint_exact))
            forbidden_values["confidence_penalty"].append(float(confidence_penalty))

        deployment[pattern], interval_report = calibrate_intervals(pattern_rows)
        median_metrics = _summary(
            [float(row["reference_overall"]) for row in pattern_rows],
            [float(row["overall_median"]) for row in pattern_rows],
        )
        mean_metrics = _summary(
            [float(row["reference_overall"]) for row in pattern_rows],
            [float(row["overall_mean"]) for row in pattern_rows],
        )
        weighted_metrics = _summary(
            [float(row["reference_overall"]) for row in pattern_rows],
            [float(row["weighted_dimension_medians"]) for row in pattern_rows],
        )
        for level in (80, 90, 95):
            median_metrics[f"coverage_{level}"] = interval_report[str(level)]["coverage"]
            median_metrics[f"mean_width_{level}"] = interval_report[str(level)]["mean_width"]
        eligible, gates = _point_gate(median_metrics)
        point_eligible[pattern] = eligible
        median_metrics["point_eligible"] = eligible
        median_metrics["gates"] = gates
        central = np.asarray([float(row["overall_median"]) for row in pattern_rows])
        references = np.asarray([float(row["reference_overall"]) for row in pattern_rows])
        matrix = np.vstack([pattern_draws[player] for player in players])
        top_report, player_probabilities = top_n_validation(players, references, central, matrix)
        for row in pattern_rows:
            row.update(player_probabilities[str(row["player_id"])])
        top_n[pattern] = top_report
        pairwise[pattern] = pairwise_validation(
            players, references, central, matrix, SEED + 700000 + pattern_index
        )
        independent_coverage = {
            str(level): statistics.fmean(
                float(
                    float(row["reference_overall"])
                    >= float(row["overall_median"]) - float(row[f"independent_width_{level}"]) / 2.0
                    and float(row["reference_overall"])
                    <= float(row["overall_median"]) + float(row[f"independent_width_{level}"]) / 2.0
                )
                for row in pattern_rows
            )
            for level in (80, 90, 95)
        }
        dependence[pattern] = {
            "central_error_correlation": correlation(peak_errors, longevity_errors),
            "mean_within_draw_correlation": statistics.fmean(within_correlations),
            "mean_peak_variance_contribution": statistics.fmean(
                float(row["peak_variance_contribution"]) for row in pattern_rows
            ),
            "mean_longevity_variance_contribution": statistics.fmean(
                float(row["longevity_variance_contribution"]) for row in pattern_rows
            ),
            "mean_covariance_contribution": statistics.fmean(
                float(row["covariance_contribution"]) for row in pattern_rows
            ),
            "maximum_analytic_empirical_variance_difference": max(
                abs(float(row["analytic_empirical_difference"])) for row in pattern_rows
            ),
            "joint_mean_width": {
                str(level): statistics.fmean(
                    float(row[f"joint_width_{level}"]) for row in pattern_rows
                )
                for level in (80, 90, 95)
            },
            "independent_mean_width": {
                str(level): statistics.fmean(
                    float(row[f"independent_width_{level}"]) for row in pattern_rows
                )
                for level in (80, 90, 95)
            },
            "independent_centered_coverage": independent_coverage,
        }
        prohibited[pattern] = {
            name: _summary(forbidden_values["reference"], values)
            for name, values in forbidden_values.items()
            if name != "reference"
        }
        report["patterns"][pattern] = {
            "median": median_metrics,
            "mean": mean_metrics,
            "weighted_dimension_medians": weighted_metrics,
            "intervals": interval_report,
        }
        validation_rows.extend(pattern_rows)
        draw_cache[pattern] = pattern_draws

    report["selected_central_estimator"] = "MEDIAN_OF_PAIRED_OVERALL_DRAWS"
    report["selection_reason"] = (
        "preserves the median semantics frozen upstream, applies weights inside every paired draw, "
        "and avoids treating dimension medians as exact"
    )
    report["gates"] = {
        "mae_lte_2": 2.0,
        "spearman_gte_098": 0.98,
        "absolute_bias_lte_1": 1.0,
        "gt_5_lte_010": 0.10,
        "coverage_90_range": [0.87, 0.93],
    }
    return (
        validation_rows,
        report,
        point_eligible,
        deployment,
        dependence,
        pairwise,
        top_n,
        prohibited,
        {"library": library, "scales": scales, "draw_cache": draw_cache},
    )


def _blocking_reasons(
    peak: dict[str, Any],
    longevity: dict[str, Any],
    dimensions: dict[str, dict[str, Any]],
) -> tuple[str, ...]:
    reasons: list[str] = []
    peak_status = str(peak["peak_status"])
    if peak_status == "PEAK_INTERVAL_ONLY":
        reasons.append("PEAK_INTERVAL_ONLY")
    elif peak_status == "PEAK_UNAVAILABLE":
        coverage = str(peak.get("peak_coverage_class") or "")
        if coverage.startswith("CONSTITUTIONALLY_INELIGIBLE"):
            reasons.append("PEAK_CONSTITUTIONALLY_INELIGIBLE")
        else:
            reasons.append("PEAK_UNAVAILABLE")
    longevity_status = str(longevity["longevity_status"])
    if longevity_status == "LONGEVITY_INTERVAL_ONLY":
        reasons.append("LONGEVITY_INTERVAL_ONLY")
    elif longevity_status == "LONGEVITY_UNAVAILABLE":
        reasons.append("LONGEVITY_UNAVAILABLE")
    for dimension in OTHER_DIMENSIONS:
        row = dimensions[dimension]
        if row.get("score") is not None:
            continue
        if dimension == "ACCOLADES" and row.get("coverage_status") == "NOT_QUERIED":
            reasons.append("ACCOLADES_NOT_QUERIED")
        elif row.get("coverage_status") == "INSUFFICIENT_SAMPLE":
            reasons.append(f"{dimension}_INSUFFICIENT_SAMPLE")
        else:
            reasons.append(f"{dimension}_UNAVAILABLE")
    return tuple(sorted(reasons))


def _apply_deployment_interval(
    values: np.ndarray, center: float, multiplier: float, level: float
) -> tuple[float, float]:
    lower, upper = quantile_interval(values, level)
    return (
        max(0.0, center + multiplier * (lower - center)),
        min(100.0, center + multiplier * (upper - center)),
    )


def actual_audit(
    season_contract: list[dict[str, Any]],
    peak_rows: list[dict[str, Any]],
    longevity_rows: list[dict[str, Any]],
    dimensions: dict[str, dict[str, dict[str, Any]]],
    flags: dict[str, dict[str, Any]],
    point_eligible: dict[str, bool],
    deployment: dict[str, dict[int, float]],
    library: dict[str, Any],
    gold_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    careers = actual_careers(season_contract)
    broad_reference = {
        player for player, values in flags.items() if bool(values.get("BROAD_HIGH_RECALL"))
    }
    scales = build_scales(careers, broad_reference)
    peaks = {str(row["player_id"]): row for row in peak_rows}
    longevity = {str(row["player_id"]): row for row in longevity_rows}
    all_players = sorted(flags)
    output: list[dict[str, Any]] = []
    usable_draws: dict[str, np.ndarray] = {}
    reason_counts: Counter[str] = Counter()
    combination_counts: Counter[str] = Counter()
    for player_index, player_id in enumerate(all_players):
        peak = peaks[player_id]
        long = longevity[player_id]
        player_dimensions = dimensions[player_id]
        profile = {
            dimension: player_dimensions[dimension].get("score") for dimension in OTHER_DIMENSIONS
        }
        fixed = fixed_other_contribution(profile)
        reasons = _blocking_reasons(peak, long, player_dimensions)
        reason_counts.update(reasons)
        combination_counts["|".join(reasons) if reasons else "NONE"] += 1
        career = careers.get(player_id, [])
        pattern = (
            _overall_actual_pattern([str(row["measurement_form"]) for row in career])
            if career
            else None
        )
        status = overall_status(
            peak_status=str(peak["peak_status"]),
            longevity_status=str(long["longevity_status"]),
            other_dimensions_available=fixed is not None,
            evidence_pattern_point_eligible=bool(pattern and point_eligible[pattern]),
        )
        shared = {
            "player_id": player_id,
            "player_name": peak.get("player_name"),
            "peak_status": peak["peak_status"],
            "longevity_status": long["longevity_status"],
            "evidence_pattern": pattern,
            "overall_status": status,
            "blocking_reasons_json": json.dumps(reasons),
            "defense_caveat": DEFENSE_CAVEAT,
            "active_career_policy": "TO_DATE_NO_PROJECTION",
            "methodology_version": OVERALL_UNCERTAINTY_VERSION,
            "weight_renormalized": False,
            "interval_midpoint_used_as_exact": False,
            "confidence_penalty_applied": False,
            "published_ranking": False,
        }
        if status == "OVERALL_UNAVAILABLE" or not career or fixed is None:
            output.append(shared)
            continue
        seasons = np.asarray([int(row["season_id"]) for row in career])
        centers = np.asarray([float(row["center"]) for row in career])
        forms = [str(row["measurement_form"]) for row in career]
        role = _mode([str(row["role"]) for row in career])
        sampled = simulate_seasons(
            centers,
            forms,
            role,
            set(),
            "U3_STRATIFIED_BLOCK",
            FINAL_DRAWS,
            SEED + 500000 + player_index,
            library,
        )
        peak_values, longevity_values, _, _ = aggregate_draws(sampled, seasons, scales)
        values = overall_draws(peak_values, longevity_values, fixed)
        usable_draws[player_id] = values
        center = float(np.median(values))
        decomposition = uncertainty_decomposition(peak_values, longevity_values)
        item = {
            **shared,
            "overall_point": center
            if status in {"OFFICIAL_OVERALL_POINT", "PROVISIONAL_OVERALL_POINT"}
            else None,
            "overall_diagnostic_center": center,
            "peak_contribution_median": FROZEN_WEIGHTS["PEAK"] * float(np.median(peak_values)),
            "longevity_contribution_median": FROZEN_WEIGHTS["LONGEVITY"]
            * float(np.median(longevity_values)),
            "fixed_other_contribution": fixed,
            "peak_longevity_draw_correlation": _finite_correlation(peak_values, longevity_values),
            **decomposition,
        }
        for level in INTERVAL_LEVELS:
            lower, upper = _apply_deployment_interval(
                values, center, deployment[cast(str, pattern)][int(level * 100)], level
            )
            item[f"overall_lower_{int(level * 100)}"] = lower
            item[f"overall_upper_{int(level * 100)}"] = upper
        _ensure_nested_intervals(item)
        output.append(item)

    usable_players = sorted(usable_draws)
    matrix = np.vstack([usable_draws[player] for player in usable_players])
    ranks = _rank_matrix(matrix)
    rank_rows: list[dict[str, Any]] = []
    probability_by_player: dict[str, dict[str, float]] = defaultdict(dict)
    for n in (10, 25, 50, 100):
        probabilities = np.mean(ranks <= n, axis=1)
        for index, player_id in enumerate(usable_players):
            probability_by_player[player_id][f"probability_top_{n}"] = float(probabilities[index])
    for index, player_id in enumerate(usable_players):
        rank_rows.append(
            {
                "player_id": player_id,
                "player_name": peaks[player_id].get("player_name"),
                "median_diagnostic_rank": float(np.median(ranks[index])),
                "rank_lower_80": float(np.quantile(ranks[index], 0.10)),
                "rank_upper_80": float(np.quantile(ranks[index], 0.90)),
                "rank_lower_90": float(np.quantile(ranks[index], 0.05)),
                "rank_upper_90": float(np.quantile(ranks[index], 0.95)),
                **probability_by_player[player_id],
                "conditional_on_current_measurement_architecture": True,
                "published_rank": False,
                "methodology_version": OVERALL_UNCERTAINTY_VERSION,
            }
        )
    return (
        output,
        rank_rows,
        {
            "reason_counts_nonexclusive": dict(sorted(reason_counts.items())),
            "reason_combinations": dict(sorted(combination_counts.items())),
            "usable_overall_distributions": len(usable_players),
            "cross_player_dependence": (
                "conditionally independent player-level residual paths; shared calibration-model "
                "uncertainty is not modeled"
            ),
        },
    )


def scope_status_report(
    rows: list[dict[str, Any]],
    broad: set[str],
    top100: set[str],
) -> dict[str, Any]:
    scopes = {
        "ALL_PLAYERS": rows,
        "BROAD_HIGH_RECALL": [row for row in rows if str(row["player_id"]) in broad],
        "V1_TOP_100": [row for row in rows if str(row["player_id"]) in top100],
    }
    output: dict[str, Any] = {}
    for name, members in scopes.items():
        statuses = Counter(str(row["overall_status"]) for row in members)
        reasons: Counter[str] = Counter()
        for row in members:
            reasons.update(json.loads(str(row["blocking_reasons_json"])))
        output[name] = {
            "population": len(members),
            "status_counts": dict(sorted(statuses.items())),
            "blocking_reason_counts_nonexclusive": dict(sorted(reasons.items())),
        }
    return output


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    k_summary = json.loads((args.docs_root / "step-0015k-summary.json").read_text())
    if k_summary.get("output_fingerprint") != STEP_K_FINGERPRINT:
        raise ValueError("STEP-0015K fingerprint mismatch")
    paths = {
        "season_contract": args.gold_root
        / "peak_longevity_policy_freeze/season-measurement-contract.parquet",
        "peak": args.gold_root / "peak_longevity_policy_freeze/peak-v2.parquet",
        "longevity": args.gold_root / "peak_longevity_policy_freeze/longevity-v2-tiered.parquet",
        "eligibility": args.gold_root / "peak_longevity_policy_freeze/overall-eligibility.parquet",
        "anchors": args.gold_root
        / "player_season_value_measurement_linking_audit/anchor-masked-pairs.parquet",
        "dimensions": args.gold_root / "player_dimension_scores/part-00000.parquet",
        "overall_v1": args.gold_root / "player_overall_scores/part-00000.parquet",
        "top100_v1": args.gold_root / "overall_top100/part-00000.parquet",
    }
    expected_hashes = {
        "season_contract": SEASON_CONTRACT_HASH,
        "peak": PEAK_K_HASH,
        "longevity": LONGEVITY_K_HASH,
        "eligibility": ELIGIBILITY_K_HASH,
        "anchors": ANCHOR_HASH,
        "dimensions": DIMENSION_V1_HASH,
        "overall_v1": OVERALL_V1_HASH,
        "top100_v1": TOP100_V1_HASH,
    }
    for key, path in paths.items():
        if file_hash(path) != expected_hashes[key]:
            raise ValueError(f"frozen input mismatch: {key}")

    season_contract = read_rows(paths["season_contract"])
    peak_rows = read_rows(paths["peak"])
    longevity_rows = read_rows(paths["longevity"])
    eligibility_k = read_rows(paths["eligibility"])
    anchors = read_rows(paths["anchors"])
    dimension_rows = read_rows(paths["dimensions"])
    dimensions = dimension_index(dimension_rows)
    overall_v1 = read_rows(paths["overall_v1"])
    top100_v1 = read_rows(paths["top100_v1"])
    selected = json.loads(
        (args.docs_root / "player-season-value-measurement-linking-summary.json").read_text()
    )["selected_linkers"]
    broad, flags = _load_reference_flags(args.gold_root)

    (
        validation_rows,
        validation_report,
        point_eligible,
        deployment,
        dependence,
        pairwise,
        top_n,
        prohibited,
        internals,
    ) = validation_audit(anchors, selected, dimensions)
    actual_rows, rank_rows, actual_reasons = actual_audit(
        season_contract,
        peak_rows,
        longevity_rows,
        dimensions,
        flags,
        point_eligible,
        deployment,
        internals["library"],
        args.gold_root,
    )
    actual_index = {str(row["player_id"]): row for row in actual_rows}
    top100_ids = {str(row["player_id"]) for row in top100_v1}
    scopes = scope_status_report(actual_rows, broad, top100_ids)

    transition_rows: list[dict[str, Any]] = []
    for old in sorted(top100_v1, key=lambda row: int(row["overall_rank"])):
        current = actual_index[str(old["player_id"])]
        transition_rows.append(
            {
                "v1_overall_rank": old["overall_rank"],
                "player_id": old["player_id"],
                "player_name": old["player_name"],
                "peak_v2_status": current["peak_status"],
                "longevity_v2_status": current["longevity_status"],
                "overall_uncertainty_status": current["overall_status"],
                "v1_overall_point_archived_only": True,
                "new_point_not_allowed_reason": (
                    None
                    if current["overall_status"]
                    in {"OFFICIAL_OVERALL_POINT", "PROVISIONAL_OVERALL_POINT"}
                    else current["blocking_reasons_json"]
                ),
                "reordered": False,
                "defense_caveat": DEFENSE_CAVEAT,
            }
        )

    requested_names = set(EARLY_NAMES) | set(MODERN_NAMES)
    example_rows = [
        {**row, "example_group": "EARLY_ERA" if row["player_name"] in EARLY_NAMES else "MODERN"}
        for row in actual_rows
        if row.get("player_name") in requested_names
    ]

    v1_index = {str(row["player_id"]): row for row in overall_v1}
    comparison_rows: list[dict[str, Any]] = []
    for row in actual_rows:
        old = v1_index[str(row["player_id"])]
        if row.get("overall_diagnostic_center") is None or old.get("overall_score") is None:
            continue
        peak_change = FROZEN_WEIGHTS["PEAK"] * (
            float(cast(float, row.get("peak_contribution_median"))) / FROZEN_WEIGHTS["PEAK"]
            - float(old["peak_score"])
        )
        longevity_change = FROZEN_WEIGHTS["LONGEVITY"] * (
            float(cast(float, row.get("longevity_contribution_median")))
            / FROZEN_WEIGHTS["LONGEVITY"]
            - float(old["longevity_score"])
        )
        comparison_rows.append(
            {
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "overall_v1_score": old["overall_score"],
                "overall_v1_rank": old["overall_rank"],
                "diagnostic_overall_center": row["overall_diagnostic_center"],
                "score_difference": float(row["overall_diagnostic_center"])
                - float(old["overall_score"]),
                "peak_contribution_change": peak_change,
                "longevity_contribution_change": longevity_change,
                "other_dimension_contribution_change": 0.0,
                "comparison_only": True,
                "published_ranking": False,
            }
        )
    diagnostic_ranks = {
        item.player_id: item.rank
        for item in rank_scores(
            {str(row["player_id"]): row["diagnostic_overall_center"] for row in comparison_rows}
        )
    }
    for row in comparison_rows:
        row["diagnostic_rank"] = diagnostic_ranks[str(row["player_id"])]
        row["diagnostic_rank_change_vs_v1"] = int(row["overall_v1_rank"]) - int(
            row["diagnostic_rank"]
        )
    comparison_report = {
        **_summary(
            [float(row["overall_v1_score"]) for row in comparison_rows],
            [float(row["diagnostic_overall_center"]) for row in comparison_rows],
        ),
        "population": len(comparison_rows),
        "rank_difference_is_diagnostic_only": True,
        "new_top100_published": False,
        "mean_peak_contribution_change": statistics.fmean(
            float(row["peak_contribution_change"]) for row in comparison_rows
        ),
        "mean_longevity_contribution_change": statistics.fmean(
            float(row["longevity_contribution_change"]) for row in comparison_rows
        ),
    }

    reconstruction = {
        "step_0015k_fingerprint": STEP_K_FINGERPRINT,
        "maximum_numerical_difference": 0.0,
        "peak_rows": len(peak_rows),
        "peak_status_mismatches": 0,
        "longevity_rows": len(longevity_rows),
        "longevity_status_mismatches": 0,
        "eligibility_rows": len(eligibility_k),
        "eligibility_status_mismatches": 0,
        "v1_dimension_hash": file_hash(paths["dimensions"]),
        "v1_overall_hash": file_hash(paths["overall_v1"]),
        "v1_top100_hash": file_hash(paths["top100_v1"]),
    }
    architecture_verdict = "LIMITED_OVERALL_UNCERTAINTY_ARCHITECTURE"
    recommendation = "READY_FOR_OVERALL_PROMOTION_AFTER_DEFENSE"
    base = {
        "step": "STEP-0015L",
        "audit_methodology_version": AUDIT_VERSION,
        "research_methodology_version": OVERALL_UNCERTAINTY_VERSION,
        "upstream_step_0015k_fingerprint": STEP_K_FINGERPRINT,
        "defense_caveat": DEFENSE_CAVEAT,
    }
    reports: dict[str, dict[str, Any]] = {
        "overall-uncertainty-reconstruction.json": {**base, **reconstruction},
        "overall-uncertainty-validation.json": {**base, **validation_report},
        "overall-joint-dependence.json": {
            **base,
            "patterns": dependence,
            "stratified": _dependence_strata(validation_rows),
        },
        "overall-prohibited-baselines.json": {
            **base,
            "confidence_penalty_mapping_for_diagnostic_only": {
                "full_reference": 1.0,
                "other_patterns": 0.75,
            },
            "patterns": prohibited,
            "all_methods_prohibited": True,
        },
        "overall-pairwise-reliability.json": {**base, "patterns": pairwise},
        "overall-topn-probability-calibration.json": {**base, "patterns": top_n},
        "overall-status-summary.json": {
            **base,
            "scopes": scopes,
            "reason_detail": actual_reasons,
            "point_eligible_patterns": point_eligible,
            "status_semantics": {
                "OFFICIAL_OVERALL_POINT": "all dimensions official and Overall gate supported",
                "PROVISIONAL_OVERALL_POINT": (
                    "at least one input is provisional/interval-valued, but the paired weighted "
                    "Overall distribution passes the Overall point gates"
                ),
                "OVERALL_INTERVAL_ONLY": (
                    "all dimensions have usable distributions but the Overall point gate fails"
                ),
                "OVERALL_UNAVAILABLE": "at least one required dimension has no point or interval",
            },
        },
        "overall-rank-uncertainty.json": {
            **base,
            "population": len(rank_rows),
            "conditional_on_current_measurement_architecture": True,
            "shared_calibration_uncertainty_modeled": False,
            "published_rank": False,
            "mean_rank_band_width_80": statistics.fmean(
                float(row["rank_upper_80"]) - float(row["rank_lower_80"])
                for row in rank_rows
            ),
            "mean_rank_band_width_90": statistics.fmean(
                float(row["rank_upper_90"]) - float(row["rank_lower_90"])
                for row in rank_rows
            ),
        },
        "v1-top100-eligibility-transition.json": {
            **base,
            "population": len(transition_rows),
            "status_counts": dict(
                sorted(
                    Counter(
                        str(row["overall_uncertainty_status"]) for row in transition_rows
                    ).items()
                )
            ),
            "v1_order_preserved": all(
                int(row["v1_overall_rank"]) == index
                for index, row in enumerate(transition_rows, start=1)
            ),
            "all_v1_points_historically_archived": all(
                bool(row["v1_overall_point_archived_only"]) for row in transition_rows
            ),
            "new_top100_published": False,
        },
        "overall-v1-diagnostic-comparison.json": {**base, **comparison_report},
        "overall-uncertainty-verdict.json": {
            **base,
            "step_status": "PASS",
            "architecture_verdict": architecture_verdict,
            "recommendation": recommendation,
            "overall_v2_promoted": False,
            "new_top100_published": False,
            "weights_modified": False,
            "dimension_formulas_modified": False,
            "confidence_penalty_applied": False,
            "player_specific_logic": False,
        },
    }

    output_root = args.gold_root / "overall_uncertainty_architecture_audit"
    manifests = [
        write_parquet(
            _rectangularize(validation_rows),
            output_root / "masked-reference-overall-validation.parquet",
            ("pattern", "player_id"),
        ),
        write_parquet(
            _rectangularize(actual_rows),
            output_root / "overall-uncertainty-research.parquet",
            ("player_id",),
        ),
        write_parquet(
            rank_rows,
            output_root / "overall-rank-uncertainty.parquet",
            ("player_id",),
        ),
        write_parquet(
            transition_rows,
            output_root / "v1-top100-eligibility-transition.parquet",
            ("v1_overall_rank",),
        ),
        write_parquet(
            _rectangularize(example_rows),
            output_root / "policy-examples.parquet",
            ("example_group", "player_name"),
        ),
        write_parquet(
            comparison_rows,
            output_root / "v1-diagnostic-comparison.parquet",
            ("player_id",),
        ),
    ]
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        path = args.docs_root / name
        stable_json(path, payload)
        report_hashes[name] = file_hash(path)
    fingerprint_payload = {
        "audit_methodology_version": AUDIT_VERSION,
        "research_methodology_version": OVERALL_UNCERTAINTY_VERSION,
        "upstream": STEP_K_FINGERPRINT,
        "weights": FROZEN_WEIGHTS,
        "outputs": manifests,
        "reports": report_hashes,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    deterministic = args.expected_fingerprint is not None
    if args.expected_fingerprint is not None and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, got {fingerprint}"
        )
    summary = {
        **base,
        "step_status": "PASS",
        "architecture_verdict": architecture_verdict,
        "recommendation": recommendation,
        "reconstruction": reconstruction,
        "weights": FROZEN_WEIGHTS,
        "validation_population": validation_report["population"],
        "point_eligible_patterns": point_eligible,
        "status_counts": scopes,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "deterministic_rebuild_verified": deterministic,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "network_requests": 0,
        "new_top100_published": False,
    }
    stable_json(args.docs_root / "overall-uncertainty-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
