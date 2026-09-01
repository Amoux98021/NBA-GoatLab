from __future__ import annotations

import math

import pytest

from goatlab.features.dimension_candidates import (
    CandidateStatus,
    CoverageConfidence,
    Dimension,
    MissingnessPolicy,
    ScalingMethod,
    candidate_specs,
    combine_components,
    correlation_pair,
    era_group,
    rejection_reasons,
    scale_values,
    shared_primitive_lineage,
    simplex_weights,
)


def test_catalog_has_every_dimension_and_no_final_status() -> None:
    specs = candidate_specs()
    assert {spec.dimension for spec in specs} == set(Dimension)
    assert len(specs) == 38
    assert all(spec.status is not CandidateStatus.REJECTED for spec in specs)
    assert all(spec.status.value != "FINAL" for spec in specs)


def test_feature_ownership_lineage_detects_double_counting() -> None:
    specs = {spec.candidate_id: spec for spec in candidate_specs()}
    shared = shared_primitive_lineage(specs["DEFENSE-B"], specs["ACCOLADES-A"])
    assert "dpoy_count" in shared
    assert "all_defense_total_count" in shared
    assert shared_primitive_lineage(specs["OFFENSE-B"], specs["WINNING-C"]) == ()


def test_scaling_methods_preserve_missingness_and_ties() -> None:
    values = {"a": 1.0, "b": 2.0, "c": 2.0, "d": None, "outside": 100.0}
    reference = {"a", "b", "c"}
    percentile = scale_values(values, reference, ScalingMethod.CAREER_UNIVERSE_PERCENTILE)
    cdf = scale_values(values, reference, ScalingMethod.EMPIRICAL_CDF)
    assert percentile["b"] == percentile["c"] == pytest.approx(2.0 / 3.0)
    assert cdf["b"] == cdf["c"] == 1.0
    assert percentile["d"] is None
    assert percentile["outside"] == 1.0  # no min-max compression from the extreme value
    standard = scale_values(values, reference, ScalingMethod.STANDARD_Z)
    assert math.isclose(sum(float(standard[key]) for key in reference), 0.0, abs_tol=1e-12)


def test_missingness_policies_do_not_impute_or_reward_missing() -> None:
    values = [0.9, None, 0.3]
    core = [True, True, False]
    assert combine_components(values, core, MissingnessPolicy.CORE_FEATURE_ONLY).value is None
    available = combine_components(
        values, core, MissingnessPolicy.AVAILABLE_FEATURE_RENORMALIZATION
    )
    assert available.value == pytest.approx(0.6)
    threshold = combine_components(values, core, MissingnessPolicy.COVERAGE_THRESHOLD)
    assert threshold.value == pytest.approx(0.6)
    assert threshold.confidence is CoverageConfidence.LIMITED
    enriched = combine_components(values, core, MissingnessPolicy.ERA_SPECIFIC_ENRICHMENT)
    assert enriched.value is None


def test_coverage_threshold_rejects_insufficient_evidence() -> None:
    result = combine_components(
        [1.0, None, None, None],
        [True, True, False, False],
        MissingnessPolicy.COVERAGE_THRESHOLD,
    )
    assert result.value is None
    assert result.evidence_coverage_pct == 0.25
    assert result.confidence is CoverageConfidence.LIMITED


def test_weighted_candidate_computation_is_renormalized() -> None:
    result = combine_components(
        [1.0, 3.0, None],
        [True, True, False],
        MissingnessPolicy.AVAILABLE_FEATURE_RENORMALIZATION,
        weights=[0.25, 0.75, 9.0],
    )
    assert result.value == pytest.approx(2.5)


def test_active_career_semantics_are_declared_in_every_candidate() -> None:
    # The immutable specs are consumed by the registry builder, which labels every
    # active career as to-date with no projection rather than applying a penalty.
    assert all(spec.description for spec in candidate_specs())


def test_award_applicability_and_all_star_semantics_are_separate() -> None:
    specs = {spec.candidate_id: spec for spec in candidate_specs()}
    names = {primitive.name for primitive in specs["ACCOLADES-D"].primitives}
    assert "all_star_roster_seasons" in names
    assert "stat_title_count" in names
    assert "all_star_count" not in names


def test_defense_historical_coverage_is_explicit() -> None:
    specs = {spec.candidate_id: spec for spec in candidate_specs()}
    assert any(primitive.post_1996_only for primitive in specs["DEFENSE-C"].primitives)
    assert any("1996" in bias for bias in specs["DEFENSE-C"].known_biases)
    assert any(not primitive.core for primitive in specs["DEFENSE-A"].primitives)


def test_playoff_sample_and_winning_participation_inputs_remain_distinct() -> None:
    specs = {spec.candidate_id: spec for spec in candidate_specs()}
    playoffs = {primitive.name for primitive in specs["PLAYOFFS-E"].primitives}
    finals = {primitive.name for primitive in specs["WINNING-C"].primitives}
    assert "playoff_games" in playoffs
    assert "champion_finals_seasons" in finals
    assert "champion_regular_seasons" not in finals


def test_correlation_and_redundancy_preserve_pairwise_population() -> None:
    result = correlation_pair(
        {"a": 1.0, "b": 2.0, "c": None},
        {"a": 2.0, "b": 4.0, "c": 9.0},
    )
    assert result == {"n": 2, "pearson": 1.0, "spearman": 1.0}


def test_monte_carlo_simplex_is_deterministic() -> None:
    first = simplex_weights(4, 20, 120012)
    second = simplex_weights(4, 20, 120012)
    assert first == second
    assert all(sum(row) == pytest.approx(1.0) for row in first)
    assert first != simplex_weights(4, 20, 120013)


@pytest.mark.parametrize(
    ("season", "expected"),
    [(1959, "PRE_1960"), (1960, "1960S"), (1999, "1990S"), (2025, "2020S"), (None, "UNKNOWN")],
)
def test_era_fairness_groups(season: int | None, expected: str) -> None:
    assert era_group(season) == expected


def test_rejection_rules_flag_modern_dependency_and_instability() -> None:
    reasons = rejection_reasons(
        available_rate=0.4,
        post_1996_dependency=True,
        ordering_stability_value=0.7,
        redundant_correlation=0.99,
        shared_lineage_count=2,
    )
    assert reasons == (
        "SEVERE_COVERAGE_LIMITATION",
        "HIDDEN_MODERN_ERA_DEPENDENCY",
        "WEIGHT_SENSITIVE",
        "NEAR_DUPLICATE_SIGNAL",
    )
