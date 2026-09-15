#!/usr/bin/env python3
"""Run the STEP-0015F factual historical player-season recovery audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from goatlab.data.canonical import canonical_id, parse_season_label
from goatlab.data.historical_recovery import (
    HISTORICAL_RECOVERY_VERSION,
    INTRODUCTION_SEASONS,
    MissingReason,
    canonical_regular_season_rows,
    missing_reason,
    named_result_rows,
    player_career_stats_spec,
    safe_percentage,
    safe_rate,
    true_shooting_pct,
)
from goatlab.data.nba_api_client import (
    NBAAPIClient,
    RateLimiter,
    RequestOutcome,
    ResponseCache,
)
from goatlab.data.nba_api_probe import result_rows
from goatlab.rankings.dimension_scores import weighted_observed
from goatlab.rankings.player_season_value import evidence_regime
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_historical_bridge import bridge_validation, defensive_audit
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet
from pipelines.rankings.audit_player_season_value import (
    build_candidates,
    career_counterfactuals,
    compare_scores,
    season_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ID = "GOATLAB-HIST-V1"
AUDIT_VERSION = "goatlab-historical-data-recovery-audit-v1"
STEP_E_FINGERPRINT = "731130b7fffd53ff084321b78175c7651f7c04387d9d574f5add205428bcbf63"
RUN_AT_DEFAULT = "2026-09-14T20:00:00Z"
RECOVERY_FIELDS = {
    "games_played": "GP",
    "minutes_total": "MIN",
    "points_total": "PTS",
    "fgm_total": "FGM",
    "fga_total": "FGA",
    "ftm_total": "FTM",
    "fta_total": "FTA",
    "oreb_total": "OREB",
    "dreb_total": "DREB",
    "rebounds_total": "REB",
    "assists_total": "AST",
    "steals_total": "STL",
    "blocks_total": "BLK",
    "turnovers_total": "TOV",
    "personal_fouls_total": "PF",
}
CASE_NAMES = (
    "Bill Russell",
    "Wilt Chamberlain",
    "Oscar Robertson",
    "Bob Pettit",
    "George Mikan",
    "Elgin Baylor",
    "Jerry West",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-partial-cache", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--minimum-interval", type=float, default=0.75)
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--bronze-root", type=Path, default=ROOT / "data/bronze/nba_api")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument("--legacy-db", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    return parser.parse_args()


def _verify_inputs(docs_root: Path) -> dict[str, str]:
    bridge = cast(
        dict[str, Any],
        json.loads((docs_root / "historical-evidence-bridge-summary.json").read_text()),
    )
    if bridge.get("output_fingerprint") != STEP_E_FINGERPRINT:
        raise ValueError("STEP-0015E fingerprint mismatch")
    corpus = cast(
        dict[str, Any],
        json.loads((docs_root / "historical-corpus-v1-manifest.json").read_text()),
    )
    corpus_fingerprint = str(
        corpus.get("corpus_fingerprint") or corpus.get("aggregate_fingerprint")
    )
    if corpus_fingerprint != "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c":
        raise ValueError("historical corpus fingerprint mismatch")
    return {
        "step_0015e": STEP_E_FINGERPRINT,
        "corpus": corpus_fingerprint,
        "constitution": file_hash(ROOT / "docs/constitution/GOATLAB_V1_CONSTITUTION.md"),
    }


def _identity_map(legacy_db: Path, docs_root: Path) -> dict[str, dict[str, str]]:
    connection = sqlite3.connect(legacy_db)
    try:
        rows = connection.execute("SELECT id, full_name FROM player").fetchall()
    finally:
        connection.close()
    output = {
        canonical_id("player", "nba", str(nba_id)): {
            "nba_player_id": str(nba_id),
            "player_name": str(name),
        }
        for nba_id, name in rows
    }
    report = json.loads((docs_root / "full-identity-reconciliation.json").read_text())
    for row in report["official_source_only_records"]:
        output[str(row["player_id"])] = {
            "nba_player_id": str(row["nba_player_id"]),
            "player_name": str(row["diagnostic_name"]),
        }
    return output


def _original_missingness(rows: list[dict[str, Any]]) -> dict[str, int]:
    early = [row for row in rows if row["evidence_regime"] == "EARLY_LIMITED"]
    result = {
        "early_limited_player_seasons": len(early),
        "missing_apg": sum(row.get("apg") is None for row in early),
        "missing_ts": sum(row.get("ts_pct") is None for row in early),
        "missing_rebound_action": sum(
            row.get("role_aware_actions") is None and row.get("action_value") is None
            for row in early
        ),
        "missing_presence": sum(row.get("observed_presence") is None for row in early),
        "ppg_team_only": sum(
            row.get("ppg") is not None
            and row.get("team_suppression") is not None
            and all(row.get(field) is None for field in ("ts_pct", "apg", "rpg", "spg", "bpg"))
            for row in early
        ),
    }
    expected = {
        "early_limited_player_seasons": 5881,
        "missing_apg": 5863,
        "missing_ts": 5321,
        "missing_rebound_action": 5242,
        "missing_presence": 2074,
        "ppg_team_only": 4311,
    }
    if result != expected:
        raise ValueError(f"STEP-0015E missingness mismatch: {result}")
    return result


def _acquire(
    player_ids: list[str], args: argparse.Namespace
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    cache = ResponseCache(args.bronze_root)
    client = NBAAPIClient(
        cache,
        timeout_seconds=30.0,
        max_attempts=5,
        backoff_base_seconds=2.0,
        backoff_cap_seconds=16.0,
        rate_limiter=RateLimiter(args.minimum_interval),
    )
    output: dict[str, list[dict[str, Any]]] = {}
    states: Counter[str] = Counter()
    fingerprints: list[str] = []
    network_requests = retries = 0
    for index, nba_id in enumerate(player_ids, start=1):
        spec = player_career_stats_spec(nba_id)
        cached = cache.load(spec)
        if cached is None and not args.allow_network:
            if args.allow_partial_cache:
                states["PENDING"] += 1
                output[nba_id] = []
                continue
            raise RuntimeError(f"cache miss for PlayerCareerStats PlayerID={nba_id}")
        result = client.execute(spec)
        network_requests += int(not result.from_cache)
        retries += result.retry_count
        states[result.outcome.value] += 1
        if result.response_sha256:
            fingerprints.append(result.response_sha256)
        if result.outcome is not RequestOutcome.SUCCESS_WITH_ROWS:
            output[nba_id] = []
            continue
        raw = named_result_rows(result.payload, "SeasonTotalsRegularSeason")
        output[nba_id] = canonical_regular_season_rows(raw, nba_player_id=nba_id)
        if index % 50 == 0 or index == len(player_ids):
            print(f"historical recovery: {index}/{len(player_ids)} players")
    manifest = {
        "players_requested": len(player_ids),
        "request_states": dict(sorted(states.items())),
        "network_requests": network_requests,
        "cache_reuses": len(player_ids) - network_requests,
        "retries": retries,
        "response_fingerprint": hashlib.sha256("".join(sorted(fingerprints)).encode()).hexdigest(),
    }
    return output, manifest


def _silver_total_rows(silver_root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (str(row["player_id"]), int(row["season_id"])): row
        for row in read_rows(silver_root / "player_season_stats")
        if row.get("season_type") == "REGULAR" and row.get("row_scope") == "TOTAL"
    }


def _source_index(
    acquired: dict[str, list[dict[str, Any]]], identity: dict[str, dict[str, str]]
) -> dict[tuple[str, int], dict[str, Any]]:
    reverse = {value["nba_player_id"]: player_id for player_id, value in identity.items()}
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for nba_id, rows in acquired.items():
        player_id = reverse[nba_id]
        for row in rows:
            season_id = parse_season_label(str(row["SEASON_ID"]))
            key = (player_id, season_id)
            if key in output:
                raise ValueError(f"duplicate source season: {key}")
            output[key] = row
    return output


def _league_leaders_per_game_index(
    bronze_root: Path,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Load already-cached official per-game facts without converting them to totals."""
    output: dict[tuple[str, int], dict[str, Any]] = {}
    directory = bronze_root / "leagueleaders"
    for metadata_path in sorted(directory.glob("*.meta.json")):
        metadata = json.loads(metadata_path.read_text())
        parameters = metadata["request_contract"]["parameters"]
        if (
            metadata.get("outcome") != RequestOutcome.SUCCESS_WITH_ROWS.value
            or parameters.get("PerMode") != "PerGame"
            or parameters.get("StatCategory") != "PTS"
        ):
            continue
        raw_path = directory / metadata_path.name.removesuffix(".meta.json")
        raw_path = raw_path.with_suffix(".json")
        payload = json.loads(raw_path.read_text())
        _, rows = result_rows(payload)
        season_id = parse_season_label(str(parameters["Season"]))
        for row in rows:
            player_id = canonical_id("player", "nba", str(row["PLAYER_ID"]))
            key = (player_id, season_id)
            if key in output:
                raise ValueError(f"duplicate cached LeagueLeaders player-season: {key}")
            output[key] = row
    return output


def _player_game_aggregation_audit(
    silver_root: Path,
    source: dict[tuple[str, int], dict[str, Any]],
    current: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    """Test exact recovery from existing game rows without accepting sparse partial sums."""
    mappings = {
        "MIN": ("minutes", "minutes_total"),
        "PTS": ("points", "points_total"),
        "FGM": ("fgm", "fgm_total"),
        "FGA": ("fga", "fga_total"),
        "FTM": ("ftm", "ftm_total"),
        "FTA": ("fta", "fta_total"),
        "OREB": ("oreb", "oreb_total"),
        "DREB": ("dreb", "dreb_total"),
        "REB": ("rebounds", "rebounds_total"),
        "AST": ("assists", "assists_total"),
        "STL": ("steals", "steals_total"),
        "BLK": ("blocks", "blocks_total"),
        "TOV": ("turnovers", "turnovers_total"),
        "PF": ("personal_fouls", "personal_fouls_total"),
    }
    values: dict[tuple[str, int], dict[str, list[float | None]]] = defaultdict(
        lambda: defaultdict(list)
    )
    games: dict[tuple[str, int], set[str]] = defaultdict(set)
    for path in sorted(
        (silver_root / "player_game_stats").glob("season=*/season_type=REGULAR/*.parquet")
    ):
        season = int(path.parent.parent.name.split("=", 1)[1])
        if season > 1995:
            continue
        columns = ["player_id", "game_id", *(field for field, _ in mappings.values())]
        for row in pq.read_table(path, columns=columns).to_pylist():
            key = (str(row["player_id"]), season)
            if key not in source:
                continue
            games[key].add(str(row["game_id"]))
            for source_field, (game_field, _) in mappings.items():
                value = row.get(game_field)
                values[key][source_field].append(float(value) if value is not None else None)
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)
    difference_sums: dict[str, float] = defaultdict(float)
    difference_maxima: dict[str, float] = defaultdict(float)
    compared: Counter[str] = Counter()
    pipeline_bug_examples: list[dict[str, Any]] = []
    mismatch_examples: list[dict[str, Any]] = []
    for key, source_row in sorted(source.items()):
        if key[1] > 1995 or key not in values:
            continue
        source_gp = source_row.get("GP")
        gp_match = source_gp is not None and len(games[key]) == int(source_gp)
        if source_gp is not None:
            gp_difference = abs(len(games[key]) - int(source_gp))
            compared["GP"] += 1
            difference_sums["GP"] += gp_difference
            difference_maxima["GP"] = max(difference_maxima["GP"], gp_difference)
            field_counts["GP"]["EXACT_MATCH" if gp_difference == 0 else "SOURCE_CONFLICT"] += 1
        for source_field, (_, canonical_total) in mappings.items():
            if key[1] < INTRODUCTION_SEASONS[source_field]:
                continue
            observations = values[key][source_field]
            if not gp_match or not observations or any(value is None for value in observations):
                field_counts[source_field]["INCOMPLETE_GAME_EVIDENCE"] += 1
                continue
            aggregate = sum(cast(float, value) for value in observations)
            official = source_row.get(source_field)
            if official is None:
                field_counts[source_field]["SOURCE_TOTAL_UNAVAILABLE"] += 1
                continue
            difference = abs(aggregate - float(official))
            difference_sums[source_field] += difference
            difference_maxima[source_field] = max(difference_maxima[source_field], difference)
            compared[source_field] += 1
            if difference == 0:
                field_counts[source_field]["EXACT_MATCH"] += 1
                if current.get(key, {}).get(canonical_total) is None:
                    field_counts[source_field]["PIPELINE_AGGREGATION_OMISSION"] += 1
                    if len(pipeline_bug_examples) < 25:
                        pipeline_bug_examples.append(
                            {
                                "player_id": key[0],
                                "season_id": key[1],
                                "field": source_field,
                                "game_aggregate": aggregate,
                                "career_total": official,
                            }
                        )
            elif difference <= 1.0:
                field_counts[source_field]["TOLERANCE_MATCH"] += 1
            else:
                field_counts[source_field]["SOURCE_CONFLICT"] += 1
                if len(mismatch_examples) < 25:
                    mismatch_examples.append(
                        {
                            "player_id": key[0],
                            "season_id": key[1],
                            "field": source_field,
                            "game_aggregate": aggregate,
                            "career_total": official,
                        }
                    )
    return {
        "method": (
            "sum only player-game groups with complete non-null observations and exact GP; "
            "never treat partial game rows as zero"
        ),
        "fields": {
            field: {
                **dict(sorted(counts.items())),
                "compared": compared[field],
                "mean_absolute_difference": (
                    difference_sums[field] / compared[field] if compared[field] else None
                ),
                "maximum_absolute_difference": difference_maxima[field],
            }
            for field, counts in sorted(field_counts.items())
        },
        "pipeline_aggregation_omission_count": sum(
            counts["PIPELINE_AGGREGATION_OMISSION"] for counts in field_counts.values()
        ),
        "pipeline_aggregation_omission_examples": pipeline_bug_examples,
        "source_conflict_count": sum(counts["SOURCE_CONFLICT"] for counts in field_counts.values()),
        "source_conflict_examples": mismatch_examples,
    }


def _recovered_facts(
    base_rows: list[dict[str, Any]],
    silver: dict[tuple[str, int], dict[str, Any]],
    source: dict[tuple[str, int], dict[str, Any]],
    league_leaders: dict[tuple[str, int], dict[str, Any]],
    identity: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    comparisons: Counter[str] = Counter()
    field_comparisons: dict[str, Counter[str]] = defaultdict(Counter)
    max_difference: dict[str, float] = defaultdict(float)
    sum_difference: dict[str, float] = defaultdict(float)
    compared_count: Counter[str] = Counter()
    for base in base_rows:
        player_id, season_id = str(base["player_id"]), int(base["season_id"])
        current = silver[(player_id, season_id)]
        recovered = source.get((player_id, season_id), {})
        per_game_source = league_leaders.get((player_id, season_id), {})
        values: dict[str, Any] = {}
        provenance: dict[str, str] = {}
        reasons: dict[str, str | None] = {}
        for canonical_field, source_field in RECOVERY_FIELDS.items():
            old, new = current.get(canonical_field), recovered.get(source_field)
            if season_id < INTRODUCTION_SEASONS[source_field]:
                values[canonical_field] = None
                provenance[canonical_field] = "UNAVAILABLE"
                reasons[canonical_field] = MissingReason.HISTORICALLY_NOT_RECORDED.value
                continue
            if old is not None and new is not None:
                difference = abs(float(old) - float(new))
                status = (
                    "EXACT_MATCH"
                    if difference == 0
                    else "TOLERANCE_MATCH"
                    if difference <= 1.0
                    else "SOURCE_CONFLICT"
                )
                comparisons[status] += 1
                field_comparisons[source_field][status] += 1
                max_difference[source_field] = max(max_difference[source_field], difference)
                sum_difference[source_field] += difference
                compared_count[source_field] += 1
            if new is not None and season_id < 1996:
                values[canonical_field] = new
                provenance[canonical_field] = "NBA_PLAYER_CAREER_STATS_TOTALS"
                reasons[canonical_field] = (
                    MissingReason.SOURCE_CONFLICT.value
                    if old is not None and float(old) != float(new)
                    else MissingReason.SOURCE_NOT_INGESTED.value
                    if old is None
                    else None
                )
            elif old is not None:
                values[canonical_field] = old
                provenance[canonical_field] = "GOATLAB_HIST_V1"
                reasons[canonical_field] = None
            elif new is not None:
                values[canonical_field] = new
                provenance[canonical_field] = "NBA_PLAYER_CAREER_STATS_TOTALS"
                reasons[canonical_field] = MissingReason.SOURCE_NOT_INGESTED.value
            else:
                values[canonical_field] = None
                provenance[canonical_field] = "UNAVAILABLE"
                reason = missing_reason(source_field, season_id, new)
                reasons[canonical_field] = reason.value if reason else None
        gp = values["games_played"]
        per_game_fields = {
            "minutes_per_game": ("minutes_total", "MIN"),
            "points_per_game": ("points_total", "PTS"),
            "rebounds_per_game": ("rebounds_total", "REB"),
            "assists_per_game": ("assists_total", "AST"),
            "steals_per_game": ("steals_total", "STL"),
            "blocks_per_game": ("blocks_total", "BLK"),
            "turnovers_per_game": ("turnovers_total", "TOV"),
        }
        for field, (total_field, source_field) in per_game_fields.items():
            direct = safe_rate(values[total_field], gp)
            league_value = per_game_source.get(source_field)
            use_league = season_id < 1996 and not recovered and league_value is not None
            values[field] = league_value if use_league else direct
            if values[field] is None:
                values[field] = league_value
            provenance[field] = (
                "NBA_LEAGUE_LEADERS_PER_GAME"
                if use_league
                else "DERIVED_FROM_OBSERVED_TOTALS"
                if direct is not None
                else "NBA_LEAGUE_LEADERS_PER_GAME"
                if values[field] is not None
                else "UNAVAILABLE"
            )
            if values[field] is None:
                total_reason = reasons.get(total_field)
                reasons[field] = total_reason or MissingReason.SOURCE_UNAVAILABLE.value
            else:
                reasons[field] = (
                    MissingReason.DERIVABLE_FROM_OBSERVED_FACTS.value
                    if direct is not None
                    else MissingReason.SOURCE_NOT_INGESTED.value
                )
        totals_fg_pct = safe_percentage(values["fgm_total"], values["fga_total"])
        totals_ft_pct = safe_percentage(values["ftm_total"], values["fta_total"])
        totals_ts = true_shooting_pct(
            values["points_total"], values["fga_total"], values["fta_total"]
        )
        values["fg_pct"] = (
            totals_fg_pct if totals_fg_pct is not None else per_game_source.get("FG_PCT")
        )
        values["ft_pct"] = (
            totals_ft_pct if totals_ft_pct is not None else per_game_source.get("FT_PCT")
        )
        values["true_shooting_pct"] = totals_ts
        if totals_ts is None:
            values["true_shooting_pct"] = true_shooting_pct(
                per_game_source.get("PTS"),
                per_game_source.get("FGA"),
                per_game_source.get("FTA"),
            )
        for field in ("fg_pct", "ft_pct", "true_shooting_pct"):
            provenance[field] = (
                "DERIVED_FROM_OBSERVED_TOTALS"
                if (field == "fg_pct" and totals_fg_pct is not None)
                or (field == "ft_pct" and totals_ft_pct is not None)
                or (field == "true_shooting_pct" and totals_ts is not None)
                else "NBA_LEAGUE_LEADERS_PER_GAME"
                if values[field] is not None
                else "UNAVAILABLE"
            )
            reasons[field] = (
                MissingReason.DERIVABLE_FROM_OBSERVED_FACTS.value
                if values[field] is not None
                else MissingReason.SOURCE_UNAVAILABLE.value
            )
        facts.append(
            {
                "player_id": player_id,
                "nba_player_id": identity[player_id]["nba_player_id"],
                "player_name": identity[player_id]["player_name"],
                "season_id": season_id,
                "season_type": "REGULAR",
                **values,
                "source_recovery_available": bool(recovered or per_game_source),
                "career_totals_source_available": bool(recovered),
                "league_leaders_source_available": bool(per_game_source),
                "field_provenance_json": json.dumps(provenance, sort_keys=True),
                "missingness_reason_json": json.dumps(reasons, sort_keys=True),
                "methodology_version": HISTORICAL_RECOVERY_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    report = {
        "comparisons": dict(sorted(comparisons.items())),
        "by_field": {
            field: {
                **dict(sorted(counts.items())),
                "compared": compared_count[field],
                "exact_match_rate": counts["EXACT_MATCH"] / compared_count[field],
                "tolerance_match_rate": counts["TOLERANCE_MATCH"] / compared_count[field],
                "disagreement_rate": counts["SOURCE_CONFLICT"] / compared_count[field],
                "mean_absolute_difference": sum_difference[field] / compared_count[field],
                "maximum_absolute_difference": max_difference[field],
            }
            for field, counts in sorted(field_comparisons.items())
        },
    }
    return facts, report


def _ts_validation(facts: list[dict[str, Any]], silver_root: Path) -> dict[str, float | int | str]:
    """Validate the standard totals-derived TS estimate against official advanced TS."""
    official = {
        (str(row["player_id"]), int(row["season_id"])): float(row["true_shooting_pct"])
        for row in read_rows(silver_root / "player_season_advanced")
        if row.get("season_type") == "REGULAR"
        and row.get("row_scope") == "TOTAL"
        and row.get("true_shooting_pct") is not None
    }
    differences = [
        abs(float(row["true_shooting_pct"]) - official[key])
        for row in facts
        if row.get("true_shooting_pct") is not None
        and (key := (str(row["player_id"]), int(row["season_id"]))) in official
    ]
    if not differences:
        raise ValueError("no official advanced TS overlap for validation")
    return {
        "formula": "PTS / (2 * (FGA + 0.44 * FTA))",
        "semantics": "standard estimate derived from observed factual totals",
        "official_advanced_overlap": len(differences),
        "mean_absolute_difference": sum(differences) / len(differences),
        "maximum_absolute_difference": max(differences),
        "within_source_rounding_0_0005": sum(value <= 0.0005000001 for value in differences),
        "historical_caution": (
            "The 0.44 factor is an estimate rather than a reconstructed possession count; "
            "historical free-throw rule changes remain a documented comparability limitation."
        ),
    }


def _midranks(rows: list[dict[str, Any]], raw_field: str) -> dict[tuple[str, int], float]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get(raw_field) is not None:
            groups[int(row["season_id"])].append(row)
    output: dict[tuple[str, int], float] = {}
    for season, members in groups.items():
        ordered = sorted(members, key=lambda row: (float(row[raw_field]), str(row["player_id"])))
        cursor = 0
        while cursor < len(ordered):
            end = cursor + 1
            while end < len(ordered) and ordered[end][raw_field] == ordered[cursor][raw_field]:
                end += 1
            percentile = ((cursor + 1 + end) / 2.0 - 1.0) / max(1, len(ordered) - 1)
            for row in ordered[cursor:end]:
                output[(str(row["player_id"]), season)] = percentile
            cursor = end
    return output


def _recovered_candidate_rows(
    base_rows: list[dict[str, Any]], facts: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    fact_index = {(str(row["player_id"]), int(row["season_id"])): row for row in facts}
    ranks = {
        "ppg": _midranks(facts, "points_per_game"),
        "ts_pct": _midranks(facts, "true_shooting_pct"),
        "apg": _midranks(facts, "assists_per_game"),
        "rpg": _midranks(facts, "rebounds_per_game"),
        "spg": _midranks(facts, "steals_per_game"),
        "bpg": _midranks(facts, "blocks_per_game"),
    }
    recovered_inputs: list[dict[str, Any]] = []
    for original in base_rows:
        row = dict(original)
        key = (str(row["player_id"]), int(row["season_id"]))
        fact = fact_index[key]
        for field in ranks:
            row[field] = ranks[field].get(key)
        action = weighted_observed(
            {field: row.get(field) for field in ("rpg", "spg", "bpg")},
            {"rpg": 0.50, "spg": 0.25, "bpg": 0.25},
        )
        row["action_value"] = action.value
        # Existing role-aware action evidence remains the richer observed channel. Newly recovered
        # total rebounds are kept as explicitly weaker total-rebound evidence.
        row["evidence_regime"] = evidence_regime(
            ts_available=row.get("ts_pct") is not None,
            creation_available=row.get("apg") is not None,
            rebound_available=row.get("rpg") is not None,
            steals_blocks_available=row.get("spg") is not None and row.get("bpg") is not None,
            role_actions_available=row.get("role_aware_actions") is not None,
            presence_available=row.get("observed_presence") is not None,
        )
        row["recovery_source_available"] = fact["source_recovery_available"]
        recovered_inputs.append(row)
    candidates, summary = build_candidates(recovered_inputs)
    return (
        [row for row in candidates if row["candidate"] == "D_REGIME_RELIABILITY"],
        summary["D_REGIME_RELIABILITY"],
        recovered_inputs,
    )


def _regimes(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["evidence_regime"])].append(row)
    return {
        name: {
            "player_seasons": len(members),
            "players": len({str(row["player_id"]) for row in members}),
            "first_season": min(int(row["season_id"]) for row in members),
            "last_season": max(int(row["season_id"]) for row in members),
        }
        for name, members in sorted(groups.items())
    }


def _availability_map(facts: list[dict[str, Any]]) -> dict[str, Any]:
    definitions = {
        "GP": ("games_played", "DIRECT"),
        "MIN": ("minutes_total", "DIRECT"),
        "PTS": ("points_total", "DIRECT"),
        "FGM": ("fgm_total", "DIRECT"),
        "FGA": ("fga_total", "DIRECT"),
        "FG_PCT": ("fg_pct", "DERIVED_EXACT_RATIO"),
        "FTM": ("ftm_total", "DIRECT"),
        "FTA": ("fta_total", "DIRECT"),
        "FT_PCT": ("ft_pct", "DERIVED_EXACT_RATIO"),
        "REB": ("rebounds_total", "DIRECT"),
        "OREB": ("oreb_total", "DIRECT"),
        "DREB": ("dreb_total", "DIRECT"),
        "AST": ("assists_total", "DIRECT"),
        "STL": ("steals_total", "DIRECT"),
        "BLK": ("blocks_total", "DIRECT"),
        "TOV": ("turnovers_total", "DIRECT"),
        "PF": ("personal_fouls_total", "DIRECT"),
        "TS": ("true_shooting_pct", "DERIVED_STANDARD_0_44_ESTIMATE"),
    }
    output: dict[str, Any] = {}
    for stat, (field, semantics) in definitions.items():
        observed = [row for row in facts if row.get(field) is not None]
        seasons = sorted({int(row["season_id"]) for row in observed})
        by_season: list[dict[str, Any]] = []
        for season_id in sorted({int(row["season_id"]) for row in facts}):
            members = [row for row in facts if int(row["season_id"]) == season_id]
            observed_members = [row for row in members if row.get(field) is not None]
            current = 0
            recovered = 0
            for row in observed_members:
                provenance = json.loads(str(row["field_provenance_json"]))
                source_field = {
                    "FG_PCT": "fg_pct",
                    "FT_PCT": "ft_pct",
                    "TS": "true_shooting_pct",
                }.get(stat, field)
                if provenance.get(source_field) == "GOATLAB_HIST_V1":
                    current += 1
                else:
                    recovered += 1
            introduction = INTRODUCTION_SEASONS.get(stat, 1946)
            by_season.append(
                {
                    "season_id": season_id,
                    "historical_status": (
                        MissingReason.HISTORICALLY_NOT_RECORDED.value
                        if season_id < introduction
                        else "APPLICABLE"
                    ),
                    "player_seasons": len(members),
                    "current_goatlab_observed": current,
                    "recovered_or_derived_observed": recovered,
                    "post_recovery_observed": len(observed_members),
                    "post_recovery_missing": len(members) - len(observed_members),
                }
            )
        output[stat] = {
            "first_officially_recorded_season": INTRODUCTION_SEASONS.get(stat, 1946),
            "first_observed_season": seasons[0] if seasons else None,
            "last_observed_season": seasons[-1] if seasons else None,
            "observed_player_seasons": len(observed),
            "continuity_gaps": [
                season for season in range(seasons[0], seasons[-1] + 1) if season not in seasons
            ]
            if seasons
            else [],
            "semantics": semantics,
            "source": "GOATLAB-HIST-V1 then official NBA PlayerCareerStats",
            "season_by_season": by_season,
        }
    return output


def _missing_reason_summary(facts: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in facts:
        reasons = json.loads(str(row["missingness_reason_json"]))
        for reason in reasons.values():
            if reason is not None:
                counts[str(reason)] += 1
    return {reason.value: counts[reason.value] for reason in MissingReason}


def _recovery_counts(
    base_rows: list[dict[str, Any]], recovered: list[dict[str, Any]]
) -> dict[str, int]:
    after = {(str(row["player_id"]), int(row["season_id"])): row for row in recovered}
    early = [row for row in base_rows if row["evidence_regime"] == "EARLY_LIMITED"]
    return {
        "apg_recovered": sum(
            row.get("apg") is None
            and after[(str(row["player_id"]), int(row["season_id"]))].get("apg") is not None
            for row in early
        ),
        "ts_recovered": sum(
            row.get("ts_pct") is None
            and after[(str(row["player_id"]), int(row["season_id"]))].get("ts_pct") is not None
            for row in early
        ),
        "rebound_action_recovered": sum(
            row.get("action_value") is None
            and after[(str(row["player_id"]), int(row["season_id"]))].get("actions") is not None
            for row in early
        ),
        "early_limited_remaining": sum(
            after[(str(row["player_id"]), int(row["season_id"]))]["evidence_regime"]
            == "EARLY_LIMITED"
            for row in early
        ),
    }


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    inputs = _verify_inputs(args.docs_root)
    base_rows, _ = season_inputs(args.gold_root)
    pre = _original_missingness(base_rows)
    identity = _identity_map(args.legacy_db, args.docs_root)
    source_scope = sorted(
        {str(row["player_id"]) for row in base_rows if int(row["season_id"]) < 1996}
    )
    nba_ids = sorted(identity[player_id]["nba_player_id"] for player_id in source_scope)
    acquired, current_acquisition = _acquire(nba_ids, args)
    acquisition_path = args.bronze_root / "historical-recovery-acquisition-manifest.json"
    if args.allow_network:
        stable_json(acquisition_path, current_acquisition)
        acquisition = current_acquisition
    elif args.allow_partial_cache:
        acquisition = current_acquisition
    else:
        if current_acquisition["network_requests"] != 0:
            raise ValueError("cache-only rebuild issued network requests")
        acquisition = cast(dict[str, Any], json.loads(acquisition_path.read_text()))
    source = _source_index(acquired, identity)
    league_leaders = _league_leaders_per_game_index(args.bronze_root)
    silver = _silver_total_rows(args.silver_root)
    game_aggregation = _player_game_aggregation_audit(args.silver_root, source, silver)
    facts, reconciliation = _recovered_facts(base_rows, silver, source, league_leaders, identity)
    ts_validation = _ts_validation(facts, args.silver_root)
    recovered, candidate_summary, recovered_inputs = _recovered_candidate_rows(base_rows, facts)
    counts = _recovery_counts(base_rows, recovered)
    _, recovered_defense_state = defensive_audit(recovered_inputs)
    masking_after, _ = bridge_validation(recovered_defense_state)

    original_candidate = read_rows(
        args.gold_root / "historical_bridge_audit/candidate-d-reconstruction.parquet"
    )
    before_regimes = _regimes(original_candidate)
    after_regimes = _regimes(recovered)
    dimensions: dict[str, dict[str, float | None]] = defaultdict(dict)
    names: dict[str, str] = {}
    for row in read_rows(args.gold_root / "player_dimension_scores/part-00000.parquet"):
        player_id = str(row["player_id"])
        names[player_id] = str(row["display_name"])
        dimensions[str(row["dimension"])][player_id] = row.get("score")
    players = sorted(names)
    reference = {
        str(row["player_id"])
        for row in read_rows(
            args.gold_root / "peak_forensic_audit/v1-player-peak-decomposition.parquet"
        )
        if row.get("raw_peak") is not None
    }
    peak, longevity, peak_details, longevity_details = career_counterfactuals(
        recovered, "D_REGIME_RELIABILITY", players, reference
    )
    peak_comparison = compare_scores(peak, dimensions["PEAK"])
    longevity_comparison = compare_scores(longevity, dimensions["LONGEVITY"])
    old_peak = json.loads(
        (args.docs_root / "player-season-value-peak-counterfactual.json").read_text()
    )
    old_longevity = json.loads(
        (args.docs_root / "player-season-value-longevity-counterfactual.json").read_text()
    )

    recovered_index = {(str(row["player_id"]), int(row["season_id"])): row for row in recovered}
    fact_index = {(str(row["player_id"]), int(row["season_id"])): row for row in facts}
    case_rows: list[dict[str, Any]] = []
    for name in CASE_NAMES:
        player_id = next((key for key, value in names.items() if value == name), None)
        if player_id is None:
            continue
        seasons = [row for row in base_rows if row["player_id"] == player_id]
        for old in seasons:
            new = recovered_index[(player_id, int(old["season_id"]))]
            recovered_fact = fact_index[(player_id, int(old["season_id"]))]
            if (
                old["evidence_regime"] == new["evidence_regime"]
                and not recovered_fact["source_recovery_available"]
            ):
                continue
            case_rows.append(
                {
                    "player_id": player_id,
                    "player_name": name,
                    "season_id": int(old["season_id"]),
                    "old_regime": old["evidence_regime"],
                    "new_regime": new["evidence_regime"],
                    "recovered_apg": new.get("apg"),
                    "recovered_ts": new.get("ts_pct"),
                    "recovered_rpg": new.get("rpg"),
                    "remaining_presence": new.get("presence"),
                    "player_season_value": new.get("player_season_value_percentile"),
                    "confidence": new.get("confidence"),
                    "peak_eligible": peak[player_id] is not None,
                    "longevity_eligible": longevity[player_id] is not None,
                }
            )

    availability = _availability_map(facts)
    missing_reason_counts = _missing_reason_summary(facts)
    source_complete = not any(
        acquisition["request_states"].get(status, 0) for status in ("PENDING", "RETRYABLE_FAILURE")
    )
    verdict = (
        "MATERIAL_RECOVERY"
        if counts["early_limited_remaining"] < pre["early_limited_player_seasons"] // 2
        else "LIMITED_RECOVERY"
    )
    recommendation = (
        "RERUN_MEASUREMENT_WITH_RECOVERED_FACTS"
        if verdict == "MATERIAL_RECOVERY" and source_complete
        else "FURTHER_SOURCE_RESEARCH_REQUIRED"
    )
    output_root = args.gold_root / "historical_data_recovery_audit"
    manifests = [
        write_parquet(
            facts,
            args.silver_root / "historical_player_season_facts_v2_research/part-00000.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            recovered,
            output_root / "candidate-d-recovered-facts.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            case_rows,
            output_root / "early-era-case-studies.parquet",
            ("player_name", "season_id"),
        ),
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "v1_peak": dimensions["PEAK"][player_id],
                    "recovered_peak": peak[player_id],
                    **peak_details[player_id],
                }
                for player_id in players
            ],
            output_root / "peak-coverage-impact.parquet",
            ("player_id",),
        ),
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "v1_longevity": dimensions["LONGEVITY"][player_id],
                    "recovered_longevity": longevity[player_id],
                    **longevity_details[player_id],
                }
                for player_id in players
            ],
            output_root / "longevity-coverage-impact.parquet",
            ("player_id",),
        ),
    ]
    crosswalk = [{"player_id": player_id, **identity[player_id]} for player_id in source_scope]
    reports: dict[str, dict[str, Any]] = {
        "historical-stat-availability-map.json": {"statistics": availability},
        "historical-current-corpus-field-audit.json": {
            "original_missingness": pre,
            "finding": (
                "Early PlayerGameLogs rows exist but several recorded fields are sparse; "
                "the official player-scoped career totals endpoint contains season totals."
            ),
            "player_game_aggregation": game_aggregation,
            "pipeline_bug_count": game_aggregation["pipeline_aggregation_omission_count"],
            "source_not_ingested": True,
        },
        "historical-source-reconciliation.json": reconciliation,
        "historical-external-source-inventory.json": {
            "sources": [
                {
                    "name": "NBA Stats PlayerGameLogs",
                    "role": "frozen primary player-game source",
                    "coverage": "1946-47 through 2025-26; metric sparsity is empirical",
                    "provenance": "GOATLAB-HIST-V1",
                },
                {
                    "name": "NBA Stats PlayerCareerStats",
                    "role": "supplemental official season-total recovery",
                    "endpoint": "https://stats.nba.com/stats/playercareerstats",
                    "access_date": "2026-09-14",
                    "acquisition": (
                        "official PLAYER_ID scoped, Totals mode, cached and retry bounded"
                    ),
                    "terms": "NBA.com Terms of Use; internal research cache remains Git-ignored",
                    "terms_url": "https://www.nba.com/termsofuse",
                },
                {
                    "name": "NBA Stats LeagueLeaders",
                    "role": "cached source-direct per-game fallback and reconciliation evidence",
                    "coverage": "empirically populated from 1951-52 for PTS/REB/AST scopes",
                    "constraint": (
                        "rounded per-game facts are never multiplied into invented totals"
                    ),
                    "provenance": "STEP-0011 cache",
                },
                {
                    "name": "NBA Stats FAQ",
                    "role": "official statistic-introduction validation",
                    "url": "https://www.nba.com/stats/help/faq",
                    "access_date": "2026-09-14",
                },
                {
                    "name": "NBA 1946-47 season review",
                    "role": "official inaugural-season assists validation",
                    "url": "https://www.nba.com/news/history-season-review-1946-47",
                    "finding": "official review identifies the 1946-47 assists-per-game leader",
                    "access_date": "2026-09-14",
                },
                {
                    "name": "nbadb/Kaggle v238 legacy snapshot",
                    "role": "identity and game reference only",
                    "finding": "physical 16-table bundle has no player box-score or season totals",
                },
            ],
            "third_party_player_stat_source_ingested": False,
            "source_precedence_changed": True,
            "source_precedence": (
                "Official PlayerCareerStats totals supersede empirically incomplete "
                "PlayerGameLogs aggregates before 1996 in the research artifact only; "
                "GOATLAB-HIST-V1 and all published V1 outputs remain frozen."
            ),
            "true_shooting_validation": ts_validation,
            "missingness_reason_counts": missing_reason_counts,
        },
        "historical-recovery-identity-crosswalk.json": {
            "business_key": "official NBA PLAYER_ID",
            "rows": len(crosswalk),
            "unresolved": 0,
            "crosswalk": crosswalk,
        },
        "historical-evidence-regimes-v2.json": {
            "before": before_regimes,
            "after": after_regimes,
        },
        "historical-recovery-impact.json": {
            "pre_recovery": pre,
            "recovered": counts,
            "candidate_d_before": {"scored_player_seasons": 16576, "players": 2950},
            "candidate_d_after": candidate_summary,
            "peak_before": old_peak["comparison"],
            "peak_after": peak_comparison,
            "longevity_before": old_longevity["comparison"],
            "longevity_after": longevity_comparison,
            "masking_before": json.loads(
                (args.docs_root / "historical-mask-validation.json").read_text()
            ),
            "masking_after": masking_after,
            "masking_interpretation": (
                "Recovered observations replace bridge predictions. Artificial masks remain "
                "diagnostic tests of information removal, not recovered facts."
            ),
        },
        "historical-recovery-acquisition-summary.json": acquisition,
        "historical-recovery-case-studies.json": {"rows": case_rows},
        "historical-recovery-verdict.json": {
            "step_result": "PASS" if source_complete else "PARTIAL",
            "recovery_verdict": verdict,
            "recommendation": recommendation,
            "frozen_outputs_modified": False,
            "model_imputation_used": False,
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        document = {
            "step": "STEP-0015F",
            "audit_methodology_version": AUDIT_VERSION,
            "facts_methodology_version": HISTORICAL_RECOVERY_VERSION,
            "input_fingerprints": inputs,
            **payload,
        }
        stable_json(args.docs_root / name, document)
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": inputs,
                "acquisition": acquisition,
                "outputs": manifests,
                "reports": report_hashes,
                "verdict": verdict,
                "recommendation": recommendation,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015F",
        "result": "PASS" if source_complete else "PARTIAL",
        "recovery_verdict": verdict,
        "recommendation": recommendation,
        "audit_methodology_version": AUDIT_VERSION,
        "facts_methodology_version": HISTORICAL_RECOVERY_VERSION,
        "input_fingerprints": inputs,
        "original_missingness": pre,
        "recovery_counts": counts,
        "acquisition": acquisition,
        "player_game_aggregation": game_aggregation,
        "reconciliation": reconciliation,
        "true_shooting_validation": ts_validation,
        "missingness_reason_counts": missing_reason_counts,
        "regimes_before": before_regimes,
        "regimes_after": after_regimes,
        "candidate_d_before": {"scored_player_seasons": 16576, "players": 2950},
        "candidate_d_after": candidate_summary,
        "masking_after": masking_after,
        "peak_before": old_peak["comparison"],
        "peak_after": peak_comparison,
        "longevity_before": old_longevity["comparison"],
        "longevity_after": longevity_comparison,
        "outputs": manifests,
        "output_fingerprint": fingerprint,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint,
    }
    stable_json(args.docs_root / "historical-data-recovery-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, observed {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
