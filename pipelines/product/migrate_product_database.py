#!/usr/bin/env python3
"""Apply checksum-locked STEP-0017 PostgreSQL product migrations."""

from __future__ import annotations

import json
import os

from goatlab.product.migrations import apply_migrations


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required; credentials are never passed on the command line"
        )
    applied = apply_migrations(database_url)
    print(json.dumps({"applied_migrations": applied}, sort_keys=True))


if __name__ == "__main__":
    main()
