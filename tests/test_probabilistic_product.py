"""STEP-0016 product contract, immutable release, and offline integration checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from goatlab.product.build import (
    RELEASE_ID,
    canonical_json,
    immutable_write,
    paired_draw_bytes,
    sha256,
)
from goatlab.product.models import (
    DimensionProfile,
    LeaderboardEntry,
    PlayerIdentity,
    RankDistributionSummary,
    TopNProbabilities,
)
from goatlab.product.repository import RankingRepository, normalized_search_name
from pipelines.product.build_probabilistic_leaderboard import _exact_reconstruction

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "data/product" / RELEASE_ID


def test_search_name_does_not_change_canonical_identity() -> None:
    assert normalized_search_name("José O'Neal, Jr.") == "jose o neal jr"


def test_topn_monotonicity_is_required() -> None:
    with pytest.raises(ValueError, match="nondecreasing"):
        TopNProbabilities(top_1=0.1, top_5=0.2, top_10=0.4, top_25=0.3, top_50=0.5, top_100=0.8)


def test_nested_rank_bands_are_required() -> None:
    with pytest.raises(ValueError, match="nested"):
        RankDistributionSummary(
            median_rank=10,
            mean_rank=11,
            lower_50=9,
            upper_50=11,
            lower_80=8,
            upper_80=12,
            lower_90=7,
            upper_90=13,
            lower_95=8,
            upper_95=14,
        )


def test_active_identity_cannot_claim_a_completed_career() -> None:
    with pytest.raises(ValueError, match="career end"):
        PlayerIdentity(
            player_id="p",
            player_name="Player",
            search_name="player",
            career_state="ACTIVE",
            career_start_season=2023,
            career_end_season=2025,
            latest_season_used=2025,
            ranking_status="OFFICIAL",
            ranking_eligible=True,
        )


def test_interval_dimension_cannot_become_point_or_zero() -> None:
    with pytest.raises(ValueError, match="official point"):
        DimensionProfile(
            dimension="DEFENSE",
            status="DEFENSE_INTERVAL_ONLY",
            point_value=0,
            diagnostic_center=80,
            lower_90=70,
            upper_90=90,
            methodology_version="frozen",
        )


def test_immutable_write_rejects_changed_release(tmp_path: Path) -> None:
    path = tmp_path / "release.json"
    assert immutable_write(path, b"frozen")
    assert not immutable_write(path, b"frozen")
    with pytest.raises(ValueError, match="immutable"):
        immutable_write(path, b"changed")


def test_canonical_json_rejects_nonfinite_values() -> None:
    with pytest.raises(ValueError):
        canonical_json({"score": float("nan")})


def test_paired_distribution_bytes_are_deterministic() -> None:
    import numpy as np

    overall = np.full((2, 2500), 75.0)
    ranks = np.vstack((np.ones(2500), np.full(2500, 2)))
    one = paired_draw_bytes(["a", "b"], overall, ranks)
    two = paired_draw_bytes(["a", "b"], overall, ranks)
    assert sha256(one) == sha256(two)


def test_frozen_sparse_rows_reconstruct_with_explicit_nulls_only() -> None:
    assert _exact_reconstruction(
        [{"player_id": "p", "score": 80.0}],
        [{"player_id": "p", "score": 80.0, "missing_field": None}],
    ) == {"players": 1, "field_mismatches": 0, "maximum_numeric_difference": 0.0}
    with pytest.raises(ValueError, match="exact reconstruction failed"):
        _exact_reconstruction(
            [{"player_id": "p", "score": 79.0}],
            [{"player_id": "p", "score": 80.0}],
        )


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="run offline STEP-0016 build for integration")
def test_release_artifacts_and_api_models() -> None:
    repository = RankingRepository(RELEASE_DIR)
    release = repository.get_release()
    assert (release.player_count, release.rankable_count, release.unavailable_count) == (
        5103,
        1882,
        3221,
    )
    leaderboard = repository.get_leaderboard(limit=1882)
    assert len(leaderboard) == len({row.player_id for row in leaderboard}) == 1882
    assert [row.display_position for row in leaderboard] == list(range(1, 1883))
    assert all(isinstance(row, LeaderboardEntry) for row in leaderboard)
    assert all(
        row.top_n.top_1
        <= row.top_n.top_5
        <= row.top_n.top_10
        <= row.top_n.top_25
        <= row.top_n.top_50
        <= row.top_n.top_100
        for row in leaderboard
    )
    top100 = json.loads((RELEASE_DIR / "leaderboard-v2-probabilistic.json").read_text())
    assert len(top100) == 100
    assert [row["player_id"] for row in top100] == [row.player_id for row in leaderboard[:100]]
    assert all(row.ranking_status.value != "UNAVAILABLE" for row in leaderboard)
    assert any(row.ranking_status.value == "INTERVAL_NATIVE" for row in leaderboard)
    assert repository.get_player(leaderboard[0].player_id) is not None
    assert repository.get_player("not-a-player") is None
    assert repository.get_methodology()["overall_exact_point_promoted"] is False


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="run offline STEP-0016 build for integration")
def test_pairwise_complementarity_and_unavailable_exclusion() -> None:
    repository = RankingRepository(RELEASE_DIR)
    first, second = repository.get_leaderboard(limit=2)
    forward = repository.compare_players(first.player_id, second.player_id)
    reverse = repository.compare_players(second.player_id, first.player_id)
    assert forward.probability_a_above_b + forward.probability_b_above_a == pytest.approx(1)
    assert forward.probability_a_above_b == pytest.approx(reverse.probability_b_above_a)
    assert len(forward.dimensions) == 7
    with pytest.raises(ValueError, match="himself"):
        repository.compare_players(first.player_id, first.player_id)
    unranked = json.loads((RELEASE_DIR / "unranked.jsonl").read_text().splitlines()[0])
    with pytest.raises(LookupError, match="distribution-rankable"):
        repository.compare_players(first.player_id, unranked["player_id"])


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="run offline STEP-0016 build for integration")
def test_db_artifact_schema_and_profile_completeness() -> None:
    import pyarrow.parquet as pq

    expected = {
        "players": 5103,
        "ranking_versions": 1,
        "player_rankings": 1882,
        "player_rank_probabilities": 1882,
        "player_dimensions": 5103 * 7,
    }
    for name, count in expected.items():
        table = pq.read_table(RELEASE_DIR / "db" / f"{name}.parquet")
        assert table.num_rows == count
        assert "release_id" in table.schema.names
    profiles = (RELEASE_DIR / "player-profiles.jsonl").read_text().splitlines()
    assert len(profiles) == 5103
    assert all(len(json.loads(row)["dimensions"]) == 7 for row in profiles)
    assert sum(json.loads(row)["leaderboard"] is None for row in profiles) == 3221


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="run offline STEP-0016 build for integration")
def test_release_fingerprints_and_frozen_sources() -> None:
    manifest = json.loads((RELEASE_DIR / "ranking-release-manifest.json").read_text())
    fingerprint = manifest.pop("release_fingerprint")
    assert sha256(canonical_json(manifest)) == fingerprint
    record = json.loads((ROOT / "docs/product/step-0016-release-record.json").read_text())
    assert record["release_fingerprint"] == fingerprint
    assert (
        record["artifact_sha256"]["leaderboard"] == manifest["artifact_sha256"]["leaderboard.json"]
    )
    assert (
        record["artifact_sha256"]["top100"]
        == manifest["artifact_sha256"]["leaderboard-v2-probabilistic.json"]
    )
    frozen = json.loads((ROOT / "docs/data/step-0015p-governance-summary.json").read_text())
    assert (
        manifest["upstream_sha256"]["step_0015p_governance_fingerprint"]
        == frozen["governance_fingerprint"]
    )
    assert (
        manifest["upstream_sha256"]["step_0015o_fingerprint"]
        == frozen["upstream_fingerprints"]["step_0015o"]
    )
    for relative, expected in manifest["artifact_sha256"].items():
        assert sha256((RELEASE_DIR / relative).read_bytes()) == expected
    summary = json.loads((RELEASE_DIR / "product-build-summary.json").read_text())
    assert summary["upstream_reconstruction"]["step_0015n_mismatches"] == 0
    assert summary["upstream_reconstruction"]["step_0015o_mismatches"] == 0
