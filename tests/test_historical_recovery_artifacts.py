from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((DOCS / name).read_text(encoding="utf-8")))


def test_original_missingness_and_source_scope_are_reproduced() -> None:
    summary = _json("historical-data-recovery-summary.json")
    assert summary["original_missingness"] == {
        "early_limited_player_seasons": 5881,
        "missing_apg": 5863,
        "missing_presence": 2074,
        "missing_rebound_action": 5242,
        "missing_ts": 5321,
        "ppg_team_only": 4311,
    }
    acquisition = summary["acquisition"]
    assert acquisition["players_requested"] == 2234
    assert acquisition["request_states"].get("PENDING", 0) == 0
    assert acquisition["request_states"].get("RETRYABLE_FAILURE", 0) == 0


def test_recovery_is_factual_and_never_missing_as_zero() -> None:
    verdict = _json("historical-recovery-verdict.json")
    assert verdict["step_result"] == "PASS"
    assert verdict["recovery_verdict"] == "MATERIAL_RECOVERY"
    assert verdict["model_imputation_used"] is False
    assert verdict["frozen_outputs_modified"] is False
    table = pq.read_table(
        ROOT / "data/silver/historical_player_season_facts_v2_research/part-00000.parquet"
    )
    rows = table.to_pylist()
    inaugural = [row for row in rows if row["season_id"] == 1946]
    assert inaugural
    assert all(row["rebounds_total"] is None for row in inaugural)
    assert all(row["steals_total"] is None for row in inaugural)
    assert all(row["blocks_total"] is None for row in inaugural)


def test_recorded_stat_boundaries_and_ts_validation() -> None:
    availability = _json("historical-stat-availability-map.json")["statistics"]
    assert availability["AST"]["first_officially_recorded_season"] == 1946
    assert availability["REB"]["first_officially_recorded_season"] == 1950
    assert availability["STL"]["first_officially_recorded_season"] == 1973
    assert availability["BLK"]["first_officially_recorded_season"] == 1973
    inventory = _json("historical-external-source-inventory.json")
    validation = inventory["true_shooting_validation"]
    assert validation["official_advanced_overlap"] > 10000
    assert float(validation["maximum_absolute_difference"]) <= 0.0005000001


def test_identity_source_precedence_and_pipeline_findings_are_explicit() -> None:
    identity = _json("historical-recovery-identity-crosswalk.json")
    assert identity["business_key"] == "official NBA PLAYER_ID"
    assert identity["unresolved"] == 0
    field_audit = _json("historical-current-corpus-field-audit.json")
    assert field_audit["pipeline_bug_count"] > 0
    source = _json("historical-external-source-inventory.json")
    assert source["source_precedence_changed"] is True
    assert source["third_party_player_stat_source_ingested"] is False


def test_recovery_outputs_are_deterministic_and_versioned() -> None:
    summary = _json("historical-data-recovery-summary.json")
    assert summary["result"] == "PASS"
    assert summary["deterministic_rebuild_verified"] is True
    assert summary["facts_methodology_version"] == (
        "goatlab-historical-player-season-facts-v2-research"
    )
    fingerprint = summary["output_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert len(summary["outputs"]) == 5
