#!/usr/bin/env python3
"""Fail-fast smoke and immutable-release QA for a deployed GOATLab stack."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote

import requests

from goatlab.product.loading import FROZEN_RELEASE_FINGERPRINT, FROZEN_RELEASE_ID


@dataclass(frozen=True)
class TimedResponse:
    response: requests.Response
    elapsed_ms: float


def timed_get(session: requests.Session, url: str, *, timeout: float) -> TimedResponse:
    started = time.perf_counter()
    response = session.get(url, timeout=timeout, allow_redirects=False)
    return TimedResponse(response=response, elapsed_ms=(time.perf_counter() - started) * 1000)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def json_get(
    session: requests.Session, base: str, path: str, *, timeout: float, status: int = 200
) -> tuple[dict[str, Any], float]:
    result = timed_get(session, f"{base}{path}", timeout=timeout)
    require(
        result.response.status_code == status,
        f"{path}: expected {status}, got {result.response.status_code}",
    )
    try:
        payload = result.response.json()
    except requests.JSONDecodeError as error:
        raise RuntimeError(f"{path}: response was not JSON") from error
    require(isinstance(payload, dict), f"{path}: response was not an object")
    return payload, result.elapsed_ms


def find_player(session: requests.Session, api: str, name: str, timeout: float) -> dict[str, Any]:
    payload, _ = json_get(
        session,
        api,
        f"/api/v1/leaderboard?limit=5&search={quote(name)}&release={FROZEN_RELEASE_ID}",
        timeout=timeout,
    )
    require(payload.get("total") == 1, f"canonical search failed for {name}")
    entries = cast(list[dict[str, Any]], payload["entries"])
    return entries[0]


def check_api(session: requests.Session, api: str, timeout: float) -> dict[str, Any]:
    timings: dict[str, float] = {}
    health, timings["health_ms"] = json_get(session, api, "/api/v1/health", timeout=timeout)
    require(health.get("status") == "OK", "API health is not OK")
    require(health.get("release_id") == FROZEN_RELEASE_ID, "health release ID mismatch")
    require(health.get("configured_release_present") is True, "configured release is absent")
    require(
        health.get("publication_rights_gate") == "PUBLICATION_RIGHTS_REVIEW_REQUIRED",
        "publication-rights gate unexpectedly changed",
    )
    release, timings["release_ms"] = json_get(
        session, api, f"/api/v1/releases/{FROZEN_RELEASE_ID}", timeout=timeout
    )
    require(
        release.get("release_fingerprint") == FROZEN_RELEASE_FINGERPRINT,
        "release fingerprint mismatch",
    )
    leaderboard, timings["leaderboard_100_ms"] = json_get(
        session,
        api,
        f"/api/v1/leaderboard?limit=100&release={FROZEN_RELEASE_ID}",
        timeout=timeout,
    )
    require(leaderboard.get("total") == 1882, "rankable population mismatch")
    raw_entries = leaderboard.get("entries")
    require(
        isinstance(raw_entries, list) and len(raw_entries) == 100,
        "leaderboard page is incomplete",
    )
    entries = cast(list[dict[str, Any]], raw_entries)
    top100, timings["top100_ms"] = json_get(session, api, "/api/v1/top100", timeout=timeout)
    raw_top_entries = top100.get("entries")
    require(
        isinstance(raw_top_entries, list) and len(raw_top_entries) == 100,
        "Top 100 is incomplete",
    )
    top_entries = cast(list[dict[str, Any]], raw_top_entries)
    require(
        [row["player_id"] for row in entries] == [row["player_id"] for row in top_entries],
        "Top 100 differs from leaderboard navigation order",
    )
    jordan = find_player(session, api, "Michael Jordan", timeout)
    lebron = find_player(session, api, "LeBron James", timeout)
    player, timings["profile_ms"] = json_get(
        session, api, f"/api/v1/players/{quote(jordan['player_id'])}", timeout=timeout
    )
    require(player.get("identity", {}).get("player_name") == "Michael Jordan", "profile mismatch")
    forward, timings["pairwise_cold_ms"] = json_get(
        session,
        api,
        f"/api/v1/compare/{quote(jordan['player_id'])}/{quote(lebron['player_id'])}",
        timeout=timeout,
    )
    reverse, timings["pairwise_reverse_ms"] = json_get(
        session,
        api,
        f"/api/v1/compare/{quote(lebron['player_id'])}/{quote(jordan['player_id'])}",
        timeout=timeout,
    )
    require(
        abs(
            float(forward["probability_a_above_b"])
            + float(forward["probability_b_above_a"])
            - 1
        )
        < 1e-9,
        "pairwise probabilities are not complementary",
    )
    require(
        abs(
            float(forward["probability_a_above_b"])
            - float(reverse["probability_b_above_a"])
        )
        < 1e-9,
        "reversed pairwise probability differs",
    )
    _, timings["same_player_ms"] = json_get(
        session,
        api,
        f"/api/v1/compare/{quote(jordan['player_id'])}/{quote(jordan['player_id'])}",
        timeout=timeout,
        status=400,
    )
    _, timings["unknown_player_ms"] = json_get(
        session, api, "/api/v1/players/not-a-goatlab-player", timeout=timeout, status=404
    )
    return {
        "jordan_id": jordan["player_id"],
        "lebron_id": lebron["player_id"],
        "timings_ms": {key: round(value, 3) for key, value in timings.items()},
    }


def check_frontend(
    session: requests.Session,
    frontend: str,
    *,
    jordan_id: str,
    lebron_id: str,
    timeout: float,
    rights_approved: bool,
) -> dict[str, float]:
    paths = {
        "home": ("/", "Top 100"),
        "leaderboard": ("/leaderboard", "Explore the leaderboard"),
        "methodology": ("/methodology", "Methodology"),
        "player": (f"/players/{quote(jordan_id)}", "Michael Jordan"),
        "comparison": (f"/compare/{quote(jordan_id)}/{quote(lebron_id)}", "Michael Jordan"),
    }
    timings: dict[str, float] = {}
    for label, (path, marker) in paths.items():
        result = timed_get(session, f"{frontend}{path}", timeout=timeout)
        require(
            result.response.status_code == 200,
            f"frontend {path} returned {result.response.status_code}",
        )
        require(
            marker.lower() in result.response.text.lower(),
            f"frontend {path} lacks expected content",
        )
        require(
            any(
                disclosure in result.response.text.lower()
                for disclosure in ("uncertainty", "summary position", "not exact")
            ),
            f"frontend {path} lacks rank uncertainty disclosure",
        )
        if not rights_approved:
            require(
                "noindex" in result.response.headers.get("X-Robots-Tag", ""),
                f"frontend {path} is indexable before rights approval",
            )
        timings[f"{label}_ms"] = round(result.elapsed_ms, 3)
    robots = timed_get(session, f"{frontend}/robots.txt", timeout=timeout)
    require(robots.response.status_code == 200, "robots.txt unavailable")
    if not rights_approved:
        require("Disallow: /" in robots.response.text, "robots.txt does not block indexing")
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--frontend-base-url", required=True)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--publication-rights-approved", action="store_true")
    args = parser.parse_args()
    require(args.repeat > 0, "repeat must be positive")
    api = args.api_base_url.rstrip("/")
    frontend = args.frontend_base_url.rstrip("/")
    with requests.Session() as session:
        api_result = check_api(session, api, args.timeout)
        frontend_timings: list[dict[str, float]] = []
        for _ in range(args.repeat):
            frontend_timings.append(
                check_frontend(
                    session,
                    frontend,
                    jordan_id=api_result["jordan_id"],
                    lebron_id=api_result["lebron_id"],
                    timeout=args.timeout,
                    rights_approved=args.publication_rights_approved,
                )
            )
    medians = {
        key: round(statistics.median(run[key] for run in frontend_timings), 3)
        for key in frontend_timings[0]
    }
    print(
        json.dumps(
            {
                "api": api_result,
                "frontend_median_timings_ms": medians,
                "publication_rights_gate": (
                    "APPROVED"
                    if args.publication_rights_approved
                    else "PUBLICATION_RIGHTS_REVIEW_REQUIRED"
                ),
                "release_fingerprint": FROZEN_RELEASE_FINGERPRINT,
                "release_id": FROZEN_RELEASE_ID,
                "status": "PASS",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
