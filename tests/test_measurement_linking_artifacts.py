from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((DOCS / name).read_text(encoding="utf-8")))


def test_step_g_is_reconstructed_exactly() -> None:
    summary = _json("player-season-value-measurement-linking-summary.json")
    reconstruction = summary["reconstruction"]
    assert reconstruction["silver_rows"] == 22457
    assert reconstruction["scoreable_player_seasons"] == 21107
    assert reconstruction["raw_mismatches"] == 0
    assert reconstruction["percentile_mismatches"] == 0
    assert reconstruction["maximum_raw_difference"] == 0.0
    assert reconstruction["maximum_percentile_difference"] == 0.0


def test_point_statuses_follow_predeclared_gates() -> None:
    summary = _json("player-season-value-measurement-linking-summary.json")
    assert summary["score_status"]["status"] == {
        "INTERVAL_ONLY": 3937,
        "OFFICIAL_POINT": 14687,
        "PROVISIONAL_POINT": 3831,
        "UNAVAILABLE": 2,
    }
    calibration = summary["calibration"]
    assert calibration["NO_TEAM_CONTEXT"]["point_eligible"] is True
    assert calibration["TRADITIONAL_WITH_PRESENCE"]["point_eligible"] is True
    assert calibration["EXPANDED_NO_PRESENCE"]["point_eligible"] is False
    assert calibration["TRADITIONAL_BOX"]["point_eligible"] is False


def test_intervals_are_nested_and_missing_is_not_zero() -> None:
    rows = pq.read_table(
        ROOT
        / "data/gold/player_season_value_measurement_linking_audit"
        / "linked-season-measurements.parquet"
    ).to_pylist()
    assert len(rows) == 22457
    for row in rows:
        if row["score_status"] == "UNAVAILABLE":
            assert row["linked_point_estimate"] is None
            assert row["interval_center"] is None
            continue
        point = float(row["interval_center"])
        assert row["lower_95"] <= row["lower_90"] <= row["lower_80"] <= point
        assert point <= row["upper_80"] <= row["upper_90"] <= row["upper_95"]
        if row["score_status"] == "INTERVAL_ONLY":
            assert row["linked_point_estimate"] is None


def test_no_stat_imputation_or_methodology_promotion() -> None:
    verdict = _json("player-season-value-measurement-linking-verdict.json")
    assert verdict["missing_statistics_predicted"] is False
    assert verdict["candidate_d_modified"] is False
    assert verdict["official_methodology_created"] is False
    assert verdict["architecture_verdict"] == "LIMITED_TIERED_ARCHITECTURE"


def test_interval_calibration_and_transport_are_reported() -> None:
    report = _json("player-season-value-linking-validation.json")
    assert set(report["measurement_forms"]) >= {
        "FULL_PORTABLE",
        "EXPANDED_NO_PRESENCE",
        "TRADITIONAL_BOX",
        "OFFENSE_ONLY_EARLY",
        "NO_TEAM_CONTEXT",
    }
    assert set(report["era_transport"]) == set(report["selected"])
    for form, result in report["common_scale"].items():
        intervals = result["intervals"]
        assert 0.79 <= intervals["80"]["coverage"] <= 0.81, form
        assert 0.89 <= intervals["90"]["coverage"] <= 0.91, form
        assert 0.94 <= intervals["95"]["coverage"] <= 0.96, form


def test_research_fingerprint_is_present() -> None:
    summary = _json("player-season-value-measurement-linking-summary.json")
    fingerprint = summary["output_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert summary["research_methodology_version"].endswith("linked-research")
