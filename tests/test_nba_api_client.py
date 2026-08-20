import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests

from goatlab.data.nba_api_client import (
    NBAAPIClient,
    RateLimiter,
    RequestOutcome,
    RequestSpec,
    ResponseCache,
    TransportResponse,
    classify_exception,
    classify_http_response,
)


class SequenceTransport:
    def __init__(self, responses: list[TransportResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def send(
        self, endpoint: str, parameters: Mapping[str, Any], timeout_seconds: float
    ) -> TransportResponse:
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _response(status: int, rows: list[list[object]]) -> TransportResponse:
    return TransportResponse(
        status_code=status,
        body=json.dumps({"resultSets": [{"headers": ["PLAYER_ID"], "rowSet": rows}]}),
        url="https://stats.nba.com/stats/test",
        response_headers={},
    )


def test_request_cache_key_is_deterministic_and_scope_sensitive() -> None:
    first = RequestSpec("playergamelogs", {"Season": "2022-23", "SeasonType": "Playoffs"})
    reordered = RequestSpec("PLAYERGAMELOGS", {"SeasonType": "Playoffs", "Season": "2022-23"})
    changed = RequestSpec("playergamelogs", {"Season": "2022-23", "SeasonType": "Regular Season"})
    assert first.cache_key() == reordered.cache_key()
    assert first.cache_key() != changed.cache_key()


def test_retry_classification_and_bounded_retry(tmp_path: Path) -> None:
    transport = SequenceTransport([_response(503, []), _response(200, [[1]])])
    client = NBAAPIClient(
        ResponseCache(tmp_path), transport=transport, max_attempts=2,
        rate_limiter=RateLimiter(0), sleeper=lambda _: None,
    )
    result = client.execute(RequestSpec("test", {"Season": "2022-23"}))
    assert result.outcome is RequestOutcome.SUCCESS_WITH_ROWS
    assert result.attempts == 2
    assert result.retry_count == 1
    assert transport.calls == 2


def test_errors_are_not_classified_as_empty() -> None:
    assert classify_http_response(429, "rate limited")[0] is RequestOutcome.RETRYABLE_FAILURE
    assert classify_http_response(400, "bad request")[0] is RequestOutcome.PERMANENT_FAILURE
    assert classify_exception(requests.Timeout()) is RequestOutcome.RETRYABLE_FAILURE
    assert classify_http_response(200, '{"resultSets":[{"headers":[],"rowSet":[]}]}')[0] is (
        RequestOutcome.SUCCESS_EMPTY
    )


def test_cache_is_resumable_and_preserves_provenance(tmp_path: Path) -> None:
    transport = SequenceTransport([_response(200, [[76003]])])
    client = NBAAPIClient(
        ResponseCache(tmp_path), transport=transport, rate_limiter=RateLimiter(0)
    )
    spec = RequestSpec("test", {"Season": "1955-56"})
    first = client.execute(spec)
    second = client.execute(spec)
    assert first.response_sha256
    assert second.from_cache
    assert second.cache_key == spec.cache_key()
    assert transport.calls == 1

