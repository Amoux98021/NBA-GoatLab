from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def _json(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "docs/data" / name).read_text(encoding="utf-8")),
    )


def test_recovered_candidate_is_exactly_reconstructed() -> None:
    summary = _json("player-season-value-v2-promotion-summary.json")
    reconstruction = summary["reconstruction"]
    assert reconstruction["silver_rows"] == 22457
    assert reconstruction["raw_mismatches"] == 0
    assert reconstruction["percentile_mismatches"] == 0
    assert reconstruction["maximum_raw_difference"] == 0.0


def test_source_conflicts_are_stable_but_not_averaged() -> None:
    report = _json("player-season-value-v2-source-conflict-impact.json")
    assert report["conflicts"]["material_conflicts"] == 9299
    sensitivity = report["sensitivity"]["percentile_score"]
    assert float(sensitivity["mean_absolute_error"]) < 2.0
    assert float(sensitivity["more_than_5_points"]) < 0.10
    assert "never averaged" in report["sensitivity"]["interpretation"]


def test_missingness_and_confidence_remain_separate() -> None:
    coverage = _json("player-season-value-v2-coverage.json")
    assert coverage["remaining_missingness"]["unavailable_player_seasons"] == 1350
    summary = _json("player-season-value-v2-promotion-summary.json")
    assert summary["gates"]["missingness_explicit"] is True
    assert summary["gates"]["confidence_separate"] is True
    rows = pq.read_table(
        ROOT
        / "data/gold/player_season_value_v2_promotion_audit/candidate-d-reconstruction.parquet"
    ).to_pylist()
    assert any(row["player_season_value_raw"] is None for row in rows)
    assert all(row["season_type"] == "REGULAR" for row in rows)


def test_team_context_cap_and_ownership_hold() -> None:
    influence = _json("player-season-value-v2-influence.json")
    assert (
        float(influence["influence"]["team_context"]["maximum_effective_weight"])
        <= 0.05500000000000001
    )
    verdict = _json("player-season-value-v2-promotion-verdict.json")
    assert verdict["gates"]["no_award_playoff_championship_inputs"] is True
    assert verdict["gates"]["no_player_specific_tuning"] is True


def test_frozen_architectures_are_counterfactual_only() -> None:
    peak = _json("player-season-value-v2-peak-counterfactual.json")
    longevity = _json("player-season-value-v2-longevity-counterfactual.json")
    assert peak["architecture"] == "70% contiguous three-year + 30% apex"
    assert longevity["architecture"].startswith("35% P80 breadth")
    assert peak["promoted"] is False
    assert longevity["promoted"] is False
    overall = _json("player-season-value-v2-overall-sensitivity.json")
    assert overall["status"] == "NOT_PRODUCED_PROMOTION_GATE_FAILED"


def test_promotion_is_blocked_by_actual_regime_comparability() -> None:
    summary = _json("player-season-value-v2-promotion-summary.json")
    assert summary["result"] == "PASS"
    assert summary["promotion_verdict"] == "DO_NOT_PROMOTE"
    assert summary["official_methodology_version"] is None
    assert summary["gates"]["regime_comparability_acceptable"] is False
    assert isinstance(summary["output_fingerprint"], str)
    assert len(summary["output_fingerprint"]) == 64
