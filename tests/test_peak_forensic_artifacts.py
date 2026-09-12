from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def _json(name: str) -> dict[str, object]:
    return json.loads((ROOT / "docs/data" / name).read_text(encoding="utf-8"))


def test_frozen_v1_peak_reconstructs_exactly_without_mutation() -> None:
    summary = _json("peak-v1-forensic-summary.json")
    reconstruction = summary["reconstruction"]
    assert isinstance(reconstruction, dict)
    assert reconstruction["players"] == 5103
    assert reconstruction["mismatches"] == 0
    assert reconstruction["maximum_raw_difference"] == 0.0
    assert reconstruction["maximum_score_difference"] == 0.0
    gates = summary["audit_gates"]
    assert isinstance(gates, dict)
    assert gates["frozen_non_peak_dimensions_unchanged"] is True
    assert gates["frozen_overall_unchanged"] is True


def test_peak_decomposition_uses_regular_season_and_preserves_missingness() -> None:
    table = pq.read_table(
        ROOT / "data/gold/peak_forensic_audit/v1-season-quality-decomposition.parquet"
    )
    rows = table.to_pylist()
    assert rows
    assert {row["season_type"] for row in rows} == {"REGULAR"}
    assert any(row["spg"] is None for row in rows)
    assert all(int(row["observed_inputs"]) > 0 for row in rows)


def test_masking_audit_is_deterministic_and_exposes_construct_change() -> None:
    report = _json("peak-missingness-mask-audit.json")
    regimes = report["regimes"]
    assert isinstance(regimes, dict)
    assert regimes["CURRENT_V1_FULL"]["mean_absolute_error"] == 0.0
    assert float(regimes["EARLY_NO_STEALS_BLOCKS"]["mean_absolute_error"]) > 0.0
    assert float(regimes["TEAM_CONTEXT_UNAVAILABLE"]["mean_absolute_error"]) > 10.0
    assert report["advanced_or_possession_inputs_in_v1"] is False


def test_peak_audit_records_no_cross_dimension_leakage() -> None:
    summary = _json("peak-v1-forensic-summary.json")
    gates = summary["audit_gates"]
    assert isinstance(gates, dict)
    assert gates["no_award_playoff_winning_leakage"] is True
    assert gates["regular_season_only"] is True
    validation = summary["independent_validation"]
    assert isinstance(validation, dict)
    assert validation["awards_used_as_inputs"] is False


def test_research_candidate_is_not_promoted_and_counterfactual_is_bounded() -> None:
    summary = _json("peak-v1-forensic-summary.json")
    assert summary["constitutional_verdict"] == "REQUIRES_REVISION"
    assert summary["research_candidate_promoted"] is False
    table = pq.read_table(ROOT / "data/gold/peak_forensic_audit/peak-v2-research-scores.parquet")
    rows = table.to_pylist()
    assert rows
    assert all(row["promoted"] is False for row in rows)
    assert all(
        row["research_peak"] is None or 0.0 <= float(row["research_peak"]) <= 100.0 for row in rows
    )


def test_counterfactual_preserves_frozen_non_peak_dimensions() -> None:
    table = pq.read_table(
        ROOT / "data/gold/peak_forensic_audit/overall-peak-v2-counterfactual.parquet"
    )
    rows = table.to_pylist()
    assert rows
    assert all(row["published_v1_overwritten"] is False for row in rows)
    assert all(
        row["counterfactual_overall"] is None
        or 0.0 <= float(row["counterfactual_overall"]) <= 100.0
        for row in rows
    )


def test_output_fingerprint_is_present_and_offline() -> None:
    summary = _json("peak-v1-forensic-summary.json")
    fingerprint = summary["output_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert summary["network_requests"] == 0
