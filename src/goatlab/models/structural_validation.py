"""Deterministic, coverage-aware unsupervised diagnostics for STEP-0013.

The functions in this module deliberately do not produce an overall player
score or ranking.  They operate only on explicitly complete analytical
matrices and expose the transformation and stability diagnostics needed to
audit latent structure and player-profile archetypes.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

STRUCTURAL_METHODOLOGY_VERSION = "unsupervised-structural-validation-v1"
STRUCTURAL_RANDOM_SEED = 130013


class ScalingMethod(StrEnum):
    STANDARD = "STANDARD"
    ROBUST = "ROBUST"


class MatrixKind(StrEnum):
    DIMENSION_CANDIDATE = "DIMENSION_CANDIDATE"
    CROSS_ERA_PRIMITIVE = "CROSS_ERA_PRIMITIVE"
    MODERN_ENRICHED = "MODERN_ENRICHED"
    PROFILE_MAGNITUDE = "PROFILE_MAGNITUDE"
    PROFILE_SHAPE = "PROFILE_SHAPE"


class PruningStatus(StrEnum):
    RETAIN_FOR_FINALIZATION = "RETAIN_FOR_FINALIZATION"
    REDUNDANT = "REDUNDANT"
    REJECTED = "REJECTED"
    DEFER_MODERN_ONLY = "DEFER_MODERN_ONLY"
    INSUFFICIENT_ALL_ERA_EVIDENCE = "INSUFFICIENT_ALL_ERA_EVIDENCE"


@dataclass(frozen=True)
class CompleteMatrix:
    values: np.ndarray
    retained_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    feature_names: tuple[str, ...]


@dataclass(frozen=True)
class ScaleResult:
    values: np.ndarray
    centers: np.ndarray
    scales: np.ndarray
    valid_columns: np.ndarray


@dataclass(frozen=True)
class PCAResult:
    scores: np.ndarray
    loadings: np.ndarray
    explained_variance: np.ndarray
    explained_variance_ratio: np.ndarray
    reconstruction_rmse: tuple[float, ...]


@dataclass(frozen=True)
class FactorResult:
    loadings: np.ndarray
    rotated_loadings: np.ndarray
    communalities: np.ndarray
    uniquenesses: np.ndarray
    iterations: int
    converged: bool
    reconstruction_rmse: float


@dataclass(frozen=True)
class KMeansResult:
    labels: np.ndarray
    centroids: np.ndarray
    inertia: float
    iterations: int


@dataclass(frozen=True)
class GMMResult:
    labels: np.ndarray
    responsibilities: np.ndarray
    means: np.ndarray
    variances: np.ndarray
    weights: np.ndarray
    log_likelihood: float
    aic: float
    bic: float
    iterations: int


def complete_case_matrix(
    rows: dict[str, dict[str, float | None]],
    player_ids: set[str],
    feature_names: tuple[str, ...],
) -> CompleteMatrix:
    """Build an explicitly complete matrix without imputing any missing value."""
    retained: list[str] = []
    excluded: list[str] = []
    values: list[list[float]] = []
    for player_id in sorted(player_ids):
        row = rows.get(player_id, {})
        observed = [row.get(name) for name in feature_names]
        if all(value is not None and math.isfinite(float(value)) for value in observed):
            retained.append(player_id)
            values.append([float(value) for value in observed])  # type: ignore[arg-type]
        else:
            excluded.append(player_id)
    matrix = np.asarray(values, dtype=np.float64)
    if not values:
        matrix = np.empty((0, len(feature_names)), dtype=np.float64)
    return CompleteMatrix(matrix, tuple(retained), tuple(excluded), feature_names)


def scale_matrix(values: np.ndarray, method: ScalingMethod) -> ScaleResult:
    """Scale columns; constant columns are reported invalid instead of synthesized."""
    if values.ndim != 2:
        raise ValueError("values must be a two-dimensional matrix")
    if not np.isfinite(values).all():
        raise ValueError("matrix contains non-finite values")
    if method is ScalingMethod.STANDARD:
        centers = np.mean(values, axis=0)
        scales = np.std(values, axis=0, ddof=0)
    elif method is ScalingMethod.ROBUST:
        centers = np.median(values, axis=0)
        scales = 1.4826 * np.median(np.abs(values - centers), axis=0)
    else:
        raise ValueError(f"unsupported scaling method: {method}")
    valid = scales > 1e-12
    scaled = np.zeros_like(values, dtype=np.float64)
    scaled[:, valid] = (values[:, valid] - centers[valid]) / scales[valid]
    return ScaleResult(scaled, centers, scales, valid)


def row_center_profiles(values: np.ndarray) -> np.ndarray:
    """Create shape-only profiles with zero row mean and unit row RMS."""
    centered = values - np.mean(values, axis=1, keepdims=True)
    scales = np.sqrt(np.mean(centered * centered, axis=1, keepdims=True))
    output = np.zeros_like(centered)
    valid = scales[:, 0] > 1e-12
    output[valid] = centered[valid] / scales[valid]
    return output


def fit_pca(values: np.ndarray) -> PCAResult:
    """Fit deterministic SVD PCA to an already scaled complete matrix."""
    if values.ndim != 2 or values.shape[0] < 2:
        raise ValueError("PCA requires a 2D matrix with at least two rows")
    centered = values - np.mean(values, axis=0)
    _, singular, vt = np.linalg.svd(centered, full_matrices=False)
    scores = centered @ vt.T
    explained = singular * singular / (values.shape[0] - 1)
    total = float(np.sum(explained))
    ratio = explained / total if total > 0.0 else np.zeros_like(explained)
    loadings = vt.T * np.sqrt(explained)
    rmse: list[float] = []
    for count in range(1, len(singular) + 1):
        reconstruction = scores[:, :count] @ vt[:count]
        rmse.append(float(np.sqrt(np.mean((centered - reconstruction) ** 2))))
    return PCAResult(scores, loadings, explained, ratio, tuple(rmse))


def parallel_analysis(
    values: np.ndarray,
    *,
    repetitions: int = 100,
    percentile: float = 0.95,
    seed: int = STRUCTURAL_RANDOM_SEED,
) -> dict[str, np.ndarray | int]:
    """Permutation parallel analysis preserving every feature marginal."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    baseline = fit_pca(values).explained_variance
    generator = np.random.default_rng(seed)
    simulated = np.empty((repetitions, values.shape[1]), dtype=np.float64)
    for repetition in range(repetitions):
        permuted = np.empty_like(values)
        for column in range(values.shape[1]):
            permuted[:, column] = generator.permutation(values[:, column])
        simulated[repetition] = fit_pca(permuted).explained_variance
    threshold = np.quantile(simulated, percentile, axis=0)
    return {
        "observed": baseline,
        "random_mean": np.mean(simulated, axis=0),
        "random_percentile": threshold,
        "retained_components": int(np.sum(baseline > threshold)),
    }


def match_and_align_loadings(
    reference: np.ndarray, candidate: np.ndarray
) -> tuple[np.ndarray, tuple[int, ...], tuple[float, ...]]:
    """Greedily match components by absolute loading correlation and align signs."""
    count = min(reference.shape[1], candidate.shape[1])
    remaining = set(range(candidate.shape[1]))
    columns: list[np.ndarray] = []
    mapping: list[int] = []
    correlations: list[float] = []
    for index in range(count):
        best: tuple[float, int, float] | None = None
        for other in sorted(remaining):
            correlation = float(np.corrcoef(reference[:, index], candidate[:, other])[0, 1])
            score = abs(correlation) if math.isfinite(correlation) else -1.0
            if best is None or score > best[0]:
                best = (score, other, correlation)
        if best is None:
            break
        _, other, correlation = best
        remaining.remove(other)
        sign = -1.0 if correlation < 0.0 else 1.0
        columns.append(candidate[:, other] * sign)
        mapping.append(other)
        correlations.append(abs(correlation))
    aligned = np.column_stack(columns) if columns else np.empty((reference.shape[0], 0))
    return aligned, tuple(mapping), tuple(correlations)


def pca_bootstrap_stability(
    values: np.ndarray,
    components: int,
    *,
    repetitions: int = 30,
    fraction: float = 0.8,
    seed: int = STRUCTURAL_RANDOM_SEED,
) -> dict[str, object]:
    baseline = fit_pca(values).loadings[:, :components]
    generator = np.random.default_rng(seed)
    component_correlations: list[list[float]] = []
    subspace_similarities: list[float] = []
    sample_size = max(2, round(values.shape[0] * fraction))
    for _ in range(repetitions):
        indices = np.sort(generator.choice(values.shape[0], sample_size, replace=True))
        fitted = fit_pca(values[indices]).loadings[:, :components]
        aligned, _, correlations = match_and_align_loadings(baseline, fitted)
        component_correlations.append(list(correlations))
        q_reference, _ = np.linalg.qr(baseline)
        q_candidate, _ = np.linalg.qr(aligned)
        singular = np.linalg.svd(q_reference.T @ q_candidate, compute_uv=False)
        subspace_similarities.append(float(np.mean(singular * singular)))
    correlations_array = np.asarray(component_correlations)
    return {
        "repetitions": repetitions,
        "sample_fraction": fraction,
        "mean_component_loading_correlation": np.mean(correlations_array, axis=0).tolist(),
        "minimum_component_loading_correlation": np.min(correlations_array, axis=0).tolist(),
        "mean_subspace_similarity": float(np.mean(subspace_similarities)),
        "minimum_subspace_similarity": float(np.min(subspace_similarities)),
    }


def varimax(loadings: np.ndarray, *, iterations: int = 100, tolerance: float = 1e-7) -> np.ndarray:
    """Orthogonal Varimax rotation with deterministic SVD updates."""
    rows, columns = loadings.shape
    rotation = np.eye(columns)
    previous = 0.0
    for _ in range(iterations):
        transformed = loadings @ rotation
        u, singular, vt = np.linalg.svd(
            loadings.T
            @ (transformed**3 - transformed @ np.diag(np.sum(transformed**2, axis=0)) / rows)
        )
        rotation = u @ vt
        objective = float(np.sum(singular))
        if previous and objective - previous < tolerance:
            break
        previous = objective
    return loadings @ rotation


def principal_axis_factor_analysis(
    values: np.ndarray,
    factors: int,
    *,
    max_iterations: int = 200,
    tolerance: float = 1e-6,
) -> FactorResult:
    """Principal-axis factor analysis with iterated communalities and Varimax."""
    if factors < 1 or factors >= values.shape[1]:
        raise ValueError("factor count must be between one and feature_count - 1")
    correlation = np.corrcoef(values, rowvar=False)
    inverse = np.linalg.pinv(correlation)
    communalities = np.clip(1.0 - 1.0 / np.diag(inverse), 0.05, 0.99)
    converged = False
    loadings = np.empty((values.shape[1], factors))
    iterations_run = 0
    for iteration in range(1, max_iterations + 1):
        iterations_run = iteration
        reduced = correlation.copy()
        np.fill_diagonal(reduced, communalities)
        eigenvalues, eigenvectors = np.linalg.eigh(reduced)
        order = np.argsort(eigenvalues)[::-1][:factors]
        positive = np.clip(eigenvalues[order], 0.0, None)
        loadings = eigenvectors[:, order] * np.sqrt(positive)
        updated = np.clip(np.sum(loadings * loadings, axis=1), 0.0, 0.999999)
        if float(np.max(np.abs(updated - communalities))) < tolerance:
            communalities = updated
            converged = True
            break
        communalities = updated
    reconstructed = loadings @ loadings.T
    mask = ~np.eye(correlation.shape[0], dtype=bool)
    rmse = float(np.sqrt(np.mean((correlation[mask] - reconstructed[mask]) ** 2)))
    return FactorResult(
        loadings,
        varimax(loadings),
        communalities,
        1.0 - communalities,
        iterations_run,
        converged,
        rmse,
    )


def multiple_r_squared(target: np.ndarray, predictors: np.ndarray) -> float | None:
    if target.size < 3 or predictors.ndim != 2 or predictors.shape[0] != target.size:
        return None
    design = np.column_stack((np.ones(target.size), predictors))
    coefficients, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
    predicted = design @ coefficients
    total = float(np.sum((target - np.mean(target)) ** 2))
    residual = float(np.sum((target - predicted) ** 2))
    return 1.0 - residual / total if total > 1e-12 else None


def candidate_uniqueness(
    values: np.ndarray,
    feature_names: tuple[str, ...],
    families: tuple[str, ...],
) -> list[dict[str, float | str | int | None]]:
    """Quantify cross-family correlation and residual variance for complete cases."""
    output: list[dict[str, float | str | int | None]] = []
    correlation = np.corrcoef(values, rowvar=False)
    for index, name in enumerate(feature_names):
        other_indices = [
            position for position, family in enumerate(families) if family != families[index]
        ]
        cross = [abs(float(correlation[index, position])) for position in other_indices]
        r_squared = multiple_r_squared(values[:, index], values[:, other_indices])
        output.append(
            {
                "candidate_id": name,
                "dimension": families[index],
                "sample_size": values.shape[0],
                "max_absolute_cross_family_correlation": max(cross) if cross else None,
                "multiple_r_squared_other_families": r_squared,
                "residual_variance_fraction": None if r_squared is None else 1.0 - r_squared,
            }
        )
    return output


def _canonicalize_labels(
    labels: np.ndarray, centroids: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Canonicalize arbitrary cluster labels by a hash of rounded centroid shape."""
    keys = [
        (hashlib.sha256(np.round(row, 10).tobytes()).hexdigest(), index)
        for index, row in enumerate(centroids)
    ]
    order = [index for _, index in sorted(keys)]
    remap = {old: new for new, old in enumerate(order)}
    return np.asarray([remap[int(label)] for label in labels]), centroids[order]


def fit_kmeans(
    values: np.ndarray,
    clusters: int,
    *,
    seed: int = STRUCTURAL_RANDOM_SEED,
    n_init: int = 20,
    max_iterations: int = 300,
) -> KMeansResult:
    if clusters < 2 or clusters > values.shape[0]:
        raise ValueError("invalid cluster count")
    best: KMeansResult | None = None
    for initialization in range(n_init):
        generator = np.random.default_rng(seed + initialization * 104729)
        first = int(generator.integers(values.shape[0]))
        chosen = [first]
        distances = np.sum((values - values[first]) ** 2, axis=1)
        for _ in range(1, clusters):
            total = float(np.sum(distances))
            if total <= 1e-12:
                remaining = [i for i in range(values.shape[0]) if i not in chosen]
                chosen.append(remaining[0])
            else:
                chosen.append(int(generator.choice(values.shape[0], p=distances / total)))
            distances = np.minimum(distances, np.sum((values - values[chosen[-1]]) ** 2, axis=1))
        centroids = values[chosen].copy()
        labels = np.zeros(values.shape[0], dtype=int)
        iterations_run = 0
        for iteration in range(1, max_iterations + 1):
            iterations_run = iteration
            squared = np.sum((values[:, None, :] - centroids[None, :, :]) ** 2, axis=2)
            updated_labels = np.argmin(squared, axis=1)
            updated = centroids.copy()
            for cluster in range(clusters):
                members = values[updated_labels == cluster]
                if len(members):
                    updated[cluster] = np.mean(members, axis=0)
            if np.array_equal(updated_labels, labels) and np.allclose(updated, centroids):
                labels = updated_labels
                centroids = updated
                break
            labels = updated_labels
            centroids = updated
        inertia = float(np.sum((values - centroids[labels]) ** 2))
        labels, centroids = _canonicalize_labels(labels, centroids)
        result = KMeansResult(labels, centroids, inertia, iterations_run)
        if best is None or result.inertia < best.inertia - 1e-10:
            best = result
    if best is None:
        raise AssertionError("K-means failed to initialize")
    return best


def cluster_metrics(
    values: np.ndarray,
    labels: np.ndarray,
    *,
    silhouette_sample: int = 500,
    seed: int = STRUCTURAL_RANDOM_SEED,
) -> dict[str, float | int | list[int] | None]:
    unique = np.unique(labels)
    sizes = [int(np.sum(labels == cluster)) for cluster in unique]
    overall = np.mean(values, axis=0)
    within = 0.0
    between = 0.0
    dispersions: list[float] = []
    centroids: list[np.ndarray] = []
    for cluster in unique:
        members = values[labels == cluster]
        centroid = np.mean(members, axis=0)
        centroids.append(centroid)
        within += float(np.sum((members - centroid) ** 2))
        between += len(members) * float(np.sum((centroid - overall) ** 2))
        dispersions.append(float(np.max(np.linalg.norm(members - centroid, axis=1))))
    ch = None
    if within > 0.0 and len(unique) > 1 and values.shape[0] > len(unique):
        ch = (between / (len(unique) - 1)) / (within / (values.shape[0] - len(unique)))
    centroid_matrix = np.asarray(centroids)
    db_terms: list[float] = []
    for left in range(len(unique)):
        ratios = []
        for right in range(len(unique)):
            if left == right:
                continue
            distance = float(np.linalg.norm(centroid_matrix[left] - centroid_matrix[right]))
            if distance > 0.0:
                ratios.append((dispersions[left] + dispersions[right]) / distance)
        if ratios:
            db_terms.append(max(ratios))
    db = float(np.mean(db_terms)) if db_terms else None

    generator = np.random.default_rng(seed)
    count = min(silhouette_sample, values.shape[0])
    indices = np.sort(generator.choice(values.shape[0], count, replace=False))
    sample = values[indices]
    sample_labels = labels[indices]
    distances = np.sqrt(np.sum((sample[:, None, :] - sample[None, :, :]) ** 2, axis=2))
    silhouettes: list[float] = []
    for index, label in enumerate(sample_labels):
        same = sample_labels == label
        same[index] = False
        a = float(np.mean(distances[index, same])) if np.any(same) else 0.0
        alternatives = [
            float(np.mean(distances[index, sample_labels == other]))
            for other in np.unique(sample_labels)
            if other != label and np.any(sample_labels == other)
        ]
        b = min(alternatives) if alternatives else 0.0
        denominator = max(a, b)
        silhouettes.append((b - a) / denominator if denominator > 0.0 else 0.0)
    return {
        "silhouette": float(np.mean(silhouettes)),
        "silhouette_sample_size": count,
        "calinski_harabasz": ch,
        "davies_bouldin": db,
        "cluster_sizes": sizes,
    }


def adjusted_rand_index(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        raise ValueError("label vectors must have equal shape")
    left_values = np.unique(left)
    right_values = np.unique(right)
    contingency = np.asarray(
        [[np.sum((left == a) & (right == b)) for b in right_values] for a in left_values],
        dtype=np.int64,
    )

    def choose2(value: int) -> float:
        return value * (value - 1) / 2.0

    sum_cells = float(sum(choose2(int(value)) for value in contingency.flat))
    sum_rows = float(sum(choose2(int(value)) for value in np.sum(contingency, axis=1)))
    sum_columns = float(sum(choose2(int(value)) for value in np.sum(contingency, axis=0)))
    total = choose2(left.size)
    expected = sum_rows * sum_columns / total if total else 0.0
    maximum = 0.5 * (sum_rows + sum_columns)
    denominator = maximum - expected
    return (sum_cells - expected) / denominator if denominator else 1.0


def adjusted_mutual_information(left: np.ndarray, right: np.ndarray) -> float:
    """Adjusted MI using the exact hypergeometric expectation and arithmetic mean."""
    left_values = np.unique(left)
    right_values = np.unique(right)
    contingency = np.asarray(
        [[np.sum((left == a) & (right == b)) for b in right_values] for a in left_values],
        dtype=np.int64,
    )
    n = int(left.size)
    rows = np.sum(contingency, axis=1)
    columns = np.sum(contingency, axis=0)
    mutual = 0.0
    for i, row_total in enumerate(rows):
        for j, column_total in enumerate(columns):
            cell = int(contingency[i, j])
            if cell:
                mutual += cell / n * math.log(cell * n / (row_total * column_total))
    entropy_left = -sum((value / n) * math.log(value / n) for value in rows if value)
    entropy_right = -sum((value / n) * math.log(value / n) for value in columns if value)
    expected = 0.0
    for row_total in rows:
        for column_total in columns:
            low = max(1, int(row_total + column_total - n))
            high = min(int(row_total), int(column_total))
            for cell in range(low, high + 1):
                log_probability = (
                    math.lgamma(int(row_total) + 1)
                    - math.lgamma(cell + 1)
                    - math.lgamma(int(row_total) - cell + 1)
                    + math.lgamma(n - int(row_total) + 1)
                    - math.lgamma(int(column_total) - cell + 1)
                    - math.lgamma(n - int(row_total) - int(column_total) + cell + 1)
                    - math.lgamma(n + 1)
                    + math.lgamma(int(column_total) + 1)
                    + math.lgamma(n - int(column_total) + 1)
                )
                probability = math.exp(log_probability)
                expected += probability * cell / n * math.log(cell * n / (row_total * column_total))
    normalizer = 0.5 * (entropy_left + entropy_right) - expected
    return (mutual - expected) / normalizer if abs(normalizer) > 1e-15 else 1.0


def fit_diagonal_gmm(
    values: np.ndarray,
    components: int,
    *,
    seed: int = STRUCTURAL_RANDOM_SEED,
    covariance_type: str = "DIAGONAL",
    max_iterations: int = 300,
    tolerance: float = 1e-6,
) -> GMMResult:
    """Fit a deterministic diagonal or spherical Gaussian mixture by EM."""
    if covariance_type not in {"DIAGONAL", "SPHERICAL"}:
        raise ValueError("covariance_type must be DIAGONAL or SPHERICAL")
    initial = fit_kmeans(values, components, seed=seed, n_init=10)
    means = initial.centroids.copy()
    labels = initial.labels
    weights = np.asarray([np.mean(labels == cluster) for cluster in range(components)])
    global_variance = np.var(values, axis=0) + 1e-6
    variances = np.asarray(
        [
            np.var(values[labels == cluster], axis=0) + 1e-6
            if np.sum(labels == cluster) > 1
            else global_variance
            for cluster in range(components)
        ]
    )
    previous = -math.inf
    responsibilities = np.empty((values.shape[0], components))
    iterations_run = 0
    for iteration in range(1, max_iterations + 1):
        iterations_run = iteration
        log_probabilities = np.empty_like(responsibilities)
        for cluster in range(components):
            delta = values - means[cluster]
            log_probabilities[:, cluster] = (
                math.log(max(float(weights[cluster]), 1e-15))
                - 0.5 * np.sum(np.log(2.0 * math.pi * variances[cluster]))
                - 0.5 * np.sum(delta * delta / variances[cluster], axis=1)
            )
        maximum = np.max(log_probabilities, axis=1, keepdims=True)
        exponentiated = np.exp(log_probabilities - maximum)
        normalizer = np.sum(exponentiated, axis=1, keepdims=True)
        responsibilities = exponentiated / normalizer
        likelihood = float(np.sum(maximum[:, 0] + np.log(normalizer[:, 0])))
        counts = np.sum(responsibilities, axis=0) + 1e-12
        weights = counts / values.shape[0]
        means = responsibilities.T @ values / counts[:, None]
        for cluster in range(components):
            delta = values - means[cluster]
            variances[cluster] = (
                np.sum(responsibilities[:, cluster, None] * delta * delta, axis=0) / counts[cluster]
                + 1e-6
            )
            if covariance_type == "SPHERICAL":
                variances[cluster] = np.mean(variances[cluster])
        if likelihood - previous < tolerance:
            break
        previous = likelihood
    raw_labels = np.argmax(responsibilities, axis=1)
    labels, canonical_means = _canonicalize_labels(raw_labels, means)
    order = [int(np.where(np.all(means == row, axis=1))[0][0]) for row in canonical_means]
    responsibilities = responsibilities[:, order]
    variances = variances[order]
    weights = weights[order]
    variance_parameters = values.shape[1] if covariance_type == "DIAGONAL" else 1
    parameters = components * (values.shape[1] + variance_parameters) + (components - 1)
    aic = 2 * parameters - 2 * likelihood
    bic = math.log(values.shape[0]) * parameters - 2 * likelihood
    return GMMResult(
        labels,
        responsibilities,
        canonical_means,
        variances,
        weights,
        likelihood,
        aic,
        bic,
        iterations_run,
    )


def agglomerative_average_linkage(
    values: np.ndarray, clusters: int
) -> tuple[np.ndarray, list[dict[str, float | int]]]:
    """Deterministic average-linkage clustering for a bounded audit sample."""
    count = values.shape[0]
    if clusters < 2 or clusters >= count:
        raise ValueError("invalid cluster count")
    distances = np.sqrt(np.sum((values[:, None, :] - values[None, :, :]) ** 2, axis=2))
    np.fill_diagonal(distances, np.inf)
    active = np.ones(count, dtype=bool)
    members: dict[int, list[int]] = {index: [index] for index in range(count)}
    merges: list[dict[str, float | int]] = []
    while int(np.sum(active)) > clusters:
        masked = np.where(active[:, None] & active[None, :], distances, np.inf)
        lower = np.tril(masked, k=-1)
        lower[lower == 0.0] = np.inf
        flat = int(np.argmin(lower))
        left_raw, right_raw = np.unravel_index(flat, lower.shape)
        left, right = int(left_raw), int(right_raw)
        if right > left:
            left, right = right, left
        distance = float(distances[left, right])
        left_size = len(members[left])
        right_size = len(members[right])
        for other in np.where(active)[0]:
            if other in {left, right}:
                continue
            updated = (
                distances[left, other] * left_size + distances[right, other] * right_size
            ) / (left_size + right_size)
            distances[left, other] = distances[other, left] = updated
        members[left].extend(members.pop(right))
        active[right] = False
        distances[right, :] = np.inf
        distances[:, right] = np.inf
        merges.append(
            {
                "left": int(left),
                "right": int(right),
                "distance": distance,
                "merged_size": left_size + right_size,
            }
        )
    labels = np.empty(count, dtype=int)
    active_clusters = sorted(members)
    centroids = np.asarray([np.mean(values[members[index]], axis=0) for index in active_clusters])
    temporary = np.empty(count, dtype=int)
    for label, index in enumerate(active_clusters):
        temporary[members[index]] = label
    labels, _ = _canonicalize_labels(temporary, centroids)
    return labels, merges
