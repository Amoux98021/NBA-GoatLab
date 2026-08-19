"""Command-line entry point for the reproducible nbadb source audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

from goatlab.data.nbadb_audit import (
    audit_sqlite,
    audit_to_dict,
    inspect_bundle_claims,
    package_versions,
    render_markdown,
)

DEFAULT_INVENTORY: Final = Path("docs/data/nbadb-inventory.json")
DEFAULT_REPORT: Final = Path("docs/data/NBADB_SOURCE_AUDIT.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--kaggle-version", type=int, required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--inventory-output", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sqlite_path = args.data_dir / "nba.sqlite"
    audit = audit_sqlite(sqlite_path, display_path="data/bronze/nbadb/nba.sqlite")
    claims = inspect_bundle_claims(
        args.data_dir / "dataset-metadata.json",
        args.data_dir / "nba.duckdb",
        args.data_dir / "csv",
    )
    payload = {
        "retrieved_at": args.retrieved_at,
        "kaggle_version": args.kaggle_version,
        "package_versions": package_versions(),
        "bundle_claims": claims,
        "sqlite_audit": audit_to_dict(audit),
    }
    args.inventory_output.parent.mkdir(parents=True, exist_ok=True)
    args.inventory_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(
        render_markdown(
            audit,
            claims,
            kaggle_version=args.kaggle_version,
            retrieved_at=args.retrieved_at,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
