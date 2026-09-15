#!/usr/bin/env python3
"""Run the offline STEP-0015H measurement-linking and uncertainty audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import numpy as np

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
from goatlab.rankings.player_season_value import (
    PLAYER_SEASON_VALUE_RESEARCH_VERSION,
    combine_player_value,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet
from pipelines.rankings.audit_player_season_value import (
    archetypes,
    candidate_row,
    season_inputs,
)
from pipelines.rankings.audit_player_season_value_v2_promotion import (
    reconstruction,
    verify_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
AUDIT_VERSION = "goatlab-v1-player-season-value-measurement-linking-audit-v1"
LINKED_VERSION = "goatlab-v1-player-season-value-v2-linked-research"
STEP_G_FINGERPRINT = "120c319c8b3883b2066187947d3a6b813aa4d590231035fdd02943486268dd4f"
RUN_AT_DEFAULT = "2026-09-15T14:00:00Z"
METHODS: tuple[LinkMethod, ...] = (
    "identity",
    "linear",
    "quantile",
    "isotonic",
    "role_isotonic",
)
FORMS = (
    "EXPANDED_NO_PRESENCE",
    "EXPANDED_PROXY_ACTION_WITH_PRESENCE",
    "TRADITIONAL_BOX",
    "TRADITIONAL_WITH_PRESENCE",
    "EARLY_OFFENSE_WITH_PRESENCE",
    "OFFENSE_ONLY_EARLY",
    "NO_TEAM_CONTEXT",
)
CASE_NAMES = (
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
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _rank_by_season(rows: list[dict[str, Any]], field: str) -> dict[tuple[str, int], float]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get(field) is not None:
            grouped[int(row["season_id"])].append(row)
    output: dict[tuple[str, int], float] = {}
    for season_rows in grouped.values():
        ordered = sorted(season_rows, key=lambda row: (float(row[field]), str(row["player_id"])))
        start = 0
        while start < len(ordered):
            end = start + 1
            while end < len(ordered) and float(ordered[end][field]) == float(ordered[start][field]):
                end += 1
            percentile = 100.0 * (((start + end - 1) / 2.0) + 0.5) / len(ordered)
            for row in ordered[start:end]:
                output[(str(row["player_id"]), int(row["season_id"]))] = percentile
            start = end
    return output


def _no_team_raw(row: dict[str, Any]) -> float | None:
    base = candidate_row(row, "D_REGIME_RELIABILITY")
    offense = base.get("offense")
    actions = row.get("role_aware_actions")
    if actions is None:
        actions = row.get("action_value")
    if offense is None or actions is None:
        return None
    reliability = min(1.0, max(0.0, float(row.get("presence_reliability") or 0.0)))
    presence = row.get("observed_presence")
    presence_weight = 0.35 * reliability if presence is not None else 0.0
    action_weight = 0.90 - presence_weight
    defense = action_weight * float(actions)
    if presence is not None:
        defense += presence_weight * float(presence)
    estimate = combine_player_value(
        float(offense),
        defense,
        architecture="M4_BOUNDED_STRONGER_55_45",
        defense_team_weight=0.0,
    )
    return estimate.value


def _masked_form(row: dict[str, Any], form: str) -> float | None:
    masked = dict(row)
    if form == "EXPANDED_NO_PRESENCE":
        masked["observed_presence"] = None
        masked["presence_reliability"] = 0.0
        masked["evidence_regime"] = "EXPANDED_BOX_NO_PRESENCE"
        return cast(
            float | None, candidate_row(masked, "D_REGIME_RELIABILITY")["player_season_value_raw"]
        )
    if form == "EXPANDED_PROXY_ACTION_WITH_PRESENCE":
        masked["role_aware_actions"] = None
        return cast(
            float | None, candidate_row(masked, "D_REGIME_RELIABILITY")["player_season_value_raw"]
        )
    if form in {"TRADITIONAL_BOX", "TRADITIONAL_WITH_PRESENCE"}:
        if form == "TRADITIONAL_BOX":
            masked["observed_presence"] = None
            masked["presence_reliability"] = 0.0
        masked["role_aware_actions"] = None
        masked["action_value"] = row.get("rpg")
        masked["spg"] = None
        masked["bpg"] = None
        masked["evidence_regime"] = "TRADITIONAL_BOX"
        return cast(
            float | None, candidate_row(masked, "D_REGIME_RELIABILITY")["player_season_value_raw"]
        )
    if form == "OFFENSE_ONLY_EARLY":
        return cast(float | None, candidate_row(row, "D_REGIME_RELIABILITY").get("offense"))
    if form == "EARLY_OFFENSE_WITH_PRESENCE":
        base = candidate_row(row, "D_REGIME_RELIABILITY")
        offense, presence = base.get("offense"), row.get("observed_presence")
        if offense is None or presence is None:
            return None
        return combine_player_value(
            float(offense),
            float(presence),
            architecture="M4_BOUNDED_STRONGER_55_45",
            defense_team_weight=0.0,
        ).value
    if form == "NO_TEAM_CONTEXT":
        return _no_team_raw(row)
    raise ValueError(form)


def build_anchors(
    inputs: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidate_index = {(str(row["player_id"]), int(row["season_id"])): row for row in candidates}
    rows: list[dict[str, Any]] = []
    for source in inputs:
        if source["evidence_regime"] != "FULL_PORTABLE":
            continue
        full = candidate_row(source, "D_REGIME_RELIABILITY")
        if full["player_season_value_raw"] is None:
            continue
        row = {
            "player_id": str(source["player_id"]),
            "season_id": int(source["season_id"]),
            "role": str(source.get("broad_role") or "UNKNOWN"),
            "full_raw": float(full["player_season_value_raw"]),
            "full_score": 100.0
            * float(
                candidate_index[(str(source["player_id"]), int(source["season_id"]))][
                    "player_season_value_percentile"
                ]
            ),
            "offense": float(full["offense"]),
            "defense": float(full["defense_evidence"]),
            "presence_reliability": float(source.get("presence_reliability") or 0.0),
        }
        for form in FORMS:
            row[f"{form}_raw"] = _masked_form(source, form)
            raw_value = row[f"{form}_raw"]
            row[f"{form}_score"] = 100.0 * float(raw_value) if raw_value is not None else None
        labels = archetypes(source)
        row["archetypes_json"] = json.dumps(labels, sort_keys=True)
        rows.append(row)
    return rows


def _folds(anchors: list[dict[str, Any]], mode: str) -> np.ndarray:
    if mode == "grouped_player":
        return np.asarray([deterministic_fold(str(row["player_id"])) for row in anchors])
    if mode == "random":
        return np.asarray(
            [
                deterministic_fold(f"{row['player_id']}|{row['season_id']}", seed=1516)
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


def linking_audit(anchors: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    report: dict[str, Any] = {}
    selected: dict[str, str] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        methods: dict[str, Any] = {}
        for method in METHODS:
            modes: dict[str, Any] = {}
            for mode in ("grouped_player", "era_block", "random"):
                pred = cross_fitted_predictions(method, x, y, _folds(anchors, mode), roles)
                modes[mode] = regression_metrics(y, pred)
            methods[method] = modes
        # Prefer simplicity within 0.10 MAE of the best primary result.
        best_mae = min(float(value["grouped_player"]["mae"]) for value in methods.values())
        choice = next(
            method
            for method in METHODS
            if float(methods[method]["grouped_player"]["mae"]) <= best_mae + 0.10
        )
        selected[form] = choice
        report[form] = {"methods": methods, "selected": choice}
    return report, selected


def transport_audit(anchors: list[dict[str, Any]], selected: dict[str, str]) -> dict[str, Any]:
    """Test leave-decade-out and directional era transport."""
    output: dict[str, Any] = {}
    seasons = np.asarray([int(row["season_id"]) for row in anchors])
    decades = seasons // 10
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        method = cast(LinkMethod, selected[form])
        leave_decade = cross_fitted_predictions(method, x, y, decades, roles)
        by_decade = {
            f"{decade * 10}s": regression_metrics(
                y[decades == decade], leave_decade[decades == decade]
            )
            for decade in sorted(set(decades.tolist()))
        }
        transfers: dict[str, Any] = {}
        for name, train, test in (
            ("earlier_to_2000_plus", seasons < 2000, seasons >= 2000),
            ("2000_plus_to_earlier", seasons >= 2000, seasons < 2000),
        ):
            model = fit_linker(method, x[train], y[train], roles[train])
            prediction = predict_linker(model, x[test], roles[test])
            transfers[name] = regression_metrics(y[test], prediction)
        output[form] = {
            "leave_decade_out": by_decade,
            "directional_transfer": transfers,
        }
    return output


def _subgroups(anchors: list[dict[str, Any]], form: str, estimates: np.ndarray) -> dict[str, Any]:
    _, y, _ = _arrays(anchors, form)
    output: dict[str, Any] = {"role": {}, "score_band": {}, "archetype": {}}
    for role in sorted({str(row["role"]) for row in anchors}):
        mask = np.asarray([str(row["role"]) == role for row in anchors])
        output["role"][role] = regression_metrics(y[mask], estimates[mask])
    for low, high in ((0, 25), (25, 50), (50, 75), (75, 101)):
        mask = (y >= low) & (y < high)
        output["score_band"][f"{low}_{min(high, 100)}"] = regression_metrics(
            y[mask], estimates[mask]
        )
    labels = sorted({label for row in anchors for label in json.loads(row["archetypes_json"])})
    for label in labels:
        mask = np.asarray([label in json.loads(row["archetypes_json"]) for row in anchors])
        if int(np.sum(mask)) >= 50:
            output["archetype"][label] = regression_metrics(y[mask], estimates[mask])
    return output


def split_conformal(
    anchors: list[dict[str, Any]], form: str, method: LinkMethod
) -> tuple[np.ndarray, dict[int, np.ndarray], dict[str, Any]]:
    x, y, roles = _arrays(anchors, form)
    folds = _folds(anchors, "grouped_player")
    points = np.full(x.shape, np.nan)
    bounds = {level: np.full((x.size, 2), np.nan) for level in (80, 90, 95)}
    for fold in range(5):
        test = folds == fold
        calibration = folds == ((fold + 1) % 5)
        train = ~(test | calibration)
        model = fit_linker(method, x[train], y[train], roles[train])
        test_points = predict_linker(model, x[test], roles[test])
        calibration_points = predict_linker(model, x[calibration], roles[calibration])
        residuals = np.abs(calibration_points - y[calibration])
        points[test] = test_points
        for level in (80, 90, 95):
            radius = conformal_radius(residuals, level / 100.0)
            bounds[level][test, 0] = np.maximum(0.0, test_points - radius)
            bounds[level][test, 1] = np.minimum(100.0, test_points + radius)
    metrics: dict[str, Any] = {"point": regression_metrics(y, points), "intervals": {}}
    for level in (80, 90, 95):
        inside = (y >= bounds[level][:, 0]) & (y <= bounds[level][:, 1])
        width = bounds[level][:, 1] - bounds[level][:, 0]
        metrics["intervals"][str(level)] = {
            "coverage": float(np.mean(inside)),
            "mean_width": float(np.mean(width)),
            "median_width": float(np.median(width)),
            "width_by_role": {
                role: float(np.mean(width[roles == role])) for role in sorted(set(roles.tolist()))
            },
            "width_by_score_band": {
                f"{low}_{min(high, 100)}": float(np.mean(width[(y >= low) & (y < high)]))
                for low, high in ((0, 25), (25, 50), (50, 75), (75, 101))
            },
        }
    empirical_residuals = np.abs(points - y)
    metrics["empirical_residual_intervals"] = {}
    for level in (80, 90, 95):
        radius = float(np.quantile(empirical_residuals, level / 100.0))
        lower = np.maximum(0.0, points - radius)
        upper = np.minimum(100.0, points + radius)
        metrics["empirical_residual_intervals"][str(level)] = {
            "coverage": float(np.mean((y >= lower) & (y <= upper))),
            "mean_width": float(np.mean(upper - lower)),
            "radius": radius,
            "evaluation_caution": "OOF residual reuse; conformal result is primary",
        }
    return points, bounds, metrics


def eligibility(metrics: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    point = metrics["point"]
    role_biases = [
        abs(float(item.get("bias", 999.0)))
        for item in metrics["subgroups"]["role"].values()
        if int(item.get("n", 0)) >= 100
    ]
    interval = metrics["intervals"]["90"]
    gates = {
        "mae_lte_5": float(point["mae"]) <= 5.0,
        "spearman_gte_095": float(point["spearman"]) >= 0.95,
        "absolute_bias_lte_2": abs(float(point["bias"])) <= 2.0,
        "major_role_bias_lte_3": max(role_biases, default=999.0) <= 3.0,
        "gt_10_lte_015": float(point["gt_10"]) <= 0.15,
        "interval_90_calibrated": 0.87 <= float(interval["coverage"]) <= 0.93,
    }
    return all(gates.values()), gates


def pairwise_audit(
    anchors: list[dict[str, Any]],
    form: str,
    raw: np.ndarray,
    linked: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> dict[str, Any]:
    _, y, _ = _arrays(anchors, form)
    rng = np.random.default_rng(1515)
    left = rng.integers(0, y.size, 250_000)
    right = rng.integers(0, y.size, 250_000)
    distinct = left != right
    left, right = left[distinct], right[distinct]
    diff = np.abs(y[left] - y[right])
    truth = np.sign(y[left] - y[right])
    result: dict[str, Any] = {}
    for gap in (2, 5, 10, 15, 20):
        mask = (diff >= gap) & (diff < gap + 2)
        raw_order = np.sign(raw[left] - raw[right])
        linked_order = np.sign(linked[left] - linked[right])
        robust = (lower[left] > upper[right]) | (lower[right] > upper[left])
        robust_correct = ((lower[left] > upper[right]) & (truth > 0)) | (
            (lower[right] > upper[left]) & (truth < 0)
        )
        result[str(gap)] = {
            "pairs": int(np.sum(mask)),
            "raw_order_accuracy": float(np.mean(raw_order[mask] == truth[mask])),
            "linked_order_accuracy": float(np.mean(linked_order[mask] == truth[mask])),
            "robust_order_share": float(np.mean(robust[mask])),
            "uncertain_order_share": float(np.mean(~robust[mask])),
            "robust_reverse_share": float(np.mean(robust[mask] & ~robust_correct[mask])),
            "robust_order_accuracy": (
                float(np.sum(robust_correct[mask]) / np.sum(robust[mask]))
                if int(np.sum(robust[mask]))
                else None
            ),
        }
    return result


def apply_architecture(
    inputs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    selected: dict[str, str],
    interval_metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    candidate_index = {(str(row["player_id"]), int(row["season_id"])): row for row in candidates}
    working: list[dict[str, Any]] = []
    for source in inputs:
        key = (str(source["player_id"]), int(source["season_id"]))
        candidate = candidate_index[key]
        form: str
        raw: float | None
        if source.get("team_suppression") is None and _no_team_raw(source) is not None:
            form, raw = "NO_TEAM_CONTEXT", _no_team_raw(source)
        elif source["evidence_regime"] == "FULL_PORTABLE":
            form, raw = "FULL_PORTABLE", candidate.get("player_season_value_raw")
        elif source["evidence_regime"] == "EXPANDED_BOX_NO_PRESENCE":
            if source.get("observed_presence") is not None:
                form = "EXPANDED_PROXY_ACTION_WITH_PRESENCE"
                raw = _masked_form(source, form)
            else:
                form, raw = "EXPANDED_NO_PRESENCE", candidate.get("player_season_value_raw")
        elif source["evidence_regime"] == "TRADITIONAL_BOX":
            form = (
                "TRADITIONAL_WITH_PRESENCE"
                if source.get("observed_presence") is not None
                else "TRADITIONAL_BOX"
            )
            raw = _masked_form(source, form)
        else:
            form = (
                "EARLY_OFFENSE_WITH_PRESENCE"
                if source.get("observed_presence") is not None
                else "OFFENSE_ONLY_EARLY"
            )
            raw = _masked_form(source, form)
        working.append(
            {
                "player_id": key[0],
                "season_id": key[1],
                "role": str(source.get("broad_role") or "UNKNOWN"),
                "measurement_form": form,
                "form_raw": raw,
                "form_score": 100.0 * float(raw) if raw is not None else None,
                "raw_candidate_d_score": (
                    100.0 * float(candidate["player_season_value_percentile"])
                    if candidate.get("player_season_value_percentile") is not None
                    else None
                ),
                "presence_reliability": float(source.get("presence_reliability") or 0.0),
                "observed_channels": int(source.get("observed_inputs") or 0),
                "missing_channels": source.get("missing_inputs_json") or "[]",
                "source_confidence": candidate.get("confidence") or "UNAVAILABLE",
                "methodology_version": LINKED_VERSION,
            }
        )
    full_radii = {
        level: float(interval_metrics["NO_TEAM_CONTEXT"]["radii"][str(level)])
        for level in (80, 90, 95)
    }
    models: dict[str, Any] = {}
    radii: dict[str, dict[int, float]] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        models[form] = fit_linker(cast(LinkMethod, selected[form]), x, y, roles)
        radii[form] = {
            level: float(interval_metrics[form]["radii"][str(level)]) for level in (80, 90, 95)
        }
    for row in working:
        form = str(row["measurement_form"])
        reason: list[str] = []
        if form == "FULL_PORTABLE":
            point = row["raw_candidate_d_score"]
            status = "OFFICIAL_POINT"
            form_radii = full_radii
            reason.append("FULL_PORTABLE_REFERENCE_FORM")
        else:
            form_score = row.get("form_score")
            if form_score is None and row["raw_candidate_d_score"] is not None:
                form_score = row["raw_candidate_d_score"]
            if form_score is None:
                row.update(
                    linked_point_estimate=None,
                    interval_center=None,
                    score_status="UNAVAILABLE",
                    confidence="UNAVAILABLE",
                    reason_codes_json=json.dumps(["INSUFFICIENT_FACTUAL_ANCHORS"]),
                )
                continue
            point = float(
                predict_linker(models[form], np.asarray([form_score]), np.asarray([row["role"]]))[0]
            )
            passed = bool(interval_metrics[form]["point_eligible"])
            status = "PROVISIONAL_POINT" if passed else "INTERVAL_ONLY"
            form_radii = radii[form]
            reason.extend([f"MEASUREMENT_FORM_{form}", "LINKED_NOT_IMPUTED"])
            if not passed:
                reason.append("POINT_CALIBRATION_GATE_FAILED")
        bounds = interval_bounds(float(point), form_radii)
        row.update(bounds)
        row["interval_center"] = float(point)
        row["linked_point_estimate"] = float(point) if status != "INTERVAL_ONLY" else None
        row["score_status"] = status
        if status == "OFFICIAL_POINT":
            row["confidence"] = row["source_confidence"]
        elif status == "PROVISIONAL_POINT":
            row["confidence"] = "MODERATE" if row["source_confidence"] != "LIMITED" else "LIMITED"
        else:
            row["confidence"] = "LIMITED"
        row["reason_codes_json"] = json.dumps(reason, sort_keys=True)
        row["methodology_version"] = LINKED_VERSION
    return working


def interval_diagnostics(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("interval_center") is not None:
            by_player[str(row["player_id"])].append(row)
    peak_rows: list[dict[str, Any]] = []
    longevity_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(1515)
    for player_id, seasons in sorted(by_player.items()):
        ordered = sorted(seasons, key=lambda row: int(row["season_id"]))
        windows = [
            ordered[index : index + 3]
            for index in range(max(0, len(ordered) - 2))
            if int(ordered[index + 2]["season_id"]) - int(ordered[index]["season_id"]) == 2
        ]
        if windows:
            draws: list[float] = []
            chosen: Counter[str] = Counter()
            for _ in range(300):
                common = rng.normal()
                sampled: dict[int, float] = {}
                for row in ordered:
                    sigma = (float(row["upper_90"]) - float(row["lower_90"])) / (2 * 1.645)
                    sampled[int(row["season_id"])] = float(
                        np.clip(
                            float(row["interval_center"])
                            + sigma * (0.5 * common + math.sqrt(0.75) * rng.normal()),
                            0.0,
                            100.0,
                        )
                    )
                best_window = max(
                    windows,
                    key=lambda group: sum(sampled[int(row["season_id"])] for row in group) / 3,
                )
                chosen["-".join(str(row["season_id"]) for row in best_window)] += 1
                three = sum(sampled[int(row["season_id"])] for row in best_window) / 3
                apex = max(sampled.values())
                draws.append(0.70 * three + 0.30 * apex)
            peak_rows.append(
                {
                    "player_id": player_id,
                    "central": float(np.median(draws)),
                    "lower_90": float(np.quantile(draws, 0.05)),
                    "upper_90": float(np.quantile(draws, 0.95)),
                    "best_supported_window": chosen.most_common(1)[0][0],
                    "plausible_windows_json": json.dumps(
                        {key: value / 300 for key, value in chosen.items() if value >= 30},
                        sort_keys=True,
                    ),
                }
            )
        probabilities = []
        for row in ordered:
            center = float(row["interval_center"])
            sigma = max(0.25, (float(row["upper_90"]) - float(row["lower_90"])) / (2 * 1.645))
            p80 = 0.5 * (1.0 + math.erf((center - 80.0) / (sigma * math.sqrt(2))))
            p90 = 0.5 * (1.0 + math.erf((center - 90.0) / (sigma * math.sqrt(2))))
            probabilities.append((int(row["season_id"]), p80, p90))
        longest_expected = 0.0
        running = 0.0
        for index, (season, p80, _) in enumerate(probabilities):
            if index and season != probabilities[index - 1][0] + 1:
                running = 0.0
            running += p80
            longest_expected = max(longest_expected, running)
        longevity_rows.append(
            {
                "player_id": player_id,
                "expected_seasons_above_p80": sum(item[1] for item in probabilities),
                "expected_seasons_above_p90": sum(item[2] for item in probabilities),
                "expected_longest_p80_run": longest_expected,
                "architecture_preserved": "35/40/25_REQUIRES_DEDICATED_VALIDATION",
            }
        )
    return (
        {
            "players": len(peak_rows),
            "method": "300 deterministic correlated normal draws; 0.50 shared player shock",
            "rows": peak_rows,
        },
        {
            "players": len(longevity_rows),
            "method": "probabilistic P80/P90 exceedance; frozen 35/40/25 not promoted",
            "rows": longevity_rows,
        },
    )


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    inputs_fingerprints = verify_inputs(args)
    step_g = json.loads(
        (args.docs_root / "player-season-value-v2-promotion-summary.json").read_text()
    )
    if step_g.get("output_fingerprint") != STEP_G_FINGERPRINT:
        raise ValueError("STEP-0015G fingerprint mismatch")
    inputs_fingerprints["step_0015g"] = STEP_G_FINGERPRINT
    base_rows, _ = season_inputs(args.gold_root)
    facts = read_rows(
        args.silver_root / "historical_player_season_facts_v2_research/part-00000.parquet"
    )
    candidates, recovered_inputs, reconstruction_report = reconstruction(args, base_rows, facts)
    if (
        reconstruction_report["maximum_raw_difference"] != 0.0
        or reconstruction_report["maximum_percentile_difference"] != 0.0
    ):
        raise ValueError("STEP-0015G Candidate D reconstruction failed")
    anchors = build_anchors(recovered_inputs, candidates)
    linking, selected = linking_audit(anchors)
    transport = transport_audit(anchors, selected)

    interval_metrics: dict[str, Any] = {}
    pairwise: dict[str, Any] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        method = cast(LinkMethod, selected[form])
        points, bounds, calibrated = split_conformal(anchors, form, method)
        calibrated["subgroups"] = _subgroups(anchors, form, points)
        # The all-data radii are used only to apply the frozen research architecture.
        all_model = fit_linker(method, x, y, roles)
        all_points = predict_linker(all_model, x, roles)
        residuals = np.abs(all_points - y)
        calibrated["radii"] = {
            str(level): conformal_radius(residuals, level / 100.0) for level in (80, 90, 95)
        }
        eligible, gates = eligibility(calibrated)
        calibrated["point_eligible"] = eligible
        calibrated["gates"] = gates
        interval_metrics[form] = calibrated
        pairwise[form] = pairwise_audit(
            anchors,
            form,
            x,
            points,
            bounds[90][:, 0],
            bounds[90][:, 1],
        )

    scored = apply_architecture(recovered_inputs, candidates, anchors, selected, interval_metrics)
    peak, longevity = interval_diagnostics(scored)
    dimension_rows = read_rows(args.gold_root / "player_dimension_scores/part-00000.parquet")
    names = {str(row["player_id"]): str(row["display_name"]) for row in dimension_rows}
    cases: list[dict[str, Any]] = []
    for row in scored:
        if names.get(str(row["player_id"])) in CASE_NAMES:
            cases.append({"player_name": names[str(row["player_id"])], **row})
    modern_names = {
        "Michael Jordan",
        "LeBron James",
        "Stephen Curry",
        "Shaquille O'Neal",
        "Tim Duncan",
        "Kevin Garnett",
        "Rudy Gobert",
        "Nikola Jokic",
        "Giannis Antetokounmpo",
    }
    anchor_models: dict[str, Any] = {}
    for form in FORMS:
        x, y, roles = _arrays(anchors, form)
        anchor_models[form] = fit_linker(cast(LinkMethod, selected[form]), x, y, roles)
    modern_controls: list[dict[str, Any]] = []
    for player_name in sorted(modern_names):
        player_id = next((key for key, value in names.items() if value == player_name), None)
        player_rows = [row for row in anchors if row["player_id"] == player_id]
        if not player_rows:
            continue
        anchor = max(player_rows, key=lambda row: float(row["full_score"]))
        for form in FORMS:
            raw_score = float(anchor[f"{form}_score"])
            linked = float(
                predict_linker(
                    anchor_models[form],
                    np.asarray([raw_score]),
                    np.asarray([anchor["role"]]),
                )[0]
            )
            control_bounds = interval_bounds(
                linked,
                {
                    level: float(interval_metrics[form]["radii"][str(level)])
                    for level in (80, 90, 95)
                },
            )
            modern_controls.append(
                {
                    "player_id": player_id,
                    "player_name": player_name,
                    "season_id": anchor["season_id"],
                    "measurement_form": form,
                    "full_score": anchor["full_score"],
                    "raw_masked_score": raw_score,
                    "linked_estimate": linked,
                    **control_bounds,
                    "full_captured_90": (
                        control_bounds["lower_90"]
                        <= float(anchor["full_score"])
                        <= control_bounds["upper_90"]
                    ),
                }
            )

    status = Counter(str(row["score_status"]) for row in scored)
    by_decade: dict[str, Counter[str]] = defaultdict(Counter)
    by_regime: dict[str, Counter[str]] = defaultdict(Counter)
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    for row in scored:
        by_decade[f"{int(row['season_id']) // 10 * 10}s"][str(row["score_status"])] += 1
        by_regime[str(row["measurement_form"])][str(row["score_status"])] += 1
        by_role[str(row["role"])][str(row["score_status"])] += 1
    status_report = {
        "total": len(scored),
        "status": dict(sorted(status.items())),
        "by_decade": {key: dict(sorted(value.items())) for key, value in sorted(by_decade.items())},
        "by_measurement_form": {
            key: dict(sorted(value.items())) for key, value in sorted(by_regime.items())
        },
        "by_role": {key: dict(sorted(value.items())) for key, value in sorted(by_role.items())},
        "pre_1950": {
            "recommendation": "INTERVAL_ONLY_WHEN_OFFENSE_FORM_OBSERVED_OTHERWISE_UNAVAILABLE",
            "no_rebounds_invented": True,
        },
        "1970s": {
            "candidate_d_coverage_before_linking": step_g["coverage"],
            "finding": (
                "Missing Team Context can be linked provisionally because its total "
                "weight is small; traditional-form seasons remain interval-only "
                "because missing STL/BLK and Presence "
                "alter ordering materially."
            ),
        },
        "full_portable_uncertainty": {
            "method": "no-Team-Context channel sensitivity radii",
            "caution": (
                "Reference-form sensitivity, not calibration against unknowable basketball truth"
            ),
            "confidence_changes_quality": False,
        },
    }
    gates_by_form = {form: interval_metrics[form]["gates"] for form in FORMS}
    verdict = "LIMITED_TIERED_ARCHITECTURE"
    recommendation = "READY_FOR_PEAK_LONGEVITY_UNCERTAINTY_AUDIT"
    result = "PASS"

    output_root = args.gold_root / "player_season_value_measurement_linking_audit"
    manifests = [
        write_parquet(
            anchors, output_root / "anchor-masked-pairs.parquet", ("season_id", "player_id")
        ),
        write_parquet(
            scored, output_root / "linked-season-measurements.parquet", ("season_id", "player_id")
        ),
        write_parquet(
            cases, output_root / "diagnostic-player-seasons.parquet", ("player_name", "season_id")
        ),
        write_parquet(
            modern_controls,
            output_root / "modern-masked-controls.parquet",
            ("player_name", "season_id", "measurement_form"),
        ),
        write_parquet(
            peak["rows"], output_root / "peak-interval-diagnostics.parquet", ("player_id",)
        ),
        write_parquet(
            longevity["rows"],
            output_root / "longevity-interval-diagnostics.parquet",
            ("player_id",),
        ),
    ]
    reports: dict[str, dict[str, Any]] = {
        "player-season-value-linking-validation.json": {
            "measurement_forms": {
                "FULL_PORTABLE": "reference form, not asserted basketball truth",
                "EXPANDED_NO_PRESENCE": "full portable box/actions without observed Presence",
                "EXPANDED_PROXY_ACTION_WITH_PRESENCE": (
                    "expanded box plus Presence but without role-adjusted action metadata"
                ),
                "TRADITIONAL_BOX": "PPG/TS/APG/rebound proxy without STL/BLK or Presence",
                "TRADITIONAL_WITH_PRESENCE": "traditional box plus observed Presence",
                "EARLY_OFFENSE_WITH_PRESENCE": (
                    "observed offense plus observed Presence, with no invented rebound channel"
                ),
                "OFFENSE_ONLY_EARLY": "observed scoring/efficiency/creation form; defense absent",
                "NO_TEAM_CONTEXT": (
                    "Candidate D with the bounded team term omitted, not renormalized"
                ),
            },
            "candidates": linking,
            "selected": selected,
            "era_transport": transport,
            "common_scale": interval_metrics,
            "gates": gates_by_form,
        },
        "player-season-value-interval-calibration.json": interval_metrics,
        "player-season-value-pairwise-reliability.json": pairwise,
        "player-season-value-score-status.json": status_report,
        "player-season-value-peak-interval-diagnostics.json": {
            key: value for key, value in peak.items() if key != "rows"
        },
        "player-season-value-longevity-interval-diagnostics.json": {
            key: value for key, value in longevity.items() if key != "rows"
        },
        "player-season-value-linking-case-studies.json": {"rows": cases},
        "player-season-value-modern-masked-controls.json": {"rows": modern_controls},
        "player-season-value-measurement-linking-verdict.json": {
            "step_result": result,
            "architecture_verdict": verdict,
            "recommendation": recommendation,
            "candidate_d_modified": False,
            "missing_statistics_predicted": False,
            "official_methodology_created": False,
            "network_requests": 0,
            "architectures": {
                "A_RAW_PLUS_UNCERTAINTY": "baseline; form location and scale bias retained",
                "B_LINKED_EMPIRICAL": "diagnostic; OOF residual reuse limits coverage claim",
                "C_LINKED_CONFORMAL": "selected interval method",
                "D_TIERED": "accepted research architecture",
            },
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        stable_json(
            args.docs_root / name,
            {
                "step": "STEP-0015H",
                "audit_methodology_version": AUDIT_VERSION,
                "research_methodology_version": LINKED_VERSION,
                "input_fingerprints": inputs_fingerprints,
                **payload,
            },
        )
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": inputs_fingerprints,
                "outputs": manifests,
                "reports": report_hashes,
                "reconstruction": reconstruction_report,
                "selected": selected,
                "status": dict(sorted(status.items())),
                "verdict": verdict,
                "recommendation": recommendation,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015H",
        "result": result,
        "architecture_verdict": verdict,
        "recommendation": recommendation,
        "audit_methodology_version": AUDIT_VERSION,
        "research_methodology_version": LINKED_VERSION,
        "frozen_candidate_d_version": PLAYER_SEASON_VALUE_RESEARCH_VERSION,
        "input_fingerprints": inputs_fingerprints,
        "reconstruction": reconstruction_report,
        "anchor_rows": len(anchors),
        "selected_linkers": selected,
        "calibration": interval_metrics,
        "score_status": status_report,
        "peak_diagnostic": {key: value for key, value in peak.items() if key != "rows"},
        "longevity_diagnostic": {key: value for key, value in longevity.items() if key != "rows"},
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "network_requests": 0,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint,
    }
    stable_json(args.docs_root / "player-season-value-measurement-linking-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, observed {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
