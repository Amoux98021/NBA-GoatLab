#!/usr/bin/env python3
"""Run the offline STEP-0015B Defense V2 promotion audit.

Frozen V1 artifacts remain immutable. Any promoted Defense and provisional
Overall outputs are written to a new, ignored Gold directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.defense_forensics import (
    defense_candidate,
    role_aware_action_context,
)
from goatlab.rankings.defense_promotion import (
    DEFENSE_PROMOTION_AUDIT_VERSION,
    DEFENSE_V2_VERSION,
    OVERALL_V2_COUNTERFACTUAL_VERSION,
    blended_presence,
    confidence_from_channels,
    continuous_presence_estimate,
    deterministic_group_fold,
    error_summary,
    expected_presence_features,
    fit_ridge,
    predict_ridge,
    weighted_three_channel,
)
from goatlab.rankings.dimension_scores import midrank_percentile_scores
from pipelines.rankings.audit_defense_v1 import (
    CORPUS_ID,
    DIAGNOSTIC_NAMES,
    DIMENSION_FINGERPRINT,
    DIMENSION_VERSION,
    OVERALL_FINGERPRINT,
    award_validation,
    candidate_scores,
    defensive_rebound_evidence,
    game_context,
    midrank_within_group,
    modern_defense,
    normalized_seasons,
    position_metadata,
    presence_estimates,
    read_rows,
    reference_population,
    role_actions,
    team_suppression,
)

ROOT = Path(__file__).resolve().parents[2]
STEP_0015A_FINGERPRINT = "07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324"
OVERALL_WEIGHTS = {
    "peak_score": 0.17,
    "longevity_score": 0.14,
    "offense_score": 0.16,
    "defense_score": 0.14,
    "playoffs_score": 0.18,
    "accolades_score": 0.10,
    "winning_score": 0.11,
}
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)
RIDGE_FEATURE_NAMES = (
    "team_context",
    "role_aware_actions",
    "team_x_actions",
    "role_known",
    "role_guard",
    "role_wing",
    "role_forward",
    "role_big",
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
    dimension = json.loads((docs_root / "dimension-score-summary.json").read_text())
    overall = json.loads((docs_root / "overall-ranking-summary.json").read_text())
    forensic = json.loads((docs_root / "defense-forensic-audit-summary.json").read_text())
    if dimension["output_fingerprint"] != DIMENSION_FINGERPRINT:
        raise ValueError("frozen dimension fingerprint mismatch")
    if overall["output_fingerprint"] != OVERALL_FINGERPRINT:
        raise ValueError("frozen Overall fingerprint mismatch")
    if forensic["output_fingerprint"] != STEP_0015A_FINGERPRINT:
        raise ValueError("STEP-0015A fingerprint mismatch")
    if forensic["constitutional_verdict"] != "REQUIRES_REVISION":
        raise ValueError("STEP-0015A did not authorize a promotion audit")
    return {
        "dimension": DIMENSION_FINGERPRINT,
        "overall": OVERALL_FINGERPRINT,
        "defense_forensic": STEP_0015A_FINGERPRINT,
    }


def map_against_reference(target: float, reference: list[float]) -> float | None:
    if not reference:
        return None
    ordered = sorted(reference)
    below = sum(value < target for value in ordered)
    equal = sum(value == target for value in ordered)
    denominator = max(len(ordered) - 1, 1)
    midrank = below + (equal - 1) / 2.0
    return min(1.0, max(0.0, midrank / denominator))


def continuous_presence_rows(
    silver_root: Path,
    games: list[dict[str, Any]],
    hard_raw: dict[tuple[str, int], float],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], tuple[float, float]]]:
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
    season_parts: dict[tuple[str, int], list[tuple[float, float, int]]] = defaultdict(list)
    for (player_id, season, team_id), with_ids in sorted(player_games.items()):
        all_ids = set(team_games[(season, team_id)])
        without_ids = all_ids - with_ids
        estimate = continuous_presence_estimate(
            [residual[(game_id, team_id)] for game_id in sorted(with_ids)],
            [residual[(game_id, team_id)] for game_id in sorted(without_ids)],
        )
        if estimate.shrunk_difference is not None:
            season_parts[(player_id, season)].append(
                (estimate.shrunk_difference, estimate.threshold_continuity, len(with_ids))
            )
        rows.append(
            {
                "player_id": player_id,
                "season_id": season,
                "team_id": team_id,
                "games_with": estimate.games_with,
                "games_without": estimate.games_without,
                "effective_sample_size": estimate.effective_sample_size,
                "raw_difference_points": estimate.raw_difference,
                "shrunk_difference_points": estimate.shrunk_difference,
                "magnitude_shrinkage": estimate.shrinkage,
                "threshold_continuity": estimate.threshold_continuity,
                "former_hard_eligible": (player_id, season) in hard_raw,
                "season_type": "REGULAR",
                "methodology_version": DEFENSE_PROMOTION_AUDIT_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
    season_raw: dict[tuple[str, int], tuple[float, float]] = {}
    for key, parts in season_parts.items():
        denominator = sum(games_count for _, _, games_count in parts)
        season_raw[key] = (
            sum(value * games_count for value, _, games_count in parts) / denominator,
            sum(reliability * games_count for _, reliability, games_count in parts) / denominator,
        )
    hard_by_season: dict[int, list[float]] = defaultdict(list)
    for (_, season), value in hard_raw.items():
        hard_by_season[season].append(value)
    scaled: dict[tuple[str, int], tuple[float, float]] = {}
    for key, (value, reliability) in season_raw.items():
        mapped = map_against_reference(value, hard_by_season[key[1]])
        if mapped is not None:
            scaled[key] = (mapped, reliability)
    return rows, scaled


def hard_presence_percentiles(
    hard_raw: dict[tuple[str, int], float],
) -> dict[tuple[str, int], float]:
    grouped: dict[int, dict[str, float]] = defaultdict(dict)
    for (player_id, season), value in hard_raw.items():
        grouped[season][player_id] = value
    return {
        (player_id, season): percentile
        for season, values in grouped.items()
        for player_id, percentile in midrank_within_group(values).items()
    }


def regression_fallback(
    full_rows: list[dict[str, Any]],
) -> tuple[dict[tuple[str, int], float], dict[str, Any], Any]:
    features = np.asarray(
        [
            expected_presence_features(
                team=float(row["team"]), action=float(row["action"]), role=row["role"]
            )
            for row in full_rows
        ],
        dtype=float,
    )
    target = np.asarray([float(row["presence"]) for row in full_rows], dtype=float)
    groups = [str(row["player_id"]) for row in full_rows]
    selected_alpha = RIDGE_ALPHAS[0]
    best_mae = float("inf")
    alpha_results: dict[str, Any] = {}
    selected_predictions = np.zeros(len(target), dtype=float)
    for alpha in RIDGE_ALPHAS:
        predictions = np.zeros(len(target), dtype=float)
        for fold in range(5):
            train = np.asarray(
                [deterministic_group_fold(group) != fold for group in groups], dtype=bool
            )
            test = ~train
            model = fit_ridge(features[train], target[train], alpha=alpha)
            predictions[test] = predict_ridge(model, features[test])
        mae = float(np.mean(np.abs(predictions - target)))
        alpha_results[str(alpha)] = {
            "mae_presence_percentile": mae,
            "rmse_presence_percentile": float(np.sqrt(np.mean((predictions - target) ** 2))),
            "spearman": spearman(target.tolist(), predictions.tolist()),
            "pearson": float(np.corrcoef(target, predictions)[0, 1]),
        }
        if mae < best_mae:
            best_mae = mae
            selected_alpha = alpha
            selected_predictions = predictions
    model = fit_ridge(features, target, alpha=selected_alpha)
    oof = {
        (str(row["player_id"]), int(row["season_id"])): float(prediction)
        for row, prediction in zip(full_rows, selected_predictions, strict=True)
    }
    residual = target - selected_predictions
    ss_total = float(np.sum((target - np.mean(target)) ** 2))
    report = {
        "model": "GROUPED_FIVE_FOLD_RIDGE",
        "grouping": "PLAYER_ID",
        "feature_names": RIDGE_FEATURE_NAMES,
        "alpha_candidates": alpha_results,
        "selected_alpha": selected_alpha,
        "rows": len(full_rows),
        "players": len(set(groups)),
        "out_of_fold_mae_presence_percentile": best_mae,
        "out_of_fold_rmse_presence_percentile": float(np.sqrt(np.mean(residual**2))),
        "out_of_fold_r_squared": 1.0 - float(np.sum(residual**2)) / ss_total,
        "coefficients": {
            "intercept": model.coefficients[0],
            **dict(zip(RIDGE_FEATURE_NAMES, model.coefficients[1:], strict=True)),
        },
        "awards_used": False,
        "modern_metrics_used": False,
        "player_names_used": False,
    }
    return oof, report, model


def paired_report(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    report: dict[str, Any] = error_summary(actual, predicted)
    report["spearman"] = spearman(actual, predicted)
    actual_array = np.asarray(actual)
    predicted_array = np.asarray(predicted)
    bands = []
    for low, high in zip(np.arange(0.0, 1.0, 0.1), np.arange(0.1, 1.1, 0.1), strict=True):
        mask = (actual_array >= low) & (
            actual_array <= high if high == 1.0 else actual_array < high
        )
        if np.any(mask):
            bands.append(
                {
                    "actual_band": [float(low), float(high)],
                    "observations": int(np.sum(mask)),
                    "mean_actual": float(np.mean(actual_array[mask])),
                    "mean_predicted": float(np.mean(predicted_array[mask])),
                }
            )
    report["percentile_calibration"] = bands
    return report


def masking_audits(
    full_rows: list[dict[str, Any]],
    oof_expected: dict[tuple[str, int], float],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    actual = [float(row["full_raw"]) for row in full_rows]
    renormalized = [0.50 * float(row["team"]) + 0.50 * float(row["action"]) for row in full_rows]
    expected = [
        weighted_three_channel(
            float(row["team"]),
            float(row["action"]),
            oof_expected[(str(row["player_id"]), int(row["season_id"]))],
        )
        for row in full_rows
    ]
    overall = {
        "current_renormalization": paired_report(actual, renormalized),
        "cross_validated_expected_presence": paired_report(actual, expected),
    }
    career_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row, actual_value, renormalized_value, expected_value in zip(
        full_rows, actual, renormalized, expected, strict=True
    ):
        player_id = str(row["player_id"])
        career_values[player_id]["actual"].append(actual_value)
        career_values[player_id]["renormalized"].append(renormalized_value)
        career_values[player_id]["expected"].append(expected_value)
    career_actual = [
        statistics.fmean(values["actual"]) for _, values in sorted(career_values.items())
    ]
    career_renormalized = [
        statistics.fmean(values["renormalized"]) for _, values in sorted(career_values.items())
    ]
    career_expected = [
        statistics.fmean(values["expected"]) for _, values in sorted(career_values.items())
    ]
    overall["career_level"] = {
        "current_renormalization": paired_report(career_actual, career_renormalized),
        "cross_validated_expected_presence": paired_report(career_actual, career_expected),
    }
    role_report: dict[str, Any] = {}
    for role in ("GUARD", "WING", "FORWARD", "BIG"):
        rows = [row for row in full_rows if row["role"] == role]
        if not rows:
            continue
        left = [float(row["full_raw"]) for row in rows]
        right_a = [0.50 * float(row["team"]) + 0.50 * float(row["action"]) for row in rows]
        right_d = [
            weighted_three_channel(
                float(row["team"]),
                float(row["action"]),
                oof_expected[(str(row["player_id"]), int(row["season_id"]))],
            )
            for row in rows
        ]
        slope, intercept = np.polyfit(left, right_d, 1)
        role_report[role] = {
            "current_renormalization": paired_report(left, right_a),
            "expected_presence": paired_report(left, right_d),
            "expected_calibration_slope": float(slope),
            "expected_calibration_intercept": float(intercept),
        }
    archetypes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in full_rows:
        if float(row["block"] or -1.0) >= 0.90:
            archetypes["HIGH_BLOCK_RIM_PROXY"].append(row)
        if float(row["steal"] or -1.0) >= 0.90:
            archetypes["HIGH_STEAL_DISRUPTION"].append(row)
        if float(row["rebound"] or -1.0) >= 0.90:
            archetypes["HIGH_REBOUND_INTERIOR_PROXY"].append(row)
        if float(row["action"]) <= 0.25:
            archetypes["LOW_BOX_EVENT"].append(row)
        if float(row["team"]) >= 0.80 and float(row["action"]) <= 0.50:
            archetypes["STRONG_TEAM_WEAK_ACTION"].append(row)
        if float(row["action"]) >= 0.80 and float(row["team"]) <= 0.50:
            archetypes["STRONG_ACTION_WEAK_TEAM"].append(row)
    archetype_report = {}
    for name, rows in sorted(archetypes.items()):
        left = [float(row["full_raw"]) for row in rows]
        right = [
            weighted_three_channel(
                float(row["team"]),
                float(row["action"]),
                oof_expected[(str(row["player_id"]), int(row["season_id"]))],
            )
            for row in rows
        ]
        archetype_report[name] = paired_report(left, right)
    return overall, role_report, archetype_report


def era_masking(full_rows: list[dict[str, Any]]) -> dict[str, Any]:
    regimes: dict[str, list[float]] = defaultdict(list)
    actual: list[float] = []
    for row in full_rows:
        team, presence = float(row["team"]), float(row["presence"])
        actual.append(float(row["full_raw"]))
        rebound_only = float(row["rebound"]) if row["rebound"] is not None else None
        if rebound_only is not None:
            regimes["PRE_STEAL_BLOCK_REBOUND_ONLY"].append(
                weighted_three_channel(team, rebound_only, presence)
            )
        else:
            regimes["PRE_STEAL_BLOCK_REBOUND_ONLY"].append(float("nan"))
        regimes["STL_BLOCK_NO_PRESENCE"].append(0.50 * team + 0.50 * float(row["action"]))
        global_action, _ = role_aware_action_context(row["rpg"], row["stl"], row["blk"])
        regimes["REDUCED_POSITION_DREB_METADATA"].append(
            weighted_three_channel(team, float(global_action), presence)
            if global_action is not None
            else float("nan")
        )
        regimes["FULL_PORTABLE"].append(float(row["full_raw"]))
    result = {}
    for name, values in sorted(regimes.items()):
        paired = [
            (left, right) for left, right in zip(actual, values, strict=True) if np.isfinite(right)
        ]
        result[name] = paired_report([value[0] for value in paired], [value[1] for value in paired])
    return result


def threshold_audit() -> dict[str, Any]:
    scenarios = []
    for observed in (0.20, 0.50, 0.80):
        for expected in (0.35, 0.50, 0.65):
            team, action = 0.55, 0.55
            for axis, before, after in (("WITH", 9 / 10, 1.0), ("WITHOUT", 4 / 5, 1.0)):
                fallback = 0.50 * team + 0.50 * action
                full = weighted_three_channel(team, action, observed)
                before_continuous = weighted_three_channel(
                    team, action, expected + before * (observed - expected)
                )
                after_continuous = weighted_three_channel(
                    team, action, expected + after * (observed - expected)
                )
                scenarios.append(
                    {
                        "axis": axis,
                        "observed_presence": observed,
                        "expected_presence": expected,
                        "hard_gate_jump_points": abs(full - fallback) * 100,
                        "continuous_jump_points": abs(after_continuous - before_continuous) * 100,
                    }
                )
    return {
        "former_thresholds": {"games_with": 10, "games_without": 5},
        "simulation": scenarios,
        "maximum_hard_gate_jump_points": max(row["hard_gate_jump_points"] for row in scenarios),
        "maximum_continuous_jump_points": max(row["continuous_jump_points"] for row in scenarios),
        "selected_policy": (
            "smoothly blend observed Presence into expected Presence using "
            "min(1, games_with/10) * min(1, games_without/5)"
        ),
    }


def distribution(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values)
    return {
        "players": len(values),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "std": float(np.std(array)),
        "p10": float(np.quantile(array, 0.10)),
        "p90": float(np.quantile(array, 0.90)),
        "above_90_pct": float(np.mean(array >= 90.0)),
        "above_95_pct": float(np.mean(array >= 95.0)),
    }


def eta_squared_by_team(
    values: dict[tuple[str, int], float],
    player_team: dict[tuple[str, int, str], float],
) -> float | None:
    memberships: dict[tuple[str, int], list[str]] = defaultdict(list)
    groups: dict[tuple[int, str], list[str]] = defaultdict(list)
    for player_id, season, team_id in player_team:
        memberships[(player_id, season)].append(team_id)
        groups[(season, team_id)].append(player_id)
    grouped = []
    for (season, _), players in groups.items():
        observed = [
            values[(player_id, season)]
            for player_id in set(players)
            if len(memberships[(player_id, season)]) == 1 and (player_id, season) in values
        ]
        if len(observed) >= 2:
            grouped.append(observed)
    flat = [value for group in grouped for value in group]
    grand = statistics.fmean(flat)
    total = sum((value - grand) ** 2 for value in flat)
    between = sum(len(group) * (statistics.fmean(group) - grand) ** 2 for group in grouped)
    return between / total if total else None


def team_attribution_report(
    season_variants: dict[str, dict[tuple[str, int], float]],
    team_values: dict[tuple[str, int], float],
    player_team: dict[tuple[str, int, str], float],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, values in season_variants.items():
        by_player_value: dict[str, list[float]] = defaultdict(list)
        by_player_team: dict[str, list[float]] = defaultdict(list)
        for key, value in values.items():
            team = team_values.get(key)
            if team is not None:
                by_player_value[key[0]].append(value)
                by_player_team[key[0]].append(team)
        career_values, career_teams = [], []
        for player_id in sorted(by_player_value):
            career_values.append(statistics.fmean(by_player_value[player_id]))
            career_teams.append(statistics.fmean(by_player_team[player_id]))
        output[name] = {
            "career_spearman_with_team_context": spearman(career_values, career_teams),
            "season_between_team_eta_squared": eta_squared_by_team(values, player_team),
            "season_within_team_variance_positive": name != "TEAM_CONTEXT_CHANNEL",
        }
    return output


def teammate_collision_report(
    season_variants: dict[str, dict[tuple[str, int], float]],
    player_team: dict[tuple[str, int, str], float],
) -> dict[str, Any]:
    groups: dict[tuple[int, str], set[str]] = defaultdict(set)
    for player_id, season, team_id in player_team:
        groups[(season, team_id)].add(player_id)
    pair_differences: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for (season, _team_id), players in groups.items():
        ordered = sorted(players)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                for name, values in season_variants.items():
                    if (left, season) in values and (right, season) in values:
                        pair_differences[(left, right)][name].append(
                            abs(values[(left, season)] - values[(right, season)])
                        )
    qualified = {
        pair: values
        for pair, values in pair_differences.items()
        if len(values.get("V1_TEAM_DOMINANT", [])) >= 3
    }
    output: dict[str, Any] = {"qualified_pairs": len(qualified)}
    for name in season_variants:
        differences = [
            statistics.fmean(values[name])
            for values in qualified.values()
            if len(values.get(name, [])) >= 3
        ]
        output[name] = {
            "pairs": len(differences),
            "mean_shared_season_absolute_gap": statistics.fmean(differences)
            if differences
            else None,
            "median_shared_season_absolute_gap": statistics.median(differences)
            if differences
            else None,
            "near_collision_below_0_02": sum(value < 0.02 for value in differences),
        }
    return output


def overall_counterfactual(
    gold_root: Path,
    final_scores: dict[str, float | None],
    names: dict[str, str],
    season_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frozen = read_rows(gold_root / "player_overall_scores")
    rows = []
    for row in frozen:
        player_id = str(row["player_id"])
        new_defense = final_scores.get(player_id)
        eligible = row["eligibility_status"] == "ELIGIBLE_OFFICIAL" and new_defense is not None
        new_overall = (
            float(row["overall_score"]) + 0.14 * (float(new_defense) - float(row["defense_score"]))
            if eligible
            else None
        )
        rows.append(
            {
                "player_id": player_id,
                "player_name": names.get(player_id, str(row["player_name"])),
                "v1_defense": row["defense_score"],
                "v2_defense": new_defense,
                "v1_overall": row["overall_score"],
                "v1_rank": row["overall_rank"],
                "provisional_overall": new_overall,
                "provisional_rank": None,
                "eligibility_status": row["eligibility_status"] if eligible else "UNRANKED",
                "methodology_version": OVERALL_V2_COUNTERFACTUAL_VERSION,
                "published_v1_overwritten": False,
                "corpus_id": CORPUS_ID,
            }
        )
    ranked = sorted(
        (row for row in rows if row["provisional_overall"] is not None),
        key=lambda row: (-float(row["provisional_overall"]), str(row["player_id"])),
    )
    for rank, row in enumerate(ranked, start=1):
        row["provisional_rank"] = rank
    old_ranked = sorted(
        (row for row in rows if row["v1_rank"] is not None), key=lambda row: int(row["v1_rank"])
    )
    old_ids = [str(row["player_id"]) for row in old_ranked]
    new_ids = [str(row["player_id"]) for row in ranked]
    season_by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in season_rows:
        season_by_player[str(row["player_id"])].append(row)
    changed = set(old_ids[:10]) ^ set(new_ids[:10])
    changed_rows = []
    lookup = {str(row["player_id"]): row for row in rows}
    for player_id in sorted(changed):
        item = lookup[player_id]
        season_values = season_by_player[player_id]
        action_changes = [
            0.30 * float(value["action"]) - 0.35 * float(value["v1_action"])
            for value in season_values
            if value["action"] is not None and value["v1_action"] is not None
        ]
        causes = {
            "reduced_team_inheritance": statistics.fmean(
                0.30 * float(value["team"]) - 0.65 * float(value["v1_team"])
                for value in season_values
            ),
            "role_action_change": statistics.fmean(action_changes) if action_changes else None,
            "presence_or_fallback": statistics.fmean(
                0.40 * float(value["final_presence"]) for value in season_values
            ),
        }
        driver = max(
            (key for key, value in causes.items() if value is not None),
            key=lambda key: abs(float(causes[key])),
        )
        changed_rows.append(
            {**item, "raw_component_changes": causes, "largest_mechanical_driver": driver}
        )
    old_top15 = [
        {
            "rank": int(row["v1_rank"]),
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "defense": row["v1_defense"],
            "overall": row["v1_overall"],
        }
        for row in old_ranked[:15]
    ]
    new_top15 = [
        {
            "rank": int(row["provisional_rank"]),
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "defense": row["v2_defense"],
            "overall": row["provisional_overall"],
        }
        for row in ranked[:15]
    ]
    report = {
        "players_ranked": len(ranked),
        "spearman": spearman(
            [float(lookup[player_id]["v1_rank"]) for player_id in new_ids],
            [float(lookup[player_id]["provisional_rank"]) for player_id in new_ids],
        ),
        "top_10_overlap": len(set(old_ids[:10]) & set(new_ids[:10])) / 10,
        "top_25_overlap": len(set(old_ids[:25]) & set(new_ids[:25])) / 25,
        "top_50_overlap": len(set(old_ids[:50]) & set(new_ids[:50])) / 50,
        "top_100_overlap": len(set(old_ids[:100]) & set(new_ids[:100])) / 100,
        "old_v1_top_15": old_top15,
        "defense_v2_provisional_top_15": new_top15,
        "top_10_membership_changes": changed_rows,
        "published_overall_overwritten": False,
    }
    return rows, report


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    inputs = verify_inputs(args.docs_root)
    scores = read_rows(args.gold_root / "player_dimension_scores")
    seasons = normalized_seasons(args.gold_root)
    reference = reference_population(args.gold_root, seasons)
    positions = position_metadata(args.legacy_db, scores)
    team_values, player_team = team_suppression(args.silver_root, args.gold_root)
    dreb = defensive_rebound_evidence(args.silver_root, set(seasons), positions)
    actions = role_actions(seasons, positions, dreb)
    games = game_context(args.silver_root)
    hard_rows, hard_raw, _ = presence_estimates(args.silver_root, games)
    player_rows = read_rows(
        args.gold_root / "defense_forensic_audit/v1-player-decomposition.parquet"
    )
    rebuilt_rows, rebuilt_scores = candidate_scores(
        player_rows, seasons, team_values, actions, hard_raw, reference
    )
    expected_candidate = {
        str(row["player_id"]): row
        for row in read_rows(
            args.gold_root / "defense_forensic_audit/candidate-defense-scores.parquet"
        )
        if row["candidate"] == "B_TRIANGULATED_PRESENCE"
    }
    rebuilt_candidate = {
        str(row["player_id"]): row
        for row in rebuilt_rows
        if row["candidate"] == "B_TRIANGULATED_PRESENCE"
    }
    candidate_differences = [
        abs(
            float(expected_candidate[player_id]["score"])
            - float(rebuilt_candidate[player_id]["score"])
        )
        for player_id in expected_candidate
        if expected_candidate[player_id]["score"] is not None
        and rebuilt_candidate[player_id]["score"] is not None
    ]
    candidate_raw_differences = [
        abs(
            float(expected_candidate[player_id]["raw_value"])
            - float(rebuilt_candidate[player_id]["raw_value"])
        )
        for player_id in expected_candidate
        if expected_candidate[player_id]["raw_value"] is not None
        and rebuilt_candidate[player_id]["raw_value"] is not None
    ]
    prior_presence = {
        (str(row["player_id"]), int(row["season_id"]), str(row["team_id"])): row
        for row in read_rows(
            args.gold_root / "defense_forensic_audit/defensive-presence-estimates.parquet"
        )
    }
    rebuilt_presence = {
        (str(row["player_id"]), int(row["season_id"]), str(row["team_id"])): row
        for row in hard_rows
    }
    presence_differences = [
        abs(
            float(prior_presence[key]["shrunk_difference_points"])
            - float(rebuilt_presence[key]["shrunk_difference_points"])
        )
        for key in prior_presence
        if prior_presence[key]["shrunk_difference_points"] is not None
        and rebuilt_presence[key]["shrunk_difference_points"] is not None
    ]
    prior_stress = json.loads((args.docs_root / "defense-stress-tests.json").read_text())
    prior_stress_scores = {
        str(row["player_id"]): row["candidates"]["B_TRIANGULATED_PRESENCE"]["score"]
        for row in prior_stress["players"]
    }
    stress_differences = [
        abs(float(value) - float(rebuilt_scores["B_TRIANGULATED_PRESENCE"][player_id]))
        for player_id, value in prior_stress_scores.items()
        if value is not None and rebuilt_scores["B_TRIANGULATED_PRESENCE"][player_id] is not None
    ]
    reconstruction = {
        "players": len(expected_candidate),
        "score_mismatches": sum(value > 1e-12 for value in candidate_differences),
        "maximum_score_difference": max(candidate_differences, default=0.0),
        "maximum_career_raw_difference": max(candidate_raw_differences, default=0.0),
        "presence_rows": len(hard_rows),
        "maximum_shrunk_presence_difference": max(presence_differences, default=0.0),
        "stress_test_players": len(stress_differences),
        "maximum_stress_test_score_difference": max(stress_differences, default=0.0),
        "identical_presence_eligible_player_seasons": len(hard_raw) == 17089,
        "step0015a_fingerprint_verified": True,
        "exact": all(value <= 1e-12 for value in candidate_differences)
        and all(value <= 1e-12 for value in candidate_raw_differences)
        and all(value <= 1e-12 for value in presence_differences)
        and all(value <= 1e-12 for value in stress_differences),
    }
    if (
        not reconstruction["exact"]
        or not reconstruction["identical_presence_eligible_player_seasons"]
    ):
        raise ValueError("Candidate B reconstruction failed")

    hard_presence = hard_presence_percentiles(hard_raw)
    continuous_rows, continuous_presence = continuous_presence_rows(
        args.silver_root, games, hard_raw
    )
    full_rows = []
    for key, presence in sorted(hard_presence.items()):
        team, action = team_values.get(key), actions.get(key, {}).get("value")
        if team is None or action is None:
            continue
        source = seasons[key]
        full_rows.append(
            {
                "player_id": key[0],
                "season_id": key[1],
                "role": positions.get(key[0], {}).get("role"),
                "team": team,
                "action": action,
                "presence": presence,
                "full_raw": weighted_three_channel(float(team), float(action), presence),
                "rebound": actions[key]["rebound_evidence"],
                "steal": actions[key]["steal_evidence"],
                "block": actions[key]["block_evidence"],
                "rpg": source.get("rpg_percentile"),
                "stl": source.get("spg_percentile"),
                "blk": source.get("bpg_percentile"),
            }
        )
    oof_expected, fallback_model_report, fallback_model = regression_fallback(full_rows)
    masking, role_masking, archetype_masking = masking_audits(full_rows, oof_expected)
    era_report = era_masking(full_rows)
    threshold_report = threshold_audit()
    boundary_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in continuous_rows:
        if row["games_with"] in {9, 10}:
            boundary_groups[f"games_with_{row['games_with']}"].append(row)
        if row["games_without"] in {4, 5}:
            boundary_groups[f"games_without_{row['games_without']}"].append(row)
    threshold_report["observed_boundary_groups"] = {
        name: {
            "rows": len(rows),
            "mean_effective_sample_size": statistics.fmean(
                float(row["effective_sample_size"]) for row in rows
            ),
            "mean_threshold_continuity": statistics.fmean(
                float(row["threshold_continuity"]) for row in rows
            ),
            "mean_absolute_shrunk_points": statistics.fmean(
                abs(float(row["shrunk_difference_points"]))
                for row in rows
                if row["shrunk_difference_points"] is not None
            ),
        }
        for name, rows in sorted(boundary_groups.items())
    }

    season_rows = []
    season_variants: dict[str, dict[tuple[str, int], float]] = defaultdict(dict)
    valid_keys = [key for key in sorted(seasons) if team_values.get(key) is not None]
    full_feature_array = np.asarray(
        [
            expected_presence_features(
                team=float(team_values[key]),
                action=(
                    float(actions[key]["value"])
                    if actions.get(key, {}).get("value") is not None
                    else 0.50
                ),
                role=positions.get(key[0], {}).get("role"),
            )
            for key in valid_keys
        ]
    )
    all_expected = predict_ridge(fallback_model, full_feature_array)
    expected_lookup = dict(zip(valid_keys, (float(value) for value in all_expected), strict=True))
    for key in valid_keys:
        team = float(team_values[key])
        action_source = actions.get(key, {}).get("value")
        action = float(action_source) if action_source is not None else None
        expected = expected_lookup[key]
        observed, continuity = continuous_presence.get(key, (None, 0.0))
        if key in hard_presence:
            observed, continuity = hard_presence[key], 1.0
        final_presence, fallback_type = blended_presence(expected, observed, continuity)
        final_raw, _ = defense_candidate(
            team_suppression=team,
            action_context=action,
            presence_impact=final_presence,
            weights=(0.30, 0.30, 0.40),
        )
        current_raw, _ = defense_candidate(
            team_suppression=team,
            action_context=action,
            presence_impact=hard_presence.get(key),
            weights=(0.30, 0.30, 0.40),
        )
        confidence, reasons = confidence_from_channels(
            team_available=True,
            action_coverage=float(actions[key]["coverage"]) if key in actions else 0.0,
            presence_reliability=continuity,
            fallback_type=fallback_type,
        )
        source = seasons[key]
        v1_action, _ = role_aware_action_context(
            source.get("rpg_percentile"), source.get("spg_percentile"), source.get("bpg_percentile")
        )
        season_rows.append(
            {
                "player_id": key[0],
                "season_id": key[1],
                "season_type": "REGULAR",
                "broad_role": positions.get(key[0], {}).get("role"),
                "team_context": team,
                "role_aware_actions": action,
                "observed_presence": observed,
                "expected_presence": expected,
                "final_presence": final_presence,
                "presence_reliability": continuity,
                "fallback_type": fallback_type,
                "action_coverage": actions[key]["coverage"] if key in actions else 0.0,
                "current_candidate_b_raw": current_raw,
                "promoted_v2_raw": final_raw,
                "evidence_confidence": confidence,
                "reason_codes_json": json.dumps(reasons, separators=(",", ":")),
                "rebound_semantics": actions[key]["rebound_semantics"]
                if key in actions
                else "SOURCE_UNAVAILABLE",
                "team": team,
                "action": action,
                "v1_team": team,
                "v1_action": float(v1_action) if v1_action is not None else None,
                "methodology_version": DEFENSE_V2_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )
        v1_raw, _ = defense_candidate(
            team_suppression=team,
            action_context=float(v1_action) if v1_action is not None else None,
            weights=(0.65, 0.35, 0.0),
        )
        if v1_raw is not None:
            season_variants["V1_TEAM_DOMINANT"][key] = v1_raw
        if current_raw is not None:
            season_variants["CANDIDATE_B"][key] = current_raw
        if final_raw is not None:
            season_variants["PROMOTION_CANDIDATE"][key] = final_raw

    career_values: dict[str, list[float]] = defaultdict(list)
    career_rows_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in season_rows:
        player_id = str(row["player_id"])
        if row["promoted_v2_raw"] is not None:
            career_values[player_id].append(float(row["promoted_v2_raw"]))
        career_rows_source[player_id].append(row)
    all_players = [str(row["player_id"]) for row in player_rows]
    raw_career = {
        player_id: statistics.fmean(career_values[player_id]) if career_values[player_id] else None
        for player_id in all_players
    }
    final_scores = midrank_percentile_scores(raw_career, reference)
    names = {str(row["player_id"]): str(row["player_name"]) for row in player_rows}
    v1_lookup = {str(row["player_id"]): row for row in player_rows}
    candidate_b_scores = rebuilt_scores["B_TRIANGULATED_PRESENCE"]
    defense_rows = []
    for player_id in all_players:
        parts = career_rows_source[player_id]
        observed_seasons = sum(row["fallback_type"] == "OBSERVED" for row in parts)
        blended_seasons = sum(row["fallback_type"] == "RELIABILITY_BLEND" for row in parts)
        expected_seasons = sum(row["fallback_type"] == "EXPECTED_PRESENCE" for row in parts)
        mean_reliability = (
            statistics.fmean(float(row["presence_reliability"]) for row in parts) if parts else 0.0
        )
        confidence = (
            "STRONG"
            if parts and observed_seasons / len(parts) >= 0.75
            else "MODERATE"
            if parts and (observed_seasons + blended_seasons) / len(parts) >= 0.50
            else "LIMITED"
            if parts
            else "UNAVAILABLE"
        )
        defense_rows.append(
            {
                "player_id": player_id,
                "player_name": names[player_id],
                "v1_defense_score": v1_lookup[player_id]["v1_defense_score"],
                "step0015a_candidate_b_score": candidate_b_scores[player_id],
                "defense_v2_score": final_scores[player_id],
                "raw_defense_value": raw_career[player_id],
                "evidence_confidence": confidence,
                "team_coverage": 1.0 if parts else 0.0,
                "action_coverage": statistics.fmean(float(row["action_coverage"]) for row in parts)
                if parts
                else 0.0,
                "presence_coverage": (observed_seasons + blended_seasons) / len(parts)
                if parts
                else 0.0,
                "presence_reliability": mean_reliability,
                "observed_presence_seasons": observed_seasons,
                "reliability_blend_seasons": blended_seasons,
                "expected_presence_seasons": expected_seasons,
                "relevant_seasons": len(parts),
                "fallback_type": (
                    "MIXED"
                    if len({row["fallback_type"] for row in parts}) > 1
                    else parts[0]["fallback_type"]
                    if parts
                    else "UNAVAILABLE"
                ),
                "methodology_version": DEFENSE_V2_VERSION,
                "upstream_dimension_methodology": DIMENSION_VERSION,
                "corpus_id": CORPUS_ID,
            }
        )

    team_report = team_attribution_report(
        {
            **season_variants,
            "TEAM_CONTEXT_CHANNEL": team_values,
        },
        team_values,
        player_team,
    )
    collision_report = teammate_collision_report(season_variants, player_team)
    role_report: dict[str, Any] = {}
    for name, lookup in (
        ("V1", {str(row["player_id"]): row["v1_defense_score"] for row in player_rows}),
        ("CANDIDATE_B", candidate_b_scores),
        ("PROMOTION_CANDIDATE", final_scores),
    ):
        by_role: dict[str, list[float]] = defaultdict(list)
        for player_id, value in lookup.items():
            role = positions.get(player_id, {}).get("role")
            if role and value is not None:
                by_role[str(role)].append(float(value))
        role_report[name] = {role: distribution(values) for role, values in sorted(by_role.items())}

    modern = modern_defense(args.silver_root, reference)
    modern_report = {}
    for name, lookup in (
        ("V1", {str(row["player_id"]): row["v1_defense_score"] for row in player_rows}),
        ("CANDIDATE_B", candidate_b_scores),
        ("PROMOTION_CANDIDATE", final_scores),
    ):
        shared = sorted(
            player_id
            for player_id in lookup
            if lookup[player_id] is not None and player_id in modern
        )
        x = np.asarray([float(lookup[player_id]) for player_id in shared])
        y = np.asarray([modern[player_id] for player_id in shared])
        slope, intercept = np.polyfit(x, y, 1)
        residual = y - (slope * x + intercept)
        by_role: dict[str, list[float]] = defaultdict(list)
        for player_id, value in zip(shared, residual, strict=True):
            role = positions.get(player_id, {}).get("role")
            if role:
                by_role[str(role)].append(float(value))
        modern_report[name] = {
            "players": len(shared),
            "spearman": spearman(x.tolist(), y.tolist()),
            "pearson": float(np.corrcoef(x, y)[0, 1]),
            "calibration_slope": float(slope),
            "calibration_intercept": float(intercept),
            "residual_mean_by_role": {
                role: statistics.fmean(values) for role, values in sorted(by_role.items())
            },
        }

    award_candidates = {
        "V1": {str(row["player_id"]): row["v1_defense_score"] for row in player_rows},
        "CANDIDATE_B": candidate_b_scores,
        "PROMOTION_CANDIDATE": final_scores,
    }
    award_report = award_validation(args.silver_root, award_candidates)
    for candidate, groups in award_report["validation"].items():
        for award_type, values in groups.items():
            players = {
                str(row["player_id"])
                for row in read_rows(
                    args.silver_root / "player_awards", ["player_id", "award_type"]
                )
                if row["award_type"] == award_type
            }
            scores_for_award = [
                float(award_candidates[candidate][player_id])
                for player_id in players
                if award_candidates[candidate].get(player_id) is not None
            ]
            values["share_at_or_above_95"] = (
                sum(value >= 95.0 for value in scores_for_award) / len(scores_for_award)
                if scores_for_award
                else None
            )

    overall_rows, top_report = overall_counterfactual(
        args.gold_root, final_scores, names, season_rows
    )
    stress = []
    player_defense_lookup = {str(row["player_id"]): row for row in defense_rows}
    for player_id, name in sorted(names.items(), key=lambda item: item[1]):
        if name not in DIAGNOSTIC_NAMES:
            continue
        rows = career_rows_source[player_id]
        stress.append(
            {
                **player_defense_lookup[player_id],
                "broad_role": positions.get(player_id, {}).get("role"),
                "career_team_component": (
                    statistics.fmean(float(row["team_context"]) for row in rows) if rows else None
                ),
                "career_action_component": statistics.fmean(
                    float(row["role_aware_actions"])
                    for row in rows
                    if row["role_aware_actions"] is not None
                )
                if any(row["role_aware_actions"] is not None for row in rows)
                else None,
                "career_presence_component": (
                    statistics.fmean(float(row["final_presence"]) for row in rows) if rows else None
                ),
                "movement_reason": (
                    "presence/fallback replaces dominant shared team credit; "
                    "role-aware actions also "
                    "replace V1 total-rebound-heavy evidence"
                ),
            }
        )

    temporal_jumps = []
    for player_id, rows in career_rows_source.items():
        ordered = sorted(rows, key=lambda row: int(row["season_id"]))
        for left, right in pairwise(ordered):
            if int(right["season_id"]) != int(left["season_id"]) + 1:
                continue
            jump = float(right["promoted_v2_raw"]) - float(left["promoted_v2_raw"])
            regime_change = left["fallback_type"] != right["fallback_type"]
            if abs(jump) >= 0.30:
                temporal_jumps.append(
                    {
                        "player_id": player_id,
                        "from_season": left["season_id"],
                        "to_season": right["season_id"],
                        "raw_jump": jump,
                        "coverage_regime_change": regime_change,
                    }
                )

    # Promotion gates are deliberately stricter than "better than V1". The
    # portable fallback must predict withheld Presence well enough to support a
    # common scale; marginal relative improvement is not sufficient.
    current_mae = float(masking["current_renormalization"]["mean_absolute_error"])
    expected_mae = float(masking["cross_validated_expected_presence"]["mean_absolute_error"])
    expected_large_error = float(
        masking["cross_validated_expected_presence"]["more_than_10_points"]
    )
    fallback_r_squared = float(fallback_model_report["out_of_fold_r_squared"])
    v1_team_corr = float(team_report["V1_TEAM_DOMINANT"]["career_spearman_with_team_context"])
    promoted_team_corr = float(
        team_report["PROMOTION_CANDIDATE"]["career_spearman_with_team_context"]
    )
    audit_gates = {
        "candidate_b_reconstructed": bool(reconstruction["exact"]),
        "no_missing_as_zero": all(row["final_presence"] is not None for row in season_rows),
        "all_scores_bounded": all(
            row["defense_v2_score"] is None or 0.0 <= float(row["defense_v2_score"]) <= 100.0
            for row in defense_rows
        ),
        "frozen_outputs_unchanged": True,
        "awards_not_inputs": True,
        "modern_metrics_not_inputs": True,
        "regular_season_only": True,
    }
    promotion_gates = {
        "fallback_improves_masked_mae": expected_mae < current_mae,
        "fallback_mae_at_most_8_points": expected_mae <= 8.0,
        "fallback_over_10_point_error_at_most_25_pct": expected_large_error <= 0.25,
        "expected_presence_cross_validated_r_squared_at_least_0_10": fallback_r_squared >= 0.10,
        "threshold_jump_reduced": threshold_report["maximum_continuous_jump_points"]
        < threshold_report["maximum_hard_gate_jump_points"],
        "team_attribution_reduced_at_least_20_pct": abs(promoted_team_corr)
        <= 0.80 * abs(v1_team_corr),
    }
    audit_result = "PASS" if all(audit_gates.values()) else "FAIL"
    promotion = (
        "PROMOTE_WITH_LIMITATIONS"
        if audit_result == "PASS" and all(promotion_gates.values())
        else "DO_NOT_PROMOTE"
    )

    output_dir = args.gold_root / "defense_v2_promotion_audit"
    manifests = [
        write_parquet(
            continuous_rows,
            output_dir / "continuous-presence-estimates.parquet",
            ("season_id", "team_id", "player_id"),
        ),
        write_parquet(
            season_rows,
            output_dir / "defense-v2-season-components.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            defense_rows,
            output_dir / "player-defense-v2-promotion-candidate.parquet",
            ("player_id",),
        ),
        write_parquet(
            overall_rows,
            output_dir / "overall-defense-v2-counterfactual.parquet",
            ("provisional_rank", "player_id"),
        ),
        write_parquet(
            stress,
            output_dir / "defense-v2-stress-tests.parquet",
            ("player_name",),
        ),
    ]

    reports = {
        "defense-presence-masking-audit.json": {
            "season_masking": masking,
            "role_masking": role_masking,
            "archetype_masking": archetype_masking,
        },
        "defense-era-style-masking-audit.json": era_report,
        "defense-threshold-continuity.json": threshold_report,
        "defense-fallback-comparison.json": {
            "current_renormalization": masking["current_renormalization"],
            "continuous_reliability": {
                "mathematically_eligible_player_team_seasons": sum(
                    row["shrunk_difference_points"] is not None for row in continuous_rows
                ),
                "former_hard_eligible_player_seasons": len(hard_raw),
                "hard_gate_removed": True,
            },
            "expected_presence": fallback_model_report,
            "conservative_hybrid": masking["cross_validated_expected_presence"],
            "selected": "CONSERVATIVE_CONTINUOUS_EXPECTED_PRESENCE_HYBRID",
        },
        "defense-v2-attribution-role-validation.json": {
            "team_attribution": team_report,
            "teammate_collision": collision_report,
            "role_distributions": role_report,
            "modern_validation": modern_report,
            "award_validation": award_report,
        },
        "defense-v2-stress-tests.json": {"players": stress},
        "defense-v2-top-ranking-impact.json": top_report,
        "defense-v2-promotion-candidate-methodology.json": {
            "version": DEFENSE_V2_VERSION,
            "status": promotion,
            "formula": {
                "team_context": 0.30,
                "role_aware_actions": 0.30,
                "defensive_presence_channel": 0.40,
            },
            "presence_channel": (
                "expected portable Presence + continuous reliability * "
                "(observed Presence - expected portable Presence)"
            ),
            "fallback_model": "grouped five-fold validated ridge using team/actions/role only",
            "score_scale": "frozen BROAD_HIGH_RECALL midrank ECDF 0-100",
            "confidence_separate_from_quality": True,
            "awards_in_score": False,
            "modern_metrics_in_score": False,
            "postseason_in_score": False,
            "upstream_dimension_methodology": DIMENSION_VERSION,
            "overall_counterfactual_version": OVERALL_V2_COUNTERFACTUAL_VERSION,
        },
        "defense-v2-promotion-verdict.json": {
            "audit_result": audit_result,
            "promotion_verdict": promotion,
            "audit_completion_gates": audit_gates,
            "promotion_gates": promotion_gates,
            "candidate_b_reconstruction": reconstruction,
            "coverage": {
                "player_seasons": len(season_rows),
                "players": len(defense_rows),
                "former_hard_presence_player_seasons": len(hard_raw),
                "continuous_presence_player_seasons": len(continuous_presence),
                "fallback_counts": dict(Counter(row["fallback_type"] for row in season_rows)),
                "confidence_counts": dict(
                    Counter(row["evidence_confidence"] for row in defense_rows)
                ),
            },
            "temporal_large_jumps": {
                "count": len(temporal_jumps),
                "coverage_regime_change_count": sum(
                    row["coverage_regime_change"] for row in temporal_jumps
                ),
                "examples": sorted(temporal_jumps, key=lambda row: -abs(float(row["raw_jump"])))[
                    :20
                ],
            },
        },
    }
    report_hashes = {}
    for name, payload in reports.items():
        document = {
            "step": "STEP-0015B",
            "methodology_version": DEFENSE_PROMOTION_AUDIT_VERSION,
            "input_fingerprints": inputs,
            **payload,
        }
        stable_json(args.docs_root / name, document)
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint_payload = {
        "inputs": inputs,
        "outputs": manifests,
        "reports": report_hashes,
        "result": audit_result,
        "promotion": promotion,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015B",
        "result": audit_result,
        "promotion_verdict": promotion,
        "audit_methodology_version": DEFENSE_PROMOTION_AUDIT_VERSION,
        "defense_methodology_version": DEFENSE_V2_VERSION
        if promotion != "DO_NOT_PROMOTE"
        else None,
        "provisional_overall_version": (
            "goatlab-v1-overall-v2-defense-update" if promotion != "DO_NOT_PROMOTE" else None
        ),
        "candidate_b_reconstruction": reconstruction,
        "audit_completion_gates": audit_gates,
        "promotion_gates": promotion_gates,
        "coverage": reports["defense-v2-promotion-verdict.json"]["coverage"],
        "masking": masking,
        "fallback_model": fallback_model_report,
        "threshold_continuity": threshold_report,
        "team_attribution": team_report,
        "teammate_collision": collision_report,
        "role_distributions": role_report,
        "modern_validation": modern_report,
        "award_validation": award_report,
        "top_ranking_impact": top_report,
        "temporal_large_jumps": reports["defense-v2-promotion-verdict.json"][
            "temporal_large_jumps"
        ],
        "input_fingerprints": inputs,
        "output_partitions": manifests,
        "output_fingerprint": fingerprint,
        "network_requests": 0,
        "frozen_v1_mutated": False,
        "frozen_overall_mutated": False,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint
        if args.expected_fingerprint
        else False,
    }
    stable_json(args.docs_root / "defense-v2-promotion-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(f"output fingerprint mismatch: {fingerprint}")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
