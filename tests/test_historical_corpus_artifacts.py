"""Offline validation of committed GOATLAB-HIST-V1 audit artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/data"


def _read(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_frozen_corpus_artifacts_are_internally_consistent() -> None:
    manifest = _read("historical-corpus-v1-manifest.json")
    summary = _read("full-backfill-summary.json")
    coverage = _read("full-metric-coverage.json")
    reconciliation = _read("full-base-reconciliation.json")
    quality = _read("full-data-quality-report.json")

    assert manifest["corpus_id"] == "GOATLAB-HIST-V1"
    assert manifest["season_start"] == "1946-47"
    assert manifest["season_end"] == "2025-26"
    assert manifest["future_seasons_excluded"] is True
    assert len(manifest["silver_partitions"]) == 380
    assert all("season=2026" not in item["path"] for item in manifest["silver_partitions"])
    assert manifest["reproducibility"]["pass"] is True
    assert (
        manifest["reproducibility"]["observed_corpus_fingerprint"] == manifest["corpus_fingerprint"]
    )

    assert summary["decision"] == "PASS"
    assert summary["requests"]["total"] == 280
    assert summary["requests"]["failed"] == 0
    assert (
        summary["silver"]["player_game_rows"] + summary["quarantined_rows"]
        == summary["bronze"]["player_game_rows"]
    )
    assert summary["silver"]["partition_files"] == 380

    assert coverage["summary"]["records"] == 3040
    assert sum(coverage["summary"]["classification_counts"].values()) == 3040
    assert reconciliation["summary"]["partitions"] == 60
    assert reconciliation["summary"]["mismatches"] == 0
    assert quality["totals"]["pipeline_error_quarantine_rows"] == 0
    assert quality["totals"]["source_anomaly_quarantine_rows"] == 125
