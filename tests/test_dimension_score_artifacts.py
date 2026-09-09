from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dimension_reports_are_complete_and_fingerprinted() -> None:
    summary = json.loads((DOCS / "dimension-score-summary.json").read_text())
    report_names = (
        "goat-v1-dimension-formulas.yaml",
        "dimension-score-sensitivity.json",
        "dimension-score-cross-audit.json",
        "dimension-score-era-fairness.json",
        "dimension-score-modern-bridge.json",
        "dimension-score-case-studies.json",
    )
    paths = [DOCS / report_names[0], *(DOCS / name for name in sorted(report_names[1:]))]
    fingerprint = hashlib.sha256(
        "\n".join(f"{path.name}:{_sha256(path)}" for path in paths).encode()
    ).hexdigest()

    assert summary["methodology_version"] == "goatlab-v1-dimension-scores-v1"
    assert summary["master_players"] == 5103
    assert summary["reference_players"] == 2656
    assert summary["dimension_score_rows"] == 5103 * 7
    assert summary["complete_seven_dimension_players"] > 0
    assert summary["network_requests"] == 0
    assert summary["official_overall_score_created"] is False
    assert summary["official_overall_weights_selected"] is False
    assert summary["deterministic_rebuild_verified"] is True
    assert summary["committed_report_fingerprint"] == fingerprint


def test_all_player_dimension_rows_are_bounded_and_missingness_is_explicit() -> None:
    rows = pq.read_table(ROOT / "data/gold/player_dimension_scores/part-00000.parquet").to_pylist()
    assert len(rows) == 5103 * 7
    assert len({(row["player_id"], row["dimension"]) for row in rows}) == len(rows)
    assert {row["dimension"] for row in rows} == {
        "PEAK",
        "LONGEVITY",
        "OFFENSE",
        "DEFENSE",
        "PLAYOFFS",
        "ACCOLADES",
        "WINNING",
    }
    for row in rows:
        score = row["score"]
        if score is None:
            assert row["coverage_status"] in {
                "INSUFFICIENT_SAMPLE",
                "SOURCE_UNAVAILABLE",
                "NOT_QUERIED",
            }
            assert row["evidence_confidence"] == "UNAVAILABLE"
        else:
            assert math.isfinite(score)
            assert 0.0 <= score <= 100.0
    assert all(
        row["completeness_context"] in {"TO_DATE_NO_PROJECTION", "RECORDED_TO_CORPUS_CUTOFF"}
        for row in rows
    )


def test_formula_registry_enforces_cross_dimension_ownership() -> None:
    registry = yaml.safe_load((DOCS / "goat-v1-dimension-formulas.yaml").read_text())
    formulas = {row["dimension"]: row for row in registry["dimensions"]}
    assert set(formulas) == {
        "PEAK",
        "LONGEVITY",
        "OFFENSE",
        "DEFENSE",
        "PLAYOFFS",
        "ACCOLADES",
        "WINNING",
    }
    assert "DPOY" in formulas["DEFENSE"]["excluded"]
    assert "All-Defense" in formulas["DEFENSE"]["excluded"]
    assert "statistical titles" in formulas["OFFENSE"]["excluded"]
    assert "series wins" in formulas["PLAYOFFS"]["excluded"]
    assert "NBA Champion" in formulas["ACCOLADES"]["excluded"]
    assert "raw champion award count" in formulas["WINNING"]["excluded"]
    assert registry["era_dominance"] == "DIAGNOSTIC_ONLY_NOT_ADDITIVE"
    assert registry["common"]["modern_only_features_in_universal_scores"] is False


def test_stacking_bridge_and_structural_audits_are_explicit() -> None:
    summary = json.loads((DOCS / "dimension-score-summary.json").read_text())
    bridge = json.loads((DOCS / "dimension-score-modern-bridge.json").read_text())
    audit = json.loads((DOCS / "dimension-score-cross-audit.json").read_text())

    assert summary["winning_stacking_audit"]["within_season_tiers_are_mutually_exclusive"]
    assert summary["accolade_stacking_audit"]["cross_axis_same_season_caps"] > 0
    assert summary["accolade_stacking_audit"]["champion_events_used"] == 0
    assert bridge["modern_offense_bridge"]["universal_score_changed"] is False
    assert bridge["modern_defense_bridge"]["universal_score_changed"] is False
    assert bridge["defense_restricted_action_bridge"]["passes"] is True
    assert audit["complete_players"] == summary["complete_seven_dimension_players"]
    assert audit["random_simplex_weight_audit"]["official_overall_weights_selected"] is False
    assertions = audit["ownership_assertions"]
    assert assertions["peak_longevity_capped"] is True
    assert assertions["regular_postseason_separated"] is True
    assert assertions["winning_hierarchical_tiers"] is True
    assert assertions["accolades_same_season_capped"] is True
    assert assertions["playoffs_use_team_outcomes"] is False
    assert assertions["defense_uses_dpoy_or_all_defense"] is False
    assert assertions["offense_uses_stat_titles"] is False
    assert assertions["generic_wowy_additive"] is False
    assert assertions["era_dominance_additive"] is False


def test_every_formula_sensitivity_audits_bias_movers_and_missingness() -> None:
    report = json.loads((DOCS / "dimension-score-sensitivity.json").read_text())
    assert len(report["records"]) == 21
    assert {row["dimension"] for row in report["records"]} == {
        "PEAK",
        "LONGEVITY",
        "OFFENSE",
        "DEFENSE",
        "PLAYOFFS",
        "ACCOLADES",
        "WINNING",
    }
    for row in report["records"]:
        assert row["position_bias_status"] == "UNAVAILABLE_POSITION_COVERAGE_NOT_QUALIFIED"
        assert row["active_career_sensitivity"]
        assert row["era_sensitivity"]
        assert row["archetype_sensitivity"]
        assert len(row["largest_rank_movers"]) <= 10
        assert row["missingness_sensitivity"]["both_available"] == row["shared_players"]


def test_active_careers_are_cutoff_only_and_no_modern_leakage_occurs() -> None:
    rows = pq.read_table(ROOT / "data/gold/player_dimension_scores/part-00000.parquet").to_pylist()
    active = [row for row in rows if row["career_status"] == "ACTIVE_TO_CUTOFF"]
    assert active
    assert all(row["completeness_context"] == "TO_DATE_NO_PROJECTION" for row in active)
    components = pq.read_table(
        ROOT / "data/gold/player_dimension_components/part-00000.parquet"
    ).to_pylist()
    assert not any(
        row["component_name"] in {"modern_advanced_bonus", "tracking_bonus"} for row in components
    )
