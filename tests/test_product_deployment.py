"""STEP-0020 deployment hardening without methodology mutation."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

from goatlab.product import deployment
from goatlab.product.api import create_app
from goatlab.product.loading import FROZEN_RELEASE_FINGERPRINT, FROZEN_RELEASE_ID
from goatlab.product.postgres_repository import PostgresRankingRepository
from goatlab.product.repository import RankingRepository
from goatlab.product.settings import ProductSettings

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "data/product" / FROZEN_RELEASE_ID
FROZEN_DRAW_SHA256 = "1fa326cf9a5bbece581e5e1b253ebcb5d40b30bcc2bcea3268752583e54b7f26"


class _FakeS3Client:
    def __init__(self, payload: bytes, *, missing: bool = False) -> None:
        self.payload = payload
        self.missing = missing

    def head_object(self, **kwargs: str) -> dict[str, object]:
        if self.missing:
            raise FileNotFoundError("object not found")
        return {"ContentLength": len(self.payload)}

    def get_object(self, **kwargs: str) -> dict[str, object]:
        return {"Body": io.BytesIO(self.payload)}


def test_production_settings_fail_closed() -> None:
    common = {
        "environment": "production",
        "backend_mode": "postgres",
        "allowed_cors_origins": ("https://goatlab.example",),
    }
    with pytest.raises(ValueError, match="sslmode"):
        ProductSettings(database_url="postgresql://db/goatlab", **common)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="HTTPS origins"):
        ProductSettings(
            database_url="postgresql://db/goatlab?sslmode=require",
            **{**common, "allowed_cors_origins": ("http://goatlab.example",)},  # type: ignore[arg-type]
        )
    settings = ProductSettings(
        database_url="postgresql://db/goatlab?sslmode=require",
        **common,  # type: ignore[arg-type]
    )
    assert settings.database_connect_timeout_seconds == 5
    assert settings.database_statement_timeout_ms == 10_000


def test_deterministic_release_transport_and_atomic_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source" / FROZEN_RELEASE_ID
    source.mkdir(parents=True)
    (source / "alpha.txt").write_text("frozen\n")
    (source / "nested").mkdir()
    (source / "nested/beta.bin").write_bytes(b"\x00\x01")
    monkeypatch.setattr(deployment, "read_release_bundle", lambda *args, **kwargs: object())
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    first_hash = deployment.package_release(source, first)
    second_hash = deployment.package_release(source, second)
    assert first_hash == second_hash
    assert first.read_bytes() == second.read_bytes()
    target = tmp_path / "target"
    assert (
        deployment.materialize_release(
            target,
            archive_path=first,
            archive_sha256=first_hash,
        )
        == "MATERIALIZED"
    )
    assert (target / FROZEN_RELEASE_ID / "nested/beta.bin").read_bytes() == b"\x00\x01"
    assert deployment.materialize_release(target) == "ALREADY_VERIFIED"
    with pytest.raises(ValueError, match="SHA-256"):
        deployment.materialize_release(
            tmp_path / "bad-target", archive_path=first, archive_sha256="0" * 64
        )


def test_release_transport_rejects_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar.gz"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        info = tarfile.TarInfo(f"{FROZEN_RELEASE_ID}/../escape")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with gzip.GzipFile(filename="", mode="wb", fileobj=archive_path.open("wb"), mtime=0) as target:
        target.write(raw.getvalue())
    with pytest.raises(ValueError, match="unsafe release bundle member"):
        deployment._extract_verified_archive(archive_path, tmp_path / "extract", FROZEN_RELEASE_ID)
    assert not (tmp_path / "escape").exists()


def test_private_s3_release_download_and_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source" / FROZEN_RELEASE_ID
    source.mkdir(parents=True)
    (source / "payload.txt").write_text("private-r2\n")
    monkeypatch.setattr(deployment, "read_release_bundle", lambda *args, **kwargs: object())
    archive = tmp_path / "release.tar.gz"
    archive_hash = deployment.package_release(source, archive)
    monkeypatch.setattr(
        deployment,
        "_create_s3_client",
        lambda *args: _FakeS3Client(archive.read_bytes()),
    )

    target = tmp_path / "target"
    outcome = deployment.materialize_release(
        target,
        archive_sha256=archive_hash,
        s3_endpoint_url="https://example.r2.cloudflarestorage.com",
        s3_bucket="goatlab-releases",
        s3_object_key=f"releases/{FROZEN_RELEASE_ID}.tar.gz",
        s3_access_key_id="private-access-key",
        s3_secret_access_key="private-secret-key",
    )

    assert outcome == "MATERIALIZED"
    assert (target / FROZEN_RELEASE_ID / "payload.txt").read_text() == "private-r2\n"


def test_private_s3_release_requires_complete_credentials(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="complete private S3"):
        deployment.materialize_release(
            tmp_path / "target",
            archive_sha256="0" * 64,
            s3_endpoint_url="https://example.r2.cloudflarestorage.com",
            s3_bucket="goatlab-releases",
            s3_object_key="releases/release.tar.gz",
        )


def test_private_s3_release_object_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deployment,
        "_create_s3_client",
        lambda *args: _FakeS3Client(b"", missing=True),
    )
    with pytest.raises(RuntimeError, match="private S3 release bundle download failed"):
        deployment.download_s3_bundle(
            "https://example.r2.cloudflarestorage.com",
            "goatlab-releases",
            "releases/missing.tar.gz",
            "private-access-key",
            "private-secret-key",
            tmp_path / "release.tar.gz",
        )
    assert not (tmp_path / "release.tar.gz").exists()


def test_private_s3_release_rejects_bad_transport_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deployment,
        "_create_s3_client",
        lambda *args: _FakeS3Client(b"not-the-approved-bundle"),
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        deployment.materialize_release(
            tmp_path / "target",
            archive_sha256="0" * 64,
            s3_endpoint_url="https://example.r2.cloudflarestorage.com",
            s3_bucket="goatlab-releases",
            s3_object_key="releases/release.tar.gz",
            s3_access_key_id="private-access-key",
            s3_secret_access_key="private-secret-key",
        )


def test_private_s3_failure_does_not_leak_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    access_key = "access-key-must-not-leak"
    secret_key = "secret-key-must-not-leak"

    def fail_client(*args: str) -> object:
        raise RuntimeError(f"provider rejected {access_key} {secret_key}")

    monkeypatch.setattr(deployment, "_create_s3_client", fail_client)
    with pytest.raises(RuntimeError) as error:
        deployment.download_s3_bundle(
            "https://example.r2.cloudflarestorage.com",
            "goatlab-releases",
            "releases/release.tar.gz",
            access_key,
            secret_key,
            tmp_path / "release.tar.gz",
        )
    assert access_key not in str(error.value)
    assert secret_key not in str(error.value)


def test_https_bearer_release_download_remains_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_headers: dict[str, str] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            return [b"https-bundle"]

    def fake_get(
        url: str, *, headers: dict[str, str], stream: bool, timeout: tuple[int, int]
    ) -> FakeResponse:
        captured_headers.update(headers)
        return FakeResponse()

    monkeypatch.setattr(deployment.requests, "get", fake_get)
    destination = tmp_path / "release.tar.gz"
    deployment.download_bundle(
        "https://downloads.example/release.tar.gz",
        destination,
        bearer_token="private-bearer-token",
    )

    assert destination.read_bytes() == b"https-bundle"
    assert captured_headers == {"Authorization": "Bearer private-bearer-token"}


def test_deployment_descriptors_pin_release_and_contain_no_secrets() -> None:
    descriptor = yaml.safe_load((ROOT / "render.yaml").read_text())
    service = descriptor["services"][0]
    values = {row["key"]: row.get("value") for row in service["envVars"]}
    assert values["GOATLAB_RELEASE_ID"] == FROZEN_RELEASE_ID
    assert values["GOATLAB_RELEASE_FINGERPRINT"] == FROZEN_RELEASE_FINGERPRINT
    assert next(row for row in service["envVars"] if row["key"] == "DATABASE_URL")["sync"] is False
    assert values["GOATLAB_R2_OBJECT_KEY"] == f"releases/{FROZEN_RELEASE_ID}.tar.gz"
    for key in (
        "GOATLAB_R2_ENDPOINT_URL",
        "GOATLAB_R2_BUCKET",
        "GOATLAB_R2_ACCESS_KEY_ID",
        "GOATLAB_R2_SECRET_ACCESS_KEY",
        "GOATLAB_RELEASE_BUNDLE_SHA256",
    ):
        assert next(row for row in service["envVars"] if row["key"] == key)["sync"] is False
    assert "GOATLAB_RELEASE_BUNDLE_BEARER_TOKEN" not in values
    assert "GOATLAB_RELEASE_BUNDLE_URL" not in values
    serialized = json.dumps(descriptor).lower()
    assert "password=" not in serialized and "postgresql://" not in serialized


def test_postgres_runtime_connection_preserves_provider_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = object.__new__(PostgresRankingRepository)
    repository.database_url = "postgresql://db/goatlab?options=-c%20search_path%3Drelease_schema"
    repository.settings = ProductSettings(
        environment="test",
        backend_mode="postgres",
        database_url=repository.database_url,
    )
    captured: list[str] = []

    def fake_connect(conninfo: str, **kwargs: object) -> object:
        captured.append(conninfo)
        return object()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    repository._connect()
    options = conninfo_to_dict(captured[0])["options"]
    assert "search_path=release_schema" in options
    assert "statement_timeout=10000" in options
    assert "default_transaction_read_only=on" in options


def test_api_security_headers_preserve_publication_gate() -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("run the offline STEP-0016 product build first")
    settings = ProductSettings(environment="test", product_artifact_root=RELEASE_DIR.parent)
    with TestClient(create_app(settings, repository=RankingRepository(RELEASE_DIR))) as client:
        response = client.get("/api/v1/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.json()["publication_rights_gate"] == "PUBLICATION_RIGHTS_REVIEW_REQUIRED"


def test_deployment_fingerprints_are_deterministic() -> None:
    manifest = json.loads((ROOT / "docs/data/step-0020-deployment-fingerprints.json").read_text())
    rows: list[str] = []
    for relative, expected in sorted(manifest["files"].items()):
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected
        rows.append(f"{actual}  {relative}\n")
    aggregate = hashlib.sha256("".join(rows).encode()).hexdigest()
    assert aggregate == manifest["deployment_artifact_set_sha256"]


def test_frozen_release_remains_unchanged() -> None:
    assert FROZEN_RELEASE_ID == "goatlab-ranking-release-2026-v2-probabilistic"
    assert FROZEN_RELEASE_FINGERPRINT == (
        "2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093"
    )
    if not RELEASE_DIR.exists():
        pytest.skip("run the offline STEP-0016 product build first")
    assert deployment.sha256_file(RELEASE_DIR / "paired-overall-rank-draws.npz") == (
        FROZEN_DRAW_SHA256
    )
