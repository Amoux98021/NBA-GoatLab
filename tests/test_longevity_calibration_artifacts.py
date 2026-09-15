from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"
GOLD = ROOT / "data/gold/longevity_threshold_run_calibration_audit"


def _json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((DOCS / name).read_text()))


def test_step_i_reconstruction_and_peak_regression_are_exact() -> None:
    summary = _json("longevity-calibration-summary.json")
    reconstruction = summary["reconstruction"]
    assert reconstruction["step_i_validation"]["mismatches"] == 0
    assert reconstruction["step_i_validation"]["maximum_numerical_difference"] == 0.0
    assert reconstruction["step_i_actual"]["mismatches"] == 0
    assert reconstruction["step_i_actual"]["maximum_longevity_difference"] == 0.0
    assert reconstruction["step_i_peak_hash"]["maximum_numerical_difference"] == 0.0
    assert reconstruction["step_i_peak_hash"]["scores_intervals_statuses_windows_unchanged"]


def test_constitutional_thresholds_weights_and_upstreams_remain_frozen() -> None:
    threshold = _json("longevity-threshold-forensics.json")
    verdict = _json("longevity-calibration-verdict.json")
    assert threshold["fixed_thresholds"] == {"p80": 80.0, "p90": 90.0}
    assert threshold["thresholds_changed"] is False
    assert verdict["weights_modified"] is False
    assert verdict["player_season_value_modified"] is False
    assert verdict["peak_modified"] is False
    assert verdict["official_methodology_created"] is False
    assert verdict["forbidden_inputs"] is False


def test_statuses_cover_master_universe_without_forced_provisional_points() -> None:
    rows = pq.read_table(GOLD / "longevity-uncertainty-research-2.parquet").to_pylist()
    counts = _json("longevity-status-output.json")["counts"]
    assert len(rows) == sum(counts.values()) == 5103
    assert counts == {
        "LONGEVITY_INTERVAL_ONLY": 2210,
        "LONGEVITY_UNAVAILABLE": 917,
        "OFFICIAL_LONGEVITY_POINT": 1976,
    }
    assert all(row["longevity_status"] != "PROVISIONAL_LONGEVITY_POINT" for row in rows)


def test_research_intervals_are_nested_and_active_careers_are_to_date() -> None:
    rows = pq.read_table(GOLD / "longevity-uncertainty-research-2.parquet").to_pylist()
    for row in rows:
        if row.get("longevity_central") is None:
            continue
        point = float(row["longevity_central"])
        assert row["longevity_lower_95"] <= row["longevity_lower_90"]
        assert row["longevity_lower_90"] <= row["longevity_lower_80"] <= point
        assert point <= row["longevity_upper_80"] <= row["longevity_upper_90"]
        assert row["longevity_upper_90"] <= row["longevity_upper_95"]
        if row["active_career_status"] == "TO_DATE_NO_PROJECTION":
            assert "PROJECTION" not in row["reason_codes_json"]


def test_point_gates_are_not_weakened_to_force_promotion() -> None:
    calibration = _json("longevity-aggregate-calibration.json")["patterns"]
    assert calibration["FULL_REFERENCE"]["point_eligible"] is True
    for pattern in (
        "MIXED_PROVISIONAL_INTERVAL",
        "PARTIAL_PRESENCE_LATE",
        "TRADITIONAL_CAREER",
        "EARLY_TRADITIONAL_TO_EXPANDED",
    ):
        assert calibration[pattern]["point_eligible"] is False
    verdict = _json("longevity-calibration-verdict.json")
    assert verdict["longevity_verdict"] == "LONGEVITY_AGGREGATION_LIMITED"


def test_output_fingerprint_is_deterministic() -> None:
    summary = _json("longevity-calibration-summary.json")
    assert (
        summary["output_fingerprint"]
        == "15dd0713f3629e0e4a39b0ac718061053e08054ff49f498fe284e3cce83b1c9c"
    )
    assert summary["network_requests"] == 0
