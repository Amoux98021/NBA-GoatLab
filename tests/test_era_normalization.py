"""Offline unit and artifact tests for STEP-0007 era normalization."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from goatlab.features.era_normalization import (
    CORPUS_FINGERPRINT,
    CORPUS_ID,
    FEATURE_DEFINITIONS,
    FEATURES_BY_NAME,
    METHODOLOGY_VERSION,
    EligibilityStatus,
    QualificationStatus,
    candidate_thresholds,
    distribution,
    effective_fg_pct,
    empirical_percentile,
    feature_registry,
    fingerprint_partitions,
    league_reference,
    partition_coverage_status,
    per_36,
    per_75,
    per_game,
    qualification_threshold,
    qualify_player_season,
    relative_index,
    robust_z_score,
    standard_z_score,
    true_shooting_pct,
)

ROOT = Path(__file__).resolve().parents[1]


def test_comparison_population_scales_regular_and_shortened_seasons() -> None:
    assert qualification_threshold("REGULAR", 82) == 17
    assert qualification_threshold("REGULAR", 50) == 10
    assert qualification_threshold("REGULAR", 66) == 14
    qualified = qualify_player_season(10, season_type="REGULAR", season_opportunity_games=50)
    excluded = qualify_player_season(9, season_type="REGULAR", season_opportunity_games=50)
    assert qualified.status is QualificationStatus.QUALIFIED
    assert excluded.status is QualificationStatus.NOT_QUALIFIED
    assert "opportunity_games=50" in qualified.reason


def test_playoff_qualification_excludes_one_game_without_erasing_short_series() -> None:
    assert qualification_threshold("PLAYOFF", 23) == 3
    assert qualification_threshold("PLAYOFF", 11) == 2
    assert (
        qualify_player_season(2, season_type="PLAYOFF", season_opportunity_games=11).status
        is QualificationStatus.QUALIFIED
    )
    assert (
        qualify_player_season(1, season_type="PLAYOFF", season_opportunity_games=11).status
        is QualificationStatus.NOT_QUALIFIED
    )
    assert candidate_thresholds("PLAYOFF", 20) == {
        "PO_ALL_APPEARANCES": 1,
        "PO_GAMES_10PCT_SELECTED": 2,
        "PO_GAMES_20PCT": 4,
    }


def test_standard_and_robust_z_scores_have_documented_behavior() -> None:
    stats = distribution([1.0, 2.0, 3.0])
    values = [standard_z_score(value, stats.mean, stats.std) for value in (1.0, 2.0, 3.0)]
    assert sum(value for value in values if value is not None) == pytest.approx(0.0)
    assert standard_z_score(2.0, stats.mean, 0.0) is None

    baseline = distribution([1.0, 2.0, 3.0, 4.0, 5.0])
    with_outlier = distribution([1.0, 2.0, 3.0, 4.0, 1000.0])
    assert baseline.median == with_outlier.median == 3.0
    assert baseline.mad == with_outlier.mad == 1.0
    assert robust_z_score(4.0, baseline.median, baseline.mad) == pytest.approx(
        robust_z_score(4.0, with_outlier.median, with_outlier.mad)
    )


def test_percentile_midrank_ties_and_relative_index() -> None:
    population = [1.0, 2.0, 2.0, 4.0]
    assert empirical_percentile(2.0, population) == pytest.approx(0.5)
    assert empirical_percentile(1.0, population) == pytest.approx(0.125)
    assert empirical_percentile(4.0, population) == pytest.approx(0.875)
    assert relative_index(0.6, 0.5) == pytest.approx(120.0)
    assert relative_index(1.0, 0.0) is None


def test_rate_and_shooting_formulas_preserve_invalid_denominators_as_null() -> None:
    assert per_game(30, 3) == pytest.approx(10.0)
    assert per_36(30, 36) == pytest.approx(30.0)
    assert per_75(30, 75) == pytest.approx(30.0)
    assert per_36(30, 0) is None
    assert per_75(30, None) is None
    assert effective_fg_pct(10, 4, 20) == pytest.approx(0.6)
    assert effective_fg_pct(10, None, 20) is None
    assert true_shooting_pct(30, 20, 10) == pytest.approx(30 / (2 * (20 + 4.4)))
    assert true_shooting_pct(0, 0, 0) is None


def test_league_efficiency_reference_uses_only_complete_comparison_rows() -> None:
    rows = [
        {"fgm_total": 10, "fga_total": 20, "points_total": 30, "fta_total": 10},
        {"fgm_total": 100, "fga_total": None, "points_total": 200, "fta_total": None},
    ]
    assert league_reference("fg_pct", rows, {}) == pytest.approx(0.5)
    assert league_reference("ts_pct", rows, {}) == pytest.approx(30 / (2 * (20 + 4.4)))


def test_coverage_gating_blocks_minutes_and_possessions_without_evidence() -> None:
    reliable = {"points": "RELIABLE", "minutes": "RELIABLE"}
    available, status = partition_coverage_status(
        FEATURES_BY_NAME["points_per_36"],
        reliable,
        possessions_qualified=False,
        minutes_qualified=False,
    )
    assert available is False
    assert "minutes_positive_share" in status

    available, status = partition_coverage_status(
        FEATURES_BY_NAME["points_per_75"],
        reliable,
        possessions_qualified=False,
    )
    assert available is False
    assert status == EligibilityStatus.UNAVAILABLE_POSSESSIONS.value


def test_feature_registry_has_complete_gold_provenance() -> None:
    registry = feature_registry()
    assert registry["corpus_id"] == CORPUS_ID
    assert registry["corpus_fingerprint"] == CORPUS_FINGERPRINT
    assert registry["methodology_version"] == METHODOLOGY_VERSION
    assert len(registry["features"]) == len(FEATURE_DEFINITIONS) == 16
    assert all(feature["source_metrics"] for feature in registry["features"])
    assert all(feature["formula"] for feature in registry["features"])


def test_partition_fingerprint_is_order_independent_and_sensitive() -> None:
    partitions = [
        {"path": "b", "rows": 2, "columns": 3, "size_bytes": 4, "sha256": "two"},
        {"path": "a", "rows": 1, "columns": 3, "size_bytes": 3, "sha256": "one"},
    ]
    assert fingerprint_partitions(partitions) == fingerprint_partitions(list(reversed(partitions)))
    changed = [{**partitions[0], "sha256": "changed"}, partitions[1]]
    assert fingerprint_partitions(partitions) != fingerprint_partitions(changed)


def test_committed_gold_artifacts_enforce_total_rows_isolation_and_reproducibility() -> None:
    summary = json.loads(
        (ROOT / "docs/data/era-normalization-summary.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "docs/data/era-normalization-gold-manifest.json").read_text(encoding="utf-8")
    )
    eligibility = json.loads(
        (ROOT / "docs/data/feature-eligibility-matrix.json").read_text(encoding="utf-8")
    )
    assert summary["decision"] == "PASS"
    assert summary["outputs"]["normalized_wide_rows"] == 37472
    assert summary["outputs"]["feature_long_rows"] == 37472 * 16
    assert summary["quality_checks"]["team_rows_consumed"] == 0
    assert summary["quality_checks"]["season_type_mixing"] == 0
    assert summary["quality_checks"]["unavailable_metric_non_null_leakage"] == 0
    assert manifest["partition_count"] == 480
    assert manifest["input_corpus_fingerprint"] == CORPUS_FINGERPRINT
    assert eligibility["records"] == 160 * 16 * 4
    assert all(item["season_type"] in {"REGULAR", "PLAYOFF"} for item in eligibility["matrix"])
    assert all(
        math.isfinite(float(item["qualified_population_size"])) for item in eligibility["matrix"]
    )
