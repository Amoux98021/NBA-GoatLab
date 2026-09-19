"""Checksum-locked, transactional PostgreSQL migrations for product releases."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import psycopg

LOGGER = logging.getLogger(__name__)
DEFAULT_MIGRATIONS = Path(__file__).resolve().parents[3] / "db/migrations"


def apply_migrations(database_url: str, migrations_dir: Path = DEFAULT_MIGRATIONS) -> list[str]:
    """Apply each checked-in migration once; reject edited migration history."""

    files = sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise ValueError(f"no SQL migrations found in {migrations_dir}")
    applied: list[str] = []
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(6917017)")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS product_schema_migrations ("
            "name text PRIMARY KEY, checksum char(64) NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        cursor.execute("SELECT name, checksum FROM product_schema_migrations")
        known: dict[str, str] = dict(cursor.fetchall())
        file_names = {file.name for file in files}
        if set(known) - file_names:
            raise ValueError("database has unknown product migrations")
        for file in files:
            sql = file.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if file.name in known:
                if known[file.name] != checksum:
                    raise ValueError(f"migration changed after application: {file.name}")
                continue
            LOGGER.info("applying product migration %s", file.name)
            cursor.execute(sql)
            cursor.execute(
                "INSERT INTO product_schema_migrations(name, checksum) VALUES (%s, %s)",
                (file.name, checksum),
            )
            applied.append(file.name)
    return applied
