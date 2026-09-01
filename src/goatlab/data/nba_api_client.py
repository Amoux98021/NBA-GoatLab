"""Bounded, cached, provenance-rich client for official NBA Stats endpoints."""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast

import requests
from nba_api.stats.library.http import NBAStatsHTTP  # type: ignore[import-untyped]

JsonScalar = str | int | float | bool | None


class RequestOutcome(StrEnum):
    SUCCESS_WITH_ROWS = "SUCCESS_WITH_ROWS"
    SUCCESS_EMPTY = "SUCCESS_EMPTY"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    UNSUPPORTED_SCOPE = "UNSUPPORTED_SCOPE"


@dataclass(frozen=True)
class RequestSpec:
    endpoint: str
    parameters: Mapping[str, JsonScalar]
    contract_version: int = 1

    def canonical_contract(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "endpoint": self.endpoint.lower(),
            "nba_api_version": metadata.version("nba_api"),
            "parameters": {key: self.parameters[key] for key in sorted(self.parameters)},
        }

    def cache_key(self) -> str:
        encoded = json.dumps(
            self.canonical_contract(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: str
    url: str
    response_headers: Mapping[str, str]


class Transport(Protocol):
    def send(
        self, endpoint: str, parameters: Mapping[str, JsonScalar], timeout_seconds: float
    ) -> TransportResponse: ...


class NBAStatsTransport:
    """HTTP transport using the installed nba_api header contract."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._headers = dict(NBAStatsHTTP.headers)

    def send(
        self, endpoint: str, parameters: Mapping[str, JsonScalar], timeout_seconds: float
    ) -> TransportResponse:
        url = NBAStatsHTTP.base_url.format(endpoint=endpoint.lower())
        response = self._session.get(
            url,
            params=sorted(parameters.items()),
            headers=self._headers,
            timeout=timeout_seconds,
        )
        return TransportResponse(
            status_code=response.status_code,
            body=response.text.lstrip("\ufeff"),
            url=response.url,
            response_headers={key: value for key, value in response.headers.items()},
        )


@dataclass(frozen=True)
class RequestResult:
    outcome: RequestOutcome
    cache_key: str
    endpoint: str
    parameters: Mapping[str, JsonScalar]
    attempts: int
    elapsed_seconds: float
    status_code: int | None
    response_sha256: str | None
    payload: dict[str, Any] | None
    error_type: str | None
    error_message: str | None
    request_url: str | None
    from_cache: bool = False

    @property
    def retry_count(self) -> int:
        return max(self.attempts - 1, 0)


class RateLimiter:
    """Single-process minimum-interval limiter shared across attempts."""

    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be non-negative")
        self.minimum_interval_seconds = minimum_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self.minimum_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleeper(remaining)
                now = self._clock()
        self._last_request_at = now


class ResponseCache:
    """Ignored Bronze cache with immutable request keys and atomic writes."""

    TERMINAL_OUTCOMES: ClassVar[set[RequestOutcome]] = {
        RequestOutcome.SUCCESS_WITH_ROWS,
        RequestOutcome.SUCCESS_EMPTY,
        RequestOutcome.PERMANENT_FAILURE,
        RequestOutcome.UNSUPPORTED_SCOPE,
    }

    def __init__(self, root: Path) -> None:
        self.root = root

    def _paths(self, spec: RequestSpec) -> tuple[Path, Path]:
        directory = self.root / spec.endpoint.lower()
        key = spec.cache_key()
        return directory / f"{key}.json", directory / f"{key}.meta.json"

    def load(self, spec: RequestSpec) -> RequestResult | None:
        raw_path, metadata_path = self._paths(spec)
        if not metadata_path.is_file():
            return None
        cache_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        outcome = RequestOutcome(cache_metadata["outcome"])
        if outcome not in self.TERMINAL_OUTCOMES:
            return None
        payload: dict[str, Any] | None = None
        if raw_path.is_file():
            parsed = json.loads(raw_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                payload = cast(dict[str, Any], parsed)
        return RequestResult(
            outcome=outcome,
            cache_key=spec.cache_key(),
            endpoint=spec.endpoint,
            parameters=dict(spec.parameters),
            attempts=int(cache_metadata["attempts"]),
            elapsed_seconds=float(cache_metadata["elapsed_seconds"]),
            status_code=cache_metadata.get("status_code"),
            response_sha256=cache_metadata.get("response_sha256"),
            payload=payload,
            error_type=cache_metadata.get("error_type"),
            error_message=cache_metadata.get("error_message"),
            request_url=cache_metadata.get("request_url"),
            from_cache=True,
        )

    def write(self, spec: RequestSpec, result: RequestResult, raw_body: str | None) -> None:
        raw_path, metadata_path = self._paths(spec)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if raw_body is not None:
            raw_temp = raw_path.with_suffix(".json.tmp")
            raw_temp.write_text(raw_body, encoding="utf-8")
            raw_temp.replace(raw_path)
        metadata_payload = {
            "request_contract": spec.canonical_contract(),
            "outcome": result.outcome.value,
            "attempts": result.attempts,
            "elapsed_seconds": result.elapsed_seconds,
            "status_code": result.status_code,
            "response_sha256": result.response_sha256,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "request_url": result.request_url,
        }
        metadata_temp = metadata_path.with_suffix(".json.tmp")
        metadata_temp.write_text(
            json.dumps(metadata_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        metadata_temp.replace(metadata_path)


def _parse_payload(body: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else None


def _response_has_rows(payload: Mapping[str, Any]) -> bool | None:
    # Modern NBA box-score V3 endpoints use a nested response contract rather
    # than the legacy resultSets/rowSet shape.  A listed player is a source row,
    # including an explicitly rostered DNP.
    box_score = payload.get("boxScoreTraditional")
    if isinstance(box_score, Mapping):
        found_team = False
        for key in ("homeTeam", "awayTeam"):
            team = box_score.get(key)
            if not isinstance(team, Mapping) or "players" not in team:
                continue
            found_team = True
            players = team.get("players")
            if isinstance(players, list) and players:
                return True
        return False if found_team else None
    raw_results = payload.get("resultSets", payload.get("resultSet"))
    if raw_results is None:
        return None
    results = [raw_results] if isinstance(raw_results, dict) else raw_results
    if not isinstance(results, list):
        return None
    found_result_set = False
    for result in results:
        if not isinstance(result, dict) or "rowSet" not in result:
            continue
        found_result_set = True
        rows = result["rowSet"]
        if isinstance(rows, list) and rows:
            return True
    return False if found_result_set else None


def classify_http_response(
    status_code: int, body: str
) -> tuple[RequestOutcome, dict[str, Any] | None, str | None]:
    """Classify HTTP/API outcomes without conflating errors with empty results."""
    payload = _parse_payload(body)
    message = body[:500]
    if payload is not None:
        for key in ("message", "error", "Message", "Error"):
            if key in payload:
                message = str(payload[key])[:500]
                break
    lowered = message.lower()
    if any(token in lowered for token in ("unsupported", "not supported", "invalid season")):
        return RequestOutcome.UNSUPPORTED_SCOPE, payload, message
    if status_code in {403, 408, 425, 429, 500, 502, 503, 504}:
        return RequestOutcome.RETRYABLE_FAILURE, payload, message
    if status_code < 200 or status_code >= 300:
        return RequestOutcome.PERMANENT_FAILURE, payload, message
    if payload is None:
        return RequestOutcome.RETRYABLE_FAILURE, None, "Successful HTTP status with invalid JSON"
    has_rows = _response_has_rows(payload)
    if has_rows is True:
        return RequestOutcome.SUCCESS_WITH_ROWS, payload, None
    if has_rows is False:
        return RequestOutcome.SUCCESS_EMPTY, payload, None
    return RequestOutcome.PERMANENT_FAILURE, payload, "JSON lacks an NBA result set"


def classify_exception(error: Exception) -> RequestOutcome:
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return RequestOutcome.RETRYABLE_FAILURE
    return RequestOutcome.PERMANENT_FAILURE


class NBAAPIClient:
    """Bounded NBA Stats client with resumable Bronze caching."""

    def __init__(
        self,
        cache: ResponseCache,
        *,
        transport: Transport | None = None,
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 1.0,
        backoff_cap_seconds: float = 8.0,
        jitter_fraction: float = 0.25,
        rate_limiter: RateLimiter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts < 1:
            raise ValueError("timeout_seconds and max_attempts must be positive")
        if not 0 <= jitter_fraction <= 1:
            raise ValueError("jitter_fraction must be between 0 and 1")
        self.cache = cache
        self.transport = transport or NBAStatsTransport()
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_cap_seconds = backoff_cap_seconds
        self.jitter_fraction = jitter_fraction
        self.rate_limiter = rate_limiter or RateLimiter(0.75)
        self._sleeper = sleeper
        self._rng = rng or random.Random()
        self._clock = clock

    def _backoff(self, retry_index: int) -> float:
        base = min(self.backoff_base_seconds * (2**retry_index), self.backoff_cap_seconds)
        return float(base + self._rng.uniform(0.0, base * self.jitter_fraction))

    def execute(self, spec: RequestSpec, *, force: bool = False) -> RequestResult:
        if not force and (cached := self.cache.load(spec)) is not None:
            return cached
        started = self._clock()
        last_result: RequestResult | None = None
        last_body: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.rate_limiter.wait()
            try:
                response = self.transport.send(
                    spec.endpoint, spec.parameters, self.timeout_seconds
                )
                last_body = response.body
                outcome, payload, error_message = classify_http_response(
                    response.status_code, response.body
                )
                last_result = RequestResult(
                    outcome=outcome,
                    cache_key=spec.cache_key(),
                    endpoint=spec.endpoint,
                    parameters=dict(spec.parameters),
                    attempts=attempt,
                    elapsed_seconds=round(self._clock() - started, 6),
                    status_code=response.status_code,
                    response_sha256=hashlib.sha256(response.body.encode("utf-8")).hexdigest(),
                    payload=payload,
                    error_type=None if error_message is None else "APIResponseError",
                    error_message=error_message,
                    request_url=response.url,
                )
            except Exception as error:  # bounded classification boundary around transport
                outcome = classify_exception(error)
                last_result = RequestResult(
                    outcome=outcome,
                    cache_key=spec.cache_key(),
                    endpoint=spec.endpoint,
                    parameters=dict(spec.parameters),
                    attempts=attempt,
                    elapsed_seconds=round(self._clock() - started, 6),
                    status_code=None,
                    response_sha256=None,
                    payload=None,
                    error_type=type(error).__name__,
                    error_message=str(error)[:500],
                    request_url=None,
                )
            if last_result.outcome is not RequestOutcome.RETRYABLE_FAILURE:
                self.cache.write(spec, last_result, last_body)
                return last_result
            if attempt < self.max_attempts:
                self._sleeper(self._backoff(attempt - 1))
        if last_result is None:
            raise RuntimeError("request loop did not execute")
        self.cache.write(spec, last_result, last_body)
        return last_result


def result_metadata(result: RequestResult) -> dict[str, object]:
    """Return stable request evidence for probe reporting."""
    values = asdict(result)
    values.pop("payload")
    values.pop("from_cache")
    values["outcome"] = result.outcome.value
    values["retry_count"] = result.retry_count
    return values
