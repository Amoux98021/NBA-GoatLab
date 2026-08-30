import json
from pathlib import Path

import pytest

from goatlab.data.historical_corpus import (
    CORPUS_END_SEASON,
    BackfillStatus,
    OutputPartitionStatus,
    acquisition_matrix,
    frozen_seasons,
    initial_checkpoint,
    load_or_initialize_checkpoint,
    partition_fingerprint,
    reconciliation_summary,
    season_label,
    set_output_status,
    update_request_checkpoint,
    write_atomic_json,
)
from goatlab.data.nba_api_client import RequestOutcome, RequestResult


def _result(outcome: RequestOutcome = RequestOutcome.SUCCESS_WITH_ROWS) -> RequestResult:
    return RequestResult(
        outcome=outcome,
        cache_key="abc",
        endpoint="playergamelogs",
        parameters={"Season": "1946-47"},
        attempts=2,
        elapsed_seconds=1.25,
        status_code=200,
        response_sha256="def",
        payload={"resultSets": [{"headers": ["PLAYER_ID"], "rowSet": [[1]]}]},
        error_type=None,
        error_message=None,
        request_url="fixture",
        from_cache=False,
    )


def test_frozen_corpus_cutoff_and_matrix() -> None:
    seasons = frozen_seasons()
    scopes = acquisition_matrix()
    assert len(seasons) == 80
    assert seasons[0] == "1946-47"
    assert seasons[-1] == CORPUS_END_SEASON
    assert len(scopes) == 280
    assert sum(scope.endpoint == "playergamelogs" for scope in scopes) == 160
    assert sum(scope.measure_type == "Base" for scope in scopes) == 60
    assert sum(scope.measure_type == "Advanced" for scope in scopes) == 60
    assert all(scope.season != "2026-27" for scope in scopes)
    assert season_label(2025) == CORPUS_END_SEASON


def test_checkpoint_resumes_and_rejects_matrix_drift(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = initial_checkpoint()
    scope = acquisition_matrix()[0]
    update_request_checkpoint(
        checkpoint,
        scope,
        _result(),
        row_count=1,
        retrieval_timestamp="2026-08-27T15:00:00Z",
    )
    set_output_status(checkpoint, scope, OutputPartitionStatus.WRITTEN, ["partition"])
    write_atomic_json(path, checkpoint)
    resumed = load_or_initialize_checkpoint(path)
    assert resumed["requests"][scope.scope_id]["request_status"] == (
        BackfillStatus.SUCCESS_WITH_ROWS.value
    )
    assert resumed["requests"][scope.scope_id]["output_paths"] == ["partition"]

    drifted = json.loads(path.read_text())
    drifted["requests"].pop(scope.scope_id)
    write_atomic_json(path, drifted)
    with pytest.raises(ValueError, match="matrix differs"):
        load_or_initialize_checkpoint(path)


def test_partition_status_transition_requires_success() -> None:
    checkpoint = initial_checkpoint()
    scope = acquisition_matrix()[0]
    with pytest.raises(ValueError, match="unsuccessful"):
        set_output_status(checkpoint, scope, OutputPartitionStatus.WRITTEN)
    update_request_checkpoint(
        checkpoint,
        scope,
        _result(RequestOutcome.RETRYABLE_FAILURE),
        row_count=0,
        retrieval_timestamp="2026-08-27T15:00:00Z",
    )
    assert checkpoint["requests"][scope.scope_id]["request_status"] == "FAILED_RETRYABLE"


def test_corpus_partition_fingerprint_is_deterministic_and_sensitive() -> None:
    first = [
        {"path": "b", "rows": 2, "columns": 3, "size_bytes": 4, "sha256": "two"},
        {"path": "a", "rows": 1, "columns": 3, "size_bytes": 3, "sha256": "one"},
    ]
    assert partition_fingerprint(first) == partition_fingerprint(list(reversed(first)))
    changed = [*first[:-1], {**first[-1], "sha256": "changed"}]
    assert partition_fingerprint(first) != partition_fingerprint(changed)


def test_reconciliation_summary_accounts_for_mismatches() -> None:
    partition = {
        "compared_values": 3,
        "exact_matches": 1,
        "tolerance_matches": 1,
        "mismatches": 1,
        "derived_only_players": ["a"],
        "official_only_players": ["b"],
        "passes_v1_gate": False,
        "fields": {"PTS": {"mismatches": 1}},
        "mismatch_examples": [{"player_id": "a", "source_field": "PTS"}],
    }
    summary = reconciliation_summary({"scope": partition})
    assert summary["values_compared"] == 3
    assert summary["mismatches"] == 1
    assert summary["mismatches_by_field"] == {"PTS": 1}
    assert summary["derived_only_players"] == 1
    assert summary["official_only_players"] == 1
