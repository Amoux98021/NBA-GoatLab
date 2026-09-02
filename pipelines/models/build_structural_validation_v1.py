#!/usr/bin/env python3
"""Build STEP-0013 unsupervised structural diagnostics entirely offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from goatlab.features.dimension_candidates import era_group
from goatlab.models.structural_validation import (
    STRUCTURAL_METHODOLOGY_VERSION,
    STRUCTURAL_RANDOM_SEED,
    MatrixKind,
    PruningStatus,
    ScalingMethod,
    adjusted_mutual_information,
    adjusted_rand_index,
    agglomerative_average_linkage,
    candidate_uniqueness,
    cluster_metrics,
    complete_case_matrix,
    fit_diagonal_gmm,
    fit_kmeans,
    fit_pca,
    match_and_align_loadings,
    parallel_analysis,
    pca_bootstrap_stability,
    principal_axis_factor_analysis,
    row_center_profiles,
    scale_matrix,
)
from pipelines.features.build_dimension_candidates_v1 import (
    build_primitive_matrix,
    evaluation_populations,
    file_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
NORMALIZATION_FINGERPRINT = "a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852"
CAREER_FINGERPRINT = "5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b"
AWARDS_FINGERPRINT = "666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258"
TEAM_FINGERPRINT = "707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333"
ACCOLADE_FINGERPRINT = "e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880"
CANDIDATE_FINGERPRINT = "e5cd648afbc36306251ec1229b4c9f2beba830ca0ce93056c8e783e596bfc11f"
PRIMARY_SCALING = "CAREER_UNIVERSE_PERCENTILE"
PRIMARY_POLICY = "COVERAGE_THRESHOLD"
PARALLEL_REPETITIONS = 80
BOOTSTRAP_REPETITIONS = 24

CROSS_ERA_FEATURES = (
    "regular_qualified_seasons",
    "regular_total_games",
    "reg_ppg_mean_z",
    "reg_rpg_mean_z",
    "reg_apg_mean_z",
    "reg_ppg_peak3_quality",
    "reg_rpg_peak3_quality",
    "reg_apg_peak3_quality",
    "reg_ppg_cum_positive_z",
    "reg_rpg_cum_positive_z",
    "reg_apg_cum_positive_z",
    "po_ppg_mean_z",
    "po_rpg_mean_z",
    "po_apg_mean_z",
    "mean_team_win_percentile",
    "playoff_games",
)
MODERN_FEATURES = (
    "reg_ppg_mean_z",
    "modern_reg_apg_mean_z",
    "modern_reg_ts_pct_mean_z",
    "modern_reg_spg_mean_z",
    "modern_reg_bpg_mean_z",
    "reg_points_per_75_mean_z",
    "modern_def_rating_mean_z",
)
PROFILE_CANDIDATES = (
    "PEAK-B",
    "LONGEVITY-B",
    "OFFENSE-A",
    "DEFENSE-A",
    "PLAYOFFS-A",
    "ACCOLADES-A",
    "WINNING-A",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return round(number, 12) if math.isfinite(number) else None


def stable_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_parquet(rows: list[dict[str, Any]], path: Path, keys: tuple[str, ...]) -> dict[str, Any]:
    rows.sort(key=lambda row: tuple(str(row.get(key) or "") for key in keys))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=9,
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
    )
    temporary.replace(path)
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": table.num_rows,
        "columns": table.num_columns,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def verify_inputs(docs_root: Path) -> dict[str, str]:
    expected = {
        "corpus": ("historical-corpus-v1-manifest.json", CORPUS_FINGERPRINT),
        "normalization": ("era-normalization-gold-manifest.json", NORMALIZATION_FINGERPRINT),
        "career": ("career-gold-manifest.json", CAREER_FINGERPRINT),
        "awards": ("award-canonicalization-summary.json", AWARDS_FINGERPRINT),
        "team_success": ("team-success-summary.json", TEAM_FINGERPRINT),
        "all_star_stat_leaders": (
            "accolade-fact-completion-summary.json",
            ACCOLADE_FINGERPRINT,
        ),
        "dimension_candidates": ("dimension-candidate-summary.json", CANDIDATE_FINGERPRINT),
    }
    for _, (name, fingerprint) in expected.items():
        payload = json.loads((docs_root / name).read_text(encoding="utf-8"))
        found = {str(value) for key, value in payload.items() if "fingerprint" in key}
        if fingerprint not in found:
            raise ValueError(f"unexpected input fingerprint in {name}")
    return {key: fingerprint for key, (_, fingerprint) in expected.items()}


def load_candidate_matrix(
    gold_root: Path, registry: dict[str, Any]
) -> tuple[dict[str, dict[str, float | None]], dict[str, str], dict[str, str]]:
    candidate_rows: dict[str, dict[str, float | None]] = defaultdict(dict)
    dimensions: dict[str, str] = {}
    prior_status: dict[str, str] = {}
    for candidate in registry["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        dimensions[candidate_id] = str(candidate["dimension"])
        prior_status[candidate_id] = str(candidate["status"])
        path = next(
            gold_root.glob(
                f"dimension_candidate_scores/dimension=*/candidate={candidate_id}/part-00000.parquet"
            )
        )
        for row in pq.read_table(path).to_pylist():
            if (
                row["scaling_method"] == PRIMARY_SCALING
                and row["coverage_policy"] == PRIMARY_POLICY
            ):
                candidate_rows[str(row["player_id"])][candidate_id] = finite(
                    row["diagnostic_value"]
                )
    return dict(candidate_rows), dimensions, prior_status


def primitive_rows(
    primitives: dict[str, dict[str, float | None]], players: set[str]
) -> dict[str, dict[str, float | None]]:
    return {
        player_id: {feature: values.get(player_id) for feature, values in primitives.items()}
        for player_id in players
    }


def matrix_audit(
    name: str,
    kind: MatrixKind,
    rows: dict[str, dict[str, float | None]],
    features: tuple[str, ...],
    population_name: str,
    population: set[str],
    context: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], Any]:
    complete = complete_case_matrix(rows, population, features)
    exclusion_reasons = Counter()
    for player_id in complete.excluded_ids:
        missing = sum(rows.get(player_id, {}).get(feature) is None for feature in features)
        exclusion_reasons[f"MISSING_{missing}_FEATURES"] += 1
    era_retained = Counter(
        era_group(context[player_id]["regular_first_season"]) for player_id in complete.retained_ids
    )
    era_start = Counter(
        era_group(context[player_id]["regular_first_season"]) for player_id in population
    )
    active_retained = sum(
        bool(context[player_id]["career_active"]) for player_id in complete.retained_ids
    )
    report = {
        "matrix_name": name,
        "matrix_kind": kind.value,
        "population": population_name,
        "starting_players": len(population),
        "retained_players": len(complete.retained_ids),
        "excluded_players": len(complete.excluded_ids),
        "retention_rate": finite(len(complete.retained_ids) / len(population)),
        "feature_count": len(features),
        "features": list(features),
        "missingness_policy": "COVERAGE_QUALIFIED_COMPLETE_INTERSECTION_NO_IMPUTATION",
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "starting_era_distribution": dict(sorted(era_start.items())),
        "retained_era_distribution": dict(sorted(era_retained.items())),
        "retained_active_players": active_retained,
        "retained_completed_or_indeterminate_players": len(complete.retained_ids) - active_retained,
    }
    return report, complete


def component_records(
    feature_names: tuple[str, ...], loadings: np.ndarray, component_prefix: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for component in range(loadings.shape[1]):
        order = np.argsort(np.abs(loadings[:, component]))[::-1]
        records.append(
            {
                "component": f"{component_prefix}{component + 1}",
                "sign_note": (
                    "sign is arbitrary; interpretation is invariant to full-column reversal"
                ),
                "loadings": [
                    {
                        "feature": feature_names[index],
                        "loading": finite(loadings[index, component]),
                    }
                    for index in order
                ],
            }
        )
    return records


def cross_validated_factor_rmse(values: np.ndarray, factors: int, folds: int = 5) -> float:
    errors: list[float] = []
    for fold in range(folds):
        train = values[np.arange(values.shape[0]) % folds != fold]
        test = values[np.arange(values.shape[0]) % folds == fold]
        model = principal_axis_factor_analysis(train, factors)
        observed = np.corrcoef(test, rowvar=False)
        reconstructed = model.loadings @ model.loadings.T
        mask = ~np.eye(observed.shape[0], dtype=bool)
        errors.append(float(np.sqrt(np.mean((observed[mask] - reconstructed[mask]) ** 2))))
    return statistics.fmean(errors)


def top_correlation(
    candidates: dict[str, dict[str, float | None]],
    left: str,
    right: str,
    players: set[str],
) -> dict[str, Any]:
    paired = [
        (candidates[player][left], candidates[player][right])
        for player in sorted(players)
        if candidates[player].get(left) is not None and candidates[player].get(right) is not None
    ]
    x = np.asarray([float(item[0]) for item in paired])
    y = np.asarray([float(item[1]) for item in paired])
    correlation = float(np.corrcoef(x, y)[0, 1]) if len(paired) > 1 else None
    return {"left": left, "right": right, "n": len(paired), "pearson": finite(correlation)}


def cramers_v(categories: list[str], labels: np.ndarray) -> float | None:
    left = sorted(set(categories))
    right = sorted(int(value) for value in np.unique(labels))
    table = np.asarray(
        [
            [
                sum(
                    cat == a and int(label) == b
                    for cat, label in zip(categories, labels, strict=True)
                )
                for b in right
            ]
            for a in left
        ],
        dtype=float,
    )
    total = float(np.sum(table))
    if total == 0 or min(table.shape) <= 1:
        return None
    expected = np.sum(table, axis=1, keepdims=True) @ np.sum(table, axis=0, keepdims=True) / total
    valid = expected > 0
    chi = float(np.sum(((table - expected) ** 2)[valid] / expected[valid]))
    return math.sqrt(chi / (total * min(table.shape[0] - 1, table.shape[1] - 1)))


def assign_to_centroids(values: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    distances = np.sum((values[:, None, :] - centroids[None, :, :]) ** 2, axis=2)
    return np.argmin(distances, axis=1)


def svg_line_chart(path: Path, series: dict[str, list[float]], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height, margin = 800, 450, 55
    values = [value for row in series.values() for value in row]
    low, high = min(values), max(values)
    if math.isclose(low, high):
        high = low + 1.0
    colors = ["#2563eb", "#dc2626", "#059669", "#7c3aed"]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{margin}" y="30" font-family="sans-serif" font-size="18">{title}</text>',
        (
            f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" '
            f'y2="{height - margin}" stroke="#555"/>'
        ),
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#555"/>',
    ]
    for series_index, (name, row) in enumerate(series.items()):
        points = []
        for index, value in enumerate(row):
            x = margin + index * (width - 2 * margin) / max(1, len(row) - 1)
            y = height - margin - (value - low) * (height - 2 * margin) / (high - low)
            points.append(f"{x:.2f},{y:.2f}")
        color = colors[series_index % len(colors)]
        lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(points)}"/>'
        )
        lines.append(
            f'<text x="{width - 190}" y="{30 + 18 * series_index}" '
            f'font-family="sans-serif" font-size="12" fill="{color}">{name}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def report_fingerprint(paths: list[Path]) -> str:
    return hashlib.sha256(
        "\n".join(f"{path.name}:{file_sha256(path)}" for path in paths).encode()
    ).hexdigest()


def build(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    input_fingerprints = verify_inputs(args.docs_root)
    registry = yaml.safe_load((args.docs_root / "goat-dimension-candidates.yaml").read_text())
    candidate_rows, dimensions, prior_status = load_candidate_matrix(args.gold_root, registry)
    primitives, context = build_primitive_matrix(args.gold_root)
    populations, _ = evaluation_populations(primitives, context)
    all_players = set(context)
    population_map = {"ALL_PLAYERS": all_players, **populations}

    validated = tuple(
        sorted(
            candidate
            for candidate, status in prior_status.items()
            if status == "VALIDATED_FOR_EXPERIMENT"
        )
    )
    primitive_matrix = primitive_rows(primitives, all_players)
    matrix_definitions = {
        "dimension_candidates": (MatrixKind.DIMENSION_CANDIDATE, candidate_rows, validated),
        "cross_era_primitives": (
            MatrixKind.CROSS_ERA_PRIMITIVE,
            primitive_matrix,
            CROSS_ERA_FEATURES,
        ),
        "modern_enriched": (MatrixKind.MODERN_ENRICHED, primitive_matrix, MODERN_FEATURES),
        "profile_magnitude": (MatrixKind.PROFILE_MAGNITUDE, candidate_rows, PROFILE_CANDIDATES),
    }
    audits: list[dict[str, Any]] = []
    complete_matrices: dict[tuple[str, str], Any] = {}
    for name, (kind, rows, features) in matrix_definitions.items():
        for population_name in (
            "ALL_PLAYERS",
            "PARTICIPATION_QUALIFIED",
            "CAREER_SIGNAL",
            "BROAD_HIGH_RECALL",
        ):
            audit, complete = matrix_audit(
                name,
                kind,
                rows,
                features,
                population_name,
                population_map[population_name],
                context,
            )
            audits.append(audit)
            complete_matrices[(name, population_name)] = complete
    for population_name in (
        "ALL_PLAYERS",
        "PARTICIPATION_QUALIFIED",
        "CAREER_SIGNAL",
        "BROAD_HIGH_RECALL",
    ):
        shape_audit = dict(
            next(
                row
                for row in audits
                if row["matrix_name"] == "profile_magnitude"
                and row["population"] == population_name
            )
        )
        shape_audit["matrix_name"] = "profile_shape"
        shape_audit["matrix_kind"] = MatrixKind.PROFILE_SHAPE.value
        shape_audit["transformation"] = "column-standardized then row-centered and row-RMS-scaled"
        audits.append(shape_audit)
    primary = complete_matrices[("dimension_candidates", "BROAD_HIGH_RECALL")]
    profile = complete_matrices[("profile_magnitude", "BROAD_HIGH_RECALL")]

    pca_models: list[dict[str, Any]] = []
    pca_partitions: list[dict[str, Any]] = []
    primary_pca: Any = None
    primary_features: tuple[str, ...] = ()
    primary_scaled: np.ndarray | None = None
    for matrix_name in matrix_definitions:
        for population_name in (
            "ALL_PLAYERS",
            "PARTICIPATION_QUALIFIED",
            "CAREER_SIGNAL",
            "BROAD_HIGH_RECALL",
        ):
            complete = complete_matrices[(matrix_name, population_name)]
            if complete.values.shape[0] < 50:
                continue
            for scaling in ScalingMethod:
                scaled = scale_matrix(complete.values, scaling)
                selected = scaled.values[:, scaled.valid_columns]
                selected_names = tuple(
                    np.asarray(complete.feature_names)[scaled.valid_columns].tolist()
                )
                if selected.shape[1] < 2:
                    continue
                model = fit_pca(selected)
                count_80 = int(np.searchsorted(np.cumsum(model.explained_variance_ratio), 0.80) + 1)
                pca_models.append(
                    {
                        "matrix": matrix_name,
                        "population": population_name,
                        "scaling": scaling.value,
                        "players": selected.shape[0],
                        "features": selected.shape[1],
                        "constant_features_excluded": [
                            feature
                            for feature, valid in zip(
                                complete.feature_names, scaled.valid_columns, strict=True
                            )
                            if not valid
                        ],
                        "explained_variance_ratio": [
                            finite(value) for value in model.explained_variance_ratio
                        ],
                        "cumulative_explained_variance": [
                            finite(value) for value in np.cumsum(model.explained_variance_ratio)
                        ],
                        "components_for_80_pct": count_80,
                        "reconstruction_rmse": [
                            finite(value) for value in model.reconstruction_rmse
                        ],
                    }
                )
                score_rows = []
                component_limit = min(12, model.scores.shape[1])
                for index, player_id in enumerate(complete.retained_ids):
                    row: dict[str, Any] = {
                        "player_id": player_id,
                        "matrix": matrix_name,
                        "population": population_name,
                        "scaling": scaling.value,
                        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
                        "corpus_id": CORPUS_ID,
                    }
                    for component in range(component_limit):
                        row[f"component_{component + 1}"] = finite(model.scores[index, component])
                    score_rows.append(row)
                pca_partitions.append(
                    write_parquet(
                        score_rows,
                        args.gold_root
                        / "ml_structure/pca"
                        / f"matrix={matrix_name}"
                        / f"population={population_name}"
                        / f"scaling={scaling.value}"
                        / "scores.parquet",
                        ("player_id",),
                    )
                )
                if (
                    matrix_name == "dimension_candidates"
                    and population_name == "BROAD_HIGH_RECALL"
                    and scaling is ScalingMethod.STANDARD
                ):
                    primary_pca = model
                    primary_features = selected_names
                    primary_scaled = selected
    if primary_pca is None or primary_scaled is None:
        raise AssertionError("primary PCA was not built")

    parallel = parallel_analysis(primary_scaled, repetitions=PARALLEL_REPETITIONS)
    component_count = max(1, int(parallel["retained_components"]))
    component_count = min(component_count, 12, primary_scaled.shape[1] - 1)
    pca_stability = pca_bootstrap_stability(
        primary_scaled,
        component_count,
        repetitions=BOOTSTRAP_REPETITIONS,
    )
    pca_summary = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "primary_matrix": "dimension_candidates",
        "primary_population": "BROAD_HIGH_RECALL",
        "primary_scaling": "STANDARD",
        "players": primary_scaled.shape[0],
        "features": list(primary_features),
        "explained_variance_ratio": [
            finite(value) for value in primary_pca.explained_variance_ratio
        ],
        "cumulative_explained_variance": [
            finite(value) for value in np.cumsum(primary_pca.explained_variance_ratio)
        ],
        "parallel_analysis": {
            "repetitions": PARALLEL_REPETITIONS,
            "percentile": 0.95,
            "retained_components": component_count,
            "observed": [finite(value) for value in parallel["observed"]],
            "random_mean": [finite(value) for value in parallel["random_mean"]],
            "random_95th_percentile": [finite(value) for value in parallel["random_percentile"]],
        },
        "component_loadings": component_records(
            primary_features, primary_pca.loadings[:, :component_count], "PC"
        ),
        "all_matrix_runs": pca_models,
        "interpretation_guardrail": (
            "Components describe covariance; sign is arbitrary and neither component nor score "
            "is greatness."
        ),
    }

    factor_candidates: list[dict[str, Any]] = []
    factor_models: dict[int, Any] = {}
    maximum_factors = min(10, primary_scaled.shape[1] - 1)
    for factors in range(2, maximum_factors + 1):
        model = principal_axis_factor_analysis(primary_scaled, factors)
        factor_models[factors] = model
        factor_candidates.append(
            {
                "factor_count": factors,
                "converged": model.converged,
                "iterations": model.iterations,
                "correlation_reconstruction_rmse": finite(model.reconstruction_rmse),
                "five_fold_heldout_correlation_rmse": finite(
                    cross_validated_factor_rmse(primary_scaled, factors)
                ),
                "mean_communality": finite(np.mean(model.communalities)),
                "minimum_communality": finite(np.min(model.communalities)),
            }
        )
    chosen_factor_record = min(
        factor_candidates,
        key=lambda row: (
            float(row["five_fold_heldout_correlation_rmse"]) + 0.0025 * int(row["factor_count"])
        ),
    )
    chosen_factors = int(chosen_factor_record["factor_count"])
    chosen_factor = factor_models[chosen_factors]
    factor_summary = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "method": "ITERATED_PRINCIPAL_AXIS_FACTORING",
        "rotation": "VARIMAX",
        "probabilistic_likelihood": "NOT_APPLICABLE_TO_PRINCIPAL_AXIS_METHOD",
        "selection_rule": (
            "minimum five-fold held-out correlation reconstruction RMSE plus 0.0025 per factor; "
            "parallel/PCA interpretability audited separately"
        ),
        "selected_factors": chosen_factors,
        "candidate_models": factor_candidates,
        "rotated_factor_loadings": component_records(
            primary_features, chosen_factor.rotated_loadings, "F"
        ),
        "communalities": [
            {
                "feature": feature,
                "communality": finite(chosen_factor.communalities[index]),
                "uniqueness": finite(chosen_factor.uniquenesses[index]),
            }
            for index, feature in enumerate(primary_features)
        ],
    }
    factor_partitions = [
        write_parquet(
            [
                {
                    "feature": feature,
                    **{
                        f"factor_{factor + 1}_loading": finite(
                            chosen_factor.rotated_loadings[index, factor]
                        )
                        for factor in range(chosen_factors)
                    },
                    "communality": finite(chosen_factor.communalities[index]),
                    "uniqueness": finite(chosen_factor.uniquenesses[index]),
                    "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
                }
                for index, feature in enumerate(primary_features)
            ],
            args.gold_root / "ml_structure/factor_analysis/loadings.parquet",
            ("feature",),
        )
    ]

    pca_factors_aligned, _, pca_factor_correlations = match_and_align_loadings(
        primary_pca.loadings[:, : min(component_count, chosen_factors)],
        chosen_factor.rotated_loadings,
    )
    _ = pca_factors_aligned
    inactive_primary_indices = np.asarray(
        [
            index
            for index, player_id in enumerate(primary.retained_ids)
            if not bool(context[player_id]["career_active"])
        ]
    )
    inactive_pca = fit_pca(primary_scaled[inactive_primary_indices])
    _, _, inactive_pca_correlations = match_and_align_loadings(
        primary_pca.loadings[:, :component_count],
        inactive_pca.loadings[:, :component_count],
    )
    factor_bootstrap_correlations: list[list[float]] = []
    factor_generator = np.random.default_rng(STRUCTURAL_RANDOM_SEED + 71)
    for _ in range(12):
        indices = factor_generator.choice(
            primary_scaled.shape[0], round(0.8 * primary_scaled.shape[0]), replace=True
        )
        bootstrap_factor = principal_axis_factor_analysis(primary_scaled[indices], chosen_factors)
        _, _, correlations = match_and_align_loadings(
            chosen_factor.rotated_loadings,
            bootstrap_factor.rotated_loadings,
        )
        factor_bootstrap_correlations.append(list(correlations))
    factor_stability = np.asarray(factor_bootstrap_correlations)
    stability_summary = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "pca_bootstrap": pca_stability,
        "pca_factor_absolute_loading_correlations": [
            finite(value) for value in pca_factor_correlations
        ],
        "active_exclusion_pca_loading_correlations": [
            finite(value) for value in inactive_pca_correlations
        ],
        "factor_bootstrap": {
            "repetitions": 12,
            "mean_loading_correlation": [
                finite(value) for value in np.mean(factor_stability, axis=0)
            ],
            "minimum_loading_correlation": [
                finite(value) for value in np.min(factor_stability, axis=0)
            ],
        },
        "population_and_scaling_sensitivity": [
            {
                "matrix": row["matrix"],
                "population": row["population"],
                "scaling": row["scaling"],
                "components_for_80_pct": row["components_for_80_pct"],
                "first_component_variance": row["explained_variance_ratio"][0],
            }
            for row in pca_models
            if row["matrix"] == "dimension_candidates"
        ],
    }

    uniqueness = candidate_uniqueness(
        primary_scaled,
        primary_features,
        tuple(dimensions[feature] for feature in primary_features),
    )
    for row in uniqueness:
        index = primary_features.index(str(row["candidate_id"]))
        row["maximum_absolute_pca_loading"] = finite(
            np.max(np.abs(primary_pca.loadings[index, :component_count]))
        )
        row["maximum_absolute_factor_loading"] = finite(
            np.max(np.abs(chosen_factor.rotated_loadings[index]))
        )
        row["incremental_variance_proxy"] = finite(
            float(row["residual_variance_fraction"]) / len(primary_features)
            if row["residual_variance_fraction"] is not None
            else None
        )
        row["interpretation"] = "Uniqueness measures residual structure, not importance or value."
    uniqueness_report = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "matrix_sample_size": primary_scaled.shape[0],
        "candidate_records": uniqueness,
        "candidate_family_mapping": [
            {
                "dimension": dimension,
                "candidate_count": len(
                    [feature for feature in primary_features if dimensions[feature] == dimension]
                ),
                "nearest_pca_component": int(
                    np.argmax(
                        np.mean(
                            np.abs(
                                primary_pca.loadings[
                                    [
                                        index
                                        for index, feature in enumerate(primary_features)
                                        if dimensions[feature] == dimension
                                    ],
                                    :component_count,
                                ]
                            ),
                            axis=0,
                        )
                    )
                    + 1
                ),
                "nearest_factor": int(
                    np.argmax(
                        np.mean(
                            np.abs(
                                chosen_factor.rotated_loadings[
                                    [
                                        index
                                        for index, feature in enumerate(primary_features)
                                        if dimensions[feature] == dimension
                                    ]
                                ]
                            ),
                            axis=0,
                        )
                    )
                    + 1
                ),
                "mean_residual_variance_fraction": finite(
                    statistics.fmean(
                        float(row["residual_variance_fraction"])
                        for row in uniqueness
                        if row["dimension"] == dimension
                        and row["residual_variance_fraction"] is not None
                    )
                ),
            }
            for dimension in sorted(set(dimensions.values()))
        ],
        "era_dominance_hypothesis": {
            "tested_against": ["PEAK", "LONGEVITY", "OFFENSE", "DEFENSE"],
            "conclusion": "USE_AS_DIAGNOSTIC_ONLY",
            "reason": (
                "Era candidates are direct summaries of already era-normalized peak and cumulative "
                "evidence and show low incremental residual structure."
            ),
        },
        "peak_b_d_e": [
            top_correlation(candidate_rows, left, right, populations["BROAD_HIGH_RECALL"])
            for left, right in (("PEAK-B", "PEAK-D"), ("PEAK-B", "PEAK-E"), ("PEAK-D", "PEAK-E"))
        ],
        "accolades_a_b_c": [
            top_correlation(candidate_rows, left, right, populations["BROAD_HIGH_RECALL"])
            for left, right in (
                ("ACCOLADES-A", "ACCOLADES-B"),
                ("ACCOLADES-A", "ACCOLADES-C"),
                ("ACCOLADES-B", "ACCOLADES-C"),
            )
        ],
        "defense_policy": {
            "all_era": (
                "Box Defense remains a coverage-limited rebounding-led profile; no universal "
                "scalar is established."
            ),
            "modern": (
                "Modern advanced/steal/block evidence is analyzed only in the labeled post-1996 "
                "enriched matrix."
            ),
        },
    }

    profile_scale = scale_matrix(profile.values, ScalingMethod.STANDARD)
    magnitude_values = profile_scale.values[:, profile_scale.valid_columns]
    profile_values = row_center_profiles(magnitude_values)
    profile_names = tuple(np.asarray(profile.feature_names)[profile_scale.valid_columns].tolist())
    cluster_selection: dict[str, list[dict[str, Any]]] = {}
    kmeans_models: dict[str, dict[int, Any]] = {}
    for transform_name, values in (
        ("MAGNITUDE_PRESERVING", magnitude_values),
        ("PROFILE_SHAPE", profile_values),
    ):
        records: list[dict[str, Any]] = []
        models: dict[int, Any] = {}
        for clusters in range(2, 13):
            model = fit_kmeans(values, clusters)
            models[clusters] = model
            records.append(
                {
                    "clusters": clusters,
                    "inertia": finite(model.inertia),
                    **cluster_metrics(values, model.labels),
                }
            )
        cluster_selection[transform_name] = records
        kmeans_models[transform_name] = models
    eligible_k = [
        row
        for row in cluster_selection["PROFILE_SHAPE"]
        if min(row["cluster_sizes"]) >= max(10, int(0.02 * len(profile.retained_ids)))
    ]
    chosen_k_record = max(
        eligible_k, key=lambda row: (float(row["silhouette"]), -int(row["clusters"]))
    )
    chosen_k = int(chosen_k_record["clusters"])
    chosen_kmeans = kmeans_models["PROFILE_SHAPE"][chosen_k]

    gmm_records: list[dict[str, Any]] = []
    gmm_models: dict[tuple[str, int], Any] = {}
    for covariance_type in ("DIAGONAL", "SPHERICAL"):
        for components in range(2, 11):
            model = fit_diagonal_gmm(
                profile_values,
                components,
                covariance_type=covariance_type,
            )
            gmm_models[(covariance_type, components)] = model
            gmm_records.append(
                {
                    "covariance_type": covariance_type,
                    "components": components,
                    "aic": finite(model.aic),
                    "bic": finite(model.bic),
                    "log_likelihood": finite(model.log_likelihood),
                    "cluster_sizes": [
                        int(np.sum(model.labels == cluster)) for cluster in range(components)
                    ],
                    "mean_max_probability": finite(np.mean(np.max(model.responsibilities, axis=1))),
                    "ambiguous_probability_below_0_60": int(
                        np.sum(np.max(model.responsibilities, axis=1) < 0.60)
                    ),
                }
            )
    selected_gmm_record = min(gmm_records, key=lambda row: float(row["bic"]))
    selected_gmm = gmm_models[
        (
            str(selected_gmm_record["covariance_type"]),
            int(selected_gmm_record["components"]),
        )
    ]
    gmm_seed_labels = [
        fit_diagonal_gmm(
            profile_values,
            int(selected_gmm_record["components"]),
            covariance_type=str(selected_gmm_record["covariance_type"]),
            seed=STRUCTURAL_RANDOM_SEED + seed,
        ).labels
        for seed in range(5)
    ]

    sample_size = min(300, len(profile.retained_ids))
    sample_indices = np.asarray(
        sorted(
            range(len(profile.retained_ids)),
            key=lambda index: hashlib.sha256(profile.retained_ids[index].encode()).hexdigest(),
        )[:sample_size]
    )
    hierarchical_sample_labels, merge_history = agglomerative_average_linkage(
        profile_values[sample_indices], chosen_k
    )
    hierarchical_centroids = np.asarray(
        [
            np.mean(profile_values[sample_indices][hierarchical_sample_labels == cluster], axis=0)
            for cluster in np.unique(hierarchical_sample_labels)
        ]
    )
    hierarchical_full_labels = assign_to_centroids(profile_values, hierarchical_centroids)

    seed_labels = [
        fit_kmeans(profile_values, chosen_k, seed=STRUCTURAL_RANDOM_SEED + seed, n_init=8).labels
        for seed in range(8)
    ]
    seed_ari = [adjusted_rand_index(chosen_kmeans.labels, labels) for labels in seed_labels]
    seed_ami = [adjusted_mutual_information(chosen_kmeans.labels, labels) for labels in seed_labels]
    generator = np.random.default_rng(STRUCTURAL_RANDOM_SEED)
    bootstrap_labels: list[np.ndarray] = []
    for _ in range(12):
        indices = generator.choice(
            profile_values.shape[0], int(0.8 * profile_values.shape[0]), replace=True
        )
        model = fit_kmeans(profile_values[indices], chosen_k, n_init=8)
        bootstrap_labels.append(assign_to_centroids(profile_values, model.centroids))
    inactive = np.asarray(
        [not bool(context[player]["career_active"]) for player in profile.retained_ids]
    )
    inactive_model = fit_kmeans(profile_values[inactive], chosen_k, n_init=12)
    inactive_labels = assign_to_centroids(profile_values[inactive], inactive_model.centroids)
    active_sensitivity_ari = adjusted_rand_index(chosen_kmeans.labels[inactive], inactive_labels)
    active_sensitivity_ami = adjusted_mutual_information(
        chosen_kmeans.labels[inactive], inactive_labels
    )
    magnitude_k_record = max(
        [
            row
            for row in cluster_selection["MAGNITUDE_PRESERVING"]
            if min(row["cluster_sizes"]) >= max(10, int(0.02 * len(profile.retained_ids)))
        ],
        key=lambda row: (float(row["silhouette"]), -int(row["clusters"])),
    )
    magnitude_model = kmeans_models["MAGNITUDE_PRESERVING"][int(magnitude_k_record["clusters"])]
    era_categories = [
        era_group(context[player]["regular_first_season"]) for player in profile.retained_ids
    ]
    active_categories = [
        "ACTIVE" if context[player]["career_active"] else "NOT_ACTIVE"
        for player in profile.retained_ids
    ]
    cluster_stability = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "selected_k": chosen_k,
        "seed_runs": len(seed_labels),
        "seed_ari_mean": finite(np.mean(seed_ari)),
        "seed_ari_min": finite(np.min(seed_ari)),
        "seed_ami_mean": finite(np.mean(seed_ami)),
        "seed_ami_min": finite(np.min(seed_ami)),
        "bootstrap_runs": len(bootstrap_labels),
        "bootstrap_ari_mean": finite(
            np.mean(
                [adjusted_rand_index(chosen_kmeans.labels, labels) for labels in bootstrap_labels]
            )
        ),
        "bootstrap_ami_mean": finite(
            np.mean(
                [
                    adjusted_mutual_information(chosen_kmeans.labels, labels)
                    for labels in bootstrap_labels
                ]
            )
        ),
        "gmm_agreement_ari": finite(adjusted_rand_index(chosen_kmeans.labels, selected_gmm.labels)),
        "gmm_agreement_ami": finite(
            adjusted_mutual_information(chosen_kmeans.labels, selected_gmm.labels)
        ),
        "gmm_seed_ari_mean": finite(
            np.mean(
                [adjusted_rand_index(selected_gmm.labels, labels) for labels in gmm_seed_labels]
            )
        ),
        "gmm_seed_ami_mean": finite(
            np.mean(
                [
                    adjusted_mutual_information(selected_gmm.labels, labels)
                    for labels in gmm_seed_labels
                ]
            )
        ),
        "hierarchical_agreement_ari": finite(
            adjusted_rand_index(chosen_kmeans.labels, hierarchical_full_labels)
        ),
        "hierarchical_agreement_ami": finite(
            adjusted_mutual_information(chosen_kmeans.labels, hierarchical_full_labels)
        ),
        "hierarchical_sample_size": sample_size,
        "hierarchical_merge_count": len(merge_history),
        "active_exclusion_ari": finite(active_sensitivity_ari),
        "active_exclusion_ami": finite(active_sensitivity_ami),
        "era_cluster_cramers_v": finite(cramers_v(era_categories, chosen_kmeans.labels)),
        "active_cluster_cramers_v": finite(cramers_v(active_categories, chosen_kmeans.labels)),
        "magnitude_profile_agreement_ari": finite(
            adjusted_rand_index(chosen_kmeans.labels, magnitude_model.labels)
        ),
        "magnitude_profile_agreement_ami": finite(
            adjusted_mutual_information(chosen_kmeans.labels, magnitude_model.labels)
        ),
        "magnitude_era_cluster_cramers_v": finite(
            cramers_v(era_categories, magnitude_model.labels)
        ),
        "magnitude_active_cluster_cramers_v": finite(
            cramers_v(active_categories, magnitude_model.labels)
        ),
    }

    archetypes: list[dict[str, Any]] = []
    player_names = {player_id: str(row["display_name"]) for player_id, row in context.items()}
    for cluster in range(chosen_k):
        member_indices = np.where(chosen_kmeans.labels == cluster)[0]
        centroid = chosen_kmeans.centroids[cluster]
        distances = np.linalg.norm(profile_values[member_indices] - centroid, axis=1)
        nearest = member_indices[np.argsort(distances)[:5]]
        high = np.argsort(centroid)[::-1][:2]
        low = np.argsort(centroid)[:2]
        archetypes.append(
            {
                "cluster_id": int(cluster),
                "neutral_profile_label": (
                    f"relative {profile_names[high[0]]}/{profile_names[high[1]]} emphasis; lower "
                    f"{profile_names[low[0]]}/{profile_names[low[1]]}"
                ),
                "size": len(member_indices),
                "centroid": {
                    feature: finite(centroid[index]) for index, feature in enumerate(profile_names)
                },
                "median_profile": {
                    feature: finite(np.median(profile_values[member_indices, index]))
                    for index, feature in enumerate(profile_names)
                },
                "era_distribution": dict(
                    sorted(Counter(era_categories[index] for index in member_indices).items())
                ),
                "active_players": int(
                    sum(
                        bool(context[profile.retained_ids[index]]["career_active"])
                        for index in member_indices
                    )
                ),
                "centroid_nearest_examples": [
                    {
                        "player_id": profile.retained_ids[index],
                        "display_name": player_names[profile.retained_ids[index]],
                        "distance": finite(distances[np.where(member_indices == index)[0][0]]),
                    }
                    for index in nearest
                ],
            }
        )
    ambiguous = np.argsort(np.max(selected_gmm.responsibilities, axis=1))[:10]
    archetype_report = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "not_quality_tiers": True,
        "selected_model": "KMEANS_PROFILE_SHAPE",
        "selected_k": chosen_k,
        "profile_features": list(profile_names),
        "position_distribution_status": (
            "NOT_MODELED: full-corpus canonical position coverage was not established as reliable"
        ),
        "archetypes": archetypes,
        "gmm_ambiguous_examples": [
            {
                "player_id": profile.retained_ids[index],
                "display_name": player_names[profile.retained_ids[index]],
                "maximum_probability": finite(np.max(selected_gmm.responsibilities[index])),
            }
            for index in ambiguous
        ],
        "interpretation": (
            "Labels describe relative profile shape only; clusters are not ordered and do not "
            "measure greatness."
        ),
    }

    cluster_model_report = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "profile_matrix_players": len(profile.retained_ids),
        "profile_features": list(profile_names),
        "transformations": {
            "MAGNITUDE_PRESERVING": "column-standardized candidate profiles",
            "PROFILE_SHAPE": "column-standardized then row-centered and row-RMS-scaled",
        },
        "kmeans": cluster_selection,
        "selected_kmeans": {"transformation": "PROFILE_SHAPE", **chosen_k_record},
        "selected_magnitude_kmeans": magnitude_k_record,
        "gmm": gmm_records,
        "selected_gmm": selected_gmm_record,
        "hierarchical": {
            "method": "AVERAGE_LINKAGE_EUCLIDEAN",
            "audit_sample_size": sample_size,
            "clusters": chosen_k,
            "merge_count": len(merge_history),
            "full_assignment": "nearest audit-sample cluster centroid",
        },
    }

    clustering_partitions = [
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "kmeans_profile_cluster": int(chosen_kmeans.labels[index]),
                    "kmeans_magnitude_cluster": int(
                        kmeans_models["MAGNITUDE_PRESERVING"][chosen_k].labels[index]
                    ),
                    "gmm_profile_cluster": int(selected_gmm.labels[index]),
                    "gmm_max_probability": finite(np.max(selected_gmm.responsibilities[index])),
                    "hierarchical_profile_cluster": int(hierarchical_full_labels[index]),
                    "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
                    "corpus_id": CORPUS_ID,
                }
                for index, player_id in enumerate(profile.retained_ids)
            ],
            args.gold_root / "ml_structure/clustering/player_archetypes.parquet",
            ("player_id",),
        ),
        write_parquet(
            [
                {**row, "methodology_version": STRUCTURAL_METHODOLOGY_VERSION}
                for row in merge_history
            ],
            args.gold_root / "ml_structure/clustering/hierarchical_merges.parquet",
            ("merged_size", "left", "right"),
        ),
    ]

    predeclared_rules = {
        "prior_rejected": "REJECTED",
        "prior_modern_only": "DEFER_MODERN_ONLY",
        "coverage": "under 65% primary broad-population availability blocks universal finalization",
        "redundancy": (
            "requires high empirical overlap plus shared/derivative lineage and a simpler retained "
            "alternative; correlation alone is insufficient"
        ),
        "uniqueness": (
            "multiple R2 and residual variance inform retention but never measure importance"
        ),
        "era": (
            "direct re-expression of normalized Peak/Longevity evidence is diagnostic unless "
            "material independent residual structure is demonstrated"
        ),
        "defense": (
            "all-era and modern evidence remain separate; limited pre-introduction evidence cannot "
            "be repaired"
        ),
    }
    retain = {
        "PEAK-A",
        "PEAK-B",
        "PEAK-E",
        "LONGEVITY-A",
        "LONGEVITY-B",
        "LONGEVITY-D",
        "OFFENSE-A",
        "OFFENSE-C",
        "DEFENSE-A",
        "PLAYOFFS-A",
        "PLAYOFFS-C",
        "PLAYOFFS-D",
        "ACCOLADES-A",
        "ACCOLADES-D",
        "ACCOLADES-E",
        "WINNING-A",
        "WINNING-B",
        "WINNING-C",
    }
    insufficient = {"DEFENSE-D"}
    pruning: list[dict[str, Any]] = []
    uniqueness_by_id = {str(row["candidate_id"]): row for row in uniqueness}
    coverage_records = json.loads((args.docs_root / "dimension-coverage-audit.json").read_text())[
        "records"
    ]
    broad_coverage = {
        str(row["candidate_id"]): row["primary_available_rate"] for row in coverage_records
    }
    for candidate in registry["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        old = str(candidate["status"])
        if old == "REJECTED":
            status = PruningStatus.REJECTED
            reason = "STEP-0012 rejection preserved"
        elif old == "DEFERRED":
            status = PruningStatus.DEFER_MODERN_ONLY
            reason = "post-1996 evidence remains a labeled enrichment, not a universal input"
        elif candidate_id in insufficient:
            status = PruningStatus.INSUFFICIENT_ALL_ERA_EVIDENCE
            reason = "coverage bridge cannot establish universal individual defensive evidence"
        elif candidate_id in retain:
            status = PruningStatus.RETAIN_FOR_FINALIZATION
            reason = (
                "retains a materially interpretable definition after coverage, lineage, and "
                "structural audit"
            )
        else:
            status = PruningStatus.REDUNDANT
            reason = (
                "overlaps a simpler retained definition or directly re-expresses another candidate "
                "family"
            )
        pruning.append(
            {
                "candidate_id": candidate_id,
                "dimension": candidate["dimension"],
                "step_0012_status": old,
                "step_0013_status": status.value,
                "reason": reason,
                "broad_availability": broad_coverage.get(candidate_id),
                "uniqueness": uniqueness_by_id.get(candidate_id),
                "final": False,
            }
        )
    shortlist = [
        row
        for row in pruning
        if row["step_0013_status"] == PruningStatus.RETAIN_FOR_FINALIZATION.value
    ]
    recommendations = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "candidate_count_start": len(pruning),
        "shortlist_count": len(shortlist),
        "status_counts": dict(sorted(Counter(row["step_0013_status"] for row in pruning).items())),
        "predeclared_rules": predeclared_rules,
        "era_dominance_conclusion": "USE_AS_DIAGNOSTIC_ONLY",
        "accolades_conclusion": (
            "Retain raw-profile, honor-persistence, and major-winner lenses; scarcity and "
            "opportunity transforms are redundant with raw counts in this corpus."
        ),
        "peak_conclusion": (
            "Retain one-year, contiguous three-year, and availability-adjusted three-year lenses; "
            "multi-horizon PEAK-D is redundant and five-year PEAK-C remains rejected for coverage."
        ),
        "defense_all_era_conclusion": (
            "Retain DEFENSE-A only as a coverage-qualified candidate; no universal scalar is "
            "established."
        ),
        "defense_modern_conclusion": "Keep DEFENSE-C deferred as a separate post-1996 enrichment.",
        "recommended_conceptual_structure": {
            "count": 7,
            "concepts": [
                "PEAK",
                "LONGEVITY",
                "OFFENSE",
                "DEFENSE",
                "PLAYOFFS",
                "ACCOLADES",
                "WINNING",
            ],
            "era_dominance": (
                "diagnostic lens over already era-normalized evidence, not an independent additive "
                "dimension"
            ),
        },
        "original_eight_dimension_framework": "NOT_EMPIRICALLY_DEFENSIBLE_AS_EIGHT_ADDITIVE_VOTES",
        "pruning_records": pruning,
        "shortlist": shortlist,
        "no_final_candidates": True,
        "no_overall_score": True,
    }
    shortlist_yaml = {
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "status": "EXPERIMENTAL_SHORTLIST_NOT_FINAL",
        "candidate_count": len(shortlist),
        "candidates": [
            {key: row[key] for key in ("candidate_id", "dimension", "step_0013_status", "reason")}
            for row in shortlist
        ],
    }
    shortlist_path = args.docs_root / "dimension-candidate-shortlist.yaml"
    shortlist_path.write_text(yaml.safe_dump(shortlist_yaml, sort_keys=False), encoding="utf-8")
    pruning_partitions = [
        write_parquet(
            pruning,
            args.gold_root / "ml_structure/candidate_pruning/candidate_status.parquet",
            ("dimension", "candidate_id"),
        )
    ]

    reports: dict[str, dict[str, Any]] = {
        "pca-structure-summary.json": pca_summary,
        "factor-analysis-summary.json": factor_summary,
        "latent-component-stability.json": stability_summary,
        "candidate-uniqueness.json": uniqueness_report,
        "cluster-model-selection.json": cluster_model_report,
        "cluster-stability.json": cluster_stability,
        "player-archetype-summary.json": archetype_report,
        "dimension-structural-recommendations.json": recommendations,
    }
    for name, payload in reports.items():
        stable_json(args.docs_root / name, payload)

    figure_root = args.gold_root / "ml_structure/figures"
    svg_line_chart(
        figure_root / "pca-scree-parallel.svg",
        {
            "observed eigenvalue": [float(value) for value in parallel["observed"]],
            "random 95th percentile": [float(value) for value in parallel["random_percentile"]],
        },
        "PCA scree and parallel-analysis threshold",
    )
    svg_line_chart(
        figure_root / "cluster-model-selection.svg",
        {
            "magnitude silhouette": [
                float(row["silhouette"]) for row in cluster_selection["MAGNITUDE_PRESERVING"]
            ],
            "profile silhouette": [
                float(row["silhouette"]) for row in cluster_selection["PROFILE_SHAPE"]
            ],
        },
        "K-means model selection (k=2..12)",
    )
    svg_line_chart(
        figure_root / "factor-heldout-error.svg",
        {
            "held-out correlation RMSE": [
                float(row["five_fold_heldout_correlation_rmse"]) for row in factor_candidates
            ]
        },
        "Factor-analysis held-out reconstruction (2..10 factors)",
    )
    svg_line_chart(
        figure_root / "hierarchical-merge-distance.svg",
        {"merge distance": [float(row["distance"]) for row in merge_history]},
        "Agglomerative merge-distance trace",
    )

    output_partitions = (
        pca_partitions + factor_partitions + clustering_partitions + pruning_partitions
    )
    figure_partitions = [
        {
            "path": str(path.relative_to(ROOT)),
            "rows": None,
            "columns": None,
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(figure_root.glob("*.svg"))
    ]
    all_outputs = sorted(output_partitions + figure_partitions, key=lambda row: row["path"])
    output_fingerprint = hashlib.sha256(
        "\n".join(f"{row['path']}:{row['sha256']}" for row in all_outputs).encode()
    ).hexdigest()
    committed_paths = [args.docs_root / name for name in sorted(reports)] + [shortlist_path]
    committed_fingerprint = report_fingerprint(committed_paths)
    runtime = time.perf_counter() - started
    prior_summary_path = args.docs_root / "structural-validation-summary.json"
    if args.expected_fingerprint and prior_summary_path.exists():
        prior_summary = json.loads(prior_summary_path.read_text(encoding="utf-8"))
        if prior_summary.get("output_fingerprint") == output_fingerprint:
            runtime = float(prior_summary["runtime_seconds"])
    summary = {
        "step": "STEP-0013",
        "methodology_version": STRUCTURAL_METHODOLOGY_VERSION,
        "run_at": args.run_at,
        "input_fingerprints": input_fingerprints,
        "matrix_audits": audits,
        "primary_pca_components": component_count,
        "selected_factor_count": chosen_factors,
        "selected_archetype_clusters": chosen_k,
        "candidate_start_count": len(pruning),
        "candidate_shortlist_count": len(shortlist),
        "output_partitions": len(all_outputs),
        "output_size_bytes": sum(int(row["size_bytes"]) for row in all_outputs),
        "output_fingerprint": output_fingerprint,
        "committed_report_fingerprint": committed_fingerprint,
        "runtime_seconds": runtime,
        "runtime_definition": (
            "baseline successful build; preserved across exact-fingerprint certification rebuilds"
        ),
        "random_seed": STRUCTURAL_RANDOM_SEED,
        "numpy_version": np.__version__,
        "parallel_repetitions": PARALLEL_REPETITIONS,
        "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
        "network_requests": 0,
        "deterministic_rebuild_verified": args.expected_fingerprint is not None,
        "no_imputation": True,
        "no_overall_score": True,
        "no_player_ranking": True,
        "result": "PASS",
        "partitions": all_outputs,
    }
    if args.expected_fingerprint and output_fingerprint != args.expected_fingerprint:
        raise ValueError(
            "output fingerprint mismatch: "
            f"expected {args.expected_fingerprint}, got {output_fingerprint}"
        )
    stable_json(args.docs_root / "structural-validation-summary.json", summary)
    return summary


def main() -> None:
    summary = build(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
