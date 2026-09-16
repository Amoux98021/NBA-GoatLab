from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def test_step_0015n_verdict_and_frozen_rules() -> None:
    summary = json.loads((ROOT / "docs/data/overall-v2-promotion-summary.json").read_text())
    assert summary["step_status"] == "PASS"
    assert summary["promotion_verdict"] == "DO_NOT_PROMOTE_OVERALL_V2"
    assert summary["selected_coupling"] == "C2_PATTERN_GAUSSIAN"
    assert (
        summary["output_fingerprint"]
        == "b6248062490ca6b2d63e616af5ac759a59abc9ea3e9dc15dd4f2bd264741bb95"
    )
    assert summary["deterministic_rebuild_verified"] is True
    assert summary["promotion_gates"]["ranking_population_not_structurally_truncated"] is False
    assert summary["v1_v2_overlaps"] is None


def test_no_v2_top100_is_published_after_failed_promotion() -> None:
    assert not (ROOT / "docs/data/overall-v2-top100.json").exists()
    assert not (ROOT / "data/gold/overall_v2_promotion_audit/overall-v2-top100.parquet").exists()


def test_overall_v2_statuses_do_not_renormalize_or_penalize() -> None:
    rows = pq.read_table(
        ROOT / "data/gold/overall_v2_promotion_audit/overall-v2-player-scores.parquet"
    ).to_pylist()
    assert len(rows) == 5_103
    assert all(row["weight_renormalized"] is False for row in rows)
    assert all(row["confidence_penalty_applied"] is False for row in rows)
    assert all(row["interval_midpoint_used_as_exact"] is False for row in rows)


def test_mixed_pattern_fails_frozen_gate_without_rounding() -> None:
    report = json.loads((ROOT / "docs/data/overall-v2-dependence-validation.json").read_text())
    mixed = report["selected_patterns"]["MIXED_PROVISIONAL_INTERVAL"]
    assert mixed["mae"] > 2.0
    assert mixed["point_eligible"] is False
    assert mixed["gates"]["mae_lte_2"] is False
