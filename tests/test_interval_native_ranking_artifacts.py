from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"
GOLD = ROOT / "data/gold/interval_native_ranking_policy_audit"


def load_json(name: str) -> dict[str, object]:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_step_0015n_reconstruction_and_policy_verdict() -> None:
    reconstruction = load_json("interval-ranking-reconstruction.json")
    assert reconstruction["status_mismatches"] == 0
    assert reconstruction["maximum_center_difference"] == 0.0
    status = load_json("ranking-policy-status.json")
    assert status["step_status"] == "PASS"
    assert status["publication_verdict"] == "VALID_PROBABILISTIC_RANKING_ONLY"
    assert status["overall_readiness_verdict"] == "OVERALL_V2_STILL_NOT_READY"
    assert status["top100_generated"] is False
    summary = load_json("interval-native-ranking-policy-summary.json")
    assert summary["deterministic_rebuild_verified"] is True
    assert (
        summary["output_fingerprint"]
        == "544843af8d316c6b5d54786b29562451ce01e3f6b5c35a0fe936e27fa2290a15"
    )


def test_distribution_rankability_is_independent_of_point_status() -> None:
    population = load_json("distribution-rankable-population.json")
    assert population["rankability"]["ALL_PLAYERS"] == {
        "distribution_rankable": 1882,
        "not_rankable": 3221,
        "population": 5103,
    }
    assert population["rankability"]["V1_TOP_100"]["distribution_rankable"] == 100
    rows = pq.read_table(GOLD / "distribution-rankable-player-ranks.parquet").to_pylist()
    assert len(rows) == 1882
    assert {row["distribution_rankability"] for row in rows} == {"DISTRIBUTION_RANKABLE"}
    assert any(row["overall_status"] == "OVERALL_INTERVAL_ONLY" for row in rows)
    assert not any(row["overall_status"] == "OVERALL_UNAVAILABLE" for row in rows)


def test_rank_outputs_obey_probability_and_interval_contracts() -> None:
    rows = pq.read_table(GOLD / "distribution-rankable-player-ranks.parquet").to_pylist()
    for row in rows:
        probabilities = [
            row["probability_top_10"],
            row["probability_top_25"],
            row["probability_top_50"],
            row["probability_top_100"],
        ]
        assert all(0.0 <= value <= 1.0 for value in probabilities)
        assert probabilities == sorted(probabilities)
        assert (
            row["rank_lower_95"]
            <= row["rank_lower_90"]
            <= row["rank_lower_80"]
            <= row["rank_lower_50"]
            <= row["median_rank"]
            <= row["rank_upper_50"]
            <= row["rank_upper_80"]
            <= row["rank_upper_90"]
            <= row["rank_upper_95"]
        )
        assert row["ranking_is_official"] is False
        assert row["shared_cross_player_calibration_uncertainty_modeled"] is False


def test_no_top100_is_generated_when_exact_policy_fails() -> None:
    status = load_json("ranking-policy-status.json")
    gates = status["policy_gates"]
    assert all(
        gates[f"{method}_exact_rank_gate"] is False
        for method in (
            "R0_CENTRAL_OVERALL_SORT",
            "R1_MEDIAN_RANK",
            "R2_EXPECTED_RANK",
            "R3_PAIRWISE_EXPECTED_WINS",
        )
    )
    assert gates["rank_band_calibration"] is True
    assert gates["topn_probability_calibration"] is True
    assert gates["pairwise_probability_calibration"] is True
    assert not (DOCS / "overall-v2-top100-uncertainty-aware.json").exists()
    assert not (GOLD / "overall-v2-top100-uncertainty-aware.parquet").exists()


def test_v1_top100_transition_is_diagnostic_only() -> None:
    rows = pq.read_table(GOLD / "v1-top100-uncertainty-transition.parquet").to_pylist()
    assert len(rows) == 100
    assert {int(row["v1_rank"]) for row in rows} == set(range(1, 101))
    assert all(row["distribution_rankable"] is True for row in rows)
