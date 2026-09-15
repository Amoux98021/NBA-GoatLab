from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"
GOLD = ROOT / "data/gold/overall_uncertainty_architecture_audit"


def load_json(name: str) -> dict[str, object]:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_upstream_reconstruction_is_exact() -> None:
    report = load_json("overall-uncertainty-reconstruction.json")
    assert report["maximum_numerical_difference"] == 0.0
    assert report["peak_status_mismatches"] == 0
    assert report["longevity_status_mismatches"] == 0


def test_joint_dependence_is_preserved_and_material() -> None:
    report = load_json("overall-joint-dependence.json")
    for values in report["patterns"].values():
        assert values["mean_within_draw_correlation"] > 0.0
        assert values["mean_covariance_contribution"] > 0.0
        assert values["joint_mean_width"]["90"] > values["independent_mean_width"]["90"]
        assert abs(values["maximum_analytic_empirical_variance_difference"]) < 1e-10


def test_statuses_and_interval_semantics_are_enforced() -> None:
    report = load_json("overall-status-summary.json")
    assert report["scopes"]["ALL_PLAYERS"]["status_counts"] == {
        "OFFICIAL_OVERALL_POINT": 602,
        "OVERALL_UNAVAILABLE": 3221,
        "PROVISIONAL_OVERALL_POINT": 1280,
    }
    table = pq.read_table(GOLD / "overall-uncertainty-research.parquet").to_pydict()
    for index, status in enumerate(table["overall_status"]):
        assert table["weight_renormalized"][index] is False
        assert table["interval_midpoint_used_as_exact"][index] is False
        assert table["confidence_penalty_applied"][index] is False
        assert table["defense_caveat"][index] == "DEFENSE_V1_FROZEN_PENDING_REVISION"
        if status in {"OVERALL_INTERVAL_ONLY", "OVERALL_UNAVAILABLE"}:
            assert table["overall_point"][index] is None
        else:
            assert table["overall_point"][index] is not None
        center = table["overall_diagnostic_center"][index]
        if center is not None:
            assert (
                table["overall_lower_95"][index]
                <= table["overall_lower_90"][index]
                <= table["overall_lower_80"][index]
                <= center
                <= table["overall_upper_80"][index]
                <= table["overall_upper_90"][index]
                <= table["overall_upper_95"][index]
            )


def test_no_top_100_is_published_or_reordered() -> None:
    report = load_json("overall-uncertainty-verdict.json")
    assert report["new_top100_published"] is False
    assert report["overall_v2_promoted"] is False
    transition = pq.read_table(GOLD / "v1-top100-eligibility-transition.parquet").to_pydict()
    assert len(transition["player_id"]) == 100
    assert {int(value) for value in transition["v1_overall_rank"]} == set(range(1, 101))
    assert set(transition["reordered"]) == {False}
    assert load_json("v1-top100-eligibility-transition.json")["v1_order_preserved"] is True


def test_validation_gates_and_forbidden_baselines_are_recorded() -> None:
    status = load_json("overall-status-summary.json")
    assert status["point_eligible_patterns"] == {
        "EARLY_TRADITIONAL_TO_EXPANDED": True,
        "FULL_REFERENCE": True,
        "MIXED_PROVISIONAL_INTERVAL": True,
        "NO_PRESENCE_CAREER": True,
        "PARTIAL_PRESENCE_LATE": True,
        "TRADITIONAL_CAREER": False,
    }
    prohibited = load_json("overall-prohibited-baselines.json")
    assert prohibited["all_methods_prohibited"] is True


def test_step_fingerprint_is_deterministic() -> None:
    report = load_json("overall-uncertainty-summary.json")
    assert report["deterministic_rebuild_verified"] is True
    assert report["output_fingerprint"] == (
        "cb740fc68a77df3cb30b68e854e413c670394638ff2bf7b47401b905c7a81580"
    )
