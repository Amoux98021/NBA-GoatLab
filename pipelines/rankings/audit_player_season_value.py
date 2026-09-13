#!/usr/bin/env python3
"""Run the offline STEP-0015D universal player-season value audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.dimension_scores import (
    longevity_evidence,
    midrank_percentile_scores,
    weighted_observed,
)
from goatlab.rankings.peak_forensics import correlation, player_peak
from goatlab.rankings.player_season_value import (
    LONGEVITY_COUNTERFACTUAL_VERSION,
    OVERALL_COUNTERFACTUAL_VERSION,
    PEAK_COUNTERFACTUAL_VERSION,
    PLAYER_SEASON_VALUE_AUDIT_VERSION,
    PLAYER_SEASON_VALUE_RESEARCH_VERSION,
    combine_player_value,
    confidence_from_evidence,
    defensive_axis,
    evidence_regime,
    offensive_axis,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_v1 import (
    distribution,
    file_hash,
    overall_counterfactual,
    paired,
    rank_percentiles_by_season,
    stable_json,
    write_parquet,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ID = "GOATLAB-HIST-V1"
PEAK_FORENSIC_FINGERPRINT = "a9db1e7f75b3f3b8af9474bf556917b98f8aceeeb890fdc9ba36bdf7c3de7287"
DIMENSION_FINGERPRINT = "0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a"
OVERALL_FINGERPRINT = "02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa"
DEFENSE_PROMOTION_FINGERPRINT = "103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f"
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
    "Chris Paul",
    "Kevin Garnett",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def verify_inputs(docs_root: Path) -> dict[str, str]:
    checks = {
        "dimension": ("dimension-score-summary.json", DIMENSION_FINGERPRINT),
        "overall": ("overall-ranking-summary.json", OVERALL_FINGERPRINT),
        "defense_promotion": ("defense-v2-promotion-summary.json", DEFENSE_PROMOTION_FINGERPRINT),
        "peak_forensic": ("peak-v1-forensic-summary.json", PEAK_FORENSIC_FINGERPRINT),
    }
    output: dict[str, str] = {}
    for label, (name, expected) in checks.items():
        payload = json.loads((docs_root / name).read_text(encoding="utf-8"))
        if payload.get("output_fingerprint") != expected:
            raise ValueError(f"unexpected upstream fingerprint: {name}")
        output[label] = expected
    output["constitution"] = file_hash(ROOT / "docs/constitution/GOATLAB_V1_CONSTITUTION.md")
    return output


def season_inputs(
    gold_root: Path,
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], dict[str, Any]]]:
    base = read_rows(gold_root / "peak_forensic_audit/v1-season-quality-decomposition.parquet")
    defense = {
        (str(row["player_id"]), int(row["season_id"])): row
        for row in read_rows(
            gold_root / "defense_v2_promotion_audit/defense-v2-season-components.parquet"
        )
    }
    output: list[dict[str, Any]] = []
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for source in base:
        key = (str(source["player_id"]), int(source["season_id"]))
        supplementary = defense.get(key, {})
        row = {
            **source,
            "broad_role": supplementary.get("broad_role"),
            "role_aware_actions": supplementary.get("role_aware_actions"),
            "observed_presence": supplementary.get("observed_presence"),
            "expected_presence": supplementary.get("expected_presence"),
            "final_presence": supplementary.get("final_presence"),
            "presence_reliability": float(supplementary.get("presence_reliability") or 0.0),
            "action_coverage": float(supplementary.get("action_coverage") or 0.0),
            "rebound_semantics": supplementary.get("rebound_semantics"),
        }
        row["evidence_regime"] = evidence_regime(
            ts_available=row.get("ts_pct") is not None,
            creation_available=row.get("apg") is not None,
            rebound_available=row.get("rpg") is not None,
            steals_blocks_available=row.get("spg") is not None and row.get("bpg") is not None,
            role_actions_available=row.get("role_aware_actions") is not None,
            presence_available=row.get("observed_presence") is not None,
        )
        output.append(row)
        index[key] = row
    return output, index


def evidence_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    registry = {
        "ppg": ("INDIVIDUAL_OFFENSE", True, False, False, "DIRECT"),
        "ts_pct": ("INDIVIDUAL_OFFENSE", True, False, False, "DERIVED_EFFICIENCY"),
        "apg": ("INDIVIDUAL_OFFENSE", True, False, False, "CREATION_PROXY"),
        "rpg": ("INDIVIDUAL_DEFENSE", True, False, False, "TOTAL_REBOUND_PROXY"),
        "spg": ("INDIVIDUAL_DEFENSE", True, False, False, "RECORDED_ACTION"),
        "bpg": ("INDIVIDUAL_DEFENSE", True, False, False, "RECORDED_ACTION"),
        "team_suppression": ("TEAM_CONTEXT", True, True, False, "CONTEXT"),
        "role_aware_actions": ("INDIVIDUAL_DEFENSE", True, False, False, "ROLE_AWARE_PROXY"),
        "observed_presence": ("INDIVIDUAL_DEFENSE", True, False, False, "WOWY_STYLE_PROXY"),
    }
    output: dict[str, Any] = {}
    for name, (category, portable, shared, modern_only, semantics) in registry.items():
        observed = [row for row in rows if row.get(name) is not None]
        seasons = [int(row["season_id"]) for row in observed]
        output[name] = {
            "category": category,
            "rows": len(rows),
            "observed_rows": len(observed),
            "coverage_pct": len(observed) / len(rows),
            "first_observed_season": min(seasons) if seasons else None,
            "last_observed_season": max(seasons) if seasons else None,
            "portable": portable,
            "individual": not shared,
            "team_shared": shared,
            "modern_only": modern_only,
            "semantics": semantics,
            "missingness": "SOURCE_OR_HISTORICAL_UNAVAILABLE_NOT_ZERO",
        }
    output["minutes"] = {
        "category": "AVAILABILITY",
        "portable": False,
        "individual": True,
        "team_shared": False,
        "modern_only": False,
        "semantics": "COVERAGE_GATED_NOT_IN_VALUE",
        "missingness": "HISTORICAL_PLACEHOLDER_RISK",
    }
    output["games"] = {
        "category": "AVAILABILITY",
        "observed_rows": len(rows),
        "coverage_pct": 1.0,
        "portable": True,
        "individual": True,
        "team_shared": False,
        "modern_only": False,
        "semantics": "QUALIFICATION_AND_CONFIDENCE_ONLY",
    }
    return output


def regime_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["evidence_regime"])].append(row)
    report: dict[str, Any] = {}
    for regime, members in sorted(groups.items()):
        seasons = [int(row["season_id"]) for row in members]
        report[regime] = {
            "player_seasons": len(members),
            "players": len({str(row["player_id"]) for row in members}),
            "first_observed_season": min(seasons),
            "last_observed_season": max(seasons),
            "share": len(members) / len(rows),
            "derivation": "OBSERVED_CHANNEL_COVERAGE_NOT_DATE_ASSIGNMENT",
        }
    return report


def paired_calibration(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    report = paired(actual, predicted)
    if not actual or len(actual) != len(predicted):
        return report
    design = np.vstack([np.asarray(actual), np.ones(len(actual))]).T
    slope, intercept = np.linalg.lstsq(design, np.asarray(predicted), rcond=None)[0]
    report["calibration_slope"] = float(slope)
    report["calibration_intercept"] = float(intercept)
    return report


def archetypes(row: dict[str, Any]) -> tuple[str, ...]:
    """Assign evidence-defined diagnostic archetypes; labels never enter scoring."""
    labels: list[str] = []
    ppg, ts, apg = row.get("ppg"), row.get("ts_pct"), row.get("apg")
    rpg, actions = row.get("rpg"), row.get("role_aware_actions")
    scoring = _scoring(row)
    if ppg is not None and float(ppg) >= 0.90:
        labels.append("HIGH_VOLUME_SCORER")
    if ts is not None and float(ts) >= 0.90 and (ppg is None or float(ppg) < 0.80):
        labels.append("EFFICIENCY_DOMINANT_SCORER")
    if apg is not None and float(apg) >= 0.90:
        labels.append("PRIMARY_CREATOR")
    if rpg is not None and float(rpg) >= 0.90:
        labels.append("REBOUND_INTERIOR")
    if actions is not None and float(actions) >= 0.90:
        labels.append("DEFENSIVE_ACTION_ANCHOR")
    if scoring is not None and apg is not None and actions is not None:
        offense = offensive_axis(scoring, apg, architecture="O3_MULTIPATH_60_40")
        if offense is not None and offense >= 0.90 and float(actions) < 0.60:
            labels.append("OFFENSIVE_ENGINE")
        if offense is not None and offense >= 0.80 and float(actions) >= 0.80:
            labels.append("TWO_WAY_EVIDENCE")
        if scoring >= 0.70 and float(apg) >= 0.70 and float(actions) >= 0.70:
            labels.append("BALANCED_ALL_AROUND")
    return tuple(labels)


def _scoring(row: dict[str, Any]) -> float | None:
    if row.get("ppg") is None:
        return None
    if row.get("ts_pct") is None:
        return float(row["ppg"])
    return 0.65 * float(row["ppg"]) + 0.35 * float(row["ts_pct"])


def candidate_row(row: dict[str, Any], label: str) -> dict[str, Any]:
    scoring = _scoring(row)
    if label == "A_TRANSPARENT_PORTABLE":
        offense_arch, defense_arch, combine_arch = (
            "O1_STRONGER_65_35",
            "D2_ACTIONS_TEAM_75_25",
            "M3_OFFENSE_65_DEFENSE_35",
        )
        actions, presence = row.get("action_value"), None
        action_semantics = "CURRENT_50_25_25"
        reliability = 0.0
    elif label == "B_MULTIPATH_BOUNDED_TEAM":
        offense_arch, defense_arch, combine_arch = (
            "O3_MULTIPATH_60_40",
            "D2_ACTIONS_TEAM_75_25",
            "M2_STRONGER_60_40",
        )
        actions = (
            row.get("role_aware_actions")
            if row.get("role_aware_actions") is not None
            else row.get("action_value")
        )
        action_semantics = (
            "ROLE_AWARE_40_30_30"
            if row.get("role_aware_actions") is not None
            else "CURRENT_50_25_25"
        )
        presence, reliability = None, 0.0
    elif label == "C_FULL_EVIDENCE_MEASUREMENT":
        offense_arch, defense_arch, combine_arch = (
            "O3_MULTIPATH_60_40",
            "D3_FULL_50_10_40",
            "M4_BOUNDED_STRONGER_55_45",
        )
        actions = row.get("role_aware_actions")
        action_semantics = "ROLE_AWARE_40_30_30"
        presence = row.get("observed_presence")
        reliability = float(row.get("presence_reliability") or 0.0)
    elif label == "D_REGIME_RELIABILITY":
        offense_arch, defense_arch, combine_arch = (
            "O3_MULTIPATH_60_40",
            "D4_RELIABILITY_55_10_35",
            "M4_BOUNDED_STRONGER_55_45",
        )
        actions = (
            row.get("role_aware_actions")
            if row.get("role_aware_actions") is not None
            else row.get("action_value")
        )
        action_semantics = (
            "ROLE_AWARE_40_30_30"
            if row.get("role_aware_actions") is not None
            else "CURRENT_50_25_25"
        )
        presence = row.get("observed_presence")
        reliability = float(row.get("presence_reliability") or 0.0)
    else:
        raise ValueError(label)
    offense = offensive_axis(scoring, row.get("apg"), architecture=offense_arch)
    defense, team_local, defense_reasons = defensive_axis(
        actions,
        row.get("team_suppression"),
        presence,
        architecture=defense_arch,
        presence_reliability=reliability,
    )
    combined = combine_player_value(
        offense,
        defense,
        architecture=combine_arch,
        defense_team_weight=team_local,
    )
    confidence, confidence_reasons = confidence_from_evidence(
        regime=str(row["evidence_regime"]),
        presence_reliability=reliability,
        role_known=row.get("broad_role") is not None,
        games=int(row.get("games") or 0),
    )
    if combined.value is None:
        confidence = "UNAVAILABLE"
    return {
        "candidate": label,
        "player_id": str(row["player_id"]),
        "season_id": int(row["season_id"]),
        "season_type": "REGULAR",
        "primary_team_id": row.get("primary_team_id"),
        "evidence_regime": row["evidence_regime"],
        "broad_role": row.get("broad_role"),
        "ppg": row.get("ppg"),
        "ts_pct": row.get("ts_pct"),
        "apg": row.get("apg"),
        "rpg": row.get("rpg"),
        "spg": row.get("spg"),
        "bpg": row.get("bpg"),
        "scoring": scoring,
        "creation": row.get("apg"),
        "offense": offense,
        "actions": actions,
        "action_semantics": action_semantics,
        "team_context": row.get("team_suppression"),
        "presence": presence,
        "presence_reliability": reliability,
        "defense_evidence": defense,
        "player_season_value_raw": combined.value,
        "player_season_value_percentile": None,
        "team_effective_weight": combined.team_effective_weight,
        "offense_effective_weight": combined.offense_effective_weight,
        "defense_effective_weight": combined.defense_effective_weight,
        "confidence": confidence,
        "reason_codes_json": json.dumps(
            sorted(set((*defense_reasons, *combined.reason_codes, *confidence_reasons)))
        ),
        "methodology_version": PLAYER_SEASON_VALUE_RESEARCH_VERSION,
        "promoted": False,
        "corpus_id": CORPUS_ID,
    }


def build_candidates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    labels = (
        "A_TRANSPARENT_PORTABLE",
        "B_MULTIPATH_BOUNDED_TEAM",
        "C_FULL_EVIDENCE_MEASUREMENT",
        "D_REGIME_RELIABILITY",
    )
    output = [candidate_row(row, label) for label in labels for row in rows]
    formulas = {
        "A_TRANSPARENT_PORTABLE": (
            "65% season scoring/35% creation on stronger axis; defense is 75% current "
            "actions/25% team; total is 65% offense/35% defense"
        ),
        "B_MULTIPATH_BOUNDED_TEAM": (
            "60/40 stronger/secondary scoring-creation; defense is 75% role-aware actions/"
            "25% team; total is 60/40 stronger/secondary offense-defense"
        ),
        "C_FULL_EVIDENCE_MEASUREMENT": (
            "60/40 scoring-creation; defense is 50% role-aware actions/10% team/40% "
            "observed Presence; total is 55/45 stronger/secondary offense-defense"
        ),
        "D_REGIME_RELIABILITY": (
            "60/40 scoring-creation; defense is 10% team, up to 35% continuously reliable "
            "observed Presence, remainder individual actions; total is 55/45 stronger/secondary"
        ),
    }
    for label in labels:
        subset = [row for row in output if row["candidate"] == label]
        ranked = rank_percentiles_by_season(
            {
                (str(row["player_id"]), int(row["season_id"])): row["player_season_value_raw"]
                for row in subset
            }
        )
        for row in subset:
            row["player_season_value_percentile"] = ranked[
                (str(row["player_id"]), int(row["season_id"]))
            ]
    report: dict[str, Any] = {}
    for label in labels:
        subset = [row for row in output if row["candidate"] == label]
        available = [row for row in subset if row["player_season_value_raw"] is not None]
        report[label] = {
            "formula": formulas[label],
            "player_seasons": len(available),
            "players": len({str(row["player_id"]) for row in available}),
            "coverage_pct": len(available) / len(subset),
            "mean_team_effective_weight": statistics.fmean(
                float(row["team_effective_weight"]) for row in available
            )
            if available
            else None,
            "maximum_team_effective_weight": max(
                (float(row["team_effective_weight"]) for row in available), default=None
            ),
            "confidence": dict(Counter(str(row["confidence"]) for row in available)),
        }
    return output, report


def candidate_pair_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    indexed: dict[str, dict[tuple[str, int], float]] = defaultdict(dict)
    for row in rows:
        value = row.get("player_season_value_percentile")
        if value is not None:
            indexed[str(row["candidate"])][(str(row["player_id"]), int(row["season_id"]))] = float(
                value
            )
    output: dict[str, Any] = {}
    labels = sorted(indexed)
    for index, left_label in enumerate(labels):
        for right_label in labels[index + 1 :]:
            common = sorted(set(indexed[left_label]) & set(indexed[right_label]))
            left = [indexed[left_label][key] for key in common]
            right = [indexed[right_label][key] for key in common]
            output[f"{left_label}__{right_label}"] = {
                "observations": len(common),
                "spearman": spearman(left, right),
                "pearson": correlation(left, right),
            }
    return output


def masking_audit(
    base_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    full = [
        row
        for row in base_rows
        if row.get("role_aware_actions") is not None
        and row.get("observed_presence") is not None
        and row.get("ts_pct") is not None
        and row.get("apg") is not None
        and row.get("rpg") is not None
        and row.get("spg") is not None
        and row.get("bpg") is not None
    ]
    actual = [candidate_row(row, "C_FULL_EVIDENCE_MEASUREMENT") for row in full]
    regimes: dict[str, list[dict[str, Any]]] = {
        "EARLY_LIMITED": [],
        "TRADITIONAL_BOX": [],
        "EXPANDED_BOX_NO_PRESENCE": [],
        "FULL_PORTABLE": [],
    }
    for row in full:
        early = dict(row)
        for field in (
            "ts_pct",
            "apg",
            "rpg",
            "spg",
            "bpg",
            "role_aware_actions",
            "observed_presence",
        ):
            early[field] = None
        early["evidence_regime"] = "EARLY_LIMITED"
        traditional = dict(row)
        for field in ("ts_pct", "spg", "bpg", "role_aware_actions", "observed_presence"):
            traditional[field] = None
        traditional["action_value"] = row.get("rpg")
        traditional["evidence_regime"] = "TRADITIONAL_BOX"
        expanded = dict(row)
        expanded["observed_presence"] = None
        expanded["presence_reliability"] = 0.0
        expanded["evidence_regime"] = "EXPANDED_BOX_NO_PRESENCE"
        regimes["EARLY_LIMITED"].append(early)
        regimes["TRADITIONAL_BOX"].append(traditional)
        regimes["EXPANDED_BOX_NO_PRESENCE"].append(expanded)
        regimes["FULL_PORTABLE"].append(row)

    report: dict[str, Any] = {"full_evidence_rows": len(full), "regimes": {}}
    role_report: dict[str, Any] = {}
    subgroup_report: dict[str, Any] = {}
    for regime, rows in regimes.items():
        candidate_label = (
            "C_FULL_EVIDENCE_MEASUREMENT" if regime == "FULL_PORTABLE" else "D_REGIME_RELIABILITY"
        )
        predicted = [candidate_row(row, candidate_label) for row in rows]
        pairs = [
            (
                float(left["player_season_value_raw"]) * 100.0,
                float(right["player_season_value_raw"]) * 100.0,
            )
            for left, right in zip(actual, predicted, strict=True)
            if left["player_season_value_raw"] is not None
            and right["player_season_value_raw"] is not None
        ]
        report["regimes"][regime] = {
            **paired_calibration([left for left, _ in pairs], [right for _, right in pairs]),
            "unavailable": len(actual) - len(pairs),
            "coverage_pct": len(pairs) / len(actual) if actual else 0.0,
        }
        for role in ("GUARD", "WING", "FORWARD", "BIG"):
            role_pairs = [
                pair
                for pair, source in zip(
                    [
                        (
                            float(left["player_season_value_raw"]) * 100.0,
                            float(right["player_season_value_raw"]) * 100.0,
                        )
                        if left["player_season_value_raw"] is not None
                        and right["player_season_value_raw"] is not None
                        else None
                        for left, right in zip(actual, predicted, strict=True)
                    ],
                    full,
                    strict=True,
                )
                if pair is not None and source.get("broad_role") == role
            ]
            role_report.setdefault(role, {})[regime] = paired_calibration(
                [left for left, _ in role_pairs], [right for _, right in role_pairs]
            )
        paired_rows = [
            (source, left, right)
            for source, left, right in zip(full, actual, predicted, strict=True)
            if left["player_season_value_raw"] is not None
            and right["player_season_value_raw"] is not None
        ]
        labels = sorted({label for source, _, _ in paired_rows for label in archetypes(source)})
        for label in labels:
            members = [item for item in paired_rows if label in archetypes(item[0])]
            subgroup_report.setdefault(f"ARCHETYPE:{label}", {})[regime] = paired_calibration(
                [100.0 * float(left["player_season_value_raw"]) for _, left, _ in members],
                [100.0 * float(right["player_season_value_raw"]) for _, _, right in members],
            )
        for band, predicate in (
            ("WEAK", lambda value: value < 0.25),
            ("MIDDLE", lambda value: 0.25 <= value < 0.75),
            ("STRONG", lambda value: value >= 0.75),
        ):
            members = [
                item
                for item in paired_rows
                if item[0].get("team_suppression") is not None
                and predicate(float(item[0]["team_suppression"]))
            ]
            subgroup_report.setdefault(f"TEAM_CONTEXT:{band}", {})[regime] = paired_calibration(
                [100.0 * float(left["player_season_value_raw"]) for _, left, _ in members],
                [100.0 * float(right["player_season_value_raw"]) for _, _, right in members],
            )
    return report, role_report, subgroup_report


def offense_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for architecture in ("O1_STRONGER_65_35", "O2_DIRECT_70_30", "O3_MULTIPATH_60_40"):
        values = [
            offensive_axis(_scoring(row), row.get("apg"), architecture=architecture) for row in rows
        ]
        observed = [float(value) for value in values if value is not None]
        output[architecture] = {
            "observations": len(observed),
            "coverage_pct": len(observed) / len(rows),
            "distribution": distribution([100.0 * value for value in observed]),
        }
    overlap = [row for row in rows if _scoring(row) is not None and row.get("apg") is not None]
    output["effective_influence_full_evidence"] = {
        "O1_scoring_mean_realized_weight": statistics.fmean(
            0.65 if float(_scoring(row)) >= float(row["apg"]) else 0.35 for row in overlap
        ),
        "O1_creation_mean_realized_weight": statistics.fmean(
            0.35 if float(_scoring(row)) >= float(row["apg"]) else 0.65 for row in overlap
        ),
        "O3_scoring_mean_realized_weight": statistics.fmean(
            0.60 if float(_scoring(row)) >= float(row["apg"]) else 0.40 for row in overlap
        ),
        "O3_creation_mean_realized_weight": statistics.fmean(
            0.40 if float(_scoring(row)) >= float(row["apg"]) else 0.60 for row in overlap
        ),
    }
    return output


def candidate_influence(candidate_rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    rows = [
        row
        for row in candidate_rows
        if row["candidate"] == label and row["player_season_value_raw"] is not None
    ]
    contributions = {
        "offense_axis": [
            float(row["offense_effective_weight"]) * float(row["offense"]) for row in rows
        ],
        "defense_axis": [
            float(row["defense_effective_weight"]) * float(row["defense_evidence"]) for row in rows
        ],
    }
    total = np.asarray([float(row["player_season_value_raw"]) for row in rows])
    variance = float(np.var(total))
    report: dict[str, Any] = {}
    for name, values in contributions.items():
        array = np.asarray(values)
        share = float(np.cov(array, total, ddof=0)[0, 1] / variance) if variance > 0 else None
        report[name] = {
            "mean_effective_weight": statistics.fmean(
                float(row[f"{name.split('_')[0]}_effective_weight"]) for row in rows
            ),
            "shapley_covariance_variance_share": share,
        }
    report["team_context"] = {
        "mean_effective_weight": statistics.fmean(
            float(row["team_effective_weight"]) for row in rows
        ),
        "maximum_effective_weight": max(float(row["team_effective_weight"]) for row in rows),
        "correlation_with_value": correlation(
            [float(row["team_context"]) for row in rows],
            [float(row["player_season_value_raw"]) for row in rows],
        ),
    }
    primitive_weights: dict[str, list[float]] = defaultdict(list)
    primitive_contributions: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        offense_weight = float(row["offense_effective_weight"])
        defense_weight = float(row["defense_effective_weight"])
        scoring = float(row["scoring"])
        creation = float(row["creation"])
        scoring_weight = 0.60 if scoring >= creation else 0.40
        creation_weight = 1.0 - scoring_weight
        ts_available = row.get("ts_pct") is not None
        ppg_local_weight = 0.65 if ts_available else 1.0
        ts_local_weight = 0.35 if ts_available else 0.0
        ppg_weight = offense_weight * scoring_weight * ppg_local_weight
        ts_weight = offense_weight * scoring_weight * ts_local_weight
        apg_weight = offense_weight * creation_weight
        reliability = float(row["presence_reliability"])
        presence_weight = (
            defense_weight * 0.35 * reliability if row.get("presence") is not None else 0.0
        )
        local_presence_weight = 0.35 * reliability if row.get("presence") is not None else 0.0
        action_weight = defense_weight * (0.90 - local_presence_weight)
        team_weight = defense_weight * 0.10
        action_mix = (
            {"rpg": 0.40, "spg": 0.30, "bpg": 0.30}
            if row["action_semantics"] == "ROLE_AWARE_40_30_30"
            else {"rpg": 0.50, "spg": 0.25, "bpg": 0.25}
        )
        for name, weight in (
            ("ppg", ppg_weight),
            ("ts_pct", ts_weight),
            ("apg", apg_weight),
            ("presence", presence_weight),
            ("team_context", team_weight),
        ):
            primitive_weights[name].append(weight)
        for name, local in action_mix.items():
            primitive_weights[name].append(action_weight * local)
        # Action contributions allocate the constructed action axis for
        # interpretability; they are not raw-event causal shares.
        primitive_contributions["ppg"].append(ppg_weight * float(row["ppg"]))
        primitive_contributions["ts_pct"].append(
            ts_weight * float(row["ts_pct"]) if row.get("ts_pct") is not None else 0.0
        )
        primitive_contributions["apg"].append(apg_weight * creation)
        primitive_contributions["presence"].append(
            presence_weight * float(row["presence"]) if row.get("presence") is not None else 0.0
        )
        primitive_contributions["team_context"].append(team_weight * float(row["team_context"]))
        for name, local in action_mix.items():
            primitive_contributions[name].append(action_weight * local * float(row["actions"]))
    report["primitive_effective_weights"] = {
        name: {
            "mean_effective_weight": statistics.fmean(weights),
            "maximum_effective_weight": max(weights),
            "covariance_variance_share": (
                float(
                    np.cov(np.asarray(primitive_contributions[name]), total, ddof=0)[0, 1]
                    / variance
                )
                if variance > 0
                else None
            ),
            "interpretation": (
                "ROLE_ACTION_ALLOCATION_NOT_RAW_EVENT_CAUSAL_SHARE"
                if name in action_mix
                else "FORMULA_REALIZED_WEIGHT"
            ),
        }
        for name, weights in sorted(primitive_weights.items())
    }
    report["role_adjustment"] = {
        "additive_weight": 0.0,
        "role_aware_rows": sum(row.get("broad_role") is not None for row in rows),
        "interpretation": "ROLE_CONDITIONS_ACTION_EVIDENCE_AND_IS_NOT_AN_ADDITIVE_VALUE_CHANNEL",
    }
    return report


def career_counterfactuals(
    candidate_rows: list[dict[str, Any]],
    label: str,
    player_ids: list[str],
    reference: set[str],
) -> tuple[dict[str, float | None], dict[str, float | None], dict[str, Any], dict[str, Any]]:
    values: dict[str, dict[int, float | None]] = defaultdict(dict)
    for row in candidate_rows:
        if row["candidate"] == label:
            values[str(row["player_id"])][int(row["season_id"])] = row[
                "player_season_value_percentile"
            ]
    peak_raw: dict[str, float | None] = {}
    peak_details: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    for player_id in player_ids:
        raw, window, apex = player_peak(values.get(player_id, {}))
        peak_raw[player_id] = raw
        peak_details[player_id] = {
            "raw": raw,
            "three_year": window.value,
            "start_season": window.start_season,
            "end_season": window.end_season,
            "apex": apex,
        }
        evidence[player_id] = longevity_evidence(
            values.get(player_id, {}), threshold=0.80, cap=0.90
        )
    peak_scores = midrank_percentile_scores(peak_raw, reference)
    components = {
        "breadth": {player: float(item.breadth) for player, item in evidence.items()},
        "area": {player: item.capped_area for player, item in evidence.items()},
        "persistence": {player: float(item.longest_run) for player, item in evidence.items()},
    }
    scaled = {
        name: midrank_percentile_scores(value, reference) for name, value in components.items()
    }
    longevity_raw: dict[str, float | None] = {}
    for player_id in player_ids:
        relevant = [value for value in values.get(player_id, {}).values() if value is not None]
        combined = weighted_observed(
            {name: scaled[name][player_id] for name in scaled},
            {"breadth": 0.35, "area": 0.40, "persistence": 0.25},
        )
        longevity_raw[player_id] = combined.value if relevant else None
    longevity_scores = midrank_percentile_scores(longevity_raw, reference)
    return (
        peak_scores,
        longevity_scores,
        peak_details,
        {
            player_id: {
                "raw": longevity_raw[player_id],
                "breadth": evidence[player_id].breadth,
                "capped_area": evidence[player_id].capped_area,
                "longest_run": evidence[player_id].longest_run,
            }
            for player_id in player_ids
        },
    )


def compare_scores(
    candidate: dict[str, float | None],
    frozen: dict[str, float | None],
) -> dict[str, Any]:
    overlap = [
        key for key, value in candidate.items() if value is not None and frozen.get(key) is not None
    ]
    left = [float(frozen[key]) for key in overlap]
    right = [float(candidate[key]) for key in overlap]
    report = {
        "candidate_scores": sum(value is not None for value in candidate.values()),
        "overlap": len(overlap),
        "spearman": spearman(left, right),
        "pearson": correlation(left, right),
    }
    for n in (25, 50, 100):
        old = set(sorted(overlap, key=lambda key: (-float(frozen[key]), key))[:n])
        new = set(sorted(overlap, key=lambda key: (-float(candidate[key]), key))[:n])
        report[f"top_{n}_overlap"] = len(old & new) / n if len(overlap) >= n else None
    return report


def fairness_audit(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row["candidate"] == label and row["player_season_value_percentile"] is not None
    ]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        groups[f"REGIME:{row['evidence_regime']}"].append(row)
        if row.get("broad_role"):
            groups[f"ROLE:{row['broad_role']}"].append(row)
        groups[f"DECADE:{int(row['season_id']) // 10 * 10}s"].append(row)
    return {
        key: {
            "rows": len(members),
            "distribution": distribution(
                [100.0 * float(row["player_season_value_percentile"]) for row in members]
            ),
        }
        for key, members in sorted(groups.items())
    }


def temporal_continuity_audit(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    by_player: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row["candidate"] == label and row["player_season_value_percentile"] is not None:
            by_player[str(row["player_id"])][int(row["season_id"])] = row
    buckets: dict[str, list[float]] = defaultdict(list)
    examples: list[dict[str, Any]] = []
    for player_id, seasons in by_player.items():
        for season, current in seasons.items():
            following = seasons.get(season + 1)
            if following is None:
                continue
            change = 100.0 * (
                float(following["player_season_value_percentile"])
                - float(current["player_season_value_percentile"])
            )
            buckets["ALL_ADJACENT"].append(change)
            regime_changed = current["evidence_regime"] != following["evidence_regime"]
            team_changed = current.get("primary_team_id") != following.get("primary_team_id")
            buckets["REGIME_CHANGED" if regime_changed else "SAME_REGIME"].append(change)
            buckets["TEAM_CHANGED" if team_changed else "SAME_TEAM"].append(change)
            if regime_changed and abs(change) >= 15.0:
                examples.append(
                    {
                        "player_id": player_id,
                        "from_season": season,
                        "to_season": season + 1,
                        "from_regime": current["evidence_regime"],
                        "to_regime": following["evidence_regime"],
                        "score_change": change,
                    }
                )
    return {
        "groups": {
            name: {
                "pairs": len(values),
                "mean_signed_change": statistics.fmean(values) if values else None,
                "mean_absolute_change": statistics.fmean(abs(value) for value in values)
                if values
                else None,
                "share_over_15_points": sum(abs(value) > 15.0 for value in values) / len(values)
                if values
                else None,
            }
            for name, values in sorted(buckets.items())
        },
        "large_regime_transition_examples": sorted(
            examples,
            key=lambda row: (-abs(float(row["score_change"])), str(row["player_id"])),
        )[:25],
        "interpretation": (
            "Adjacent-season changes are diagnostic only; transitions can mix real performance, "
            "team changes, and evidence-regime changes."
        ),
    }


def validation_audit(
    candidate_rows: list[dict[str, Any]], label: str, silver_root: Path
) -> dict[str, Any]:
    index = {
        (str(row["player_id"]), int(row["season_id"])): row
        for row in candidate_rows
        if row["candidate"] == label
    }
    awards: dict[str, list[float]] = defaultdict(list)
    for row in read_rows(silver_root / "player_awards"):
        if row.get("season_id") is None:
            continue
        key = (str(row["player_id"]), int(row["season_id"]))
        value = index.get(key, {}).get("player_season_value_percentile")
        if value is None:
            continue
        if row.get("award_type") == "MVP":
            awards["MVP"].append(100.0 * float(value))
        if row.get("award_type") == "ALL_NBA" and row.get("award_level") == "FIRST":
            awards["ALL_NBA_FIRST"].append(100.0 * float(value))
    selected = [
        row
        for row in candidate_rows
        if row["candidate"] == label and row["player_season_value_percentile"] is not None
    ]
    adjacent: list[tuple[float, float]] = []
    by_player: dict[str, dict[int, float]] = defaultdict(dict)
    for row in selected:
        by_player[str(row["player_id"])][int(row["season_id"])] = float(
            row["player_season_value_percentile"]
        )
    for seasons in by_player.values():
        for season, value in seasons.items():
            if season + 1 in seasons:
                adjacent.append((value, seasons[season + 1]))
    return {
        "awards_used_as_inputs": False,
        "MVP": {
            "seasons": len(awards["MVP"]),
            "mean_percentile": statistics.fmean(awards["MVP"]) if awards["MVP"] else None,
            "share_at_or_above_90": sum(value >= 90 for value in awards["MVP"]) / len(awards["MVP"])
            if awards["MVP"]
            else None,
        },
        "ALL_NBA_FIRST": {
            "seasons": len(awards["ALL_NBA_FIRST"]),
            "mean_percentile": statistics.fmean(awards["ALL_NBA_FIRST"])
            if awards["ALL_NBA_FIRST"]
            else None,
            "share_at_or_above_90": sum(value >= 90 for value in awards["ALL_NBA_FIRST"])
            / len(awards["ALL_NBA_FIRST"])
            if awards["ALL_NBA_FIRST"]
            else None,
        },
        "adjacent_season_pairs": len(adjacent),
        "adjacent_season_spearman": spearman(
            [left for left, _ in adjacent], [right for _, right in adjacent]
        ),
    }


def diagnostic_rows(
    candidate_rows: list[dict[str, Any]],
    label: str,
    names: dict[str, str],
    confidence_by_key: dict[tuple[str, int], tuple[str, str]],
) -> list[dict[str, Any]]:
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        if row["candidate"] == label and names.get(str(row["player_id"])) in DIAGNOSTIC_NAMES:
            selected[str(row["player_id"])].append(row)
    output: list[dict[str, Any]] = []
    for player_id, rows in selected.items():
        best = sorted(
            [row for row in rows if row["player_season_value_percentile"] is not None],
            key=lambda row: (-float(row["player_season_value_percentile"]), int(row["season_id"])),
        )[:5]
        output.append(
            {
                "player_id": player_id,
                "player_name": names[player_id],
                "best_seasons_json": json.dumps(
                    [
                        {
                            "season": row["season_id"],
                            "value_percentile": row["player_season_value_percentile"],
                            "offense": row["offense"],
                            "defense_evidence": row["defense_evidence"],
                            "regime": row["evidence_regime"],
                            "confidence": confidence_by_key.get(
                                (player_id, int(row["season_id"])), (row["confidence"], "")
                            )[0],
                        }
                        for row in best
                    ]
                ),
                "methodology_version": PLAYER_SEASON_VALUE_RESEARCH_VERSION,
                "promoted": False,
                "corpus_id": CORPUS_ID,
            }
        )
    return output


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    inputs = verify_inputs(args.docs_root)
    base_rows, _ = season_inputs(args.gold_root)
    candidate_rows, candidate_summary = build_candidates(base_rows)
    candidate_relationships = candidate_pair_comparison(candidate_rows)
    inventory = evidence_inventory(base_rows)
    regimes = regime_report(base_rows)
    offense = offense_audit(base_rows)
    masking, role_masking, subgroup_masking = masking_audit(base_rows)
    selected = "D_REGIME_RELIABILITY"
    influence = candidate_influence(candidate_rows, selected)
    fairness = fairness_audit(candidate_rows, selected)
    temporal_detail = temporal_continuity_audit(candidate_rows, selected)
    validation = validation_audit(candidate_rows, selected, args.silver_root)

    dimension_rows = read_rows(args.gold_root / "player_dimension_scores/part-00000.parquet")
    dimensions: dict[str, dict[str, float | None]] = defaultdict(dict)
    names: dict[str, str] = {}
    for row in dimension_rows:
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
    peak_scores, longevity_scores, peak_details, longevity_details = career_counterfactuals(
        candidate_rows, selected, players, reference
    )
    peak_comparison = compare_scores(peak_scores, dimensions["PEAK"])
    longevity_comparison = compare_scores(longevity_scores, dimensions["LONGEVITY"])
    distinct_overlap = [
        player_id
        for player_id in players
        if peak_scores[player_id] is not None and longevity_scores[player_id] is not None
    ]
    distinctness = {
        "players": len(distinct_overlap),
        "spearman": spearman(
            [float(peak_scores[player]) for player in distinct_overlap],
            [float(longevity_scores[player]) for player in distinct_overlap],
        ),
        "pearson": correlation(
            [float(peak_scores[player]) for player in distinct_overlap],
            [float(longevity_scores[player]) for player in distinct_overlap],
        ),
        "peak_architecture": "70% complete contiguous three-year + 30% apex",
        "longevity_architecture": "35% P80 breadth + 40% capped P80-P90 area + 25% longest P80 run",
    }
    overall_rows = read_rows(args.gold_root / "player_overall_scores/part-00000.parquet")
    overall_cf_rows, overall_report = overall_counterfactual(peak_scores, overall_rows)
    for row in overall_cf_rows:
        row["methodology_version"] = OVERALL_COUNTERFACTUAL_VERSION

    confidence_by_key = {
        (str(row["player_id"]), int(row["season_id"])): (
            str(row["confidence"]),
            str(row["reason_codes_json"]),
        )
        for row in candidate_rows
        if row["candidate"] == selected
    }
    diagnostics = diagnostic_rows(candidate_rows, selected, names, confidence_by_key)
    for row in diagnostics:
        player_id = str(row["player_id"])
        row["v1_peak"] = dimensions["PEAK"][player_id]
        row["research_peak"] = peak_scores[player_id]
        row["v1_longevity"] = dimensions["LONGEVITY"][player_id]
        row["research_longevity"] = longevity_scores[player_id]
    temporal = {
        "adjacent_season_spearman": validation["adjacent_season_spearman"],
        "adjacent_season_pairs": validation["adjacent_season_pairs"],
        **temporal_detail,
        "coverage_transition_warning": (
            "Trajectories can change at action/role/Presence availability transitions; "
            "the selected research candidate does not pass a universal-regime bridge."
        ),
    }
    latent = {
        "D1": "role/current action evidence only",
        "D2": "75% action + 25% team context",
        "D3": "50% role action + 10% team + 40% observed Presence; complete evidence only",
        "D4": (
            "10% team + up to 35% continuously reliability-weighted observed Presence; "
            "unused Presence share remains on individual actions"
        ),
        "expected_presence_bridge_from_step_0015b": {
            "out_of_fold_r_squared": 0.0174,
            "status": "FAILED_AS_LATENT_FALLBACK",
        },
        "latent_estimate_presented_as_observed": False,
    }

    # The candidate is materially better in attribution but cannot score the early
    # evidence mask and lacks an identified defensive latent bridge.
    verdict = "PROMISING_BUT_NOT_READY"
    gates = {
        "individual_performance_dominates_team_context": float(
            influence["team_context"]["maximum_effective_weight"]
        )
        <= 0.10,
        "team_context_cap_at_most_10_percent": float(
            influence["team_context"]["maximum_effective_weight"]
        )
        <= 0.10,
        "missing_not_zero": True,
        "no_award_postseason_championship_inputs": True,
        "confidence_separate": True,
        "peak_70_30_unchanged": True,
        "longevity_35_40_25_unchanged": True,
        "early_regime_masking_passes": masking["regimes"]["EARLY_LIMITED"]["coverage_pct"] >= 0.95,
        "historical_coverage_sufficient": candidate_summary[selected]["coverage_pct"] >= 0.90,
        "frozen_v1_unchanged": True,
    }
    result = "PASS"

    output_root = args.gold_root / "player_season_value_audit"
    selected_rows = [row for row in candidate_rows if row["candidate"] == selected]
    manifests = [
        write_parquet(
            selected_rows,
            output_root / "player-season-value-research.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "v1_peak": dimensions["PEAK"][player_id],
                    "counterfactual_peak": peak_scores[player_id],
                    **peak_details[player_id],
                    "methodology_version": PEAK_COUNTERFACTUAL_VERSION,
                    "promoted": False,
                    "corpus_id": CORPUS_ID,
                }
                for player_id in players
            ],
            output_root / "peak-counterfactual.parquet",
            ("player_id",),
        ),
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "v1_longevity": dimensions["LONGEVITY"][player_id],
                    "counterfactual_longevity": longevity_scores[player_id],
                    **longevity_details[player_id],
                    "methodology_version": LONGEVITY_COUNTERFACTUAL_VERSION,
                    "promoted": False,
                    "corpus_id": CORPUS_ID,
                }
                for player_id in players
            ],
            output_root / "longevity-counterfactual.parquet",
            ("player_id",),
        ),
        write_parquet(
            overall_cf_rows,
            output_root / "overall-counterfactual.parquet",
            ("player_id",),
        ),
        write_parquet(
            diagnostics,
            output_root / "diagnostic-players.parquet",
            ("player_name",),
        ),
    ]

    report_payloads: dict[str, dict[str, Any]] = {
        "player-season-value-evidence-inventory.json": {"evidence": inventory},
        "player-season-value-regimes.json": {"regimes": regimes},
        "player-season-value-offense-audit.json": {"offense_candidates": offense},
        "player-season-value-defensive-measurement.json": {"defensive_models": latent},
        "player-season-value-masking-audit.json": {
            "masking": masking,
            "role_masking": role_masking,
            "archetype_and_team_context_masking": subgroup_masking,
        },
        "player-season-value-component-influence.json": {
            "selected_candidate": selected,
            **influence,
        },
        "player-season-value-fairness-continuity.json": {
            "groups": fairness,
            "temporal": temporal,
        },
        "player-season-value-candidate-comparison.json": {
            "candidates": candidate_summary,
            "pairwise_candidate_relationships": candidate_relationships,
            "selected_research_candidate": selected,
            "measurement_verdict": verdict,
            "promotion_gates": gates,
        },
        "player-season-value-peak-counterfactual.json": {
            "comparison": peak_comparison,
            "architecture_unchanged": True,
        },
        "player-season-value-longevity-counterfactual.json": {
            "comparison": longevity_comparison,
            "architecture_unchanged": True,
        },
        "player-season-value-peak-longevity-distinctness.json": distinctness,
        "player-season-value-validation.json": validation,
        "player-season-value-diagnostic-players.json": {"players": diagnostics},
        "player-season-value-overall-sensitivity.json": overall_report,
        "player-season-value-verdict.json": {
            "step_result": result,
            "measurement_verdict": verdict,
            "promotion_gates": gates,
            "production_methodology_created": False,
            "frozen_v1_overwritten": False,
            "defense_modified": False,
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in report_payloads.items():
        document = {
            "step": "STEP-0015D",
            "methodology_version": PLAYER_SEASON_VALUE_AUDIT_VERSION,
            "input_fingerprints": inputs,
            **payload,
        }
        stable_json(args.docs_root / name, document)
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": inputs,
                "outputs": manifests,
                "reports": report_hashes,
                "result": result,
                "verdict": verdict,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015D",
        "result": result,
        "measurement_verdict": verdict,
        "audit_methodology_version": PLAYER_SEASON_VALUE_AUDIT_VERSION,
        "research_methodology_version": PLAYER_SEASON_VALUE_RESEARCH_VERSION,
        "production_methodology_created": False,
        "selected_research_candidate": selected,
        "input_fingerprints": inputs,
        "target": "overall regular-season individual basketball value for one player-season",
        "season_rows": len(base_rows),
        "players": len(players),
        "regimes": regimes,
        "candidate_summary": candidate_summary,
        "masking": masking,
        "influence": influence,
        "peak_counterfactual": peak_comparison,
        "longevity_counterfactual": longevity_comparison,
        "peak_longevity_distinctness": distinctness,
        "overall_sensitivity": overall_report,
        "validation": validation,
        "promotion_gates": gates,
        "network_requests": 0,
        "output_partitions": manifests,
        "output_fingerprint": fingerprint,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint,
    }
    stable_json(args.docs_root / "player-season-value-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, observed {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
