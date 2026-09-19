#!/usr/bin/env python3
"""Verify and transactionally COPY the frozen probabilistic release into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from goatlab.product.loading import (
    FROZEN_RELEASE_FINGERPRINT,
    FROZEN_RELEASE_ID,
    load_ranking_release,
    read_release_bundle,
)

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=ROOT / "data/product" / FROZEN_RELEASE_ID,
    )
    parser.add_argument("--expected-fingerprint", default=FROZEN_RELEASE_FINGERPRINT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    bundle = read_release_bundle(
        args.release_dir,
        expected_release_id=FROZEN_RELEASE_ID,
        expected_fingerprint=args.expected_fingerprint,
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "release_id": bundle.manifest.release_id,
                    "fingerprint": bundle.manifest.release_fingerprint,
                    "validated_only": True,
                },
                sort_keys=True,
            )
        )
        return
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required; credentials are never passed on the command line"
        )
    print(json.dumps(load_ranking_release(database_url, bundle), sort_keys=True))


if __name__ == "__main__":
    main()
