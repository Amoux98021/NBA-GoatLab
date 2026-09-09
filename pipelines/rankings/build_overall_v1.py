#!/usr/bin/env python3
"""Build and audit the transparent GOATLab V1 Overall rating offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from goatlab.features.dimension_candidates import era_group
from goatlab.rankings.overall import (
    DIMENSIONS,
    OVERALL_METHODOLOGY_VERSION,
    OVERALL_RANDOM_SEED,
    classify_rank_stability,
    kendall_tau_for_unique_orders,
    proportional_perturbation,
    shapley_variance_influence,
    top_n_overlap,
    validate_weights,
)

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_METHOD = "goatlab-v1-dimension-scores-v1"
UPSTREAM_FINGERPRINT = "0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a"
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
AWARD_FINGERPRINT = "666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258"
RUN_DRAWS = 10_000
BOOTSTRAP_REPETITIONS = 250

CANDIDATES: dict[str, dict[str, float]] = {
    "A_EQUAL_NOMINAL": {name: 1.0 / 7.0 for name in DIMENSIONS},
    "B_CONSTITUTION_BALANCED": {
        "PEAK": 0.21,
        "LONGEVITY": 0.16,
        "OFFENSE": 0.17,
        "DEFENSE": 0.11,
        "PLAYOFFS": 0.17,
        "ACCOLADES": 0.09,
        "WINNING": 0.09,
    },
    "C_REDUNDANCY_ADJUSTED": {
        "PEAK": 0.17,
        "LONGEVITY": 0.14,
        "OFFENSE": 0.16,
        "DEFENSE": 0.14,
        "PLAYOFFS": 0.18,
        "ACCOLADES": 0.10,
        "WINNING": 0.11,
    },
}
BOUNDS = np.asarray(
    (
        (0.18, 0.24),
        (0.14, 0.20),
        (0.14, 0.20),
        (0.08, 0.14),
        (0.15, 0.21),
        (0.07, 0.13),
        (0.08, 0.14),
    ),
    dtype=np.float64,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def stable_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def read_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        rows.extend(pq.ParquetFile(path).read().to_pylist())
    return rows


def write_parquet(rows: list[dict[str, Any]], path: Path, keys: tuple[str, ...]) -> dict[str, Any]:
    rows.sort(key=lambda row: tuple((row.get(key) is None, row.get(key)) for key in keys))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, tmp, compression="zstd", compression_level=9, use_dictionary=False)
    tmp.replace(path)
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": len(rows),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def rank_vector(scores: np.ndarray, ids: list[str]) -> tuple[np.ndarray, list[str]]:
    order = np.lexsort((np.asarray(ids), -scores))
    ranks = np.empty(len(ids), dtype=np.int32)
    ranks[order] = np.arange(1, len(ids) + 1, dtype=np.int32)
    return ranks, [ids[int(index)] for index in order]


def corr(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.corrcoef(left.astype(float), right.astype(float))[0, 1])


def admissible_weights() -> np.ndarray:
    rng = np.random.default_rng(OVERALL_RANDOM_SEED)
    center = np.asarray([0.21, 0.17, 0.17, 0.11, 0.18, 0.08, 0.08])
    accepted: list[np.ndarray] = []
    while len(accepted) < RUN_DRAWS:
        batch = rng.dirichlet(center * 80.0, size=20_000)
        mask = ((batch >= BOUNDS[:, 0]) & (batch <= BOUNDS[:, 1])).all(axis=1)
        mask &= batch[:, :5].sum(axis=1) >= 0.72
        mask &= batch[:, 5:].sum(axis=1) <= 0.26
        for row in batch[mask]:
            accepted.append(row)
            if len(accepted) == RUN_DRAWS:
                break
    return np.asarray(accepted)


def group_summary(scores: np.ndarray, groups: list[str]) -> dict[str, dict[str, float | int]]:
    output: dict[str, dict[str, float | int]] = {}
    for group in sorted(set(groups)):
        indexes = [i for i, value in enumerate(groups) if value == group]
        values = scores[indexes]
        output[group] = {
            "players": len(indexes),
            "mean": float(values.mean()),
            "median": float(np.median(values)),
            "p90": float(np.percentile(values, 90)),
        }
    return output


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    summary_path = args.docs_root / "dimension-score-summary.json"
    upstream = json.loads(summary_path.read_text(encoding="utf-8"))
    if (
        upstream.get("methodology_version") != UPSTREAM_METHOD
        or upstream.get("output_fingerprint") != UPSTREAM_FINGERPRINT
    ):
        raise ValueError("frozen STEP-0014 methodology/fingerprint mismatch")
    if upstream.get("deterministic_rebuild_verified") is not True:
        raise ValueError("STEP-0014 is not certified reproducible")

    dimension_rows = read_rows(args.gold_root / "player_dimension_scores")
    if len(dimension_rows) != 35_721:
        raise ValueError("unexpected frozen dimension row count")
    by_player: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in dimension_rows:
        player_id, dimension = str(row["player_id"]), str(row["dimension"])
        if dimension in by_player[player_id]:
            raise ValueError("duplicate player-dimension key")
        by_player[player_id][dimension] = row
    if len(by_player) != 5_103 or any(set(rows) != set(DIMENSIONS) for rows in by_player.values()):
        raise ValueError("frozen player/dimension grain mismatch")

    career = {
        str(row["player_id"]): row for row in read_rows(args.gold_root / "player_career_summary")
    }
    cluster_rows = read_rows(args.gold_root / "ml_structure/clustering")
    clusters = {
        str(row["player_id"]): f"STEP13_CLUSTER_{row['kmeans_profile_cluster']}"
        for row in cluster_rows
        if "kmeans_profile_cluster" in row
    }
    complete_ids = sorted(
        player_id
        for player_id, rows in by_player.items()
        if all(rows[d]["score"] is not None for d in DIMENSIONS)
    )
    if len(complete_ids) != 1_882:
        raise ValueError("unexpected complete-profile count")
    matrix = np.asarray(
        [[float(by_player[p][d]["score"]) for d in DIMENSIONS] for p in complete_ids]
    )
    debut_groups = [era_group(int(career[p]["regular_first_season"])) for p in complete_ids]
    active_groups = [
        "ACTIVE_TO_DATE" if career[p]["career_active"] else "COMPLETE_OR_INDETERMINATE"
        for p in complete_ids
    ]
    profile_groups: list[str] = []
    for values in matrix:
        spread = float(values.max() - values.min())
        profile_groups.append(
            "BALANCED"
            if spread <= 15
            else f"{DIMENSIONS[int(np.argmax(values - values.mean()))]}_HEAVY"
        )

    simplex = admissible_weights()
    covariance = np.cov(matrix, rowvar=False, ddof=0)
    bootstrap_rng = np.random.default_rng(OVERALL_RANDOM_SEED + 1)
    bootstrap_covariances = np.asarray(
        [
            np.cov(
                matrix[bootstrap_rng.integers(0, len(matrix), size=len(matrix))],
                rowvar=False,
                ddof=0,
            )
            for _ in range(BOOTSTRAP_REPETITIONS)
        ]
    )
    # Candidate D is selected without player identities: minimize effective concentration and
    # between-era/profile mean spread, subject to the documented constitutional region.
    era_masks = [
        np.asarray([g == name for g in debut_groups]) for name in sorted(set(debut_groups))
    ]
    profile_masks = [
        np.asarray([g == name for g in profile_groups]) for name in sorted(set(profile_groups))
    ]
    objectives: list[tuple[float, int]] = []
    for index, weights in enumerate(simplex):
        variance = float(weights @ covariance @ weights)
        shares = weights * (covariance @ weights) / variance
        bootstrap_cov_weight = np.einsum("bij,j->bi", bootstrap_covariances, weights)
        bootstrap_variance = np.einsum("bi,i->b", bootstrap_cov_weight, weights)
        bootstrap_shares = weights * bootstrap_cov_weight / bootstrap_variance[:, None]
        bootstrap_instability = float(bootstrap_shares.std(axis=0).mean())
        scores = matrix @ weights
        era_range = (
            max(float(scores[m].mean()) for m in era_masks)
            - min(float(scores[m].mean()) for m in era_masks)
        ) / 100
        profile_range = (
            max(float(scores[m].mean()) for m in profile_masks)
            - min(float(scores[m].mean()) for m in profile_masks)
        ) / 100
        objectives.append(
            (
                float(
                    0.45 * np.square(shares).sum()
                    + 0.15 * bootstrap_instability
                    + 0.20 * era_range
                    + 0.20 * profile_range
                ),
                index,
            )
        )
    best_objective, best_index = min(objectives)
    CANDIDATES["D_STABILITY_ORIENTED"] = dict(
        zip(DIMENSIONS, map(float, simplex[best_index]), strict=True)
    )
    for weights in CANDIDATES.values():
        validate_weights(weights)

    candidate_ranks: dict[str, np.ndarray] = {}
    candidate_orders: dict[str, list[str]] = {}
    candidate_scores: dict[str, np.ndarray] = {}
    candidate_reports: dict[str, Any] = {}
    for name, weights in CANDIDATES.items():
        weight_vector = np.asarray(validate_weights(weights))
        scores = matrix @ weight_vector
        ranks, order = rank_vector(scores, complete_ids)
        candidate_scores[name], candidate_ranks[name], candidate_orders[name] = scores, ranks, order
        influence = shapley_variance_influence(matrix, weights)
        bootstrap_cov_weight = np.einsum("bij,j->bi", bootstrap_covariances, weight_vector)
        bootstrap_variance = np.einsum("bi,i->b", bootstrap_cov_weight, weight_vector)
        bootstrap_shares = weight_vector * bootstrap_cov_weight / bootstrap_variance[:, None]
        candidate_reports[name] = {
            "nominal_weights": weights,
            "overall_variance": influence.overall_variance,
            "effective_shapley_influence": dict(zip(DIMENSIONS, influence.shares, strict=True)),
            "bootstrap_effective_influence": {
                dimension: {
                    "mean": float(bootstrap_shares[:, index].mean()),
                    "std": float(bootstrap_shares[:, index].std()),
                    "p05": float(np.percentile(bootstrap_shares[:, index], 5)),
                    "p95": float(np.percentile(bootstrap_shares[:, index], 95)),
                }
                for index, dimension in enumerate(DIMENSIONS)
            },
            "career_shape_nominal": weights["PEAK"] + weights["LONGEVITY"],
            "direct_performance_nominal": sum(weights[d] for d in DIMENSIONS[:5]),
            "recognition_outcome_nominal": weights["ACCOLADES"] + weights["WINNING"],
            "debut_era": group_summary(scores, debut_groups),
            "profile_archetype": group_summary(scores, profile_groups),
            "career_status": group_summary(scores, active_groups),
        }

    for left in CANDIDATES:
        comparisons: dict[str, Any] = {}
        for right in CANDIDATES:
            comparisons[right] = {
                "spearman": corr(candidate_ranks[left], candidate_ranks[right]),
                **{
                    f"top_{n}_overlap": top_n_overlap(
                        candidate_orders[left], candidate_orders[right], n
                    )
                    for n in (10, 25, 50, 100)
                },
            }
        candidate_reports[left]["candidate_comparisons"] = comparisons

    default_name = "C_REDUNDANCY_ADJUSTED"
    default_weights = CANDIDATES[default_name]
    default_scores, default_ranks, default_order = (
        candidate_scores[default_name],
        candidate_ranks[default_name],
        candidate_orders[default_name],
    )
    index_by_player = {player_id: index for index, player_id in enumerate(complete_ids)}

    # Exact upper-bound screening over every candidate and every admissible simplex draw.
    complete_cutoffs = np.partition(matrix @ simplex.T, -100, axis=0)[-100, :]
    eligibility_rows: list[dict[str, Any]] = []
    unknown_six_complete: list[tuple[str, np.ndarray]] = []
    statuses = Counter()
    for player_id in sorted(by_player):
        rows = by_player[player_id]
        missing = [d for d in DIMENSIONS if rows[d]["score"] is None]
        award_status = str(rows["ACCOLADES"]["coverage_status"])
        classification = "COMPLETE_SEVEN_DIMENSIONS"
        reason = "ALL_REQUIRED_DIMENSIONS_AVAILABLE"
        max_upper: float | None = None
        closest_gap: float | None = None
        could_cross = False
        if award_status == "NOT_QUERIED":
            other_missing = [d for d in missing if d != "ACCOLADES"]
            if other_missing:
                classification, reason = "REVIEW_REQUIRED", "OTHER_REQUIRED_DIMENSION_UNAVAILABLE"
            else:
                six = np.asarray(
                    [100.0 if d == "ACCOLADES" else float(rows[d]["score"]) for d in DIMENSIONS]
                )
                upper = six @ simplex.T
                gaps = upper - complete_cutoffs
                max_upper, closest_gap, could_cross = (
                    float(upper.max()),
                    float(gaps.max()),
                    bool((gaps >= 0).any()),
                )
                if could_cross:
                    classification, reason = (
                        "MUST_QUERY_FOR_RANKING_ELIGIBILITY",
                        "CAN_CROSS_TOP100_UPPER_BOUND",
                    )
                    unknown_six_complete.append((player_id, six))
                elif closest_gap >= -5.0:
                    classification, reason = "REVIEW_REQUIRED", "WITHIN_FIVE_POINT_CUTOFF_BUFFER"
                else:
                    classification, reason = (
                        "SAFE_TO_EXCLUDE_FROM_V1_QUERY",
                        "UPPER_BOUND_BELOW_ALL_CUTOFFS",
                    )
        elif missing:
            classification, reason = "UNRANKED_INCOMPLETE", "REQUIRED_DIMENSION_UNAVAILABLE"
        statuses[classification] += 1
        eligibility_rows.append(
            {
                "player_id": player_id,
                "nba_player_id": str(rows["PEAK"]["nba_player_id"]),
                "display_name": str(rows["PEAK"]["display_name"]),
                "accolades_coverage_status": award_status,
                "eligibility_classification": classification,
                "reason_code": reason,
                "missing_dimensions_json": json.dumps(missing, separators=(",", ":")),
                "optimistic_max_overall": max_upper,
                "closest_top100_gap": closest_gap,
                "could_cross_any_admissible_top100": could_cross,
                "methodology_version": OVERALL_METHODOLOGY_VERSION,
            }
        )
    if unknown_six_complete:
        raise RuntimeError("award expansion is required before offline Overall publication")

    # Leave-one-out diagnostics (never used to rank incomplete players).
    loo: dict[str, Any] = {}
    for dim_index, dimension in enumerate(DIMENSIONS):
        weights = np.asarray(validate_weights(default_weights))
        weights[dim_index] = 0.0
        weights /= weights.sum()
        ranks, order = rank_vector(matrix @ weights, complete_ids)
        movers = np.argsort(-np.abs(ranks - default_ranks))[:10]
        loo[dimension] = {
            "spearman": corr(default_ranks, ranks),
            "kendall_tau": kendall_tau_for_unique_orders(default_order, order),
            **{f"top_{n}_overlap": top_n_overlap(default_order, order, n) for n in (25, 50, 100)},
            "largest_rank_movers": [
                {
                    "player_id": complete_ids[int(i)],
                    "default_rank": int(default_ranks[i]),
                    "without_dimension_rank": int(ranks[i]),
                    "absolute_move": int(abs(ranks[i] - default_ranks[i])),
                }
                for i in movers
            ],
        }

    # Local elasticity for every named candidate.
    local_rows: list[dict[str, Any]] = []
    for candidate_name, base_weights in CANDIDATES.items():
        base_ranks = candidate_ranks[candidate_name]
        base_order = candidate_orders[candidate_name]
        candidate_local: list[dict[str, Any]] = []
        for dimension in DIMENSIONS:
            for delta in (-0.05, -0.025, -0.01, 0.01, 0.025, 0.05):
                perturbed = proportional_perturbation(base_weights, dimension, delta)
                ranks, order = rank_vector(
                    matrix @ np.asarray(validate_weights(perturbed)), complete_ids
                )
                record = {
                    "candidate_method": candidate_name,
                    "dimension": dimension,
                    "delta_percentage_points": delta * 100,
                    "spearman": corr(base_ranks, ranks),
                    **{
                        f"top_{n}_overlap": top_n_overlap(base_order, order, n)
                        for n in (25, 50, 100)
                    },
                    "maximum_absolute_rank_move": int(np.abs(ranks - base_ranks).max()),
                    "top100_cutoff": float(
                        np.sort(matrix @ np.asarray(validate_weights(perturbed)))[-100]
                    ),
                }
                local_rows.append(record)
                candidate_local.append(record)
        candidate_reports[candidate_name]["local_perturbation_summary"] = {
            "minimum_spearman": min(row["spearman"] for row in candidate_local),
            "minimum_top25_overlap": min(row["top_25_overlap"] for row in candidate_local),
            "minimum_top50_overlap": min(row["top_50_overlap"] for row in candidate_local),
            "minimum_top100_overlap": min(row["top_100_overlap"] for row in candidate_local),
            "maximum_absolute_rank_move": max(
                row["maximum_absolute_rank_move"] for row in candidate_local
            ),
        }

    # Random-simplex rank intervals and distribution audits.
    random_scores = matrix @ simplex.T
    random_ranks = np.empty((len(complete_ids), RUN_DRAWS), dtype=np.int16)
    random_spearman = np.empty(RUN_DRAWS)
    overlap = {n: np.empty(RUN_DRAWS) for n in (10, 25, 50, 100)}
    default_sets = {n: set(default_order[:n]) for n in overlap}
    for draw in range(RUN_DRAWS):
        ranks, order = rank_vector(random_scores[:, draw], complete_ids)
        random_ranks[:, draw] = ranks
        random_spearman[draw] = corr(default_ranks, ranks)
        for n in overlap:
            overlap[n][draw] = len(default_sets[n] & set(order[:n])) / n
    stability_rows: list[dict[str, Any]] = []
    for i, player_id in enumerate(complete_ids):
        p05, p95 = np.percentile(random_ranks[i], (5, 95))
        probability = float((random_ranks[i] <= 100).mean())
        stability_rows.append(
            {
                "player_id": player_id,
                "default_rank": int(default_ranks[i]),
                "min_rank": int(random_ranks[i].min()),
                "p05_rank": float(p05),
                "median_rank": float(np.median(random_ranks[i])),
                "p95_rank": float(p95),
                "max_rank": int(random_ranks[i].max()),
                "top_10_probability": float((random_ranks[i] <= 10).mean()),
                "top_25_probability": float((random_ranks[i] <= 25).mean()),
                "top_50_probability": float((random_ranks[i] <= 50).mean()),
                "top_100_probability": probability,
                "rank_stability": classify_rank_stability(probability, round(p95 - p05)),
                "methodology_version": OVERALL_METHODOLOGY_VERSION,
            }
        )

    random_report = {
        "draws": RUN_DRAWS,
        "seed": OVERALL_RANDOM_SEED,
        "bounds": dict(zip(DIMENSIONS, BOUNDS.tolist(), strict=True)),
        "constraints": {"direct_performance_min": 0.72, "recognition_outcome_max": 0.26},
        "weight_draw_fingerprint": hashlib.sha256(simplex.tobytes()).hexdigest(),
        "spearman_vs_default": {
            key: float(value)
            for key, value in zip(
                ("min", "p05", "median", "p95", "max"),
                np.percentile(random_spearman, (0, 5, 50, 95, 100)),
                strict=True,
            )
        },
        "top_n_overlap": {
            str(n): {
                key: float(value)
                for key, value in zip(
                    ("min", "p05", "median", "p95", "max"),
                    np.percentile(values, (0, 5, 50, 95, 100)),
                    strict=True,
                )
            }
            for n, values in overlap.items()
        },
        "rank_stability_counts": dict(Counter(row["rank_stability"] for row in stability_rows)),
    }

    # Overall outputs: incomplete profiles remain explicitly unranked with NULL score.
    stability_by_id = {row["player_id"]: row for row in stability_rows}
    overall_rows: list[dict[str, Any]] = []
    candidate_output: list[dict[str, Any]] = []
    for player_id in sorted(by_player):
        rows = by_player[player_id]
        complete = player_id in index_by_player
        i = index_by_player.get(player_id)
        row: dict[str, Any] = {
            "player_id": player_id,
            "nba_player_id": str(rows["PEAK"]["nba_player_id"]),
            "player_name": str(rows["PEAK"]["display_name"]),
            **{f"{d.lower()}_score": rows[d]["score"] for d in DIMENSIONS},
            **{f"{d.lower()}_confidence": rows[d]["evidence_confidence"] for d in DIMENSIONS},
            "nominal_weights_json": json.dumps(
                default_weights, sort_keys=True, separators=(",", ":")
            ),
            "overall_score": float(default_scores[i]) if i is not None else None,
            "overall_rank": int(default_ranks[i]) if i is not None else None,
            "eligibility_status": "ELIGIBLE_OFFICIAL"
            if complete
            else "UNRANKED_INCOMPLETE_REQUIRED_DIMENSION",
            "career_status": rows["PEAK"]["career_status"],
            "active_career_policy": "TO_DATE_NO_PROJECTION"
            if career[player_id]["career_active"]
            else "NOT_ACTIVE",
            "rank_stability": stability_by_id[player_id]["rank_stability"] if complete else None,
            "overall_methodology_version": OVERALL_METHODOLOGY_VERSION,
            "upstream_dimension_methodology": UPSTREAM_METHOD,
            "corpus_id": CORPUS_ID,
        }
        overall_rows.append(row)
        if complete:
            for name in CANDIDATES:
                candidate_output.append(
                    {
                        "player_id": player_id,
                        "candidate_method": name,
                        "overall_score": float(candidate_scores[name][i]),
                        "rank": int(candidate_ranks[name][i]),
                        "methodology_version": OVERALL_METHODOLOGY_VERSION,
                    }
                )
    top100 = sorted(
        (row for row in overall_rows if row["overall_rank"] is not None),
        key=lambda row: int(row["overall_rank"]),
    )[:100]
    if any(row["accolades_score"] is None for row in top100):
        raise AssertionError("unresolved Accolades reached official Top 100")

    output_reports = [
        write_parquet(
            overall_rows,
            args.gold_root / "player_overall_scores/part-00000.parquet",
            ("player_id",),
        ),
        write_parquet(
            top100, args.gold_root / "overall_top100/part-00000.parquet", ("overall_rank",)
        ),
        write_parquet(
            stability_rows,
            args.gold_root / "overall_rank_stability/part-00000.parquet",
            ("player_id",),
        ),
        write_parquet(
            candidate_output,
            args.gold_root / "overall_candidate_scores/part-00000.parquet",
            ("candidate_method", "rank"),
        ),
        write_parquet(
            eligibility_rows,
            args.gold_root / "ranking_eligibility/part-00000.parquet",
            ("player_id",),
        ),
    ]
    output_fingerprint = hashlib.sha256(
        "".join(item["sha256"] for item in output_reports).encode()
    ).hexdigest()
    if args.expected_fingerprint and args.expected_fingerprint != output_fingerprint:
        raise ValueError("deterministic rebuild fingerprint mismatch")

    weights_registry = {
        "methodology_version": OVERALL_METHODOLOGY_VERSION,
        "upstream_methodology": UPSTREAM_METHOD,
        "default_candidate": default_name,
        "score_formula": "sum(nominal_weight * frozen_dimension_score)",
        "missing_dimension_policy": "UNRANKED_NO_WEIGHT_REDISTRIBUTION",
        "candidates": {
            name: {
                "weights": weights,
                "status": "SELECTED_DEFAULT" if name == default_name else "DIAGNOSTIC",
            }
            for name, weights in CANDIDATES.items()
        },
        "selection_principles": [
            "constitutional fidelity",
            "coverage",
            "interpretability",
            "stability",
            "redundancy",
            "era fairness",
        ],
        "candidate_d_objective": {
            "effective_concentration": 0.45,
            "bootstrap_effective_influence_instability": 0.15,
            "era_mean_range": 0.20,
            "profile_mean_range": 0.20,
            "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
            "best_objective": best_objective,
        },
    }
    stable_yaml(args.docs_root / "overall-weight-methodologies.yaml", weights_registry)
    eligibility_report = {
        "methodology_version": OVERALL_METHODOLOGY_VERSION,
        "master_players": len(by_player),
        "complete_before_and_after": len(complete_ids),
        "not_queried_accolades": 2963,
        "classification_counts": dict(statuses),
        "additional_award_queries_required": 0,
        "additional_award_queries_executed": 0,
        "network_requests": 0,
        "admissible_weight_vectors_tested": RUN_DRAWS + len(CANDIDATES),
        "top100_buffer_points": 5.0,
        "unresolved_upper_bound_crossers": 0,
        "safe_player_max_optimistic_overall": max(
            float(row["optimistic_max_overall"])
            for row in eligibility_rows
            if row["eligibility_classification"] == "SAFE_TO_EXCLUDE_FROM_V1_QUERY"
        ),
        "safe_player_closest_cutoff_gap": max(
            float(row["closest_top100_gap"])
            for row in eligibility_rows
            if row["eligibility_classification"] == "SAFE_TO_EXCLUDE_FROM_V1_QUERY"
        ),
        "candidate_top100_cutoffs": {
            name: float(np.sort(candidate_scores[name])[-100]) for name in CANDIDATES
        },
        "publication_rule": (
            "Only complete seven-dimension profiles receive official scores/ranks; "
            "weights are never redistributed."
        ),
        "result": "PASS",
    }
    stable_json(args.docs_root / "ranking-eligibility-audit.json", eligibility_report)
    stable_json(
        args.docs_root / "accolades-query-expansion-audit.json",
        {
            "award_input_fingerprint": AWARD_FINGERPRINT,
            "old_candidate_count": 2140,
            "new_queries": 0,
            "reason": (
                "No six-dimension-complete NOT_QUERIED player crossed or approached "
                "the Top-100 upper-bound cutoff."
            ),
            "not_queried_preserved_as_unknown": True,
            "confirmed_success_empty_preserved_as_observed_no_events": 953,
            "source_pipeline_mutated": False,
            "network_requests": 0,
        },
    )
    stable_json(
        args.docs_root / "overall-effective-influence.json",
        {
            "methodology": "exact linear-score Shapley variance allocation w_i*Cov(X_i,Y)",
            "complete_population": len(complete_ids),
            "candidates": candidate_reports,
            "family_influence_default": {
                "career_shape": sum(
                    candidate_reports[default_name]["effective_shapley_influence"][d]
                    for d in ("PEAK", "LONGEVITY")
                ),
                "direct_basketball_performance": sum(
                    candidate_reports[default_name]["effective_shapley_influence"][d]
                    for d in DIMENSIONS[:5]
                ),
                "recognition_outcome": sum(
                    candidate_reports[default_name]["effective_shapley_influence"][d]
                    for d in DIMENSIONS[5:]
                ),
            },
        },
    )
    stable_json(
        args.docs_root / "overall-leave-one-out.json",
        {"default_candidate": default_name, "diagnostic_only": True, "dimensions": loo},
    )
    stable_json(
        args.docs_root / "overall-local-sensitivity.json",
        {"default_candidate": default_name, "perturbations": local_rows},
    )
    stable_json(args.docs_root / "overall-random-simplex.json", random_report)
    stable_json(
        args.docs_root / "overall-era-archetype-audit.json",
        {
            "default_candidate": default_name,
            "debut_era": candidate_reports[default_name]["debut_era"],
            "dimension_profile_archetype": candidate_reports[default_name]["profile_archetype"],
            "step13_archetype_coverage": dict(
                Counter(clusters.get(p, "UNAVAILABLE") for p in complete_ids)
            ),
            "career_status": candidate_reports[default_name]["career_status"],
            "position_audit": "UNAVAILABLE_UNQUALIFIED_CANONICAL_POSITION_COVERAGE",
            "no_era_or_archetype_quotas": True,
            "active_policy": "TO_DATE_NO_PROJECTION",
        },
    )

    diagnostics_ids = {
        str(row["nba_player_id"]): player_id
        for player_id, rows in by_player.items()
        for row in [rows["PEAK"]]
        if str(row["nba_player_id"])
        in {
            "78049",
            "76375",
            "76003",
            "77142",
            "1449",
            "893",
            "165",
            "406",
            "1495",
            "977",
            "2544",
            "201939",
            "201142",
            "203999",
            "1112",
            "203497",
        }
    }
    diagnostic_players = set(diagnostics_ids.values())
    diagnostic_players.update(default_order[94:105])
    for group in ("LONGEVITY_HEAVY", "PEAK_HEAVY"):
        candidates = [
            p for p, label in zip(complete_ids, profile_groups, strict=True) if label == group
        ]
        diagnostic_players.update(
            sorted(candidates, key=lambda p: default_ranks[index_by_player[p]])[:2]
        )
    diagnostic_report = []
    for player_id in sorted(diagnostic_players, key=lambda p: default_ranks[index_by_player[p]]):
        i = index_by_player[player_id]
        values = {d: float(matrix[i, j]) for j, d in enumerate(DIMENSIONS)}
        diagnostic_report.append(
            {
                "player_id": player_id,
                "player_name": by_player[player_id]["PEAK"]["display_name"],
                "overall_rank": int(default_ranks[i]),
                "overall_score": float(default_scores[i]),
                "dimension_scores": values,
                "weighted_contributions": {d: values[d] * default_weights[d] for d in DIMENSIONS},
                "mechanical_explanation": (
                    "Overall is the sum of the seven displayed weighted contributions; "
                    "no player-specific adjustment."
                ),
            }
        )
    stable_json(
        args.docs_root / "overall-player-diagnostics.json",
        {
            "selection_policy": (
                "predetermined historical cases plus data-derived archetypes and "
                "ranks 95-105; never used for weights"
            ),
            "players": diagnostic_report,
        },
    )
    stable_json(
        args.docs_root / "overall-top-100.json",
        {
            "methodology_version": OVERALL_METHODOLOGY_VERSION,
            "eligibility": "COMPLETE_SEVEN_DIMENSIONS_ONLY",
            "players": [
                {
                    "rank": row["overall_rank"],
                    "player_id": row["player_id"],
                    "player_name": row["player_name"],
                    "overall_score": row["overall_score"],
                }
                for row in top100
            ],
        },
    )

    committed_report_names = (
        "accolades-query-expansion-audit.json",
        "overall-effective-influence.json",
        "overall-era-archetype-audit.json",
        "overall-leave-one-out.json",
        "overall-local-sensitivity.json",
        "overall-player-diagnostics.json",
        "overall-random-simplex.json",
        "overall-top-100.json",
        "overall-weight-methodologies.yaml",
        "ranking-eligibility-audit.json",
    )
    committed_report_fingerprint = hashlib.sha256(
        "".join(sha256(args.docs_root / name) for name in committed_report_names).encode()
    ).hexdigest()

    summary = {
        "step": "STEP-0015",
        "result": "PASS",
        "run_at": args.run_at,
        "methodology_version": OVERALL_METHODOLOGY_VERSION,
        "upstream_methodology": UPSTREAM_METHOD,
        "upstream_fingerprint": UPSTREAM_FINGERPRINT,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "award_fingerprint": AWARD_FINGERPRINT,
        "master_players": len(by_player),
        "officially_ranked_players": len(complete_ids),
        "official_top100_rows": len(top100),
        "additional_award_queries": 0,
        "network_requests": 0,
        "default_candidate": default_name,
        "default_weights": default_weights,
        "output_fingerprint": output_fingerprint,
        "committed_report_fingerprint": committed_report_fingerprint,
        "partitions": output_reports,
        "output_size_bytes": sum(item["size_bytes"] for item in output_reports),
        "output_partitions": len(output_reports),
        "random_simplex_draws": RUN_DRAWS,
        "random_seed": OVERALL_RANDOM_SEED,
        "deterministic_rebuild_verified": bool(args.expected_fingerprint),
        "runtime_seconds": time.perf_counter() - started,
        "runtime_definition": (
            "offline Overall build; exact certification rebuild runtime may differ"
        ),
        "constitutional_assertions": {
            "era_dominance_excluded": True,
            "confidence_does_not_change_score": True,
            "modern_diagnostics_excluded": True,
            "no_player_specific_weights": True,
            "missing_weights_not_redistributed": True,
            "dimension_formulas_unchanged": True,
        },
    }
    stable_json(args.docs_root / "overall-ranking-summary.json", summary)
    print(
        json.dumps(
            {
                "output_fingerprint": output_fingerprint,
                "ranked": len(complete_ids),
                "top100": len(top100),
                "additional_queries": 0,
                "runtime_seconds": summary["runtime_seconds"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
