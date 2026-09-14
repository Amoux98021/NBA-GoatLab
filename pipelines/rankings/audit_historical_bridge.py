#!/usr/bin/env python3
"""Run the offline STEP-0015E historical evidence bridge audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.defense_promotion import predict_ridge
from goatlab.rankings.historical_bridge import (
    BRIDGE_RANDOM_SEED,
    HISTORICAL_BRIDGE_AUDIT_VERSION,
    HISTORICAL_BRIDGE_RESEARCH_VERSION,
    clipped_interval,
    era_block_predictions,
    fit_full_ridge,
    fit_latent_measurement,
    grouped_oof_ridge,
    interval_metrics,
    latent_scores,
    polynomial_features,
    practical_gate,
    regression_metrics,
)
from goatlab.rankings.player_season_value import (
    combine_player_value,
    offensive_axis,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_v1 import (
    distribution,
    file_hash,
    rank_percentiles_by_season,
    stable_json,
    write_parquet,
)
from pipelines.rankings.audit_player_season_value import (
    build_candidates,
    candidate_row,
    career_counterfactuals,
    compare_scores,
    season_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
STEP_D_FINGERPRINT = "f96ee13b7aa7ba6101e2ad80b757cc28179a52b378cbd961ceb3f739bdcae282"
CORPUS_ID = "GOATLAB-HIST-V1"
CHANNELS = (
    "ppg",
    "ts_pct",
    "apg",
    "rpg",
    "spg",
    "bpg",
    "team_suppression",
    "role_aware_actions",
    "observed_presence",
)
EARLY_NAMES = (
    "Bill Russell",
    "Wilt Chamberlain",
    "Oscar Robertson",
    "Bob Pettit",
    "George Mikan",
    "Elgin Baylor",
    "Jerry West",
)
MODERN_NAMES = (
    "Michael Jordan",
    "LeBron James",
    "Stephen Curry",
    "Shaquille O'Neal",
    "Tim Duncan",
    "Kevin Garnett",
    "Rudy Gobert",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _features(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> npt.NDArray[np.float64]:
    return np.asarray(
        [polynomial_features([float(row[field]) for field in fields]) for row in rows],
        dtype=np.float64,
    )


def _global_percentiles(values: npt.NDArray[np.float64]) -> list[float]:
    """Return a deterministic midrank ECDF for a complete vector."""
    order = sorted(range(len(values)), key=lambda index: (float(values[index]), index))
    output = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        percentile = ((cursor + 1 + end) / 2.0 - 1.0) / max(1, len(order) - 1)
        for position in order[cursor:end]:
            output[position] = float(percentile)
        cursor = end
    return output


def _role_report(
    rows: list[dict[str, Any]], actual: list[float], predicted: list[float]
) -> tuple[dict[str, Any], float]:
    groups: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for row, left, right in zip(rows, actual, predicted, strict=True):
        role = str(row.get("broad_role") or "UNKNOWN")
        groups[role][0].append(left)
        groups[role][1].append(right)
    report = {
        role: regression_metrics(left, right)
        for role, (left, right) in sorted(groups.items())
        if len(left) >= 20
    }
    known_bias = [
        abs(float(value["mean_signed_error"]))
        for role, value in report.items()
        if role != "UNKNOWN"
    ]
    return report, max(known_bias, default=0.0)


def verify_step_d(docs_root: Path) -> dict[str, Any]:
    summary = cast(
        dict[str, Any],
        json.loads((docs_root / "player-season-value-summary.json").read_text()),
    )
    if summary.get("output_fingerprint") != STEP_D_FINGERPRINT:
        raise ValueError("STEP-0015D fingerprint mismatch")
    return summary


def reconstruction(
    base_rows: list[dict[str, Any]], gold_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates, summary = build_candidates(base_rows)
    rebuilt = [row for row in candidates if row["candidate"] == "D_REGIME_RELIABILITY"]
    frozen = read_rows(gold_root / "player_season_value_audit/player-season-value-research.parquet")
    index = {(str(row["player_id"]), int(row["season_id"])): row for row in frozen}
    maximum = 0.0
    mismatches = 0
    fields = (
        "player_season_value_raw",
        "player_season_value_percentile",
        "offense",
        "defense_evidence",
        "team_effective_weight",
    )
    for row in rebuilt:
        other = index[(str(row["player_id"]), int(row["season_id"]))]
        for field in fields:
            left, right = row.get(field), other.get(field)
            if left is None or right is None:
                mismatches += int(left is not right)
                continue
            difference = abs(float(left) - float(right))
            maximum = max(maximum, difference)
            mismatches += int(difference > 1e-12)
        mismatches += int(row["evidence_regime"] != other["evidence_regime"])
        mismatches += int(row["confidence"] != other["confidence"])
    return candidates, {
        "rows": len(rebuilt),
        "expected_rows": 22457,
        "scored_rows": sum(row["player_season_value_raw"] is not None for row in rebuilt),
        "expected_scored_rows": 16576,
        "maximum_numerical_difference": maximum,
        "mismatches": mismatches,
        "candidate_summary_matches": summary["D_REGIME_RELIABILITY"]["player_seasons"] == 16576,
    }


def missing_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_regime[str(row["evidence_regime"])].append(row)
    season_availability = {
        (season, channel): any(
            row.get(channel) is not None for row in rows if int(row["season_id"]) == season
        )
        for season in {int(row["season_id"]) for row in rows}
        for channel in CHANNELS
    }
    channel_notes = {
        "ppg": ("direct individual scoring-volume anchor", None),
        "ts_pct": ("derived individual efficiency", "PPG is not an efficiency proxy"),
        "apg": ("direct individual creation proxy", "PPG-only creation prediction is tested"),
        "rpg": ("individual total-rebound proxy", None),
        "spg": ("individual recorded action", None),
        "bpg": ("individual recorded action", None),
        "team_suppression": ("team-shared context", "not an individual substitute"),
        "role_aware_actions": (
            "individual role-conditioned action evidence",
            "RPG-only proxy tested",
        ),
        "observed_presence": (
            "individual WOWY-style proxy",
            "team/actions prediction previously weak",
        ),
    }
    output: dict[str, Any] = {}
    for regime, members in sorted(by_regime.items()):
        detail: dict[str, Any] = {}
        for channel in CHANNELS:
            missing = [row for row in members if row.get(channel) is None]
            seasons = [int(row["season_id"]) for row in missing]
            structural = sum(
                not season_availability[(int(row["season_id"]), channel)] for row in missing
            )
            semantics, proxy = channel_notes[channel]
            detail[channel] = {
                "missing_player_seasons": len(missing),
                "affected_players": len({str(row["player_id"]) for row in missing}),
                "first_affected_season": min(seasons) if seasons else None,
                "last_affected_season": max(seasons) if seasons else None,
                "structurally_unavailable_rows": structural,
                "sporadically_missing_rows": len(missing) - structural,
                "semantics": semantics,
                "proxy": proxy,
            }
        output[regime] = {
            "player_seasons": len(members),
            "players": len({str(row["player_id"]) for row in members}),
            "channels": detail,
        }
    early = by_regime["EARLY_LIMITED"]
    output["EARLY_LIMITED"]["unscorable_reasons"] = {
        "candidate_d_unscored": sum(
            candidate_row(row, "D_REGIME_RELIABILITY")["player_season_value_raw"] is None
            for row in early
        ),
        "creation_unavailable": sum(row.get("apg") is None for row in early),
        "individual_action_evidence_unavailable": sum(
            row.get("role_aware_actions") is None and row.get("action_value") is None
            for row in early
        ),
        "only_ppg_and_team_context_observed": sum(
            row.get("ppg") is not None
            and row.get("team_suppression") is not None
            and all(row.get(field) is None for field in ("ts_pct", "apg", "rpg", "spg", "bpg"))
            for row in early
        ),
    }
    return output


def creation_audit(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    observed = [row for row in rows if row.get("apg") is not None and row.get("ppg") is not None]
    y = np.asarray([float(row["apg"]) for row in observed])
    groups = [str(row["player_id"]) for row in observed]
    seasons = [int(row["season_id"]) for row in observed]
    c1 = np.asarray([float(row["ppg"]) for row in observed])
    x2 = _features(observed, ("ppg",))
    c2 = grouped_oof_ridge(x2, y, groups, alpha=2.0, salt="creation-player")
    era2, eligible2 = era_block_predictions(x2, y, seasons, alpha=2.0)
    rich = [row for row in observed if row.get("ts_pct") is not None]
    yr = np.asarray([float(row["apg"]) for row in rich])
    x3 = _features(rich, ("ppg", "ts_pct"))
    c3 = grouped_oof_ridge(
        x3, yr, [str(row["player_id"]) for row in rich], alpha=2.0, salt="creation-player"
    )
    era3, eligible3 = era_block_predictions(
        x3, yr, [int(row["season_id"]) for row in rich], alpha=2.0
    )
    random = grouped_oof_ridge(
        x2,
        y,
        [f"{row['player_id']}:{row['season_id']}" for row in observed],
        alpha=2.0,
        salt="creation-row",
    )
    report = {
        "target": "era-relative APG as an observed creation proxy, not total playmaking",
        "C1_DIRECT_PPG": regression_metrics(y.tolist(), c1.tolist()),
        "C2_PPG_GROUPED_RIDGE": regression_metrics(y.tolist(), c2.tolist()),
        "C2_PPG_RANDOM_ROW": regression_metrics(y.tolist(), random.tolist()),
        "C2_PPG_ERA_BLOCK": regression_metrics(y[eligible2].tolist(), era2[eligible2].tolist()),
        "C3_PPG_TS_GROUPED_RIDGE": regression_metrics(yr.tolist(), c3.tolist()),
        "C3_PPG_TS_ERA_BLOCK": regression_metrics(yr[eligible3].tolist(), era3[eligible3].tolist()),
        "group_leakage_control": "player IDs define grouped folds and are never predictors",
        "partial_identification": (
            "point estimates are rejected when downstream gates fail; intervals remain diagnostic"
        ),
    }
    model = fit_full_ridge(x2, y, alpha=2.0)
    return report, {"model": model, "oof": c2, "rows": observed}


def _full_validation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if all(
            row.get(field) is not None
            for field in (
                "ppg",
                "ts_pct",
                "apg",
                "rpg",
                "role_aware_actions",
                "team_suppression",
                "observed_presence",
            )
        )
    ]


def defensive_audit(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    full = _full_validation(rows)
    target_rows = [candidate_row(row, "C_FULL_EVIDENCE_MEASUREMENT") for row in full]
    y = np.asarray([float(row["defense_evidence"]) for row in target_rows])
    groups = [str(row["player_id"]) for row in full]
    seasons = [int(row["season_id"]) for row in full]
    specs = {
        "EXPANDED_BOX_NO_PRESENCE": ("role_aware_actions", "team_suppression"),
        "TRADITIONAL_BOX": ("rpg", "team_suppression"),
        "EARLY_WITH_PRESENCE": ("observed_presence", "team_suppression"),
        "EARLY_MINIMAL": ("team_suppression",),
    }
    predictions: dict[str, npt.NDArray[np.float64]] = {}
    models: dict[str, Any] = {}
    validation: dict[str, Any] = {
        "D1_ACTIONS_ONLY": regression_metrics(
            y.tolist(), [float(row["role_aware_actions"]) for row in full]
        ),
        "D2_ACTIONS_BOUNDED_TEAM": regression_metrics(
            y.tolist(),
            [
                0.90 * float(row["role_aware_actions"]) + 0.10 * float(row["team_suppression"])
                for row in full
            ],
        ),
    }
    for label, fields in specs.items():
        x = _features(full, fields)
        predicted = grouped_oof_ridge(x, y, groups, alpha=3.0, salt=f"defense-{label}")
        era_predicted, eligible = era_block_predictions(x, y, seasons, alpha=3.0)
        predictions[label] = predicted
        models[label] = fit_full_ridge(x, y, alpha=3.0)
        validation[label] = {
            "fields": fields,
            "grouped_player": regression_metrics(y.tolist(), predicted.tolist()),
            "era_block": regression_metrics(y[eligible].tolist(), era_predicted[eligible].tolist()),
            "full_fit_model": {
                "coefficients": models[label].coefficients,
                "feature_means": models[label].feature_means,
                "feature_scales": models[label].feature_scales,
                "alpha": models[label].alpha,
            },
        }
    matrix = np.asarray(
        [
            [
                float(row["role_aware_actions"]),
                float(row["team_suppression"]),
                float(row["observed_presence"]),
            ]
            for row in full
        ]
    )
    latent = fit_latent_measurement(matrix)
    full_latent = latent_scores(latent, matrix)
    masks = {
        "NO_PRESENCE": np.asarray([[True, True, False]] * len(full)),
        "TEAM_ONLY": np.asarray([[False, True, False]] * len(full)),
        "ACTIONS_ONLY": np.asarray([[True, False, False]] * len(full)),
    }
    latent_report: dict[str, Any] = {
        "loadings": latent.loadings,
        "explained_variance_ratio": latent.explained_variance_ratio,
    }
    for label, mask in masks.items():
        estimated = latent_scores(latent, matrix, mask)
        latent_report[label] = regression_metrics(
            _global_percentiles(full_latent), _global_percentiles(estimated)
        )
    by_decade: dict[str, Any] = {}
    for decade in sorted({int(row["season_id"]) // 10 * 10 for row in full}):
        subset = [
            index for index, row in enumerate(full) if int(row["season_id"]) // 10 * 10 == decade
        ]
        if len(subset) < 100:
            continue
        local = fit_latent_measurement(matrix[subset])
        cosine = float(
            np.dot(latent.loadings, local.loadings)
            / (np.linalg.norm(latent.loadings) * np.linalg.norm(local.loadings))
        )
        by_decade[str(decade)] = {
            "rows": len(subset),
            "loadings": local.loadings,
            "cosine_with_pooled_loadings": cosine,
            "explained_variance_ratio": local.explained_variance_ratio,
        }
    validation["D4_LATENT_MEASUREMENT"] = {
        **latent_report,
        "loading_stability_by_decade": by_decade,
    }
    validation["interpretation"] = (
        "The one-factor model tests measurement coherence; it is not treated as "
        "observed defense or ground truth."
    )
    return validation, {"rows": full, "targets": y, "predictions": predictions, "models": models}


def _raw_value(scoring: float, creation: float, defense: float) -> float:
    offense = offensive_axis(scoring, creation, architecture="O3_MULTIPATH_60_40")
    assert offense is not None
    combined = combine_player_value(
        offense, defense, architecture="M4_BOUNDED_STRONGER_55_45", defense_team_weight=0.0
    )
    assert combined.value is not None
    return float(combined.value)


def bridge_validation(
    defense_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    full = cast(list[dict[str, Any]], defense_state["rows"])
    defense_predictions = cast(dict[str, npt.NDArray[np.float64]], defense_state["predictions"])
    actual_rows = [candidate_row(row, "C_FULL_EVIDENCE_MEASUREMENT") for row in full]
    actual_raw = [float(row["player_season_value_raw"]) for row in actual_rows]
    actual_ranked = rank_percentiles_by_season(
        {
            (str(row["player_id"]), int(row["season_id"])): value
            for row, value in zip(full, actual_raw, strict=True)
        }
    )
    actual = [actual_ranked[(str(row["player_id"]), int(row["season_id"]))] for row in full]
    # Creation C2 is refit with the exact full-validation groups for honest masking.
    creation_x = _features(full, ("ppg",))
    creation_y = np.asarray([float(row["apg"]) for row in full])
    creation_prediction = grouped_oof_ridge(
        creation_x,
        creation_y,
        [str(row["player_id"]) for row in full],
        alpha=2.0,
        salt="creation-player",
    )
    results: dict[str, Any] = {}
    details: dict[str, Any] = {"rows": full, "actual": actual}
    masks = {
        "EXPANDED_BOX_NO_PRESENCE": (False, "EXPANDED_BOX_NO_PRESENCE"),
        "TRADITIONAL_BOX": (False, "TRADITIONAL_BOX"),
        "EARLY_WITH_PRESENCE": (True, "EARLY_WITH_PRESENCE"),
        "EARLY_MINIMAL": (True, "EARLY_MINIMAL"),
    }
    candidate_results: dict[str, dict[str, Any]] = defaultdict(dict)
    masked_predictions: dict[str, list[float]] = {}
    for regime, (creation_missing, defense_key) in masks.items():
        defense_pred = defense_predictions[defense_key]
        raw = []
        for index, row in enumerate(full):
            scoring = (
                float(row["ppg"])
                if regime.startswith("EARLY")
                else (0.65 * float(row["ppg"]) + 0.35 * float(row["ts_pct"]))
            )
            creation = float(creation_prediction[index]) if creation_missing else float(row["apg"])
            raw.append(_raw_value(scoring, creation, float(defense_pred[index])))
        ranked_map = rank_percentiles_by_season(
            {
                (str(row["player_id"]), int(row["season_id"])): value
                for row, value in zip(full, raw, strict=True)
            }
        )
        predicted = [ranked_map[(str(row["player_id"]), int(row["season_id"]))] for row in full]
        masked_predictions[regime] = predicted
        metrics = regression_metrics(actual, predicted)
        role, maximum_role_bias = _role_report(full, actual, predicted)
        metrics["maximum_absolute_major_role_bias"] = maximum_role_bias
        gate = practical_gate(metrics)
        gate["major_role_bias_at_most_3"] = maximum_role_bias <= 3.0
        gate["passes"] = bool(gate["passes"] and gate["major_role_bias_at_most_3"])
        residuals = np.abs(np.asarray(predicted) - np.asarray(actual))
        intervals: dict[str, Any] = {}
        for confidence in (0.80, 0.90, 0.95):
            radius = float(np.quantile(residuals, confidence))
            interval_rows = [
                clipped_interval(value, radius, confidence=confidence) for value in predicted
            ]
            intervals[str(confidence)] = interval_metrics(actual, interval_rows)
            intervals[str(confidence)]["radius_points"] = 100.0 * radius
        results[regime] = {
            "metrics": metrics,
            "role_metrics": role,
            "practical_gates": gate,
            "interval_calibration": intervals,
            "point_score_status": "SUPPORTED" if gate["passes"] else "REJECTED",
        }
        candidate_results["D_COMBINED_UNCERTAINTY_AWARE"][regime] = results[regime]
        candidate_results["E_PARTIAL_IDENTIFICATION"][regime] = {
            "point_score_status": "SUPPORTED" if gate["passes"] else "INTERVAL_ONLY",
            "interval_calibration": intervals,
        }
        candidate_results["B_CREATION_ONLY"][regime] = {
            "status": "UNAVAILABLE"
            if defense_key != "EXPANDED_BOX_NO_PRESENCE"
            else "DEFENSE_UNBRIDGED"
        }
        candidate_results["C_DEFENSE_ONLY"][regime] = {
            "status": "UNAVAILABLE_CREATION"
            if creation_missing
            else "TESTED_AS_DEFENSIVE_COMPONENT"
        }
    candidate_results["A_STRICT_OBSERVED"] = {
        "FULL_PORTABLE": {"point_score_status": "SUPPORTED", "coverage": len(full)},
        "other_regimes": {"point_score_status": "UNAVAILABLE"},
    }
    details["creation_prediction"] = creation_prediction
    details["masked_predictions"] = masked_predictions
    details["candidate_results"] = candidate_results
    return {
        "full_evidence_rows": len(full),
        "regimes": results,
        "candidates": candidate_results,
    }, details


def bridge_player_seasons(
    base_rows: list[dict[str, Any]],
    d_rows: list[dict[str, Any]],
    creation_state: dict[str, Any],
    defense_state: dict[str, Any],
    masks: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build non-promoted point/interval research records for every input row."""
    existing = {(str(row["player_id"]), int(row["season_id"])): row for row in d_rows}
    creation_model = creation_state["model"]
    defense_models = defense_state["models"]
    staged: list[dict[str, Any]] = []
    raw_by_key: dict[tuple[str, int], float | None] = {}
    for row in base_rows:
        key = (str(row["player_id"]), int(row["season_id"]))
        current = existing[key]
        observed = current.get("player_season_value_raw")
        fallback: str | None = None
        raw = float(observed) if observed is not None else None
        if raw is None and row.get("ppg") is not None and row.get("team_suppression") is not None:
            creation_x = _features([row], ("ppg",))
            creation = float(predict_ridge(creation_model, creation_x)[0])
            fields: tuple[str, ...]
            if row.get("observed_presence") is not None:
                fallback = "EARLY_WITH_PRESENCE"
                fields = ("observed_presence", "team_suppression")
            else:
                fallback = "EARLY_MINIMAL"
                fields = ("team_suppression",)
            defense_x = _features([row], fields)
            defense = float(predict_ridge(defense_models[fallback], defense_x)[0])
            raw = _raw_value(float(row["ppg"]), creation, defense)
        raw_by_key[key] = raw
        staged.append(
            {
                "player_id": key[0],
                "season_id": key[1],
                "evidence_regime": row["evidence_regime"],
                "observed_candidate_d": current.get("player_season_value_percentile"),
                "bridge_raw": raw,
                "fallback_type": fallback or "OBSERVED_CANDIDATE_D",
            }
        )
    ranked = rank_percentiles_by_season(raw_by_key)
    for row in staged:
        key = (str(row["player_id"]), int(row["season_id"]))
        central = ranked[key]
        fallback = str(row["fallback_type"])
        if central is None:
            lower = upper = None
            status, confidence = "UNAVAILABLE", "UNAVAILABLE"
            reasons = ["INSUFFICIENT_PORTABLE_EVIDENCE"]
        elif fallback == "OBSERVED_CANDIDATE_D":
            lower = upper = central
            status = "OBSERVED_RESEARCH_SCORE"
            confidence = str(existing[key]["confidence"])
            reasons = json.loads(str(existing[key]["reason_codes_json"]))
        else:
            radius = (
                float(masks["regimes"][fallback]["interval_calibration"]["0.9"]["radius_points"])
                / 100.0
            )
            lower, upper = max(0.0, central - radius), min(1.0, central + radius)
            status, confidence = "INTERVAL_ONLY", "LIMITED"
            reasons = [
                "CREATION_ESTIMATED_FROM_PPG",
                "DEFENSE_ESTIMATED_FROM_SPARSE_EVIDENCE",
                "POINT_BRIDGE_FAILED_PREDECLARED_GATES",
            ]
        row.update(
            {
                "bridge_central_percentile": central,
                "bridge_lower_90": lower,
                "bridge_upper_90": upper,
                "score_status": status,
                "confidence": confidence,
                "reason_codes_json": json.dumps(reasons, sort_keys=True),
                "methodology_version": HISTORICAL_BRIDGE_RESEARCH_VERSION,
                "promoted": False,
                "corpus_id": CORPUS_ID,
            }
        )
    return staged


def modern_mask_controls(mask_state: dict[str, Any], names: dict[str, str]) -> list[dict[str, Any]]:
    rows = cast(list[dict[str, Any]], mask_state["rows"])
    actual = cast(list[float], mask_state["actual"])
    predictions = cast(dict[str, list[float]], mask_state["masked_predictions"])
    selected: dict[str, int] = {}
    for index, row in enumerate(rows):
        name = names.get(str(row["player_id"]))
        if name not in MODERN_NAMES:
            continue
        if name not in selected or actual[index] > actual[selected[name]]:
            selected[name] = index
    return [
        {
            "player_id": str(rows[index]["player_id"]),
            "player_name": name,
            "season_id": int(rows[index]["season_id"]),
            "full_score": actual[index],
            **{f"masked_{regime.lower()}": values[index] for regime, values in predictions.items()},
            "methodology_version": HISTORICAL_BRIDGE_RESEARCH_VERSION,
            "promoted": False,
        }
        for name, index in sorted(selected.items())
    ]


def transition_audit(rows: list[dict[str, Any]], d_rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = {
        (str(row["player_id"]), int(row["season_id"])): float(row["player_season_value_percentile"])
        for row in d_rows
        if row.get("player_season_value_percentile") is not None
    }
    by_player: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_player[str(row["player_id"])][int(row["season_id"])] = row
    buckets: dict[str, list[float]] = defaultdict(list)
    examples: list[dict[str, Any]] = []
    for player, seasons in by_player.items():
        for season, row in seasons.items():
            following = seasons.get(season + 1)
            if following is None:
                continue
            left, right = scores.get((player, season)), scores.get((player, season + 1))
            if left is None or right is None:
                continue
            change = 100.0 * (right - left)
            changed = row["evidence_regime"] != following["evidence_regime"]
            buckets["REGIME_TRANSITION" if changed else "SAME_REGIME"].append(change)
            if changed and abs(change) > 10:
                examples.append(
                    {
                        "player_id": player,
                        "from": season,
                        "to": season + 1,
                        "change": change,
                        "from_regime": row["evidence_regime"],
                        "to_regime": following["evidence_regime"],
                    }
                )
    return {
        label: {
            "pairs": len(values),
            "mean_signed_change": statistics.fmean(values) if values else None,
            "mean_absolute_change": statistics.fmean(abs(value) for value in values)
            if values
            else None,
            "share_over_10": sum(abs(value) > 10 for value in values) / len(values)
            if values
            else None,
        }
        for label, values in sorted(buckets.items())
    } | {
        "largest_transition_examples": sorted(examples, key=lambda row: -abs(float(row["change"])))[
            :25
        ]
    }


def era_discontinuity(rows: list[dict[str, Any]], d_rows: list[dict[str, Any]]) -> dict[str, Any]:
    index = {(str(row["player_id"]), int(row["season_id"])): row for row in rows}
    groups: dict[str, list[float]] = defaultdict(list)
    for row in d_rows:
        value = row.get("player_season_value_percentile")
        if value is None:
            continue
        source = index[(str(row["player_id"]), int(row["season_id"]))]
        groups[str(source["evidence_regime"])].append(100.0 * float(value))
    return {
        name: {"rows": len(values), "distribution": distribution(values)}
        for name, values in sorted(groups.items())
    }


def names_and_dimensions(
    gold_root: Path,
) -> tuple[dict[str, str], dict[str, dict[str, float | None]]]:
    names: dict[str, str] = {}
    dimensions: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in read_rows(gold_root / "player_dimension_scores/part-00000.parquet"):
        player = str(row["player_id"])
        names[player] = str(row["display_name"])
        dimensions[str(row["dimension"])][player] = row.get("score")
    return names, dimensions


def case_studies(
    rows: list[dict[str, Any]],
    d_rows: list[dict[str, Any]],
    bridge_rows: list[dict[str, Any]],
    names: dict[str, str],
) -> list[dict[str, Any]]:
    d_index = {(str(row["player_id"]), int(row["season_id"])): row for row in d_rows}
    bridge_index = {(str(row["player_id"]), int(row["season_id"])): row for row in bridge_rows}
    wanted = set(EARLY_NAMES + MODERN_NAMES)
    output: list[dict[str, Any]] = []
    for row in rows:
        player = str(row["player_id"])
        if names.get(player) not in wanted:
            continue
        current = d_index[(player, int(row["season_id"]))]
        bridge = bridge_index[(player, int(row["season_id"]))]
        output.append(
            {
                "player_id": player,
                "player_name": names[player],
                "season_id": int(row["season_id"]),
                "evidence_regime": row["evidence_regime"],
                "ppg": row.get("ppg"),
                "ts_pct": row.get("ts_pct"),
                "apg": row.get("apg"),
                "role_actions": row.get("role_aware_actions"),
                "team_context": row.get("team_suppression"),
                "presence": row.get("observed_presence"),
                "candidate_d_score": current.get("player_season_value_percentile"),
                "confidence": current.get("confidence"),
                "reason_codes_json": current.get("reason_codes_json"),
                "bridge_status": "OBSERVED_RESEARCH_SCORE"
                if current.get("player_season_value_percentile") is not None
                else bridge["score_status"],
                "bridge_central_diagnostic": bridge["bridge_central_percentile"],
                "bridge_lower_90": bridge["bridge_lower_90"],
                "bridge_upper_90": bridge["bridge_upper_90"],
                "bridge_reason_codes_json": bridge["reason_codes_json"],
                "methodology_version": HISTORICAL_BRIDGE_RESEARCH_VERSION,
                "promoted": False,
                "corpus_id": CORPUS_ID,
            }
        )
    return output


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    step_d = verify_step_d(args.docs_root)
    base_rows, _ = season_inputs(args.gold_root)
    candidates, reconstruct = reconstruction(base_rows, args.gold_root)
    if reconstruct["mismatches"] or reconstruct["maximum_numerical_difference"] > 1e-12:
        raise ValueError("STEP-0015D reconstruction failed")
    d_rows = [row for row in candidates if row["candidate"] == "D_REGIME_RELIABILITY"]
    missing = missing_inventory(base_rows)
    creation, creation_state = creation_audit(base_rows)
    defense, defense_state = defensive_audit(base_rows)
    masks, mask_state = bridge_validation(defense_state)
    names, dimensions = names_and_dimensions(args.gold_root)
    bridge_rows = bridge_player_seasons(base_rows, d_rows, creation_state, defense_state, masks)
    modern_controls = modern_mask_controls(mask_state, names)

    supported = [
        regime for regime, result in masks["regimes"].items() if result["practical_gates"]["passes"]
    ]
    major_sparse_supported = any(
        regime in supported
        for regime in ("TRADITIONAL_BOX", "EARLY_WITH_PRESENCE", "EARLY_MINIMAL")
    )
    verdict = (
        "LIMITED_BRIDGE"
        if supported and not major_sparse_supported
        else (
            "VALID_BRIDGE" if major_sparse_supported and len(supported) == 4 else "NO_VALID_BRIDGE"
        )
    )
    recommendation = (
        "READY_FOR_PROMOTION_AUDIT"
        if verdict == "VALID_BRIDGE"
        else "REQUIRES_MORE_MEASUREMENT_WORK"
    )
    regime_policy = {
        "FULL_PORTABLE": "FULL_RESEARCH_SCORE",
        "EXPANDED_BOX_NO_PRESENCE": "PROVISIONAL_POINT_SCORE"
        if "EXPANDED_BOX_NO_PRESENCE" in supported
        else "INTERVAL_ONLY",
        "TRADITIONAL_BOX": "PROVISIONAL_POINT_SCORE"
        if "TRADITIONAL_BOX" in supported
        else "INTERVAL_ONLY",
        "EARLY_LIMITED": "INTERVAL_ONLY_OR_UNAVAILABLE",
    }

    players = sorted(names)
    reference = {
        str(row["player_id"])
        for row in read_rows(
            args.gold_root / "peak_forensic_audit/v1-player-peak-decomposition.parquet"
        )
        if row.get("raw_peak") is not None
    }
    peak, longevity, peak_detail, longevity_detail = career_counterfactuals(
        candidates, "D_REGIME_RELIABILITY", players, reference
    )
    frozen_peak = {
        str(row["player_id"]): row.get("counterfactual_peak")
        for row in read_rows(
            args.gold_root / "player_season_value_audit/peak-counterfactual.parquet"
        )
    }
    frozen_longevity = {
        str(row["player_id"]): row.get("counterfactual_longevity")
        for row in read_rows(
            args.gold_root / "player_season_value_audit/longevity-counterfactual.parquet"
        )
    }
    reconstruct["peak_counterfactual_maximum_difference"] = max(
        (
            abs(float(value) - float(frozen_peak[player]))
            for player, value in peak.items()
            if value is not None and frozen_peak[player] is not None
        ),
        default=0.0,
    )
    reconstruct["longevity_counterfactual_maximum_difference"] = max(
        (
            abs(float(value) - float(frozen_longevity[player]))
            for player, value in longevity.items()
            if value is not None and frozen_longevity[player] is not None
        ),
        default=0.0,
    )
    if (
        reconstruct["peak_counterfactual_maximum_difference"] > 1e-12
        or reconstruct["longevity_counterfactual_maximum_difference"] > 1e-12
    ):
        raise ValueError("STEP-0015D downstream counterfactual reconstruction failed")
    peak_comparison = compare_scores(peak, dimensions["PEAK"])
    longevity_comparison = compare_scores(longevity, dimensions["LONGEVITY"])
    overlap = [
        player for player in players if peak[player] is not None and longevity[player] is not None
    ]
    peak_longevity = {
        "players": len(overlap),
        "spearman": spearman(
            [float(peak[player]) for player in overlap],
            [float(longevity[player]) for player in overlap],
        ),
        "architecture_unchanged": True,
    }
    transitions = transition_audit(base_rows, d_rows)
    discontinuity = era_discontinuity(base_rows, d_rows)
    studies = case_studies(base_rows, d_rows, bridge_rows, names)

    # Explicitly retain the exact STEP-0015D score; failed bridges never fill the frozen candidate.
    output_root = args.gold_root / "historical_bridge_audit"
    manifests = [
        write_parquet(
            d_rows, output_root / "candidate-d-reconstruction.parquet", ("season_id", "player_id")
        ),
        write_parquet(
            bridge_rows,
            output_root / "bridge-player-season-counterfactual.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            studies, output_root / "bridge-case-studies.parquet", ("player_name", "season_id")
        ),
        write_parquet(
            modern_controls,
            output_root / "modern-mask-controls.parquet",
            ("player_name",),
        ),
        write_parquet(
            [
                {
                    "player_id": player,
                    "player_name": names[player],
                    "score": peak[player],
                    **peak_detail[player],
                    "methodology_version": HISTORICAL_BRIDGE_RESEARCH_VERSION,
                    "promoted": False,
                }
                for player in players
            ],
            output_root / "peak-counterfactual.parquet",
            ("player_id",),
        ),
        write_parquet(
            [
                {
                    "player_id": player,
                    "player_name": names[player],
                    "score": longevity[player],
                    **longevity_detail[player],
                    "methodology_version": HISTORICAL_BRIDGE_RESEARCH_VERSION,
                    "promoted": False,
                }
                for player in players
            ],
            output_root / "longevity-counterfactual.parquet",
            ("player_id",),
        ),
    ]

    common = {
        "step": "STEP-0015E",
        "audit_methodology_version": HISTORICAL_BRIDGE_AUDIT_VERSION,
        "research_methodology_version": HISTORICAL_BRIDGE_RESEARCH_VERSION,
        "upstream_step_0015d_fingerprint": STEP_D_FINGERPRINT,
        "random_seed": BRIDGE_RANDOM_SEED,
    }
    reports: dict[str, Any] = {
        "historical-bridge-reconstruction.json": {"reconstruction": reconstruct},
        "historical-bridge-missing-channels.json": {"regimes": missing},
        "creation-bridge-validation.json": {"creation": creation},
        "defensive-measurement-invariance.json": {"defense": defense},
        "historical-mask-validation.json": masks,
        "historical-bridge-grouped-era-validation.json": {
            "creation": {
                key: value
                for key, value in creation.items()
                if "GROUPED" in key or "ERA_BLOCK" in key or "RANDOM" in key
            },
            "defense": {
                key: value
                for key, value in defense.items()
                if isinstance(value, dict) and ("grouped_player" in value or "era_block" in value)
            },
        },
        "bridge-uncertainty-calibration.json": {
            regime: result["interval_calibration"] for regime, result in masks["regimes"].items()
        },
        "historical-bridge-transition-audit.json": {
            "same_player": transitions,
            "regime_distributions": discontinuity,
        },
        "player-season-value-bridge-comparison.json": {
            "candidates": masks["candidates"],
            "bridge_verdict": verdict,
            "regime_policy": regime_policy,
            "recommendation": recommendation,
        },
        "historical-bridge-case-studies.json": {"rows": studies},
        "historical-bridge-modern-controls.json": {"players": modern_controls},
        "historical-bridge-peak-counterfactual.json": {
            "comparison": peak_comparison,
            "coverage": sum(value is not None for value in peak.values()),
            "architecture": "70% best contiguous 3-year + 30% apex",
            "bridge_filled_rows": 0,
        },
        "historical-bridge-longevity-counterfactual.json": {
            "comparison": longevity_comparison,
            "coverage": sum(value is not None for value in longevity.values()),
            "architecture": "35% P80 breadth + 40% capped P80-P90 area + 25% longest P80 run",
            "bridge_filled_rows": 0,
        },
        "historical-bridge-peak-longevity.json": peak_longevity,
        "historical-bridge-effective-influence.json": {
            "candidate_d_baseline": step_d["influence"],
            "bridge_adopted": False,
            "team_context_maximum_direct_weight": step_d["influence"]["team_context"][
                "maximum_effective_weight"
            ],
            "warning": (
                "Rejected proxy models may encode shared team context indirectly; "
                "they are not promoted or used to fill point scores."
            ),
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        stable_json(args.docs_root / name, {**common, **payload})
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "upstream": STEP_D_FINGERPRINT,
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
        **common,
        "result": "PASS",
        "bridge_verdict": verdict,
        "recommendation": recommendation,
        "step_0015d_reconstruction": reconstruct,
        "scored_player_seasons": 16576,
        "total_player_seasons": len(base_rows),
        "players_scored": len(
            {
                str(row["player_id"])
                for row in d_rows
                if row.get("player_season_value_percentile") is not None
            }
        ),
        "bridge_counterfactual_status_counts": dict(
            Counter(str(row["score_status"]) for row in bridge_rows)
        ),
        "regime_policy": regime_policy,
        "supported_masked_regimes": supported,
        "peak_counterfactual": peak_comparison,
        "longevity_counterfactual": longevity_comparison,
        "network_requests": 0,
        "runtime_seconds": time.perf_counter() - started,
        "output_partitions": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint
        if args.expected_fingerprint
        else False,
        "production_promoted": False,
        "frozen_v1_unchanged": True,
        "candidate_d_unchanged": True,
    }
    stable_json(args.docs_root / "historical-evidence-bridge-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(f"fingerprint mismatch: {fingerprint}")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
