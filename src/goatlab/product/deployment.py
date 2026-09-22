"""Immutable release packaging and deployment materialization helpers."""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
import requests

from goatlab.product.loading import (
    FROZEN_RELEASE_FINGERPRINT,
    FROZEN_RELEASE_ID,
    read_release_bundle,
)

MAX_BUNDLE_BYTES = 256 * 1024 * 1024


class _S3Body(Protocol):
    def read(self, amount: int = -1) -> bytes: ...

    def close(self) -> None: ...


class _S3Client(Protocol):
    def head_object(self, **kwargs: str) -> Mapping[str, object]: ...

    def get_object(self, **kwargs: str) -> Mapping[str, object]: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_release(source_dir: Path, output_path: Path) -> str:
    """Create a deterministic gzip-compressed tar containing one immutable release."""

    read_release_bundle(source_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        output_path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        paths = [source_dir, *sorted(source_dir.rglob("*"))]
        for path in paths:
            if path.is_symlink():
                raise ValueError("release bundles may not contain symbolic links")
            relative = Path(source_dir.name) / path.relative_to(source_dir)
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if info.isfile():
                with path.open("rb") as source:
                    archive.addfile(info, source)
            else:
                archive.addfile(info)
    return sha256_file(output_path)


def download_bundle(
    url: str,
    destination: Path,
    *,
    bearer_token: str | None = None,
    max_bytes: int = MAX_BUNDLE_BYTES,
) -> None:
    if not url.startswith("https://"):
        raise ValueError("release bundle URL must use HTTPS")
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    total = 0
    with requests.get(url, headers=headers, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        with destination.open("wb") as target:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("release bundle exceeds configured size limit")
                target.write(chunk)


def _create_s3_client(
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
) -> _S3Client:
    return cast(
        _S3Client,
        boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        ),
    )


def download_s3_bundle(
    endpoint_url: str,
    bucket: str,
    object_key: str,
    access_key_id: str,
    secret_access_key: str,
    destination: Path,
    *,
    max_bytes: int = MAX_BUNDLE_BYTES,
) -> None:
    """Download a private S3-compatible object without exposing credentials."""

    if not endpoint_url.startswith("https://"):
        raise ValueError("private S3 endpoint must use HTTPS")
    if not all(value.strip() for value in (bucket, object_key, access_key_id, secret_access_key)):
        raise ValueError("complete private S3 bundle configuration is required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        client = _create_s3_client(endpoint_url, access_key_id, secret_access_key)
        metadata = client.head_object(Bucket=bucket, Key=object_key)
        content_length = metadata.get("ContentLength")
        if isinstance(content_length, int) and content_length > max_bytes:
            raise ValueError("release bundle exceeds configured size limit")
        response = client.get_object(Bucket=bucket, Key=object_key)
        body = cast(_S3Body, response["Body"])
        total = 0
        try:
            with destination.open("wb") as target:
                while chunk := body.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("release bundle exceeds configured size limit")
                    target.write(chunk)
        finally:
            body.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise RuntimeError("private S3 release bundle download failed") from None


def _safe_member_path(member: tarfile.TarInfo, release_id: str) -> PurePosixPath:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != release_id:
        raise ValueError(f"unsafe release bundle member: {member.name}")
    if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
        raise ValueError(f"unsupported release bundle member: {member.name}")
    return path


def _extract_verified_archive(archive_path: Path, target_root: Path, release_id: str) -> Path:
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            relative = _safe_member_path(member, release_id)
            destination = target_root.joinpath(*relative.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"unable to read bundle member: {member.name}")
            with source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            os.chmod(destination, member.mode & 0o777)
    return target_root / release_id


def materialize_release(
    artifact_root: Path,
    *,
    release_id: str = FROZEN_RELEASE_ID,
    expected_release_fingerprint: str = FROZEN_RELEASE_FINGERPRINT,
    archive_path: Path | None = None,
    archive_sha256: str | None = None,
    bundle_url: str | None = None,
    bearer_token: str | None = None,
    s3_endpoint_url: str | None = None,
    s3_bucket: str | None = None,
    s3_object_key: str | None = None,
    s3_access_key_id: str | None = None,
    s3_secret_access_key: str | None = None,
) -> str:
    """Verify an existing release or atomically install a hash-pinned archive."""

    release_dir = artifact_root / release_id
    if release_dir.exists():
        read_release_bundle(
            release_dir,
            expected_release_id=release_id,
            expected_fingerprint=expected_release_fingerprint,
        )
        return "ALREADY_VERIFIED"
    if not archive_sha256 or len(archive_sha256) != 64:
        raise ValueError("a SHA-256-pinned release bundle is required")
    artifact_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="goatlab-release-", dir=artifact_root) as temp_name:
        temp_root = Path(temp_name)
        selected = archive_path
        if selected is None:
            selected = temp_root / "release.tar.gz"
            s3_configuration = (
                s3_endpoint_url,
                s3_bucket,
                s3_object_key,
                s3_access_key_id,
                s3_secret_access_key,
            )
            if any(s3_configuration):
                if not all(s3_configuration):
                    raise ValueError("complete private S3 bundle configuration is required")
                download_s3_bundle(
                    cast(str, s3_endpoint_url),
                    cast(str, s3_bucket),
                    cast(str, s3_object_key),
                    cast(str, s3_access_key_id),
                    cast(str, s3_secret_access_key),
                    selected,
                )
            elif bundle_url:
                download_bundle(bundle_url, selected, bearer_token=bearer_token)
            else:
                raise ValueError("release bundle path, private S3 object, or HTTPS URL is required")
        if sha256_file(selected) != archive_sha256:
            raise ValueError("release bundle SHA-256 mismatch")
        staged = _extract_verified_archive(selected, temp_root / "extracted", release_id)
        read_release_bundle(
            staged,
            expected_release_id=release_id,
            expected_fingerprint=expected_release_fingerprint,
        )
        if release_dir.exists():
            raise FileExistsError("release destination appeared during materialization")
        os.replace(staged, release_dir)
    return "MATERIALIZED"
