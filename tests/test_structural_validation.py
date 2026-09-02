from __future__ import annotations

import math

import numpy as np
import pytest

from goatlab.models.structural_validation import (
    STRUCTURAL_RANDOM_SEED,
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
    principal_axis_factor_analysis,
    row_center_profiles,
    scale_matrix,
)


def _structured_matrix() -> np.ndarray:
    generator = np.random.default_rng(130013)
    latent = generator.normal(size=(180, 3))
    weights = np.asarray(
        [
            [1.0, 0.0, 0.1],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.1],
            [0.1, 0.8, 0.2],
            [0.0, 0.1, 1.0],
            [0.2, 0.0, 0.9],
        ]
    )
    return latent @ weights.T + generator.normal(scale=0.08, size=(180, 6))


def test_complete_case_matrix_never_imputes() -> None:
    rows = {
        "a": {"x": 1.0, "y": 2.0},
        "b": {"x": None, "y": 0.0},
        "c": {"x": 3.0, "y": 0.0},
    }
    result = complete_case_matrix(rows, {"a", "b", "c"}, ("x", "y"))
    assert result.retained_ids == ("a", "c")
    assert result.excluded_ids == ("b",)
    assert result.values.tolist() == [[1.0, 2.0], [3.0, 0.0]]


def test_standard_and_robust_scaling_are_distinct_and_finite() -> None:
    values = np.asarray([[0.0, 1.0], [1.0, 2.0], [100.0, 3.0]])
    standard = scale_matrix(values, ScalingMethod.STANDARD)
    robust = scale_matrix(values, ScalingMethod.ROBUST)
    assert np.allclose(np.mean(standard.values, axis=0), 0.0)
    assert np.allclose(np.median(robust.values, axis=0), 0.0)
    assert not np.allclose(standard.values, robust.values)


def test_constant_scaling_column_is_explicitly_invalid() -> None:
    result = scale_matrix(np.asarray([[1.0, 2.0], [1.0, 4.0]]), ScalingMethod.STANDARD)
    assert result.valid_columns.tolist() == [False, True]
    assert result.values[:, 0].tolist() == [0.0, 0.0]


def test_pca_explained_variance_and_reconstruction() -> None:
    values = scale_matrix(_structured_matrix(), ScalingMethod.STANDARD).values
    model = fit_pca(values)
    assert math.isclose(float(np.sum(model.explained_variance_ratio)), 1.0)
    assert all(
        left >= right - 1e-12
        for left, right in zip(
            model.reconstruction_rmse, model.reconstruction_rmse[1:], strict=False
        )
    )
    assert model.reconstruction_rmse[-1] == pytest.approx(0.0, abs=1e-10)


def test_pca_sign_alignment_and_component_matching() -> None:
    reference = np.asarray([[1.0, 0.1], [0.2, 0.9], [-0.3, 0.4]])
    candidate = np.column_stack((-reference[:, 1], reference[:, 0]))
    aligned, mapping, correlations = match_and_align_loadings(reference, candidate)
    assert mapping == (1, 0)
    assert min(correlations) == pytest.approx(1.0)
    assert np.allclose(aligned, reference)


def test_parallel_analysis_is_deterministic() -> None:
    values = scale_matrix(_structured_matrix(), ScalingMethod.STANDARD).values
    first = parallel_analysis(values, repetitions=12, seed=STRUCTURAL_RANDOM_SEED)
    second = parallel_analysis(values, repetitions=12, seed=STRUCTURAL_RANDOM_SEED)
    assert first["retained_components"] == second["retained_components"]
    assert np.array_equal(first["random_percentile"], second["random_percentile"])


def test_factor_analysis_is_separate_and_varimax_preserves_communality() -> None:
    values = scale_matrix(_structured_matrix(), ScalingMethod.STANDARD).values
    model = principal_axis_factor_analysis(values, 3)
    assert model.loadings.shape == (6, 3)
    assert model.rotated_loadings.shape == (6, 3)
    assert np.allclose(
        np.sum(model.loadings**2, axis=1),
        np.sum(model.rotated_loadings**2, axis=1),
    )
    assert np.all((model.communalities >= 0.0) & (model.communalities <= 1.0))


def test_candidate_uniqueness_uses_only_other_families() -> None:
    values = np.asarray([[1.0, 1.1, 0.0], [2.0, 2.1, 1.0], [3.0, 3.1, 0.0], [4.0, 4.1, 1.0]])
    rows = candidate_uniqueness(values, ("A", "B", "C"), ("X", "X", "Y"))
    assert len(rows) == 3
    assert rows[0]["sample_size"] == 4
    assert rows[0]["multiple_r_squared_other_families"] is not None


def test_profile_centering_removes_player_magnitude() -> None:
    values = np.asarray([[1.0, 2.0, 3.0], [11.0, 12.0, 13.0]])
    profiles = row_center_profiles(values)
    assert np.allclose(profiles[0], profiles[1])
    assert np.allclose(np.mean(profiles, axis=1), 0.0)
    assert np.allclose(np.sqrt(np.mean(profiles**2, axis=1)), 1.0)


def test_kmeans_is_seed_deterministic_and_labels_are_canonical() -> None:
    values = np.vstack((np.zeros((20, 2)), np.ones((20, 2)) * 5.0))
    first = fit_kmeans(values, 2, n_init=5)
    second = fit_kmeans(values, 2, n_init=5)
    assert np.array_equal(first.labels, second.labels)
    assert np.allclose(first.centroids, second.centroids)
    assert sorted(np.bincount(first.labels).tolist()) == [20, 20]


def test_cluster_metrics_bounds_and_permutation_invariant_agreement() -> None:
    labels = np.asarray([0, 0, 1, 1, 2, 2])
    permuted = np.asarray([2, 2, 0, 0, 1, 1])
    values = np.asarray([[0.0], [0.1], [5.0], [5.1], [10.0], [10.1]])
    metrics = cluster_metrics(values, labels, silhouette_sample=6)
    assert -1.0 <= float(metrics["silhouette"]) <= 1.0
    assert adjusted_rand_index(labels, permuted) == pytest.approx(1.0)
    assert adjusted_mutual_information(labels, permuted) == pytest.approx(1.0)


def test_diagonal_gmm_probabilities_and_information_criteria() -> None:
    values = np.vstack((np.zeros((30, 2)), np.ones((30, 2)) * 4.0))
    model = fit_diagonal_gmm(values, 2)
    assert np.allclose(np.sum(model.responsibilities, axis=1), 1.0)
    assert np.isfinite(model.aic)
    assert np.isfinite(model.bic)
    assert sorted(np.bincount(model.labels).tolist()) == [30, 30]
    spherical = fit_diagonal_gmm(values, 2, covariance_type="SPHERICAL")
    assert np.allclose(spherical.variances[:, 0], spherical.variances[:, 1])


def test_gmm_rejects_unknown_covariance() -> None:
    with pytest.raises(ValueError, match="covariance_type"):
        fit_diagonal_gmm(np.asarray([[0.0], [1.0], [3.0]]), 2, covariance_type="FULL")


def test_agglomerative_audit_returns_requested_clusters_and_merges() -> None:
    values = np.asarray([[0.0], [0.1], [5.0], [5.1], [10.0], [10.1]])
    labels, merges = agglomerative_average_linkage(values, 3)
    assert len(np.unique(labels)) == 3
    assert len(merges) == 3


def test_missing_values_and_infinite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        scale_matrix(np.asarray([[1.0, np.nan], [2.0, 3.0]]), ScalingMethod.STANDARD)
