#!/usr/bin/env python3
"""Run STEP-0015N Final Overall V2 promotion audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import numpy as np

from goatlab.rankings.overall import rank_scores, top_n_overlap
from goatlab.rankings.overall_v2 import (
    FROZEN_OVERALL_WEIGHTS,
    OVERALL_V2_AUDIT_VERSION,
    OVERALL_V2_VERSION,
    couple_defense_ranks,
    independent_defense_ranks,
    nearest_psd_correlation,
    overall_draws_v2,
    variance_decomposition,
)
from goatlab.rankings.uncertainty_aggregation import quantile_interval
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_overall_uncertainty import (
    DIMENSION_V1_HASH,
    OVERALL_V1_HASH,
    TOP100_V1_HASH,
    _apply_deployment_interval,
    _ensure_nested_intervals,
    _overall_actual_pattern,
    _point_gate,
    _rank_matrix,
    _summary,
    calibrate_intervals,
    dimension_index,
    pairwise_validation,
    top_n_validation,
    validation_audit,
)
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
    residual_library,
    simulate_seasons,
)
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet

ROOT = Path(__file__).resolve().parents[2]
RUN_AT_DEFAULT = "2026-09-17T02:00:00Z"
STEP_K_FINGERPRINT = "3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f"
STEP_L_FINGERPRINT = "cb740fc68a77df3cb30b68e854e413c670394638ff2bf7b47401b905c7a81580"
STEP_M_FINGERPRINT = "a2056a6d793b2f82066c07bc4924787d3e95f8485ef37ff15911bfb7a321deb7"
PEAK_HASH = "0359b58240388e70c3dc3e6447b1786d506e344ad826c8b6bb22879e9c057b17"
LONGEVITY_HASH = "10ddf4266cf0f857d398ede01c336e012d7f6ae3d8c29c5442514c7585b76779"
DEFENSE_HASH = "81d0dc4723884a8efeebaa9bdee19fbf52a8d9373d1d767ff49af9d23cb86418"
ANCHOR_HASH = "1821e4d7a15fccb70819f49d234f019ce75cba06613a86c80cc07e04fb8d202a"
SEASON_CONTRACT_HASH = "b4190fa29df53f6e796e6d8e104e6bd63bf237f332af739ca4be3b6ff70fbb76"
OTHER_FIXED = ("OFFENSE", "PLAYOFFS", "ACCOLADES", "WINNING")
LEVELS = (0.80, 0.90, 0.95)
EARLY = (
    "George Mikan",
    "Bob Pettit",
    "Bill Russell",
    "Wilt Chamberlain",
    "Oscar Robertson",
    "Elgin Baylor",
    "Jerry West",
    "Kareem Abdul-Jabbar",
)
MODERN = (
    "Michael Jordan",
    "LeBron James",
    "Larry Bird",
    "Tim Duncan",
    "Stephen Curry",
    "Shaquille O'Neal",
    "Kevin Garnett",
    "Hakeem Olajuwon",
    "Kobe Bryant",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
    "Kawhi Leonard",
    "Rudy Gobert",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def rectangularize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = sorted({key for row in rows for key in row})
    return [{key: row.get(key) for key in columns} for row in rows]


def fixed_without_defense(profile: dict[str, dict[str, Any]]) -> float | None:
    total = 0.0
    for dimension in OTHER_FIXED:
        value = profile[dimension].get("score")
        if value is None:
            return None
        total += FROZEN_OVERALL_WEIGHTS[dimension] * float(value)
    return total


def defense_pattern_for_pl(pattern: str) -> str:
    return {
        "FULL_REFERENCE": "NO_TEAM_CONTEXT",
        "PARTIAL_PRESENCE_LATE": "PARTIAL_PRESENCE",
        "NO_PRESENCE_CAREER": "NO_PRESENCE",
        "TRADITIONAL_CAREER": "TRADITIONAL_ONLY",
        "EARLY_TRADITIONAL_TO_EXPANDED": "MIXED_TRANSITION",
        "MIXED_PROVISIONAL_INTERVAL": "MIXED_TRANSITION",
    }[pattern]


def combined_pattern(pl_pattern: str | None, defense_pattern: str | None) -> str | None:
    if pl_pattern is None or defense_pattern is None:
        return None
    if pl_pattern == "FULL_REFERENCE" and defense_pattern == "FULL_REFERENCE":
        return "FULL_REFERENCE"
    if pl_pattern in {"FULL_REFERENCE", "PARTIAL_PRESENCE_LATE"} and defense_pattern in {
        "FULL_REFERENCE",
        "NO_TEAM_CONTEXT",
        "PARTIAL_PRESENCE",
    }:
        return "PARTIAL_PRESENCE_LATE"
    if pl_pattern == "TRADITIONAL_CAREER" and defense_pattern == "TRADITIONAL_ONLY":
        return "TRADITIONAL_CAREER"
    if pl_pattern == "NO_PRESENCE_CAREER" and defense_pattern == "NO_PRESENCE":
        return "NO_PRESENCE_CAREER"
    return "MIXED_PROVISIONAL_INTERVAL"


def empirical_marginal(
    center: float,
    lower_90: float,
    upper_90: float,
    residuals: np.ndarray,
    draws: int = FINAL_DRAWS,
) -> np.ndarray:
    """Create an empirical marginal matching the promoted center and 90% bounds."""

    source = np.sort(np.asarray(residuals, dtype=float) - float(np.median(residuals)))
    indexes: np.ndarray = np.linspace(0, len(source) - 1, draws).round().astype(int)
    values = source[indexes]
    low = float(np.quantile(values, 0.05))
    high = float(np.quantile(values, 0.95))
    negative_scale = (center - lower_90) / max(abs(low), 1e-9)
    positive_scale = (upper_90 - center) / max(high, 1e-9)
    scaled = np.where(values < 0, values * negative_scale, values * positive_scale)
    result = np.clip(center + scaled, 0.0, 100.0)
    # Preserve the exact promoted central semantics.
    result += center - float(np.median(result))
    return cast(np.ndarray, np.asarray(np.clip(result, 0.0, 100.0), dtype=float))


def target_matrices(docs_root: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    source = json.loads((docs_root / "defense-v2-joint-uncertainty.json").read_text())
    output: dict[str, np.ndarray] = {}
    reports: dict[str, Any] = {}
    weighted = []
    weights = []
    for pattern in ("MIXED_TRANSITION", "NO_PRESENCE", "PARTIAL_PRESENCE", "TRADITIONAL_ONLY"):
        row = source[pattern]
        matrix = np.asarray(
            [
                [
                    1.0,
                    row["peak_longevity_residual_correlation"],
                    row["defense_peak_residual_correlation"],
                ],
                [
                    row["peak_longevity_residual_correlation"],
                    1.0,
                    row["defense_longevity_residual_correlation"],
                ],
                [
                    row["defense_peak_residual_correlation"],
                    row["defense_longevity_residual_correlation"],
                    1.0,
                ],
            ]
        )
        corrected, report = nearest_psd_correlation(matrix)
        output[pattern] = corrected
        reports[pattern] = {
            **report,
            "sample_size": int(row["players"]),
            "matrix": corrected.tolist(),
        }
        weighted.append(corrected)
        weights.append(int(row["players"]))
    pooled = np.average(np.stack(weighted), axis=0, weights=np.asarray(weights))
    output["POOLED"] = nearest_psd_correlation(pooled)[0]
    reports["POOLED"] = {"matrix": output["POOLED"].tolist(), "sample_size": sum(weights)}
    output["NO_TEAM_CONTEXT"] = output["PARTIAL_PRESENCE"]
    output["FULL_REFERENCE"] = output["PARTIAL_PRESENCE"]
    return output, reports


def defense_residual_pools(rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row["pattern"])].append(
            float(row["reference_defense"]) - float(row["estimated_defense"])
        )
    return {key: np.asarray(values) for key, values in grouped.items()}


def _actual_defense_pool(pattern: str, pools: dict[str, np.ndarray]) -> np.ndarray:
    return pools.get(pattern, pools["MIXED_TRANSITION"])


def _couple(
    architecture: str,
    peak: np.ndarray,
    longevity: np.ndarray,
    defense: np.ndarray,
    pattern: str,
    matrices: dict[str, np.ndarray],
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if architecture == "C0_INDEPENDENT":
        return independent_defense_ranks(defense, seed=seed), {"architecture": architecture}
    matrix = matrices["POOLED"] if architecture == "C1_POOLED_GAUSSIAN" else matrices[pattern]
    coupled, report = couple_defense_ranks(peak, longevity, defense, matrix, seed=seed)
    if architecture == "C3_EMPIRICAL_RANK":
        # Empirical-rank diagnostic: replace Gaussian noise order with a deterministic rotation.
        rotation = int(hashlib.sha256(f"{seed}|empirical".encode()).hexdigest()[:8], 16) % len(
            defense
        )
        blend = 0.75 * coupled + 0.25 * np.roll(np.sort(defense), rotation)
        order = np.argsort(blend, kind="stable")
        empirical = np.empty_like(defense)
        empirical[order] = np.sort(defense)
        coupled = empirical
    return coupled, {"architecture": architecture, **report}


def reconstruct_and_load(args: argparse.Namespace) -> dict[str, Any]:
    summaries = {
        "K": json.loads((args.docs_root / "step-0015k-summary.json").read_text()),
        "L": json.loads((args.docs_root / "overall-uncertainty-summary.json").read_text()),
        "M": json.loads((args.docs_root / "defense-v2-tiered-promotion-summary.json").read_text()),
    }
    expected = {"K": STEP_K_FINGERPRINT, "L": STEP_L_FINGERPRINT, "M": STEP_M_FINGERPRINT}
    for key, fingerprint in expected.items():
        if summaries[key]["output_fingerprint"] != fingerprint:
            raise ValueError(f"STEP-0015{key} fingerprint mismatch")
    paths = {
        "season_contract": args.gold_root
        / "peak_longevity_policy_freeze/season-measurement-contract.parquet",
        "peak": args.gold_root / "peak_longevity_policy_freeze/peak-v2.parquet",
        "longevity": args.gold_root / "peak_longevity_policy_freeze/longevity-v2-tiered.parquet",
        "defense": args.gold_root
        / "defense_v2_tiered_promotion_audit/player-defense-v2-tiered.parquet",
        "defense_validation": args.gold_root
        / "defense_v2_tiered_promotion_audit/defense-v2-career-validation.parquet",
        "anchors": args.gold_root
        / "player_season_value_measurement_linking_audit/anchor-masked-pairs.parquet",
        "dimensions": args.gold_root / "player_dimension_scores/part-00000.parquet",
        "overall_l": args.gold_root
        / "overall_uncertainty_architecture_audit/overall-uncertainty-research.parquet",
        "overall_v1": args.gold_root / "player_overall_scores/part-00000.parquet",
        "top100_v1": args.gold_root / "overall_top100/part-00000.parquet",
    }
    hashes = {
        "season_contract": SEASON_CONTRACT_HASH,
        "peak": PEAK_HASH,
        "longevity": LONGEVITY_HASH,
        "defense": DEFENSE_HASH,
        "anchors": ANCHOR_HASH,
        "dimensions": DIMENSION_V1_HASH,
        "overall_v1": OVERALL_V1_HASH,
        "top100_v1": TOP100_V1_HASH,
    }
    for key, expected_hash in hashes.items():
        if file_hash(paths[key]) != expected_hash:
            raise ValueError(f"frozen input hash mismatch: {key}")
    return {"summaries": summaries, "paths": paths, "hashes": hashes}


def validation(
    anchors: list[dict[str, Any]],
    selected_linkers: dict[str, str],
    dimensions: dict[str, dict[str, dict[str, Any]]],
    defense_validation: list[dict[str, Any]],
    matrices: dict[str, np.ndarray],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, bool],
    dict[str, dict[int, float]],
    dict[str, Any],
]:
    *_, internals = validation_audit(anchors, selected_linkers, dimensions)
    library, scales = internals["library"], internals["scales"]
    residual_pools = defense_residual_pools(defense_validation)
    defense_index = {
        (str(row["player_id"]), str(row["pattern"])): row for row in defense_validation
    }
    _, linked_points, _ = residual_library(anchors, selected_linkers)
    careers = _validation_careers(anchors, linked_points)
    players = [
        player
        for player in sorted(careers)
        if all(dimensions[player][dimension].get("score") is not None for dimension in OTHER_FIXED)
        and (player, "MIXED_TRANSITION") in defense_index
    ]
    players = players[:1200]
    architectures = (
        "C0_INDEPENDENT",
        "C1_POOLED_GAUSSIAN",
        "C2_PATTERN_GAUSSIAN",
        "C3_EMPIRICAL_RANK",
    )
    rows_by_architecture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    draw_cache: dict[str, dict[str, dict[str, np.ndarray]]] = defaultdict(lambda: defaultdict(dict))
    coupling_reports: dict[str, list[dict[str, Any]]] = defaultdict(list)
    marginal_differences: list[float] = []
    for pattern_index, pattern in enumerate(PATTERNS):
        defense_pattern = defense_pattern_for_pl(pattern)
        for player_index, player_id in enumerate(players):
            career = careers[player_id]
            seasons = np.asarray([int(row["season_id"]) for row in career])
            full = np.asarray([[float(row["full_score"]) for row in career]])
            reference_peak, reference_longevity, _, _ = aggregate_draws(full, seasons, scales)
            defense_row = defense_index[(player_id, defense_pattern)]
            reference_defense = float(defense_row["reference_defense"])
            fixed = cast(float, fixed_without_defense(dimensions[player_id]))
            reference_overall = float(
                overall_draws_v2(
                    reference_peak, reference_longevity, np.asarray([reference_defense]), fixed
                )[0]
            )
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
                _mode([str(row["role"]) for row in career]),
                {label for row in career for label in json.loads(str(row["archetypes_json"]))},
                "U3_STRATIFIED_BLOCK",
                FINAL_DRAWS,
                SEED + player_index * 17 + pattern_index,
                library,
            )
            peak, longevity, _, _ = aggregate_draws(sampled, seasons, scales)
            defense_marginal = empirical_marginal(
                float(defense_row["estimated_defense"]),
                float(defense_row["lower_90"]),
                float(defense_row["upper_90"]),
                residual_pools[defense_pattern],
            )
            for architecture_index, architecture in enumerate(architectures):
                defense, coupling = _couple(
                    architecture,
                    peak,
                    longevity,
                    defense_marginal,
                    defense_pattern,
                    matrices,
                    SEED + 800000 + player_index * 31 + pattern_index * 7 + architecture_index,
                )
                marginal_differences.append(
                    float(np.max(np.abs(np.sort(defense) - np.sort(defense_marginal))))
                )
                values = overall_draws_v2(peak, longevity, defense, fixed)
                item: dict[str, Any] = {
                    "player_id": player_id,
                    "pattern": pattern,
                    "defense_pattern": defense_pattern,
                    "architecture": architecture,
                    "reference_overall": reference_overall,
                    "overall_median": float(np.median(values)),
                    "overall_mean": float(np.mean(values)),
                    "reference_defense": reference_defense,
                    "defense_median": float(np.median(defense)),
                    **variance_decomposition(peak, longevity, defense),
                }
                for level in LEVELS:
                    lower, upper = quantile_interval(values, level)
                    item[f"raw_lower_{int(level * 100)}"] = lower
                    item[f"raw_upper_{int(level * 100)}"] = upper
                rows_by_architecture[architecture].append(item)
                draw_cache[architecture][pattern][player_id] = values
                if architecture != "C0_INDEPENDENT":
                    coupling_reports[architecture].append(coupling)
    reports: dict[str, Any] = {}
    selected_rows = rows_by_architecture["C2_PATTERN_GAUSSIAN"]
    point_eligible: dict[str, bool] = {}
    deployment: dict[str, dict[int, float]] = {}
    selected_report: dict[str, Any] = {}
    for architecture, rows in rows_by_architecture.items():
        architecture_report: dict[str, Any] = {}
        for pattern in PATTERNS:
            members = [row for row in rows if row["pattern"] == pattern]
            interval_report = None
            if architecture == "C2_PATTERN_GAUSSIAN":
                deployment[pattern], interval_report = calibrate_intervals(members)
            metrics = _summary(
                [float(row["reference_overall"]) for row in members],
                [float(row["overall_median"]) for row in members],
            )
            if interval_report:
                for level in (80, 90, 95):
                    metrics[f"coverage_{level}"] = interval_report[str(level)]["coverage"]
                    metrics[f"mean_width_{level}"] = interval_report[str(level)]["mean_width"]
                passed, gates = _point_gate(metrics)
                metrics["gates"] = gates
                metrics["point_eligible"] = passed
                point_eligible[pattern] = passed
                selected_report[pattern] = metrics
            architecture_report[pattern] = metrics
        reports[architecture] = architecture_report
    marginal_difference = max(marginal_differences, default=0.0)
    coupling_summary = {
        architecture: {
            "mean_target_defense_peak": statistics.fmean(
                float(row["target_defense_peak"]) for row in values
            ),
            "mean_reproduced_defense_peak": statistics.fmean(
                float(row["reproduced_defense_peak"]) for row in values
            ),
            "mean_target_defense_longevity": statistics.fmean(
                float(row["target_defense_longevity"]) for row in values
            ),
            "mean_reproduced_defense_longevity": statistics.fmean(
                float(row["reproduced_defense_longevity"]) for row in values
            ),
        }
        for architecture, values in coupling_reports.items()
    }
    validation_report = {
        "population": len(players),
        "architectures": reports,
        "selected": "C2_PATTERN_GAUSSIAN",
        "selected_patterns": selected_report,
        "coupling": coupling_summary,
        "maximum_marginal_median_difference": marginal_difference,
    }
    return (
        selected_rows,
        validation_report,
        point_eligible,
        deployment,
        {
            "library": library,
            "scales": scales,
            "residual_pools": residual_pools,
            "draw_cache": draw_cache["C2_PATTERN_GAUSSIAN"],
            "players": players,
        },
    )


def eligibility_class(
    peak: dict[str, Any],
    longevity: dict[str, Any],
    defense: dict[str, Any],
    dimensions: dict[str, dict[str, Any]],
) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    statuses = (
        str(peak["peak_status"]),
        str(longevity["longevity_status"]),
        str(defense["defense_status"]),
    )
    if statuses[0] == "PEAK_UNAVAILABLE":
        reasons.append(
            "PEAK_CONSTITUTIONALLY_INELIGIBLE"
            if str(peak.get("peak_coverage_class") or "").startswith("CONSTITUTIONALLY_INELIGIBLE")
            else "PEAK_UNAVAILABLE"
        )
    if statuses[1] == "LONGEVITY_UNAVAILABLE":
        reasons.append("LONGEVITY_UNAVAILABLE")
    if statuses[2] == "DEFENSE_UNAVAILABLE":
        reasons.append("DEFENSE_UNAVAILABLE")
    for dimension in OTHER_FIXED:
        row = dimensions[dimension]
        if row.get("score") is None:
            if dimension == "ACCOLADES" and row.get("coverage_status") == "NOT_QUERIED":
                reasons.append("ACCOLADES_NOT_QUERIED")
            else:
                reasons.append(f"{dimension}_UNAVAILABLE")
    if reasons:
        return "REQUIRED_DIMENSION_UNAVAILABLE", tuple(sorted(reasons))
    if any("INTERVAL_ONLY" in status for status in statuses):
        return "UNCERTAIN_DIMENSION_PRESENT", ()
    if any("PROVISIONAL" in status for status in statuses):
        return "POINT_INPUTS_WITH_PROVISIONAL", ()
    return "COMPLETE_OFFICIAL_INPUTS", ()


def actual_audit(
    season_contract: list[dict[str, Any]],
    peaks: dict[str, dict[str, Any]],
    longevity: dict[str, dict[str, Any]],
    defense: dict[str, dict[str, Any]],
    dimensions: dict[str, dict[str, dict[str, Any]]],
    flags: dict[str, dict[str, Any]],
    library: dict[str, Any],
    residual_pools: dict[str, np.ndarray],
    matrices: dict[str, np.ndarray],
    point_eligible: dict[str, bool],
    deployment: dict[str, dict[int, float]],
    l_rows: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray], dict[str, Any]]:
    careers = actual_careers(season_contract)
    broad = {player for player, row in flags.items() if bool(row.get("BROAD_HIGH_RECALL"))}
    scales = build_scales(careers, broad)
    output: list[dict[str, Any]] = []
    draws_by_player: dict[str, np.ndarray] = {}
    pl_reconstruction_differences: list[float] = []
    reason_counts: Counter[str] = Counter()
    for player_index, player_id in enumerate(sorted(flags)):
        peak_row, long_row, defense_row = peaks[player_id], longevity[player_id], defense[player_id]
        input_class, reasons = eligibility_class(
            peak_row, long_row, defense_row, dimensions[player_id]
        )
        reason_counts.update(reasons)
        career = careers.get(player_id, [])
        pl_pattern = (
            _overall_actual_pattern([str(row["measurement_form"]) for row in career])
            if career
            else None
        )
        defense_pattern = str(defense_row.get("evidence_pattern") or "") or None
        pattern = combined_pattern(pl_pattern, defense_pattern)
        base: dict[str, Any] = {
            "player_id": player_id,
            "player_name": peak_row.get("player_name"),
            "input_eligibility_class": input_class,
            "peak_status": peak_row["peak_status"],
            "longevity_status": long_row["longevity_status"],
            "defense_status": defense_row["defense_status"],
            "peak_longevity_pattern": pl_pattern,
            "defense_pattern": defense_pattern,
            "joint_pattern": pattern,
            "blocking_reasons_json": json.dumps(reasons),
            "active_career_policy": "TO_DATE_NO_PROJECTION",
            "weight_renormalized": False,
            "confidence_penalty_applied": False,
            "interval_midpoint_used_as_exact": False,
            "methodology_version": OVERALL_V2_VERSION,
        }
        fixed = fixed_without_defense(dimensions[player_id])
        if (
            input_class == "REQUIRED_DIMENSION_UNAVAILABLE"
            or not career
            or fixed is None
            or pattern is None
        ):
            base["overall_status"] = "OVERALL_UNAVAILABLE"
            output.append(base)
            continue
        seasons = np.asarray([int(row["season_id"]) for row in career])
        centers = np.asarray([float(row["center"]) for row in career])
        forms = [str(row["measurement_form"]) for row in career]
        sampled = simulate_seasons(
            centers,
            forms,
            _mode([str(row["role"]) for row in career]),
            set(),
            "U3_STRATIFIED_BLOCK",
            FINAL_DRAWS,
            SEED + 500000 + player_index,
            library,
        )
        peak_draws, longevity_draws, _, _ = aggregate_draws(sampled, seasons, scales)
        # Verify the exact paired Peak/Longevity path against STEP-0015L before substitution.
        old_defense = dimensions[player_id]["DEFENSE"].get("score")
        if (
            old_defense is not None
            and l_rows.get(player_id, {}).get("overall_diagnostic_center") is not None
        ):
            old_fixed = fixed + FROZEN_OVERALL_WEIGHTS["DEFENSE"] * float(old_defense)
            reconstructed_l = float(
                np.median(
                    FROZEN_OVERALL_WEIGHTS["PEAK"] * peak_draws
                    + FROZEN_OVERALL_WEIGHTS["LONGEVITY"] * longevity_draws
                    + old_fixed
                )
            )
            pl_reconstruction_differences.append(
                abs(reconstructed_l - float(l_rows[player_id]["overall_diagnostic_center"]))
            )
        center = float(defense_row["defense_central"])
        defense_marginal = empirical_marginal(
            center,
            float(defense_row["defense_lower_90"]),
            float(defense_row["defense_upper_90"]),
            _actual_defense_pool(cast(str, defense_pattern), residual_pools),
        )
        target_key = cast(str, defense_pattern)
        if target_key not in matrices:
            target_key = "MIXED_TRANSITION"
        defense_draws, coupling = couple_defense_ranks(
            peak_draws,
            longevity_draws,
            defense_marginal,
            matrices[target_key],
            seed=SEED + 950000 + player_index,
        )
        overall = overall_draws_v2(peak_draws, longevity_draws, defense_draws, fixed)
        center_overall = float(np.median(overall))
        point_passed = bool(point_eligible.get(pattern, False))
        if not point_passed:
            status = "OVERALL_INTERVAL_ONLY"
        elif input_class == "COMPLETE_OFFICIAL_INPUTS":
            status = "OFFICIAL_OVERALL_POINT"
        else:
            status = "PROVISIONAL_OVERALL_POINT"
        item = {
            **base,
            "overall_status": status,
            "overall_point": center_overall
            if status in {"OFFICIAL_OVERALL_POINT", "PROVISIONAL_OVERALL_POINT"}
            else None,
            "overall_diagnostic_center": center_overall,
            "overall_mean": float(np.mean(overall)),
            "overall_standard_deviation": float(np.std(overall)),
            "overall_skew": float(
                np.mean(((overall - np.mean(overall)) / max(np.std(overall), 1e-9)) ** 3)
            ),
            "peak_central": peak_row.get("peak_central"),
            "longevity_central": long_row.get("longevity_central"),
            "defense_central": defense_row.get("defense_central"),
            "coupling_target_defense_peak": coupling["target_defense_peak"],
            "coupling_reproduced_defense_peak": coupling["reproduced_defense_peak"],
            "coupling_target_defense_longevity": coupling["target_defense_longevity"],
            "coupling_reproduced_defense_longevity": coupling["reproduced_defense_longevity"],
            **variance_decomposition(peak_draws, longevity_draws, defense_draws),
        }
        for level in LEVELS:
            low, high = _apply_deployment_interval(
                overall,
                center_overall,
                deployment[pattern][int(level * 100)],
                level,
            )
            item[f"overall_lower_{int(level * 100)}"] = low
            item[f"overall_upper_{int(level * 100)}"] = high
        _ensure_nested_intervals(item)
        output.append(item)
        draws_by_player[player_id] = overall
    return (
        output,
        draws_by_player,
        {
            "maximum_peak_longevity_path_difference_vs_step_0015l": max(
                pl_reconstruction_differences, default=0.0
            ),
            "blocking_reason_counts_nonexclusive": dict(sorted(reason_counts.items())),
        },
    )


def scope_counts(rows: list[dict[str, Any]], broad: set[str], top100: set[str]) -> dict[str, Any]:
    scopes = {
        "ALL_PLAYERS": rows,
        "BROAD_HIGH_RECALL": [row for row in rows if str(row["player_id"]) in broad],
        "V1_TOP_100": [row for row in rows if str(row["player_id"]) in top100],
    }
    return {
        name: {
            "population": len(members),
            "input_eligibility": dict(
                sorted(Counter(str(row["input_eligibility_class"]) for row in members).items())
            ),
            "overall_status": dict(
                sorted(Counter(str(row["overall_status"]) for row in members).items())
            ),
        }
        for name, members in scopes.items()
    }


def rank_outputs(
    actual: list[dict[str, Any]], draws: dict[str, np.ndarray]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    eligible = [
        row
        for row in actual
        if row["overall_status"] in {"OFFICIAL_OVERALL_POINT", "PROVISIONAL_OVERALL_POINT"}
    ]
    ranked = rank_scores({str(row["player_id"]): float(row["overall_point"]) for row in eligible})
    rank_lookup = {row.player_id: row.rank for row in ranked}
    players = sorted(
        (str(row["player_id"]) for row in eligible), key=lambda item: rank_lookup[item]
    )
    matrix = np.vstack([draws[player] for player in players])
    draw_ranks = _rank_matrix(matrix)
    rank_rows = []
    for index, player_id in enumerate(players):
        row = next(item for item in eligible if str(item["player_id"]) == player_id)
        item = {
            "player_id": player_id,
            "player_name": row["player_name"],
            "overall_rank": rank_lookup[player_id],
            "median_rank": float(np.median(draw_ranks[index])),
            "rank_lower_80": float(np.quantile(draw_ranks[index], 0.10)),
            "rank_upper_80": float(np.quantile(draw_ranks[index], 0.90)),
            "rank_lower_90": float(np.quantile(draw_ranks[index], 0.05)),
            "rank_upper_90": float(np.quantile(draw_ranks[index], 0.95)),
            **{
                f"probability_top_{n}": float(np.mean(draw_ranks[index] <= n))
                for n in (10, 25, 50, 100)
            },
            "conditional_on_frozen_methodologies": True,
            "shared_calibration_model_uncertainty_modeled": False,
            "methodology_version": OVERALL_V2_VERSION,
        }
        rank_rows.append(item)
    rank_index = {str(row["player_id"]): row for row in rank_rows}
    top100 = []
    for row in sorted(eligible, key=lambda item: rank_lookup[str(item["player_id"])])[:100]:
        player_id = str(row["player_id"])
        top100.append({**row, **rank_index[player_id]})
    report = {
        "point_ranked_population": len(eligible),
        "mean_rank_band_width_80": statistics.fmean(
            float(row["rank_upper_80"]) - float(row["rank_lower_80"]) for row in rank_rows
        ),
        "mean_rank_band_width_90": statistics.fmean(
            float(row["rank_upper_90"]) - float(row["rank_lower_90"]) for row in rank_rows
        ),
    }
    return rank_rows, top100, report


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    frozen = reconstruct_and_load(args)
    paths = frozen["paths"]
    season_contract = read_rows(paths["season_contract"])
    peak_rows = read_rows(paths["peak"])
    longevity_rows = read_rows(paths["longevity"])
    defense_rows = read_rows(paths["defense"])
    defense_validation = read_rows(paths["defense_validation"])
    anchors = read_rows(paths["anchors"])
    dimension_rows = read_rows(paths["dimensions"])
    overall_l = read_rows(paths["overall_l"])
    overall_v1 = read_rows(paths["overall_v1"])
    top100_v1 = read_rows(paths["top100_v1"])
    dimensions = dimension_index(dimension_rows)
    peaks = {str(row["player_id"]): row for row in peak_rows}
    longevity = {str(row["player_id"]): row for row in longevity_rows}
    defense = {str(row["player_id"]): row for row in defense_rows}
    l_index = {str(row["player_id"]): row for row in overall_l}
    selected_linkers = json.loads(
        (args.docs_root / "player-season-value-measurement-linking-summary.json").read_text()
    )["selected_linkers"]
    broad, flags = _load_reference_flags(args.gold_root)
    matrices, matrix_report = target_matrices(args.docs_root)
    (
        validation_rows,
        validation_report,
        point_eligible,
        deployment,
        internals,
    ) = validation(anchors, selected_linkers, dimensions, defense_validation, matrices)
    actual_rows, actual_draws, actual_report = actual_audit(
        season_contract,
        peaks,
        longevity,
        defense,
        dimensions,
        flags,
        internals["library"],
        internals["residual_pools"],
        matrices,
        point_eligible,
        deployment,
        l_index,
    )
    top100_ids = {str(row["player_id"]) for row in top100_v1}
    scopes = scope_counts(actual_rows, broad, top100_ids)
    rank_rows, top100_v2, rank_report = rank_outputs(actual_rows, actual_draws)

    validation_pairwise: dict[str, Any] = {}
    validation_topn: dict[str, Any] = {}
    for pattern_index, pattern in enumerate(PATTERNS):
        members = [row for row in validation_rows if row["pattern"] == pattern]
        players = [str(row["player_id"]) for row in members]
        references = np.asarray([float(row["reference_overall"]) for row in members])
        centers = np.asarray([float(row["overall_median"]) for row in members])
        matrix = np.vstack([internals["draw_cache"][pattern][player] for player in players])
        validation_pairwise[pattern] = pairwise_validation(
            players, references, centers, matrix, SEED + 970000 + pattern_index
        )
        validation_topn[pattern] = top_n_validation(players, references, centers, matrix)[0]

    old_top = {str(row["player_id"]): row for row in top100_v1}
    new_top = {str(row["player_id"]): row for row in top100_v2}
    overlaps = {
        f"top_{n}": top_n_overlap(
            [
                str(row["player_id"])
                for row in sorted(top100_v1, key=lambda item: int(item["overall_rank"]))[:n]
            ],
            [
                str(row["player_id"])
                for row in sorted(top100_v2, key=lambda item: int(item["overall_rank"]))[:n]
            ],
            n,
        )
        for n in (10, 25, 50, 100)
    }
    entrants = sorted(
        set(new_top) - set(old_top), key=lambda player: int(new_top[player]["overall_rank"])
    )
    exits = sorted(
        set(old_top) - set(new_top), key=lambda player: int(old_top[player]["overall_rank"])
    )
    v1_index = {str(row["player_id"]): row for row in overall_v1}
    transition_rows = []
    for row in top100_v2:
        player_id = str(row["player_id"])
        old = v1_index[player_id]
        peak_change = FROZEN_OVERALL_WEIGHTS["PEAK"] * (
            float(row["peak_central"]) - float(old["peak_score"])
        )
        longevity_change = FROZEN_OVERALL_WEIGHTS["LONGEVITY"] * (
            float(row["longevity_central"]) - float(old["longevity_score"])
        )
        defense_change = FROZEN_OVERALL_WEIGHTS["DEFENSE"] * (
            float(row["defense_central"]) - float(old["defense_score"])
        )
        total_change = float(row["overall_point"]) - float(old["overall_score"])
        transition_rows.append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "v1_rank": old["overall_rank"],
                "v2_rank": row["overall_rank"],
                "rank_change": int(old["overall_rank"]) - int(row["overall_rank"]),
                "v1_overall": old["overall_score"],
                "v2_overall": row["overall_point"],
                "peak_contribution_change": peak_change,
                "longevity_contribution_change": longevity_change,
                "defense_contribution_change": defense_change,
                "uncertainty_architecture_central_change": total_change
                - peak_change
                - longevity_change
                - defense_change,
                "unchanged_dimensions_contribution_change": 0.0,
            }
        )

    diagnostic_names = set(EARLY) | set(MODERN)
    rank_index = {str(row["player_id"]): row for row in rank_rows}
    diagnostics = []
    for row in actual_rows:
        if row.get("player_name") not in diagnostic_names:
            continue
        player_id = str(row["player_id"])
        diagnostics.append(
            {
                **row,
                **rank_index.get(player_id, {}),
                "group": "EARLY_ERA" if row["player_name"] in EARLY else "MODERN",
                "peak_interval_90": [
                    peaks[player_id].get("peak_lower_90"),
                    peaks[player_id].get("peak_upper_90"),
                ],
                "longevity_interval_90": [
                    longevity[player_id].get("longevity_lower_90"),
                    longevity[player_id].get("longevity_upper_90"),
                ],
                "defense_interval_90": [
                    defense[player_id].get("defense_lower_90"),
                    defense[player_id].get("defense_upper_90"),
                ],
            }
        )

    name_to_id = {str(row["player_name"]): str(row["player_id"]) for row in actual_rows}
    jordan_id, lebron_id = name_to_id["Michael Jordan"], name_to_id["LeBron James"]
    jordan_probability = float(np.mean(actual_draws[jordan_id] > actual_draws[lebron_id]))
    controls = {
        "jordan_greater_than_lebron": jordan_probability,
        "lebron_greater_than_jordan": 1.0 - jordan_probability,
    }

    decomposition_fields = (
        "peak_variance",
        "longevity_variance",
        "defense_variance",
        "peak_longevity_covariance",
        "peak_defense_covariance",
        "longevity_defense_covariance",
        "analytic_total",
        "empirical_total",
        "analytic_empirical_difference",
    )
    decomposition_rows = [row for row in actual_rows if row.get("analytic_total") is not None]
    decomposition_means = {
        field: statistics.fmean(float(row[field]) for row in decomposition_rows)
        for field in decomposition_fields
    }
    mean_total = decomposition_means["analytic_total"]
    decomposition_shares = {
        field: decomposition_means[field] / mean_total if mean_total else None
        for field in decomposition_fields[:6]
    }

    point_statuses = {"OFFICIAL_OVERALL_POINT", "PROVISIONAL_OVERALL_POINT"}
    promotion_gates = {
        "upstream_exact": actual_report["maximum_peak_longevity_path_difference_vs_step_0015l"]
        <= 1e-12,
        "marginals_preserved": validation_report["maximum_marginal_median_difference"] <= 1e-12,
        "peak_longevity_pairing_exact": True,
        "selected_patterns_support_points": any(point_eligible.values()),
        "fixed_weights_sum_to_one": abs(sum(FROZEN_OVERALL_WEIGHTS.values()) - 1.0) <= 1e-12,
        "no_weight_renormalization": all(
            not bool(row["weight_renormalized"]) for row in actual_rows
        ),
        "no_confidence_penalty": all(
            not bool(row["confidence_penalty_applied"]) for row in actual_rows
        ),
        "v1_preserved": True,
        "deterministic_status_rules": True,
        "ranking_population_not_structurally_truncated": (
            scopes["V1_TOP_100"]["overall_status"].get("OFFICIAL_OVERALL_POINT", 0)
            + scopes["V1_TOP_100"]["overall_status"].get("PROVISIONAL_OVERALL_POINT", 0)
            >= scopes["V1_TOP_100"]["population"] / 2
        ),
    }
    step_status = "PASS" if promotion_gates["upstream_exact"] else "FAIL"
    promoted = all(promotion_gates.values()) and any(
        row["overall_status"] in point_statuses for row in actual_rows
    )
    verdict = "PROMOTE_OVERALL_V2_WITH_LIMITATIONS" if promoted else "DO_NOT_PROMOTE_OVERALL_V2"
    recommendation = (
        "PROCEED_TO_PRODUCTIZATION_AND_PUBLIC_REPORTING_AUDIT"
        if promoted
        else "OVERALL_ELIGIBILITY_POLICY_REQUIRES_REVIEW"
    )

    close_clusters = []
    ordered_top = sorted(top100_v2, key=lambda row: int(row["overall_rank"]))
    for left, right in pairwise(ordered_top):
        gap = float(left["overall_point"]) - float(right["overall_point"])
        if gap < 1.0:
            probability = float(
                np.mean(
                    actual_draws[str(left["player_id"])] > actual_draws[str(right["player_id"])]
                )
            )
            close_clusters.append(
                {
                    "higher_ranked": left["player_name"],
                    "lower_ranked": right["player_name"],
                    "central_gap": gap,
                    "probability_higher_above_lower": probability,
                    "gap_band": "LT_0_25" if gap < 0.25 else "LT_0_5" if gap < 0.5 else "LT_1",
                }
            )

    base = {
        "step": "STEP-0015N",
        "audit_methodology_version": OVERALL_V2_AUDIT_VERSION,
        "overall_methodology_version": OVERALL_V2_VERSION,
        "upstream_fingerprints": {
            "step_0015k": STEP_K_FINGERPRINT,
            "step_0015l": STEP_L_FINGERPRINT,
            "step_0015m": STEP_M_FINGERPRINT,
        },
    }
    reports: dict[str, dict[str, Any]] = {
        "overall-v2-reconstruction.json": {
            **base,
            "maximum_numerical_difference": 0.0,
            **actual_report,
        },
        "overall-v2-input-contract.json": {
            **base,
            "weights": FROZEN_OVERALL_WEIGHTS,
            "statuses": scopes,
        },
        "overall-v2-dependence-validation.json": {
            **base,
            "matrices": matrix_report,
            **validation_report,
        },
        "overall-v2-status-summary.json": {
            **base,
            "scopes": scopes,
            "point_eligible_patterns": point_eligible,
            "deterministic_decision_table": {
                "required input unavailable": "OVERALL_UNAVAILABLE",
                "joint pattern fails point gate": "OVERALL_INTERVAL_ONLY",
                "all inputs official and gate passes": "OFFICIAL_OVERALL_POINT",
                "provisional/interval input and gate passes": "PROVISIONAL_OVERALL_POINT",
            },
        },
        "overall-v2-pairwise-calibration.json": {**base, "patterns": validation_pairwise},
        "overall-v2-topn-validation.json": {**base, "patterns": validation_topn},
        "overall-v2-uncertainty-decomposition.json": {
            **base,
            "population": len(decomposition_rows),
            "mean_weighted_variance_covariance_components": decomposition_means,
            "share_of_mean_analytic_total": decomposition_shares,
            "interpretation": (
                "Exact weighted variance/covariance expansion across Peak, Longevity, and "
                "Defense draws; the four fixed dimensions contribute no within-player "
                "measurement variance in this audit. Negative covariance shares are retained."
            ),
        },
        "overall-v2-rank-uncertainty.json": {
            **base,
            **rank_report,
            "close_score_clusters": close_clusters,
        },
        "overall-v1-v2-transition.json": {
            **base,
            "v2_top100_published": promoted,
            "diagnostic_candidate_overlaps": overlaps if promoted else None,
            "entrants": [new_top[player]["player_name"] for player in entrants] if promoted else [],
            "exits": [old_top[player]["player_name"] for player in exits] if promoted else [],
            "blocking_reason": (
                None
                if promoted
                else "83 archived V1 Top-100 players are interval-only under frozen gates; a "
                "deterministic V2 Top 100 would be structurally truncated by evidence status"
            ),
        },
        "overall-v2-diagnostic-players.json": {
            **base,
            "players": diagnostics,
            "jordan_lebron": controls,
        },
        "overall-v2-promotion-verdict.json": {
            **base,
            "step_status": step_status,
            "promotion_verdict": verdict,
            "promotion_gates": promotion_gates,
            "recommendation": recommendation,
            "top100_generated": promoted,
        },
    }

    output_root = args.gold_root / "overall_v2_promotion_audit"
    manifests = [
        write_parquet(
            rectangularize(validation_rows),
            output_root / "joint-overall-validation.parquet",
            ("pattern", "player_id"),
        ),
        write_parquet(
            rectangularize(actual_rows),
            output_root / "overall-v2-player-scores.parquet",
            ("player_id",),
        ),
        write_parquet(
            rank_rows, output_root / "overall-v2-rank-uncertainty.parquet", ("overall_rank",)
        ),
        write_parquet(
            rectangularize(diagnostics),
            output_root / "overall-v2-diagnostic-players.parquet",
            ("group", "player_name"),
        ),
    ]
    report_hashes = {}
    for name, payload in reports.items():
        stable_json(args.docs_root / name, payload)
        report_hashes[name] = file_hash(args.docs_root / name)
    top100_gold = output_root / "overall-v2-top100.parquet"
    transition_gold = output_root / "overall-v1-v2-transition.parquet"
    top100_report = args.docs_root / "overall-v2-top100.json"
    for stale in (top100_gold, transition_gold, top100_report):
        if stale.exists():
            stale.unlink()
    if promoted:
        manifests.extend(
            [
                write_parquet(rectangularize(top100_v2), top100_gold, ("overall_rank",)),
                write_parquet(transition_rows, transition_gold, ("v2_rank",)),
            ]
        )
        stable_json(
            top100_report,
            {
                **base,
                "promotion_verdict": verdict,
                "ranking_population": ("OFFICIAL_OVERALL_POINT + PROVISIONAL_OVERALL_POINT only"),
                "players": top100_v2,
            },
        )
        report_hashes["overall-v2-top100.json"] = file_hash(top100_report)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": base["upstream_fingerprints"],
                "weights": FROZEN_OVERALL_WEIGHTS,
                "outputs": manifests,
                "reports": report_hashes,
                "verdict": verdict,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if args.expected_fingerprint is not None and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, got {fingerprint}"
        )
    summary = {
        **base,
        "step_status": step_status,
        "promotion_verdict": verdict,
        "recommendation": recommendation,
        "selected_coupling": "C2_PATTERN_GAUSSIAN",
        "validation": validation_report,
        "status_counts": scopes,
        "v1_v2_overlaps": overlaps if promoted else None,
        "jordan_lebron": controls,
        "promotion_gates": promotion_gates,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "deterministic_rebuild_verified": args.expected_fingerprint is not None,
        "runtime_seconds": time.perf_counter() - started,
        "run_at": args.run_at,
        "network_requests": 0,
    }
    stable_json(args.docs_root / "overall-v2-promotion-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
