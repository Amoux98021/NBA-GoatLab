from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_structural_reports_are_complete_and_fingerprinted() -> None:
    summary = json.loads((DOCS / "structural-validation-summary.json").read_text())
    report_names = (
        "candidate-uniqueness.json",
        "cluster-model-selection.json",
        "cluster-stability.json",
        "dimension-structural-recommendations.json",
        "factor-analysis-summary.json",
        "latent-component-stability.json",
        "pca-structure-summary.json",
        "player-archetype-summary.json",
        "dimension-candidate-shortlist.yaml",
    )
    paths = [DOCS / name for name in report_names]
    fingerprint = hashlib.sha256(
        "\n".join(f"{path.name}:{_sha256(path)}" for path in paths).encode()
    ).hexdigest()

    assert summary["methodology_version"] == "unsupervised-structural-validation-v1"
    assert summary["candidate_start_count"] == 38
    assert summary["candidate_shortlist_count"] == 18
    assert summary["network_requests"] == 0
    assert summary["numpy_version"]
    assert summary["no_imputation"] is True
    assert summary["no_overall_score"] is True
    assert summary["no_player_ranking"] is True
    assert summary["deterministic_rebuild_verified"] is True
    assert summary["committed_report_fingerprint"] == fingerprint


def test_pca_factor_and_stability_contracts() -> None:
    pca = json.loads((DOCS / "pca-structure-summary.json").read_text())
    factor = json.loads((DOCS / "factor-analysis-summary.json").read_text())
    stability = json.loads((DOCS / "latent-component-stability.json").read_text())

    assert pca["parallel_analysis"]["retained_components"] == 4
    assert len(pca["component_loadings"]) == 4
    assert 0.99 <= sum(pca["explained_variance_ratio"]) <= 1.01
    assert factor["method"] == "ITERATED_PRINCIPAL_AXIS_FACTORING"
    assert factor["rotation"] == "VARIMAX"
    assert factor["selected_factors"] == 7
    assert len(factor["rotated_factor_loadings"]) == 7
    assert min(stability["pca_bootstrap"]["mean_component_loading_correlation"]) > 0.95
    assert min(stability["factor_bootstrap"]["mean_loading_correlation"]) > 0.95
    assert min(stability["active_exclusion_pca_loading_correlations"]) > 0.95


def test_cluster_audit_is_profile_based_and_not_a_quality_order() -> None:
    selection = json.loads((DOCS / "cluster-model-selection.json").read_text())
    stability = json.loads((DOCS / "cluster-stability.json").read_text())
    archetypes = json.loads((DOCS / "player-archetype-summary.json").read_text())

    assert {row["clusters"] for row in selection["kmeans"]["PROFILE_SHAPE"]} == set(range(2, 13))
    assert {row["covariance_type"] for row in selection["gmm"]} == {
        "DIAGONAL",
        "SPHERICAL",
    }
    assert stability["seed_ari_mean"] > 0.90
    assert stability["bootstrap_ari_mean"] > 0.80
    assert stability["era_cluster_cramers_v"] < 0.25
    assert archetypes["not_quality_tiers"] is True
    assert archetypes["selected_model"] == "KMEANS_PROFILE_SHAPE"
    assert all(record["centroid_nearest_examples"] for record in archetypes["archetypes"])


def test_pruning_shortlist_is_nonfinal_and_era_is_diagnostic() -> None:
    recommendations = json.loads((DOCS / "dimension-structural-recommendations.json").read_text())
    shortlist = yaml.safe_load((DOCS / "dimension-candidate-shortlist.yaml").read_text())
    uniqueness = json.loads((DOCS / "candidate-uniqueness.json").read_text())

    allowed = {
        "RETAIN_FOR_FINALIZATION",
        "REDUNDANT",
        "REJECTED",
        "DEFER_MODERN_ONLY",
        "INSUFFICIENT_ALL_ERA_EVIDENCE",
    }
    assert {row["step_0013_status"] for row in recommendations["pruning_records"]} <= allowed
    assert all(row["final"] is False for row in recommendations["pruning_records"])
    assert recommendations["no_final_candidates"] is True
    assert recommendations["era_dominance_conclusion"] == "USE_AS_DIAGNOSTIC_ONLY"
    assert uniqueness["era_dominance_hypothesis"]["conclusion"] == "USE_AS_DIAGNOSTIC_ONLY"
    assert shortlist["status"] == "EXPERIMENTAL_SHORTLIST_NOT_FINAL"
    assert shortlist["candidate_count"] == 18
