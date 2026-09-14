from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((DOCS / name).read_text(encoding="utf-8")))


def test_step_d_reconstruction_and_frozen_outputs() -> None:
    summary = _json("historical-evidence-bridge-summary.json")
    reconstruction = summary["step_0015d_reconstruction"]
    assert isinstance(reconstruction, dict)
    assert reconstruction["rows"] == 22457
    assert reconstruction["scored_rows"] == 16576
    assert reconstruction["mismatches"] == 0
    assert reconstruction["maximum_numerical_difference"] == 0.0
    assert reconstruction["peak_counterfactual_maximum_difference"] == 0.0
    assert reconstruction["longevity_counterfactual_maximum_difference"] == 0.0
    assert summary["frozen_v1_unchanged"] is True
    assert summary["candidate_d_unchanged"] is True
    assert summary["production_promoted"] is False


def test_sparse_point_bridges_fail_predeclared_gates() -> None:
    report = _json("historical-mask-validation.json")
    regimes = report["regimes"]
    assert isinstance(regimes, dict)
    assert set(regimes) == {
        "EXPANDED_BOX_NO_PRESENCE",
        "TRADITIONAL_BOX",
        "EARLY_WITH_PRESENCE",
        "EARLY_MINIMAL",
    }
    for result in regimes.values():
        assert isinstance(result, dict)
        gates = result["practical_gates"]
        assert isinstance(gates, dict)
        assert gates["passes"] is False
        assert result["point_score_status"] == "REJECTED"


def test_unknown_quality_is_interval_or_unavailable_never_zero() -> None:
    summary = _json("historical-evidence-bridge-summary.json")
    statuses = summary["bridge_counterfactual_status_counts"]
    assert statuses == {
        "INTERVAL_ONLY": 5098,
        "OBSERVED_RESEARCH_SCORE": 16576,
        "UNAVAILABLE": 783,
    }
    assert summary["bridge_verdict"] == "NO_VALID_BRIDGE"
    assert summary["recommendation"] == "REQUIRES_MORE_MEASUREMENT_WORK"


def test_uncertainty_intervals_preserve_nominal_ordering() -> None:
    report = _json("bridge-uncertainty-calibration.json")
    for regime in (
        "EXPANDED_BOX_NO_PRESENCE",
        "TRADITIONAL_BOX",
        "EARLY_WITH_PRESENCE",
        "EARLY_MINIMAL",
    ):
        intervals = report[regime]
        assert intervals["0.8"]["mean_width_points"] < intervals["0.9"]["mean_width_points"]
        assert intervals["0.9"]["mean_width_points"] < intervals["0.95"]["mean_width_points"]


def test_bridge_reports_are_offline_and_fingerprinted() -> None:
    summary = _json("historical-evidence-bridge-summary.json")
    assert summary["network_requests"] == 0
    fingerprint = summary["output_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    reports = summary["report_hashes"]
    assert isinstance(reports, dict) and len(reports) >= 15
    assert all((DOCS / name).exists() for name in reports)
