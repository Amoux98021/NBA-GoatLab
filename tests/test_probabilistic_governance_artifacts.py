from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from goatlab.rankings.publication_policy import (
    FROZEN_CUTOFF,
    LEAN_ORDER_MINIMUM,
    POLICY_VERSION,
    PROBABILITY_LEVELS,
    PRODUCT_CONTRACT_VERSION,
    RANK_BAND_LEVELS,
    STRONG_ORDER_MINIMUM,
    RankingStatus,
)

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "docs/data/step-0015p-governance-summary.json"


def test_upstream_artifacts_are_bitwise_frozen() -> None:
    summary = json.loads(SUMMARY.read_text())
    for name, expected in summary["frozen_file_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert (
        json.loads((ROOT / "docs/data/overall-ranking-summary.json").read_text())[
            "output_fingerprint"
        ]
        == summary["upstream_fingerprints"]["overall_v1"]
    )
    for step, source in (
        ("step_0015m", "defense-v2-tiered-promotion-summary.json"),
        ("step_0015n", "overall-v2-promotion-summary.json"),
        ("step_0015o", "interval-native-ranking-policy-summary.json"),
    ):
        assert (
            json.loads((ROOT / "docs/data" / source).read_text())["output_fingerprint"]
            == summary["upstream_fingerprints"][step]
        )


def test_governance_fingerprint_reproduces_offline() -> None:
    summary = json.loads(SUMMARY.read_text())
    for name, expected in summary["governance_file_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    fingerprint = summary.pop("governance_fingerprint")
    assert fingerprint == "9511a3c85fe429da80cdf485715d8168c75046373ea6504ece50478943ca802d"
    assert (
        hashlib.sha256(
            json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == fingerprint
    )


def test_registry_freezes_policy_without_promoting_overall_point_method() -> None:
    registry = yaml.safe_load(
        (ROOT / "docs/data/goatlab-v1-ranking-policy-v2-probabilistic.yaml").read_text()
    )
    assert registry["policy_version"] == POLICY_VERSION
    assert registry["overall_substrate"]["status"] == (
        "research_probabilistic_substrate_not_exact_point_promoted"
    )
    assert registry["topn_probabilities"] == list(PROBABILITY_LEVELS)
    assert registry["rank_bands"] == list(RANK_BAND_LEVELS)
    assert registry["pairwise_ordering"]["strong_min"] == STRONG_ORDER_MINIMUM
    assert registry["pairwise_ordering"]["lean_min"] == LEAN_ORDER_MINIMUM
    assert registry["limits"]["cutoff_season"] == FROZEN_CUTOFF
    assert set(registry["evidence_statuses"]) == {status.value for status in RankingStatus}
    assert registry["forbidden"]["overall_v2_exact_point_promotion"] is True
    assert registry["navigation"]["generated_in_step_0015p"] is False
    assert (
        PRODUCT_CONTRACT_VERSION
        in (ROOT / "docs/data/probabilistic-ranking-product-contract.md").read_text()
    )


def test_no_successor_top100_is_published_in_governance_step() -> None:
    summary = json.loads(SUMMARY.read_text())
    assert summary["step_status"] == "PASS"
    assert summary["governance_verdict"] == "FREEZE_PROBABILISTIC_FIRST_POLICY"
    assert summary["overall_exact_point_promoted"] is False
    assert summary["top100_generated"] is False
    assert summary["step_0015_closed"] is True
    assert not (ROOT / "docs/data/overall-v2-top100-uncertainty-aware.json").exists()
    audit_gold = ROOT / "data/gold/interval_native_ranking_policy_audit"
    assert not (audit_gold / "overall-v2-top100-uncertainty-aware.parquet").exists()
    assert (
        json.loads((ROOT / "docs/data/overall-v2-promotion-summary.json").read_text())[
            "promotion_verdict"
        ]
        == "DO_NOT_PROMOTE_OVERALL_V2"
    )
