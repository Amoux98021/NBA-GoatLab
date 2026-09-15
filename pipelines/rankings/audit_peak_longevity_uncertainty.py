#!/usr/bin/env python3
"""Run the offline STEP-0015I Peak/Longevity uncertainty propagation audit."""

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

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.measurement_linking import (
    LinkMethod,
    cross_fitted_predictions,
)
from goatlab.rankings.peak_forensics import correlation
from goatlab.rankings.uncertainty_aggregation import (
    LONGEVITY_WEIGHTS,
    PEAK_THREE_YEAR_WEIGHT,
    fixed_midrank_ecdf,
    longevity_components,
    longevity_score_draws,
    peak_draws,
    quantile_interval,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet
from pipelines.rankings.audit_player_season_value import season_inputs
from pipelines.rankings.audit_player_season_value_measurement_linking import (
    FORMS,
    _arrays,
    _folds,
    apply_architecture,
    build_anchors,
    interval_diagnostics,
    linking_audit,
    split_conformal,
)
from pipelines.rankings.audit_player_season_value_v2_promotion import reconstruction

ROOT = Path(__file__).resolve().parents[2]
STEP_H_FINGERPRINT = "4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54"
LINKED_SEASON_HASH = "2908de32b614b96e405630334e07aeb262d690536c0c33fc7fe77b6f51ff6dc4"
ANCHOR_HASH = "1821e4d7a15fccb70819f49d234f019ce75cba06613a86c80cc07e04fb8d202a"
AUDIT_VERSION = "goatlab-v1-peak-longevity-uncertainty-audit-v1"
PEAK_VERSION = "goatlab-v1-peak-v2-uncertainty-research"
LONGEVITY_VERSION = "goatlab-v1-longevity-v2-uncertainty-research"
RUN_AT_DEFAULT = "2026-09-15T20:00:00Z"
SEED = 1515009
FINAL_DRAWS = 2500
PATTERNS = (
    "FULL_REFERENCE",
    "NO_PRESENCE_CAREER",
    "TRADITIONAL_CAREER",
    "EARLY_TRADITIONAL_TO_EXPANDED",
    "PARTIAL_PRESENCE_LATE",
    "MIXED_PROVISIONAL_INTERVAL",
)
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
    "Stephen Curry",
    "Shaquille O'Neal",
    "Tim Duncan",
    "Kevin Garnett",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
    "Rudy Gobert",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _rectangularize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill absent optional fields so Arrow retains the complete row contract."""
    columns = sorted({column for row in rows for column in row})
    return [{column: row.get(column) for column in columns} for row in rows]


def _compare_rows(
    rebuilt: list[dict[str, Any]],
    stored: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    index = {(str(row["player_id"]), int(row["season_id"])): row for row in stored}
    mismatches = 0
    maximum = 0.0
    for row in rebuilt:
        other = index.get((str(row["player_id"]), int(row["season_id"])))
        if other is None:
            mismatches += 1
            continue
        for field in fields:
            left, right = row.get(field), other.get(field)
            if left is None or right is None:
                mismatches += int(left is not right)
            elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
                difference = abs(float(left) - float(right))
                maximum = max(maximum, difference)
                mismatches += int(difference > 1e-12)
            else:
                mismatches += int(left != right)
    return {"mismatches": mismatches, "maximum_numerical_difference": maximum}


def reconstruct_step_h(
    args: argparse.Namespace,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, str],
    dict[str, Any],
]:
    summary = json.loads(
        (args.docs_root / "player-season-value-measurement-linking-summary.json").read_text()
    )
    if summary.get("output_fingerprint") != STEP_H_FINGERPRINT:
        raise ValueError("STEP-0015H fingerprint mismatch")
    linked_path = (
        args.gold_root
        / "player_season_value_measurement_linking_audit/linked-season-measurements.parquet"
    )
    anchor_path = (
        args.gold_root / "player_season_value_measurement_linking_audit/anchor-masked-pairs.parquet"
    )
    if file_hash(linked_path) != LINKED_SEASON_HASH or file_hash(anchor_path) != ANCHOR_HASH:
        raise ValueError("STEP-0015H frozen artifact mismatch")

    base_rows, _ = season_inputs(args.gold_root)
    facts = read_rows(
        args.silver_root / "historical_player_season_facts_v2_research/part-00000.parquet"
    )
    candidates, recovered_inputs, candidate_reconstruction = reconstruction(args, base_rows, facts)
    anchors = build_anchors(recovered_inputs, candidates)
    _, selected = linking_audit(anchors)
    interval_metrics: dict[str, Any] = {}
    for form in FORMS:
        method = cast(LinkMethod, selected[form])
        _, _, calibrated = split_conformal(anchors, form, method)
        calibrated["point_eligible"] = bool(summary["calibration"][form]["point_eligible"])
        calibrated["radii"] = summary["calibration"][form]["radii"]
        interval_metrics[form] = calibrated
    rebuilt = apply_architecture(recovered_inputs, candidates, anchors, selected, interval_metrics)
    stored = read_rows(linked_path)
    comparison = _compare_rows(
        rebuilt,
        stored,
        (
            "raw_candidate_d_score",
            "linked_point_estimate",
            "interval_center",
            "lower_80",
            "upper_80",
            "lower_90",
            "upper_90",
            "lower_95",
            "upper_95",
            "score_status",
            "measurement_form",
            "evidence_regime",
        ),
    )
    if comparison["mismatches"]:
        raise ValueError("STEP-0015H linked measurement reconstruction failed")
    preliminary_peak, preliminary_longevity = interval_diagnostics(rebuilt)
    comparison.update(
        {
            "silver_rows": len(facts),
            "season_rows": len(rebuilt),
            "anchor_rows": len(anchors),
            "raw_candidate_d_mismatches": candidate_reconstruction["raw_mismatches"],
            "candidate_d_maximum_difference": candidate_reconstruction["maximum_raw_difference"],
            "preliminary_peak_players": preliminary_peak["players"],
            "preliminary_longevity_players": preliminary_longevity["players"],
            "frozen_linked_sha256": file_hash(linked_path),
            "frozen_anchor_sha256": file_hash(anchor_path),
        }
    )
    return rebuilt, anchors, recovered_inputs, selected, comparison


def _mode(values: list[str]) -> str:
    return Counter(values).most_common(1)[0][0] if values else "UNKNOWN"


def residual_library(
    anchors: list[dict[str, Any]], selected: dict[str, str]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any]]:
    residuals: dict[str, np.ndarray] = {}
    points: dict[str, np.ndarray] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        estimate = cross_fitted_predictions(
            cast(LinkMethod, selected[form]), x, y, _folds(anchors, "grouped_player"), roles
        )
        points[form] = estimate
        residuals[form] = y - estimate
    return (
        residuals,
        points,
        {
            "semantics": "FULL_PORTABLE_REFERENCE_MINUS_GROUPED_PLAYER_OOF_LINKED_FORM",
            "full_portable_uncertainty_proxy": "NO_TEAM_CONTEXT_EMPIRICAL_SENSITIVITY",
            "normal_distribution_assumed": False,
        },
    )


def residual_dependence(
    anchors: list[dict[str, Any]],
    residuals: dict[str, np.ndarray],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    teams = {
        (str(row["player_id"]), int(row["season_id"])): str(row.get("primary_team_id") or "")
        for row in source_rows
    }
    by_player: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(anchors):
        by_player[str(row["player_id"])].append(index)
    report: dict[str, Any] = {}
    for form in FORMS:
        values = residuals[form]
        adjacent_left: list[float] = []
        adjacent_right: list[float] = []
        same_team_left: list[float] = []
        same_team_right: list[float] = []
        changed_team_left: list[float] = []
        changed_team_right: list[float] = []
        player_means: list[float] = []
        for player_id, indices in by_player.items():
            ordered = sorted(indices, key=lambda idx: int(anchors[idx]["season_id"]))
            player_means.append(float(np.mean(values[ordered])))
            for left, right in pairwise(ordered):
                if int(anchors[right]["season_id"]) != int(anchors[left]["season_id"]) + 1:
                    continue
                adjacent_left.append(float(values[left]))
                adjacent_right.append(float(values[right]))
                left_team = teams.get((player_id, int(anchors[left]["season_id"])))
                right_team = teams.get((player_id, int(anchors[right]["season_id"])))
                if left_team and left_team == right_team:
                    same_team_left.append(float(values[left]))
                    same_team_right.append(float(values[right]))
                elif left_team and right_team:
                    changed_team_left.append(float(values[left]))
                    changed_team_right.append(float(values[right]))
        total_variance = float(np.var(values))
        report[form] = {
            "players": len(by_player),
            "season_residual_sd": float(np.std(values)),
            "player_mean_sd": float(np.std(player_means)),
            "player_effect_variance_share": (
                float(np.var(player_means) / total_variance) if total_variance else 0.0
            ),
            "adjacent_pairs": len(adjacent_left),
            "adjacent_correlation": correlation(adjacent_left, adjacent_right),
            "same_team_adjacent_pairs": len(same_team_left),
            "same_team_adjacent_correlation": correlation(same_team_left, same_team_right),
            "changed_team_adjacent_pairs": len(changed_team_left),
            "changed_team_adjacent_correlation": correlation(changed_team_left, changed_team_right),
        }
    return report


def donor_library(
    anchors: list[dict[str, Any]], residuals: dict[str, np.ndarray]
) -> dict[str, Any]:
    forms = tuple(FORMS)
    form_index = {form: index for index, form in enumerate(forms)}
    by_player: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(anchors):
        by_player[str(row["player_id"])].append(index)
    players = sorted(by_player)
    maximum = max(len(indices) for indices in by_player.values())
    matrix = np.zeros((len(players), maximum, len(forms)), dtype=float)
    roles: list[str] = []
    archetype_sets: list[set[str]] = []
    bands: list[int] = []
    for player_index, player_id in enumerate(players):
        indices = sorted(by_player[player_id], key=lambda idx: int(anchors[idx]["season_id"]))
        roles.append(_mode([str(anchors[idx]["role"]) for idx in indices]))
        labels = {
            label for idx in indices for label in json.loads(str(anchors[idx]["archetypes_json"]))
        }
        archetype_sets.append(labels)
        mean_score = np.mean([float(anchors[idx]["full_score"]) for idx in indices])
        bands.append(min(3, int(mean_score // 25)))
        for position in range(maximum):
            source_index = indices[position % len(indices)]
            for form, column in form_index.items():
                matrix[player_index, position, column] = residuals[form][source_index]
    pools = {
        role: np.asarray([i for i, item in enumerate(roles) if item == role]) for role in set(roles)
    }
    return {
        "forms": forms,
        "form_index": form_index,
        "players": players,
        "matrix": matrix,
        "roles": roles,
        "archetypes": archetype_sets,
        "bands": np.asarray(bands),
        "pools": pools,
        "maximum": maximum,
        "pooled": {form: residuals[form] for form in forms},
    }


def simulate_seasons(
    centers: np.ndarray,
    forms: list[str],
    role: str,
    archetypes: set[str],
    method: str,
    draws: int,
    seed: int,
    library: dict[str, Any],
) -> np.ndarray:
    """Draw empirical errors; no normal distribution or missing-stat imputation."""
    rng = np.random.default_rng(seed)
    mapped_forms = ["NO_TEAM_CONTEXT" if form == "FULL_PORTABLE" else form for form in forms]
    output = np.repeat(np.asarray(centers, dtype=float)[None, :], draws, axis=0)
    if method == "U0_INDEPENDENT":
        for column, form in enumerate(mapped_forms):
            pool = cast(np.ndarray, library["pooled"][form])
            output[:, column] += pool[rng.integers(0, pool.size, draws)]
        return np.clip(output, 0.0, 100.0)

    all_donors = np.arange(len(library["players"]))
    donors = all_donors
    if method in {"U2_ROLE_BLOCK", "U3_STRATIFIED_BLOCK"}:
        role_pool = library["pools"].get(role)
        if role_pool is not None and role_pool.size >= 50:
            donors = role_pool
    if method == "U3_STRATIFIED_BLOCK":
        band = min(3, int(float(np.mean(centers)) // 25))
        filtered = np.asarray(
            [
                index
                for index in donors.tolist()
                if abs(int(library["bands"][index]) - band) <= 1
                and (
                    not archetypes
                    or bool(archetypes & cast(list[set[str]], library["archetypes"])[index])
                )
            ],
            dtype=int,
        )
        if filtered.size >= 50:
            donors = filtered
    chosen = donors[rng.integers(0, donors.size, draws)]
    starts = rng.integers(0, int(library["maximum"]), draws)
    matrix = cast(np.ndarray, library["matrix"])
    form_index = cast(dict[str, int], library["form_index"])
    maximum = int(library["maximum"])
    for column, form in enumerate(mapped_forms):
        output[:, column] += matrix[
            chosen,
            (starts + column) % maximum,
            form_index[form],
        ]
    return np.clip(output, 0.0, 100.0)


def _pattern_forms(pattern: str, count: int) -> list[str]:
    if pattern == "FULL_REFERENCE":
        return ["FULL_PORTABLE"] * count
    if pattern == "NO_PRESENCE_CAREER":
        return ["EXPANDED_NO_PRESENCE"] * count
    if pattern == "TRADITIONAL_CAREER":
        return ["TRADITIONAL_BOX"] * count
    if pattern == "EARLY_TRADITIONAL_TO_EXPANDED":
        split = max(1, count // 2)
        return ["TRADITIONAL_BOX"] * split + ["EXPANDED_NO_PRESENCE"] * (count - split)
    if pattern == "PARTIAL_PRESENCE_LATE":
        split = max(1, count // 2)
        return ["EXPANDED_NO_PRESENCE"] * split + ["EXPANDED_PROXY_ACTION_WITH_PRESENCE"] * (
            count - split
        )
    if pattern == "MIXED_PROVISIONAL_INTERVAL":
        cycle = (
            "TRADITIONAL_BOX",
            "TRADITIONAL_WITH_PRESENCE",
            "EXPANDED_NO_PRESENCE",
            "EXPANDED_PROXY_ACTION_WITH_PRESENCE",
        )
        return [cycle[index % len(cycle)] for index in range(count)]
    raise ValueError(pattern)


def _central_components(values: np.ndarray, seasons: np.ndarray) -> tuple[float, float, float]:
    components = longevity_components(values[None, :], seasons)
    return (
        float(components.breadth[0]),
        float(components.capped_area[0]),
        float(components.longest_run[0]),
    )


def build_scales(
    careers: dict[str, list[dict[str, Any]]], reference_players: set[str]
) -> dict[str, np.ndarray]:
    peak_raw: dict[str, float] = {}
    components: dict[str, tuple[float, float, float]] = {}
    for player_id, rows in careers.items():
        ordered = sorted(rows, key=lambda row: int(row["season_id"]))
        values = np.asarray([float(row["center"]) for row in ordered])
        seasons = np.asarray([int(row["season_id"]) for row in ordered])
        peak = peak_draws(values[None, :], seasons)
        if peak.values.size:
            peak_raw[player_id] = float(peak.values[0])
        components[player_id] = _central_components(values, seasons)
    eligible = sorted(set(careers) & reference_players)
    breadth_reference = np.asarray([components[player][0] for player in eligible])
    area_reference = np.asarray([components[player][1] for player in eligible])
    run_reference = np.asarray([components[player][2] for player in eligible])
    longevity_raw: list[float] = []
    for player in eligible:
        breadth, area, run = components[player]
        longevity_raw.append(
            LONGEVITY_WEIGHTS[0]
            * float(fixed_midrank_ecdf(breadth_reference, np.asarray([breadth]))[0])
            + LONGEVITY_WEIGHTS[1]
            * float(fixed_midrank_ecdf(area_reference, np.asarray([area]))[0])
            + LONGEVITY_WEIGHTS[2] * float(fixed_midrank_ecdf(run_reference, np.asarray([run]))[0])
        )
    return {
        "peak": np.asarray([peak_raw[player] for player in eligible if player in peak_raw]),
        "breadth": breadth_reference,
        "area": area_reference,
        "run": run_reference,
        "longevity": np.asarray(longevity_raw),
        "reference_players": np.asarray(eligible),
    }


def aggregate_draws(
    draws: np.ndarray, seasons: np.ndarray, scales: dict[str, np.ndarray]
) -> tuple[np.ndarray, np.ndarray, Any, Any]:
    peak = peak_draws(draws, seasons)
    peak_scores = (
        fixed_midrank_ecdf(scales["peak"], peak.values)
        if peak.values.size
        else np.asarray([], dtype=float)
    )
    components = longevity_components(draws, seasons)
    longevity_scores = longevity_score_draws(
        components,
        scales["breadth"],
        scales["area"],
        scales["run"],
        scales["longevity"],
    )
    return peak_scores, longevity_scores, peak, components


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
        "gt_5": float(np.mean(np.abs(residual) > 5.0)),
        "gt_10": float(np.mean(np.abs(residual) > 10.0)),
    }


def _gate(metrics: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    gates = {
        "mae_lte_5": float(metrics["mae"]) <= 5.0,
        "spearman_gte_095": float(metrics["spearman"]) >= 0.95,
        "absolute_bias_lte_2": abs(float(metrics["bias"])) <= 2.0,
        "gt_10_lte_015": float(metrics["gt_10"]) <= 0.15,
        "interval_90_calibrated": 0.87 <= float(metrics["coverage_90"]) <= 0.93,
    }
    return all(gates.values()), gates


def _validation_careers(
    anchors: list[dict[str, Any]], points: dict[str, np.ndarray]
) -> dict[str, list[dict[str, Any]]]:
    careers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(anchors):
        careers[str(row["player_id"])].append(
            {
                **row,
                "center": float(row["full_score"]),
                "linked_by_form": {form: float(points[form][index]) for form in FORMS},
            }
        )
    return {
        player_id: sorted(rows, key=lambda row: int(row["season_id"]))
        for player_id, rows in careers.items()
        if len(rows) >= 5
        and peak_draws(
            np.asarray([[float(row["full_score"]) for row in rows]]),
            np.asarray([int(row["season_id"]) for row in rows]),
        ).values.size
    }


def _reference_scores(
    careers: dict[str, list[dict[str, Any]]], scales: dict[str, np.ndarray]
) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for player_id, rows in careers.items():
        values = np.asarray([[float(row["full_score"]) for row in rows]])
        seasons = np.asarray([int(row["season_id"]) for row in rows])
        peak, longevity, _, _ = aggregate_draws(values, seasons, scales)
        output[player_id] = {"peak": float(peak[0]), "longevity": float(longevity[0])}
    return output


def propagation_comparison(
    careers: dict[str, list[dict[str, Any]]],
    scales: dict[str, np.ndarray],
    library: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Compare U0-U3 on a deterministic career subset before final validation."""
    reference = _reference_scores(careers, scales)
    selected_players = sorted(careers)[: min(300, len(careers))]
    methods = (
        "U0_INDEPENDENT",
        "U1_PLAYER_BLOCK",
        "U2_ROLE_BLOCK",
        "U3_STRATIFIED_BLOCK",
    )
    report: dict[str, Any] = {}
    for method in methods:
        dimensions: dict[str, dict[str, list[float]]] = {
            "peak": defaultdict(list),
            "longevity": defaultdict(list),
        }
        for player_index, player_id in enumerate(selected_players):
            rows = careers[player_id]
            forms = _pattern_forms("MIXED_PROVISIONAL_INTERVAL", len(rows))
            centers = np.asarray(
                [float(row["linked_by_form"][form]) for row, form in zip(rows, forms, strict=True)]
            )
            role = _mode([str(row["role"]) for row in rows])
            labels = {label for row in rows for label in json.loads(str(row["archetypes_json"]))}
            draws = simulate_seasons(
                centers,
                forms,
                role,
                labels,
                method,
                300,
                SEED + player_index,
                library,
            )
            seasons = np.asarray([int(row["season_id"]) for row in rows])
            peak, longevity, _, _ = aggregate_draws(draws, seasons, scales)
            for dimension, values in (("peak", peak), ("longevity", longevity)):
                lower, upper = quantile_interval(values, 0.90)
                dimensions[dimension]["reference"].append(reference[player_id][dimension])
                dimensions[dimension]["central"].append(float(np.median(values)))
                dimensions[dimension]["covered"].append(
                    float(lower <= reference[player_id][dimension] <= upper)
                )
                dimensions[dimension]["width"].append(upper - lower)
        report[method] = {}
        for dimension, values in dimensions.items():
            metrics = _summary(values["reference"], values["central"])
            metrics["coverage_90"] = statistics.fmean(values["covered"])
            metrics["mean_width_90"] = statistics.fmean(values["width"])
            report[method][dimension] = metrics
    # Aggregate calibration is primary; dependence-preserving simplicity breaks close ties.
    selected = min(
        methods[1:],
        key=lambda method: (
            abs(float(report[method]["peak"]["coverage_90"]) - 0.90)
            + abs(float(report[method]["longevity"]["coverage_90"]) - 0.90),
            float(report[method]["peak"]["mean_width_90"])
            + float(report[method]["longevity"]["mean_width_90"]),
            methods.index(method),
        ),
    )
    return {
        "population": len(selected_players),
        "pattern": "MIXED_PROVISIONAL_INTERVAL",
        "draws": 300,
        "methods": report,
        "selected": selected,
        "selection_rule": (
            "closest joint 90% aggregate coverage, then narrower intervals; independent U0 "
            "is baseline-only and cannot be selected when within-career dependence is observed"
        ),
    }, selected


def convergence_audit(
    careers: dict[str, list[dict[str, Any]]],
    scales: dict[str, np.ndarray],
    library: dict[str, Any],
    method: str,
) -> dict[str, Any]:
    players = sorted(careers)[: min(120, len(careers))]
    levels = (300, 1000, 2500)
    records: dict[int, dict[str, list[float]]] = {level: defaultdict(list) for level in levels}
    for player_index, player_id in enumerate(players):
        rows = careers[player_id]
        forms = _pattern_forms("MIXED_PROVISIONAL_INTERVAL", len(rows))
        centers = np.asarray(
            [float(row["linked_by_form"][form]) for row, form in zip(rows, forms, strict=True)]
        )
        role = _mode([str(row["role"]) for row in rows])
        labels = {label for row in rows for label in json.loads(str(row["archetypes_json"]))}
        seasons = np.asarray([int(row["season_id"]) for row in rows])
        for draw_count in levels:
            draws = simulate_seasons(
                centers,
                forms,
                role,
                labels,
                method,
                draw_count,
                SEED + 10000 + player_index,
                library,
            )
            peak, longevity, peak_details, components = aggregate_draws(draws, seasons, scales)
            for label, values in (("peak", peak), ("longevity", longevity)):
                lower, upper = quantile_interval(values, 0.90)
                records[draw_count][f"{label}_median"].append(float(np.median(values)))
                records[draw_count][f"{label}_lower"].append(lower)
                records[draw_count][f"{label}_upper"].append(upper)
            if peak_details.window_indices.size:
                counts = np.bincount(
                    peak_details.window_indices, minlength=len(peak_details.windows)
                )
                records[draw_count]["best_window_probability"].append(
                    float(np.max(counts) / draw_count)
                )
            records[draw_count]["mean_p80_probability"].append(
                float(np.mean(components.breadth / max(len(rows), 1)))
            )
            records[draw_count]["mean_p90_area"].append(
                float(np.mean(components.capped_area / max(len(rows), 1)))
            )
    reference = records[2500]
    output: dict[str, Any] = {"players": len(players), "selected_draws": FINAL_DRAWS}
    for draw_count in levels:
        output[str(draw_count)] = {
            field: {
                "mean_absolute_difference_vs_2500": float(
                    np.mean(np.abs(np.asarray(values) - np.asarray(reference[field])))
                ),
                "maximum_absolute_difference_vs_2500": float(
                    np.max(np.abs(np.asarray(values) - np.asarray(reference[field])))
                ),
            }
            for field, values in records[draw_count].items()
        }
    return output


def masked_career_validation(
    careers: dict[str, list[dict[str, Any]]],
    scales: dict[str, np.ndarray],
    library: dict[str, Any],
    method: str,
    draws: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reference = _reference_scores(careers, scales)
    rows_out: list[dict[str, Any]] = []
    for player_index, player_id in enumerate(sorted(careers)):
        rows = careers[player_id]
        seasons = np.asarray([int(row["season_id"]) for row in rows])
        full_values = np.asarray([float(row["full_score"]) for row in rows])
        full_peak = peak_draws(full_values[None, :], seasons)
        true_window = (
            "-".join(
                str(seasons[index]) for index in full_peak.windows[full_peak.window_indices[0]]
            )
            if full_peak.values.size
            else None
        )
        role = _mode([str(row["role"]) for row in rows])
        labels = {label for row in rows for label in json.loads(str(row["archetypes_json"]))}
        for pattern_index, pattern in enumerate(PATTERNS):
            forms = _pattern_forms(pattern, len(rows))
            centers = np.asarray(
                [
                    float(row["full_score"])
                    if form == "FULL_PORTABLE"
                    else float(row["linked_by_form"][form])
                    for row, form in zip(rows, forms, strict=True)
                ]
            )
            sampled = simulate_seasons(
                centers,
                forms,
                role,
                labels,
                method,
                draws,
                SEED + player_index * 17 + pattern_index,
                library,
            )
            peak_values, longevity_values, peak_details, _ = aggregate_draws(
                sampled, seasons, scales
            )
            central_peak = peak_draws(centers[None, :], seasons)
            central_window = (
                "-".join(
                    str(seasons[index])
                    for index in central_peak.windows[central_peak.window_indices[0]]
                )
                if central_peak.values.size
                else None
            )
            window_counts = np.bincount(
                peak_details.window_indices, minlength=len(peak_details.windows)
            )
            supported_index = int(np.argmax(window_counts))
            supported_window = "-".join(
                str(seasons[index]) for index in peak_details.windows[supported_index]
            )
            item: dict[str, Any] = {
                "player_id": player_id,
                "pattern": pattern,
                "role": role,
                "career_seasons": len(rows),
                "reference_peak": reference[player_id]["peak"],
                "reference_longevity": reference[player_id]["longevity"],
                "naive_peak": float(fixed_midrank_ecdf(scales["peak"], central_peak.values)[0]),
                "peak_central": float(np.median(peak_values)),
                "longevity_central": float(np.median(longevity_values)),
                "true_peak_window": true_window,
                "naive_peak_window": central_window,
                "supported_peak_window": supported_window,
                "supported_window_probability": float(window_counts[supported_index] / draws),
                "method": method,
                "draws": draws,
            }
            for dimension, values in (("peak", peak_values), ("longevity", longevity_values)):
                for level in (0.80, 0.90, 0.95):
                    lower, upper = quantile_interval(values, level)
                    suffix = str(int(level * 100))
                    item[f"{dimension}_lower_{suffix}"] = lower
                    item[f"{dimension}_upper_{suffix}"] = upper
                    item[f"{dimension}_covered_{suffix}"] = (
                        lower <= reference[player_id][dimension] <= upper
                    )
            rows_out.append(item)

    report: dict[str, Any] = {"population": len(careers), "draws": draws, "patterns": {}}
    for pattern in PATTERNS:
        members = [row for row in rows_out if row["pattern"] == pattern]
        pattern_report: dict[str, Any] = {}
        for dimension in ("peak", "longevity"):
            metrics = _summary(
                [float(row[f"reference_{dimension}"]) for row in members],
                [float(row[f"{dimension}_central"]) for row in members],
            )
            for level in (80, 90, 95):
                metrics[f"coverage_{level}"] = statistics.fmean(
                    float(row[f"{dimension}_covered_{level}"]) for row in members
                )
                metrics[f"mean_width_{level}"] = statistics.fmean(
                    float(row[f"{dimension}_upper_{level}"])
                    - float(row[f"{dimension}_lower_{level}"])
                    for row in members
                )
            eligible, gates = _gate(metrics)
            metrics["point_eligible"] = eligible
            metrics["gates"] = gates
            if dimension == "peak":
                metrics["naive_window_accuracy"] = statistics.fmean(
                    float(row["naive_peak_window"] == row["true_peak_window"]) for row in members
                )
                metrics["simulation_window_accuracy"] = statistics.fmean(
                    float(row["supported_peak_window"] == row["true_peak_window"])
                    for row in members
                )
                metrics["naive_max_bias"] = statistics.fmean(
                    float(row["naive_peak"]) - float(row["reference_peak"]) for row in members
                )
            pattern_report[dimension] = metrics
        report["patterns"][pattern] = pattern_report
    return rows_out, report


def _load_reference_flags(gold_root: Path) -> tuple[set[str], dict[str, dict[str, Any]]]:
    rows = read_rows(
        gold_root / "dimension_candidate_scores/dimension=PEAK/candidate=PEAK-A/part-00000.parquet"
    )
    flags: dict[str, dict[str, Any]] = {}
    for row in rows:
        player_id = str(row["player_id"])
        if player_id not in flags:
            flags[player_id] = json.loads(str(row["analytical_population_flags"]))
    return {
        player_id for player_id, values in flags.items() if bool(values.get("BROAD_HIGH_RECALL"))
    }, flags


def _career_metadata(gold_root: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for path in sorted((gold_root / "player_career_summary").glob("bucket=*/part-*.parquet")):
        for row in read_rows(path):
            output[str(row["player_id"])] = row
    return output


def actual_careers(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("interval_center") is not None:
            grouped[str(row["player_id"])].append({**row, "center": float(row["interval_center"])})
    return {
        player_id: sorted(items, key=lambda row: int(row["season_id"]))
        for player_id, items in grouped.items()
    }


def _window_label(seasons: np.ndarray, indices: tuple[int, int, int]) -> str:
    return "-".join(str(int(seasons[index])) for index in indices)


def aggregate_actual(
    careers: dict[str, list[dict[str, Any]]],
    all_players: list[str],
    scales: dict[str, np.ndarray],
    library: dict[str, Any],
    method: str,
    metadata: dict[str, dict[str, Any]],
    validation: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    peak_rows: list[dict[str, Any]] = []
    longevity_rows: list[dict[str, Any]] = []
    dependence = {
        "simulation_method": method,
        "draws": FINAL_DRAWS,
        "peak_architecture": "70% best complete contiguous 3-year + 30% apex",
        "longevity_architecture": "35% P80 breadth + 40% capped P80-P90 area + 25% longest P80 run",
    }
    for player_index, player_id in enumerate(all_players):
        rows = careers.get(player_id, [])
        career = metadata.get(player_id, {})
        shared = {
            "player_id": player_id,
            "player_name": career.get("display_name"),
            "career_status": career.get("career_status", "INDETERMINATE"),
            "active_career_status": (
                "TO_DATE_NO_PROJECTION"
                if bool(career.get("career_active"))
                else "COMPLETE_OR_INDETERMINATE_AS_RECORDED"
            ),
            "methodology_version": AUDIT_VERSION,
        }
        if not rows:
            peak_rows.append(
                {
                    **shared,
                    "peak_status": "PEAK_UNAVAILABLE",
                    "reason_codes_json": json.dumps(["NO_SEASON_MEASUREMENT"]),
                }
            )
            longevity_rows.append(
                {
                    **shared,
                    "longevity_status": "LONGEVITY_UNAVAILABLE",
                    "reason_codes_json": json.dumps(["NO_SEASON_MEASUREMENT"]),
                }
            )
            continue
        seasons = np.asarray([int(row["season_id"]) for row in rows])
        centers = np.asarray([float(row["center"]) for row in rows])
        forms = [str(row["measurement_form"]) for row in rows]
        role = _mode([str(row["role"]) for row in rows])
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
        peak_values, longevity_values, peak_details, components = aggregate_draws(
            sampled, seasons, scales
        )
        season_p80 = np.mean(sampled >= 80.0, axis=0)
        season_p90 = np.mean(sampled >= 90.0, axis=0)
        expected_area_by_season = np.mean(np.clip((sampled - 80.0) / 10.0, 0.0, 1.0), axis=0)
        contribution_rows = [
            {
                "season_id": int(season),
                "p80_probability": float(season_p80[index]),
                "p90_probability": float(season_p90[index]),
                "expected_capped_area": float(expected_area_by_season[index]),
                "measurement_form": forms[index],
                "score_status": rows[index]["score_status"],
            }
            for index, season in enumerate(seasons)
        ]
        point_grade = {"OFFICIAL_POINT", "PROVISIONAL_POINT"}
        contributor_statuses = {
            str(rows[index]["score_status"])
            for index, probability in enumerate(season_p80)
            if probability >= 0.05
        }

        if peak_values.size:
            window_counts = np.bincount(
                peak_details.window_indices, minlength=len(peak_details.windows)
            )
            order = np.argsort(-window_counts, kind="mergesort")
            best_index = int(order[0])
            best_window = peak_details.windows[best_index]
            supported = [
                {
                    "window": _window_label(seasons, peak_details.windows[int(index)]),
                    "probability": float(window_counts[int(index)] / FINAL_DRAWS),
                }
                for index in order
                if window_counts[int(index)] / FINAL_DRAWS >= 0.05
            ]
            apex_counts = np.bincount(peak_details.apex_indices, minlength=len(rows))
            relevant_indices = {
                item
                for index in order
                if window_counts[int(index)] / FINAL_DRAWS >= 0.05
                for item in peak_details.windows[int(index)]
            } | {index for index, count in enumerate(apex_counts) if count / FINAL_DRAWS >= 0.05}
            relevant_statuses = {str(rows[index]["score_status"]) for index in relevant_indices}
            relevant_forms = {forms[index] for index in relevant_indices}
            weak_forms = relevant_forms - {
                "FULL_PORTABLE",
                "EXPANDED_PROXY_ACTION_WITH_PRESENCE",
                "TRADITIONAL_WITH_PRESENCE",
                "NO_TEAM_CONTEXT",
            }
            mixed_validated = bool(
                validation["patterns"]["MIXED_PROVISIONAL_INTERVAL"]["peak"]["point_eligible"]
            )
            partial_validated = bool(
                validation["patterns"]["PARTIAL_PRESENCE_LATE"]["peak"]["point_eligible"]
            )
            if relevant_statuses == {"OFFICIAL_POINT"}:
                peak_status = "OFFICIAL_PEAK_POINT"
            elif (relevant_statuses and relevant_statuses <= point_grade and partial_validated) or (
                weak_forms and relevant_forms - weak_forms and mixed_validated
            ):
                peak_status = "PROVISIONAL_PEAK_POINT"
            else:
                peak_status = "PEAK_INTERVAL_ONLY"
            if window_counts[best_index] / FINAL_DRAWS >= 0.70:
                window_status = "STABLE_WINDOW"
            elif window_counts[best_index] / FINAL_DRAWS >= 0.40:
                window_status = "COMPETING_WINDOWS"
            else:
                window_status = "UNCERTAIN_WINDOW"
            peak_item: dict[str, Any] = {
                **shared,
                "peak_central": float(np.median(peak_values)),
                "peak_status": peak_status,
                "best_supported_window": _window_label(seasons, best_window),
                "best_window_probability": float(window_counts[best_index] / FINAL_DRAWS),
                "second_window": (
                    _window_label(seasons, peak_details.windows[int(order[1])])
                    if len(order) > 1
                    else None
                ),
                "second_window_probability": (
                    float(window_counts[int(order[1])] / FINAL_DRAWS) if len(order) > 1 else None
                ),
                "window_status": window_status,
                "plausible_windows_json": json.dumps(supported, sort_keys=True),
                "relevant_seasons": len(rows),
                "draws": FINAL_DRAWS,
                "reason_codes_json": json.dumps(
                    ["WINDOW_RESELECTED_EACH_DRAW", "EMPIRICAL_DEPENDENCE_PRESERVED"],
                    sort_keys=True,
                ),
            }
            for level in (0.80, 0.90, 0.95):
                lower, upper = quantile_interval(peak_values, level)
                peak_item[f"peak_lower_{int(level * 100)}"] = lower
                peak_item[f"peak_upper_{int(level * 100)}"] = upper
            peak_rows.append(peak_item)
        else:
            peak_rows.append(
                {
                    **shared,
                    "peak_status": "PEAK_UNAVAILABLE",
                    "relevant_seasons": len(rows),
                    "draws": FINAL_DRAWS,
                    "reason_codes_json": json.dumps(["NO_COMPLETE_CONTIGUOUS_THREE_YEAR_WINDOW"]),
                }
            )

        if not contributor_statuses:
            contributor_statuses = {str(row["score_status"]) for row in rows}
        longevity_partial_validated = bool(
            validation["patterns"]["PARTIAL_PRESENCE_LATE"]["longevity"]["point_eligible"]
        )
        if contributor_statuses == {"OFFICIAL_POINT"}:
            longevity_status = "OFFICIAL_LONGEVITY_POINT"
        elif contributor_statuses <= point_grade and longevity_partial_validated:
            longevity_status = "PROVISIONAL_LONGEVITY_POINT"
        else:
            longevity_status = "LONGEVITY_INTERVAL_ONLY"
        longest_values = components.longest_run
        longevity_item: dict[str, Any] = {
            **shared,
            "longevity_central": float(np.median(longevity_values)),
            "longevity_status": longevity_status,
            "expected_elite_seasons_p80": float(np.mean(components.breadth)),
            "expected_capped_p80_p90_area": float(np.mean(components.capped_area)),
            "median_longest_p80_run": float(np.median(longest_values)),
            "modal_longest_p80_run": float(
                Counter(longest_values.astype(int).tolist()).most_common(1)[0][0]
            ),
            "probability_run_ge_2": float(np.mean(longest_values >= 2)),
            "probability_run_ge_3": float(np.mean(longest_values >= 3)),
            "probability_run_ge_5": float(np.mean(longest_values >= 5)),
            "season_probabilities_json": json.dumps(contribution_rows, sort_keys=True),
            "relevant_seasons": len(rows),
            "draws": FINAL_DRAWS,
            "reason_codes_json": json.dumps(
                ["P80_P90_FIXED_COMMON_SCALE", "EXACT_RUN_PER_CORRELATED_DRAW"],
                sort_keys=True,
            ),
        }
        for level in (0.80, 0.90, 0.95):
            lower, upper = quantile_interval(longevity_values, level)
            longevity_item[f"longevity_lower_{int(level * 100)}"] = lower
            longevity_item[f"longevity_upper_{int(level * 100)}"] = upper
            run_lower, run_upper = quantile_interval(longest_values, level)
            longevity_item[f"run_lower_{int(level * 100)}"] = run_lower
            longevity_item[f"run_upper_{int(level * 100)}"] = run_upper
        longevity_rows.append(longevity_item)
    return peak_rows, longevity_rows, dependence


def status_report(
    peak_rows: list[dict[str, Any]],
    longevity_rows: list[dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    def summarize(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
        status = Counter(str(row[field]) for row in rows)
        by_debut: dict[str, Counter[str]] = defaultdict(Counter)
        by_active: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            player = metadata.get(str(row["player_id"]), {})
            first = player.get("regular_first_season")
            cohort = f"{int(first) // 10 * 10}s" if first is not None else "UNKNOWN"
            by_debut[cohort][str(row[field])] += 1
            active = "ACTIVE_TO_DATE" if bool(player.get("career_active")) else "NOT_ACTIVE"
            by_active[active][str(row[field])] += 1
        return {
            "counts": dict(sorted(status.items())),
            "by_debut_cohort": {
                key: dict(sorted(value.items())) for key, value in sorted(by_debut.items())
            },
            "by_active_status": {
                key: dict(sorted(value.items())) for key, value in sorted(by_active.items())
            },
        }

    return {
        "peak": summarize(peak_rows, "peak_status"),
        "longevity": summarize(longevity_rows, "longevity_status"),
    }


def distinctness_audit(
    peak_rows: list[dict[str, Any]], longevity_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    peak = {
        str(row["player_id"]): float(row["peak_central"])
        for row in peak_rows
        if row.get("peak_central") is not None
    }
    longevity = {
        str(row["player_id"]): float(row["longevity_central"])
        for row in longevity_rows
        if row.get("longevity_central") is not None
    }
    common = sorted(set(peak) & set(longevity))
    left = np.asarray([peak[player] for player in common])
    right = np.asarray([longevity[player] for player in common])
    design = np.column_stack([np.ones(left.size), left])
    fitted = design @ np.linalg.lstsq(design, right, rcond=None)[0]
    return {
        "players": len(common),
        "spearman": spearman(left.tolist(), right.tolist()),
        "pearson": correlation(left.tolist(), right.tolist()),
        "longevity_residual_variance_share": float(np.var(right - fitted) / np.var(right)),
        "interpretation": (
            "Peak uses only the selected three-year/apex height; Longevity uses thresholded, "
            "capped breadth and consecutive duration across the observed career."
        ),
    }


def pairwise_reliability(validation_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    output: dict[str, Any] = {}
    for pattern in PATTERNS:
        members = [row for row in validation_rows if row["pattern"] == pattern]
        if len(members) < 2:
            continue
        left = rng.integers(0, len(members), 150_000)
        right = rng.integers(0, len(members), 150_000)
        distinct = left != right
        left, right = left[distinct], right[distinct]
        output[pattern] = {}
        for dimension in ("peak", "longevity"):
            reference = np.asarray([float(row[f"reference_{dimension}"]) for row in members])
            central = np.asarray([float(row[f"{dimension}_central"]) for row in members])
            naive = np.asarray(
                [
                    float(row["naive_peak"])
                    if dimension == "peak"
                    else float(row["longevity_central"])
                    for row in members
                ]
            )
            lower = np.asarray([float(row[f"{dimension}_lower_90"]) for row in members])
            upper = np.asarray([float(row[f"{dimension}_upper_90"]) for row in members])
            difference = np.abs(reference[left] - reference[right])
            truth = np.sign(reference[left] - reference[right])
            result: dict[str, Any] = {}
            for gap in (2, 5, 10, 15, 20):
                mask = (difference >= gap) & (difference < gap + 2)
                robust = (lower[left] > upper[right]) | (lower[right] > upper[left])
                robust_correct = ((lower[left] > upper[right]) & (truth > 0)) | (
                    (lower[right] > upper[left]) & (truth < 0)
                )
                result[str(gap)] = {
                    "pairs": int(np.sum(mask)),
                    "naive_order_accuracy": float(
                        np.mean(np.sign(naive[left][mask] - naive[right][mask]) == truth[mask])
                    ),
                    "uncertainty_aware_central_accuracy": float(
                        np.mean(np.sign(central[left][mask] - central[right][mask]) == truth[mask])
                    ),
                    "robust_order_share": float(np.mean(robust[mask])),
                    "robust_order_accuracy": (
                        float(np.sum(robust_correct[mask]) / np.sum(robust[mask]))
                        if int(np.sum(robust[mask]))
                        else None
                    ),
                }
            output[pattern][dimension] = result
    return output


def _window_summary(peak_rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in peak_rows if row.get("peak_central") is not None]
    return {
        "players": len(available),
        "window_status": dict(Counter(str(row["window_status"]) for row in available)),
        "mean_best_window_probability": statistics.fmean(
            float(row["best_window_probability"]) for row in available
        ),
        "architecture": {
            "three_year_weight": PEAK_THREE_YEAR_WEIGHT,
            "apex_weight": 1.0 - PEAK_THREE_YEAR_WEIGHT,
            "window_reselected_each_draw": True,
            "incomplete_windows_allowed": False,
        },
    }


def _case_studies(
    peak_rows: list[dict[str, Any]],
    longevity_rows: list[dict[str, Any]],
    names: set[str],
) -> list[dict[str, Any]]:
    peak_index = {str(row["player_id"]): row for row in peak_rows}
    longevity_index = {str(row["player_id"]): row for row in longevity_rows}
    output: list[dict[str, Any]] = []
    for player_id, peak in peak_index.items():
        if peak.get("player_name") not in names:
            continue
        longevity = longevity_index[player_id]
        output.append(
            {
                "player_id": player_id,
                "player_name": peak.get("player_name"),
                "peak_status": peak.get("peak_status"),
                "peak_central": peak.get("peak_central"),
                "peak_lower_90": peak.get("peak_lower_90"),
                "peak_upper_90": peak.get("peak_upper_90"),
                "best_supported_window": peak.get("best_supported_window"),
                "best_window_probability": peak.get("best_window_probability"),
                "second_window": peak.get("second_window"),
                "second_window_probability": peak.get("second_window_probability"),
                "window_status": peak.get("window_status"),
                "longevity_status": longevity.get("longevity_status"),
                "longevity_central": longevity.get("longevity_central"),
                "longevity_lower_90": longevity.get("longevity_lower_90"),
                "longevity_upper_90": longevity.get("longevity_upper_90"),
                "expected_elite_seasons_p80": longevity.get("expected_elite_seasons_p80"),
                "expected_capped_p80_p90_area": longevity.get("expected_capped_p80_p90_area"),
                "median_longest_p80_run": longevity.get("median_longest_p80_run"),
                "run_lower_90": longevity.get("run_lower_90"),
                "run_upper_90": longevity.get("run_upper_90"),
                "active_career_status": peak.get("active_career_status"),
            }
        )
    return sorted(output, key=lambda row: str(row["player_name"]))


def _verdicts(validation: dict[str, Any]) -> tuple[str, str, str]:
    point_patterns = ("FULL_REFERENCE", "PARTIAL_PRESENCE_LATE")
    interval_patterns = tuple(pattern for pattern in PATTERNS if pattern not in point_patterns)

    def dimension_verdict(dimension: str) -> str:
        point_ok = bool(
            validation["patterns"]["PARTIAL_PRESENCE_LATE"][dimension]["point_eligible"]
        )
        intervals_usable = all(
            0.80 <= float(validation["patterns"][pattern][dimension]["coverage_90"]) <= 0.98
            for pattern in interval_patterns
        )
        if point_ok and intervals_usable:
            return f"{dimension.upper()}_UNCERTAINTY_LIMITED"
        if intervals_usable:
            return f"{dimension.upper()}_UNCERTAINTY_LIMITED"
        return f"{dimension.upper()}_UNCERTAINTY_INVALID"

    peak = dimension_verdict("peak")
    longevity = dimension_verdict("longevity")
    if peak == "PEAK_UNCERTAINTY_VALID" and longevity == "LONGEVITY_UNCERTAINTY_VALID":
        recommendation = "READY_FOR_JOINT_PSV_PEAK_LONGEVITY_PROMOTION_AUDIT"
    elif peak == "PEAK_UNCERTAINTY_VALID":
        recommendation = "READY_FOR_PEAK_PROMOTION_ONLY"
    elif longevity == "LONGEVITY_UNCERTAINTY_VALID":
        recommendation = "READY_FOR_LONGEVITY_PROMOTION_ONLY"
    elif peak.endswith("INVALID") or longevity.endswith("INVALID"):
        recommendation = "MORE_AGGREGATION_RESEARCH"
    else:
        recommendation = "MORE_AGGREGATION_RESEARCH"
    return peak, longevity, recommendation


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    linked, anchors, source_rows, selected, reconstruction_report = reconstruct_step_h(args)
    residuals, points, residual_semantics = residual_library(anchors, selected)
    dependence = residual_dependence(anchors, residuals, source_rows)
    library = donor_library(anchors, residuals)
    validation_careers = _validation_careers(anchors, points)
    validation_scales = build_scales(validation_careers, set(validation_careers))
    propagation, selected_method = propagation_comparison(
        validation_careers, validation_scales, library
    )
    convergence = convergence_audit(validation_careers, validation_scales, library, selected_method)
    validation_rows, validation_report = masked_career_validation(
        validation_careers,
        validation_scales,
        library,
        selected_method,
        FINAL_DRAWS,
    )

    broad_reference, flags = _load_reference_flags(args.gold_root)
    metadata = _career_metadata(args.gold_root)
    careers = actual_careers(linked)
    actual_scales = build_scales(careers, broad_reference)
    all_players = sorted(flags)
    peak_rows, longevity_rows, aggregation_policy = aggregate_actual(
        careers,
        all_players,
        actual_scales,
        library,
        selected_method,
        metadata,
        validation_report,
    )
    statuses = status_report(peak_rows, longevity_rows, metadata)
    distinctness = distinctness_audit(peak_rows, longevity_rows)
    pairwise = pairwise_reliability(validation_rows)
    window_report = _window_summary(peak_rows)
    early_cases = _case_studies(peak_rows, longevity_rows, set(EARLY_NAMES))
    modern_cases = _case_studies(peak_rows, longevity_rows, set(MODERN_NAMES))
    modern_ids = {str(row["player_id"]) for row in modern_cases}
    modern_masked = [row for row in validation_rows if str(row["player_id"]) in modern_ids]
    peak_verdict, longevity_verdict, recommendation = _verdicts(validation_report)

    scale_report = {
        "season_thresholds": {
            "p80": 80.0,
            "p90": 90.0,
            "scale": "STEP-0015H linked FULL_PORTABLE reference form",
            "different_era_thresholds": False,
            "threshold_redrawn": False,
        },
        "reference_population": {
            "name": "BROAD_HIGH_RECALL",
            "frozen_player_ids": len(broad_reference),
            "peak_reference_values": int(actual_scales["peak"].size),
            "longevity_reference_values": int(actual_scales["longevity"].size),
            "policy": (
                "fixed central expected reference distributions; interval-only players remain "
                "eligible when their factual measurement supports the aggregate"
            ),
        },
        "ecdf_policy": {
            "selected": "TRANSFORM_EACH_DRAW_THROUGH_FIXED_REFERENCE_ECDF",
            "recompute_reference_each_draw": False,
            "reason": (
                "uncertainty must reflect the player's measurement, not a moving population scale"
            ),
        },
        "peak_weights": {"three_year": 0.70, "single_season_apex": 0.30},
        "longevity_weights": {
            "breadth": 0.35,
            "capped_area": 0.40,
            "longest_run": 0.25,
        },
    }

    output_root = args.gold_root / "peak_longevity_uncertainty_audit"
    manifests = [
        write_parquet(
            linked,
            output_root / "season-uncertainty-input.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            validation_rows,
            output_root / "masked-career-validation.parquet",
            ("pattern", "player_id"),
        ),
        write_parquet(
            _rectangularize(peak_rows),
            output_root / "peak-uncertainty-research.parquet",
            ("player_id",),
        ),
        write_parquet(
            _rectangularize(longevity_rows),
            output_root / "longevity-uncertainty-research.parquet",
            ("player_id",),
        ),
        write_parquet(
            _rectangularize(early_cases),
            output_root / "early-era-case-studies.parquet",
            ("player_name",),
        ),
        write_parquet(
            modern_masked,
            output_root / "modern-masked-careers.parquet",
            ("player_id", "pattern"),
        ),
    ]
    reports: dict[str, dict[str, Any]] = {
        "peak-longevity-residual-dependence.json": {
            "residual_semantics": residual_semantics,
            "by_measurement_form": dependence,
        },
        "peak-longevity-propagation-comparison.json": propagation,
        "peak-longevity-simulation-convergence.json": convergence,
        "peak-longevity-masked-career-validation.json": validation_report,
        "peak-window-stability.json": window_report,
        "peak-longevity-score-status.json": statuses,
        "peak-longevity-threshold-scale.json": scale_report,
        "peak-longevity-distinctness.json": distinctness,
        "peak-longevity-pairwise-reliability.json": pairwise,
        "peak-longevity-case-studies.json": {
            "early_era": early_cases,
            "modern_actual": modern_cases,
            "modern_masked": modern_masked,
        },
        "peak-longevity-uncertainty-verdict.json": {
            "step_result": "PASS",
            "peak_verdict": peak_verdict,
            "longevity_verdict": longevity_verdict,
            "recommendation": recommendation,
            "player_season_value_modified": False,
            "peak_weights_modified": False,
            "longevity_weights_modified": False,
            "official_methodology_created": False,
            "awards_postseason_championship_inputs": False,
            "player_specific_logic": False,
            "network_requests": 0,
        },
    }
    input_fingerprints = {
        "step_0015h": STEP_H_FINGERPRINT,
        "linked_seasons": LINKED_SEASON_HASH,
        "anchors": ANCHOR_HASH,
        "constitution": file_hash(ROOT / "docs/constitution/GOATLAB_V1_CONSTITUTION.md"),
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        stable_json(
            args.docs_root / name,
            {
                "step": "STEP-0015I",
                "audit_methodology_version": AUDIT_VERSION,
                "peak_research_version": PEAK_VERSION,
                "longevity_research_version": LONGEVITY_VERSION,
                "input_fingerprints": input_fingerprints,
                **payload,
            },
        )
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": input_fingerprints,
                "outputs": manifests,
                "reports": report_hashes,
                "reconstruction": reconstruction_report,
                "propagation": selected_method,
                "statuses": statuses,
                "peak_verdict": peak_verdict,
                "longevity_verdict": longevity_verdict,
                "recommendation": recommendation,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015I",
        "result": "PASS",
        "peak_verdict": peak_verdict,
        "longevity_verdict": longevity_verdict,
        "recommendation": recommendation,
        "audit_methodology_version": AUDIT_VERSION,
        "peak_research_version": PEAK_VERSION,
        "longevity_research_version": LONGEVITY_VERSION,
        "run_at": args.run_at,
        "input_fingerprints": input_fingerprints,
        "reconstruction": reconstruction_report,
        "within_career_dependence": dependence,
        "propagation_comparison": propagation,
        "simulation_convergence": convergence,
        "validation": validation_report,
        "score_status": statuses,
        "scale": scale_report,
        "distinctness": distinctness,
        "window_stability": window_report,
        "aggregation_policy": aggregation_policy,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "runtime_seconds": time.perf_counter() - started,
        "deterministic_rebuild_verified": args.expected_fingerprint is not None,
        "network_requests": 0,
    }
    stable_json(args.docs_root / "peak-longevity-uncertainty-summary.json", summary)
    if args.expected_fingerprint and fingerprint != args.expected_fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, got {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
