from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"
GOLD = ROOT / "data/gold"


def load(name: str) -> dict[str, object]:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_summary_freezes_upstream_and_constitutional_guards() -> None:
    report = load("overall-ranking-summary.json")
    assert report["result"] == "PASS"
    assert report["methodology_version"] == "goatlab-v1-overall-v1"
    assert report["upstream_methodology"] == "goatlab-v1-dimension-scores-v1"
    assert (
        report["upstream_fingerprint"]
        == "0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a"
    )
    assertions = report["constitutional_assertions"]
    assert assertions == {
        "confidence_does_not_change_score": True,
        "dimension_formulas_unchanged": True,
        "era_dominance_excluded": True,
        "missing_weights_not_redistributed": True,
        "modern_diagnostics_excluded": True,
        "no_player_specific_weights": True,
    }


def test_weights_and_output_ranges() -> None:
    registry = yaml.safe_load((DOCS / "overall-weight-methodologies.yaml").read_text())
    assert registry["default_candidate"] == "C_REDUNDANCY_ADJUSTED"
    for candidate in registry["candidates"].values():
        weights = candidate["weights"]
        assert set(weights) == {
            "PEAK",
            "LONGEVITY",
            "OFFENSE",
            "DEFENSE",
            "PLAYOFFS",
            "ACCOLADES",
            "WINNING",
        }
        assert abs(sum(weights.values()) - 1.0) < 1e-12
        assert min(weights.values()) >= 0
    table = pq.read_table(GOLD / "player_overall_scores/part-00000.parquet")
    rows = table.to_pylist()
    ranked = [row for row in rows if row["overall_rank"] is not None]
    assert len(rows) == 5103
    assert len(ranked) == 1882
    assert all(0 <= row["overall_score"] <= 100 for row in ranked)
    assert all(row["accolades_score"] is not None for row in ranked)
    assert all(row["overall_score"] is None for row in rows if row["accolades_score"] is None)
    assert all(
        row["active_career_policy"] in {"TO_DATE_NO_PROJECTION", "NOT_ACTIVE"} for row in rows
    )


def test_accolades_unknown_is_not_zero_and_top100_is_resolved() -> None:
    audit = load("ranking-eligibility-audit.json")
    assert audit["not_queried_accolades"] == 2963
    assert audit["additional_award_queries_executed"] == 0
    assert audit["unresolved_upper_bound_crossers"] == 0
    assert audit["classification_counts"]["SAFE_TO_EXCLUDE_FROM_V1_QUERY"] == 303
    assert audit["safe_player_closest_cutoff_gap"] < -5
    top = pq.read_table(GOLD / "overall_top100/part-00000.parquet").to_pylist()
    assert len(top) == 100
    assert [row["overall_rank"] for row in top] == list(range(1, 101))
    assert all(row["eligibility_status"] == "ELIGIBLE_OFFICIAL" for row in top)
    assert all(row["accolades_score"] is not None for row in top)


def test_effective_influence_and_sensitivity_are_complete() -> None:
    influence = load("overall-effective-influence.json")
    assert len(influence["candidates"]) == 4
    for candidate in influence["candidates"].values():
        assert abs(sum(candidate["effective_shapley_influence"].values()) - 1.0) < 1e-10
        assert len(candidate["bootstrap_effective_influence"]) == 7
        assert candidate["local_perturbation_summary"]["minimum_spearman"] > 0.99
    loo = load("overall-leave-one-out.json")
    assert set(loo["dimensions"]) == {
        "PEAK",
        "LONGEVITY",
        "OFFENSE",
        "DEFENSE",
        "PLAYOFFS",
        "ACCOLADES",
        "WINNING",
    }
    random = load("overall-random-simplex.json")
    assert random["draws"] == 10000
    assert random["seed"] == 150015
    assert random["spearman_vs_default"]["min"] > 0.99


def test_no_future_projection_or_illegal_dimension_in_gold_schema() -> None:
    names = set(
        pq.ParquetFile(GOLD / "player_overall_scores/part-00000.parquet").schema_arrow.names
    )
    assert "era_dominance_score" not in names
    assert "projected_score" not in names
    assert "overall_score" in names
    assert all(
        f"{name.lower()}_score" in names
        for name in ("PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING")
    )
