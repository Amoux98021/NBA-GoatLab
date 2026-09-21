"""Immutable release packaging and deployment materialization helpers."""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

import requests

from goatlab.product.loading import (
    FROZEN_RELEASE_FINGERPRINT,
    FROZEN_RELEASE_ID,
    read_release_bundle,
)

MAX_BUNDLE_BYTES = 256 * 1024 * 1024


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
            if not bundle_url:
                raise ValueError("release bundle path or HTTPS URL is required")
            selected = temp_root / "release.tar.gz"
            download_bundle(bundle_url, selected, bearer_token=bearer_token)
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
