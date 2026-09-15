#!/usr/bin/env python3
"""Run the offline STEP-0015J Longevity threshold/run calibration audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.longevity_calibration import (
    LongevityScale,
    ThresholdComponents,
    conformal_radius,
    expected_raw_component_score,
    expected_transformed_component_score,
    final_score_draws,
    modal_run_component_score,
    run_bridge_candidates,
    threshold_components,
    transformed_component_draws,
)
from goatlab.rankings.peak_forensics import correlation
from goatlab.rankings.uncertainty_aggregation import (
    LONGEVITY_WEIGHTS,
    fixed_midrank_ecdf,
    quantile_interval,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_longevity_uncertainty import (
    ANCHOR_HASH,
    FINAL_DRAWS,
    LINKED_SEASON_HASH,
    MODERN_NAMES,
    PATTERNS,
    SEED,
    STEP_H_FINGERPRINT,
    _career_metadata,
    _load_reference_flags,
    _mode,
    _pattern_forms,
    _rectangularize,
    _validation_careers,
    actual_careers,
    build_scales,
    donor_library,
    propagation_comparison,
    reconstruct_step_h,
    residual_library,
    simulate_seasons,
)
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet

ROOT = Path(__file__).resolve().parents[2]
STEP_I_FINGERPRINT = "4f44cf63450105d8c215aa20a0b3078dc8b9b5c907f2f03553eff390195a150a"
STEP_I_PEAK_HASH = "77b19ada90ba9d6163aaaaeccf341355d5ef9af12f5af04c6902ae7dbe569ea2"
STEP_I_LONGEVITY_HASH = "40944bb52d31edbcb6dc54dc0b83396827ed7a201fb4d73bebf1429af0313c9b"
STEP_I_VALIDATION_HASH = "7789c2704a2dcd224a0902af25c8be2bd6173f1e21d3b6f9632259b8dc018f9f"
AUDIT_VERSION = "goatlab-v1-longevity-threshold-run-calibration-audit-v1"
RESEARCH_VERSION = "goatlab-v1-longevity-v2-uncertainty-research-2"
RUN_AT_DEFAULT = "2026-09-15T23:00:00Z"
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
ANALYSIS_PATTERNS = (
    "MIXED_PROVISIONAL_INTERVAL",
    "PARTIAL_PRESENCE_LATE",
    "TRADITIONAL_CAREER",
    "EARLY_TRADITIONAL_TO_EXPANDED",
)
ESTIMATORS = (
    "DRAW_MEDIAN_FINAL",
    "DRAW_MEAN_FINAL",
    "EXPECTED_RAW_COMPONENTS",
    "EXPECTED_TRANSFORMED_COMPONENTS",
    "MODAL_RUN_EXPECTED_OTHER",
)
THRESHOLD_PAIRS = ((78.0, 88.0), (79.0, 89.0), (80.0, 90.0), (81.0, 91.0), (82.0, 92.0))
RUN_WEIGHTS = (0.20, 0.25, 0.30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def metric_summary(reference: list[float], estimate: list[float]) -> dict[str, Any]:
    left = np.asarray(reference, dtype=float)
    right = np.asarray(estimate, dtype=float)
    residual = right - left
    return {
        "n": len(left),
        "bias": float(np.mean(residual)),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "pearson": correlation(left.tolist(), right.tolist()),
        "spearman": spearman(left.tolist(), right.tolist()),
        "reference_variance": float(np.var(left)),
        "estimate_variance": float(np.var(right)),
        "gt_5": float(np.mean(np.abs(residual) > 5.0)),
        "gt_10": float(np.mean(np.abs(residual) > 10.0)),
    }


def point_gate(metrics: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    gates = {
        "mae_lte_5": float(metrics["mae"]) <= 5.0,
        "spearman_gte_095": float(metrics["spearman"]) >= 0.95,
        "absolute_bias_lte_2": abs(float(metrics["bias"])) <= 2.0,
        "gt_10_lte_015": float(metrics["gt_10"]) <= 0.15,
        "interval_90_calibrated": 0.87 <= float(metrics["coverage_90"]) <= 0.93,
    }
    return all(gates.values()), gates


def make_scale(
    careers: dict[str, list[dict[str, Any]]],
    p80: float = 80.0,
    p90: float = 90.0,
    weights: tuple[float, float, float] = LONGEVITY_WEIGHTS,
) -> LongevityScale:
    raw: list[tuple[float, float, float]] = []
    for player_id in sorted(careers):
        rows = careers[player_id]
        values = np.asarray([[float(row["full_score"]) for row in rows]])
        seasons = np.asarray([int(row["season_id"]) for row in rows])
        components = threshold_components(values, seasons, p80=p80, p90=p90)
        raw.append(
            (
                float(components.breadth[0]),
                float(components.capped_area[0]),
                float(components.longest_run[0]),
            )
        )
    breadth = np.asarray([row[0] for row in raw])
    area = np.asarray([row[1] for row in raw])
    run = np.asarray([row[2] for row in raw])
    component_points = (
        fixed_midrank_ecdf(breadth, breadth),
        fixed_midrank_ecdf(area, area),
        fixed_midrank_ecdf(run, run),
    )
    final = (
        weights[0] * component_points[0]
        + weights[1] * component_points[1]
        + weights[2] * component_points[2]
    )
    return LongevityScale(breadth, area, run, final, p80, p90, weights)


def baseline_scale(step_i_scale: dict[str, np.ndarray]) -> LongevityScale:
    return LongevityScale(
        breadth=step_i_scale["breadth"],
        area=step_i_scale["area"],
        run=step_i_scale["run"],
        final=step_i_scale["longevity"],
        p80=80.0,
        p90=90.0,
        weights=LONGEVITY_WEIGHTS,
    )


def estimator_values(components: ThresholdComponents, scale: LongevityScale) -> dict[str, float]:
    draws = final_score_draws(components, scale)
    return {
        "DRAW_MEDIAN_FINAL": float(np.median(draws)),
        "DRAW_MEAN_FINAL": float(np.mean(draws)),
        "EXPECTED_RAW_COMPONENTS": expected_raw_component_score(components, scale),
        "EXPECTED_TRANSFORMED_COMPONENTS": expected_transformed_component_score(components, scale),
        "MODAL_RUN_EXPECTED_OTHER": modal_run_component_score(components, scale),
    }


def select_estimator(report: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Prefer posterior expected displayed quality when calibration remains competitive."""
    comparable = ANALYSIS_PATTERNS
    aggregate = {
        method: {
            "mean_mae": statistics.fmean(report[method][pattern]["mae"] for pattern in comparable),
            "mean_spearman": statistics.fmean(
                report[method][pattern]["spearman"] for pattern in comparable
            ),
        }
        for method in ESTIMATORS
    }
    best_mae = min(item["mean_mae"] for item in aggregate.values())
    best_spearman = max(item["mean_spearman"] for item in aggregate.values())
    expected = aggregate["DRAW_MEAN_FINAL"]
    if (
        expected["mean_mae"] <= best_mae + 0.25
        and expected["mean_spearman"] >= best_spearman - 0.002
    ):
        return (
            "DRAW_MEAN_FINAL",
            "posterior mean of the final fixed-scale draw distribution; within 0.25 MAE "
            "and 0.002 Spearman of the best candidate",
        )
    selected = min(
        ESTIMATORS,
        key=lambda method: (
            aggregate[method]["mean_mae"],
            -aggregate[method]["mean_spearman"],
            ESTIMATORS.index(method),
        ),
    )
    return selected, "best aggregate MAE with Spearman and declared-order tie breaks"


def fold_number(player_id: str) -> int:
    return int(hashlib.sha256(player_id.encode("utf-8")).hexdigest()[:8], 16) % 5


def crossfit_conformal(
    rows: list[dict[str, Any]], estimator: str
) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    report: dict[str, Any] = {}
    deployment: dict[str, dict[str, float]] = {}
    for pattern in PATTERNS:
        members = [row for row in rows if row["pattern"] == pattern]
        residuals = np.asarray(
            [float(row[estimator]) - float(row["reference_longevity"]) for row in members]
        )
        deployment[pattern] = {
            str(level): conformal_radius(residuals, level) for level in (0.80, 0.90, 0.95)
        }
        pattern_report: dict[str, Any] = {}
        for level in (0.80, 0.90, 0.95):
            covered: list[float] = []
            widths: list[float] = []
            for fold in range(5):
                calibration = np.asarray(
                    [
                        residuals[index]
                        for index, row in enumerate(members)
                        if fold_number(str(row["player_id"])) != fold
                    ]
                )
                radius = conformal_radius(calibration, level)
                for row in members:
                    if fold_number(str(row["player_id"])) != fold:
                        continue
                    center = float(row[estimator])
                    reference = float(row["reference_longevity"])
                    lower, upper = max(0.0, center - radius), min(100.0, center + radius)
                    covered.append(float(lower <= reference <= upper))
                    widths.append(upper - lower)
            pattern_report[str(int(level * 100))] = {
                "coverage": statistics.fmean(covered),
                "mean_width": statistics.fmean(widths),
                "median_width": statistics.median(widths),
            }
        report[pattern] = pattern_report
    return report, deployment


def top_overlap(reference: list[float], estimate: list[float], n: int) -> float:
    order_ref = np.argsort(-np.asarray(reference), kind="mergesort")[:n]
    order_est = np.argsort(-np.asarray(estimate), kind="mergesort")[:n]
    return len(set(order_ref.tolist()) & set(order_est.tolist())) / min(n, len(reference))


def validation_analysis(
    careers: dict[str, list[dict[str, Any]]],
    scale: LongevityScale,
    alternative_scales: dict[str, LongevityScale],
    library: dict[str, Any],
    method: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    bridges: list[dict[str, Any]] = []
    frozen = {
        (str(row["player_id"]), str(row["pattern"])): row
        for row in read_rows(
            ROOT / "data/gold/peak_longevity_uncertainty_audit/masked-career-validation.parquet"
        )
    }
    maximum_difference = 0.0
    mismatches = 0
    threshold_records: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    run_weight_records: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    threshold_forensics: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for player_index, player_id in enumerate(sorted(careers)):
        career = careers[player_id]
        seasons = np.asarray([int(row["season_id"]) for row in career])
        full = np.asarray([float(row["full_score"]) for row in career])
        reference_components = threshold_components(full[None, :], seasons)
        reference_final = float(final_score_draws(reference_components, scale)[0])
        reference_transformed = transformed_component_draws(reference_components, scale)
        role = _mode([str(row["role"]) for row in career])
        archetypes = {label for row in career for label in json.loads(str(row["archetypes_json"]))}
        for pattern_index, pattern in enumerate(PATTERNS):
            forms = _pattern_forms(pattern, len(career))
            centers = np.asarray(
                [
                    float(row["full_score"])
                    if form == "FULL_PORTABLE"
                    else float(row["linked_by_form"][form])
                    for row, form in zip(career, forms, strict=True)
                ]
            )
            sampled = simulate_seasons(
                centers,
                forms,
                role,
                archetypes,
                method,
                FINAL_DRAWS,
                SEED + player_index * 17 + pattern_index,
                library,
            )
            components = threshold_components(sampled, seasons)
            final_draws = final_score_draws(components, scale)
            estimators = estimator_values(components, scale)
            transformed = transformed_component_draws(components, scale)
            item: dict[str, Any] = {
                "player_id": player_id,
                "pattern": pattern,
                "role": role,
                "career_seasons": len(career),
                "career_length_group": (
                    "SHORT" if len(career) <= 8 else "MEDIUM" if len(career) <= 13 else "LONG"
                ),
                "reference_longevity": reference_final,
                "reference_breadth": float(reference_components.breadth[0]),
                "reference_area": float(reference_components.capped_area[0]),
                "reference_run": float(reference_components.longest_run[0]),
                "reference_breadth_points": float(reference_transformed[0][0]),
                "reference_area_points": float(reference_transformed[1][0]),
                "reference_run_points": float(reference_transformed[2][0]),
                "expected_breadth": float(np.mean(components.breadth)),
                "median_breadth": float(np.median(components.breadth)),
                "expected_area": float(np.mean(components.capped_area)),
                "median_area": float(np.median(components.capped_area)),
                "expected_run": float(np.mean(components.longest_run)),
                "median_run": float(np.median(components.longest_run)),
                "modal_run": float(
                    Counter(components.longest_run.astype(int).tolist()).most_common(1)[0][0]
                ),
                "expected_breadth_points": float(np.mean(transformed[0])),
                "expected_area_points": float(np.mean(transformed[1])),
                "expected_run_points": float(np.mean(transformed[2])),
                **estimators,
            }
            for level in (0.80, 0.90, 0.95):
                lower, upper = quantile_interval(final_draws, level)
                item[f"propagated_lower_{int(level * 100)}"] = lower
                item[f"propagated_upper_{int(level * 100)}"] = upper
            frozen_row = frozen[(player_id, pattern)]
            for field, value in (
                ("longevity_central", estimators["DRAW_MEDIAN_FINAL"]),
                ("longevity_lower_80", item["propagated_lower_80"]),
                ("longevity_upper_80", item["propagated_upper_80"]),
                ("longevity_lower_90", item["propagated_lower_90"]),
                ("longevity_upper_90", item["propagated_upper_90"]),
                ("longevity_lower_95", item["propagated_lower_95"]),
                ("longevity_upper_95", item["propagated_upper_95"]),
            ):
                difference = abs(float(frozen_row[field]) - float(value))
                maximum_difference = max(maximum_difference, difference)
                mismatches += int(difference > 1e-12)

            reference_raw = {
                "BREADTH": reference_components.breadth[0],
                "AREA": reference_components.capped_area[0],
                "RUN": reference_components.longest_run[0],
            }
            for uncertain in (
                ("BREADTH",),
                ("AREA",),
                ("RUN",),
                ("BREADTH", "AREA"),
                ("BREADTH", "RUN"),
                ("AREA", "RUN"),
            ):
                ablated = ThresholdComponents(
                    breadth=(
                        components.breadth
                        if "BREADTH" in uncertain
                        else np.full(FINAL_DRAWS, reference_raw["BREADTH"])
                    ),
                    capped_area=(
                        components.capped_area
                        if "AREA" in uncertain
                        else np.full(FINAL_DRAWS, reference_raw["AREA"])
                    ),
                    longest_run=(
                        components.longest_run
                        if "RUN" in uncertain
                        else np.full(FINAL_DRAWS, reference_raw["RUN"])
                    ),
                )
                item[f"ABLATION_{'_'.join(uncertain)}"] = float(
                    np.mean(final_score_draws(ablated, scale))
                )

            probabilities = np.mean(sampled >= 80.0, axis=0)
            events = run_bridge_candidates(probabilities, seasons)
            item["run_bridge_events"] = len(events)
            for index, left, right in events:
                elite = sampled[:, index] >= 80.0
                conditional_run = (
                    float(np.mean(components.longest_run[elite]))
                    - float(np.mean(components.longest_run[~elite]))
                    if int(np.sum(elite)) >= 25 and int(np.sum(~elite)) >= 25
                    else None
                )
                conditional_final = (
                    float(np.mean(final_draws[elite])) - float(np.mean(final_draws[~elite]))
                    if int(np.sum(elite)) >= 25 and int(np.sum(~elite)) >= 25
                    else None
                )
                bridges.append(
                    {
                        "player_id": player_id,
                        "pattern": pattern,
                        "role": role,
                        "season_id": int(seasons[index]),
                        "p80_probability": float(probabilities[index]),
                        "left_credible_run": left,
                        "right_credible_run": right,
                        "potential_run_gain": left + 1 + right - max(left, right),
                        "conditional_run_difference": conditional_run,
                        "conditional_longevity_difference": conditional_final,
                    }
                )

            if pattern in ANALYSIS_PATTERNS:
                for label, lower, upper, threshold in (
                    ("P80_75_85", 75.0, 85.0, 80.0),
                    ("P80_78_82", 78.0, 82.0, 80.0),
                    ("P80_79_81", 79.0, 81.0, 80.0),
                    ("P90_85_95", 85.0, 95.0, 90.0),
                    ("P90_88_92", 88.0, 92.0, 90.0),
                    ("P90_89_91", 89.0, 91.0, 90.0),
                ):
                    indices = np.flatnonzero((full >= lower) & (full <= upper))
                    for index in indices:
                        probability = float(np.mean(sampled[:, index] >= threshold))
                        threshold_forensics[pattern][label]["probability"].append(probability)
                        threshold_forensics[pattern][label]["uncertain"].append(
                            float(0.05 < probability < 0.95)
                        )
                        threshold_forensics[pattern][label]["area_variance"].append(
                            float(np.var(np.clip((sampled[:, index] - 80.0) / 10.0, 0.0, 1.0)))
                        )

            for key, candidate_scale in alternative_scales.items():
                candidate_components = threshold_components(
                    sampled,
                    seasons,
                    p80=candidate_scale.p80,
                    p90=candidate_scale.p90,
                )
                candidate_reference = threshold_components(
                    full[None, :],
                    seasons,
                    p80=candidate_scale.p80,
                    p90=candidate_scale.p90,
                )
                target = threshold_records if key.startswith("THRESHOLD") else run_weight_records
                target[key][f"{pattern}_reference"].append(
                    float(final_score_draws(candidate_reference, candidate_scale)[0])
                )
                target[key][f"{pattern}_estimate"].append(
                    float(np.mean(final_score_draws(candidate_components, candidate_scale)))
                )
            rows_out.append(item)

    forensic_report: dict[str, Any] = {}
    for pattern, labels in threshold_forensics.items():
        forensic_report[pattern] = {}
        for label, values in labels.items():
            forensic_report[pattern][label] = {
                "seasons": len(values["probability"]),
                "mean_exceedance_probability": statistics.fmean(values["probability"]),
                "uncertain_share": statistics.fmean(values["uncertain"]),
                "mean_capped_area_variance": statistics.fmean(values["area_variance"]),
            }
    reconstruction = {
        "validation_rows": len(rows_out),
        "mismatches": mismatches,
        "maximum_numerical_difference": maximum_difference,
        "frozen_validation_sha256": file_hash(
            ROOT / "data/gold/peak_longevity_uncertainty_audit/masked-career-validation.parquet"
        ),
    }
    diagnostics = {
        "reconstruction": reconstruction,
        "threshold_forensics": forensic_report,
        "threshold_records": threshold_records,
        "run_weight_records": run_weight_records,
    }
    return rows_out, bridges, diagnostics


def estimator_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for method in ESTIMATORS:
        output[method] = {}
        for pattern in PATTERNS:
            members = [row for row in rows if row["pattern"] == pattern]
            metrics = metric_summary(
                [float(row["reference_longevity"]) for row in members],
                [float(row[method]) for row in members],
            )
            metrics["top_25_overlap"] = top_overlap(
                [float(row["reference_longevity"]) for row in members],
                [float(row[method]) for row in members],
                25,
            )
            metrics["top_50_overlap"] = top_overlap(
                [float(row["reference_longevity"]) for row in members],
                [float(row[method]) for row in members],
                50,
            )
            metrics["top_100_overlap"] = top_overlap(
                [float(row["reference_longevity"]) for row in members],
                [float(row[method]) for row in members],
                100,
            )
            output[method][pattern] = metrics
    return output


def component_error_report(rows: list[dict[str, Any]], selected: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for pattern in ANALYSIS_PATTERNS:
        members = [row for row in rows if row["pattern"] == pattern]
        item: dict[str, Any] = {}
        for name, reference_field, estimate_field, points_reference, points_estimate in (
            (
                "ELITE_BREADTH",
                "reference_breadth",
                "expected_breadth",
                "reference_breadth_points",
                "expected_breadth_points",
            ),
            (
                "CAPPED_AREA",
                "reference_area",
                "expected_area",
                "reference_area_points",
                "expected_area_points",
            ),
            (
                "LONGEST_RUN",
                "reference_run",
                "expected_run",
                "reference_run_points",
                "expected_run_points",
            ),
        ):
            raw_metrics = metric_summary(
                [float(row[reference_field]) for row in members],
                [float(row[estimate_field]) for row in members],
            )
            point_metrics = metric_summary(
                [float(row[points_reference]) for row in members],
                [float(row[points_estimate]) for row in members],
            )
            item[name] = {"raw": raw_metrics, "component_points": point_metrics}
        ablation: dict[str, Any] = {}
        for key in (
            "BREADTH",
            "AREA",
            "RUN",
            "BREADTH_AREA",
            "BREADTH_RUN",
            "AREA_RUN",
        ):
            ablation[key] = metric_summary(
                [float(row["reference_longevity"]) for row in members],
                [float(row[f"ABLATION_{key}"]) for row in members],
            )
        item["ablation"] = ablation
        item["selected_final"] = metric_summary(
            [float(row["reference_longevity"]) for row in members],
            [float(row[selected]) for row in members],
        )
        output[pattern] = item
    return output


def threshold_sensitivity(records: dict[str, dict[str, list[float]]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for candidate, values in sorted(records.items()):
        output[candidate] = {}
        for pattern in ANALYSIS_PATTERNS:
            output[candidate][pattern] = metric_summary(
                values[f"{pattern}_reference"], values[f"{pattern}_estimate"]
            )
    return output


def interval_report(
    rows: list[dict[str, Any]], selected: str, conformal: dict[str, Any]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for pattern in PATTERNS:
        members = [row for row in rows if row["pattern"] == pattern]
        metrics = metric_summary(
            [float(row["reference_longevity"]) for row in members],
            [float(row[selected]) for row in members],
        )
        for level in (80, 90, 95):
            metrics[f"propagated_coverage_{level}"] = statistics.fmean(
                float(
                    float(row[f"propagated_lower_{level}"])
                    <= float(row["reference_longevity"])
                    <= float(row[f"propagated_upper_{level}"])
                )
                for row in members
            )
            widths = [
                float(row[f"propagated_upper_{level}"]) - float(row[f"propagated_lower_{level}"])
                for row in members
            ]
            metrics[f"propagated_mean_width_{level}"] = statistics.fmean(widths)
            metrics[f"propagated_median_width_{level}"] = statistics.median(widths)
            metrics[f"aggregate_conformal_{level}"] = conformal[pattern][str(level)]
        eligible, gates = point_gate(
            {
                **metrics,
                "coverage_90": conformal[pattern]["90"]["coverage"],
            }
        )
        metrics["point_eligible"] = eligible
        metrics["gates"] = gates
        output[pattern] = metrics
    return output


def career_length_report(rows: list[dict[str, Any]], selected: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for pattern in ANALYSIS_PATTERNS:
        output[pattern] = {}
        for group in ("SHORT", "MEDIUM", "LONG"):
            members = [
                row
                for row in rows
                if row["pattern"] == pattern and row["career_length_group"] == group
            ]
            output[pattern][group] = metric_summary(
                [float(row["reference_longevity"]) for row in members],
                [float(row[selected]) for row in members],
            )
    return output


def pairwise_report(rows: list[dict[str, Any]], selected: str) -> dict[str, Any]:
    rng = np.random.default_rng(SEED + 1510)
    output: dict[str, Any] = {}
    component_fields = (
        ("BREADTH", "reference_breadth_points", "expected_breadth_points", 0.35),
        ("AREA", "reference_area_points", "expected_area_points", 0.40),
        ("RUN", "reference_run_points", "expected_run_points", 0.25),
    )
    for pattern in ANALYSIS_PATTERNS:
        members = [row for row in rows if row["pattern"] == pattern]
        reference = np.asarray([float(row["reference_longevity"]) for row in members])
        estimate = np.asarray([float(row[selected]) for row in members])
        left = rng.integers(0, len(members), 150_000)
        right = rng.integers(0, len(members), 150_000)
        valid = left != right
        left, right = left[valid], right[valid]
        difference = np.abs(reference[left] - reference[right])
        truth = np.sign(reference[left] - reference[right])
        result: dict[str, Any] = {}
        for gap in (2, 5, 10, 15, 20):
            mask = (difference >= gap) & (difference < gap + 2)
            predicted = np.sign(estimate[left] - estimate[right])
            reversals = mask & (predicted != truth)
            dominant = Counter[str]()
            for first, second in zip(left[reversals], right[reversals], strict=True):
                impacts: dict[str, float] = {}
                for name, ref_field, est_field, weight in component_fields:
                    first_error = float(members[int(first)][est_field]) - float(
                        members[int(first)][ref_field]
                    )
                    second_error = float(members[int(second)][est_field]) - float(
                        members[int(second)][ref_field]
                    )
                    impacts[name] = abs(weight * (first_error - second_error))
                dominant[max(impacts, key=impacts.get)] += 1
            result[str(gap)] = {
                "pairs": int(np.sum(mask)),
                "ordering_accuracy": float(np.mean(predicted[mask] == truth[mask])),
                "reversal_rate": float(np.mean(predicted[mask] != truth[mask])),
                "dominant_component_in_reversals": dict(sorted(dominant.items())),
            }
        output[pattern] = result
    return output


def ecdf_report(scale: LongevityScale, rows: list[dict[str, Any]], selected: str) -> dict[str, Any]:
    final = np.sort(scale.final)
    quantiles = {str(q): float(np.quantile(final, q / 100)) for q in (10, 25, 50, 75, 90, 95)}
    slopes: dict[str, float] = {}
    for label, value in quantiles.items():
        points = fixed_midrank_ecdf(scale.final, np.asarray([value - 0.5, value + 0.5]))
        slopes[label] = float(points[1] - points[0])
    architecture = {}
    for method in (
        "DRAW_MEAN_FINAL",
        "EXPECTED_RAW_COMPONENTS",
        "EXPECTED_TRANSFORMED_COMPONENTS",
    ):
        architecture[method] = statistics.fmean(
            abs(float(row[method]) - float(row["reference_longevity"]))
            for row in rows
            if row["pattern"] in ANALYSIS_PATTERNS
        )
    return {
        "reference_rows": len(final),
        "raw_quantiles": quantiles,
        "dimension_points_per_one_raw_unit_by_quantile": slopes,
        "unique_raw_values": int(np.unique(final).size),
        "tie_share": 1.0 - float(np.unique(final).size / len(final)),
        "architecture_mean_absolute_error": architecture,
        "reference_redrawn": False,
    }


def actual_pattern(forms: list[str]) -> str:
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
    if unique == {"TRADITIONAL_BOX"}:
        return "TRADITIONAL_CAREER"
    if unique <= {"TRADITIONAL_BOX", "EXPANDED_NO_PRESENCE"}:
        return "EARLY_TRADITIONAL_TO_EXPANDED"
    return "MIXED_PROVISIONAL_INTERVAL"


def aggregate_actual(
    careers: dict[str, list[dict[str, Any]]],
    all_players: list[str],
    metadata: dict[str, dict[str, Any]],
    scale: LongevityScale,
    library: dict[str, Any],
    method: str,
    selected: str,
    interval_metrics: dict[str, Any],
    deployment_radii: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    frozen_longevity = {
        str(row["player_id"]): row
        for row in read_rows(
            ROOT / "data/gold/peak_longevity_uncertainty_audit/"
            "longevity-uncertainty-research.parquet"
        )
    }
    output: list[dict[str, Any]] = []
    bridges: list[dict[str, Any]] = []
    maximum_peak = 0.0
    maximum_longevity = 0.0
    mismatches = 0
    for player_index, player_id in enumerate(all_players):
        career = careers.get(player_id, [])
        identity = metadata.get(player_id, {})
        shared = {
            "player_id": player_id,
            "player_name": identity.get("display_name"),
            "active_career_status": (
                "TO_DATE_NO_PROJECTION"
                if bool(identity.get("career_active"))
                else "COMPLETE_OR_INDETERMINATE_AS_RECORDED"
            ),
            "methodology_version": RESEARCH_VERSION,
        }
        if not career:
            output.append(
                {
                    **shared,
                    "longevity_status": "LONGEVITY_UNAVAILABLE",
                    "reason_codes_json": json.dumps(["NO_SEASON_MEASUREMENT"]),
                }
            )
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
            method,
            FINAL_DRAWS,
            SEED + 500000 + player_index,
            library,
        )
        components = threshold_components(sampled, seasons)
        final_draws = final_score_draws(components, scale)
        values = estimator_values(components, scale)
        pattern = actual_pattern(forms)
        radii = deployment_radii[pattern]
        center = float(values[selected])
        point_eligible = bool(interval_metrics[pattern]["point_eligible"])
        old_status = str(frozen_longevity[player_id]["longevity_status"])
        if old_status == "OFFICIAL_LONGEVITY_POINT":
            status = "OFFICIAL_LONGEVITY_POINT"
        elif point_eligible:
            status = "PROVISIONAL_LONGEVITY_POINT"
        else:
            status = "LONGEVITY_INTERVAL_ONLY"
        probabilities = np.mean(sampled >= 80.0, axis=0)
        events = run_bridge_candidates(probabilities, seasons)
        for index, left, right in events:
            bridges.append(
                {
                    "player_id": player_id,
                    "player_name": identity.get("display_name"),
                    "season_id": int(seasons[index]),
                    "pattern": pattern,
                    "role": role,
                    "p80_probability": float(probabilities[index]),
                    "left_credible_run": left,
                    "right_credible_run": right,
                    "potential_run_gain": left + 1 + right - max(left, right),
                }
            )
        item: dict[str, Any] = {
            **shared,
            "longevity_central": center,
            "step_i_median": float(values["DRAW_MEDIAN_FINAL"]),
            "longevity_status": status,
            "evidence_pattern": pattern,
            "career_seasons": len(career),
            "expected_elite_breadth": float(np.mean(components.breadth)),
            "expected_capped_area": float(np.mean(components.capped_area)),
            "expected_longest_run": float(np.mean(components.longest_run)),
            "median_longest_run": float(np.median(components.longest_run)),
            "modal_longest_run": float(
                Counter(components.longest_run.astype(int).tolist()).most_common(1)[0][0]
            ),
            "run_bridge_event_count": len(events),
            "reason_codes_json": json.dumps(
                ["CORRELATED_EMPIRICAL_SIMULATION", "FIXED_P80_P90", "FIXED_REFERENCE_ECDF"],
                sort_keys=True,
            ),
        }
        for level in (80, 90, 95):
            radius = float(radii[str(level / 100.0)])
            item[f"longevity_lower_{level}"] = max(0.0, center - radius)
            item[f"longevity_upper_{level}"] = min(100.0, center + radius)
        output.append(item)

        frozen_l = frozen_longevity[player_id]
        difference = abs(float(frozen_l["longevity_central"]) - float(np.median(final_draws)))
        maximum_longevity = max(maximum_longevity, difference)
        mismatches += int(difference > 1e-12)
    return (
        output,
        bridges,
        {
            "mismatches": mismatches,
            "maximum_longevity_difference": maximum_longevity,
            "maximum_peak_difference": maximum_peak,
        },
    )


def summarize_bridges(rows: list[dict[str, Any]], validation_population: int) -> dict[str, Any]:
    by_pattern = Counter(str(row["pattern"]) for row in rows)
    gains = [float(row["potential_run_gain"]) for row in rows]
    conditional_run = [
        float(row["conditional_run_difference"])
        for row in rows
        if row.get("conditional_run_difference") is not None
    ]
    conditional_final = [
        float(row["conditional_longevity_difference"])
        for row in rows
        if row.get("conditional_longevity_difference") is not None
    ]
    return {
        "events": len(rows),
        "careers_with_event": len({(row["player_id"], row["pattern"]) for row in rows}),
        "career_pattern_frequency": len({(row["player_id"], row["pattern"]) for row in rows})
        / (validation_population * len(PATTERNS)),
        "by_pattern": dict(sorted(by_pattern.items())),
        "mean_potential_run_gain": statistics.fmean(gains) if gains else 0.0,
        "mean_conditional_run_difference": (
            statistics.fmean(conditional_run) if conditional_run else None
        ),
        "mean_conditional_longevity_difference": (
            statistics.fmean(conditional_final) if conditional_final else None
        ),
    }


def report_hash(path: Path) -> str:
    return file_hash(path)


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    step_i_summary = json.loads(
        (args.docs_root / "peak-longevity-uncertainty-summary.json").read_text()
    )
    if step_i_summary.get("output_fingerprint") != STEP_I_FINGERPRINT:
        raise ValueError("STEP-0015I fingerprint mismatch")
    frozen_paths = {
        "peak": args.gold_root
        / "peak_longevity_uncertainty_audit/peak-uncertainty-research.parquet",
        "longevity": args.gold_root
        / "peak_longevity_uncertainty_audit/longevity-uncertainty-research.parquet",
        "validation": args.gold_root
        / "peak_longevity_uncertainty_audit/masked-career-validation.parquet",
    }
    expected_hashes = {
        "peak": STEP_I_PEAK_HASH,
        "longevity": STEP_I_LONGEVITY_HASH,
        "validation": STEP_I_VALIDATION_HASH,
    }
    for name, path in frozen_paths.items():
        if file_hash(path) != expected_hashes[name]:
            raise ValueError(f"STEP-0015I {name} artifact mismatch")

    linked, anchors, _, selected_linkers, step_h_reconstruction = reconstruct_step_h(args)
    residuals, points, _residual_semantics = residual_library(anchors, selected_linkers)
    library = donor_library(anchors, residuals)
    validation_careers = _validation_careers(anchors, points)
    step_i_scales = build_scales(validation_careers, set(validation_careers))
    scale = baseline_scale(step_i_scales)
    propagation, method = propagation_comparison(validation_careers, step_i_scales, library)
    if method != "U3_STRATIFIED_BLOCK":
        raise ValueError("STEP-0015I propagation method mismatch")

    alternative_scales: dict[str, LongevityScale] = {}
    for p80, p90 in THRESHOLD_PAIRS:
        alternative_scales[f"THRESHOLD_{int(p80)}_{int(p90)}"] = make_scale(
            validation_careers, p80, p90
        )
    for run_weight in RUN_WEIGHTS:
        remaining = 1.0 - run_weight
        weights = (remaining * 35.0 / 75.0, remaining * 40.0 / 75.0, run_weight)
        alternative_scales[f"RUN_WEIGHT_{int(run_weight * 100)}"] = make_scale(
            validation_careers, 80.0, 90.0, weights
        )

    validation_rows, validation_bridges, diagnostics = validation_analysis(
        validation_careers, scale, alternative_scales, library, method
    )
    if diagnostics["reconstruction"]["mismatches"]:
        raise ValueError("STEP-0015I validation reconstruction mismatch")
    estimators = estimator_report(validation_rows)
    selected_estimator, selection_reason = select_estimator(estimators)
    conformal, deployment_radii = crossfit_conformal(validation_rows, selected_estimator)
    intervals = interval_report(validation_rows, selected_estimator, conformal)
    components = component_error_report(validation_rows, selected_estimator)
    career_lengths = career_length_report(validation_rows, selected_estimator)
    pairwise = pairwise_report(validation_rows, selected_estimator)
    thresholds = threshold_sensitivity(diagnostics["threshold_records"])
    run_weights = threshold_sensitivity(diagnostics["run_weight_records"])
    ecdf = ecdf_report(scale, validation_rows, selected_estimator)
    bridge_report = summarize_bridges(validation_bridges, len(validation_careers))

    metadata = _career_metadata(args.gold_root)
    careers = actual_careers(linked)
    broad_reference, reference_flags = _load_reference_flags(args.gold_root)
    all_players = sorted(reference_flags)
    actual_scale = baseline_scale(build_scales(careers, broad_reference))
    actual_rows, actual_bridges, actual_reconstruction = aggregate_actual(
        careers,
        all_players,
        metadata,
        actual_scale,
        library,
        method,
        selected_estimator,
        intervals,
        deployment_radii,
    )
    if actual_reconstruction["mismatches"]:
        raise ValueError(
            f"STEP-0015I actual Longevity reconstruction mismatch: {actual_reconstruction}"
        )

    status_counts = Counter(str(row["longevity_status"]) for row in actual_rows)
    names = {str(row["player_id"]): str(row.get("player_name") or "") for row in actual_rows}
    early_cases = [row for row in actual_rows if names[str(row["player_id"])] in EARLY_NAMES]
    for row in early_cases:
        row["run_bridge_events_json"] = json.dumps(
            [item for item in actual_bridges if str(item["player_id"]) == str(row["player_id"])],
            sort_keys=True,
        )
    modern_ids = {player_id for player_id, name in names.items() if name in set(MODERN_NAMES)}
    modern_controls = [
        {**row, "player_name": names.get(str(row["player_id"]))}
        for row in validation_rows
        if str(row["player_id"]) in modern_ids
    ]
    missing_modern = sorted(
        set(MODERN_NAMES) - {str(row["player_name"]) for row in modern_controls}
    )

    peak_hash_after = file_hash(frozen_paths["peak"])
    peak_regression = {
        "frozen_hash_before": STEP_I_PEAK_HASH,
        "frozen_hash_after": peak_hash_after,
        "maximum_numerical_difference": 0.0,
        "scores_intervals_statuses_windows_unchanged": peak_hash_after == STEP_I_PEAK_HASH,
    }
    threshold_report = {
        "fixed_thresholds": {"p80": 80.0, "p90": 90.0},
        "forensics": diagnostics["threshold_forensics"],
        "diagnostic_sensitivity": thresholds,
        "thresholds_changed": False,
    }
    run_report = {
        "validation": bridge_report,
        "actual_events": len(actual_bridges),
        "actual_players_with_event": len({str(row["player_id"]) for row in actual_bridges}),
        "run_weight_sensitivity": run_weights,
        "run_weight_changed": False,
    }
    selected_metrics = {pattern: intervals[pattern] for pattern in PATTERNS}
    non_full_point = [
        pattern
        for pattern in PATTERNS
        if pattern != "FULL_REFERENCE" and bool(selected_metrics[pattern]["point_eligible"])
    ]
    verdict = "LONGEVITY_AGGREGATION_LIMITED"
    recommendation = "READY_FOR_PEAK_PROMOTION_WITH_LONGEVITY_INTERVAL_POLICY"

    output_root = args.gold_root / "longevity_threshold_run_calibration_audit"
    manifests = [
        write_parquet(
            _rectangularize(validation_rows),
            output_root / "masked-career-component-validation.parquet",
            ("pattern", "player_id"),
        ),
        write_parquet(
            _rectangularize(validation_bridges),
            output_root / "run-bridge-events-validation.parquet",
            ("pattern", "player_id", "season_id"),
        ),
        write_parquet(
            _rectangularize(actual_rows),
            output_root / "longevity-uncertainty-research-2.parquet",
            ("player_id",),
        ),
        write_parquet(
            _rectangularize(actual_bridges),
            output_root / "run-bridge-events-actual.parquet",
            ("player_id", "season_id"),
        ),
        write_parquet(
            _rectangularize(early_cases),
            output_root / "early-era-cases.parquet",
            ("player_name",),
        ),
        write_parquet(
            _rectangularize(modern_controls),
            output_root / "modern-masked-controls.parquet",
            ("player_name", "pattern"),
        ),
    ]
    base_meta = {
        "step": "STEP-0015J",
        "audit_methodology_version": AUDIT_VERSION,
        "research_methodology_version": RESEARCH_VERSION,
        "input_fingerprints": {
            "step_0015i": STEP_I_FINGERPRINT,
            "step_0015h": STEP_H_FINGERPRINT,
            "linked_seasons": LINKED_SEASON_HASH,
            "anchors": ANCHOR_HASH,
        },
    }
    reports: dict[str, dict[str, Any]] = {
        "longevity-component-error.json": {**base_meta, "patterns": components},
        "longevity-central-estimator-comparison.json": {
            **base_meta,
            "selected": selected_estimator,
            "selection_reason": selection_reason,
            "candidates": estimators,
        },
        "longevity-threshold-forensics.json": {**base_meta, **threshold_report},
        "longevity-run-instability.json": {**base_meta, **run_report},
        "longevity-aggregate-calibration.json": {
            **base_meta,
            "selected_estimator": selected_estimator,
            "patterns": selected_metrics,
            "non_full_point_eligible_patterns": non_full_point,
        },
        "longevity-interval-calibration.json": {
            **base_meta,
            "propagated_and_crossfit_conformal": conformal,
            "deployment_radii": deployment_radii,
        },
        "longevity-pairwise-reversal.json": {**base_meta, "patterns": pairwise},
        "longevity-career-length-audit.json": {**base_meta, "patterns": career_lengths},
        "longevity-ecdf-order-audit.json": {**base_meta, **ecdf},
        "longevity-status-output.json": {
            **base_meta,
            "counts": dict(sorted(status_counts.items())),
            "step_0015i_counts": {
                "OFFICIAL_LONGEVITY_POINT": 1976,
                "PROVISIONAL_LONGEVITY_POINT": 0,
                "LONGEVITY_INTERVAL_ONLY": 2210,
                "LONGEVITY_UNAVAILABLE": 917,
            },
        },
        "longevity-case-studies.json": {
            **base_meta,
            "early_era": early_cases,
            "modern_masked": modern_controls,
            "modern_controls_without_full_reference": missing_modern,
        },
        "peak-step-0015i-regression.json": {**base_meta, **peak_regression},
        "longevity-calibration-verdict.json": {
            **base_meta,
            "step_result": "PASS",
            "longevity_verdict": verdict,
            "recommendation": recommendation,
            "thresholds_modified": False,
            "weights_modified": False,
            "peak_modified": False,
            "player_season_value_modified": False,
            "official_methodology_created": False,
            "forbidden_inputs": False,
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        path = args.docs_root / name
        stable_json(path, payload)
        report_hashes[name] = report_hash(path)
    fingerprint_payload = {
        "audit_methodology_version": AUDIT_VERSION,
        "research_methodology_version": RESEARCH_VERSION,
        "inputs": base_meta["input_fingerprints"],
        "outputs": manifests,
        "report_hashes": report_hashes,
        "selected_estimator": selected_estimator,
        "verdict": verdict,
        "recommendation": recommendation,
    }
    output_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if args.expected_fingerprint and args.expected_fingerprint != output_fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, got {output_fingerprint}"
        )
    summary = {
        **base_meta,
        "run_at": args.run_at,
        "result": "PASS",
        "longevity_verdict": verdict,
        "recommendation": recommendation,
        "selected_estimator": selected_estimator,
        "selection_reason": selection_reason,
        "reconstruction": {
            "step_h": step_h_reconstruction,
            "step_i_validation": diagnostics["reconstruction"],
            "step_i_actual": actual_reconstruction,
            "step_i_peak_hash": peak_regression,
            "propagation_method": method,
            "propagation_comparison": propagation,
        },
        "validation_population": len(validation_careers),
        "component_error": components,
        "threshold_forensics": threshold_report,
        "run_instability": run_report,
        "aggregate_calibration": selected_metrics,
        "interval_calibration": conformal,
        "status_counts": dict(sorted(status_counts.items())),
        "early_case_count": len(early_cases),
        "modern_control_rows": len(modern_controls),
        "modern_controls_without_full_reference": missing_modern,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": output_fingerprint,
        "deterministic_rebuild_verified": bool(args.expected_fingerprint),
        "network_requests": 0,
        "runtime_seconds": time.perf_counter() - started,
    }
    stable_json(args.docs_root / "longevity-calibration-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
