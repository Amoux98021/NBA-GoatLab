#!/usr/bin/env python3
"""Run the offline STEP-0015A Defense forensic audit.

The frozen V1 artifacts are inputs and are never rewritten.  Experimental audit
and counterfactual outputs are written under dedicated Gold directories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.defense_forensics import (
    DEFENSE_AUDIT_METHODOLOGY_VERSION,
    DEFENSE_V2_CANDIDATE_VERSION,
    broad_role,
    current_action_context,
    defense_candidate,
    defensive_presence_estimate,
    role_aware_action_context,
)
from goatlab.rankings.dimension_scores import midrank_percentile_scores

ROOT = Path(__file__).resolve().parents[2]
DIMENSION_VERSION = "goatlab-v1-dimension-scores-v1"
OVERALL_VERSION = "goatlab-v1-overall-v1"
DIMENSION_FINGERPRINT = "0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a"
OVERALL_FINGERPRINT = "02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa"
CORPUS_ID = "GOATLAB-HIST-V1"
V1_WEIGHTS = {
    "PEAK": 0.17,
    "LONGEVITY": 0.14,
    "OFFENSE": 0.16,
    "DEFENSE": 0.14,
    "PLAYOFFS": 0.18,
    "ACCOLADES": 0.10,
    "WINNING": 0.11,
}
DIAGNOSTIC_NAMES = (
    "Stephen Curry",
    "Kobe Bryant",
    "Rudy Gobert",
    "Michael Jordan",
    "Scottie Pippen",
    "Kawhi Leonard",
    "LeBron James",
    "Tim Duncan",
    "Kevin Garnett",
    "Hakeem Olajuwon",
    "Bill Russell",
    "Draymond Green",
    "Ben Wallace",
    "Gary Payton",
    "Sidney Moncrief",
    "Dennis Rodman",
    "David Robinson",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument("--legacy-db", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    return parser.parse_args()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_rows(path: Path, columns: list[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    parquets = [path] if path.is_file() else sorted(path.rglob("*.parquet"))
    for parquet in parquets:
        rows.extend(pq.ParquetFile(parquet).read(columns=columns).to_pylist())
    return rows


def write_parquet(rows: list[dict[str, Any]], path: Path, keys: tuple[str, ...]) -> dict[str, Any]:
    rows.sort(key=lambda row: tuple(str(row.get(key) or "") for key in keys))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=9,
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
    )
    temporary.replace(path)
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": table.num_rows,
        "size_bytes": path.stat().st_size,
        "sha256": file_hash(path),
    }


def verify_frozen_inputs(docs_root: Path) -> dict[str, str]:
    dimension = json.loads((docs_root / "dimension-score-summary.json").read_text())
    overall = json.loads((docs_root / "overall-ranking-summary.json").read_text())
    if (
        dimension["methodology_version"] != DIMENSION_VERSION
        or dimension["output_fingerprint"] != DIMENSION_FINGERPRINT
    ):
        raise ValueError("frozen STEP-0014 input changed")
    if (
        overall["methodology_version"] != OVERALL_VERSION
        or overall["output_fingerprint"] != OVERALL_FINGERPRINT
    ):
        raise ValueError("frozen STEP-0015 input changed")
    return {"dimension": DIMENSION_FINGERPRINT, "overall": OVERALL_FINGERPRINT}


def normalized_seasons(gold_root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    wanted = {"ppg", "rpg", "spg", "bpg", "apg", "ts_pct"}
    output: dict[tuple[str, int], dict[str, Any]] = defaultdict(dict)
    columns = [
        "player_id",
        "season_id",
        "season_type",
        "metric_name",
        "raw_value",
        "percentile",
        "coverage_status",
        "qualification_status",
        "sample_size_games",
    ]
    for row in read_rows(gold_root / "player_season_feature_long", columns):
        if row["season_type"] != "REGULAR" or row["metric_name"] not in wanted:
            continue
        if row["qualification_status"] != "QUALIFIED" or not str(row["coverage_status"]).startswith(
            "AVAILABLE"
        ):
            continue
        key = (str(row["player_id"]), int(row["season_id"]))
        metric = str(row["metric_name"])
        output[key][f"{metric}_raw"] = row["raw_value"]
        output[key][f"{metric}_percentile"] = row["percentile"]
        output[key]["games"] = int(row["sample_size_games"])
    return dict(output)


def reference_population(
    gold_root: Path, seasons: dict[tuple[str, int], dict[str, Any]]
) -> set[str]:
    reference: set[str] = set()
    for row in read_rows(gold_root / "player_career_summary"):
        player_id = str(row["player_id"])
        first = int(row["regular_first_season"] or 1946)
        last = int(row["regular_last_season"] or 1945)
        elite = any(
            any(
                float(seasons.get((player_id, season), {}).get(f"{metric}_percentile") or -1.0)
                >= 0.90
                for metric in ("ppg", "rpg", "apg", "ts_pct")
            )
            for season in range(first, last + 1)
        )
        if int(row["regular_qualified_seasons"]) >= 3 or elite:
            reference.add(player_id)
    return reference


def team_suppression(
    silver_root: Path, gold_root: Path
) -> tuple[dict[tuple[str, int], float], dict[tuple[str, int, str], float]]:
    by_season: dict[int, dict[str, float]] = defaultdict(dict)
    for row in read_rows(silver_root / "team_season_results"):
        if int(row["regular_games"]) > 0 and row["regular_points_against"] is not None:
            by_season[int(row["season_id"])][str(row["team_id"])] = -float(
                row["regular_points_against"]
            ) / int(row["regular_games"])
    team_scores: dict[tuple[int, str], float] = {}
    for season, values in by_season.items():
        scaled = midrank_percentile_scores(values, set(values))
        team_scores.update(
            {
                (season, team): float(value) / 100
                for team, value in scaled.items()
                if value is not None
            }
        )
    affiliated: dict[tuple[str, int], list[tuple[float, int]]] = defaultdict(list)
    player_team: dict[tuple[str, int, str], float] = {}
    for row in read_rows(gold_root / "player_team_success_primitives"):
        games = int(row["regular_games"])
        key = (int(row["season_id"]), str(row["team_id"]))
        score = team_scores.get(key)
        if games > 0 and score is not None:
            player_id, season, team_id = str(row["player_id"]), key[0], key[1]
            affiliated[(player_id, season)].append((score, games))
            player_team[(player_id, season, team_id)] = score
    player_scores = {
        key: sum(value * games for value, games in rows) / sum(games for _, games in rows)
        for key, rows in affiliated.items()
    }
    return player_scores, player_team


def position_metadata(database: Path, scores: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nba_to_player = {
        str(row["nba_player_id"]): str(row["player_id"]) for row in scores if row["nba_player_id"]
    }
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT person_id, position, height FROM common_player_info ORDER BY person_id"
    ).fetchall()
    connection.close()
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        player_id = nba_to_player.get(str(row["person_id"]))
        if player_id:
            height = None
            raw_height = str(row["height"] or "")
            if "-" in raw_height:
                feet, inches = raw_height.split("-", 1)
                if feet.isdigit() and inches.isdigit():
                    height = int(feet) * 12 + int(inches)
            output[player_id] = {
                "position": row["position"],
                "role": broad_role(row["position"]),
                "height_inches": height,
            }
    return output


def midrank_within_group(values: dict[str, float]) -> dict[str, float]:
    result = midrank_percentile_scores(values, set(values))
    return {key: float(value) / 100 for key, value in result.items() if value is not None}


def defensive_rebound_evidence(
    silver_root: Path,
    eligible: set[tuple[str, int]],
    positions: dict[str, dict[str, Any]],
) -> dict[tuple[str, int], float]:
    """Return season-relative DREB/game percentiles only where DREB is observed."""
    by_season: dict[int, dict[str, float]] = defaultdict(dict)
    columns = [
        "player_id",
        "season_id",
        "season_type",
        "row_scope",
        "games_played",
        "dreb_total",
    ]
    for row in read_rows(silver_root / "player_season_stats", columns):
        key = (str(row["player_id"]), int(row["season_id"]))
        games = int(row["games_played"])
        if (
            key in eligible
            and row["season_type"] == "REGULAR"
            and row["row_scope"] == "TOTAL"
            and row["dreb_total"] is not None
            and games > 0
        ):
            by_season[key[1]][key[0]] = float(row["dreb_total"]) / games
    global_scaled: dict[tuple[str, int], float] = {}
    role_values: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
    for season, values in by_season.items():
        for player_id, percentile in midrank_within_group(values).items():
            global_scaled[(player_id, season)] = percentile
            role = positions.get(player_id, {}).get("role")
            if role:
                role_values[(season, str(role))][player_id] = values[player_id]
    role_scaled = {key: midrank_within_group(values) for key, values in role_values.items()}
    output: dict[tuple[str, int], float] = {}
    for key, global_value in global_scaled.items():
        player_id, season = key
        role = positions.get(player_id, {}).get("role")
        role_value = role_scaled.get((season, str(role)), {}).get(player_id) if role else None
        output[key] = (
            0.65 * global_value + 0.35 * role_value if role_value is not None else global_value
        )
    return output


def role_actions(
    seasons: dict[tuple[str, int], dict[str, Any]],
    positions: dict[str, dict[str, Any]],
    defensive_rebounds: dict[tuple[str, int], float],
) -> dict[tuple[str, int], dict[str, Any]]:
    role_rank: dict[tuple[int, str, str], dict[str, float]] = defaultdict(dict)
    for (player_id, season), row in seasons.items():
        role = positions.get(player_id, {}).get("role")
        if role:
            for metric in ("rpg", "spg", "bpg"):
                if row.get(f"{metric}_raw") is not None:
                    role_rank[(season, str(role), metric)][player_id] = float(row[f"{metric}_raw"])
    role_scaled = {key: midrank_within_group(values) for key, values in role_rank.items()}
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for key, row in seasons.items():
        player_id, season = key
        role = positions.get(player_id, {}).get("role")
        evidence: dict[str, float | None] = {}
        for metric in ("rpg", "spg", "bpg"):
            global_value = row.get(f"{metric}_percentile")
            role_value = (
                role_scaled.get((season, str(role), metric), {}).get(player_id) if role else None
            )
            evidence[metric] = (
                0.65 * float(global_value) + 0.35 * role_value
                if global_value is not None and role_value is not None
                else global_value
            )
        rebound = defensive_rebounds.get(key, evidence["rpg"])
        value, coverage = role_aware_action_context(rebound, evidence["spg"], evidence["bpg"])
        output[key] = {
            "value": value,
            "coverage": coverage,
            "role": role,
            "rebound_evidence": rebound,
            "rebound_semantics": (
                "DEFENSIVE_REBOUNDS" if key in defensive_rebounds else "TOTAL_REBOUND_PROXY"
            ),
            "steal_evidence": evidence["spg"],
            "block_evidence": evidence["bpg"],
        }
    return output


def game_context(silver_root: Path) -> list[dict[str, Any]]:
    pattern = str(silver_root / "player_game_stats/**/*.parquet")
    connection = duckdb.connect()
    cursor = connection.execute(
        """
        WITH team_games AS (
          SELECT game_id, season_id, team_id, SUM(points) AS team_points
          FROM read_parquet(?)
          WHERE season_type='REGULAR' AND did_play AND points IS NOT NULL
          GROUP BY ALL
        ), pairs AS (
          SELECT a.game_id, a.season_id, a.team_id, a.team_points,
                 b.team_id AS opponent_team_id, b.team_points AS opponent_points
          FROM team_games a JOIN team_games b USING (game_id, season_id)
          WHERE a.team_id <> b.team_id
        ), baseline AS (
          SELECT season_id, team_id, SUM(team_points)/COUNT(*) AS ppg
          FROM team_games GROUP BY ALL
        )
        SELECT p.*, b.ppg AS expected_opponent_points
        FROM pairs p JOIN baseline b
          ON p.season_id=b.season_id AND p.opponent_team_id=b.team_id
        ORDER BY p.season_id,p.game_id,p.team_id
        """,
        [pattern],
    )
    columns = [str(item[0]) for item in cursor.description]
    game_rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    connection.close()
    return game_rows


def presence_estimates(
    silver_root: Path, games: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], float], dict[str, Any]]:
    # The frozen player-game contract does not expose venue assignment; the model
    # adjusts opponent strength and season environment, while venue is explicitly
    # recorded as unavailable rather than guessed.
    game_lookup = {(str(row["game_id"]), str(row["team_id"])): row for row in games}
    pattern = str(silver_root / "player_game_stats/**/*.parquet")
    connection = duckdb.connect()
    appearances = connection.execute(
        """SELECT DISTINCT player_id,season_id,team_id,game_id
             FROM read_parquet(?)
            WHERE season_type='REGULAR' AND did_play
            ORDER BY season_id,team_id,player_id,game_id""",
        [pattern],
    ).fetchall()
    connection.close()
    team_games: dict[tuple[int, str], list[str]] = defaultdict(list)
    residual: dict[tuple[str, str], float] = {}
    for row in games:
        game_id, team_id = str(row["game_id"]), str(row["team_id"])
        team_games[(int(row["season_id"]), team_id)].append(game_id)
        residual[(game_id, team_id)] = float(row["expected_opponent_points"]) - float(
            row["opponent_points"]
        )
    player_games: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    for player_id, season, team_id, game_id in appearances:
        if (str(game_id), str(team_id)) in game_lookup:
            player_games[(str(player_id), int(season), str(team_id))].add(str(game_id))
    rows: list[dict[str, Any]] = []
    career: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    statuses: Counter[str] = Counter()
    for (player_id, season, team_id), with_ids in sorted(player_games.items()):
        all_ids = set(team_games[(season, team_id)])
        without_ids = all_ids - with_ids
        estimate = defensive_presence_estimate(
            [residual[(game_id, team_id)] for game_id in sorted(with_ids)],
            [residual[(game_id, team_id)] for game_id in sorted(without_ids)],
        )
        statuses[estimate.confidence.value] += 1
        if estimate.adjusted_difference is not None:
            career[(player_id, season)].append((estimate.adjusted_difference, len(with_ids)))
        rows.append(
            {
                "player_id": player_id,
                "season_id": season,
                "season_type": "REGULAR",
                "team_id": team_id,
                "games_with": estimate.games_with,
                "games_without": estimate.games_without,
                "effective_sample_size": estimate.effective_sample_size,
                "raw_difference_points": estimate.raw_difference,
                "shrunk_difference_points": estimate.adjusted_difference,
                "standard_error": estimate.standard_error,
                "lower_95": estimate.lower_95,
                "upper_95": estimate.upper_95,
                "reliability": estimate.reliability,
                "confidence": estimate.confidence.value,
                "opponent_strength_adjusted": True,
                "home_away_adjusted": False,
                "team_season_baseline_context": True,
                "methodology_version": DEFENSE_AUDIT_METHODOLOGY_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    season_value = {
        key: sum(value * games for value, games in values) / sum(games for _, games in values)
        for key, values in career.items()
    }
    return (
        rows,
        season_value,
        {
            "status_counts": dict(statuses),
            "eligible_player_seasons": len(season_value),
            "venue_adjustment": "UNAVAILABLE_IN_CANONICAL_PLAYER_GAME_CONTRACT",
            "teammate_adjustment": "NOT_IDENTIFIABLE_AS_LINEUP_RAPM_FROM_GAME_PRESENCE",
        },
    )


def reconstruct(
    scores_rows: list[dict[str, Any]],
    seasons: dict[tuple[str, int], dict[str, Any]],
    suppression: dict[tuple[str, int], float],
    reference: set[str],
    positions: dict[str, dict[str, Any]],
    defensive_rebounds: dict[tuple[str, int], float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float | None], dict[str, Any]]:
    current = {str(row["player_id"]): row for row in scores_rows if row["dimension"] == "DEFENSE"}
    season_rows: list[dict[str, Any]] = []
    career_values: dict[str, list[float]] = defaultdict(list)
    action_values: dict[str, list[float]] = defaultdict(list)
    suppression_values: dict[str, list[float]] = defaultdict(list)
    for (player_id, season), row in sorted(seasons.items()):
        team = suppression.get((player_id, season))
        action, action_coverage = current_action_context(
            row.get("rpg_percentile"), row.get("spg_percentile"), row.get("bpg_percentile")
        )
        raw, coverage = defense_candidate(
            team_suppression=team,
            action_context=action,
            weights=(0.65, 0.35, 0.0),
        )
        if raw is not None:
            career_values[player_id].append(raw)
            suppression_values[player_id].append(float(team))
            if action is not None:
                action_values[player_id].append(float(action))
        season_rows.append(
            {
                "player_id": player_id,
                "season_id": season,
                "season_type": "REGULAR",
                "position": positions.get(player_id, {}).get("position"),
                "broad_role": positions.get(player_id, {}).get("role"),
                "qualification_status": "QUALIFIED",
                "team_suppression": team,
                "rpg_evidence": row.get("rpg_percentile"),
                "dreb_evidence": defensive_rebounds.get((player_id, season)),
                "stl_evidence": row.get("spg_percentile"),
                "blk_evidence": row.get("bpg_percentile"),
                "action_context": action,
                "action_coverage": action_coverage,
                "v1_raw_season_composite": raw,
                "evidence_weight_coverage": coverage,
                "rebound_semantics": "TOTAL_REBOUNDS_NOT_DEFENSIVE_REBOUNDS",
                "methodology_version": DIMENSION_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    raw_career = {
        player_id: statistics.fmean(values) if values else None
        for player_id, values in career_values.items()
    }
    all_raw = {player_id: raw_career.get(player_id) for player_id in current}
    reconstructed = midrank_percentile_scores(all_raw, reference)
    mismatches = []
    player_rows = []
    for player_id, row in current.items():
        expected, actual = row["score"], reconstructed[player_id]
        if (expected is None) != (actual is None) or (
            expected is not None and abs(float(expected) - float(actual)) > 1e-12
        ):
            mismatches.append(player_id)
        player_rows.append(
            {
                "player_id": player_id,
                "nba_player_id": row["nba_player_id"],
                "player_name": row["display_name"],
                "position": positions.get(player_id, {}).get("position"),
                "broad_role": positions.get(player_id, {}).get("role"),
                "height_inches": positions.get(player_id, {}).get("height_inches"),
                "career_team_suppression": statistics.fmean(suppression_values[player_id])
                if suppression_values[player_id]
                else None,
                "career_action_context": statistics.fmean(action_values[player_id])
                if action_values[player_id]
                else None,
                "v1_raw_defense": raw_career.get(player_id),
                "v1_defense_score": expected,
                "reconstructed_defense_score": actual,
                "evidence_confidence": row["evidence_confidence"],
                "coverage_status": row["coverage_status"],
                "relevant_seasons": row["relevant_seasons"],
                "methodology_version": DIMENSION_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    return (
        season_rows,
        player_rows,
        reconstructed,
        {
            "players_compared": len(current),
            "mismatches": len(mismatches),
            "maximum_absolute_difference": max(
                (
                    abs(float(current[p]["score"]) - float(reconstructed[p]))
                    for p in current
                    if current[p]["score"] is not None and reconstructed[p] is not None
                ),
                default=0.0,
            ),
            "exact_within_1e_12": not mismatches,
        },
    )


def candidate_scores(
    players: list[dict[str, Any]],
    seasons: dict[tuple[str, int], dict[str, Any]],
    suppression: dict[tuple[str, int], float],
    role_action: dict[tuple[str, int], dict[str, Any]],
    presence_raw: dict[tuple[str, int], float],
    reference: set[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float | None]]]:
    presence_by_season: dict[int, dict[str, float]] = defaultdict(dict)
    for (player_id, season), value in presence_raw.items():
        presence_by_season[season][player_id] = value
    presence_scaled: dict[tuple[str, int], float] = {}
    for season, values in presence_by_season.items():
        for player_id, value in midrank_within_group(values).items():
            presence_scaled[(player_id, season)] = value
    definitions = {
        "V1_BASELINE": (0.65, 0.35, 0.0, False),
        "A_REDUCED_TEAM": (0.45, 0.55, 0.0, True),
        "B_TRIANGULATED_PRESENCE": (0.30, 0.30, 0.40, True),
        "C_COVERAGE_ADAPTIVE": (0.35, 0.35, 0.30, True),
        "D_UNIVERSAL_CORE_NO_MODERN_CORRECTION": (0.40, 0.35, 0.25, True),
    }
    season_candidate: dict[tuple[str, str], list[float]] = defaultdict(list)
    coverage: dict[tuple[str, str], list[float]] = defaultdict(list)
    for key, row in seasons.items():
        player_id, _ = key
        v1_action, _ = current_action_context(
            row.get("rpg_percentile"), row.get("spg_percentile"), row.get("bpg_percentile")
        )
        for name, (team_weight, action_weight, presence_weight, role_aware) in definitions.items():
            action = role_action[key]["value"] if role_aware else v1_action
            value, available = defense_candidate(
                team_suppression=suppression.get(key),
                action_context=action,
                presence_impact=presence_scaled.get(key),
                weights=(team_weight, action_weight, presence_weight),
            )
            if value is not None:
                season_candidate[(name, player_id)].append(value)
                coverage[(name, player_id)].append(available)
    raw: dict[str, dict[str, float | None]] = {}
    scaled: dict[str, dict[str, float | None]] = {}
    all_players = [str(row["player_id"]) for row in players]
    for name in definitions:
        raw[name] = {
            player_id: statistics.fmean(season_candidate[(name, player_id)])
            if season_candidate[(name, player_id)]
            else None
            for player_id in all_players
        }
        scaled[name] = midrank_percentile_scores(raw[name], reference)
    output = []
    v1 = {str(row["player_id"]): row for row in players}
    for name in definitions:
        for player_id in all_players:
            output.append(
                {
                    "player_id": player_id,
                    "player_name": v1[player_id]["player_name"],
                    "candidate": name,
                    "raw_value": raw[name][player_id],
                    "score": scaled[name][player_id],
                    "change_from_v1": (
                        float(scaled[name][player_id]) - float(v1[player_id]["v1_defense_score"])
                        if scaled[name][player_id] is not None
                        and v1[player_id]["v1_defense_score"] is not None
                        else None
                    ),
                    "mean_weight_coverage": statistics.fmean(coverage[(name, player_id)])
                    if coverage[(name, player_id)]
                    else 0.0,
                    "team_weight": definitions[name][0],
                    "action_weight": definitions[name][1],
                    "presence_weight": definitions[name][2],
                    "role_aware_action": definitions[name][3],
                    "methodology_version": DEFENSE_AUDIT_METHODOLOGY_VERSION,
                    "corpus_id": CORPUS_ID,
                }
            )
    return output, scaled


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("mean", "median", "std", "p75", "p90", "p95")}
    array = np.asarray(values)
    return {
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "std": float(np.std(array)),
        "p75": float(np.quantile(array, 0.75)),
        "p90": float(np.quantile(array, 0.90)),
        "p95": float(np.quantile(array, 0.95)),
    }


def position_audit(players: list[dict[str, Any]], modern: dict[str, float]) -> dict[str, Any]:
    groups: dict[str, list[float]] = defaultdict(list)
    action_groups: dict[str, list[float]] = defaultdict(list)
    team_groups: dict[str, list[float]] = defaultdict(list)
    for row in players:
        if row["broad_role"] and row["v1_defense_score"] is not None:
            role = str(row["broad_role"])
            groups[role].append(float(row["v1_defense_score"]))
            if row["career_action_context"] is not None:
                action_groups[role].append(float(row["career_action_context"]))
            if row["career_team_suppression"] is not None:
                team_groups[role].append(float(row["career_team_suppression"]))
    distributions = {}
    for group, values in sorted(groups.items()):
        distributions[group] = {
            "players": len(values),
            **quantiles(values),
            "above_90_pct": sum(v >= 90 for v in values) / len(values),
            "above_95_pct": sum(v >= 95 for v in values) / len(values),
            "below_50_pct": sum(v < 50 for v in values) / len(values),
        }
    shared = [
        row
        for row in players
        if row["broad_role"] and row["player_id"] in modern and row["v1_defense_score"] is not None
    ]
    x = np.asarray([float(row["v1_defense_score"]) for row in shared])
    y = np.asarray([modern[str(row["player_id"])] for row in shared])
    design = np.column_stack((np.ones(len(shared)), x))
    residual = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
    by_role: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(shared, residual.tolist(), strict=True):
        by_role[str(row["broad_role"])].append(value)
    pooled = float(np.std(residual)) or 1.0
    return {
        "position_source_coverage": len([row for row in players if row["broad_role"]])
        / len(players),
        "score_distribution_by_role": distributions,
        "action_context_by_role": {
            role: {"players": len(values), **quantiles(values)}
            for role, values in sorted(action_groups.items())
        },
        "team_suppression_by_role": {
            role: {"players": len(values), **quantiles(values)}
            for role, values in sorted(team_groups.items())
        },
        "modern_overlap_players": len(shared),
        "modern_residual_by_role": {
            role: {
                "n": len(values),
                "mean": statistics.fmean(values),
                "standardized_effect": statistics.fmean(values) / pooled,
            }
            for role, values in sorted(by_role.items())
        },
    }


def modern_defense(silver_root: Path, reference: set[str]) -> dict[str, float]:
    by_season: dict[int, dict[str, float]] = defaultdict(dict)
    for row in read_rows(silver_root / "player_season_advanced"):
        if (
            row["season_type"] == "REGULAR"
            and row["row_scope"] == "TOTAL"
            and row["defensive_rating"] is not None
        ):
            by_season[int(row["season_id"])][str(row["player_id"])] = -float(
                row["defensive_rating"]
            )
    career: dict[str, list[float]] = defaultdict(list)
    for values in by_season.values():
        for player_id, value in midrank_within_group(values).items():
            career[player_id].append(value)
    raw = {player_id: statistics.fmean(values) for player_id, values in career.items()}
    return {
        key: float(value)
        for key, value in midrank_percentile_scores(raw, reference).items()
        if value is not None
    }


def candidate_comparison(
    candidates: dict[str, dict[str, float | None]],
    modern: dict[str, float],
    players: list[dict[str, Any]],
) -> dict[str, Any]:
    roles = {str(row["player_id"]): row.get("broad_role") for row in players}
    result = {}
    baseline = candidates["V1_BASELINE"]
    for name, scores in candidates.items():
        shared = sorted(
            player_id
            for player_id, value in scores.items()
            if value is not None and player_id in modern
        )
        x, y = [float(scores[p]) for p in shared], [modern[p] for p in shared]
        residuals = np.asarray(y) - np.asarray(x)
        role_residual: dict[str, list[float]] = defaultdict(list)
        for player_id, value in zip(shared, residuals.tolist(), strict=True):
            if roles.get(player_id):
                role_residual[str(roles[player_id])].append(value)
        result[name] = {
            "modern_overlap": len(shared),
            "spearman": spearman(x, y),
            "pearson": float(np.corrcoef(x, y)[0, 1]),
            "median_absolute_score_gap": statistics.median(abs(v) for v in residuals.tolist()),
            "mean_score_gap_by_role": {
                role: statistics.fmean(values) for role, values in sorted(role_residual.items())
            },
        }
        comparable = sorted(
            player_id
            for player_id, value in scores.items()
            if value is not None and baseline.get(player_id) is not None
        )
        result[name]["spearman_to_v1"] = spearman(
            [float(baseline[player_id]) for player_id in comparable],
            [float(scores[player_id]) for player_id in comparable],
        )
        for size in (25, 50, 100):
            baseline_top = set(
                sorted(
                    comparable,
                    key=lambda player_id: (-float(baseline[player_id]), player_id),
                )[:size]
            )
            candidate_top = set(
                sorted(
                    comparable,
                    key=lambda player_id: (-float(scores[player_id]), player_id),
                )[:size]
            )
            result[name][f"top_{size}_overlap_with_v1"] = len(baseline_top & candidate_top) / size
    return result


def award_validation(
    silver_root: Path, candidates: dict[str, dict[str, float | None]]
) -> dict[str, Any]:
    events = read_rows(silver_root / "player_awards", ["player_id", "award_type"])
    groups = {
        "DPOY": {str(row["player_id"]) for row in events if row["award_type"] == "DPOY"},
        "ALL_DEFENSE": {
            str(row["player_id"]) for row in events if row["award_type"] == "ALL_DEFENSE"
        },
    }
    output = {}
    for candidate, scores in candidates.items():
        output[candidate] = {}
        for award, players in groups.items():
            values = [float(scores[player]) for player in players if scores.get(player) is not None]
            output[candidate][award] = {
                "recognized_players": len(values),
                "share_at_or_above_90": sum(v >= 90 for v in values) / len(values)
                if values
                else None,
                "share_at_or_above_95": sum(v >= 95 for v in values) / len(values)
                if values
                else None,
                "median_score": statistics.median(values) if values else None,
            }
    return {"awards_used_as_score_inputs": False, "validation": output}


def team_attribution(
    player_team: dict[tuple[str, int, str], float], season_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    action = {
        (str(row["player_id"]), int(row["season_id"])): row["action_context"] for row in season_rows
    }
    raw = {
        (str(row["player_id"]), int(row["season_id"])): row["v1_raw_season_composite"]
        for row in season_rows
    }
    groups: dict[tuple[int, str], list[str]] = defaultdict(list)
    memberships: dict[tuple[str, int], list[str]] = defaultdict(list)
    for player_id, season, team_id in player_team:
        groups[(season, team_id)].append(player_id)
        memberships[(player_id, season)].append(team_id)
    pairs: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (season, _team_id), ids in groups.items():
        unique = sorted(set(ids))
        for index, left in enumerate(unique):
            for right in unique[index + 1 :]:
                left_action, right_action = action.get((left, season)), action.get((right, season))
                if left_action is not None and right_action is not None:
                    pairs[(left, right)].append((float(left_action), float(right_action)))
    qualified = []
    for (left, right), values in pairs.items():
        if len(values) >= 3:
            action_gap = statistics.fmean(abs(a - b) for a, b in values)
            qualified.append((action_gap, left, right, len(values)))
    qualified.sort(reverse=True)
    final_groups: list[list[float]] = []
    for (season, _team_id), ids in groups.items():
        values = [
            float(raw[(player_id, season)])
            for player_id in set(ids)
            if len(memberships[(player_id, season)]) == 1
            and raw.get((player_id, season)) is not None
        ]
        if len(values) >= 2:
            final_groups.append(values)
    all_values = [value for values in final_groups for value in values]
    grand = statistics.fmean(all_values)
    total_ss = sum((value - grand) ** 2 for value in all_values)
    between_ss = sum(
        len(values) * (statistics.fmean(values) - grand) ** 2 for values in final_groups
    )
    final_eta_squared = between_ss / total_ss if total_ss else None
    career_team: list[float] = []
    career_action: list[float] = []
    career_raw: list[float] = []
    rows_by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in season_rows:
        if (
            row["team_suppression"] is not None
            and row["action_context"] is not None
            and row["v1_raw_season_composite"] is not None
        ):
            rows_by_player[str(row["player_id"])].append(row)
    for rows in rows_by_player.values():
        career_team.append(statistics.fmean(float(row["team_suppression"]) for row in rows))
        career_action.append(statistics.fmean(float(row["action_context"]) for row in rows))
        career_raw.append(statistics.fmean(float(row["v1_raw_season_composite"]) for row in rows))
    return {
        "team_season_suppression_within_team_variance": 0.0,
        "team_season_suppression_intraclass_correlation": 1.0,
        "final_v1_season_composite_between_team_eta_squared": final_eta_squared,
        "career_raw_correlation_with_team_suppression": spearman(career_raw, career_team),
        "career_raw_correlation_with_action_context": spearman(career_raw, career_action),
        "interpretation": (
            "The 65% suppression input is exactly a team-season constant before trade weighting."
        ),
        "overlap_pairs_at_least_three_team_seasons": len(qualified),
        "pairs_with_action_gap_at_least_0_25": sum(item[0] >= 0.25 for item in qualified),
        "largest_action_gap_collisions": [
            {
                "left_player_id": left,
                "right_player_id": right,
                "shared_team_seasons": count,
                "mean_action_gap": gap,
                "team_suppression_gap_during_shared_seasons": 0.0,
            }
            for gap, left, right, count in qualified[:20]
        ],
    }


def score_scale(
    scores_rows: list[dict[str, Any]], player_rows: list[dict[str, Any]], gold_root: Path
) -> dict[str, Any]:
    top100 = {str(row["player_id"]) for row in read_rows(gold_root / "overall_top100")}
    top25 = {
        str(row["player_id"])
        for row in sorted(
            read_rows(gold_root / "player_overall_scores"),
            key=lambda row: int(row["overall_rank"] or 999999),
        )[:25]
    }
    by_dimension: dict[str, list[float]] = defaultdict(list)
    by_dimension_top100: dict[str, list[float]] = defaultdict(list)
    for row in scores_rows:
        if row["score"] is not None:
            by_dimension[str(row["dimension"])].append(float(row["score"]))
            if str(row["player_id"]) in top100:
                by_dimension_top100[str(row["dimension"])].append(float(row["score"]))
    defense_top25 = [
        float(row["v1_defense_score"])
        for row in player_rows
        if row["player_id"] in top25 and row["v1_defense_score"] is not None
    ]
    raw = [float(row["v1_raw_defense"]) for row in player_rows if row["v1_raw_defense"] is not None]
    return {
        "defense_raw_composite": quantiles(raw),
        "defense_ecdf_all": quantiles(by_dimension["DEFENSE"]),
        "defense_ecdf_top100": quantiles(by_dimension_top100["DEFENSE"]),
        "defense_ecdf_top25": quantiles(defense_top25),
        "dimension_score_standard_deviation": {
            name: float(np.std(values)) for name, values in sorted(by_dimension.items())
        },
        "top100_dimension_standard_deviation": {
            name: float(np.std(values)) for name, values in sorted(by_dimension_top100.items())
        },
        "defense_overall_contribution_std_all": 0.14 * float(np.std(by_dimension["DEFENSE"])),
        "defense_overall_contribution_std_top100": 0.14
        * float(np.std(by_dimension_top100["DEFENSE"])),
    }


def v2_counterfactual(
    gold_root: Path,
    selected: dict[str, float | None],
    player_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    overall = read_rows(gold_root / "player_overall_scores")
    rows = []
    shared = []
    for row in overall:
        player_id = str(row["player_id"])
        if row["overall_score"] is None or selected.get(player_id) is None:
            continue
        old_defense = float(row["defense_score"])
        new_overall = float(row["overall_score"]) + 0.14 * (
            float(selected[player_id]) - old_defense
        )
        shared.append(
            (player_id, float(row["overall_score"]), new_overall, int(row["overall_rank"]))
        )
    order = {
        player_id: rank
        for rank, (player_id, _, _, _) in enumerate(
            sorted(shared, key=lambda item: (-item[2], item[0])), 1
        )
    }
    for player_id, old, new, old_rank in shared:
        rows.append(
            {
                "player_id": player_id,
                "v1_overall_score": old,
                "v1_overall_rank": old_rank,
                "defense_v2_counterfactual_score": new,
                "defense_v2_counterfactual_rank": order[player_id],
                "rank_change": old_rank - order[player_id],
                "published_overall_replaced": False,
                "methodology_version": DEFENSE_V2_CANDIDATE_VERSION,
            }
        )
    old_values, new_values = [item[1] for item in shared], [item[2] for item in shared]
    report: dict[str, Any] = {"players": len(shared), "spearman": spearman(old_values, new_values)}
    for size in (10, 25, 50, 100):
        old_top = {item[0] for item in sorted(shared, key=lambda item: (-item[1], item[0]))[:size]}
        new_top = {item[0] for item in sorted(shared, key=lambda item: (-item[2], item[0]))[:size]}
        report[f"top_{size}_overlap"] = len(old_top & new_top) / size
    report["largest_movers"] = sorted(
        rows, key=lambda row: (-abs(int(row["rank_change"])), row["player_id"])
    )[:25]
    role_by_player = {str(row["player_id"]): row["broad_role"] for row in player_rows}
    career = {str(row["player_id"]): row for row in read_rows(gold_root / "player_career_summary")}
    archetypes = {
        str(row["player_id"]): str(row["kmeans_profile_cluster"])
        for row in read_rows(gold_root / "ml_structure/clustering/player_archetypes.parquet")
    }
    shifts_by_role: dict[str, list[int]] = defaultdict(list)
    shifts_by_era: dict[str, list[int]] = defaultdict(list)
    shifts_by_archetype: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        player_id = str(row["player_id"])
        change = int(row["rank_change"])
        role = role_by_player.get(player_id)
        if role:
            shifts_by_role[str(role)].append(change)
        first = career.get(player_id, {}).get("regular_first_season")
        if first is not None:
            shifts_by_era[f"{int(first) // 10 * 10}S"].append(change)
        if player_id in archetypes:
            shifts_by_archetype[archetypes[player_id]].append(change)

    def summarize(values: list[int]) -> dict[str, float | int]:
        return {
            "players": len(values),
            "mean_rank_change": statistics.fmean(values),
            "median_rank_change": statistics.median(values),
        }

    report["rank_shift_by_role"] = {
        key: summarize(values) for key, values in sorted(shifts_by_role.items())
    }
    report["rank_shift_by_debut_decade"] = {
        key: summarize(values) for key, values in sorted(shifts_by_era.items())
    }
    report["rank_shift_by_step0013_archetype"] = {
        key: summarize(values) for key, values in sorted(shifts_by_archetype.items())
    }
    return rows, report


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    inputs = verify_frozen_inputs(args.docs_root)
    scores_rows = read_rows(args.gold_root / "player_dimension_scores")
    seasons = normalized_seasons(args.gold_root)
    reference = reference_population(args.gold_root, seasons)
    positions = position_metadata(args.legacy_db, scores_rows)
    suppression, player_team = team_suppression(args.silver_root, args.gold_root)
    defensive_rebounds = defensive_rebound_evidence(args.silver_root, set(seasons), positions)
    season_rows, player_rows, _reconstructed, reconstruction = reconstruct(
        scores_rows, seasons, suppression, reference, positions, defensive_rebounds
    )
    if not reconstruction["exact_within_1e_12"]:
        raise ValueError("frozen V1 Defense reconstruction failed")
    role_action = role_actions(seasons, positions, defensive_rebounds)
    games = game_context(args.silver_root)
    presence_rows, presence_raw, presence_summary = presence_estimates(args.silver_root, games)
    presence_summary["eligible_share_of_v1_qualified_player_seasons"] = len(
        set(presence_raw) & set(seasons)
    ) / len(seasons)
    candidate_rows, candidates = candidate_scores(
        player_rows, seasons, suppression, role_action, presence_raw, reference
    )
    modern = modern_defense(args.silver_root, reference)
    modern_report = candidate_comparison(candidates, modern, player_rows)
    position_report = position_audit(player_rows, modern)
    team_report = team_attribution(player_team, season_rows)
    award_report = award_validation(args.silver_root, candidates)
    scale_report = score_scale(scores_rows, player_rows, args.gold_root)
    # Predeclared constitutional trigger: exact team identity in the majority-weight
    # channel plus weak independent modern association is material, not cosmetic.
    revision = (
        team_report["team_season_suppression_intraclass_correlation"] >= 0.80
        and modern_report["V1_BASELINE"]["spearman"] < 0.50
    )
    verdict = "REQUIRES_REVISION" if revision else "SOUND_WITH_LIMITATIONS"
    selected_name = "B_TRIANGULATED_PRESENCE" if revision else "V1_BASELINE"
    counterfactual_rows, counterfactual = (
        v2_counterfactual(args.gold_root, candidates[selected_name], player_rows)
        if revision
        else ([], None)
    )

    stress = []
    candidates_lookup = {
        (str(row["player_id"]), str(row["candidate"])): row for row in candidate_rows
    }
    for player in player_rows:
        if player["player_name"] not in DIAGNOSTIC_NAMES:
            continue
        player_id = str(player["player_id"])
        strongest = sorted(
            (
                row
                for row in season_rows
                if row["player_id"] == player_id and row["v1_raw_season_composite"] is not None
            ),
            key=lambda row: -float(row["v1_raw_season_composite"]),
        )
        stress.append(
            {
                "player_id": player_id,
                "player_name": player["player_name"],
                "v1_score": player["v1_defense_score"],
                "v1_raw": player["v1_raw_defense"],
                "career_team_suppression": player["career_team_suppression"],
                "career_action_context": player["career_action_context"],
                "confidence": player["evidence_confidence"],
                "role": player["broad_role"],
                "strongest_seasons": [row["season_id"] for row in strongest[:3]],
                "weakest_seasons": [row["season_id"] for row in strongest[-3:]],
                "candidates": {
                    name: {
                        "score": candidates_lookup[(player_id, name)]["score"],
                        "change": candidates_lookup[(player_id, name)]["change_from_v1"],
                        "coverage": candidates_lookup[(player_id, name)]["mean_weight_coverage"],
                    }
                    for name in candidates
                },
                "driver": "TEAM_SUPPRESSION"
                if float(player["career_team_suppression"] or 0)
                >= float(player["career_action_context"] or 0)
                else "ACTION_CONTEXT",
            }
        )

    output_dir = args.gold_root / "defense_forensic_audit"
    manifests = [
        write_parquet(
            season_rows, output_dir / "v1-season-decomposition.parquet", ("season_id", "player_id")
        ),
        write_parquet(player_rows, output_dir / "v1-player-decomposition.parquet", ("player_id",)),
        write_parquet(
            presence_rows,
            output_dir / "defensive-presence-estimates.parquet",
            ("season_id", "team_id", "player_id"),
        ),
        write_parquet(
            candidate_rows,
            output_dir / "candidate-defense-scores.parquet",
            ("candidate", "player_id"),
        ),
    ]
    if counterfactual_rows:
        selected_v2_rows = []
        for row in candidate_rows:
            if row["candidate"] != selected_name:
                continue
            coverage = float(row["mean_weight_coverage"])
            confidence = (
                "STRONG" if coverage >= 0.85 else "MODERATE" if coverage >= 0.65 else "LIMITED"
            )
            selected_v2_rows.append(
                {
                    "player_id": row["player_id"],
                    "player_name": row["player_name"],
                    "defense_score": row["score"],
                    "raw_defense_value": row["raw_value"],
                    "coverage_weight": coverage,
                    "evidence_confidence": confidence,
                    "methodology_version": DEFENSE_V2_CANDIDATE_VERSION,
                    "upstream_dimension_methodology": DIMENSION_VERSION,
                    "corpus_id": CORPUS_ID,
                    "published_v1_replaced": False,
                }
            )
        manifests.append(
            write_parquet(
                selected_v2_rows,
                output_dir / "defense-v2-candidate-scores.parquet",
                ("player_id",),
            )
        )
        manifests.append(
            write_parquet(
                counterfactual_rows,
                output_dir / "defense-v2-overall-counterfactual.parquet",
                ("defense_v2_counterfactual_rank", "player_id"),
            )
        )
    reports = {
        "defense-position-bias-audit.json": position_report,
        "defense-team-attribution-audit.json": team_report,
        "defensive-presence-impact-audit.json": presence_summary,
        "defense-candidate-comparison.json": {
            "candidates": modern_report,
            "award_validation": award_report,
            "selected": selected_name,
            "selection_not_player_targeted": True,
        },
        "defense-score-scale-audit.json": scale_report,
        "defense-stress-tests.json": {"players": stress},
        "defense-v2-methodology.json": {
            "status": "COUNTERFACTUAL_NOT_PROMOTED",
            "version": DEFENSE_V2_CANDIDATE_VERSION,
            "season_component_weights": {
                "team_suppression_context": 0.30,
                "role_aware_actions": 0.30,
                "defensive_presence_impact": 0.40,
            },
            "action_weights": {
                "defensive_rebounds_or_labeled_total_rebound_proxy": 0.40,
                "steals": 0.30,
                "blocks": 0.30,
            },
            "role_blend": {"global_era_percentile": 0.65, "broad_role_percentile": 0.35},
            "presence_minimums": {"games_with": 10, "games_without": 5},
            "presence_shrinkage": "raw_difference * n_eff/(n_eff+20)",
            "missingness": "available weights explicitly renormalized; team context required",
            "career_aggregation": "unweighted mean of qualified Regular Season values",
            "score_scale": "frozen BROAD_HIGH_RECALL midrank ECDF 0-100",
            "modern_features_in_universal_score": False,
            "awards_in_score": False,
            "postseason_in_score": False,
            "defensive_rebound_player_seasons": len(defensive_rebounds),
            "presence_eligible_player_seasons": len(presence_raw),
        },
    }
    if counterfactual is not None:
        reports["defense-v2-counterfactual.json"] = counterfactual
    report_hashes = {}
    for name, payload in reports.items():
        value = {
            "step": "STEP-0015A",
            "methodology_version": DEFENSE_AUDIT_METHODOLOGY_VERSION,
            "input_fingerprints": inputs,
            **payload,
        }
        stable_json(args.docs_root / name, value)
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint_payload = {
        "inputs": inputs,
        "outputs": manifests,
        "reports": report_hashes,
        "verdict": verdict,
        "selected": selected_name,
    }
    output_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015A",
        "result": "PASS",
        "constitutional_verdict": verdict,
        "audit_methodology_version": DEFENSE_AUDIT_METHODOLOGY_VERSION,
        "defense_v2_methodology_version": DEFENSE_V2_CANDIDATE_VERSION if revision else None,
        "selected_candidate": selected_name,
        "v1_reconstruction": reconstruction,
        "input_fingerprints": inputs,
        "reference_players": len(reference),
        "season_decomposition_rows": len(season_rows),
        "player_decomposition_rows": len(player_rows),
        "presence_rows": len(presence_rows),
        "presence": presence_summary,
        "position_metadata_players": len(positions),
        "defensive_rebound_player_seasons": len(defensive_rebounds),
        "modern_validation": modern_report,
        "team_attribution": team_report,
        "counterfactual": counterfactual,
        "network_requests": 0,
        "frozen_v1_mutated": False,
        "frozen_overall_mutated": False,
        "output_partitions": manifests,
        "output_fingerprint": output_fingerprint,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "deterministic_rebuild_verified": args.expected_fingerprint == output_fingerprint
        if args.expected_fingerprint
        else False,
    }
    stable_json(args.docs_root / "defense-forensic-audit-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != output_fingerprint:
        raise ValueError(f"output fingerprint mismatch: {output_fingerprint}")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
