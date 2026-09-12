from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def _json(name: str) -> dict[str, object]:
    return json.loads((ROOT / "docs/data" / name).read_text(encoding="utf-8"))


def test_frozen_v1_reconstructs_exactly_without_mutation() -> None:
    summary = _json("defense-forensic-audit-summary.json")
    reconstruction = summary["v1_reconstruction"]
    assert isinstance(reconstruction, dict)
    assert reconstruction["players_compared"] == 5103
    assert reconstruction["mismatches"] == 0
    assert reconstruction["maximum_absolute_difference"] == 0.0
    assert summary["frozen_v1_mutated"] is False
    assert summary["frozen_overall_mutated"] is False


def test_audit_never_leaks_postseason_or_awards_into_defense() -> None:
    table = pq.read_table(
        ROOT / "data/gold/defense_forensic_audit/v1-season-decomposition.parquet",
        columns=["season_type"],
    )
    assert set(table.column("season_type").to_pylist()) == {"REGULAR"}
    candidates = _json("defense-candidate-comparison.json")
    validation = candidates["award_validation"]
    assert isinstance(validation, dict)
    assert validation["awards_used_as_score_inputs"] is False


def test_v2_is_counterfactual_and_scores_are_bounded() -> None:
    summary = _json("defense-forensic-audit-summary.json")
    assert summary["constitutional_verdict"] == "REQUIRES_REVISION"
    table = pq.read_table(
        ROOT / "data/gold/defense_forensic_audit/defense-v2-candidate-scores.parquet"
    )
    rows = table.to_pylist()
    assert len(rows) == 5103
    assert all(row["published_v1_replaced"] is False for row in rows)
    assert all(
        row["defense_score"] is None or 0.0 <= float(row["defense_score"]) <= 100.0 for row in rows
    )


def test_team_identity_dominance_is_empirically_recorded() -> None:
    report = _json("defense-team-attribution-audit.json")
    assert report["team_season_suppression_intraclass_correlation"] == 1.0
    assert float(report["final_v1_season_composite_between_team_eta_squared"]) > 0.80
    assert float(report["career_raw_correlation_with_team_suppression"]) > float(
        report["career_raw_correlation_with_action_context"]
    )


def test_presence_samples_are_never_silently_zeroed() -> None:
    report = _json("defensive-presence-impact-audit.json")
    statuses = report["status_counts"]
    assert isinstance(statuses, dict)
    assert int(statuses["INSUFFICIENT_SAMPLE"]) > 0
    table = pq.read_table(
        ROOT / "data/gold/defense_forensic_audit/defensive-presence-estimates.parquet",
        columns=["confidence", "shrunk_difference_points"],
    )
    for row in table.to_pylist():
        if row["confidence"] == "INSUFFICIENT_SAMPLE":
            assert row["shrunk_difference_points"] is None
