#!/usr/bin/env python3
"""Measure local read-only API latency for a configured immutable release."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable

from fastapi.testclient import TestClient
from httpx import Response

from goatlab.product.api import create_app
from goatlab.product.settings import ProductSettings


def _measure(request: Callable[[], Response], count: int = 25) -> dict[str, float]:
    times = []
    for _ in range(count):
        started = time.perf_counter()
        response = request()
        response.raise_for_status()
        times.append((time.perf_counter() - started) * 1000)
    ordered = sorted(times)
    return {
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(ordered[int(0.95 * (count - 1))], 3),
    }


def main() -> None:
    settings = ProductSettings.from_environment()
    with TestClient(create_app(settings)) as client:
        page = client.get("/api/v1/leaderboard", params={"limit": 2})
        page.raise_for_status()
        first, second = [row["player_id"] for row in page.json()["entries"]]
        comparison_path = f"/api/v1/compare/{first}/{second}"
        started = time.perf_counter()
        client.get(comparison_path).raise_for_status()
        pairwise_cold_ms = round((time.perf_counter() - started) * 1000, 3)
        result = {
            "release_id": settings.release_id,
            "backend_mode": settings.backend_mode,
            "leaderboard_first_100": _measure(lambda: client.get("/api/v1/leaderboard")),
            "player_profile": _measure(lambda: client.get(f"/api/v1/players/{first}")),
            "pairwise_cold_ms": pairwise_cold_ms,
            "pairwise_warm": _measure(lambda: client.get(comparison_path)),
        }
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
