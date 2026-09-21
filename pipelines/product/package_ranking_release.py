#!/usr/bin/env python3
"""Package the frozen product release for hash-pinned deployment transport."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from goatlab.product.deployment import package_release
from goatlab.product.loading import FROZEN_RELEASE_ID

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-dir", type=Path, default=ROOT / "data/product" / FROZEN_RELEASE_ID
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fingerprint = package_release(args.release_dir, args.output)
    print(
        json.dumps(
            {"bundle": str(args.output), "release_id": FROZEN_RELEASE_ID, "sha256": fingerprint},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
