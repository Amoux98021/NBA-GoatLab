#!/usr/bin/env python3
"""Run STEP-0015O interval-native ranking and publication-policy audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from goatlab.rankings.interval_native import (
    RANKING_POLICY_AUDIT_VERSION,
    RANKING_POLICY_VERSION,
    apply_rank_band_offsets,
    band_report,
    crossfit_rank_bands,
    deterministic_ranks,
    pairwise_matrix,
    pairwise_probability_report,
    quantile_rank_bands,
    rank_draw_matrix,
    ranking_metrics,
    strongly_connected_components,
    topn_probability_report,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_overall_v2_promotion import (
    EARLY,
    MODERN,
    actual_audit,
    dimension_index,
    reconstruct_and_load,
    target_matrices,
    validation,
)
from pipelines.rankings.audit_peak_longevity_uncertainty import _load_reference_flags, _mode
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet

ROOT = Path(__file__).resolve().parents[2]
RUN_AT_DEFAULT = "2026-09-17T15:00:00Z"
STEP_N_FINGERPRINT = "b6248062490ca6b2d63e616af5ac759a59abc9ea3e9dc15dd4f2bd264741bb95"
STEP_N_PLAYER_HASH = "87d889989d5f17ca2756896e243e1a46f4fb2533d9bc93d662fdba75722439e4"
STEP_N_RANK_HASH = "3c640457212f9eb84f301bcc50123e24b5e34e03de5c6008c78352b2bd6fedd9"
SEED = 151_500
PAIRWISE_SEED = 151_501
SUMMARY_NAMES = (
    "R0_CENTRAL_OVERALL_SORT",
    "R1_MEDIAN_RANK",
    "R2_EXPECTED_RANK",
    "R3_PAIRWISE_EXPECTED_WINS",
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


def verify_step_n(args: argparse.Namespace) -> dict[str, Any]:
    summary_path = args.docs_root / "overall-v2-promotion-summary.json"
    summary = json.loads(summary_path.read_text())
    if summary["output_fingerprint"] != STEP_N_FINGERPRINT:
        raise ValueError("STEP-0015N fingerprint mismatch")
    if summary["promotion_verdict"] != "DO_NOT_PROMOTE_OVERALL_V2":
        raise ValueError("unexpected STEP-0015N verdict")
    paths = {
        "players": args.gold_root / "overall_v2_promotion_audit/overall-v2-player-scores.parquet",
        "ranks": args.gold_root / "overall_v2_promotion_audit/overall-v2-rank-uncertainty.parquet",
    }
    expected = {"players": STEP_N_PLAYER_HASH, "ranks": STEP_N_RANK_HASH}
    for key, expected_hash in expected.items():
        if file_hash(paths[key]) != expected_hash:
            raise ValueError(f"STEP-0015N {key} hash mismatch")
    return {"summary": summary, "paths": paths, "hashes": expected}


def _summary_rankings(
    centers: np.ndarray,
    rank_draws: np.ndarray,
    player_ids: list[str],
) -> dict[str, np.ndarray]:
    median_rank = np.median(rank_draws, axis=1)
    expected_rank = np.mean(rank_draws, axis=1)
    expected_wins = len(player_ids) - expected_rank
    return {
        "R0_CENTRAL_OVERALL_SORT": deterministic_ranks(centers, player_ids, descending=True),
        "R1_MEDIAN_RANK": deterministic_ranks(median_rank, player_ids, descending=False),
        "R2_EXPECTED_RANK": deterministic_ranks(expected_rank, player_ids, descending=False),
        "R3_PAIRWISE_EXPECTED_WINS": deterministic_ranks(
            expected_wins, player_ids, descending=True
        ),
    }


def _rank_tier(reference_rank: int) -> str:
    if reference_rank <= 10:
        return "TOP_10"
    if reference_rank <= 25:
        return "RANK_11_25"
    if reference_rank <= 50:
        return "RANK_26_50"
    if reference_rank <= 100:
        return "RANK_51_100"
    return "OUTSIDE_TOP_100"


def _group_error_report(
    reference: np.ndarray,
    estimate: np.ndarray,
    groups: list[str],
) -> dict[str, dict[str, float | int]]:
    output: dict[str, dict[str, float | int]] = {}
    scale = len(reference)
    for group in sorted(set(groups)):
        indexes = np.asarray([index for index, value in enumerate(groups) if value == group])
        if len(indexes) < 5:
            continue
        errors = estimate[indexes] - reference[indexes]
        output[group] = {
            "n": len(indexes),
            "signed_rank_bias": float(np.mean(errors)),
            "absolute_rank_mae": float(np.mean(np.abs(errors))),
            "signed_percentile_bias": float(np.mean(errors) / scale),
        }
    return output


def _rank_band_by_tier(
    reference: np.ndarray,
    bands: dict[int, tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    groups = [_rank_tier(int(value)) for value in reference]
    output: dict[str, Any] = {}
    for tier in dict.fromkeys(groups):
        indexes = np.asarray([index for index, value in enumerate(groups) if value == tier])
        output[tier] = {}
        for level, (lower, upper) in bands.items():
            output[tier][str(level)] = {
                "n": len(indexes),
                "coverage": float(
                    np.mean(
                        (lower[indexes] <= reference[indexes])
                        & (reference[indexes] <= upper[indexes])
                    )
                ),
                "mean_width": float(np.mean(upper[indexes] - lower[indexes])),
            }
    return output


def _cycle_audit(
    reference_ranks: np.ndarray,
    draw_matrix: np.ndarray,
) -> dict[str, Any]:
    top = np.flatnonzero(reference_ranks <= 100)
    outside = np.flatnonzero(reference_ranks > 100)
    if len(outside) > 100:
        positions: npt.NDArray[np.int_] = np.linspace(0, len(outside) - 1, 100).round().astype(int)
        outside = outside[positions]
    indexes = np.unique(np.concatenate([top, outside]))
    probabilities = pairwise_matrix(draw_matrix, indexes)
    output: dict[str, Any] = {"audited_players": len(indexes)}
    for name, threshold in (("LEAN", 0.65), ("STRONG", 0.90)):
        adjacency = probabilities >= threshold
        np.fill_diagonal(adjacency, False)
        components = strongly_connected_components(adjacency)
        cyclic = [component for component in components if len(component) > 1]
        output[name] = {
            "threshold": threshold,
            "cyclic_component_count": len(cyclic),
            "players_in_cycles": sum(len(component) for component in cyclic),
            "largest_cyclic_component": max((len(component) for component in cyclic), default=0),
            "edges_inside_cyclic_components": sum(
                int(np.sum(adjacency[np.ix_(component, component)])) for component in cyclic
            ),
        }
    return output


def _top100_policy_report(
    reference: np.ndarray,
    summaries: dict[str, np.ndarray],
    rank_draws: np.ndarray,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    probabilities = np.mean(rank_draws <= 100, axis=1)
    output: dict[str, Any] = {}
    for method, ranks in summaries.items():
        selected = ranks <= 100
        report: dict[str, Any] = {
            "reference_overlap": float(np.sum(selected & (reference <= 100)) / 100),
            "mean_top100_probability_selected": float(np.mean(probabilities[selected])),
        }
        if statuses is not None:
            report["status_distribution"] = dict(
                sorted(
                    Counter(
                        status for status, keep in zip(statuses, selected, strict=True) if keep
                    ).items()
                )
            )
        output[method] = report
    return output


def validation_audit(
    validation_rows: list[dict[str, Any]],
    draw_cache: dict[str, dict[str, np.ndarray]],
    players: list[str],
    anchors: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[int, float]], list[dict[str, Any]]]:
    roles_by_player: dict[str, list[str]] = defaultdict(list)
    seasons_by_player: dict[str, list[int]] = defaultdict(list)
    for row in anchors:
        player_id = str(row["player_id"])
        roles_by_player[player_id].append(str(row["role"]))
        seasons_by_player[player_id].append(int(row["season_id"]))
    roles = {player: _mode(values) for player, values in roles_by_player.items()}
    midpoint_decade = {
        player: f"{int(statistics.median(values)) // 10 * 10}s"
        for player, values in seasons_by_player.items()
    }
    patterns = sorted({str(row["pattern"]) for row in validation_rows})
    report: dict[str, Any] = {}
    deployment: dict[str, dict[int, float]] = {}
    validation_output: list[dict[str, Any]] = []
    for pattern_index, pattern in enumerate(patterns):
        members = [row for row in validation_rows if row["pattern"] == pattern]
        player_ids = [str(row["player_id"]) for row in members]
        references = np.asarray([float(row["reference_overall"]) for row in members])
        centers = np.asarray([float(row["overall_median"]) for row in members])
        draws = np.vstack([draw_cache[pattern][player] for player in player_ids])
        reference_ranks = deterministic_ranks(references, player_ids, descending=True)
        rank_draws = rank_draw_matrix(draws)
        summaries = _summary_rankings(centers, rank_draws, player_ids)
        raw_bands = quantile_rank_bands(rank_draws)
        median_raw_rank = np.median(rank_draws, axis=1)
        calibrated_bands, offsets = crossfit_rank_bands(
            player_ids, reference_ranks, raw_bands, len(player_ids), median_raw_rank
        )
        deployment[pattern] = offsets
        summary_report = {
            method: ranking_metrics(reference_ranks, ranks) for method, ranks in summaries.items()
        }
        pairwise = pairwise_probability_report(
            references, draws, seed=PAIRWISE_SEED + pattern_index
        )
        role_groups = [roles.get(player, "UNKNOWN") for player in player_ids]
        decade_groups = [midpoint_decade.get(player, "UNKNOWN") for player in player_ids]
        report[pattern] = {
            "population": len(player_ids),
            "ranking_summaries": summary_report,
            "median_rank_raw_bias": float(np.mean(median_raw_rank - reference_ranks)),
            "median_rank_raw_mae": float(np.mean(np.abs(median_raw_rank - reference_ranks))),
            "rank_bands_raw": band_report(reference_ranks, raw_bands),
            "rank_bands_crossfit_conformal": band_report(reference_ranks, calibrated_bands),
            "rank_bands_by_reference_tier": _rank_band_by_tier(reference_ranks, calibrated_bands),
            "topn_probability_calibration": topn_probability_report(reference_ranks, rank_draws),
            "pairwise_probability_calibration": pairwise,
            "cycle_audit": _cycle_audit(reference_ranks, draws),
            "role_fairness": _group_error_report(
                reference_ranks, summaries["R1_MEDIAN_RANK"], role_groups
            ),
            "career_midpoint_decade_fairness": _group_error_report(
                reference_ranks, summaries["R1_MEDIAN_RANK"], decade_groups
            ),
            "top100_policies": _top100_policy_report(reference_ranks, summaries, rank_draws),
            "deployment_rank_band_offsets_percentile": {
                str(level): value for level, value in offsets.items()
            },
        }
        for index, player_id in enumerate(player_ids):
            item: dict[str, Any] = {
                "player_id": player_id,
                "pattern": pattern,
                "reference_rank": int(reference_ranks[index]),
                "overall_center": float(centers[index]),
                "median_rank": float(median_raw_rank[index]),
                "expected_rank": float(np.mean(rank_draws[index])),
                "top_10_probability": float(np.mean(rank_draws[index] <= 10)),
                "top_25_probability": float(np.mean(rank_draws[index] <= 25)),
                "top_50_probability": float(np.mean(rank_draws[index] <= 50)),
                "top_100_probability": float(np.mean(rank_draws[index] <= 100)),
                "role": role_groups[index],
                "career_midpoint_decade": decade_groups[index],
            }
            for method, ranks in summaries.items():
                item[f"{method.lower()}_rank"] = int(ranks[index])
            for level, (lower, upper) in calibrated_bands.items():
                item[f"rank_lower_{level}"] = float(lower[index])
                item[f"rank_upper_{level}"] = float(upper[index])
            validation_output.append(item)
    return report, deployment, validation_output


def _calibration_gate(report: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    methods = {
        method: all(
            pattern["ranking_summaries"][method]["spearman"] >= 0.98
            and pattern["ranking_summaries"][method]["top_10_overlap"] >= 0.90
            and pattern["ranking_summaries"][method]["top_25_overlap"] >= 0.90
            and pattern["ranking_summaries"][method]["top_50_overlap"] >= 0.90
            and pattern["ranking_summaries"][method]["top_100_overlap"] >= 0.90
            for pattern in report.values()
        )
        for method in SUMMARY_NAMES
    }
    rank_bands = all(
        0.87 <= pattern["rank_bands_crossfit_conformal"]["90"]["coverage"] <= 0.93
        for pattern in report.values()
    )
    topn = all(
        pattern["topn_probability_calibration"][f"top_{n}"]["brier_score"] <= 0.03
        and pattern["topn_probability_calibration"][f"top_{n}"]["expected_calibration_error"]
        <= 0.02
        for pattern in report.values()
        for n in (10, 25, 50, 100)
    )
    pairwise = all(
        pattern["pairwise_probability_calibration"]["brier_score_directional"] <= 0.15
        and pattern["pairwise_probability_calibration"]["expected_calibration_error"] <= 0.03
        for pattern in report.values()
    )
    gates = {
        **{f"{method}_exact_rank_gate": passed for method, passed in methods.items()},
        "rank_band_calibration": rank_bands,
        "topn_probability_calibration": topn,
        "pairwise_probability_calibration": pairwise,
    }
    return any(methods.values()), gates


def _top100_label(probability: float) -> str:
    if probability >= 0.90:
        return "ROBUST_TOP100"
    if probability >= 0.65:
        return "LIKELY_TOP100"
    if probability >= 0.35:
        return "TOP100_BUBBLE"
    if probability >= 0.10:
        return "LIKELY_OUTSIDE_TOP100"
    return "ROBUST_OUTSIDE_TOP100"


def actual_ranking_audit(
    actual_rows: list[dict[str, Any]],
    actual_draws: dict[str, np.ndarray],
    deployment: dict[str, dict[int, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any], np.ndarray, list[str]]:
    row_index = {str(row["player_id"]): row for row in actual_rows}
    player_ids = sorted(actual_draws)
    draws = np.vstack([actual_draws[player] for player in player_ids])
    rank_draws = rank_draw_matrix(draws)
    centers = np.asarray(
        [float(row_index[player]["overall_diagnostic_center"]) for player in player_ids]
    )
    summaries = _summary_rankings(centers, rank_draws, player_ids)
    raw_bands = quantile_rank_bands(rank_draws)
    output: list[dict[str, Any]] = []
    for index, player_id in enumerate(player_ids):
        source = row_index[player_id]
        pattern = str(source["joint_pattern"])
        median_rank = float(np.median(rank_draws[index]))
        player_bands = {
            level: (np.asarray([lower[index]]), np.asarray([upper[index]]))
            for level, (lower, upper) in raw_bands.items()
        }
        calibrated = apply_rank_band_offsets(
            player_bands, deployment[pattern], len(player_ids), [median_rank]
        )
        top_probabilities = {
            n: float(np.mean(rank_draws[index] <= n)) for n in (1, 5, 10, 25, 50, 100)
        }
        item: dict[str, Any] = {
            **source,
            "distribution_rankability": "DISTRIBUTION_RANKABLE",
            "central_sort_rank": int(summaries["R0_CENTRAL_OVERALL_SORT"][index]),
            "median_rank": median_rank,
            "median_rank_sort_position": int(summaries["R1_MEDIAN_RANK"][index]),
            "expected_rank": float(np.mean(rank_draws[index])),
            "expected_rank_sort_position": int(summaries["R2_EXPECTED_RANK"][index]),
            "pairwise_expected_wins": float(len(player_ids) - np.mean(rank_draws[index])),
            "pairwise_wins_sort_position": int(summaries["R3_PAIRWISE_EXPECTED_WINS"][index]),
            **{f"probability_top_{n}": probability for n, probability in top_probabilities.items()},
            "top100_membership_label": _top100_label(top_probabilities[100]),
            "ranking_policy_version": RANKING_POLICY_VERSION,
            "ranking_is_official": False,
            "conditional_on_frozen_measurement_architecture": True,
            "shared_cross_player_calibration_uncertainty_modeled": False,
        }
        for level, (lower, upper) in calibrated.items():
            item[f"rank_lower_{level}"] = float(lower[0])
            item[f"rank_upper_{level}"] = float(upper[0])
        output.append(item)
    comparison = {
        left: {
            right: {
                "spearman": float(np.corrcoef(summaries[left], summaries[right])[0, 1]),
                **{
                    f"top_{n}_overlap": len(
                        set(np.flatnonzero(summaries[left] <= n).tolist())
                        & set(np.flatnonzero(summaries[right] <= n).tolist())
                    )
                    / n
                    for n in (10, 25, 50, 100)
                },
            }
            for right in SUMMARY_NAMES
            if right != left
        }
        for left in SUMMARY_NAMES
    }
    return output, comparison, rank_draws, player_ids


def _close_order_audit(rows: list[dict[str, Any]], draws: dict[str, np.ndarray]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: int(row["central_sort_rank"]))
    gaps = (0.1, 0.25, 0.5, 1.0, 2.0)
    grouped: dict[float, list[float]] = defaultdict(list)
    examples: list[dict[str, Any]] = []
    for left, right in pairwise(ordered):
        gap = float(left["overall_diagnostic_center"]) - float(right["overall_diagnostic_center"])
        probability = float(np.mean(draws[str(left["player_id"])] > draws[str(right["player_id"])]))
        for threshold in gaps:
            if gap < threshold:
                grouped[threshold].append(probability)
        if gap < 0.25 and len(examples) < 30:
            examples.append(
                {
                    "higher_central": left["player_name"],
                    "lower_central": right["player_name"],
                    "central_gap": gap,
                    "probability_higher_above_lower": probability,
                }
            )
    return {
        "by_maximum_central_gap": {
            str(threshold): {
                "pairs": len(probabilities),
                "mean_probability_central_order": statistics.fmean(probabilities)
                if probabilities
                else None,
                "share_indeterminate_35_65": statistics.fmean(
                    0.35 <= probability <= 0.65 for probability in probabilities
                )
                if probabilities
                else None,
            }
            for threshold, probabilities in grouped.items()
        },
        "examples_under_0_25": examples,
    }


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    step_n = verify_step_n(args)
    frozen = reconstruct_and_load(args)
    paths = frozen["paths"]
    anchors = read_rows(paths["anchors"])
    dimensions = dimension_index(read_rows(paths["dimensions"]))
    defense_validation = read_rows(paths["defense_validation"])
    selected_linkers = json.loads(
        (args.docs_root / "player-season-value-measurement-linking-summary.json").read_text()
    )["selected_linkers"]
    matrices, _ = target_matrices(args.docs_root)
    (
        validation_rows,
        validation_reconstruction,
        point_eligible,
        overall_interval_deployment,
        internals,
    ) = validation(anchors, selected_linkers, dimensions, defense_validation, matrices)
    ranking_validation, rank_band_deployment, validation_output = validation_audit(
        validation_rows, internals["draw_cache"], internals["players"], anchors
    )
    exact_rank_passed, policy_gates = _calibration_gate(ranking_validation)

    season_contract = read_rows(paths["season_contract"])
    peak_rows = read_rows(paths["peak"])
    longevity_rows = read_rows(paths["longevity"])
    defense_rows = read_rows(paths["defense"])
    overall_l = read_rows(paths["overall_l"])
    flags_broad, flags = _load_reference_flags(args.gold_root)
    peaks = {str(row["player_id"]): row for row in peak_rows}
    longevity = {str(row["player_id"]): row for row in longevity_rows}
    defense = {str(row["player_id"]): row for row in defense_rows}
    l_index = {str(row["player_id"]): row for row in overall_l}
    actual_rows, actual_draws, actual_reconstruction = actual_audit(
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
        overall_interval_deployment,
        l_index,
    )
    stored_n_rows = {str(row["player_id"]): row for row in read_rows(step_n["paths"]["players"])}
    differences: list[float] = []
    status_mismatches = 0
    for row in actual_rows:
        stored = stored_n_rows[str(row["player_id"])]
        status_mismatches += row["overall_status"] != stored["overall_status"]
        if row.get("overall_diagnostic_center") is not None:
            differences.append(
                abs(
                    float(row["overall_diagnostic_center"])
                    - float(stored["overall_diagnostic_center"])
                )
            )
    reconstruction = {
        "step_0015n_output_fingerprint": STEP_N_FINGERPRINT,
        "players": len(actual_rows),
        "joint_validation_rows": len(validation_rows),
        "status_mismatches": status_mismatches,
        "maximum_center_difference": max(differences, default=0.0),
        "maximum_peak_longevity_path_difference": actual_reconstruction[
            "maximum_peak_longevity_path_difference_vs_step_0015l"
        ],
        "dependence_selected": validation_reconstruction["selected"],
    }
    if status_mismatches or reconstruction["maximum_center_difference"] > 1e-12:
        raise ValueError("STEP-0015N reconstruction failed")

    rank_rows, summary_stability, _actual_rank_draws, rankable_ids = actual_ranking_audit(
        actual_rows, actual_draws, rank_band_deployment
    )
    row_index = {str(row["player_id"]): row for row in rank_rows}
    broad = set(flags_broad)
    top100_v1 = read_rows(paths["top100_v1"])
    top100_ids = {str(row["player_id"]) for row in top100_v1}
    rankable_set = set(rankable_ids)
    rankability = {
        "ALL_PLAYERS": {
            "population": len(actual_rows),
            "distribution_rankable": len(rankable_ids),
            "not_rankable": len(actual_rows) - len(rankable_ids),
        },
        "BROAD_HIGH_RECALL": {
            "population": len(broad),
            "distribution_rankable": len(rankable_set & broad),
            "not_rankable": len(broad - rankable_set),
        },
        "V1_TOP_100": {
            "population": 100,
            "distribution_rankable": len(rankable_set & top100_ids),
            "not_rankable": len(top100_ids - rankable_set),
        },
    }

    v1_transition: list[dict[str, Any]] = []
    for v1 in sorted(top100_v1, key=lambda row: int(row["overall_rank"])):
        player_id = str(v1["player_id"])
        research = row_index.get(player_id)
        v1_transition.append(
            {
                "player_id": player_id,
                "player_name": v1["player_name"],
                "v1_rank": int(v1["overall_rank"]),
                "distribution_rankable": research is not None,
                "overall_status": research.get("overall_status") if research else "NOT_RANKABLE",
                "median_rank": research.get("median_rank") if research else None,
                "rank_lower_80": research.get("rank_lower_80") if research else None,
                "rank_upper_80": research.get("rank_upper_80") if research else None,
                "rank_lower_90": research.get("rank_lower_90") if research else None,
                "rank_upper_90": research.get("rank_upper_90") if research else None,
                "probability_top_100": research.get("probability_top_100") if research else None,
            }
        )

    diagnostic_names = set(EARLY) | set(MODERN)
    diagnostics = [row for row in rank_rows if row.get("player_name") in diagnostic_names]
    by_name = {str(row["player_name"]): row for row in diagnostics}
    jordan, lebron = by_name["Michael Jordan"], by_name["LeBron James"]
    jordan_id, lebron_id = str(jordan["player_id"]), str(lebron["player_id"])
    jordan_lebron = {
        "jordan": {
            key: jordan[key]
            for key in (
                "overall_diagnostic_center",
                "median_rank",
                "rank_lower_80",
                "rank_upper_80",
                "rank_lower_90",
                "rank_upper_90",
                "probability_top_1",
                "probability_top_5",
            )
        },
        "lebron": {
            key: lebron[key]
            for key in (
                "overall_diagnostic_center",
                "median_rank",
                "rank_lower_80",
                "rank_upper_80",
                "rank_lower_90",
                "rank_upper_90",
                "probability_top_1",
                "probability_top_5",
            )
        },
        "probability_jordan_above_lebron": float(
            np.mean(actual_draws[jordan_id] > actual_draws[lebron_id])
        ),
    }

    close_order = _close_order_audit(rank_rows, actual_draws)
    status_distribution = dict(sorted(Counter(row["overall_status"] for row in rank_rows).items()))
    membership_distribution = dict(
        sorted(Counter(row["top100_membership_label"] for row in rank_rows).items())
    )
    interval_fairness = {
        pattern: {
            "median_rank_bias": details["median_rank_raw_bias"],
            "median_rank_mae": details["median_rank_raw_mae"],
            "role_fairness": details["role_fairness"],
            "career_midpoint_decade_fairness": details["career_midpoint_decade_fairness"],
        }
        for pattern, details in ranking_validation.items()
    }
    probabilistic_passed = (
        policy_gates["rank_band_calibration"]
        and policy_gates["topn_probability_calibration"]
        and policy_gates["pairwise_probability_calibration"]
    )
    publication_verdict = (
        "VALID_UNCERTAINTY_NATIVE_RANKING"
        if exact_rank_passed
        else "VALID_PROBABILISTIC_RANKING_ONLY"
        if probabilistic_passed
        else "PARTIAL_ORDER_ONLY"
    )
    overall_readiness = (
        "OVERALL_V2_READY_UNDER_UNCERTAINTY_NATIVE_POLICY"
        if publication_verdict == "VALID_UNCERTAINTY_NATIVE_RANKING"
        else "OVERALL_V2_STILL_NOT_READY"
    )
    generate_top100 = (
        publication_verdict == "VALID_UNCERTAINTY_NATIVE_RANKING"
        and overall_readiness == "OVERALL_V2_READY_UNDER_UNCERTAINTY_NATIVE_POLICY"
    )
    recommendation = (
        "CLOSE_STEP_0015_AND_BEGIN_PRODUCTIZATION"
        if generate_top100
        else "VALIDATE_EXACT_SUMMARY_OR_ADOPT_PROBABILISTIC_PRODUCT_REQUIREMENT"
    )

    base = {
        "step": "STEP-0015O",
        "audit_version": RANKING_POLICY_AUDIT_VERSION,
        "ranking_policy_version": RANKING_POLICY_VERSION,
        "upstream_fingerprint": STEP_N_FINGERPRINT,
    }
    reports: dict[str, dict[str, Any]] = {
        "interval-ranking-reconstruction.json": {**base, **reconstruction},
        "distribution-rankable-population.json": {
            **base,
            "rankability": rankability,
            "distribution_rankable_statuses": status_distribution,
            "rule": "A calibrated Overall distribution exists; exact point status is not required.",
        },
        "rank-summary-validation.json": {
            **base,
            "patterns": {
                pattern: details["ranking_summaries"]
                for pattern, details in ranking_validation.items()
            },
            "actual_summary_stability": summary_stability,
            "exact_rank_policy_passed": exact_rank_passed,
            "selected_display_summary": "R1_MEDIAN_RANK_DIAGNOSTIC_ONLY",
        },
        "rank-band-calibration.json": {
            **base,
            "patterns": {
                pattern: {
                    "raw": details["rank_bands_raw"],
                    "crossfit_conformal": details["rank_bands_crossfit_conformal"],
                    "by_reference_tier": details["rank_bands_by_reference_tier"],
                    "deployment_offsets_percentile": details[
                        "deployment_rank_band_offsets_percentile"
                    ],
                }
                for pattern, details in ranking_validation.items()
            },
        },
        "topn-probability-calibration.json": {
            **base,
            "patterns": {
                pattern: details["topn_probability_calibration"]
                for pattern, details in ranking_validation.items()
            },
        },
        "pairwise-rank-calibration.json": {
            **base,
            "patterns": {
                pattern: details["pairwise_probability_calibration"]
                for pattern, details in ranking_validation.items()
            },
            "semantics": {
                "STRONG_ORDER": ">=0.90",
                "LEAN_ORDER": "0.65-0.90",
                "INDETERMINATE_ORDER": "0.35-0.65",
            },
        },
        "ranking-cycle-audit.json": {
            **base,
            "patterns": {
                pattern: details["cycle_audit"] for pattern, details in ranking_validation.items()
            },
        },
        "interval-ranking-fairness.json": {**base, "patterns": interval_fairness},
        "top100-policy-comparison.json": {
            **base,
            "patterns": {
                pattern: details["top100_policies"]
                for pattern, details in ranking_validation.items()
            },
            "actual_membership_label_counts": membership_distribution,
            "official_top100_generated": generate_top100,
        },
        "ranking-policy-status.json": {
            **base,
            "step_status": "PASS",
            "publication_verdict": publication_verdict,
            "overall_readiness_verdict": overall_readiness,
            "policy_gates": policy_gates,
            "recommendation": recommendation,
            "top100_generated": generate_top100,
        },
        "interval-ranking-diagnostics.json": {
            **base,
            "jordan_lebron": jordan_lebron,
            "players": diagnostics,
            "close_order": close_order,
        },
    }

    output_root = args.gold_root / "interval_native_ranking_policy_audit"
    manifests = [
        write_parquet(
            rectangularize(validation_output),
            output_root / "ranking-policy-validation.parquet",
            ("pattern", "reference_rank", "player_id"),
        ),
        write_parquet(
            rectangularize(rank_rows),
            output_root / "distribution-rankable-player-ranks.parquet",
            ("median_rank_sort_position", "player_id"),
        ),
        write_parquet(
            rectangularize(v1_transition),
            output_root / "v1-top100-uncertainty-transition.parquet",
            ("v1_rank",),
        ),
        write_parquet(
            rectangularize(diagnostics),
            output_root / "ranking-policy-diagnostic-players.parquet",
            ("player_name",),
        ),
    ]
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        stable_json(args.docs_root / name, payload)
        report_hashes[name] = file_hash(args.docs_root / name)

    top100_json = args.docs_root / "overall-v2-top100-uncertainty-aware.json"
    top100_gold = output_root / "overall-v2-top100-uncertainty-aware.parquet"
    for stale in (top100_json, top100_gold):
        if stale.exists():
            stale.unlink()
    if generate_top100:
        selected = sorted(rank_rows, key=lambda row: int(row["median_rank_sort_position"]))[:100]
        manifest = write_parquet(
            rectangularize(selected), top100_gold, ("median_rank_sort_position",)
        )
        manifests.append(manifest)
        stable_json(
            top100_json,
            {**base, "publication_verdict": publication_verdict, "players": selected},
        )
        report_hashes[top100_json.name] = file_hash(top100_json)

    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "upstream": STEP_N_FINGERPRINT,
                "outputs": manifests,
                "reports": report_hashes,
                "publication_verdict": publication_verdict,
                "readiness": overall_readiness,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, got {fingerprint}"
        )
    summary = {
        **base,
        "step_status": "PASS",
        "publication_verdict": publication_verdict,
        "overall_readiness_verdict": overall_readiness,
        "recommendation": recommendation,
        "rankability": rankability,
        "policy_gates": policy_gates,
        "selected_display_summary": "R1_MEDIAN_RANK_DIAGNOSTIC_ONLY",
        "top100_generated": generate_top100,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "deterministic_rebuild_verified": args.expected_fingerprint is not None,
        "runtime_seconds": time.perf_counter() - started,
        "run_at": args.run_at,
        "network_requests": 0,
    }
    stable_json(args.docs_root / "interval-native-ranking-policy-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
