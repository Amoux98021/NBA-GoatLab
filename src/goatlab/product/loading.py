"""Verified, transactional import of an immutable STEP-0016 product release."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from goatlab.product.build import canonical_json
from goatlab.product.models import PlayerProfile, RankingRelease

LOGGER = logging.getLogger(__name__)
FROZEN_RELEASE_ID = "goatlab-ranking-release-2026-v2-probabilistic"
FROZEN_RELEASE_FINGERPRINT = "2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093"
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "players": (
        "release_id",
        "player_id",
        "player_name",
        "search_name",
        "career_state",
        "career_start_season",
        "career_end_season",
        "latest_season_used",
    ),
    "player_rankings": (
        "release_id",
        "player_id",
        "display_position",
        "ranking_status",
        "overall_source_status",
        "overall_center",
        "overall_json",
        "rank_json",
        "distribution_ref",
        "distribution_fingerprint",
    ),
    "player_rank_probabilities": (
        "release_id",
        "player_id",
        "top_1",
        "top_5",
        "top_10",
        "top_25",
        "top_50",
        "top_100",
        "top100_membership",
    ),
    "player_dimensions": (
        "release_id",
        "player_id",
        "dimension",
        "status",
        "point_value",
        "diagnostic_center",
        "lower_90",
        "upper_90",
        "methodology_version",
        "confidence",
        "reason_codes_json",
        "evidence_metadata_json",
    ),
}
JSON_COLUMNS = {"overall_json", "rank_json", "reason_codes_json", "evidence_metadata_json"}
RANK_BAND_COLUMNS = (
    "median_rank",
    "mean_rank",
    "rank_lower_50",
    "rank_upper_50",
    "rank_lower_80",
    "rank_upper_80",
    "rank_lower_90",
    "rank_upper_90",
    "rank_lower_95",
    "rank_upper_95",
)
TARGET_PROBABILITY_COLUMNS = TABLE_COLUMNS["player_rank_probabilities"] + RANK_BAND_COLUMNS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class ReleaseBundle:
    directory: Path
    manifest: RankingRelease
    methodology: dict[str, Any]
    tables: dict[str, list[dict[str, Any]]]
    profiles: list[dict[str, Any]]
    top100: list[dict[str, Any]]


def read_release_bundle(
    release_dir: Path,
    *,
    expected_release_id: str = FROZEN_RELEASE_ID,
    expected_fingerprint: str = FROZEN_RELEASE_FINGERPRINT,
) -> ReleaseBundle:
    """Validate every byte and relational cross-reference before opening a DB transaction."""

    manifest_path = release_dir / "ranking-release-manifest.json"
    manifest_json = json.loads(manifest_path.read_text())
    declared_fingerprint = manifest_json.pop("release_fingerprint")
    recomputed = hashlib.sha256(canonical_json(manifest_json)).hexdigest()
    if declared_fingerprint != recomputed or declared_fingerprint != expected_fingerprint:
        raise ValueError("frozen release fingerprint mismatch")
    manifest = RankingRelease.model_validate(
        {**manifest_json, "release_fingerprint": declared_fingerprint}
    )
    if manifest.release_id != expected_release_id:
        raise ValueError("unexpected ranking release ID")
    for relative, expected_hash in manifest.artifact_sha256.items():
        if _sha256(release_dir / relative) != expected_hash:
            raise ValueError(f"release artifact hash mismatch: {relative}")
    methodology = json.loads((release_dir / "methodology-metadata.json").read_text())
    if (
        methodology["release_id"] != manifest.release_id
        or methodology["ranking_policy"]["policy_version"] != manifest.ranking_policy_version
        or methodology["overall_substrate_version"] != manifest.overall_substrate_version
    ):
        raise ValueError("release methodology metadata differs from manifest")
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, columns in TABLE_COLUMNS.items():
        table = pq.read_table(release_dir / "db" / f"{name}.parquet")
        if tuple(table.schema.names) != columns:
            raise ValueError(f"DB-load schema mismatch: {name}")
        tables[name] = table.to_pylist()
        if any(row["release_id"] != manifest.release_id for row in tables[name]):
            raise ValueError(f"DB-load release ID mismatch: {name}")
    version_rows = pq.read_table(release_dir / "db/ranking_versions.parquet").to_pylist()
    if len(version_rows) != 1 or version_rows[0]["release_id"] != manifest.release_id:
        raise ValueError("ranking_versions DB-load source differs")
    if (
        version_rows[0]["source_ranking_fingerprint"]
        != manifest.upstream_sha256["step_0015o_fingerprint"]
    ):
        raise ValueError("ranking source fingerprint differs")
    tables["ranking_versions"] = version_rows
    profiles = [
        json.loads(line)
        for line in (release_dir / "player-profiles.jsonl").read_text().splitlines()
    ]
    for item in profiles:
        PlayerProfile.model_validate(item)
    top100 = json.loads((release_dir / "leaderboard-v2-probabilistic.json").read_text())
    leaderboard = json.loads((release_dir / "leaderboard.json").read_text())
    player_ids = {row["player_id"] for row in tables["players"]}
    rank_ids = {row["player_id"] for row in tables["player_rankings"]}
    prob_ids = {row["player_id"] for row in tables["player_rank_probabilities"]}
    profile_ids = {row["identity"]["player_id"] for row in profiles}
    if not (
        len(player_ids) == len(profile_ids) == len(profiles) == manifest.player_count == 5103
        and len(rank_ids) == len(prob_ids) == len(leaderboard) == manifest.rankable_count == 1882
        and len(tables["player_dimensions"]) == manifest.player_count * 7
        and len(top100) == 100
        and len(player_ids - rank_ids) == manifest.unavailable_count == 3221
        and profile_ids == player_ids
    ):
        raise ValueError("release identity or row counts do not reconcile")
    if [
        row["player_id"]
        for row in sorted(tables["player_rankings"], key=lambda r: r["display_position"])
    ] != [row["player_id"] for row in leaderboard]:
        raise ValueError("leaderboard navigation differs from DB-load table")
    if [row["player_id"] for row in top100] != [row["player_id"] for row in leaderboard[:100]]:
        raise ValueError("frozen Top-100 order differs")
    if sorted(profile_ids & rank_ids) != sorted(rank_ids):
        raise ValueError("ranked player missing profile")
    with np.load(release_dir / "paired-overall-rank-draws.npz", allow_pickle=False) as draws:
        ids = draws["player_ids"].tolist()
        if (
            len(ids) != 1882
            or set(ids) != rank_ids
            or draws["overall_draws"].shape != (1882, 2500)
            or draws["rank_draws"].shape != (1882, 2500)
        ):
            raise ValueError("paired draw population or shape differs")
    return ReleaseBundle(release_dir, manifest, methodology, tables, profiles, top100)


def _copy_rows(
    cursor: psycopg.Cursor[Any],
    table: str,
    columns: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    # Table/column identifiers are fixed constants in this module, never caller input.
    statement = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
    with cursor.copy(statement) as copy:
        for row in rows:
            values = [
                Jsonb(json.loads(row[column])) if column in JSON_COLUMNS else row[column]
                for column in columns
            ]
            copy.write_row(values)


def _enriched_probabilities(bundle: ReleaseBundle) -> list[dict[str, Any]]:
    ranks = {
        row["player_id"]: json.loads(row["rank_json"]) for row in bundle.tables["player_rankings"]
    }
    result = []
    for source in bundle.tables["player_rank_probabilities"]:
        rank = ranks[source["player_id"]]
        result.append(
            {
                **source,
                "median_rank": rank["median_rank"],
                "mean_rank": rank["mean_rank"],
                **{
                    f"rank_{direction}_{level}": rank[f"{direction}_{level}"]
                    for direction in ("lower", "upper")
                    for level in (50, 80, 90, 95)
                },
            }
        )
    return result


def _ranking_version_row(bundle: ReleaseBundle) -> tuple[Any, ...]:
    manifest = bundle.manifest
    versions = bundle.methodology["dimension_methodology_versions"]
    return (
        manifest.release_id,
        manifest.release_fingerprint,
        manifest.generated_at_utc,
        manifest.cutoff_season,
        manifest.ranking_policy_version,
        manifest.overall_substrate_version,
        versions["peak"],
        versions["longevity"],
        versions["defense"],
        manifest.player_count,
        manifest.rankable_count,
        manifest.unavailable_count,
        manifest.upstream_sha256["step_0015o_fingerprint"],
        False,
        Jsonb(manifest.artifact_sha256),
        Jsonb(manifest.upstream_sha256),
        Jsonb(bundle.methodology),
        Jsonb(manifest.model_dump(mode="json")),
        "PUBLICATION_RIGHTS_REVIEW_REQUIRED",
    )


RELEASE_COLUMNS = (
    "release_id",
    "release_fingerprint",
    "generated_at_utc",
    "cutoff_season",
    "ranking_policy_version",
    "overall_substrate_version",
    "peak_version",
    "longevity_version",
    "defense_version",
    "player_count",
    "rankable_count",
    "unavailable_count",
    "source_ranking_fingerprint",
    "exact_overall_point_promoted",
    "artifact_sha256",
    "upstream_sha256",
    "methodology_json",
    "manifest_json",
    "publication_rights_status",
)


def reconcile_loaded_release(cursor: psycopg.Cursor[Any], bundle: ReleaseBundle) -> dict[str, int]:
    """Compare every canonical ID, status, probability, dimension, profile and Top-100 payload."""

    release_id = bundle.manifest.release_id
    cursor.execute(
        "SELECT manifest_json, methodology_json, release_fingerprint FROM ranking_versions "
        "WHERE release_id = %s",
        (release_id,),
    )
    version = cursor.fetchone()
    if version is None or version["release_fingerprint"] != bundle.manifest.release_fingerprint:
        raise ValueError("loaded release metadata differs")
    if version["manifest_json"] != bundle.manifest.model_dump(mode="json"):
        raise ValueError("loaded manifest differs")
    if version["methodology_json"] != bundle.methodology:
        raise ValueError("loaded methodology differs")
    counts: dict[str, int] = {}
    for table, expected in (
        ("players", bundle.manifest.player_count),
        ("player_rankings", bundle.manifest.rankable_count),
        ("player_rank_probabilities", bundle.manifest.rankable_count),
        ("player_dimensions", bundle.manifest.player_count * 7),
        ("player_profiles", bundle.manifest.player_count),
        ("top100_entries", 100),
    ):
        cursor.execute(f"SELECT count(*) AS n FROM {table} WHERE release_id = %s", (release_id,))
        count_row = cursor.fetchone()
        assert count_row is not None
        count = int(count_row["n"])
        if count != expected:
            raise ValueError(f"post-load count mismatch: {table}")
        counts[table] = count
    for table, columns, source in (
        ("players", TABLE_COLUMNS["players"], bundle.tables["players"]),
        ("player_rankings", TABLE_COLUMNS["player_rankings"], bundle.tables["player_rankings"]),
        ("player_rank_probabilities", TARGET_PROBABILITY_COLUMNS, _enriched_probabilities(bundle)),
        (
            "player_dimensions",
            TABLE_COLUMNS["player_dimensions"],
            bundle.tables["player_dimensions"],
        ),
    ):
        order = "player_id, dimension" if table == "player_dimensions" else "player_id"
        cursor.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE release_id = %s ORDER BY {order}",
            (release_id,),
        )
        actual = cursor.fetchall()
        expected_rows = sorted(source, key=lambda r: (r["player_id"], r.get("dimension", "")))
        for db_row, source_row in zip(actual, expected_rows, strict=True):
            normalized = {
                key: json.loads(source_row[key]) if key in JSON_COLUMNS else source_row[key]
                for key in columns
            }
            if db_row != normalized:
                raise ValueError(f"post-load content mismatch: {table}/{source_row['player_id']}")
    cursor.execute(
        "SELECT player_id, profile_json FROM player_profiles "
        "WHERE release_id = %s ORDER BY player_id",
        (release_id,),
    )
    source_profiles = {row["identity"]["player_id"]: row for row in bundle.profiles}
    for row in cursor.fetchall():
        player_id = row["player_id"]
        if row["profile_json"] != source_profiles[player_id]:
            raise ValueError(f"post-load profile mismatch: {player_id}")
    cursor.execute(
        "SELECT payload_json FROM top100_entries WHERE release_id = %s ORDER BY display_position",
        (release_id,),
    )
    if [row["payload_json"] for row in cursor.fetchall()] != bundle.top100:
        raise ValueError("post-load Top-100 differs from frozen product view")
    cursor.execute(
        "SELECT ranking_status, count(*) AS n FROM player_rankings "
        "WHERE release_id = %s GROUP BY ranking_status",
        (release_id,),
    )
    actual_statuses = {row["ranking_status"]: row["n"] for row in cursor.fetchall()}
    expected_statuses: dict[str, int] = {}
    for row in bundle.tables["player_rankings"]:
        status = row["ranking_status"]
        expected_statuses[status] = expected_statuses.get(status, 0) + 1
    if actual_statuses != expected_statuses:
        raise ValueError("post-load ranking status counts differ")
    counts["unavailable"] = bundle.manifest.unavailable_count
    return counts


def load_ranking_release(
    database_url: str,
    bundle: ReleaseBundle,
    *,
    fail_after_table: str | None = None,
) -> dict[str, Any]:
    """COPY the release atomically; same fingerprint is a reconciled no-op."""

    started = time.perf_counter()
    release_id = bundle.manifest.release_id
    LOGGER.info("ranking release load started release_id=%s", release_id)
    try:
        # Keep the connection transaction boundary visibly outside the COPY cursor.
        with psycopg.connect(database_url, row_factory=dict_row) as connection:  # noqa: SIM117
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (release_id,))
                cursor.execute(
                    "SELECT release_fingerprint FROM ranking_versions WHERE release_id = %s",
                    (release_id,),
                )
                prior = cursor.fetchone()
                if prior is not None:
                    if prior["release_fingerprint"] != bundle.manifest.release_fingerprint:
                        raise ValueError("same release ID already has a different fingerprint")
                    counts = reconcile_loaded_release(cursor, bundle)
                    LOGGER.info("ranking release already loaded release_id=%s", release_id)
                    return {
                        "release_id": release_id,
                        "outcome": "ALREADY_LOADED",
                        "counts": counts,
                        "runtime_seconds": round(time.perf_counter() - started, 3),
                    }
                statement = (
                    "INSERT INTO ranking_versions ("
                    + ", ".join(RELEASE_COLUMNS)
                    + ") VALUES ("
                    + ", ".join(["%s"] * len(RELEASE_COLUMNS))
                    + ")"
                )
                cursor.execute(statement, _ranking_version_row(bundle))
                if fail_after_table == "ranking_versions":
                    raise RuntimeError("intentional transactional load failure")
                for table in (
                    "players",
                    "player_rankings",
                    "player_rank_probabilities",
                    "player_dimensions",
                ):
                    if table == "player_rank_probabilities":
                        _copy_rows(
                            cursor,
                            table,
                            TARGET_PROBABILITY_COLUMNS,
                            _enriched_probabilities(bundle),
                        )
                    else:
                        _copy_rows(cursor, table, TABLE_COLUMNS[table], bundle.tables[table])
                    if fail_after_table == table:
                        raise RuntimeError("intentional transactional load failure")
                with cursor.copy(
                    "COPY player_profiles (release_id, player_id, profile_json) FROM STDIN"
                ) as copy:
                    for profile in bundle.profiles:
                        copy.write_row(
                            (release_id, profile["identity"]["player_id"], Jsonb(profile))
                        )
                if fail_after_table == "player_profiles":
                    raise RuntimeError("intentional transactional load failure")
                with cursor.copy(
                    "COPY top100_entries (release_id, display_position, player_id, payload_json) "
                    "FROM STDIN"
                ) as copy:
                    for row in bundle.top100:
                        copy.write_row(
                            (release_id, row["display_position"], row["player_id"], Jsonb(row))
                        )
                if fail_after_table == "top100_entries":
                    raise RuntimeError("intentional transactional load failure")
                counts = reconcile_loaded_release(cursor, bundle)
        LOGGER.info("ranking release load committed release_id=%s", release_id)
        return {
            "release_id": release_id,
            "outcome": "LOADED",
            "counts": counts,
            "runtime_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception:
        LOGGER.exception("ranking release load rolled back release_id=%s", release_id)
        raise
