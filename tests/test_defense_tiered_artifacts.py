from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def test_step_0015m_summary_and_status_artifacts() -> None:
    summary = json.loads((ROOT / "docs/data/defense-v2-tiered-promotion-summary.json").read_text())
    assert summary["step_status"] == "PASS"
    assert summary["defense_promotion_verdict"] == "PROMOTE_DEFENSE_V2_WITH_LIMITATIONS"
    assert summary["reconstruction"]["maximum_numerical_difference"] == 0.0
    assert summary["selected_team_weight"] == 0.10
    assert summary["new_top_100_published"] is False
    assert summary["deterministic_rebuild_verified"] is True
    assert (
        summary["output_fingerprint"]
        == "a2056a6d793b2f82066c07bc4924787d3e95f8485ef37ff15911bfb7a321deb7"
    )
    assert sum(summary["season_status_counts"].values()) == 22_457
    assert sum(summary["career_status_counts"].values()) == 5_103


def test_defense_v2_artifacts_preserve_missingness_and_nested_intervals() -> None:
    root = ROOT / "data/gold/defense_v2_tiered_promotion_audit"
    seasons = pq.read_table(root / "defense-v2-season-measurements.parquet").to_pylist()
    careers = pq.read_table(root / "player-defense-v2-tiered.parquet").to_pylist()
    assert all(row["season_type"] == "REGULAR" for row in seasons)
    assert all("NO_MISSING_PRESENCE_IMPUTATION" in row["reason_codes_json"] for row in seasons)
    for row in careers:
        if row["defense_central"] is None:
            continue
        assert row["defense_lower_95"] <= row["defense_lower_90"]
        assert row["defense_lower_90"] <= row["defense_lower_80"]
        assert row["defense_lower_80"] <= row["defense_central"]
        assert row["defense_central"] <= row["defense_upper_80"]
        assert row["defense_upper_80"] <= row["defense_upper_90"]
        assert row["defense_upper_90"] <= row["defense_upper_95"]
        if row["defense_status"] == "DEFENSE_INTERVAL_ONLY":
            assert row["ranking_grade_defense_point"] is False


def test_v1_top100_transition_is_archived_order_only() -> None:
    rows = pq.read_table(
        ROOT / "data/gold/defense_v2_tiered_promotion_audit/v1-top100-defense-transition.parquet"
    ).to_pylist()
    assert sorted(row["v1_overall_rank"] for row in rows) == list(range(1, 101))
    assert all(row["v1_order_preserved"] for row in rows)


def test_career_uncertainty_preserves_player_dependence() -> None:
    report = json.loads((ROOT / "docs/data/defense-v2-career-uncertainty.json").read_text())
    assert report["selected"] == "PLAYER_BLOCK_WITH_CAREER_LEVEL_GROUPED_CONFORMAL"
    widths = report["candidate_90_widths"]
    assert widths["PLAYER_BLOCK"]["mean"] > widths["INDEPENDENT_BASELINE"]["mean"]


def test_active_players_use_the_same_status_vocabulary() -> None:
    report = json.loads((ROOT / "docs/data/defense-v2-status-summary.json").read_text())
    active = report["by_active_status"]["ACTIVE_TO_CUTOFF"]
    assert sum(active.values()) == 582
    assert set(active) <= {
        "OFFICIAL_DEFENSE_POINT",
        "PROVISIONAL_DEFENSE_POINT",
        "DEFENSE_INTERVAL_ONLY",
        "DEFENSE_UNAVAILABLE",
    }
