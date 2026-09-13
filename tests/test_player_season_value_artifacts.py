from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def _json(name: str) -> dict[str, object]:
    return json.loads((ROOT / "docs/data" / name).read_text(encoding="utf-8"))


def test_audit_passes_without_promoting_an_incomplete_method() -> None:
    summary = _json("player-season-value-summary.json")
    assert summary["result"] == "PASS"
    assert summary["measurement_verdict"] == "PROMISING_BUT_NOT_READY"
    assert summary["production_methodology_created"] is False
    assert summary["network_requests"] == 0


def test_research_output_is_regular_season_only_and_missingness_is_preserved() -> None:
    table = pq.read_table(
        ROOT / "data/gold/player_season_value_audit/player-season-value-research.parquet"
    )
    rows = table.to_pylist()
    assert len(rows) == 22457
    assert {row["season_type"] for row in rows} == {"REGULAR"}
    assert any(row["player_season_value_raw"] is None for row in rows)
    assert all(row["promoted"] is False for row in rows)


def test_team_context_cap_and_confidence_separation_are_recorded() -> None:
    report = _json("player-season-value-component-influence.json")
    team = report["team_context"]
    assert isinstance(team, dict)
    assert float(team["maximum_effective_weight"]) <= 0.05500000000000001
    summary = _json("player-season-value-summary.json")
    gates = summary["promotion_gates"]
    assert isinstance(gates, dict)
    assert gates["confidence_separate"] is True
    assert gates["team_context_cap_at_most_10_percent"] is True


def test_masking_rejects_false_historical_comparability() -> None:
    report = _json("player-season-value-masking-audit.json")
    masking = report["masking"]
    assert isinstance(masking, dict)
    regimes = masking["regimes"]
    assert isinstance(regimes, dict)
    assert regimes["FULL_PORTABLE"]["mean_absolute_error"] == 0.0
    assert float(regimes["EXPANDED_BOX_NO_PRESENCE"]["mean_absolute_error"]) > 5.0
    assert regimes["EARLY_LIMITED"]["coverage_pct"] == 0.0


def test_frozen_architectures_and_outputs_remain_unchanged() -> None:
    summary = _json("player-season-value-summary.json")
    gates = summary["promotion_gates"]
    assert isinstance(gates, dict)
    assert gates["peak_70_30_unchanged"] is True
    assert gates["longevity_35_40_25_unchanged"] is True
    assert gates["frozen_v1_unchanged"] is True
    verdict = _json("player-season-value-verdict.json")
    assert verdict["defense_modified"] is False
    assert verdict["frozen_v1_overwritten"] is False


def test_counterfactuals_are_bounded_and_not_promoted() -> None:
    for name, field in (
        ("peak-counterfactual.parquet", "counterfactual_peak"),
        ("longevity-counterfactual.parquet", "counterfactual_longevity"),
        ("overall-counterfactual.parquet", "counterfactual_overall"),
    ):
        rows = pq.read_table(ROOT / "data/gold/player_season_value_audit" / name).to_pylist()
        assert rows
        assert all(row[field] is None or 0.0 <= float(row[field]) <= 100.0 for row in rows)


def test_output_fingerprint_is_present_and_offline_reproducible() -> None:
    summary = _json("player-season-value-summary.json")
    fingerprint = summary["output_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert summary["deterministic_rebuild_verified"] is True
