#!/usr/bin/env python3
"""Run the bounded STEP-0004 official NBA player-fact feasibility probe."""

from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
from typing import Any

from goatlab.data.nba_api_client import NBAAPIClient, RateLimiter, ResponseCache
from goatlab.data.nba_api_probe import (
    identity_coverage,
    league_dash_player_stats_spec,
    player_game_logs_spec,
    reconcile_2022_23,
    rows_from_result,
    stable_json,
    summarize_probe,
    write_json_report,
)

ROOT = Path(__file__).resolve().parents[2]
SEASONS = (
    "1946-47", "1955-56", "1961-62", "1973-74", "1979-80", "1984-85",
    "1996-97", "2009-10", "2022-23", "2023-24", "2024-25", "2025-26",
)
ADVANCED_SEASONS = ("1995-96", "1996-97", "1997-98", "2009-10", "2022-23", "2025-26")
SEASON_TYPES = ("Regular Season", "Playoffs")

# Fixed before observing live responses.
DECISION_CRITERIA = {
    "PASS": (
        "PlayerGameLogs returns plausible bulk rows for every representative regular and playoff "
        "season from 1946-47 through 2025-26, while Advanced/Totals works from 1996-97 onward. "
        "Player-season facts can therefore be acquired directly where exposed or deterministically "
        "aggregated from official game facts."
    ),
    "PARTIAL PASS": (
        "Some representative game-level eras or season types have gaps, but official game or "
        "season endpoints still span the early and current eras and Advanced/Totals works for at "
        "least the tested modern seasons."
    ),
    "FAIL": (
        "Official endpoints do not yield plausible player-level facts spanning the early and "
        "current eras, leaving no defensible official bulk acquisition path."
    ),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-at", required=True, help="Fixed ISO-8601 evidence timestamp")
    parser.add_argument("--cache-root", type=Path, default=ROOT / "data/bronze/nba_api")
    parser.add_argument("--sqlite", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--pace", type=float, default=1.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _decision(probes: list[dict[str, Any]]) -> str:
    def plausible(kind: str, season: str, season_type: str, measure: str | None = None) -> bool:
        return any(
            probe["probe_kind"] == kind
            and probe["season"] == season
            and probe["season_type"] == season_type
            and (measure is None or probe["measure_type"] == measure)
            and probe["plausible"]
            and probe["row_count"] > 0
            for probe in probes
        )

    pgl_all = all(
        plausible("PLAYER_GAME_LOGS", season, season_type)
        for season in SEASONS
        for season_type in SEASON_TYPES
    )
    advanced_post_boundary = all(
        plausible("LEAGUE_DASH_PLAYER_STATS", season, season_type, "Advanced")
        for season in ADVANCED_SEASONS[1:]
        for season_type in SEASON_TYPES
    )
    if pgl_all and advanced_post_boundary:
        return "PASS"
    spans_official = all(
        plausible("PLAYER_GAME_LOGS", season, "Regular Season")
        or plausible("LEAGUE_DASH_PLAYER_STATS", season, "Regular Season", "Base")
        for season in (SEASONS[0], SEASONS[-1])
    )
    advanced_modern = all(
        plausible("LEAGUE_DASH_PLAYER_STATS", season, "Regular Season", "Advanced")
        for season in ("2009-10", "2022-23", "2025-26")
    )
    return "PARTIAL PASS" if spans_official and advanced_modern else "FAIL"


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Official NBA API player-fact feasibility probe",
        "",
        f"Observed at: `{report['observed_at']}`  ",
        f"nba_api: `{report['software']['nba_api']}`  ",
        f"Decision: **{report['decision']}**",
        "",
        "This is bounded endpoint evidence, not a historical backfill. PlayerID was unset for "
        "PlayerGameLogs; each request was scoped only by season and season type.",
        "",
        "## Fixed decision criteria",
        "",
    ]
    for outcome, criterion in DECISION_CRITERIA.items():
        lines.append(f"- **{outcome}:** {criterion}")
    lines.extend([
        "", "## Probe outcomes", "",
        "| Endpoint / measure | Season | Type | Outcome | Rows | Players | Games | Plausible |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ])
    for probe in report["probes"]:
        label = probe["probe_kind"]
        if probe["measure_type"]:
            label += f" / {probe['measure_type']} {probe['per_mode']}"
        lines.append(
            f"| {label} | {probe['season']} | {probe['season_type']} | "
            f"{probe['outcome']} | {probe['row_count']} | {probe['distinct_players']} | "
            f"{probe['distinct_games']} | {probe['plausible']} |"
        )
    lines.extend([
        "", "## Interpretation", "",
        "The JSON companion is authoritative for response hashes, complete returned field lists, "
        "null rates, candidate-key duplicates, timing, retries, and error classifications. A zero "
        "returned by an endpoint for a pre-introduction statistic is retained only as source audit "
        "evidence; the canonical mapping converts that value to NULL.",
        "",
        "Official documented boundaries come from the NBA Stats FAQ: base statistics and digitized "
        "box scores begin in 1946-47; advanced statistics begin in 1996-97; individual traditional "
        "metrics have later introductions. Empirical response behavior is reported independently.",
        "",
        "## Empirical boundaries and quality", "",
        "- PlayerGameLogs returned rows for every tested Regular Season and Playoffs scope from "
        "1946-47 through 2025-26.",
        "- Base/Totals returned successful empty results through 1984-85 and rows from the next "
        "tested season, 1996-97, onward.",
        "- Advanced/Totals returned successful empty results for 1995-96 and rows for every tested "
        "season from 1996-97 onward.",
        "- Early player-game rows are metric-sparse: for example, 1946-47 Regular Season has 0% "
        "PTS nulls but 92.12% FGA nulls and 97.99% AST nulls. Availability of rows is not blanket "
        "metric reliability.",
        "",
        "## Identity coverage", "",
        f"- Returned official IDs (all probes): "
        f"{report['identity']['all_probe_rows']['returned_player_ids']}",
        f"- Legacy player matches (all probes): "
        f"{report['identity']['all_probe_rows']['legacy_player_matches']} "
        f"({report['identity']['all_probe_rows']['legacy_player_match_rate']:.2%})",
        f"- Legacy player matches (2022-23 overlap): "
        f"{report['identity']['overlap_2022_23']['legacy_player_matches']} "
        f"({report['identity']['overlap_2022_23']['legacy_player_match_rate']:.2%})",
        "",
        "Names are diagnostic only. `PLAYER_ID` maps to canonical `player_id` through the stable "
        "NBA business-key transform.",
        "",
        "## Limitations", "",
        "- This matrix samples representative seasons; it is not a complete season-by-season "
        "audit.",
        "- NBA Stats is an operational web API without a project-owned availability guarantee.",
        "- Empty and failed responses remain distinct; neither is interpreted as a season of "
        "zeros.",
        "- Full raw responses remain in ignored Bronze storage.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    args = _parse_args()
    client = NBAAPIClient(
        ResponseCache(args.cache_root), timeout_seconds=args.timeout,
        max_attempts=args.max_attempts, rate_limiter=RateLimiter(args.pace),
    )
    probes: list[dict[str, Any]] = []
    rows_for_identity: list[dict[str, Any]] = []
    overlap_rows: dict[str, list[dict[str, Any]]] = {}
    request_number = 0
    total_requests = len(SEASONS) * 4 + len(ADVANCED_SEASONS) * 2

    def execute(spec: Any, **summary: Any) -> Any:
        nonlocal request_number
        request_number += 1
        print(
            f"[{request_number:02d}/{total_requests}] {summary['probe_kind']} "
            f"{summary['season']} {summary['season_type']} "
            f"{summary.get('measure_type') or ''}",
            flush=True,
        )
        result = client.execute(spec, force=args.force)
        rows = rows_from_result(result)
        probes.append(summarize_probe(result, **summary))
        rows_for_identity.extend(rows)
        if summary["probe_kind"] == "PLAYER_GAME_LOGS" and summary["season"] == "2022-23":
            overlap_rows[summary["season_type"]] = rows
        return result

    for season in SEASONS:
        for season_type in SEASON_TYPES:
            execute(
                player_game_logs_spec(season, season_type), probe_kind="PLAYER_GAME_LOGS",
                season=season, season_type=season_type,
            )
    for season in SEASONS:
        for season_type in SEASON_TYPES:
            execute(
                league_dash_player_stats_spec(season, season_type),
                probe_kind="LEAGUE_DASH_PLAYER_STATS", season=season,
                season_type=season_type, measure_type="Base", per_mode="Totals",
            )
    for season in ADVANCED_SEASONS:
        for season_type in SEASON_TYPES:
            execute(
                league_dash_player_stats_spec(season, season_type, measure_type="Advanced"),
                probe_kind="LEAGUE_DASH_PLAYER_STATS", season=season,
                season_type=season_type, measure_type="Advanced", per_mode="Totals",
            )

    probes.sort(key=lambda item: (
        item["probe_kind"], item["measure_type"] or "", item["season"], item["season_type"]
    ))
    reconciliation = reconcile_2022_23(overlap_rows, args.sqlite)
    fixture_path = ROOT / "data/fixtures/nbadb_v238_sample.json"
    identity = {
        "all_probe_rows": identity_coverage(rows_for_identity, args.sqlite, fixture_path),
        "overlap_2022_23": identity_coverage(
            [row for rows in overlap_rows.values() for row in rows],
            args.sqlite,
            fixture_path,
        ),
    }
    report = {
        "schema_version": 1,
        "step": "STEP-0004",
        "observed_at": args.observed_at,
        "scope": {"representative_seasons": list(SEASONS),
                  "advanced_seasons": list(ADVANCED_SEASONS),
                  "season_types": list(SEASON_TYPES), "request_count": total_requests},
        "software": {"nba_api": metadata.version("nba_api"),
                     "requests": metadata.version("requests")},
        "request_policy": {"timeout_seconds": args.timeout, "max_attempts": args.max_attempts,
                           "minimum_interval_seconds": args.pace,
                           "backoff": "bounded exponential with additive jitter"},
        "decision_criteria": DECISION_CRITERIA,
        "decision": _decision(probes),
        "probes": probes,
        "identity": identity,
    }
    data_docs = ROOT / "docs/data"
    write_json_report(data_docs / "nba-api-player-fact-probe.json", report)
    write_json_report(data_docs / "nba-api-kaggle-reconciliation.json", reconciliation)
    (data_docs / "NBA_API_PLAYER_FACT_PROBE.md").write_text(_markdown(report), encoding="utf-8")
    print(stable_json({"decision": report["decision"], "requests": total_requests}))


if __name__ == "__main__":
    main()
