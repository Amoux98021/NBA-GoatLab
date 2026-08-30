"""Frozen historical-corpus scope, checkpoint, and fingerprint contracts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from goatlab.data.canonical import normalize_season_type
from goatlab.data.nba_api_client import RequestOutcome, RequestResult
from goatlab.data.nba_api_probe import (
    league_dash_player_stats_spec,
    player_game_logs_spec,
)

CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_START_YEAR = 1946
CORPUS_END_YEAR = 2025
CORPUS_END_SEASON = "2025-26"
SEASON_TYPES = ("Regular Season", "Playoffs")
ADVANCED_START_YEAR = 1996


class BackfillStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS_WITH_ROWS = "SUCCESS_WITH_ROWS"
    SUCCESS_EMPTY = "SUCCESS_EMPTY"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    UNSUPPORTED = "UNSUPPORTED"


class OutputPartitionStatus(StrEnum):
    PENDING = "PENDING"
    WRITTEN = "WRITTEN"
    RECONCILED = "RECONCILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AcquisitionScope:
    endpoint: str
    season: str
    season_type: str
    measure_type: str | None = None
    per_mode: str | None = None

    @property
    def scope_id(self) -> str:
        values = (
            self.endpoint.lower(),
            self.season,
            normalize_season_type(self.season_type).value,
            self.measure_type or "",
            self.per_mode or "",
        )
        return "|".join(values)

    def request_spec(self) -> Any:
        if self.endpoint == "playergamelogs":
            return player_game_logs_spec(self.season, self.season_type)
        if self.endpoint == "leaguedashplayerstats" and self.measure_type is not None:
            return league_dash_player_stats_spec(
                self.season,
                self.season_type,
                measure_type=self.measure_type,
                per_mode=self.per_mode or "Totals",
            )
        raise ValueError(f"unsupported acquisition scope: {self}")


def season_label(start_year: int) -> str:
    if start_year < CORPUS_START_YEAR:
        raise ValueError("season precedes the frozen corpus")
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def frozen_seasons() -> tuple[str, ...]:
    return tuple(season_label(year) for year in range(CORPUS_START_YEAR, CORPUS_END_YEAR + 1))


def acquisition_matrix() -> tuple[AcquisitionScope, ...]:
    scopes: list[AcquisitionScope] = []
    for year in range(CORPUS_START_YEAR, CORPUS_END_YEAR + 1):
        season = season_label(year)
        for season_type in SEASON_TYPES:
            scopes.append(AcquisitionScope("playergamelogs", season, season_type))
            if year >= ADVANCED_START_YEAR:
                scopes.extend(
                    AcquisitionScope(
                        "leaguedashplayerstats",
                        season,
                        season_type,
                        measure_type=measure,
                        per_mode="Totals",
                    )
                    for measure in ("Base", "Advanced")
                )
    return tuple(scopes)


def outcome_status(outcome: RequestOutcome) -> BackfillStatus:
    return {
        RequestOutcome.SUCCESS_WITH_ROWS: BackfillStatus.SUCCESS_WITH_ROWS,
        RequestOutcome.SUCCESS_EMPTY: BackfillStatus.SUCCESS_EMPTY,
        RequestOutcome.RETRYABLE_FAILURE: BackfillStatus.FAILED_RETRYABLE,
        RequestOutcome.PERMANENT_FAILURE: BackfillStatus.FAILED_PERMANENT,
        RequestOutcome.UNSUPPORTED_SCOPE: BackfillStatus.UNSUPPORTED,
    }[outcome]


def initial_checkpoint() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "corpus_id": CORPUS_ID,
        "historical_corpus_end_season": CORPUS_END_SEASON,
        "retrieval_started_utc": None,
        "retrieval_completed_utc": None,
        "network_build_performance": None,
        "cache_only_reproducibility": None,
        "requests": {
            scope.scope_id: {
                **asdict(scope),
                "scope_id": scope.scope_id,
                "request_status": BackfillStatus.PENDING.value,
                "row_count": None,
                "cache_key": None,
                "cache_fingerprint": None,
                "retrieval_timestamp": None,
                "retry_count": 0,
                "response_time_seconds": 0.0,
                "from_cache": False,
                "output_partition_status": OutputPartitionStatus.PENDING.value,
                "output_paths": [],
                "error_type": None,
                "error_message": None,
            }
            for scope in acquisition_matrix()
        },
    }


def load_or_initialize_checkpoint(path: Path) -> dict[str, Any]:
    expected = initial_checkpoint()
    if not path.is_file():
        return expected
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("checkpoint must be a JSON object")
    loaded = cast(dict[str, Any], parsed)
    if loaded.get("corpus_id") != CORPUS_ID:
        raise ValueError("checkpoint belongs to a different corpus")
    requests = loaded.get("requests")
    if not isinstance(requests, dict) or set(requests) != set(expected["requests"]):
        raise ValueError("checkpoint acquisition matrix differs from frozen corpus V1")
    return loaded


def update_request_checkpoint(
    checkpoint: dict[str, Any],
    scope: AcquisitionScope,
    result: RequestResult,
    *,
    row_count: int,
    retrieval_timestamp: str,
) -> None:
    item = checkpoint["requests"][scope.scope_id]
    item.update(
        {
            "request_status": outcome_status(result.outcome).value,
            "row_count": row_count,
            "cache_key": result.cache_key,
            "cache_fingerprint": result.response_sha256,
            "retrieval_timestamp": retrieval_timestamp,
            "retry_count": result.retry_count,
            "response_time_seconds": result.elapsed_seconds,
            "from_cache": result.from_cache,
            "error_type": result.error_type,
            "error_message": result.error_message,
        }
    )


def set_output_status(
    checkpoint: dict[str, Any],
    scope: AcquisitionScope,
    status: OutputPartitionStatus,
    paths: Sequence[str] = (),
) -> None:
    item = checkpoint["requests"][scope.scope_id]
    request_status = BackfillStatus(item["request_status"])
    if status in {OutputPartitionStatus.WRITTEN, OutputPartitionStatus.RECONCILED} and (
        request_status is not BackfillStatus.SUCCESS_WITH_ROWS
    ):
        raise ValueError("cannot complete output for an unsuccessful request")
    item["output_partition_status"] = status.value
    item["output_paths"] = sorted(paths)


def write_atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def partition_fingerprint(partitions: Sequence[Mapping[str, Any]]) -> str:
    stable = [
        {
            "path": str(item["path"]),
            "rows": int(item["rows"]),
            "columns": int(item["columns"]),
            "size_bytes": int(item["size_bytes"]),
            "sha256": str(item["sha256"]),
        }
        for item in sorted(partitions, key=lambda value: str(value["path"]))
    ]
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_summary(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    requests = list(checkpoint["requests"].values())
    statuses = Counter(str(item["request_status"]) for item in requests)
    return {
        "total": len(requests),
        "status_counts": dict(sorted(statuses.items())),
        "success_with_rows": statuses[BackfillStatus.SUCCESS_WITH_ROWS.value],
        "success_empty": statuses[BackfillStatus.SUCCESS_EMPTY.value],
        "retry_count": sum(int(item["retry_count"]) for item in requests),
        "failed": sum(
            statuses[value.value]
            for value in (
                BackfillStatus.FAILED_RETRYABLE,
                BackfillStatus.FAILED_PERMANENT,
                BackfillStatus.UNSUPPORTED,
            )
        ),
        "recorded_source_response_seconds": round(
            sum(float(item["response_time_seconds"]) for item in requests),
            6,
        ),
    }


def reconciliation_summary(partitions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    values = list(partitions.values())
    fields: Counter[str] = Counter()
    mismatch_examples: list[dict[str, Any]] = []
    for partition in values:
        for field, counts in partition["fields"].items():
            fields[field] += int(counts["mismatches"])
        mismatch_examples.extend(partition["mismatch_examples"])
    return {
        "partitions": len(values),
        "values_compared": sum(int(value["compared_values"]) for value in values),
        "exact_matches": sum(int(value["exact_matches"]) for value in values),
        "tolerance_matches": sum(int(value["tolerance_matches"]) for value in values),
        "mismatches": sum(int(value["mismatches"]) for value in values),
        "derived_only_players": sum(len(value["derived_only_players"]) for value in values),
        "official_only_players": sum(len(value["official_only_players"]) for value in values),
        "mismatches_by_field": dict(sorted(fields.items())),
        "mismatch_examples": mismatch_examples[:100],
        "partitions_passing_v1_gate": sum(bool(value["passes_v1_gate"]) for value in values),
    }
