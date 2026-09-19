"""STEP-0017 release loading, repository equivalence, and read-only API tests."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from goatlab.product.api import create_app
from goatlab.product.draw_store import PairedDrawStore
from goatlab.product.loading import (
    FROZEN_RELEASE_FINGERPRINT,
    FROZEN_RELEASE_ID,
    ReleaseBundle,
    load_ranking_release,
    read_release_bundle,
)
from goatlab.product.migrations import DEFAULT_MIGRATIONS, apply_migrations
from goatlab.product.postgres_repository import PostgresRankingRepository
from goatlab.product.repository import RankingRepository
from goatlab.product.settings import ProductSettings

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "data/product" / FROZEN_RELEASE_ID


@pytest.fixture(scope="module")
def release_bundle() -> ReleaseBundle:
    if not RELEASE_DIR.exists():
        pytest.skip("run the offline STEP-0016 product build first")
    return read_release_bundle(RELEASE_DIR)


@pytest.fixture
def postgres_url() -> str:
    base_url = os.getenv("GOATLAB_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("set GOATLAB_TEST_DATABASE_URL to an isolated local PostgreSQL database")
    schema = f"goatlab_step17_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(base_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(base_url, options=f"-c search_path={schema}")
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _database_settings(url: str) -> ProductSettings:
    return ProductSettings(
        environment="test",
        backend_mode="postgres",
        database_url=url,
        product_artifact_root=RELEASE_DIR.parent,
    )


def test_settings_require_database_and_safe_cors() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        ProductSettings(backend_mode="postgres")
    with pytest.raises(ValueError, match="wildcard CORS"):
        ProductSettings(environment="production", allowed_cors_origins=("*",))


def test_frozen_bundle_and_draw_store(release_bundle: ReleaseBundle) -> None:
    assert release_bundle.manifest.release_fingerprint == FROZEN_RELEASE_FINGERPRINT
    assert len(release_bundle.profiles) == 5103
    store = PairedDrawStore(
        RELEASE_DIR,
        expected_release_id=FROZEN_RELEASE_ID,
        expected_release_fingerprint=FROZEN_RELEASE_FINGERPRINT,
    )
    assert store.state == "VERIFIED_NOT_LOADED"
    entries = RankingRepository(RELEASE_DIR).get_leaderboard(limit=2)
    a, b = entries[0].player_id, entries[1].player_id
    forward = store.pair_probability(a, b)
    reverse = store.pair_probability(b, a)
    assert store.state == "LOADED"
    assert forward[0] == pytest.approx(reverse[1])
    assert forward[0] + forward[1] == pytest.approx(1)
    assert forward == store.pair_probability(a, b)
    with pytest.raises(ValueError, match="fingerprint"):
        PairedDrawStore(
            RELEASE_DIR,
            expected_release_id=FROZEN_RELEASE_ID,
            expected_release_fingerprint="0" * 64,
        )


def test_release_artifact_corruption_blocks_loading(tmp_path: Path) -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("run the offline STEP-0016 product build first")
    (tmp_path / "ranking-release-manifest.json").write_bytes(
        (RELEASE_DIR / "ranking-release-manifest.json").read_bytes()
    )
    corrupted = tmp_path / "db/player_dimensions.parquet"
    corrupted.parent.mkdir()
    corrupted.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        read_release_bundle(tmp_path)


def test_draw_change_after_startup_is_rejected(tmp_path: Path) -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("run the offline STEP-0016 product build first")
    for name in ("ranking-release-manifest.json", "paired-overall-rank-draws.npz"):
        shutil.copy2(RELEASE_DIR / name, tmp_path / name)
    store = PairedDrawStore(
        tmp_path,
        expected_release_id=FROZEN_RELEASE_ID,
        expected_release_fingerprint=FROZEN_RELEASE_FINGERPRINT,
    )
    (tmp_path / "paired-overall-rank-draws.npz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed after startup"):
        store.pair_probability("first", "second")


def test_artifact_api_and_openapi(release_bundle: ReleaseBundle) -> None:
    settings = ProductSettings(environment="test", product_artifact_root=RELEASE_DIR.parent)
    app = create_app(settings)
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["draw_artifact_state"] == "VERIFIED_NOT_LOADED"
        assert health.json()["publication_rights_gate"] == "PUBLICATION_RIGHTS_REVIEW_REQUIRED"
        release = client.get(f"/api/v1/releases/{FROZEN_RELEASE_ID}")
        assert release.json()["release_fingerprint"] == FROZEN_RELEASE_FINGERPRINT
        assert len(client.get("/api/v1/releases").json()["releases"]) == 1
        assert client.get("/api/v1/releases/unknown").status_code == 404
        page = client.get("/api/v1/leaderboard", params={"limit": 3, "offset": 2}).json()
        assert page["total"] == 1882 and len(page["entries"]) == 3
        assert [r["display_position"] for r in page["entries"]] == [3, 4, 5]
        assert client.get("/api/v1/leaderboard", params={"release": "unknown"}).status_code == 404
        assert (
            client.get("/api/v1/leaderboard", params={"search": "  leBRON   james"}).json()["total"]
            == 1
        )
        assert client.get("/api/v1/leaderboard", params={"status": "OFFICIAL"}).json()["total"] > 0
        assert client.get("/api/v1/leaderboard", params={"active": True}).json()["total"] > 0
        top100 = client.get("/api/v1/top100").json()["entries"]
        assert top100 == release_bundle.top100
        first, second = page["entries"][:2]
        assert client.get(f"/api/v1/players/{first['player_id']}").status_code == 200
        comparison = client.get(
            f"/api/v1/compare/{first['player_id']}/{second['player_id']}"
        ).json()
        assert comparison["probability_a_above_b"] + comparison[
            "probability_b_above_a"
        ] == pytest.approx(1)
        assert (
            client.get(f"/api/v1/compare/{first['player_id']}/{first['player_id']}").status_code
            == 400
        )
        assert client.get("/api/v1/players/not-an-id").status_code == 404
        unavailable = next(row for row in release_bundle.profiles if row["leaderboard"] is None)
        missing_id = unavailable["identity"]["player_id"]
        assert client.get(f"/api/v1/players/{missing_id}").json()["leaderboard"] is None
        error = client.get(f"/api/v1/compare/{first['player_id']}/{missing_id}")
        assert error.status_code == 422
        assert error.json()["detail"]["code"] == "COMPARISON_UNAVAILABLE"
        assert client.get(f"/api/v1/compare/{first['player_id']}/not-an-id").status_code == 404
        methodology = client.get("/api/v1/methodology").json()
        assert methodology["exact_overall_point_promoted"] is False
        assert methodology["publication_rights_gate"] == "PUBLICATION_RIGHTS_REVIEW_REQUIRED"
        cors = client.options(
            "/api/v1/leaderboard",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert cors.headers["access-control-allow-origin"] == "http://localhost:3000"
        blocked_origin = client.options(
            "/api/v1/leaderboard",
            headers={
                "Origin": "https://unapproved.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in blocked_origin.headers
        openapi = client.get("/openapi.json").json()
        expected_paths = {
            "/api/v1/health",
            "/api/v1/releases",
            "/api/v1/leaderboard",
            "/api/v1/top100",
            "/api/v1/players/{player_id}",
            "/api/v1/compare/{player_a}/{player_b}",
            "/api/v1/methodology",
        }
        assert expected_paths <= set(openapi["paths"])
        assert all("post" not in operations for operations in openapi["paths"].values())


def test_health_readiness_degrades_without_rewriting_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("run the offline STEP-0016 product build first")
    repository = RankingRepository(RELEASE_DIR)
    monkeypatch.setattr(
        repository,
        "health",
        lambda: {
            "database_accessible": False,
            "configured_release_present": False,
            "draw_artifact_state": "VERIFIED_NOT_LOADED",
        },
    )
    settings = ProductSettings(environment="test", product_artifact_root=RELEASE_DIR.parent)
    with TestClient(create_app(settings, repository=repository)) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        assert response.json()["status"] == "DEGRADED"


def test_migration_rollback_and_immutable_load(
    release_bundle: ReleaseBundle, postgres_url: str, tmp_path: Path
) -> None:
    assert apply_migrations(postgres_url) == ["0001_probabilistic_ranking_release.sql"]
    assert apply_migrations(postgres_url) == []
    with pytest.raises(LookupError, match="not present"):
        PostgresRankingRepository(_database_settings(postgres_url))
    with pytest.raises(RuntimeError, match="intentional transactional"):
        load_ranking_release(postgres_url, release_bundle, fail_after_table="player_dimensions")
    with psycopg.connect(postgres_url) as connection:
        assert connection.execute("SELECT count(*) FROM ranking_versions").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM players").fetchone()[0] == 0
    first = load_ranking_release(postgres_url, release_bundle)
    assert first["outcome"] == "LOADED"
    assert first["counts"] == {
        "players": 5103,
        "player_rankings": 1882,
        "player_rank_probabilities": 1882,
        "player_dimensions": 35721,
        "player_profiles": 5103,
        "top100_entries": 100,
        "unavailable": 3221,
    }
    assert load_ranking_release(postgres_url, release_bundle)["outcome"] == "ALREADY_LOADED"
    altered = replace(
        release_bundle,
        manifest=release_bundle.manifest.model_copy(update={"release_fingerprint": "0" * 64}),
    )
    with pytest.raises(ValueError, match="different fingerprint"):
        load_ranking_release(postgres_url, altered)
    with psycopg.connect(postgres_url) as connection:
        with pytest.raises(psycopg.Error, match="immutable"):
            connection.execute(
                "UPDATE ranking_versions SET cutoff_season = 'changed' WHERE release_id = %s",
                (FROZEN_RELEASE_ID,),
            )
        connection.rollback()
    migration_copy = tmp_path / "migrations"
    migration_copy.mkdir()
    original = DEFAULT_MIGRATIONS / "0001_probabilistic_ranking_release.sql"
    copied = migration_copy / original.name
    shutil.copy2(original, copied)
    copied.write_text(copied.read_text() + "\n-- altered historical migration\n")
    with pytest.raises(ValueError, match="migration changed"):
        apply_migrations(postgres_url, migration_copy)


def test_postgres_artifact_equivalence_and_api(
    release_bundle: ReleaseBundle, postgres_url: str
) -> None:
    apply_migrations(postgres_url)
    load_ranking_release(postgres_url, release_bundle)
    artifact = RankingRepository(RELEASE_DIR)
    database = PostgresRankingRepository(_database_settings(postgres_url))
    assert database.get_release() == artifact.get_release()
    assert database.get_methodology() == artifact.get_methodology()
    assert database.get_top100() == artifact.get_top100()
    assert [row.model_dump(mode="json") for row in database.get_leaderboard()] == [
        row.model_dump(mode="json") for row in artifact.get_leaderboard()
    ]
    unavailable = next(row for row in release_bundle.profiles if row["leaderboard"] is None)
    sample_ids = [unavailable["identity"]["player_id"]]
    for name in (
        "George Mikan",
        "Michael Jordan",
        "LeBron James",
        "Stephen Curry",
        "Kobe Bryant",
        "Rudy Gobert",
    ):
        matches = artifact.get_leaderboard(limit=1882, search=name)
        assert len(matches) == 1
        sample_ids.append(matches[0].player_id)
    for player_id in sample_ids:
        assert database.get_player(player_id) == artifact.get_player(player_id)
    first, second = artifact.get_leaderboard(limit=2)
    assert database.compare_players(first.player_id, second.player_id) == artifact.compare_players(
        first.player_id, second.player_id
    )
    assert database.compare_players(second.player_id, first.player_id) == artifact.compare_players(
        second.player_id, first.player_id
    )
    assert database.count_leaderboard(search="lebron james") == 1
    assert database.get_leaderboard(search="lebron james")[0].player_name == "LeBron James"
    settings = _database_settings(postgres_url)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").json()["database_accessible"] is True
        assert client.get("/api/v1/leaderboard").json()["total"] == 1882
        assert client.get("/api/v1/top100").json()["entries"] == release_bundle.top100
        assert (
            client.get("/api/v1/leaderboard", params={"status": "INTERVAL_NATIVE"}).json()["total"]
            > 0
        )
        assert client.get(f"/api/v1/players/{sample_ids[0]}").json()["leaderboard"] is None
        assert (
            client.get(f"/api/v1/compare/{first.player_id}/{second.player_id}").status_code == 200
        )


def test_release_manifest_is_not_modified(release_bundle: ReleaseBundle) -> None:
    assert release_bundle.manifest.artifact_sha256["leaderboard.json"] == (
        "792e399d900df959dc8c21d08227faa1c9bf780957bd79a963f17c6ba728ca4d"
    )
    record = json.loads((ROOT / "docs/product/step-0016-release-record.json").read_text())
    assert record["release_fingerprint"] == release_bundle.manifest.release_fingerprint
