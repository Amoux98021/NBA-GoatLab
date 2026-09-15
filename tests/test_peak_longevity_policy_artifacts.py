from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"
GOLD = ROOT / "data/gold/peak_longevity_policy_freeze"


def load_json(name: str) -> dict[str, object]:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_upstream_reconstruction_is_exact() -> None:
    report = load_json("step-0015k-upstream-reconstruction.json")
    for key in ("step_0015h", "step_0015i_peak", "step_0015j_longevity"):
        reconstruction = report[key]
        assert reconstruction["maximum_numerical_difference"] == 0.0


def test_peak_policy_freezes_formula_and_explains_unavailable_players() -> None:
    report = load_json("peak-v2-status-summary.json")
    assert report["status_counts"] == {
        "OFFICIAL_PEAK_POINT": 974,
        "PEAK_INTERVAL_ONLY": 71,
        "PEAK_UNAVAILABLE": 2647,
        "PROVISIONAL_PEAK_POINT": 1411,
    }
    assert report["coverage_reason_counts"] == {
        "CONSTITUTIONALLY_INELIGIBLE_FEWER_THAN_THREE_QUALIFIED_SEASONS": 2529,
        "CONSTITUTIONALLY_INELIGIBLE_NO_CONTIGUOUS_QUALIFYING_WINDOW": 118,
        "INTERVAL_ONLY": 71,
        "OFFICIAL_POINT": 974,
        "PROVISIONAL_POINT": 1411,
    }
    validation = load_json("peak-v2-promotion-validation.json")
    assert validation["architecture"] == {
        "active_career_policy": "TO_DATE_NO_PROJECTION",
        "apex_weight": 0.30,
        "draws": 2500,
        "fixed_reference_ecdf": True,
        "simulation": "U3_STRATIFIED_BLOCK",
        "three_year_weight": 0.70,
        "window_reselected_each_draw": True,
    }
    table = pq.read_table(GOLD / "peak-v2.parquet").to_pydict()
    assert {value for value in table["draws"] if value is not None} == {2500}
    assert set(table["active_career_policy"]) == {"TO_DATE_NO_PROJECTION"}


def test_longevity_policy_freezes_architecture_and_blocks_midpoints() -> None:
    report = load_json("longevity-v2-status-summary.json")
    assert report["status_counts"] == {
        "LONGEVITY_INTERVAL_ONLY": 2210,
        "LONGEVITY_UNAVAILABLE": 917,
        "OFFICIAL_LONGEVITY_POINT": 1976,
    }
    assert report["ranking_grade_points"] == 1976
    assert report["interval_midpoint_official"] is False
    assert report["architecture"] == {
        "active_career_policy": "TO_DATE_NO_PROJECTION",
        "capped_area_weight": 0.40,
        "elite_breadth_weight": 0.35,
        "longest_run_weight": 0.25,
        "p80": 80.0,
        "p90": 90.0,
    }


def test_overall_audit_is_eligibility_only_and_never_reweights() -> None:
    report = load_json("overall-v2-eligibility-audit.json")
    assert report["status_counts"] == {
        "COMPLETE_POINT_DIMENSIONS": 641,
        "INTERVAL_DIMENSION_PRESENT": 1241,
        "REQUIRED_DIMENSION_UNAVAILABLE": 3221,
    }
    assert report["overall_score_created"] is False
    assert report["weight_redistribution_allowed"] is False
    assert report["interval_midpoint_as_official_allowed"] is False
    columns = pq.read_schema(GOLD / "overall-eligibility.parquet").names
    assert "overall_score" not in columns
    assert "overall_rank" not in columns


def test_v1_preservation_and_step_fingerprint() -> None:
    preservation = load_json("step-0015k-v1-preservation.json")
    summary = load_json("step-0015k-summary.json")
    assert preservation["all_unchanged"] is True
    assert preservation["expected_hashes"] == preservation["post_build_hashes"]
    assert preservation["new_overall_score_created"] is False
    assert summary["deterministic_rebuild_verified"] is True
    assert summary["output_fingerprint"] == (
        "3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f"
    )
