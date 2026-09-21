#!/usr/bin/env python3
"""Materialize a verified frozen release into an API runtime artifact root."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from goatlab.product.deployment import materialize_release
from goatlab.product.loading import FROZEN_RELEASE_FINGERPRINT, FROZEN_RELEASE_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.getenv("GOATLAB_PRODUCT_ARTIFACT_ROOT", "/tmp/goatlab-product")),
    )
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    outcome = materialize_release(
        args.artifact_root,
        archive_path=args.archive,
        archive_sha256=os.getenv("GOATLAB_RELEASE_BUNDLE_SHA256"),
        bundle_url=os.getenv("GOATLAB_RELEASE_BUNDLE_URL"),
        bearer_token=os.getenv("GOATLAB_RELEASE_BUNDLE_BEARER_TOKEN"),
    )
    print(
        json.dumps(
            {
                "artifact_root": str(args.artifact_root),
                "outcome": outcome,
                "release_fingerprint": FROZEN_RELEASE_FINGERPRINT,
                "release_id": FROZEN_RELEASE_ID,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
