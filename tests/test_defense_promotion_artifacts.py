from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"
GOLD = ROOT / "data/gold/defense_v2_promotion_audit"


def _summary() -> dict[str, object]:
    return json.loads((DOCS / "defense-v2-promotion-summary.json").read_text())


def test_candidate_b_reconstruction_is_exact() -> None:
    summary = _summary()
    reconstruction = summary["candidate_b_reconstruction"]
    assert isinstance(reconstruction, dict)
    assert reconstruction["exact"] is True
    assert reconstruction["maximum_score_difference"] == 0.0
    assert reconstruction["maximum_shrunk_presence_difference"] == 0.0


def test_promotion_is_blocked_by_fallback_not_execution() -> None:
    summary = _summary()
    assert summary["result"] == "PASS"
    assert summary["promotion_verdict"] == "DO_NOT_PROMOTE"
    gates = summary["promotion_gates"]
    assert isinstance(gates, dict)
    assert gates["fallback_mae_at_most_8_points"] is False
    assert gates["expected_presence_cross_validated_r_squared_at_least_0_10"] is False


def test_frozen_outputs_remain_unchanged() -> None:
    summary = _summary()
    assert summary["frozen_v1_mutated"] is False
    assert summary["frozen_overall_mutated"] is False
    assert summary["defense_methodology_version"] is None
    assert summary["provisional_overall_version"] is None


def test_candidate_outputs_preserve_regular_season_and_missingness() -> None:
    table = pq.read_table(GOLD / "defense-v2-season-components.parquet")
    rows = table.to_pylist()
    assert {row["season_type"] for row in rows} == {"REGULAR"}
    assert all(row["final_presence"] is not None for row in rows)
    assert any(row["fallback_type"] == "EXPECTED_PRESENCE" for row in rows)
    assert any(row["role_aware_actions"] is None for row in rows)


def test_counterfactual_does_not_overwrite_published_overall() -> None:
    table = pq.read_table(GOLD / "overall-defense-v2-counterfactual.parquet")
    assert table.num_rows == 5103
    assert not any(table.column("published_v1_overwritten").to_pylist())
    summary = _summary()
    impact = summary["top_ranking_impact"]
    assert isinstance(impact, dict)
    assert impact["players_ranked"] == 1882


def test_report_and_partition_fingerprints_are_present() -> None:
    summary = _summary()
    assert summary["deterministic_rebuild_verified"] is True
    fingerprint = summary["output_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    partitions = summary["output_partitions"]
    assert isinstance(partitions, list) and len(partitions) == 5
    assert all(len(row["sha256"]) == 64 for row in partitions)
