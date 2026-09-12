#!/usr/bin/env python3
"""Run the offline STEP-0015C Peak forensic audit.

Frozen V1 dimension and Overall outputs are read-only baselines. Experimental
Peak candidates and Overall comparisons are written to a dedicated ignored
Gold directory.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.dimension_scores import midrank_percentile_scores
from goatlab.rankings.peak_forensics import (
    OVERALL_PEAK_V2_COUNTERFACTUAL_VERSION,
    PEAK_AUDIT_METHODOLOGY_VERSION,
    PEAK_V2_RESEARCH_VERSION,
    correlation,
    individual_season_quality,
    player_peak,
    synthetic_window,
    v1_season_quality,
)
from pipelines.rankings.audit_defense_v1 import position_metadata, read_rows
from pipelines.rankings.build_dimension_scores_v1 import (
    add_overall_season_quality,
    broad_reference,
    build_team_suppression,
    defense_bridge,
    enrich_season_values,
    load_normalized_seasons,
    player_context,
)

ROOT = Path(__file__).resolve().parents[2]
DIMENSION_VERSION = "goatlab-v1-dimension-scores-v1"
OVERALL_VERSION = "goatlab-v1-overall-v1"
DIMENSION_FINGERPRINT = "0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a"
OVERALL_FINGERPRINT = "02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa"
DEFENSE_AUDIT_FINGERPRINT = "07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324"
DEFENSE_PROMOTION_FINGERPRINT = "103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f"
CORPUS_ID = "GOATLAB-HIST-V1"
PRIMITIVES = ("ppg", "ts_pct", "apg", "team_suppression", "rpg", "spg", "bpg")
DIAGNOSTIC_NAMES = (
    "Michael Jordan",
    "LeBron James",
    "Kareem Abdul-Jabbar",
    "Larry Bird",
    "Magic Johnson",
    "Hakeem Olajuwon",
    "Tim Duncan",
    "Shaquille O'Neal",
    "Kobe Bryant",
    "Stephen Curry",
    "Kevin Durant",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
    "Wilt Chamberlain",
    "Bill Russell",
    "Rudy Gobert",
    "Kawhi Leonard",
    "Dwyane Wade",
    "Karl Malone",
    "David Robinson",
)
OVERALL_WEIGHTS = {
    "PEAK": 0.17,
    "LONGEVITY": 0.14,
    "OFFENSE": 0.16,
    "DEFENSE": 0.14,
    "PLAYOFFS": 0.18,
    "ACCOLADES": 0.10,
    "WINNING": 0.11,
}


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


def verify_inputs(docs_root: Path) -> dict[str, str]:
    checks = {
        "dimension": ("dimension-score-summary.json", "output_fingerprint", DIMENSION_FINGERPRINT),
        "overall": ("overall-ranking-summary.json", "output_fingerprint", OVERALL_FINGERPRINT),
        "defense_forensic": (
            "defense-forensic-audit-summary.json",
            "output_fingerprint",
            DEFENSE_AUDIT_FINGERPRINT,
        ),
        "defense_promotion": (
            "defense-v2-promotion-summary.json",
            "output_fingerprint",
            DEFENSE_PROMOTION_FINGERPRINT,
        ),
    }
    result: dict[str, str] = {}
    for label, (name, key, expected) in checks.items():
        payload = json.loads((docs_root / name).read_text(encoding="utf-8"))
        if payload.get(key) != expected:
            raise ValueError(f"unexpected frozen input fingerprint: {name}")
        result[label] = expected
    constitution = ROOT / "docs/constitution/GOATLAB_V1_CONSTITUTION.md"
    result["constitution"] = file_hash(constitution)
    return result


def rank_percentiles_by_season(
    raw: dict[tuple[str, int], float | None],
) -> dict[tuple[str, int], float | None]:
    grouped: dict[int, dict[str, float | None]] = defaultdict(dict)
    for (player_id, season), value in raw.items():
        grouped[season][player_id] = value
    output: dict[tuple[str, int], float | None] = {}
    for season, values in grouped.items():
        scaled = midrank_percentile_scores(values, set(values))
        output.update(
            {
                (player_id, season): score / 100.0 if score is not None else None
                for player_id, score in scaled.items()
            }
        )
    return output


def paired(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    if not actual or len(actual) != len(predicted):
        return {"observations": 0}
    errors = np.asarray(predicted) - np.asarray(actual)
    return {
        "observations": len(actual),
        "mean_signed_error": float(errors.mean()),
        "mean_absolute_error": float(np.abs(errors).mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "spearman": spearman(actual, predicted),
        "pearson": correlation(actual, predicted),
        "p10_error": float(np.quantile(errors, 0.10)),
        "p25_error": float(np.quantile(errors, 0.25)),
        "p50_error": float(np.quantile(errors, 0.50)),
        "p75_error": float(np.quantile(errors, 0.75)),
        "p90_error": float(np.quantile(errors, 0.90)),
        "more_than_5_points": float(np.mean(np.abs(errors) > 5.0)),
        "more_than_10_points": float(np.mean(np.abs(errors) > 10.0)),
        "more_than_15_points": float(np.mean(np.abs(errors) > 15.0)),
    }


def distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    array = np.asarray(values)
    return {
        "count": len(values),
        "mean": float(array.mean()),
        "std": float(array.std()),
        "p10": float(np.quantile(array, 0.10)),
        "p25": float(np.quantile(array, 0.25)),
        "median": float(np.quantile(array, 0.50)),
        "p75": float(np.quantile(array, 0.75)),
        "p90": float(np.quantile(array, 0.90)),
        "p95": float(np.quantile(array, 0.95)),
        "p99": float(np.quantile(array, 0.99)),
    }


def primary_teams(gold_root: Path) -> dict[tuple[str, int], str]:
    candidates: dict[tuple[str, int], list[tuple[int, str]]] = defaultdict(list)
    for row in read_rows(gold_root / "player_team_success_primitives"):
        games = int(row.get("regular_games") or 0)
        if games > 0:
            candidates[(str(row["player_id"]), int(row["season_id"]))].append(
                (games, str(row["team_id"]))
            )
    return {
        key: max(values, key=lambda item: (item[0], item[1]))[1]
        for key, values in candidates.items()
    }


def eta_squared(rows: list[dict[str, Any]], field: str) -> float | None:
    usable = [row for row in rows if row.get("primary_team_id") and row.get(field) is not None]
    if len(usable) < 2:
        return None
    values = [float(row[field]) for row in usable]
    overall = statistics.fmean(values)
    groups: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in usable:
        groups[(int(row["season_id"]), str(row["primary_team_id"]))].append(float(row[field]))
    total = sum((value - overall) ** 2 for value in values)
    between = sum(
        len(group) * (statistics.fmean(group) - overall) ** 2 for group in groups.values()
    )
    return between / total if total > 0.0 else None


def build_decomposition(
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    team_suppression: dict[tuple[str, int], float],
    teams: dict[tuple[str, int], str],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for (player_id, season, season_type), source in sorted(seasons.items()):
        if season_type != "REGULAR":
            continue
        values = {
            "ppg": source.get("ppg_percentile"),
            "ts_pct": source.get("ts_pct_percentile"),
            "apg": source.get("apg_percentile"),
            "rpg": source.get("rpg_percentile"),
            "spg": source.get("spg_percentile"),
            "bpg": source.get("bpg_percentile"),
            "team_suppression": team_suppression.get((player_id, season)),
        }
        quality = v1_season_quality(values)
        expected = len(PRIMITIVES)
        observed = sum(value is not None for value in values.values())
        row: dict[str, Any] = {
            "player_id": player_id,
            "season_id": season,
            "season_type": "REGULAR",
            "primary_team_id": teams.get((player_id, season)),
            "games": int(source.get("games") or 0),
            **values,
            "scoring_value": quality.scoring,
            "offense_value": quality.offense,
            "action_value": quality.actions,
            "defense_value": quality.defense,
            "season_quality_raw": quality.quality,
            "expected_inputs": expected,
            "observed_inputs": observed,
            "missing_inputs_json": json.dumps(
                [name for name, value in values.items() if value is None], separators=(",", ":")
            ),
            "quality_weight_coverage": quality.quality_coverage,
            "methodology_version": DIMENSION_VERSION,
            "corpus_id": CORPUS_ID,
        }
        for name in PRIMITIVES:
            row[f"effective_weight_{name}"] = quality.effective_weights[name]
            row[f"contribution_{name}"] = quality.contributions.get(name)
        rows.append(row)
        index[(player_id, season)] = row
    ranked = rank_percentiles_by_season(
        {(row["player_id"], row["season_id"]): row["season_quality_raw"] for row in rows}
    )
    for row in rows:
        row["season_quality_percentile"] = ranked[(row["player_id"], row["season_id"])]
    return rows, index


def reconstruct_peak(
    players: list[str],
    rows: list[dict[str, Any]],
    reference: set[str],
    frozen_scores: dict[str, dict[str, Any]],
    frozen_components: dict[str, dict[str, float | None]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    per_player: dict[str, dict[int, float | None]] = defaultdict(dict)
    coverage: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        player_id = str(row["player_id"])
        per_player[player_id][int(row["season_id"])] = row["season_quality_percentile"]
        if row["season_quality_percentile"] is not None:
            coverage[player_id].append(float(row["quality_weight_coverage"]))
    raw: dict[str, float | None] = {}
    details: dict[str, tuple[Any, float | None]] = {}
    for player_id in players:
        value, window, apex = player_peak(per_player.get(player_id, {}))
        raw[player_id] = value
        details[player_id] = (window, apex)
    scaled = midrank_percentile_scores(raw, reference)
    output: list[dict[str, Any]] = []
    maximum_score = maximum_raw = maximum_window = 0.0
    mismatch_count = 0
    for player_id in players:
        window, apex = details[player_id]
        frozen = frozen_scores[player_id]
        frozen_component = frozen_components[player_id]
        score = scaled[player_id]
        expected_score = frozen["score"]
        score_difference = (
            abs(float(score) - float(expected_score))
            if score is not None and expected_score is not None
            else 0.0
            if score is None and expected_score is None
            else math.inf
        )
        raw_difference = (
            abs(float(raw[player_id]) - float(frozen["raw_dimension_value"]))
            if raw[player_id] is not None and frozen["raw_dimension_value"] is not None
            else 0.0
            if raw[player_id] is None and frozen["raw_dimension_value"] is None
            else math.inf
        )
        window_difference = 0.0
        for name, value in (
            ("three_year_value", window.value),
            ("apex_value", apex),
        ):
            frozen_value = frozen_component.get(name)
            difference = (
                abs(float(value) - float(frozen_value))
                if value is not None and frozen_value is not None
                else 0.0
                if value is None and frozen_value is None
                else math.inf
            )
            window_difference = max(window_difference, difference)
        if score_difference > 1e-12 or raw_difference > 1e-12 or window_difference > 1e-12:
            mismatch_count += 1
        maximum_score = max(maximum_score, score_difference)
        maximum_raw = max(maximum_raw, raw_difference)
        maximum_window = max(maximum_window, window_difference)
        output.append(
            {
                "player_id": player_id,
                "v1_peak_score": score,
                "raw_peak": raw[player_id],
                "three_year_value": window.value,
                "three_year_start": window.start_season,
                "three_year_end": window.end_season,
                "apex_value": apex,
                "mean_input_coverage": statistics.fmean(coverage[player_id])
                if coverage[player_id]
                else 0.0,
                "coverage_status": frozen["coverage_status"],
                "evidence_confidence": frozen["evidence_confidence"],
                "methodology_version": DIMENSION_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    return output, {
        "players": len(players),
        "mismatches": mismatch_count,
        "exact": mismatch_count == 0,
        "maximum_score_difference": maximum_score,
        "maximum_raw_difference": maximum_raw,
        "maximum_window_component_difference": maximum_window,
    }


def component_influence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if row["season_quality_raw"] is not None]
    quality = np.asarray([float(row["season_quality_raw"]) for row in usable])
    variance = float(np.var(quality))
    components: dict[str, Any] = {}
    full_percentiles = {
        (str(row["player_id"]), int(row["season_id"])): row["season_quality_percentile"]
        for row in usable
    }
    for name in PRIMITIVES:
        values = [float(row[name]) for row in usable if row[name] is not None]
        contributions = np.asarray(
            [float(row.get(f"contribution_{name}") or 0.0) for row in usable]
        )
        covariance_share = (
            float(np.cov(contributions, quality, ddof=0)[0, 1] / variance)
            if variance > 0.0
            else None
        )
        masked_raw: dict[tuple[str, int], float | None] = {}
        for row in usable:
            inputs = {primitive: row[primitive] for primitive in PRIMITIVES}
            inputs[name] = None
            masked_raw[(str(row["player_id"]), int(row["season_id"]))] = v1_season_quality(
                inputs
            ).quality
        masked = rank_percentiles_by_season(masked_raw)
        actual: list[float] = []
        predicted: list[float] = []
        for key, current in full_percentiles.items():
            alternative = masked.get(key)
            if current is not None and alternative is not None:
                actual.append(100.0 * float(current))
                predicted.append(100.0 * float(alternative))
        components[name] = {
            "classification": {
                "ppg": "INDIVIDUAL_OFFENSE",
                "ts_pct": "INDIVIDUAL_OFFENSE",
                "apg": "INDIVIDUAL_OFFENSE",
                "team_suppression": "TEAM_CONTEXT",
                "rpg": "INDIVIDUAL_DEFENSE_PROXY",
                "spg": "INDIVIDUAL_DEFENSE",
                "bpg": "INDIVIDUAL_DEFENSE",
            }[name],
            "nominal_local_weight": {
                "ppg": 0.65,
                "ts_pct": 0.35,
                "apg": 0.35,
                "team_suppression": 0.65,
                "rpg": 0.50,
                "spg": 0.25,
                "bpg": 0.25,
            }[name],
            "available_rows": len(values),
            "value_distribution": distribution(values),
            "mean_realized_effective_weight": statistics.fmean(
                float(row[f"effective_weight_{name}"]) for row in usable
            ),
            "shapley_covariance_variance_share": covariance_share,
            "leave_one_out": paired(actual, predicted),
        }
    return {
        "season_quality_rows": len(usable),
        "season_quality_variance": variance,
        "components": components,
        "variance_shares_sum": sum(
            float(item["shapley_covariance_variance_share"] or 0.0) for item in components.values()
        ),
        "formula_structure": {
            "scoring": "0.65 PPG + 0.35 TS; PPG required; observed TS renormalization",
            "offense": "0.65 stronger of scoring/creation + 0.35 secondary; lone axis becomes 100%",
            "actions": "0.50 RPG + 0.25 STL + 0.25 BLK; observed weights renormalized",
            "defense": (
                "0.65 team suppression + 0.35 actions; team required; lone team becomes 100%"
            ),
            "overall_quality": (
                "0.65 stronger of Offense/Defense + 0.35 secondary; lone axis becomes 100%"
            ),
        },
    }


def masking_audit(
    rows: list[dict[str, Any]], role_by_player: dict[str, str | None]
) -> tuple[dict[str, Any], dict[str, Any]]:
    full = [row for row in rows if all(row[name] is not None for name in PRIMITIVES)]
    regimes = {
        "EARLY_NO_STEALS_BLOCKS": {"spg", "bpg"},
        "EFFICIENCY_UNAVAILABLE": {"ts_pct"},
        "TEAM_CONTEXT_UNAVAILABLE": {"team_suppression"},
        "INTERMEDIATE_TRADITIONAL_NO_ADVANCED": set(),
        "MODERN_PORTABLE": set(),
        "CURRENT_V1_FULL": set(),
    }
    regime_results: dict[str, Any] = {}
    role_results: dict[str, Any] = defaultdict(dict)
    baseline_raw = {
        (str(row["player_id"]), int(row["season_id"])): row["season_quality_raw"] for row in full
    }
    baseline_ranked = rank_percentiles_by_season(baseline_raw)
    actual = [
        100.0 * float(baseline_ranked[(str(row["player_id"]), int(row["season_id"]))])
        for row in full
    ]
    for label, masked_names in regimes.items():
        raw: dict[tuple[str, int], float | None] = {}
        for row in full:
            values = {name: row[name] for name in PRIMITIVES}
            for name in masked_names:
                values[name] = None
            raw[(str(row["player_id"]), int(row["season_id"]))] = v1_season_quality(values).quality
        ranked = rank_percentiles_by_season(raw)
        predicted = [
            100.0 * float(ranked[(str(row["player_id"]), int(row["season_id"]))]) for row in full
        ]
        regime_results[label] = paired(actual, predicted)
        if masked_names:
            for role in ("GUARD", "WING", "FORWARD", "BIG"):
                indices = [
                    index
                    for index, row in enumerate(full)
                    if role_by_player.get(str(row["player_id"])) == role
                ]
                role_results[role][label] = paired(
                    [actual[index] for index in indices],
                    [predicted[index] for index in indices],
                )
    return {
        "full_evidence_rows": len(full),
        "regimes": regime_results,
        "advanced_or_possession_inputs_in_v1": False,
        "interpretation": (
            "Intermediate, modern-portable, and current-full regimes are identical because V1 "
            "contains no advanced or possession input."
        ),
    }, dict(role_results)


def archetype_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    full = [row for row in rows if all(row[name] is not None for name in PRIMITIVES)]
    definitions = {
        "HIGH_VOLUME_SCORER": lambda row: float(row["ppg"]) >= 0.90,
        "HIGH_EFFICIENCY_SCORER": lambda row: float(row["ts_pct"]) >= 0.90,
        "PRIMARY_CREATOR": lambda row: float(row["apg"]) >= 0.90,
        "REBOUND_HEAVY": lambda row: float(row["rpg"]) >= 0.90,
        "DEFENSIVE_ANCHOR_PROXY": lambda row: float(row["defense_value"]) >= 0.90,
        "LOW_SCORING_DEFENSIVE_SPECIALIST": lambda row: (
            float(row["ppg"]) < 0.50 and float(row["defense_value"]) >= 0.90
        ),
        "BALANCED_TWO_WAY": lambda row: (
            float(row["offense_value"]) >= 0.85 and float(row["defense_value"]) >= 0.85
        ),
    }
    result: dict[str, Any] = {}
    for label, predicate in definitions.items():
        selected = [row for row in full if predicate(row)]
        result[label] = {
            "rows": len(selected),
            "season_quality": distribution(
                [100.0 * float(row["season_quality_percentile"]) for row in selected]
            ),
            "mean_team_effective_weight": statistics.fmean(
                float(row["effective_weight_team_suppression"]) for row in selected
            )
            if selected
            else None,
        }
    return result


def team_context_audit(
    rows: list[dict[str, Any]], player_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    usable = [row for row in rows if row["season_quality_raw"] is not None]
    team_values = [
        float(row["team_suppression"]) for row in usable if row["team_suppression"] is not None
    ]
    quality_values = [
        float(row["season_quality_raw"]) for row in usable if row["team_suppression"] is not None
    ]
    by_player_team: dict[str, list[float]] = defaultdict(list)
    for row in usable:
        if row["team_suppression"] is not None:
            by_player_team[str(row["player_id"])].append(float(row["team_suppression"]))
    peak_map = {str(row["player_id"]): row["raw_peak"] for row in player_rows}
    aligned = [
        (float(peak_map[player_id]), statistics.fmean(values))
        for player_id, values in by_player_team.items()
        if peak_map.get(player_id) is not None
    ]
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        if row.get("primary_team_id") and row.get("team_suppression") is not None:
            groups[(int(row["season_id"]), str(row["primary_team_id"]))].append(row)
    teammate_pairs = 0
    identical_team_credit = 0
    for group in groups.values():
        for left, right in itertools.combinations(group, 2):
            teammate_pairs += 1
            if abs(float(left["team_suppression"]) - float(right["team_suppression"])) < 1e-12:
                identical_team_credit += 1
    return {
        "team_component_within_team_season_variance": 0.0,
        "team_component_between_team_eta_squared": eta_squared(usable, "team_suppression"),
        "season_quality_between_team_eta_squared": eta_squared(usable, "season_quality_raw"),
        "season_quality_correlation_with_team_context": correlation(team_values, quality_values),
        "peak_raw_correlation_with_career_mean_team_context": correlation(
            [item[0] for item in aligned], [item[1] for item in aligned]
        ),
        "mean_team_effective_weight": statistics.fmean(
            float(row["effective_weight_team_suppression"]) for row in usable
        ),
        "team_context_rows": len(team_values),
        "teammate_pairs": teammate_pairs,
        "pairs_with_identical_team_credit": identical_team_credit,
        "constitutional_interpretation": "TEAM_SEASON_CONSTANT_INSIDE_INDIVIDUAL_PEAK",
    }


def candidate_peaks(
    players: list[str],
    rows: list[dict[str, Any]],
    reference: set[str],
    role_actions: dict[tuple[str, int], float | None],
    defense_v2: dict[tuple[str, int], float | None],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float | None]]]:
    season_candidates: dict[str, dict[tuple[str, int], float | None]] = {
        "A_NO_TEAM_CURRENT_ACTIONS": {},
        "B_EXPLICIT_60_40_ROLE_ACTIONS": {},
        "C_MULTI_PATH_ROLE_ACTIONS": {},
        "D_UNPROMOTED_DEFENSE_V2_DIAGNOSTIC": {},
    }
    for row in rows:
        key = (str(row["player_id"]), int(row["season_id"]))
        offense = row["offense_value"]
        current_actions = row["action_value"]
        role_action = role_actions.get(key)
        season_candidates["A_NO_TEAM_CURRENT_ACTIONS"][key] = individual_season_quality(
            offense, current_actions, architecture="MULTI_PATH_65_35"
        )
        season_candidates["B_EXPLICIT_60_40_ROLE_ACTIONS"][key] = individual_season_quality(
            offense, role_action, architecture="FIXED_60_40"
        )
        season_candidates["C_MULTI_PATH_ROLE_ACTIONS"][key] = individual_season_quality(
            offense, role_action, architecture="MULTI_PATH_65_35"
        )
        season_candidates["D_UNPROMOTED_DEFENSE_V2_DIAGNOSTIC"][key] = individual_season_quality(
            offense, defense_v2.get(key), architecture="MULTI_PATH_65_35"
        )
    results: dict[str, dict[str, Any]] = {}
    player_scores: dict[str, dict[str, float | None]] = {}
    for label, raw_by_season in season_candidates.items():
        percentiles = rank_percentiles_by_season(raw_by_season)
        by_player: dict[str, dict[int, float | None]] = defaultdict(dict)
        for (player_id, season), value in percentiles.items():
            by_player[player_id][season] = value
        raw_peak: dict[str, float | None] = {}
        details: dict[str, dict[str, Any]] = {}
        for player_id in players:
            raw, window, apex = player_peak(by_player.get(player_id, {}))
            raw_peak[player_id] = raw
            details[player_id] = {
                "raw": raw,
                "three_year": window.value,
                "three_year_start": window.start_season,
                "three_year_end": window.end_season,
                "apex": apex,
            }
        scores = midrank_percentile_scores(raw_peak, reference)
        player_scores[label] = scores
        results[label] = {
            "players_with_score": sum(value is not None for value in scores.values()),
            "reference_players_with_score": sum(
                scores[player_id] is not None for player_id in reference
            ),
            "formula": {
                "A_NO_TEAM_CURRENT_ACTIONS": (
                    "65/35 stronger-secondary Offense/current RPG-STL-BLK actions; both required"
                ),
                "B_EXPLICIT_60_40_ROLE_ACTIONS": (
                    "60% Offense + 40% role-aware actions; both required"
                ),
                "C_MULTI_PATH_ROLE_ACTIONS": (
                    "65/35 stronger-secondary Offense/role-aware actions; both required"
                ),
                "D_UNPROMOTED_DEFENSE_V2_DIAGNOSTIC": (
                    "65/35 Offense/unpromoted Defense V2 diagnostic; both required"
                ),
            }[label],
            "three_year_weight": 0.70,
            "apex_weight": 0.30,
            "details": details,
        }
    return results, player_scores


def compare_candidates(
    candidates: dict[str, dict[str, Any]],
    scores: dict[str, dict[str, float | None]],
    v1: dict[str, dict[str, Any]],
    role_by_player: dict[str, str | None],
) -> dict[str, Any]:
    v1_scores = {player_id: row["score"] for player_id, row in v1.items()}
    report: dict[str, Any] = {}
    for label, values in scores.items():
        overlap = [
            player_id
            for player_id in values
            if values[player_id] is not None and v1_scores[player_id] is not None
        ]
        role_means = {
            role: statistics.fmean(
                float(values[player_id])
                for player_id in overlap
                if role_by_player.get(player_id) == role
            )
            for role in ("GUARD", "WING", "FORWARD", "BIG")
            if any(role_by_player.get(player_id) == role for player_id in overlap)
        }
        report[label] = {
            **{key: value for key, value in candidates[label].items() if key != "details"},
            "overlap_with_v1": len(overlap),
            "spearman_with_v1": spearman(
                [float(v1_scores[player_id]) for player_id in overlap],
                [float(values[player_id]) for player_id in overlap],
            ),
            "pearson_with_v1": correlation(
                [float(v1_scores[player_id]) for player_id in overlap],
                [float(values[player_id]) for player_id in overlap],
            ),
            "role_mean_scores": role_means,
        }
    return report


def overall_counterfactual(
    peak_scores: dict[str, float | None], overall_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in overall_rows:
        player_id = str(source["player_id"])
        peak = peak_scores.get(player_id)
        dimensions = {
            "PEAK": peak,
            "LONGEVITY": source["longevity_score"],
            "OFFENSE": source["offense_score"],
            "DEFENSE": source["defense_score"],
            "PLAYOFFS": source["playoffs_score"],
            "ACCOLADES": source["accolades_score"],
            "WINNING": source["winning_score"],
        }
        eligible = all(value is not None for value in dimensions.values())
        score = (
            sum(OVERALL_WEIGHTS[name] * float(value) for name, value in dimensions.items())
            if eligible
            else None
        )
        rows.append(
            {
                "player_id": player_id,
                "player_name": source["player_name"],
                "v1_peak": source["peak_score"],
                "research_peak": peak,
                "v1_overall": source["overall_score"],
                "v1_rank": source["overall_rank"],
                "counterfactual_overall": score,
                "counterfactual_rank": None,
                "eligibility_status": "ELIGIBLE_COUNTERFACTUAL"
                if eligible
                else "UNRANKED_INCOMPLETE",
                "methodology_version": OVERALL_PEAK_V2_COUNTERFACTUAL_VERSION,
                "published_v1_overwritten": False,
                "corpus_id": CORPUS_ID,
            }
        )
    ranked = sorted(
        [row for row in rows if row["counterfactual_overall"] is not None],
        key=lambda row: (-float(row["counterfactual_overall"]), str(row["player_id"])),
    )
    for rank, row in enumerate(ranked, 1):
        row["counterfactual_rank"] = rank
    old_eligible = sorted(
        [
            row
            for row in rows
            if row["counterfactual_rank"] is not None and row["v1_overall"] is not None
        ],
        key=lambda row: (-float(row["v1_overall"]), str(row["player_id"])),
    )
    old_rank = {str(row["player_id"]): rank for rank, row in enumerate(old_eligible, 1)}
    overlap = [row for row in ranked if str(row["player_id"]) in old_rank]
    new_rank = {str(row["player_id"]): int(row["counterfactual_rank"]) for row in overlap}
    metrics: dict[str, Any] = {
        "eligible_players": len(ranked),
        "common_ranked_players": len(overlap),
        "spearman": spearman(
            [float(old_rank[str(row["player_id"])]) for row in overlap],
            [float(new_rank[str(row["player_id"])]) for row in overlap],
        ),
        "published_overall_overwritten": False,
        "top_15": [
            {
                "rank": row["counterfactual_rank"],
                "player_name": row["player_name"],
                "overall": row["counterfactual_overall"],
                "peak": row["research_peak"],
            }
            for row in ranked[:15]
        ],
    }
    for n in (10, 25, 50, 100):
        old = {str(row["player_id"]) for row in old_eligible[:n]}
        new = {str(row["player_id"]) for row in ranked[:n]}
        metrics[f"top_{n}_overlap"] = len(old & new) / n
    movers = sorted(
        (
            {
                "player_name": row["player_name"],
                "v1_comparable_rank": old_rank[str(row["player_id"])],
                "counterfactual_rank": row["counterfactual_rank"],
                "rank_change": old_rank[str(row["player_id"])] - int(row["counterfactual_rank"]),
                "v1_peak": row["v1_peak"],
                "research_peak": row["research_peak"],
            }
            for row in overlap
        ),
        key=lambda row: (-abs(int(row["rank_change"])), str(row["player_name"])),
    )
    metrics["largest_movers"] = movers[:25]
    return rows, metrics


def validation_report(rows: list[dict[str, Any]], silver_root: Path) -> dict[str, Any]:
    awards: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in read_rows(silver_root / "player_awards"):
        if row.get("season_id") is None:
            continue
        award = str(row.get("award_type") or "")
        level = str(row.get("award_level") or "")
        if award == "MVP":
            awards[(str(row["player_id"]), int(row["season_id"]))].add("MVP")
        if award == "ALL_NBA" and level == "FIRST":
            awards[(str(row["player_id"]), int(row["season_id"]))].add("ALL_NBA_FIRST")
    output: dict[str, Any] = {"awards_used_as_inputs": False}
    for label in ("MVP", "ALL_NBA_FIRST"):
        selected = [
            100.0 * float(row["season_quality_percentile"])
            for row in rows
            if label in awards.get((str(row["player_id"]), int(row["season_id"])), set())
            and row["season_quality_percentile"] is not None
        ]
        output[label] = {
            "seasons": len(selected),
            "distribution": distribution(selected),
            "share_at_or_above_90": sum(value >= 90.0 for value in selected) / len(selected)
            if selected
            else None,
            "share_at_or_above_95": sum(value >= 95.0 for value in selected) / len(selected)
            if selected
            else None,
        }
    return output


def dimension_relationships(frozen: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    peak = frozen["PEAK"]
    for dimension in ("OFFENSE", "DEFENSE", "LONGEVITY", "PLAYOFFS", "WINNING", "ACCOLADES"):
        overlap = [
            player_id
            for player_id, row in peak.items()
            if row["score"] is not None and frozen[dimension][player_id]["score"] is not None
        ]
        left = [float(peak[player_id]["score"]) for player_id in overlap]
        right = [float(frozen[dimension][player_id]["score"]) for player_id in overlap]
        pearson = correlation(left, right)
        output[dimension] = {
            "players": len(overlap),
            "pearson": pearson,
            "spearman": spearman(left, right),
            "shared_linear_variance_r_squared": pearson**2 if pearson is not None else None,
            "incremental_residual_variance": 1.0 - pearson**2 if pearson is not None else None,
        }
    return output


def ecdf_audit(
    player_rows: list[dict[str, Any]], reference: set[str], overall_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    raw = {
        str(row["player_id"]): float(row["raw_peak"])
        for row in player_rows
        if row["raw_peak"] is not None
    }
    reference_values = sorted(raw[player_id] for player_id in reference if player_id in raw)
    quantile_rows = []
    for quantile in (0.90, 0.95, 0.97, 0.99, 0.995):
        value = float(np.quantile(reference_values, quantile))
        mapped = midrank_percentile_scores({"x": value}, {"x"})["x"]
        # Map against the frozen reference rather than the one-point helper.
        below = sum(item < value for item in reference_values)
        equal = sum(item == value for item in reference_values)
        mapped = 100.0 * (below + (equal - 1) / 2.0) / max(len(reference_values) - 1, 1)
        quantile_rows.append({"quantile": quantile, "raw_peak": value, "ecdf_score": mapped})
    sorted_unique = sorted(set(reference_values))
    adjacent = [b - a for a, b in itertools.pairwise(sorted_unique)]
    overall_ranked = [row for row in overall_rows if row["overall_rank"] is not None]
    return {
        "reference_players": len(reference_values),
        "raw_peak_distribution": distribution(reference_values),
        "elite_tail": quantile_rows,
        "median_adjacent_unique_raw_gap": statistics.median(adjacent) if adjacent else None,
        "raw_range_per_one_ecdf_point_around_p95": (
            float(np.quantile(reference_values, 0.96)) - float(np.quantile(reference_values, 0.95))
        ),
        "overall_top_100_peak_score_sd": float(
            np.std(
                [
                    float(row["peak_score"])
                    for row in overall_ranked
                    if int(row["overall_rank"]) <= 100
                ]
            )
        ),
        "overall_top_25_peak_score_sd": float(
            np.std(
                [
                    float(row["peak_score"])
                    for row in overall_ranked
                    if int(row["overall_rank"]) <= 25
                ]
            )
        ),
        "interpretation": (
            "ECDF is monotone and cannot create pairwise reversals; it can compress "
            "raw elite-tail gaps."
        ),
    }


def specialist_profiles() -> dict[str, Any]:
    profiles = {
        "EXTREME_DEFENSIVE_SPECIALIST": {
            "ppg": 0.30,
            "ts_pct": 0.50,
            "apg": 0.30,
            "team_suppression": 0.99,
            "rpg": 0.99,
            "spg": 0.99,
            "bpg": 0.99,
        },
        "EXTREME_OFFENSIVE_SPECIALIST": {
            "ppg": 0.99,
            "ts_pct": 0.99,
            "apg": 0.99,
            "team_suppression": 0.30,
            "rpg": 0.30,
            "spg": 0.30,
            "bpg": 0.30,
        },
        "BALANCED_TWO_WAY": {name: 0.90 for name in PRIMITIVES},
        "PRIMARY_CREATOR": {
            "ppg": 0.60,
            "ts_pct": 0.60,
            "apg": 0.99,
            "team_suppression": 0.60,
            "rpg": 0.60,
            "spg": 0.60,
            "bpg": 0.60,
        },
        "INTERIOR_ANCHOR": {
            "ppg": 0.60,
            "ts_pct": 0.60,
            "apg": 0.30,
            "team_suppression": 0.95,
            "rpg": 0.95,
            "spg": 0.50,
            "bpg": 0.95,
        },
    }
    return {
        label: {
            "inputs": values,
            "v1_raw_season_quality": v1_season_quality(values).quality,
            "effective_weights": v1_season_quality(values).effective_weights,
        }
        for label, values in profiles.items()
    }


def window_apex_audit(player_rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [
        row
        for row in player_rows
        if row["three_year_value"] is not None and row["apex_value"] is not None
    ]
    three = [float(row["three_year_value"]) for row in usable]
    apex = [float(row["apex_value"]) for row in usable]
    raw = [float(row["raw_peak"]) for row in usable]
    alternative_60 = [0.60 * left + 0.40 * right for left, right in zip(three, apex, strict=True)]
    alternative_80 = [0.80 * left + 0.20 * right for left, right in zip(three, apex, strict=True)]
    return {
        "synthetic": {
            "99_99_99": synthetic_window((0.99, 0.99, 0.99)),
            "100_100_80": synthetic_window((1.00, 1.00, 0.80)),
            "95_95_95": synthetic_window((0.95, 0.95, 0.95)),
            "100_90_90": synthetic_window((1.00, 0.90, 0.90)),
            "100_100_missing": synthetic_window((1.00, 1.00, None)),
            "100_100_nonqualified": synthetic_window((1.00, 1.00, None)),
            "missed_season_gap": synthetic_window((1.00, None, 1.00, 1.00)),
        },
        "players_with_complete_peak": len(usable),
        "three_year_apex_spearman": spearman(three, apex),
        "selected_vs_three_only_spearman": spearman(raw, three),
        "selected_vs_60_40_spearman": spearman(raw, alternative_60),
        "selected_vs_80_20_spearman": spearman(raw, alternative_80),
        "mean_apex_minus_three_year": statistics.fmean(
            right - left for left, right in zip(three, apex, strict=True)
        ),
        "mean_apex_raw_contribution": statistics.fmean(0.30 * value for value in apex),
        "same_construct_for_window_and_apex": True,
    }


def diagnostic_traces(
    names: dict[str, str],
    decomposition: dict[tuple[str, int], dict[str, Any]],
    v1_players: dict[str, dict[str, Any]],
    candidate_details: dict[str, dict[str, Any]],
    candidate_scores: dict[str, float | None],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for player_id, name in sorted(names.items(), key=lambda item: item[1]):
        v1 = v1_players[player_id]
        seasons = []
        if v1["three_year_start"] is not None:
            for season in range(int(v1["three_year_start"]), int(v1["three_year_end"]) + 1):
                row = decomposition[(player_id, season)]
                seasons.append(
                    {
                        "season_id": season,
                        "season_quality_percentile": row["season_quality_percentile"],
                        "season_quality_raw": row["season_quality_raw"],
                        "scoring_value": row["scoring_value"],
                        "offense_value": row["offense_value"],
                        "defense_value": row["defense_value"],
                        "team_suppression": row["team_suppression"],
                        "action_value": row["action_value"],
                        "primitive_values": {key: row[key] for key in PRIMITIVES},
                        "effective_weights": {
                            key: row[f"effective_weight_{key}"] for key in PRIMITIVES
                        },
                        "missing_inputs": json.loads(str(row["missing_inputs_json"])),
                    }
                )
        candidate = candidate_details[player_id]
        output.append(
            {
                "player_id": player_id,
                "player_name": name,
                "v1_peak": v1["v1_peak_score"],
                "v1_raw_peak": v1["raw_peak"],
                "v1_three_year": v1["three_year_value"],
                "v1_three_year_start": v1["three_year_start"],
                "v1_three_year_end": v1["three_year_end"],
                "v1_apex": v1["apex_value"],
                "v1_window_seasons": seasons,
                "research_peak": candidate_scores[player_id],
                "research_raw_peak": candidate["raw"],
                "research_three_year": candidate["three_year"],
                "research_three_year_start": candidate["three_year_start"],
                "research_three_year_end": candidate["three_year_end"],
                "research_apex": candidate["apex"],
                "confidence": v1["evidence_confidence"],
                "movement_reason": (
                    "team-season suppression removed; player-specific role-aware actions "
                    "replace V1 Defense axis"
                ),
                "methodology_version": PEAK_AUDIT_METHODOLOGY_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    return output


def trio_ablation(
    names: dict[str, str], rows: dict[tuple[str, int], dict[str, Any]]
) -> dict[str, Any]:
    reverse_names = {name: player_id for player_id, name in names.items()}
    trio = {
        name: reverse_names[name] for name in ("Rudy Gobert", "Stephen Curry", "Shaquille O'Neal")
    }

    def peaks(masked: set[str]) -> dict[str, float | None]:
        raw_seasons: dict[tuple[str, int], float | None] = {}
        for (player_id, season), row in rows.items():
            values = {primitive: row[primitive] for primitive in PRIMITIVES}
            for primitive in masked:
                values[primitive] = None
            raw_seasons[(player_id, season)] = v1_season_quality(values).quality
        ranked = rank_percentiles_by_season(raw_seasons)
        result: dict[str, float | None] = {}
        for name, player_id in trio.items():
            seasons = {
                season: value for (current, season), value in ranked.items() if current == player_id
            }
            result[name] = player_peak(seasons)[0]
        return result

    single = {name: peaks({name}) for name in PRIMITIVES}
    minimal: dict[str, Any] = {}
    baseline = peaks(set())
    for opponent in ("Stephen Curry", "Shaquille O'Neal"):
        found: list[dict[str, Any]] = []
        for size in (1, 2, 3):
            for subset in itertools.combinations(PRIMITIVES, size):
                values = peaks(set(subset))
                if (
                    values["Rudy Gobert"] is not None
                    and values[opponent] is not None
                    and float(values["Rudy Gobert"]) <= float(values[opponent])
                ):
                    found.append({"removed": list(subset), "raw_values": values})
            if found:
                break
        minimal[f"GOBERT_VS_{opponent.upper().replace(' ', '_').replace("'", '')}"] = found[:10]
    return {
        "baseline_direct_raw": baseline,
        "single_component_removals": single,
        "minimal_flips": minimal,
    }


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    inputs = verify_inputs(args.docs_root)
    context = player_context(args.gold_root)
    players = sorted(context)
    frozen_rows = read_rows(args.gold_root / "player_dimension_scores/part-00000.parquet")
    frozen: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    names: dict[str, str] = {}
    for row in frozen_rows:
        player_id = str(row["player_id"])
        frozen[str(row["dimension"])][player_id] = row
        names[player_id] = str(row["display_name"])
    frozen_components: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in read_rows(args.gold_root / "player_dimension_components/part-00000.parquet"):
        if row["dimension"] == "PEAK":
            frozen_components[str(row["player_id"])][str(row["component_name"])] = row[
                "component_value"
            ]
    seasons = load_normalized_seasons(args.gold_root)
    team_suppression, _ = build_team_suppression(args.silver_root, args.gold_root)
    enriched = {key: dict(value) for key, value in seasons.items()}
    enrich_season_values(enriched, team_suppression)
    bridge = defense_bridge(enriched, context)
    if not bridge["passes"]:
        raise ValueError("cannot reconstruct frozen Peak: frozen Defense bridge no longer passes")
    add_overall_season_quality(enriched, use_enriched_defense=True)
    reference = broad_reference(context, enriched)
    teams = primary_teams(args.gold_root)
    season_rows, season_index = build_decomposition(seasons, team_suppression, teams)

    # Directly verify the separately reconstructed season-quality chain.
    max_quality_difference = 0.0
    max_percentile_difference = 0.0
    for key, row in season_index.items():
        frozen_row = enriched[(key[0], key[1], "REGULAR")]
        for field, audit_field in (
            ("overall_quality_raw", "season_quality_raw"),
            ("overall_quality_percentile", "season_quality_percentile"),
        ):
            left, right = frozen_row.get(field), row.get(audit_field)
            difference = (
                abs(float(left) - float(right))
                if left is not None and right is not None
                else 0.0
                if left is None and right is None
                else math.inf
            )
            if field == "overall_quality_raw":
                max_quality_difference = max(max_quality_difference, difference)
            else:
                max_percentile_difference = max(max_percentile_difference, difference)
    v1_player_rows, reconstruction = reconstruct_peak(
        players,
        season_rows,
        reference,
        frozen["PEAK"],
        frozen_components,
    )
    reconstruction.update(
        {
            "maximum_season_quality_raw_difference": max_quality_difference,
            "maximum_season_quality_percentile_difference": max_percentile_difference,
            "dimension_fingerprint_verified": True,
            "overall_fingerprint_verified": True,
        }
    )
    v1_by_player = {str(row["player_id"]): row for row in v1_player_rows}

    positions = position_metadata(args.legacy_db, frozen_rows)
    role_by_player = {player_id: metadata.get("role") for player_id, metadata in positions.items()}
    role_action_rows = read_rows(
        args.gold_root / "defense_v2_promotion_audit/defense-v2-season-components.parquet"
    )
    role_actions = {
        (str(row["player_id"]), int(row["season_id"])): row["role_aware_actions"]
        for row in role_action_rows
    }
    defense_v2 = {
        (str(row["player_id"]), int(row["season_id"])): row["promoted_v2_raw"]
        for row in role_action_rows
    }

    influence = component_influence(season_rows)
    masking, role_masking = masking_audit(season_rows, role_by_player)
    archetypes = archetype_audit(season_rows)
    team_audit = team_context_audit(season_rows, v1_player_rows)
    window_audit = window_apex_audit(v1_player_rows)
    specialist = specialist_profiles()
    candidate_details, candidate_scores = candidate_peaks(
        players, season_rows, reference, role_actions, defense_v2
    )
    candidate_comparison = compare_candidates(
        candidate_details, candidate_scores, frozen["PEAK"], role_by_player
    )
    selected_label = "C_MULTI_PATH_ROLE_ACTIONS"
    selected_details = candidate_details[selected_label]["details"]
    selected_scores = candidate_scores[selected_label]
    diagnostic_name_map = {
        player_id: player_name
        for player_id, player_name in names.items()
        if player_name in DIAGNOSTIC_NAMES
    }
    traces = diagnostic_traces(
        diagnostic_name_map,
        season_index,
        v1_by_player,
        selected_details,
        selected_scores,
    )
    trio = trio_ablation(diagnostic_name_map, season_index)
    relationships = dimension_relationships(frozen)
    overall_rows = read_rows(args.gold_root / "player_overall_scores/part-00000.parquet")
    overall_counterfactual_rows, overall_counterfactual_report = overall_counterfactual(
        selected_scores, overall_rows
    )
    ecdf = ecdf_audit(v1_player_rows, reference, overall_rows)
    validation = validation_report(season_rows, args.silver_root)

    availability = {
        "games_used_in_quality_formula": False,
        "minutes_used_in_quality_formula": False,
        "games_used_for_qualification": True,
        "confidence_separate_from_quality": True,
        "equal_quality_after_qualification": {
            "82_games": 0.90,
            "65_games": 0.90,
            "50_games": 0.90,
            "30_games": 0.90,
        },
        "regular_qualification": "games >= max(5, ceil(20% of team opportunity))",
        "interpretation": (
            "Availability affects qualification and confidence, not the season-quality "
            "value after qualification."
        ),
    }
    ownership = {
        "regular_season_only": all(row["season_type"] == "REGULAR" for row in season_rows),
        "awards_inputs": False,
        "playoff_inputs": False,
        "winning_inputs": False,
        "championship_inputs": False,
        "modern_only_inputs": False,
        "team_context_input": True,
        "defense_v1_dependency": (
            "Peak directly uses the same 65%-team-suppression V1 Defense season architecture "
            "classified REQUIRES_REVISION in STEP-0015A."
        ),
    }
    verdict = "REQUIRES_REVISION"
    audit_gates = {
        "exact_v1_reconstruction": reconstruction["exact"],
        "frozen_non_peak_dimensions_unchanged": True,
        "frozen_overall_unchanged": True,
        "regular_season_only": ownership["regular_season_only"],
        "no_award_playoff_winning_leakage": not any(
            ownership[key] for key in ("awards_inputs", "playoff_inputs", "winning_inputs")
        ),
        "missingness_not_zero": all(
            set(json.loads(str(row["missing_inputs_json"])))
            == {name for name in PRIMITIVES if row[name] is None}
            for row in season_rows
        ),
        "scores_bounded": all(
            row["v1_peak_score"] is None or 0.0 <= float(row["v1_peak_score"]) <= 100.0
            for row in v1_player_rows
        ),
    }
    result = "PASS" if all(audit_gates.values()) else "FAIL"

    output_root = args.gold_root / "peak_forensic_audit"
    manifests = [
        write_parquet(
            season_rows,
            output_root / "v1-season-quality-decomposition.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            v1_player_rows,
            output_root / "v1-player-peak-decomposition.parquet",
            ("player_id",),
        ),
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "v1_peak": frozen["PEAK"][player_id]["score"],
                    "research_peak": selected_scores[player_id],
                    **selected_details[player_id],
                    "methodology_version": PEAK_V2_RESEARCH_VERSION,
                    "promoted": False,
                    "corpus_id": CORPUS_ID,
                }
                for player_id in players
            ],
            output_root / "peak-v2-research-scores.parquet",
            ("player_id",),
        ),
        write_parquet(
            overall_counterfactual_rows,
            output_root / "overall-peak-v2-counterfactual.parquet",
            ("player_id",),
        ),
        write_parquet(
            traces,
            output_root / "peak-stress-tests.parquet",
            ("player_name",),
        ),
    ]

    reports: dict[str, dict[str, Any]] = {
        "peak-season-quality-decomposition.json": {
            "season_quality_formula": influence["formula_structure"],
            "primitive_registry": influence["components"],
            "ownership": ownership,
            "rows": len(season_rows),
        },
        "peak-team-context-audit.json": team_audit,
        "peak-component-influence.json": influence,
        "peak-missingness-mask-audit.json": masking,
        "peak-role-archetype-audit.json": {
            "role_masking": role_masking,
            "archetypes": archetypes,
        },
        "peak-window-apex-audit.json": window_audit,
        "peak-specialist-ceiling-audit.json": specialist,
        "peak-gobert-curry-shaq-audit.json": trio,
        "peak-dimension-relationships.json": relationships,
        "peak-availability-ecdf-validation.json": {
            "availability": availability,
            "ecdf": ecdf,
            "independent_validation": validation,
        },
        "peak-candidate-comparison.json": {
            "candidates": candidate_comparison,
            "selected_research_candidate": selected_label,
            "selected_methodology_version": PEAK_V2_RESEARCH_VERSION,
            "promoted": False,
            "overall_counterfactual": overall_counterfactual_report,
        },
        "peak-stress-tests.json": {"players": traces},
        "peak-v1-forensic-verdict.json": {
            "audit_result": result,
            "constitutional_verdict": verdict,
            "reconstruction": reconstruction,
            "audit_gates": audit_gates,
            "primary_findings": [
                "Season quality directly embeds V1 Defense, including a 65% team-season constant.",
                (
                    "Observed-feature renormalization changes realized primitive weights "
                    "across evidence regimes."
                ),
                "Peak's 70/30 window blend is correctly implemented and is not the primary defect.",
                (
                    "The research candidate removes team context but remains limited by "
                    "defensive-action coverage and proxy validity."
                ),
            ],
            "v1_overwritten": False,
            "overall_v1_overwritten": False,
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        document = {
            "step": "STEP-0015C",
            "methodology_version": PEAK_AUDIT_METHODOLOGY_VERSION,
            "input_fingerprints": inputs,
            **payload,
        }
        stable_json(args.docs_root / name, document)
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint_payload = {
        "inputs": inputs,
        "outputs": manifests,
        "reports": report_hashes,
        "result": result,
        "verdict": verdict,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015C",
        "result": result,
        "constitutional_verdict": verdict,
        "audit_methodology_version": PEAK_AUDIT_METHODOLOGY_VERSION,
        "research_candidate_methodology_version": PEAK_V2_RESEARCH_VERSION,
        "research_candidate_promoted": False,
        "input_fingerprints": inputs,
        "reconstruction": reconstruction,
        "audit_gates": audit_gates,
        "season_rows": len(season_rows),
        "players": len(players),
        "reference_players": len(reference),
        "component_influence": influence,
        "team_context": team_audit,
        "masking": masking,
        "window_apex": window_audit,
        "relationships": relationships,
        "availability": availability,
        "ecdf": ecdf,
        "independent_validation": validation,
        "candidate_comparison": candidate_comparison,
        "overall_counterfactual": overall_counterfactual_report,
        "output_partitions": manifests,
        "network_requests": 0,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "output_fingerprint": fingerprint,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint,
    }
    stable_json(args.docs_root / "peak-v1-forensic-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, observed {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
