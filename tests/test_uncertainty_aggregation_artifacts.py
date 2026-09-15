from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((DOCS / name).read_text()))


def test_step_h_reconstruction_is_exact() -> None:
    summary = _json("peak-longevity-uncertainty-summary.json")
    reconstruction = summary["reconstruction"]
    assert reconstruction["season_rows"] == 22457
    assert reconstruction["anchor_rows"] == 14687
    assert reconstruction["mismatches"] == 0
    assert reconstruction["maximum_numerical_difference"] == 0.0
    assert reconstruction["raw_candidate_d_mismatches"] == 0


def test_research_architectures_and_verdicts_are_not_promotions() -> None:
    verdict = _json("peak-longevity-uncertainty-verdict.json")
    assert verdict["step_result"] == "PASS"
    assert verdict["peak_weights_modified"] is False
    assert verdict["longevity_weights_modified"] is False
    assert verdict["player_season_value_modified"] is False
    assert verdict["official_methodology_created"] is False
    assert verdict["awards_postseason_championship_inputs"] is False
    assert verdict["player_specific_logic"] is False


def test_peak_and_longevity_status_rows_cover_master_universe() -> None:
    root = ROOT / "data/gold/peak_longevity_uncertainty_audit"
    peak = pq.read_table(root / "peak-uncertainty-research.parquet").to_pylist()
    longevity = pq.read_table(root / "longevity-uncertainty-research.parquet").to_pylist()
    assert len(peak) == len(longevity) == 5103
    assert sum(row.get("peak_central") is not None for row in peak) == 2456
    assert sum(row.get("longevity_central") is not None for row in longevity) == 4186


def test_intervals_are_nested_and_active_players_are_not_projected() -> None:
    root = ROOT / "data/gold/peak_longevity_uncertainty_audit"
    for name, prefix in (
        ("peak-uncertainty-research.parquet", "peak"),
        ("longevity-uncertainty-research.parquet", "longevity"),
    ):
        for row in pq.read_table(root / name).to_pylist():
            if row.get(f"{prefix}_central") is None:
                continue
            point = float(row[f"{prefix}_central"])
            assert row[f"{prefix}_lower_95"] <= row[f"{prefix}_lower_90"]
            assert row[f"{prefix}_lower_90"] <= row[f"{prefix}_lower_80"] <= point
            assert point <= row[f"{prefix}_upper_80"] <= row[f"{prefix}_upper_90"]
            assert row[f"{prefix}_upper_90"] <= row[f"{prefix}_upper_95"]
            if row["active_career_status"] == "TO_DATE_NO_PROJECTION":
                assert "PROJECTION" not in row["reason_codes_json"]


def test_thresholds_and_weights_remain_frozen() -> None:
    scale = _json("peak-longevity-threshold-scale.json")
    assert scale["season_thresholds"]["p80"] == 80.0
    assert scale["season_thresholds"]["p90"] == 90.0
    assert scale["peak_weights"] == {"single_season_apex": 0.3, "three_year": 0.7}
    assert scale["longevity_weights"] == {
        "breadth": 0.35,
        "capped_area": 0.4,
        "longest_run": 0.25,
    }
    assert scale["ecdf_policy"]["recompute_reference_each_draw"] is False


def test_simulation_and_fingerprint_are_deterministic_metadata() -> None:
    summary = _json("peak-longevity-uncertainty-summary.json")
    assert summary["aggregation_policy"]["draws"] == 2500
    assert summary["aggregation_policy"]["simulation_method"] == "U3_STRATIFIED_BLOCK"
    assert (
        summary["output_fingerprint"]
        == "4f44cf63450105d8c215aa20a0b3078dc8b9b5c907f2f03553eff390195a150a"
    )
    assert summary["deterministic_rebuild_verified"] is True
    assert summary["network_requests"] == 0


def test_within_player_dependence_is_measured_and_preserved() -> None:
    dependence = _json("peak-longevity-residual-dependence.json")["by_measurement_form"]
    assert dependence
    assert all(row["players"] > 0 for row in dependence.values())
    assert all(0.0 < row["player_effect_variance_share"] < 1.0 for row in dependence.values())
    propagation = _json("peak-longevity-propagation-comparison.json")
    assert propagation["selected"] == "U3_STRATIFIED_BLOCK"
    assert "U0_INDEPENDENT" in propagation["methods"]
