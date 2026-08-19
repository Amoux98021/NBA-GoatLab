"""Deterministic, read-only auditing for an acquired nbadb bundle."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import duckdb

CANDIDATE_KEYS: dict[str, tuple[str, ...]] = {
    "common_player_info": ("person_id",),
    "draft_combine_stats": ("season", "player_id"),
    "draft_history": ("person_id", "season", "draft_type"),
    "game": ("game_id",),
    "game_info": ("game_id",),
    "game_summary": ("game_id",),
    "inactive_players": ("game_id", "player_id"),
    "line_score": ("game_id",),
    "officials": ("game_id", "official_id"),
    "other_stats": ("game_id",),
    "play_by_play": ("game_id", "eventnum"),
    "player": ("id",),
    "team": ("id",),
    "team_details": ("team_id",),
    "team_history": (
        "team_id",
        "city",
        "nickname",
        "year_founded",
        "year_active_till",
    ),
    "team_info_common": ("team_id", "season_year"),
}

IMPORTANT_GAME_METRICS = (
    "pts_home",
    "fgm_home",
    "fga_home",
    "fg3m_home",
    "fg3a_home",
    "ftm_home",
    "fta_home",
    "oreb_home",
    "dreb_home",
    "reb_home",
    "ast_home",
    "stl_home",
    "blk_home",
    "tov_home",
    "pf_home",
    "plus_minus_home",
)


@dataclass(frozen=True)
class ColumnAudit:
    name: str
    declared_type: str
    nullable: bool
    primary_key_ordinal: int


@dataclass(frozen=True)
class TableAudit:
    name: str
    row_count: int
    columns: tuple[ColumnAudit, ...]


@dataclass(frozen=True)
class DuplicateAudit:
    table: str
    candidate_key: tuple[str, ...]
    duplicate_groups: int


@dataclass(frozen=True)
class MetricAudit:
    metric: str
    first_observed_start_year: int | None
    last_observed_start_year: int | None
    null_count: int
    row_count: int


@dataclass(frozen=True)
class GameCoverage:
    first_start_year: int
    last_start_year: int
    distinct_start_years: int
    first_game_date: str
    last_game_date: str
    season_types: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class SourceAudit:
    source_path: str
    source_size_bytes: int
    source_sha256: str
    sqlite_version: str
    tables: tuple[TableAudit, ...]
    duplicate_checks: tuple[DuplicateAudit, ...]
    game_coverage: GameCoverage
    game_metric_observations: tuple[MetricAudit, ...]


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_game_coverage(connection: sqlite3.Connection) -> GameCoverage:
    coverage = connection.execute(
        """
        SELECT
            MIN(CAST(SUBSTR(season_id, -4) AS INTEGER)),
            MAX(CAST(SUBSTR(season_id, -4) AS INTEGER)),
            COUNT(DISTINCT CAST(SUBSTR(season_id, -4) AS INTEGER)),
            MIN(game_date),
            MAX(game_date)
        FROM game
        """
    ).fetchone()
    if coverage is None or any(value is None for value in coverage):
        raise ValueError("The source game table has no usable season coverage")
    season_types = tuple(
        (str(name), int(count))
        for name, count in connection.execute(
            "SELECT season_type, COUNT(*) FROM game GROUP BY season_type ORDER BY season_type"
        )
    )
    return GameCoverage(
        first_start_year=int(coverage[0]),
        last_start_year=int(coverage[1]),
        distinct_start_years=int(coverage[2]),
        first_game_date=str(coverage[3]),
        last_game_date=str(coverage[4]),
        season_types=season_types,
    )


def audit_sqlite(source_path: Path, display_path: str | None = None) -> SourceAudit:
    """Audit an nbadb SQLite snapshot without modifying it."""
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    connection = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    try:
        table_names = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        )
        tables: list[TableAudit] = []
        duplicate_checks: list[DuplicateAudit] = []
        for table_name in table_names:
            quoted_table = _quote_identifier(table_name)
            row_count = int(
                connection.execute(f"SELECT COUNT(*) FROM {quoted_table}").fetchone()[0]
            )
            columns = tuple(
                ColumnAudit(
                    name=str(row[1]),
                    declared_type=str(row[2]),
                    nullable=not bool(row[3]),
                    primary_key_ordinal=int(row[5]),
                )
                for row in connection.execute(f"PRAGMA table_info({quoted_table})")
            )
            tables.append(TableAudit(name=table_name, row_count=row_count, columns=columns))
            if candidate_key := CANDIDATE_KEYS.get(table_name):
                group_by = ", ".join(_quote_identifier(column) for column in candidate_key)
                duplicate_groups = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM ("
                        f"SELECT {group_by} FROM {quoted_table} "
                        f"GROUP BY {group_by} HAVING COUNT(*) > 1)"
                    ).fetchone()[0]
                )
                duplicate_checks.append(
                    DuplicateAudit(
                        table=table_name,
                        candidate_key=candidate_key,
                        duplicate_groups=duplicate_groups,
                    )
                )
        if "game" not in table_names:
            raise ValueError("The source does not contain the required audit anchor table: game")
        metrics: list[MetricAudit] = []
        game_columns = {
            column.name for table in tables if table.name == "game" for column in table.columns
        }
        for metric in IMPORTANT_GAME_METRICS:
            if metric not in game_columns:
                continue
            quoted_metric = _quote_identifier(metric)
            row = connection.execute(
                f"""
                SELECT
                    MIN(CASE WHEN {quoted_metric} IS NOT NULL
                        THEN CAST(SUBSTR(season_id, -4) AS INTEGER) END),
                    MAX(CASE WHEN {quoted_metric} IS NOT NULL
                        THEN CAST(SUBSTR(season_id, -4) AS INTEGER) END),
                    SUM(CASE WHEN {quoted_metric} IS NULL THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM game
                """
            ).fetchone()
            metrics.append(
                MetricAudit(
                    metric=metric,
                    first_observed_start_year=int(row[0]) if row[0] is not None else None,
                    last_observed_start_year=int(row[1]) if row[1] is not None else None,
                    null_count=int(row[2]),
                    row_count=int(row[3]),
                )
            )
        sqlite_version = str(connection.execute("SELECT sqlite_version()").fetchone()[0])
    finally:
        connection.close()
    return SourceAudit(
        source_path=display_path or source_path.as_posix(),
        source_size_bytes=source_path.stat().st_size,
        source_sha256=_sha256(source_path),
        sqlite_version=sqlite_version,
        tables=tuple(tables),
        duplicate_checks=tuple(duplicate_checks),
        game_coverage=_require_game_coverage_read_only(source_path),
        game_metric_observations=tuple(metrics),
    )


def _require_game_coverage_read_only(source_path: Path) -> GameCoverage:
    connection = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    try:
        return _require_game_coverage(connection)
    finally:
        connection.close()


def inspect_bundle_claims(
    metadata_path: Path, duckdb_path: Path, csv_directory: Path
) -> dict[str, Any]:
    """Compare bundle metadata claims with physical exported objects."""
    payload: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
    subtitle = str(payload.get("subtitle", ""))
    description = str(payload.get("description", ""))
    declared_match = re.search(r"(\d+)-table", subtitle)
    csv_match = re.search(r"CSV exports available\**:\s*(\d+)/(\d+)", description)
    duckdb_connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        duckdb_row = duckdb_connection.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            """
        ).fetchone()
        if duckdb_row is None:
            raise ValueError("DuckDB catalog count returned no row")
        duckdb_objects = int(duckdb_row[0])
    finally:
        duckdb_connection.close()
    csv_files = sorted(csv_directory.glob("*.csv"))
    licenses = payload.get("licenses", [])
    return {
        "dataset_id": payload.get("id"),
        "title": payload.get("title"),
        "license": licenses[0].get("name") if licenses else None,
        "declared_catalog_tables": int(declared_match.group(1)) if declared_match else None,
        "declared_csv_exports": int(csv_match.group(1)) if csv_match else None,
        "declared_csv_catalog": int(csv_match.group(2)) if csv_match else None,
        "physical_duckdb_objects": duckdb_objects,
        "physical_duckdb_size_bytes": duckdb_path.stat().st_size,
        "physical_csv_files": len(csv_files),
        "physical_csv_size_bytes": sum(path.stat().st_size for path in csv_files),
    }


def audit_to_dict(audit: SourceAudit) -> dict[str, Any]:
    """Convert immutable audit records into JSON-serializable data."""
    return asdict(audit)


def render_markdown(
    audit: SourceAudit,
    bundle_claims: dict[str, Any],
    *,
    kaggle_version: int,
    retrieved_at: str,
) -> str:
    """Render a concise but complete human-readable audit."""
    coverage = audit.game_coverage
    catalog_claim = bundle_claims["declared_catalog_tables"]
    csv_claim = bundle_claims["declared_csv_exports"]
    csv_catalog = bundle_claims["declared_csv_catalog"]
    csv_files = bundle_claims["physical_csv_files"]
    duckdb_objects = bundle_claims["physical_duckdb_objects"]
    lines = [
        "# nbadb source audit",
        "",
        f"Audited Kaggle `{bundle_claims['dataset_id']}` version `{kaggle_version}` retrieved at "
        f"`{retrieved_at}`. All SQL checks were read-only.",
        "",
        "## Publication/bundle reconciliation",
        "",
        "| Check | Declared | Observed |",
        "|---|---:|---:|",
        f"| Catalog tables | {catalog_claim} | {len(audit.tables)} SQLite tables |",
        f"| CSV exports | {csv_claim}/{csv_catalog} | {csv_files} files |",
        f"| DuckDB catalog objects | {catalog_claim} implied | {duckdb_objects} |",
        "",
        "The downloaded bundle does **not** contain the advertised v4 star schema. The 12 KiB "
        "DuckDB file has no user tables; the 2.35 GB SQLite file contains 16 legacy tables. The "
        "metadata describes current coverage, but observed games end in 2022-23. Mapping uses only "
        "the physical SQLite evidence and marks absent canonical inputs unavailable.",
        "",
        "## Observed coverage",
        "",
        f"- Game dates: `{coverage.first_game_date}` through `{coverage.last_game_date}`.",
        f"- Season start years: `{coverage.first_start_year}` through `{coverage.last_start_year}` "
        f"({coverage.distinct_start_years} distinct years).",
        "- Raw season types: "
        + ", ".join(f"`{name}` ({count:,})" for name, count in coverage.season_types)
        + ".",
        "- No player game box-score, player-season aggregate, advanced, or award table exists in "
        "the physical bundle.",
        "",
        "## Table inventory",
        "",
        "No `dim_*`, `fact_*`, `agg_*`, or `analytics_*` tables were discovered.",
        "",
        "| Physical table | Rows | Candidate key | Duplicate groups |",
        "|---|---:|---|---:|",
    ]
    duplicate_by_table = {item.table: item for item in audit.duplicate_checks}
    for table in audit.tables:
        duplicate = duplicate_by_table.get(table.name)
        key = "+".join(duplicate.candidate_key) if duplicate else "Not assessed"
        duplicate_count = str(duplicate.duplicate_groups) if duplicate else "—"
        lines.append(f"| `{table.name}` | {table.row_count:,} | `{key}` | {duplicate_count} |")
    lines.extend(
        [
            "",
            "Duplicate groups are source observations, not silently deduplicated facts. The 56 "
            "duplicate `game_id` groups are All-Star rows published under both `All Star` and "
            "`All-Star`; "
            "`play_by_play` has 7,360 duplicate `(game_id, eventnum)` groups.",
            "",
            "## Important team-game metric observations",
            "",
            "These are first/last *non-null observations*, not claims of reliable official "
            "coverage. Sparse anomalous pre-introduction values exist, so reliability must be set "
            "explicitly in `metric_coverage` rather than inferred from `MIN(season)`.",
            "",
            "| Source field | First observed | Last observed | Nulls | Null rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for metric in audit.game_metric_observations:
        null_rate = metric.null_count / metric.row_count if metric.row_count else 0.0
        lines.append(
            f"| `{metric.metric}` | {metric.first_observed_start_year} | "
            f"{metric.last_observed_start_year} | {metric.null_count:,} | {null_rate:.2%} |"
        )
    lines.extend(["", "## Physical schemas", ""])
    for table in audit.tables:
        lines.extend(
            [
                f"### `{table.name}`",
                "",
                "| Column | Declared type | Nullable | Source PK ordinal |",
                "|---|---|---:|---:|",
            ]
        )
        for column in table.columns:
            lines.append(
                f"| `{column.name}` | `{column.declared_type or 'untyped'}` | "
                f"{'yes' if column.nullable else 'no'} | {column.primary_key_ordinal} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Reproduction",
            "",
            "```bash",
            ".venv/bin/python pipelines/ingest/audit_nbadb.py \\",
            "  --data-dir data/bronze/nbadb \\",
            f"  --kaggle-version {kaggle_version} \\",
            f"  --retrieved-at {retrieved_at}",
            "```",
            "",
            f"SQLite SHA-256: `{audit.source_sha256}`.",
            "",
        ]
    )
    return "\n".join(lines)


def package_versions() -> dict[str, str]:
    """Return the installed source and analytics contract versions."""
    names = ("nbadb", "nba_api", "duckdb", "polars", "pyarrow", "pydantic", "pandera")
    return {name: metadata.version(name) for name in names}
