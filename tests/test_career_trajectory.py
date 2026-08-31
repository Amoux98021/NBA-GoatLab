"""Offline tests for STEP-0008 career trajectory primitives."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from goatlab.features.career_trajectory import (
    CAREER_METHODOLOGY_VERSION,
    CORPUS_FINGERPRINT,
    NORMALIZATION_FINGERPRINT,
    CandidateEvidence,
    CoverageStatus,
    PeakVariant,
    SeasonValue,
    age_on_season_reference,
    area_above_percentile,
    best_non_contiguous,
    best_peak_window,
    candidate_universe_flags,
    career_feature_registry,
    career_sequence,
    contiguous_windows,
    cumulative_positive_z,
    fingerprint_partitions,
    opportunity_adjusted_value,
    prime_run,
)

ROOT = Path(__file__).resolve().parents[1]


def observation(
    season: int,
    value: float,
    *,
    games: int = 70,
    opportunity: float = 0.85,
) -> SeasonValue:
    return SeasonValue(season, value, games, opportunity)


def test_career_sequence_preserves_missed_season_gap() -> None:
    rows = career_sequence(1998, 2000, {1998, 2000})
    assert [row["appeared"] for row in rows] == [True, False, True]
    assert [row["season_number"] for row in rows] == [1, 2, 3]
    assert [row["appearance_number"] for row in rows] == [1, None, 2]


def test_contiguous_windows_break_on_missing_season() -> None:
    observations = [observation(1998, 1.0), observation(2000, 2.0), observation(2001, 3.0)]
    assert contiguous_windows(observations, 3) == []
    windows = contiguous_windows(observations, 2)
    assert [[item.season_id for item in window] for window in windows] == [[2000, 2001]]


def test_peak_windows_support_one_three_five_and_reject_insufficient() -> None:
    observations = [observation(2000 + index, float(index)) for index in range(6)]
    for size in (1, 3, 5):
        peak = best_peak_window(
            observations,
            window_size=size,
            variant=PeakVariant.QUALITY,
            normalization_method="STANDARD_Z",
        )
        assert peak.coverage_status is CoverageStatus.AVAILABLE
        assert peak.end_season - peak.start_season + 1 == size  # type: ignore[operator]
    missing = best_peak_window(
        [observation(2000, 1.0), observation(2002, 3.0)],
        window_size=3,
        variant=PeakVariant.QUALITY,
        normalization_method="STANDARD_Z",
    )
    assert missing.coverage_status is CoverageStatus.INSUFFICIENT_CONTIGUOUS_COVERAGE
    assert missing.mean_value is None


def test_quality_and_availability_adjusted_peak_are_distinct() -> None:
    observations = [
        observation(2018, 3.0, opportunity=0.30),
        observation(2019, 2.0, opportunity=1.00),
    ]
    quality = best_peak_window(
        observations,
        window_size=1,
        variant=PeakVariant.QUALITY,
        normalization_method="STANDARD_Z",
    )
    adjusted = best_peak_window(
        observations,
        window_size=1,
        variant=PeakVariant.AVAILABILITY_ADJUSTED,
        normalization_method="STANDARD_Z",
    )
    assert quality.start_season == 2018
    assert adjusted.start_season == 2019
    assert opportunity_adjusted_value(3.0, 0.30, "STANDARD_Z") == pytest.approx(0.9)


def test_non_contiguous_best_seasons_are_explicit() -> None:
    observations = [
        observation(2000, 1.0),
        observation(2002, 5.0),
        observation(2004, 3.0),
    ]
    result = best_non_contiguous(observations, 3, normalization_method="STANDARD_Z")
    assert result["coverage_status"] == "AVAILABLE"
    assert result["seasons"] == [2002, 2004, 2000]
    assert result["mean_value"] == pytest.approx(3.0)
    unavailable = best_non_contiguous(observations, 5, normalization_method="STANDARD_Z")
    assert unavailable["coverage_status"] == "INSUFFICIENT_QUALIFIED_SEASONS"


def test_elite_counts_and_prime_runs_break_on_gaps_and_below_threshold() -> None:
    observations = [
        observation(2000, 0.95),
        observation(2001, 0.92),
        observation(2003, 0.99),
        observation(2004, 0.70),
        observation(2005, 0.96),
    ]
    run = prime_run(observations, 0.90)
    assert run.season_count == 4
    assert run.longest_run == 2
    assert (run.start_season, run.end_season) == (2000, 2001)


def test_cumulative_dominance_and_opportunity_weighting() -> None:
    z = [observation(2000, 2.0, opportunity=0.5), observation(2001, -1.0)]
    positive, weighted = cumulative_positive_z(z)
    assert positive == pytest.approx(2.0)
    assert weighted == pytest.approx(1.0)
    area, weighted_area = area_above_percentile(
        [observation(2000, 0.90, opportunity=0.5), observation(2001, 0.70)],
        0.80,
    )
    assert area == pytest.approx(0.10)
    assert weighted_area == pytest.approx(0.05)


def test_empty_observations_preserve_historical_unavailability() -> None:
    peak = best_peak_window(
        [],
        window_size=1,
        variant=PeakVariant.QUALITY,
        normalization_method="PERCENTILE",
    )
    assert peak.coverage_status is CoverageStatus.UNAVAILABLE_NO_QUALIFIED_VALUES
    assert peak.mean_value is None
    assert prime_run([], 0.90).career_proportion is None


def test_age_uses_documented_season_reference_without_imputation() -> None:
    age = age_on_season_reference(date(1984, 12, 30), 2012)
    assert age == pytest.approx(28.09, abs=0.02)
    assert age_on_season_reference(None, 2012) is None


def test_candidate_universe_is_broad_and_reproducible() -> None:
    flags = candidate_universe_flags(CandidateEvidence("player", 5, 0, 0))
    assert flags["participation_q5"] is True
    assert flags["union_q5_or_p90_recommended"] is True
    elite = candidate_universe_flags(CandidateEvidence("elite", 1, 1, 1))
    assert elite["elite_any_core_p90"] is True
    assert elite["union_q5_or_p90_recommended"] is True


def test_registry_and_fingerprint_capture_provenance() -> None:
    registry = career_feature_registry()
    assert registry["career_methodology_version"] == CAREER_METHODOLOGY_VERSION
    assert registry["normalization_fingerprint"] == NORMALIZATION_FINGERPRINT
    assert registry["corpus_fingerprint"] == CORPUS_FINGERPRINT
    assert len(registry["definitions"]) >= 7
    parts = [{"path": "a", "rows": 1, "columns": 2, "size_bytes": 3, "sha256": "x"}]
    assert fingerprint_partitions(parts) == fingerprint_partitions(list(reversed(parts)))


def test_committed_career_artifacts_are_reproducible_and_non_ranking() -> None:
    summary_path = ROOT / "docs/data/career-feature-summary.json"
    if not summary_path.exists():
        pytest.skip("STEP-0008 generated artifacts not built yet")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "docs/data/career-gold-manifest.json").read_text(encoding="utf-8")
    )
    candidates = json.loads(
        (ROOT / "docs/data/award-candidate-universe-analysis.json").read_text(encoding="utf-8")
    )
    assert summary["decision"] == "PASS"
    assert summary["players"]["processed"] == 5103
    assert summary["input"]["network_requests"] == 0
    assert manifest["reproducibility"]["pass"] is True
    assert candidates["master_player_count"] == 5103
    assert candidates["recommended_count"] < candidates["master_player_count"]
