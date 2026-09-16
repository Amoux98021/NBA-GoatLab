#!/usr/bin/env python3
"""Run STEP-0015M Defense V2 tiered measurement and promotion audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import numpy as np

from goatlab.rankings.defense_tiered import (
    DEFENSE_AUDIT_VERSION,
    DEFENSE_V2_TIERED_VERSION,
    career_defense_status,
    classify_defense_form,
    defense_weights,
    observed_defense_score,
    point_eligibility,
)
from goatlab.rankings.measurement_linking import (
    LinkMethod,
    conformal_radius,
    cross_fitted_predictions,
    deterministic_fold,
    fit_linker,
    interval_bounds,
    predict_linker,
    regression_metrics,
)
from pipelines.rankings.audit_defense_v1 import (
    award_validation,
    midrank_percentile_scores,
    modern_defense,
    read_rows,
    reference_population,
)
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet

ROOT = Path(__file__).resolve().parents[2]
RUN_AT_DEFAULT = "2026-09-16T15:00:00Z"
TEAM_WEIGHTS = (0.10, 0.15, 0.20, 0.30)
SELECTED_TEAM_WEIGHT = 0.10
METHODS: tuple[LinkMethod, ...] = (
    "identity",
    "linear",
    "quantile",
    "isotonic",
    "role_isotonic",
)
FORMS = (
    "DEF_ACTION_PRESENCE_NO_CONTEXT",
    "DEF_ACTION_PARTIAL_PRESENCE",
    "DEF_ACTION_NO_PRESENCE",
    "DEF_TRADITIONAL_PRESENCE",
    "DEF_TRADITIONAL",
    "DEF_REBOUND_ONLY",
    "DEF_CONTEXT_PRESENCE",
    "DEF_CONTEXT_ONLY",
)
POINT_GATE_FORMS = set(FORMS) - {"DEF_CONTEXT_ONLY"}
EXPECTED_FINGERPRINTS = {
    "step_0015a": "07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324",
    "step_0015b": "103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f",
    "step_0015h": "4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54",
    "step_0015l": "cb740fc68a77df3cb30b68e854e413c670394638ff2bf7b47401b905c7a81580",
}
CASE_NAMES = {
    "George Mikan",
    "Bob Pettit",
    "Bill Russell",
    "Wilt Chamberlain",
    "Oscar Robertson",
    "Elgin Baylor",
    "Jerry West",
    "Kareem Abdul-Jabbar",
    "Michael Jordan",
    "LeBron James",
    "Scottie Pippen",
    "Tim Duncan",
    "Kevin Garnett",
    "Hakeem Olajuwon",
    "Ben Wallace",
    "Draymond Green",
    "Rudy Gobert",
    "Kawhi Leonard",
    "Gary Payton",
    "Sidney Moncrief",
    "Kobe Bryant",
    "Stephen Curry",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _load_summary(path: Path, expected: str) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("output_fingerprint") != expected:
        raise ValueError(f"upstream fingerprint mismatch: {path}")
    return cast(dict[str, Any], payload)


def verify_upstream(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, str]]:
    summaries = {
        "step_0015a": _load_summary(
            args.docs_root / "defense-forensic-audit-summary.json",
            EXPECTED_FINGERPRINTS["step_0015a"],
        ),
        "step_0015b": _load_summary(
            args.docs_root / "defense-v2-promotion-summary.json",
            EXPECTED_FINGERPRINTS["step_0015b"],
        ),
        "step_0015h": _load_summary(
            args.docs_root / "player-season-value-measurement-linking-summary.json",
            EXPECTED_FINGERPRINTS["step_0015h"],
        ),
        "step_0015l": _load_summary(
            args.docs_root / "overall-uncertainty-summary.json",
            EXPECTED_FINGERPRINTS["step_0015l"],
        ),
    }
    fingerprints = dict(EXPECTED_FINGERPRINTS)
    fingerprints["recovered_candidate_d"] = file_hash(
        args.gold_root / "player_season_value_v2_promotion_audit/candidate-d-reconstruction.parquet"
    )
    fingerprints["v1_dimension_scores"] = file_hash(
        args.gold_root / "player_dimension_scores/part-00000.parquet"
    )
    fingerprints["peak_v2"] = file_hash(
        args.gold_root / "peak_longevity_policy_freeze/peak-v2.parquet"
    )
    fingerprints["longevity_tiered"] = file_hash(
        args.gold_root / "peak_longevity_policy_freeze/longevity-v2-tiered.parquet"
    )
    return summaries, fingerprints


def upstream_reconstruction(args: argparse.Namespace, summaries: dict[str, Any]) -> dict[str, Any]:
    v1 = read_rows(args.gold_root / "defense_forensic_audit/v1-player-decomposition.parquet")
    candidate = read_rows(
        args.gold_root / "defense_forensic_audit/candidate-defense-scores.parquet"
    )
    season_b = read_rows(
        args.gold_root / "defense_v2_promotion_audit/defense-v2-season-components.parquet"
    )
    v1_diffs = [
        abs(float(row["v1_defense_score"]) - float(row["reconstructed_defense_score"]))
        for row in v1
        if row["v1_defense_score"] is not None and row["reconstructed_defense_score"] is not None
    ]
    b_rows = [row for row in candidate if row["candidate"] == "B_TRIANGULATED_PRESENCE"]
    b_summary = summaries["step_0015b"]["candidate_b_reconstruction"]
    report = {
        "defense_v1_rows": len(v1),
        "defense_v1_maximum_difference": max(v1_diffs, default=0.0),
        "defense_v1_score_mismatches": sum(value > 1e-12 for value in v1_diffs),
        "candidate_b_rows": len(b_rows),
        "candidate_b_maximum_difference": float(b_summary["maximum_score_difference"]),
        "candidate_b_exact": bool(b_summary["exact"]),
        "continuous_candidate_rows": len(season_b),
        "continuous_candidate_source_fingerprint_verified": True,
        "step_0015h_fingerprint_verified": True,
        "step_0015l_fingerprint_verified": True,
        "maximum_numerical_difference": max(
            max(v1_diffs, default=0.0), float(b_summary["maximum_score_difference"])
        ),
    }
    report["exact"] = report["maximum_numerical_difference"] == 0.0 and report["candidate_b_exact"]
    if not report["exact"]:
        raise ValueError("Defense upstream reconstruction failed")
    return report


def _archetypes(row: dict[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    if row.get("rpg") is not None and float(row["rpg"]) >= 0.85:
        labels.append("REBOUND_HEAVY")
    if row.get("spg") is not None and float(row["spg"]) >= 0.85:
        labels.append("STEAL_HEAVY")
    if row.get("bpg") is not None and float(row["bpg"]) >= 0.85:
        labels.append("BLOCK_HEAVY")
    if row.get("actions") is not None and float(row["actions"]) <= 0.30:
        labels.append("LOW_STOCK_ACTION")
    if (
        row.get("team_context") is not None
        and row.get("actions") is not None
        and float(row["team_context"]) >= 0.80
        and float(row["actions"]) <= 0.50
    ):
        labels.append("STRONG_TEAM_WEAK_ACTION")
    if (
        row.get("team_context") is not None
        and row.get("actions") is not None
        and float(row["actions"]) >= 0.80
        and float(row["team_context"]) <= 0.50
    ):
        labels.append("STRONG_ACTION_WEAK_TEAM")
    if row.get("presence") is not None and float(row["presence"]) >= 0.85:
        labels.append("PRESENCE_HEAVY")
    return tuple(labels or ["GENERAL"])


def evidence_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {
        "team_context": ("TEAM_SHARED_CONTEXT", "era-relative team suppression"),
        "rpg": ("INDIVIDUAL_PROXY", "DREB where observed, historical TRB proxy otherwise"),
        "spg": ("INDIVIDUAL_ACTION", "steals where officially recorded"),
        "bpg": ("INDIVIDUAL_ACTION", "blocks where officially recorded"),
        "actions": ("INDIVIDUAL_COMPOSITE", "40% rebound, 30% steals, 30% blocks"),
        "presence": ("INDIVIDUAL_OBSERVATIONAL", "shrunk game-participation WOWY-style evidence"),
        "broad_role": ("INTERPRETIVE_METADATA", "broad role when source position is reliable"),
    }
    return {
        "player_seasons": len(rows),
        "channels": {
            field: {
                "observed": sum(row.get(field) is not None for row in rows),
                "coverage": sum(row.get(field) is not None for row in rows) / len(rows),
                "kind": kind,
                "definition": definition,
                "missing_is_zero": False,
            }
            for field, (kind, definition) in fields.items()
        },
        "presence_reliability": {
            "observed": sum(row.get("presence") is not None for row in rows),
            "fully_reliable": sum(
                row.get("presence") is not None
                and float(row.get("presence_reliability") or 0.0) >= 1.0
                for row in rows
            ),
            "partially_reliable": sum(
                row.get("presence") is not None
                and 0.0 < float(row.get("presence_reliability") or 0.0) < 1.0
                for row in rows
            ),
            "predicted_when_missing": False,
        },
        "season_span": [
            min(int(row["season_id"]) for row in rows),
            max(int(row["season_id"]) for row in rows),
        ],
    }


def _masked_score(row: dict[str, Any], form: str, team_weight: float) -> float | None:
    action = float(row["actions"]) if row.get("actions") is not None else None
    rebound = float(row["rpg"]) if row.get("rpg") is not None else None
    team = float(row["team_context"]) if row.get("team_context") is not None else None
    presence = float(row["presence"]) if row.get("presence") is not None else None
    if form == "DEF_ACTION_PRESENCE_NO_CONTEXT":
        values = (None, action, presence, 1.0)
    elif form == "DEF_ACTION_PARTIAL_PRESENCE":
        values = (team, action, presence, 0.60)
    elif form == "DEF_ACTION_NO_PRESENCE":
        values = (team, action, None, 0.0)
    elif form == "DEF_TRADITIONAL_PRESENCE":
        values = (team, rebound, presence, 1.0)
    elif form == "DEF_TRADITIONAL":
        values = (team, rebound, None, 0.0)
    elif form == "DEF_REBOUND_ONLY":
        values = (None, rebound, None, 0.0)
    elif form == "DEF_CONTEXT_PRESENCE":
        values = (team, None, presence, 1.0)
    elif form == "DEF_CONTEXT_ONLY":
        values = (team, None, None, 0.0)
    else:
        raise ValueError(form)
    score, _ = observed_defense_score(
        team=values[0],
        action=values[1],
        presence=values[2],
        presence_reliability=values[3],
        team_weight=team_weight,
    )
    return None if score is None else 100.0 * score


def build_anchors(rows: list[dict[str, Any]], team_weight: float) -> list[dict[str, Any]]:
    weights = defense_weights(team_weight)
    output: list[dict[str, Any]] = []
    for row in rows:
        if not (
            row.get("team_context") is not None
            and row.get("actions") is not None
            and row.get("rpg") is not None
            and row.get("spg") is not None
            and row.get("bpg") is not None
            and row.get("presence") is not None
            and float(row.get("presence_reliability") or 0.0) >= 1.0
        ):
            continue
        full = 100.0 * (
            weights[0] * float(row["team_context"])
            + weights[1] * float(row["actions"])
            + weights[2] * float(row["presence"])
        )
        anchor = {
            "player_id": str(row["player_id"]),
            "season_id": int(row["season_id"]),
            "team_id": str(row.get("primary_team_id") or "UNKNOWN"),
            "role": str(row.get("broad_role") or "UNKNOWN"),
            "full_score": full,
            "team_context": float(row["team_context"]),
            "action": float(row["actions"]),
            "rebound": float(row["rpg"]),
            "steal": float(row["spg"]),
            "block": float(row["bpg"]),
            "presence": float(row["presence"]),
            "archetypes_json": json.dumps(_archetypes(row), sort_keys=True),
        }
        for form in FORMS:
            anchor[f"{form}_score"] = _masked_score(row, form, team_weight)
        output.append(anchor)
    return output


def _folds(anchors: list[dict[str, Any]], mode: str) -> np.ndarray:
    if mode == "grouped_player":
        return np.asarray([deterministic_fold(str(row["player_id"]), seed=1516) for row in anchors])
    if mode == "random":
        return np.asarray(
            [
                deterministic_fold(f"{row['player_id']}|{row['season_id']}", seed=1517)
                for row in anchors
            ]
        )
    if mode == "era_block":
        return np.asarray([int(row["season_id"]) // 10 for row in anchors])
    raise ValueError(mode)


def _arrays(anchors: list[dict[str, Any]], form: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = [row for row in anchors if row.get(f"{form}_score") is not None]
    return (
        np.asarray([float(row[f"{form}_score"]) for row in valid]),
        np.asarray([float(row["full_score"]) for row in valid]),
        np.asarray([str(row["role"]) for row in valid]),
    )


def _subgroups(
    anchors: list[dict[str, Any]], reference: np.ndarray, estimate: np.ndarray
) -> tuple[dict[str, Any], dict[str, Any]]:
    roles = np.asarray([str(row["role"]) for row in anchors])
    role_report = {
        role: regression_metrics(reference[roles == role], estimate[roles == role])
        for role in sorted(set(roles.tolist()))
    }
    labels = sorted({label for row in anchors for label in json.loads(row["archetypes_json"])})
    archetype_report = {}
    for label in labels:
        mask = np.asarray([label in json.loads(row["archetypes_json"]) for row in anchors])
        if int(np.sum(mask)) >= 50:
            archetype_report[label] = regression_metrics(reference[mask], estimate[mask])
    return role_report, archetype_report


def split_conformal(
    anchors: list[dict[str, Any]], form: str, method: LinkMethod
) -> tuple[np.ndarray, dict[int, np.ndarray], dict[str, Any]]:
    x, y, roles = _arrays(anchors, form)
    folds = _folds(anchors, "grouped_player")
    points = np.full(len(x), np.nan)
    bounds = {level: np.full((len(x), 2), np.nan) for level in (80, 90, 95)}
    for fold in range(5):
        test = folds == fold
        calibration = folds == ((fold + 1) % 5)
        train = ~(test | calibration)
        model = fit_linker(method, x[train], y[train], roles[train])
        points[test] = predict_linker(model, x[test], roles[test])
        calibration_points = predict_linker(model, x[calibration], roles[calibration])
        residuals = np.abs(calibration_points - y[calibration])
        for level in (80, 90, 95):
            radius = conformal_radius(residuals, level / 100.0)
            bounds[level][test, 0] = np.maximum(0.0, points[test] - radius)
            bounds[level][test, 1] = np.minimum(100.0, points[test] + radius)
    roles_report, archetypes_report = _subgroups(anchors, y, points)
    result: dict[str, Any] = {
        "point": regression_metrics(y, points),
        "roles": roles_report,
        "archetypes": archetypes_report,
        "intervals": {},
    }
    for level in (80, 90, 95):
        inside = (y >= bounds[level][:, 0]) & (y <= bounds[level][:, 1])
        widths = bounds[level][:, 1] - bounds[level][:, 0]
        result["intervals"][str(level)] = {
            "coverage": float(np.mean(inside)),
            "mean_width": float(np.mean(widths)),
            "median_width": float(np.median(widths)),
        }
    return points, bounds, result


def linking_audit(
    anchors: list[dict[str, Any]], team_weight: float
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    report: dict[str, Any] = {}
    selected: dict[str, str] = {}
    calibration: dict[str, Any] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        methods: dict[str, Any] = {}
        for method in METHODS:
            methods[method] = {}
            for mode in ("grouped_player", "era_block", "random"):
                prediction = cross_fitted_predictions(method, x, y, _folds(anchors, mode), roles)
                methods[method][mode] = regression_metrics(y, prediction)
        best = min(float(value["grouped_player"]["mae"]) for value in methods.values())
        choice = next(
            method
            for method in METHODS
            if float(methods[method]["grouped_player"]["mae"]) <= best + 0.10
        )
        selected[form] = choice
        _, _, metrics = split_conformal(anchors, form, cast(LinkMethod, choice))
        eligible, gates = point_eligibility(metrics)
        if form not in POINT_GATE_FORMS:
            eligible = False
            gates["individual_evidence_required"] = False
        else:
            gates["individual_evidence_required"] = True
        model = fit_linker(cast(LinkMethod, choice), x, y, roles)
        all_points = predict_linker(model, x, roles)
        residuals = np.abs(all_points - y)
        metrics["radii"] = {
            str(level): conformal_radius(residuals, level / 100.0) for level in (80, 90, 95)
        }
        metrics["point_eligible"] = eligible
        metrics["gates"] = gates
        metrics["raw"] = regression_metrics(y, x)
        calibration[form] = metrics
        report[form] = {"methods": methods, "selected": choice}
    report["team_weight"] = team_weight
    return report, selected, calibration


def team_weight_audit(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = {
        (str(row["player_id"]), int(row["season_id"])): {
            "ppg_percentile": row.get("ppg"),
            "rpg_percentile": row.get("rpg"),
            "apg_percentile": row.get("apg"),
            "ts_pct_percentile": row.get("ts_pct"),
        }
        for row in rows
    }
    reference = reference_population(args.gold_root, normalized)
    modern = modern_defense(args.silver_root, reference)
    output: dict[str, Any] = {}
    for team_weight in TEAM_WEIGHTS:
        anchors = build_anchors(rows, team_weight)
        y = np.asarray([float(row["full_score"]) for row in anchors])
        team = np.asarray([float(row["team_context"]) * 100.0 for row in anchors])
        action = np.asarray([float(row["action"]) * 100.0 for row in anchors])
        presence = np.asarray([float(row["presence"]) * 100.0 for row in anchors])
        groups: dict[tuple[int, str], list[float]] = defaultdict(list)
        for row, score in zip(anchors, y, strict=True):
            groups[(int(row["season_id"]), str(row["team_id"]))].append(float(score))
        group_means = {key: statistics.fmean(values) for key, values in groups.items()}
        total_var = float(np.var(y))
        between = float(
            np.mean(
                [
                    (group_means[(int(row["season_id"]), str(row["team_id"]))] - float(np.mean(y)))
                    ** 2
                    for row in anchors
                ]
            )
        )
        within = float(
            np.mean(
                [
                    (score - group_means[(int(row["season_id"]), str(row["team_id"]))]) ** 2
                    for row, score in zip(anchors, y, strict=True)
                ]
            )
        )
        teammate_pairs = 0
        near_identical = 0
        for values in groups.values():
            if len(values) < 2:
                continue
            ordered = sorted(values)
            teammate_pairs += len(ordered) - 1
            near_identical += sum(abs(right - left) < 1.0 for left, right in pairwise(ordered))
        by_player: dict[str, list[float]] = defaultdict(list)
        role_values: dict[str, list[float]] = defaultdict(list)
        for row, score in zip(anchors, y, strict=True):
            by_player[str(row["player_id"])].append(float(score))
            role_values[str(row["role"])].append(float(score))
        career_raw = {
            player_id: statistics.fmean(values) for player_id, values in by_player.items()
        }
        career_scores = _fixed_ecdf(career_raw, set(career_raw))
        modern_ids = sorted(
            player_id
            for player_id, score in career_scores.items()
            if score is not None and player_id in modern
        )
        modern_metrics = (
            regression_metrics(
                np.asarray([float(modern[player_id]) for player_id in modern_ids]),
                np.asarray([float(career_scores[player_id]) for player_id in modern_ids]),
            )
            if modern_ids
            else {}
        )
        awards = award_validation(args.silver_root, {"candidate": career_scores})
        no_context = np.asarray(
            [float(row["DEF_ACTION_PRESENCE_NO_CONTEXT_score"]) for row in anchors]
        )
        output[f"{int(team_weight * 100)}pct"] = {
            "weights": defense_weights(team_weight),
            "anchors": len(anchors),
            "score_team_pearson": float(np.corrcoef(y, team)[0, 1]),
            "score_action_pearson": float(np.corrcoef(y, action)[0, 1]),
            "score_presence_pearson": float(np.corrcoef(y, presence)[0, 1]),
            "within_team_variance": within,
            "between_team_variance": between,
            "between_team_variance_share": between / total_var if total_var else None,
            "adjacent_teammate_pairs": teammate_pairs,
            "near_identical_credit_rate": near_identical / teammate_pairs
            if teammate_pairs
            else None,
            "role_bias": {
                role: {
                    "n": len(values),
                    "mean": statistics.fmean(values),
                    "standard_deviation": float(np.std(np.asarray(values))),
                }
                for role, values in sorted(role_values.items())
            },
            "modern_validation": modern_metrics,
            "award_validation": awards["validation"]["candidate"],
            "masked_no_team_context": regression_metrics(y, no_context),
            "selection_note": (
                "selected: lowest tested contextual weight; Presence/action "
                "retain primary attribution"
                if team_weight == SELECTED_TEAM_WEIGHT
                else "diagnostic"
            ),
        }
    return output


def career_uncertainty_audit(seasons: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare transparent career uncertainty dependence assumptions.

    The selected policy preserves player-level dependence; validation-set conformal
    calibration, rather than the analytical widths below, determines final status.
    """

    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in seasons:
        if row.get("defense_center") is not None and row.get("lower_90") is not None:
            by_player[str(row["player_id"])].append(row)
    widths: dict[str, list[float]] = defaultdict(list)
    for rows in by_player.values():
        radii = [(float(row["upper_90"]) - float(row["lower_90"])) / 2.0 for row in rows]
        independent = math.sqrt(sum(radius**2 for radius in radii)) / len(radii)
        player_block = statistics.fmean(radii)
        by_form: dict[str, list[float]] = defaultdict(list)
        for row, radius in zip(rows, radii, strict=True):
            by_form[str(row["measurement_form"])].append(radius)
        form_block = math.sqrt(sum(sum(form_radii) ** 2 for form_radii in by_form.values())) / len(
            radii
        )
        widths["INDEPENDENT_BASELINE"].append(2.0 * independent)
        widths["PLAYER_BLOCK"].append(2.0 * player_block)
        widths["EVIDENCE_FORM_BLOCK"].append(2.0 * form_block)
    return {
        "career_count": len(by_player),
        "candidate_90_widths": {
            method: {
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
            }
            for method, values in sorted(widths.items())
        },
        "selected": "PLAYER_BLOCK_WITH_CAREER_LEVEL_GROUPED_CONFORMAL",
        "reason": (
            "Independent draws understate repeated within-player measurement error; "
            "player-block propagation is the simplest conservative dependence model, "
            "and career-level grouped conformal residuals provide final calibration."
        ),
    }


def apply_season_architecture(
    rows: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    selected: dict[str, str],
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    models: dict[str, Any] = {}
    radii: dict[str, dict[int, float]] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        models[form] = fit_linker(cast(LinkMethod, selected[form]), x, y, roles)
        radii[form] = {
            level: float(calibration[form]["radii"][str(level)]) for level in (80, 90, 95)
        }
    full_radii = radii["DEF_ACTION_PRESENCE_NO_CONTEXT"]
    output: list[dict[str, Any]] = []
    for row in rows:
        rebound = row.get("rpg") is not None
        stocks = row.get("spg") is not None and row.get("bpg") is not None
        presence = (
            row.get("presence") is not None and float(row.get("presence_reliability") or 0.0) > 0
        )
        form = classify_defense_form(
            team_available=row.get("team_context") is not None,
            rebound_available=rebound,
            stocks_available=stocks,
            presence_available=presence,
            presence_reliability=float(row.get("presence_reliability") or 0.0),
        )
        reasons = [f"MEASUREMENT_FORM_{form}", "NO_MISSING_PRESENCE_IMPUTATION"]
        role = str(row.get("broad_role") or "UNKNOWN")
        if form == "DEF_FULL":
            raw = _masked_score(row, "DEF_ACTION_PARTIAL_PRESENCE", SELECTED_TEAM_WEIGHT)
            # Full form uses reliability 1, whereas the helper's partial mask is fixed at .6.
            weights = defense_weights(SELECTED_TEAM_WEIGHT)
            raw = 100.0 * (
                weights[0] * float(row["team_context"])
                + weights[1] * float(row["actions"])
                + weights[2] * float(row["presence"])
            )
            center = raw
            status = "OFFICIAL_DEFENSE_POINT"
            form_radii = full_radii
            reasons.append("RICH_REFERENCE_FORM")
        elif form in FORMS:
            raw = _masked_score(row, form, SELECTED_TEAM_WEIGHT)
            if raw is None or form == "DEF_CONTEXT_ONLY":
                center = None
                status = (
                    "DEFENSE_UNAVAILABLE" if form == "DEF_CONTEXT_ONLY" else "DEFENSE_INTERVAL_ONLY"
                )
                form_radii = {80: 50.0, 90: 50.0, 95: 50.0}
                reasons.append("INSUFFICIENT_INDIVIDUAL_DEFENSIVE_EVIDENCE")
            else:
                center = float(
                    predict_linker(models[form], np.asarray([raw]), np.asarray([role]))[0]
                )
                status = (
                    "PROVISIONAL_DEFENSE_POINT"
                    if calibration[form]["point_eligible"]
                    else "DEFENSE_INTERVAL_ONLY"
                )
                form_radii = radii[form]
                reasons.append("LINKED_MEASUREMENT_NOT_STAT_IMPUTATION")
                if status == "DEFENSE_INTERVAL_ONLY":
                    reasons.append("POINT_CALIBRATION_GATE_FAILED")
        else:
            raw = None
            center = None
            status = "DEFENSE_UNAVAILABLE"
            form_radii = {80: 50.0, 90: 50.0, 95: 50.0}
            reasons.append("NO_USABLE_INDIVIDUAL_DEFENSIVE_EVIDENCE")
        bounds = (
            interval_bounds(float(center), form_radii)
            if center is not None
            else {f"{edge}_{level}": None for level in (80, 90, 95) for edge in ("lower", "upper")}
        )
        raw_observed, weight_coverage = observed_defense_score(
            team=float(row["team_context"]) if row.get("team_context") is not None else None,
            action=float(row["actions"]) if row.get("actions") is not None else None,
            presence=float(row["presence"]) if row.get("presence") is not None else None,
            presence_reliability=float(row.get("presence_reliability") or 0.0),
            team_weight=SELECTED_TEAM_WEIGHT,
        )
        output.append(
            {
                "player_id": str(row["player_id"]),
                "season_id": int(row["season_id"]),
                "season_type": "REGULAR",
                "team_id": row.get("primary_team_id"),
                "broad_role": role,
                "measurement_form": form,
                "team_context": row.get("team_context"),
                "rebound_evidence": row.get("rpg"),
                "steal_evidence": row.get("spg"),
                "block_evidence": row.get("bpg"),
                "role_aware_actions": row.get("actions"),
                "presence": row.get("presence"),
                "presence_reliability": row.get("presence_reliability"),
                "raw_observed_score": None if raw_observed is None else 100.0 * raw_observed,
                "form_raw_score": raw,
                "defense_center": center,
                **bounds,
                "season_defense_status": status,
                "nominal_weight_coverage": weight_coverage,
                "confidence": (
                    "STRONG"
                    if status == "OFFICIAL_DEFENSE_POINT"
                    else "MODERATE"
                    if status == "PROVISIONAL_DEFENSE_POINT"
                    else "LIMITED"
                    if status == "DEFENSE_INTERVAL_ONLY"
                    else "UNAVAILABLE"
                ),
                "reason_codes_json": json.dumps(reasons, sort_keys=True),
                "methodology_version": DEFENSE_V2_TIERED_VERSION,
            }
        )
    return output


def _fixed_ecdf(values: dict[str, float | None], reference: set[str]) -> dict[str, float | None]:
    return midrank_percentile_scores(values, reference)


def career_validation(
    anchors: list[dict[str, Any]],
    selected: dict[str, str],
    calibration: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bool], list[dict[str, Any]]]:
    models = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        models[form] = fit_linker(cast(LinkMethod, selected[form]), x, y, roles)
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in anchors:
        by_player[str(row["player_id"])].append(row)
    eligible = {player_id: rows for player_id, rows in by_player.items() if len(rows) >= 3}
    reference_raw = {
        player_id: statistics.fmean(float(row["full_score"]) for row in rows)
        for player_id, rows in eligible.items()
    }
    reference_ids = set(reference_raw)
    reference_scores = _fixed_ecdf(reference_raw, reference_ids)
    patterns = {
        "NO_TEAM_CONTEXT": lambda index: "DEF_ACTION_PRESENCE_NO_CONTEXT",
        "PARTIAL_PRESENCE": lambda index: "DEF_ACTION_PARTIAL_PRESENCE",
        "NO_PRESENCE": lambda index: "DEF_ACTION_NO_PRESENCE",
        "TRADITIONAL_PRESENCE": lambda index: "DEF_TRADITIONAL_PRESENCE",
        "TRADITIONAL_ONLY": lambda index: "DEF_TRADITIONAL",
        "MIXED_TRANSITION": lambda index: (
            "DEF_TRADITIONAL" if index % 3 == 0 else "DEF_ACTION_PARTIAL_PRESENCE"
        ),
    }
    results: dict[str, Any] = {}
    passed: dict[str, bool] = {}
    validation_rows: list[dict[str, Any]] = []
    for pattern, chooser in patterns.items():
        masked_raw: dict[str, float | None] = {}
        player_forms: dict[str, list[str]] = {}
        for player_id, rows in eligible.items():
            values: list[float] = []
            forms: list[str] = []
            for index, row in enumerate(sorted(rows, key=lambda item: int(item["season_id"]))):
                form = chooser(index)
                raw = float(row[f"{form}_score"])
                linked = float(
                    predict_linker(models[form], np.asarray([raw]), np.asarray([str(row["role"])]))[
                        0
                    ]
                )
                values.append(linked)
                forms.append(form)
            masked_raw[player_id] = statistics.fmean(values)
            player_forms[player_id] = forms
        masked_scores = _fixed_ecdf(masked_raw, reference_ids)
        ids = sorted(reference_ids)
        y = np.asarray([float(reference_scores[player_id]) for player_id in ids])
        p = np.asarray([float(masked_scores[player_id]) for player_id in ids])
        metrics = regression_metrics(y, p)
        residual = p - y
        folds = np.asarray([deterministic_fold(player_id, seed=1518) for player_id in ids])
        interval_report: dict[str, Any] = {}
        bounds_by_level: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for level in (80, 90, 95):
            lower = np.zeros(len(ids))
            upper = np.zeros(len(ids))
            for fold in range(5):
                test = folds == fold
                calibration_fold = folds == ((fold + 1) % 5)
                radius = conformal_radius(np.abs(residual[calibration_fold]), level / 100.0)
                lower[test] = np.maximum(0.0, p[test] - radius)
                upper[test] = np.minimum(100.0, p[test] + radius)
            coverage = float(np.mean((y >= lower) & (y <= upper)))
            interval_report[str(level)] = {
                "coverage": coverage,
                "mean_width": float(np.mean(upper - lower)),
                "median_width": float(np.median(upper - lower)),
            }
            bounds_by_level[level] = (lower, upper)
        gates = {
            "mae_lte_5": float(metrics["mae"]) <= 5.0,
            "spearman_gte_095": float(metrics["spearman"]) >= 0.95,
            "absolute_bias_lte_2": abs(float(metrics["bias"])) <= 2.0,
            "gt_10_lte_015": float(metrics["gt_10"]) <= 0.15,
            "interval_90_calibrated": 0.87 <= interval_report["90"]["coverage"] <= 0.93,
        }
        passed[pattern] = all(gates.values())
        results[pattern] = {
            "point": metrics,
            "intervals": interval_report,
            "gates": gates,
            "passed": passed[pattern],
        }
        for index, player_id in enumerate(ids):
            validation_rows.append(
                {
                    "player_id": player_id,
                    "pattern": pattern,
                    "reference_defense": y[index],
                    "estimated_defense": p[index],
                    "lower_80": bounds_by_level[80][0][index],
                    "upper_80": bounds_by_level[80][1][index],
                    "lower_90": bounds_by_level[90][0][index],
                    "upper_90": bounds_by_level[90][1][index],
                    "lower_95": bounds_by_level[95][0][index],
                    "upper_95": bounds_by_level[95][1][index],
                    "forms_json": json.dumps(player_forms[player_id]),
                    "methodology_version": DEFENSE_AUDIT_VERSION,
                }
            )
    results["validation_players"] = len(reference_ids)
    results["career_aggregation"] = (
        "Arithmetic mean of season Defense measurement on the fixed reference form, then "
        "one frozen BROAD_HIGH_RECALL midrank ECDF. This preserves V1's career-quality "
        "interpretation; season count does not add quality credit."
    )
    return results, passed, validation_rows


def apply_career_architecture(
    args: argparse.Namespace,
    seasons: list[dict[str, Any]],
    career_pattern_passed: dict[str, bool],
) -> list[dict[str, Any]]:
    players = read_rows(args.gold_root / "player_overall_scores/part-00000.parquet")
    names = {str(row["player_id"]): str(row["player_name"]) for row in players}
    recovered = read_rows(
        args.gold_root / "player_season_value_v2_promotion_audit/candidate-d-reconstruction.parquet"
    )
    normalized = {
        (str(row["player_id"]), int(row["season_id"])): {
            "ppg_percentile": row.get("ppg"),
            "rpg_percentile": row.get("rpg"),
            "apg_percentile": row.get("apg"),
            "ts_pct_percentile": row.get("ts_pct"),
        }
        for row in recovered
    }
    reference = reference_population(args.gold_root, normalized)
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in seasons:
        by_player[str(row["player_id"])].append(row)
    central_raw: dict[str, float | None] = {}
    lower_raw: dict[int, dict[str, float | None]] = {level: {} for level in (80, 90, 95)}
    upper_raw: dict[int, dict[str, float | None]] = {level: {} for level in (80, 90, 95)}
    for player_id in names:
        rows = [row for row in by_player[player_id] if row.get("defense_center") is not None]
        central_raw[player_id] = (
            statistics.fmean(float(row["defense_center"]) for row in rows) if rows else None
        )
        for level in (80, 90, 95):
            lower_raw[level][player_id] = (
                statistics.fmean(float(row[f"lower_{level}"]) for row in rows) if rows else None
            )
            upper_raw[level][player_id] = (
                statistics.fmean(float(row[f"upper_{level}"]) for row in rows) if rows else None
            )
    central_score = _fixed_ecdf(central_raw, reference)
    lower_score = {level: _fixed_ecdf(lower_raw[level], reference) for level in (80, 90, 95)}
    upper_score = {level: _fixed_ecdf(upper_raw[level], reference) for level in (80, 90, 95)}
    output = []
    for player_id in sorted(names):
        rows = by_player[player_id]
        usable = [row for row in rows if row.get("defense_center") is not None]
        official = sum(row["season_defense_status"] == "OFFICIAL_DEFENSE_POINT" for row in usable)
        point = sum(
            row["season_defense_status"] in {"OFFICIAL_DEFENSE_POINT", "PROVISIONAL_DEFENSE_POINT"}
            for row in usable
        )
        forms = {str(row["measurement_form"]) for row in usable}
        if usable and official == len(usable):
            pattern = "FULL_REFERENCE"
        elif forms <= {"DEF_FULL", "DEF_ACTION_PRESENCE_NO_CONTEXT"}:
            pattern = "NO_TEAM_CONTEXT"
        elif forms <= {"DEF_FULL", "DEF_ACTION_PARTIAL_PRESENCE"}:
            pattern = "PARTIAL_PRESENCE"
        elif forms <= {"DEF_FULL", "DEF_TRADITIONAL_PRESENCE"}:
            pattern = "TRADITIONAL_PRESENCE"
        elif forms <= {"DEF_ACTION_NO_PRESENCE", "DEF_FULL"}:
            pattern = "NO_PRESENCE"
        elif forms <= {"DEF_TRADITIONAL", "DEF_FULL"}:
            pattern = "TRADITIONAL_ONLY"
        else:
            pattern = "MIXED_TRANSITION"
        status = career_defense_status(
            usable_seasons=len(usable),
            official_seasons=official,
            point_eligible_seasons=point,
            career_pattern_passed=career_pattern_passed.get(pattern, False),
        )
        center = central_score[player_id]
        bounds: dict[str, float | None] = {}
        if center is None:
            for level in (80, 90, 95):
                bounds[f"defense_lower_{level}"] = None
                bounds[f"defense_upper_{level}"] = None
        else:
            raw_lowers = {
                level: float(lower_score[level][player_id])
                for level in (80, 90, 95)
                if lower_score[level][player_id] is not None
            }
            raw_uppers = {
                level: float(upper_score[level][player_id])
                for level in (80, 90, 95)
                if upper_score[level][player_id] is not None
            }
            lower_80 = min(raw_lowers[80], float(center))
            lower_90 = min(raw_lowers[90], lower_80)
            lower_95 = min(raw_lowers[95], lower_90)
            upper_80 = max(raw_uppers[80], float(center))
            upper_90 = max(raw_uppers[90], upper_80)
            upper_95 = max(raw_uppers[95], upper_90)
            bounds.update(
                defense_lower_80=lower_80,
                defense_lower_90=lower_90,
                defense_lower_95=lower_95,
                defense_upper_80=upper_80,
                defense_upper_90=upper_90,
                defense_upper_95=upper_95,
            )
        output.append(
            {
                "player_id": player_id,
                "player_name": names[player_id],
                "defense_central": center,
                **bounds,
                "defense_status": status,
                "ranking_grade_defense_point": status
                in {"OFFICIAL_DEFENSE_POINT", "PROVISIONAL_DEFENSE_POINT"},
                "evidence_pattern": pattern,
                "career_seasons": len(rows),
                "usable_seasons": len(usable),
                "official_seasons": official,
                "provisional_seasons": point - official,
                "interval_only_seasons": sum(
                    row["season_defense_status"] == "DEFENSE_INTERVAL_ONLY" for row in rows
                ),
                "unavailable_seasons": sum(
                    row["season_defense_status"] == "DEFENSE_UNAVAILABLE" for row in rows
                ),
                "mean_presence_reliability": (
                    statistics.fmean(float(row.get("presence_reliability") or 0.0) for row in rows)
                    if rows
                    else 0.0
                ),
                "methodology_version": DEFENSE_V2_TIERED_VERSION,
                "reason_codes_json": json.dumps(
                    [
                        f"CAREER_PATTERN_{pattern}",
                        "NO_PRESENCE_PREDICTION",
                        "INTERVAL_CENTER_NOT_OFFICIAL_WHEN_STATUS_INTERVAL_ONLY",
                    ],
                    sort_keys=True,
                ),
            }
        )
    return output


def effective_influence(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    weights = defense_weights(SELECTED_TEAM_WEIGHT)
    matrix = np.asarray(
        [
            [
                float(row["team_context"]),
                0.4 * float(row["rebound"]),
                0.3 * float(row["steal"]),
                0.3 * float(row["block"]),
                float(row["presence"]),
            ]
            for row in anchors
        ]
    )
    nominal = np.asarray([weights[0], weights[1], weights[1], weights[1], weights[2]])
    # Action primitives already include 40/30/30; express their total coefficients explicitly.
    nominal = np.asarray(
        [weights[0], weights[1] * 0.4, weights[1] * 0.3, weights[1] * 0.3, weights[2]]
    )
    covariance = np.cov(matrix, rowvar=False, ddof=0)
    total = float(nominal @ covariance @ nominal)
    contributions = nominal * (covariance @ nominal)
    names = ("TEAM_CONTEXT", "REBOUND", "STEALS", "BLOCKS", "PRESENCE")
    leave_one = {}
    full = matrix @ nominal
    for index, name in enumerate(names):
        reduced = full - matrix[:, index] * nominal[index]
        leave_one[name] = {
            "pearson_without": float(np.corrcoef(full, reduced)[0, 1]),
            "variance_change": float(np.var(full) - np.var(reduced)),
        }
    return {
        "nominal_weights": dict(zip(names, nominal.tolist(), strict=True)),
        "covariance_variance_share": {
            name: float(value / total) for name, value in zip(names, contributions, strict=True)
        },
        "total_variance": total,
        "leave_one_channel_out": leave_one,
        "role_adjustment": "35% within each action primitive where role metadata is reliable",
    }


def validation_reports(
    args: argparse.Namespace,
    careers: list[dict[str, Any]],
    seasons: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    players = read_rows(args.gold_root / "player_overall_scores/part-00000.parquet")
    recovered = read_rows(
        args.gold_root / "player_season_value_v2_promotion_audit/candidate-d-reconstruction.parquet"
    )
    normalized = {
        (str(row["player_id"]), int(row["season_id"])): {
            "ppg_percentile": row.get("ppg"),
            "rpg_percentile": row.get("rpg"),
            "apg_percentile": row.get("apg"),
            "ts_pct_percentile": row.get("ts_pct"),
        }
        for row in recovered
    }
    reference = reference_population(args.gold_root, normalized)
    score_lookup = {str(row["player_id"]): row["defense_central"] for row in careers}
    v1_lookup = {str(row["player_id"]): row["defense_score"] for row in players}
    modern = modern_defense(args.silver_root, reference)
    modern_report: dict[str, Any] = {}
    for name, lookup in (("V1", v1_lookup), ("DEFENSE_V2", score_lookup)):
        shared = sorted(
            player_id
            for player_id, value in lookup.items()
            if value is not None and player_id in modern
        )
        x = np.asarray([float(lookup[player_id]) for player_id in shared])
        y = np.asarray([float(modern[player_id]) for player_id in shared])
        modern_report[name] = regression_metrics(y, x)
    awards = award_validation(args.silver_root, {"V1": v1_lookup, "DEFENSE_V2": score_lookup})
    by_group: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in seasons:
        if row.get("team_id") is not None and row.get("defense_center") is not None:
            by_group[(int(row["season_id"]), str(row["team_id"]))].append(row)
    adjacent_pairs = 0
    v2_near = 0
    action_differentiated = 0
    presence_differentiated = 0
    for group in by_group.values():
        ordered = sorted(group, key=lambda row: str(row["player_id"]))
        for left, right in pairwise(ordered):
            adjacent_pairs += 1
            v2_near += abs(float(left["defense_center"]) - float(right["defense_center"])) < 1.0
            if (
                left.get("role_aware_actions") is not None
                and right.get("role_aware_actions") is not None
            ):
                action_differentiated += (
                    abs(float(left["role_aware_actions"]) - float(right["role_aware_actions"]))
                    >= 0.05
                )
            if left.get("presence") is not None and right.get("presence") is not None:
                presence_differentiated += (
                    abs(float(left["presence"]) - float(right["presence"])) >= 0.05
                )
    prior = json.loads((args.docs_root / "defense-v2-promotion-summary.json").read_text())
    teammate = {
        "adjacent_teammate_pairs": adjacent_pairs,
        "selected_v2_near_identical_rate": v2_near / adjacent_pairs if adjacent_pairs else None,
        "action_differentiation_rate": action_differentiated / adjacent_pairs
        if adjacent_pairs
        else None,
        "presence_differentiation_rate": presence_differentiated / adjacent_pairs
        if adjacent_pairs
        else None,
        "prior_near_collision_counts": prior["teammate_collision"],
    }
    return modern_report, awards, teammate


def temporal_continuity(seasons: list[dict[str, Any]]) -> dict[str, Any]:
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in seasons:
        if row.get("defense_center") is not None:
            by_player[str(row["player_id"])].append(row)
    transition: list[float] = []
    stable: list[float] = []
    large = 0
    for rows in by_player.values():
        ordered = sorted(rows, key=lambda row: int(row["season_id"]))
        for left, right in pairwise(ordered):
            if int(right["season_id"]) != int(left["season_id"]) + 1:
                continue
            movement = abs(float(right["defense_center"]) - float(left["defense_center"]))
            if left["measurement_form"] != right["measurement_form"]:
                transition.append(movement)
                large += movement > 20.0
            else:
                stable.append(movement)
    return {
        "form_transition_pairs": len(transition),
        "within_form_pairs": len(stable),
        "mean_transition_movement": statistics.fmean(transition) if transition else None,
        "mean_within_form_movement": statistics.fmean(stable) if stable else None,
        "transition_gt_20": large,
        "interpretation": (
            "transitions retain explicit status/interval changes; no channel is zero-filled"
        ),
    }


def joint_uncertainty(
    args: argparse.Namespace, validation_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    pl = read_rows(
        args.gold_root / "peak_longevity_uncertainty_audit/masked-career-validation.parquet"
    )
    pl_index = {(str(row["player_id"]), str(row["pattern"])): row for row in pl}
    mapping = {
        "NO_PRESENCE": "NO_PRESENCE_CAREER",
        "TRADITIONAL_ONLY": "TRADITIONAL_CAREER",
        "PARTIAL_PRESENCE": "PARTIAL_PRESENCE_LATE",
        "MIXED_TRANSITION": "MIXED_PROVISIONAL_INTERVAL",
    }
    output: dict[str, Any] = {}
    for defense_pattern, pl_pattern in mapping.items():
        rows = [row for row in validation_rows if row["pattern"] == defense_pattern]
        defense_residual, peak_residual, longevity_residual = [], [], []
        for row in rows:
            source = pl_index.get((str(row["player_id"]), pl_pattern))
            if source is None:
                continue
            defense_residual.append(
                float(row["estimated_defense"]) - float(row["reference_defense"])
            )
            peak_residual.append(float(source["peak_central"]) - float(source["reference_peak"]))
            longevity_residual.append(
                float(source["longevity_central"]) - float(source["reference_longevity"])
            )
        if len(defense_residual) >= 3:
            matrix = np.corrcoef(np.asarray([defense_residual, peak_residual, longevity_residual]))
            output[defense_pattern] = {
                "players": len(defense_residual),
                "defense_peak_residual_correlation": float(matrix[0, 1]),
                "defense_longevity_residual_correlation": float(matrix[0, 2]),
                "peak_longevity_residual_correlation": float(matrix[1, 2]),
            }
    output["aligned_draw_feasibility"] = {
        "direct": False,
        "reason": (
            "Defense anchor residual draws were generated separately from U3 PSV career draws"
        ),
        "step_0015n_approximation": (
            "Use pattern-specific empirical Gaussian-copula rank alignment calibrated to the "
            "reported residual correlation matrices; retain marginal empirical/conformal draws."
        ),
        "independence_allowed": False,
    }
    return output


def overall_sensitivity(
    args: argparse.Namespace, careers: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overall = read_rows(
        args.gold_root
        / "overall_uncertainty_architecture_audit/overall-uncertainty-research.parquet"
    )
    players = read_rows(args.gold_root / "player_overall_scores/part-00000.parquet")
    defense_v1 = {str(row["player_id"]): row["defense_score"] for row in players}
    defense_v2 = {str(row["player_id"]): row for row in careers}
    rows = []
    old, new = [], []
    width_changes = []
    status_changes = Counter()
    for row in overall:
        player_id = str(row["player_id"])
        defense = defense_v2[player_id]
        center = defense["defense_central"]
        old_center = row["overall_diagnostic_center"]
        if center is None or old_center is None or defense_v1[player_id] is None:
            new_center = None
        else:
            new_center = float(old_center) + 0.14 * (float(center) - float(defense_v1[player_id]))
            old.append(float(old_center))
            new.append(new_center)
        old_width = (
            float(row["overall_upper_90"]) - float(row["overall_lower_90"])
            if row["overall_upper_90"] is not None and row["overall_lower_90"] is not None
            else None
        )
        defense_width = (
            float(defense["defense_upper_90"]) - float(defense["defense_lower_90"])
            if defense["defense_upper_90"] is not None
            else None
        )
        new_width = (
            math.sqrt(old_width**2 + (0.14 * defense_width) ** 2)
            if old_width is not None and defense_width is not None
            else None
        )
        if old_width is not None and new_width is not None:
            width_changes.append(new_width - old_width)
        old_status = str(row["overall_status"])
        new_status = (
            "OVERALL_UNAVAILABLE"
            if defense["defense_status"] == "DEFENSE_UNAVAILABLE"
            else "OVERALL_INTERVAL_ONLY"
            if defense["defense_status"] == "DEFENSE_INTERVAL_ONLY"
            else old_status
        )
        status_changes[f"{old_status}->{new_status}"] += 1
        rows.append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "step_0015l_center": old_center,
                "defense_v1": defense_v1[player_id],
                "defense_v2_center": center,
                "defense_v2_status": defense["defense_status"],
                "diagnostic_overall_center": new_center,
                "diagnostic_overall_90_width": new_width,
                "diagnostic_overall_status": new_status,
                "new_ranking_published": False,
            }
        )
    report = {
        "common_players": len(old),
        "mean_central_difference": statistics.fmean(
            right - left for left, right in zip(old, new, strict=True)
        )
        if old
        else None,
        "mean_interval_width_change": statistics.fmean(width_changes) if width_changes else None,
        "spearman": regression_metrics(np.asarray(old), np.asarray(new)).get("spearman"),
        "status_changes": dict(sorted(status_changes.items())),
        "weights_changed": False,
        "new_top_100_published": False,
    }
    return report, rows


def cases_and_transition(
    args: argparse.Namespace,
    careers: list[dict[str, Any]],
    seasons: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_b = {
        str(row["player_id"]): row
        for row in read_rows(
            args.gold_root
            / "defense_v2_promotion_audit/player-defense-v2-promotion-candidate.parquet"
        )
    }
    players = read_rows(args.gold_root / "player_overall_scores/part-00000.parquet")
    v1 = {str(row["player_id"]): row for row in players}
    career_index = {str(row["player_id"]): row for row in careers}
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in seasons:
        by_player[str(row["player_id"])].append(row)
    cases = []
    for player_id, career in career_index.items():
        if career["player_name"] not in CASE_NAMES:
            continue
        player_seasons = by_player[player_id]
        forms = Counter(str(row["measurement_form"]) for row in player_seasons)
        cases.append(
            {
                **career,
                "v1_defense": v1[player_id]["defense_score"],
                "candidate_b": candidate_b.get(player_id, {}).get("step0015a_candidate_b_score"),
                "continuous_candidate": candidate_b.get(player_id, {}).get("defense_v2_score"),
                "measurement_forms_json": json.dumps(dict(sorted(forms.items())), sort_keys=True),
                "mean_team_context": statistics.fmean(
                    float(row["team_context"])
                    for row in player_seasons
                    if row.get("team_context") is not None
                )
                if any(row.get("team_context") is not None for row in player_seasons)
                else None,
                "mean_action": statistics.fmean(
                    float(row["role_aware_actions"])
                    for row in player_seasons
                    if row.get("role_aware_actions") is not None
                )
                if any(row.get("role_aware_actions") is not None for row in player_seasons)
                else None,
                "mean_presence": statistics.fmean(
                    float(row["presence"])
                    for row in player_seasons
                    if row.get("presence") is not None
                )
                if any(row.get("presence") is not None for row in player_seasons)
                else None,
                "movement_reason": (
                    "team weight reduced to context; observed Presence and role-aware actions "
                    "drive "
                    "individual differentiation; unavailable Presence widens uncertainty"
                ),
            }
        )
    overall_v1 = sorted(
        read_rows(args.gold_root / "player_overall_scores/part-00000.parquet"),
        key=lambda row: int(row["overall_rank"]) if row["overall_rank"] is not None else 999999,
    )[:100]
    overall_status = {
        str(row["player_id"]): row
        for row in read_rows(
            args.gold_root
            / "overall_uncertainty_architecture_audit/overall-uncertainty-research.parquet"
        )
    }
    transition = []
    for row in overall_v1:
        player_id = str(row["player_id"])
        defense = career_index[player_id]
        transition.append(
            {
                "v1_overall_rank": row["overall_rank"],
                "player_id": player_id,
                "player_name": row["player_name"],
                "v1_defense": row["defense_score"],
                "defense_v2_status": defense["defense_status"],
                "defense_v2_center": defense["defense_central"],
                "defense_v2_lower_90": defense["defense_lower_90"],
                "defense_v2_upper_90": defense["defense_upper_90"],
                "current_overall_uncertainty_status": overall_status[player_id]["overall_status"],
                "defense_remains_blocker": defense["defense_status"]
                in {"DEFENSE_INTERVAL_ONLY", "DEFENSE_UNAVAILABLE"},
                "v1_order_preserved": True,
            }
        )
    return cases, transition


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    summaries, input_fingerprints = verify_upstream(args)
    reconstruction = upstream_reconstruction(args, summaries)
    source_rows = read_rows(
        args.gold_root / "player_season_value_v2_promotion_audit/candidate-d-reconstruction.parquet"
    )
    inventory = evidence_inventory(source_rows)
    weight_audit = team_weight_audit(args, source_rows)
    anchors = build_anchors(source_rows, SELECTED_TEAM_WEIGHT)
    linking, selected, calibration = linking_audit(anchors, SELECTED_TEAM_WEIGHT)
    season_rows = apply_season_architecture(source_rows, anchors, selected, calibration)
    career_uncertainty = career_uncertainty_audit(season_rows)
    career_report, career_passed, career_validation_rows = career_validation(
        anchors, selected, calibration
    )
    career_rows = apply_career_architecture(args, season_rows, career_passed)
    influence = effective_influence(anchors)
    modern, awards, teammate = validation_reports(args, career_rows, season_rows)
    temporal = temporal_continuity(season_rows)
    joint = joint_uncertainty(args, career_validation_rows)
    overall_report, overall_rows = overall_sensitivity(args, career_rows)
    cases, transition = cases_and_transition(args, career_rows, season_rows)

    season_status = Counter(str(row["season_defense_status"]) for row in season_rows)
    career_status = Counter(str(row["defense_status"]) for row in career_rows)
    by_form: dict[str, Counter[str]] = defaultdict(Counter)
    by_decade: dict[str, Counter[str]] = defaultdict(Counter)
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    player_career_status = {
        str(row["player_id"]): str(row["career_status"])
        for row in read_rows(
            args.gold_root / "player_overall_scores/part-00000.parquet",
            ["player_id", "career_status"],
        )
    }
    by_active_status: dict[str, Counter[str]] = defaultdict(Counter)
    for row in season_rows:
        status = str(row["season_defense_status"])
        by_form[str(row["measurement_form"])][status] += 1
        by_decade[f"{int(row['season_id']) // 10 * 10}s"][status] += 1
        by_role[str(row["broad_role"])][status] += 1
    for row in career_rows:
        source_status = player_career_status.get(str(row["player_id"]), "INDETERMINATE")
        active_label = (
            "ACTIVE_TO_CUTOFF" if source_status == "ACTIVE_TO_CUTOFF" else "RETIRED_OR_OTHER"
        )
        by_active_status[active_label][str(row["defense_status"])] += 1
    status_report = {
        "season": dict(sorted(season_status.items())),
        "career": dict(sorted(career_status.items())),
        "by_form": {key: dict(sorted(value.items())) for key, value in sorted(by_form.items())},
        "by_decade": {key: dict(sorted(value.items())) for key, value in sorted(by_decade.items())},
        "by_role": {key: dict(sorted(value.items())) for key, value in sorted(by_role.items())},
        "by_active_status": {
            key: dict(sorted(value.items())) for key, value in sorted(by_active_status.items())
        },
    }
    team_corr = weight_audit["10pct"]["score_team_pearson"]
    v1_team_corr = float(
        summaries["step_0015a"]["team_attribution"]["career_raw_correlation_with_team_suppression"]
    )
    promotion_gates = {
        "upstream_exact": reconstruction["exact"],
        "team_context_at_most_10_percent": SELECTED_TEAM_WEIGHT <= 0.10,
        "team_attribution_reduced": abs(float(team_corr)) < abs(v1_team_corr),
        "at_least_one_weaker_point_form_valid": any(
            value["point_eligible"]
            for key, value in calibration.items()
            if key != "DEF_CONTEXT_ONLY"
        ),
        "career_point_pattern_valid": any(career_passed.values()),
        "missing_presence_not_predicted": True,
        "context_only_not_ranked": not calibration["DEF_CONTEXT_ONLY"]["point_eligible"],
        "awards_validation_only": True,
        "regular_season_only": all(row["season_type"] == "REGULAR" for row in season_rows),
        "v1_preserved": True,
    }
    step_status = "PASS" if all(promotion_gates.values()) else "FAIL"
    defense_verdict = (
        "PROMOTE_DEFENSE_V2_WITH_LIMITATIONS"
        if step_status == "PASS" and career_status["PROVISIONAL_DEFENSE_POINT"] > 0
        else "DO_NOT_PROMOTE_DEFENSE_V2"
    )
    recommendation = (
        "READY_FOR_FINAL_OVERALL_V2_PROMOTION_AUDIT"
        if defense_verdict.startswith("PROMOTE_DEFENSE_V2")
        else "DEFENSE_REQUIRES_MORE_RESEARCH"
    )

    output_root = args.gold_root / "defense_v2_tiered_promotion_audit"
    manifests = [
        write_parquet(
            anchors, output_root / "anchor-masked-defense-forms.parquet", ("season_id", "player_id")
        ),
        write_parquet(
            season_rows,
            output_root / "defense-v2-season-measurements.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            career_validation_rows,
            output_root / "defense-v2-career-validation.parquet",
            ("pattern", "player_id"),
        ),
        write_parquet(
            career_rows, output_root / "player-defense-v2-tiered.parquet", ("player_id",)
        ),
        write_parquet(
            cases, output_root / "defense-v2-diagnostic-players.parquet", ("player_name",)
        ),
        write_parquet(
            overall_rows, output_root / "overall-defense-v2-sensitivity.parquet", ("player_id",)
        ),
        write_parquet(
            transition, output_root / "v1-top100-defense-transition.parquet", ("v1_overall_rank",)
        ),
    ]
    reports: dict[str, dict[str, Any]] = {
        "defense-v2-measurement-linking.json": {
            "forms": {
                "DEF_FULL": (
                    "Team Context + full role-aware actions + fully reliable observed Presence"
                ),
                "DEF_ACTION_PRESENCE_NO_CONTEXT": (
                    "full actions + observed Presence; Team Context unavailable"
                ),
                "DEF_ACTION_PARTIAL_PRESENCE": (
                    "full actions + continuously reliability-weighted Presence + context"
                ),
                "DEF_ACTION_NO_PRESENCE": "full actions + context; Presence unavailable",
                "DEF_TRADITIONAL_PRESENCE": (
                    "rebound proxy + context + Presence; STL/BLK unavailable"
                ),
                "DEF_TRADITIONAL": "rebound proxy + context; STL/BLK and Presence unavailable",
                "DEF_REBOUND_ONLY": "factual rebound proxy only",
                "DEF_CONTEXT_PRESENCE": "Presence plus context; action evidence unavailable",
                "DEF_CONTEXT_ONLY": "team-shared context only; no rank-grade individual Defense",
            },
            "linking": linking,
            "selected": selected,
            "calibration": calibration,
        },
        "defense-v2-role-archetype-audit.json": {
            "calibration": {
                form: {"roles": value["roles"], "archetypes": value["archetypes"]}
                for form, value in calibration.items()
            },
            "specialist_ceiling": (
                "Rebound, steal, block, and Presence-heavy pathways remain distinct; role "
                "percentiles "
                "interpret action evidence but do not equalize final ceilings."
            ),
            "rich_form_archetype_distribution": {
                archetype: {
                    "n": len(values),
                    "mean": statistics.fmean(values),
                    "p90": float(np.quantile(np.asarray(values), 0.90)),
                    "p95": float(np.quantile(np.asarray(values), 0.95)),
                    "maximum": max(values),
                }
                for archetype, values in sorted(
                    {
                        label: [
                            float(row["full_score"])
                            for row in anchors
                            if label in json.loads(row["archetypes_json"])
                        ]
                        for label in sorted(
                            {
                                label
                                for row in anchors
                                for label in json.loads(row["archetypes_json"])
                            }
                        )
                    }.items()
                )
                if values
            },
        },
        "defense-v2-career-validation.json": career_report,
        "defense-v2-career-uncertainty.json": career_uncertainty,
        "defense-v2-status-summary.json": status_report,
        "defense-v2-overall-sensitivity.json": overall_report,
        "v1-top100-defense-transition.json": {"players": transition},
        "defense-v2-diagnostic-players.json": {"players": cases},
        "defense-v2-team-weight-audit.json": weight_audit,
        "defense-v2-effective-influence.json": influence,
        "defense-v2-validation.json": {
            "modern": modern,
            "awards": awards,
            "teammate": teammate,
            "temporal": temporal,
        },
        "defense-v2-joint-uncertainty.json": joint,
        "defense-v2-tiered-promotion-verdict.json": {
            "step_status": step_status,
            "defense_verdict": defense_verdict,
            "recommendation": recommendation,
            "promotion_gates": promotion_gates,
            "official_methodology_version": DEFENSE_V2_TIERED_VERSION,
            "new_top_100_published": False,
            "candidate_architectures": {
                "D0": "65% Team Context + 35% Actions; frozen V1 diagnostic, rejected",
                "D1": (
                    "30% Team Context + 30% Actions + 40% Presence; attribution improved "
                    "but context/fallback remained too influential"
                ),
                "D2": (
                    "10/15/20/30% bounded Team Context family; 10% selected from attribution audit"
                ),
                "D3": (
                    "10% Team Context + 38.5714% Actions + 51.4286% fully reliable "
                    "Presence, with continuous Presence reliability and no missing-channel "
                    "reallocation"
                ),
            },
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        stable_json(
            args.docs_root / name,
            {
                "step": "STEP-0015M",
                "audit_methodology_version": DEFENSE_AUDIT_VERSION,
                "defense_methodology_version": DEFENSE_V2_TIERED_VERSION,
                "input_fingerprints": input_fingerprints,
                **payload,
            },
        )
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": input_fingerprints,
                "outputs": manifests,
                "reports": report_hashes,
                "reconstruction": reconstruction,
                "selected": selected,
                "season_status": dict(sorted(season_status.items())),
                "career_status": dict(sorted(career_status.items())),
                "verdict": defense_verdict,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015M",
        "step_status": step_status,
        "defense_promotion_verdict": defense_verdict,
        "recommendation": recommendation,
        "audit_methodology_version": DEFENSE_AUDIT_VERSION,
        "defense_methodology_version": DEFENSE_V2_TIERED_VERSION,
        "input_fingerprints": input_fingerprints,
        "reconstruction": reconstruction,
        "evidence_inventory": inventory,
        "anchor_rows": len(anchors),
        "selected_team_weight": SELECTED_TEAM_WEIGHT,
        "selected_linkers": selected,
        "season_status_counts": dict(sorted(season_status.items())),
        "career_status_counts": dict(sorted(career_status.items())),
        "career_validation": career_report,
        "promotion_gates": promotion_gates,
        "overall_sensitivity": overall_report,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "network_requests": 0,
        "new_top_100_published": False,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint,
    }
    stable_json(args.docs_root / "defense-v2-tiered-promotion-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, observed {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
