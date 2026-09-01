from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/data"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_committed_dimension_reports_are_complete_and_fingerprinted() -> None:
    summary = json.loads((DOCS / "dimension-candidate-summary.json").read_text())
    registry = yaml.safe_load((DOCS / "goat-dimension-candidates.yaml").read_text())
    report_paths = (
        DOCS / "goat-dimension-candidates.yaml",
        DOCS / "dimension-redundancy-audit.json",
        DOCS / "dimension-era-fairness.json",
        DOCS / "dimension-weight-sensitivity.json",
        DOCS / "dimension-coverage-audit.json",
        DOCS / "dimension-case-studies.json",
    )
    fingerprint = hashlib.sha256(
        "\n".join(f"{path.name}:{_sha256(path)}" for path in report_paths).encode()
    ).hexdigest()

    assert summary["master_players"] == 5103
    assert summary["dimensions"] == 8
    assert summary["candidate_definitions"] == 38
    assert summary["final_candidate_count"] == 0
    assert summary["no_overall_score"] is True
    assert summary["no_player_ordering_report"] is True
    assert summary["committed_report_fingerprint"] == fingerprint
    assert registry["final_candidate_count"] == 0
    assert all(candidate["status"] != "FINAL" for candidate in registry["candidates"])


def test_redundancy_and_sensitivity_reports_preserve_required_audits() -> None:
    redundancy = json.loads((DOCS / "dimension-redundancy-audit.json").read_text())
    sensitivity = json.loads((DOCS / "dimension-weight-sensitivity.json").read_text())
    fairness = json.loads((DOCS / "dimension-era-fairness.json").read_text())

    assert set(redundancy["double_counting_policy_results"]) == {
        "STRICT_OWNERSHIP",
        "SHARED_EVIDENCE_WITH_PENALTY",
        "RAW_EVIDENCE_SEPARATION",
    }
    assert redundancy["within_candidate_feature_correlations"]
    assert any(
        row["relationship"] == "CROSS_DIMENSION" for row in redundancy["pairwise_correlations"]
    )
    assert sensitivity["random_seed"] == 120012
    assert sensitivity["samples_per_candidate"] == 200
    assert all(
        row["median_player_percentile_iqr"] is not None for row in sensitivity["candidate_results"]
    )
    assert {row["era_group"] for row in fairness["records"]} >= {
        "PRE_1960",
        "1960S",
        "1970S",
        "1980S",
        "1990S",
        "2000S",
        "2010S",
        "2020S",
    }
