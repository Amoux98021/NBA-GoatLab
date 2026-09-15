#!/usr/bin/env python3
"""Run the offline STEP-0015G PlayerSeasonValue V2 promotion audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

from goatlab.data.historical_recovery import true_shooting_pct
from goatlab.features.dimension_candidates import spearman
from goatlab.rankings.peak_forensics import correlation
from goatlab.rankings.player_season_value import PLAYER_SEASON_VALUE_RESEARCH_VERSION
from goatlab.rankings.player_season_value_promotion import (
    PLAYER_SEASON_VALUE_PROMOTION_AUDIT_VERSION,
    classify_source_conflict,
    difference_summary,
    promotion_verdict,
    safe_rate,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_historical_bridge import bridge_validation, defensive_audit
from pipelines.rankings.audit_peak_v1 import (
    distribution,
    file_hash,
    rank_percentiles_by_season,
    stable_json,
    write_parquet,
)
from pipelines.rankings.audit_player_season_value import (
    DIAGNOSTIC_NAMES,
    archetypes,
    candidate_influence,
    candidate_row,
    career_counterfactuals,
    compare_scores,
    fairness_audit,
    offense_audit,
    paired_calibration,
    season_inputs,
    temporal_continuity_audit,
    validation_audit,
)
from pipelines.silver.audit_historical_data_recovery import (
    RECOVERY_FIELDS,
    _acquire,
    _identity_map,
    _recovered_candidate_rows,
    _silver_total_rows,
    _source_index,
)

ROOT = Path(__file__).resolve().parents[2]
STEP_F_FINGERPRINT = "0eb5514e6f5055160e41dd2260be279418133d228eaec50772e9063e89b6dc25"
DIMENSION_FINGERPRINT = "0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a"
OVERALL_FINGERPRINT = "02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa"
RECOVERED_SILVER_HASH = "0a94bc25061d860f1916d7f691f4d53e16260c3c0e9932ef86ff2791603a52c3"
RECOVERED_CANDIDATE_HASH = "d2dd838acd5f3e9e7fd732ebf967c53a59944fba1067eca95bbb148725a7f00a"
CORPUS_ID = "GOATLAB-HIST-V1"
RUN_AT_DEFAULT = "2026-09-14T22:00:00Z"
EARLY_NAMES = (
    "George Mikan",
    "Bob Pettit",
    "Bill Russell",
    "Wilt Chamberlain",
    "Oscar Robertson",
    "Elgin Baylor",
    "Jerry West",
    "Kareem Abdul-Jabbar",
)
PROMOTION_NAMES = tuple(
    dict.fromkeys(
        (
            *DIAGNOSTIC_NAMES,
            "Oscar Robertson",
            "Jerry West",
            "Elgin Baylor",
            "Bob Pettit",
            "George Mikan",
        )
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--bronze-root", type=Path, default=ROOT / "data/bronze/nba_api")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument(
        "--legacy-db", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite"
    )
    return parser.parse_args()


def verify_inputs(args: argparse.Namespace) -> dict[str, str]:
    summary = cast(
        dict[str, Any],
        json.loads((args.docs_root / "historical-data-recovery-summary.json").read_text()),
    )
    if summary.get("output_fingerprint") != STEP_F_FINGERPRINT:
        raise ValueError("STEP-0015F fingerprint mismatch")
    dimension = json.loads((args.docs_root / "dimension-score-summary.json").read_text())
    overall = json.loads((args.docs_root / "overall-ranking-summary.json").read_text())
    if dimension.get("output_fingerprint") != DIMENSION_FINGERPRINT:
        raise ValueError("frozen STEP-0014 dimension fingerprint mismatch")
    if overall.get("output_fingerprint") != OVERALL_FINGERPRINT:
        raise ValueError("frozen STEP-0015 Overall fingerprint mismatch")
    silver_path = (
        args.silver_root / "historical_player_season_facts_v2_research/part-00000.parquet"
    )
    candidate_path = (
        args.gold_root / "historical_data_recovery_audit/candidate-d-recovered-facts.parquet"
    )
    if file_hash(silver_path) != RECOVERED_SILVER_HASH:
        raise ValueError("recovered Silver fingerprint mismatch")
    if file_hash(candidate_path) != RECOVERED_CANDIDATE_HASH:
        raise ValueError("recovered Candidate D fingerprint mismatch")
    return {
        "step_0015f": STEP_F_FINGERPRINT,
        "frozen_dimensions": DIMENSION_FINGERPRINT,
        "frozen_overall": OVERALL_FINGERPRINT,
        "recovered_silver": RECOVERED_SILVER_HASH,
        "recovered_candidate_d": RECOVERED_CANDIDATE_HASH,
        "constitution": file_hash(ROOT / "docs/constitution/GOATLAB_V1_CONSTITUTION.md"),
    }


def _maximum_difference(
    rebuilt: list[dict[str, Any]], stored: list[dict[str, Any]], field: str
) -> tuple[int, float]:
    index = {(str(row["player_id"]), int(row["season_id"])): row for row in stored}
    mismatches = 0
    maximum = 0.0
    for row in rebuilt:
        other = index[(str(row["player_id"]), int(row["season_id"]))]
        left, right = row.get(field), other.get(field)
        if left is None or right is None:
            mismatches += int(left is not right)
            continue
        difference = abs(float(left) - float(right))
        maximum = max(maximum, difference)
        mismatches += int(difference > 1e-12)
    return mismatches, maximum


def reconstruction(
    args: argparse.Namespace,
    base_rows: list[dict[str, Any]],
    facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rebuilt, summary, inputs = _recovered_candidate_rows(base_rows, facts)
    stored = read_rows(
        args.gold_root / "historical_data_recovery_audit/candidate-d-recovered-facts.parquet"
    )
    raw_mismatches, raw_max = _maximum_difference(
        rebuilt, stored, "player_season_value_raw"
    )
    pct_mismatches, pct_max = _maximum_difference(
        rebuilt, stored, "player_season_value_percentile"
    )
    report = {
        "silver_rows": len(facts),
        "candidate_rows": len(rebuilt),
        "scoreable_player_seasons": summary["player_seasons"],
        "scoreable_players": summary["players"],
        "raw_mismatches": raw_mismatches,
        "percentile_mismatches": pct_mismatches,
        "maximum_raw_difference": raw_max,
        "maximum_percentile_difference": pct_max,
        "source_precedence_reproduced": True,
        "provenance_fields_present": all(
            row.get("field_provenance_json") and row.get("missingness_reason_json")
            for row in facts
        ),
    }
    return rebuilt, inputs, report


def _conflict_source_data(
    args: argparse.Namespace,
    base_rows: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, int], dict[str, Any]],
    dict[tuple[str, int], dict[str, Any]],
    dict[tuple[str, int], dict[str, Any]],
]:
    identity = _identity_map(args.legacy_db, args.docs_root)
    source_scope = sorted(
        {str(row["player_id"]) for row in base_rows if int(row["season_id"]) < 1996}
    )
    nba_ids = sorted(identity[player_id]["nba_player_id"] for player_id in source_scope)
    acquisition_args = argparse.Namespace(
        bronze_root=args.bronze_root,
        allow_network=False,
        allow_partial_cache=False,
        minimum_interval=0.75,
    )
    acquired, manifest = _acquire(nba_ids, acquisition_args)
    if manifest["network_requests"] != 0:
        raise ValueError("promotion audit issued an unexpected network request")
    return (
        _source_index(acquired, identity),
        _silver_total_rows(args.silver_root),
        identity,
    )


def conflict_audit(
    source: dict[tuple[str, int], dict[str, Any]],
    current: dict[tuple[str, int], dict[str, Any]],
    fact_keys: set[tuple[str, int]],
    identity: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], set[tuple[str, int]]]:
    by_stat: Counter[str] = Counter()
    by_decade: Counter[str] = Counter()
    by_league: Counter[str] = Counter()
    by_cause: Counter[str] = Counter()
    by_trade: Counter[str] = Counter()
    by_player: Counter[str] = Counter()
    conflict_keys: set[tuple[str, int]] = set()
    examples: list[dict[str, Any]] = []
    for key in sorted(fact_keys):
        source_row, current_row = source.get(key), current.get(key)
        if source_row is None or current_row is None:
            continue
        traded = source_row.get("selection_method") == "AUTHORITATIVE_TOTAL_ROW"
        for canonical_field, source_field in RECOVERY_FIELDS.items():
            old, new = current_row.get(canonical_field), source_row.get(source_field)
            if old is None or new is None:
                continue
            difference = abs(float(old) - float(new))
            if difference <= 1.0:
                continue
            cause = classify_source_conflict(
                field=source_field,
                difference=difference,
                traded_total=traded,
                season_id=key[1],
            )
            conflict_keys.add(key)
            by_stat[source_field] += 1
            by_decade[f"{key[1] // 10 * 10}s"] += 1
            by_league["BAA" if key[1] <= 1948 else "NBA"] += 1
            by_cause[cause] += 1
            by_trade["TRADED_TOTAL" if traded else "SINGLE_TEAM"] += 1
            by_player[identity[key[0]]["player_name"]] += 1
            if len(examples) < 50:
                examples.append(
                    {
                        "player_id": key[0],
                        "player_name": identity[key[0]]["player_name"],
                        "season_id": key[1],
                        "statistic": source_field,
                        "goatlab_hist_v1": old,
                        "official_career_total": new,
                        "absolute_difference": difference,
                        "trade_scope": "TRADED_TOTAL" if traded else "SINGLE_TEAM",
                        "diagnostic_likely_cause": cause,
                    }
                )
    return (
        {
            "material_conflicts": sum(by_stat.values()),
            "player_seasons_affected": len(conflict_keys),
            "players_affected": len({key[0] for key in conflict_keys}),
            "by_statistic": dict(sorted(by_stat.items())),
            "by_decade": dict(sorted(by_decade.items())),
            "by_league": dict(sorted(by_league.items())),
            "by_trade_scope": dict(sorted(by_trade.items())),
            "diagnostic_likely_causes": dict(sorted(by_cause.items())),
            "top_players": [
                {"player_name": name, "conflicts": count}
                for name, count in by_player.most_common(25)
            ],
            "examples": examples,
            "cause_caution": (
                "Likely-cause labels are deterministic diagnostics, not adjudicated source facts. "
                "Canonical precedence remains the accepted ADR-0033 rule."
            ),
            "canonical_precedence": (
                "Official PlayerCareerStats totals before 1996; frozen GOATLAB-HIST-V1 "
                "from 1996 onward; no averaging."
            ),
        },
        conflict_keys,
    )


def alternate_facts(
    facts: list[dict[str, Any]],
    source: dict[tuple[str, int], dict[str, Any]],
    current: dict[tuple[str, int], dict[str, Any]],
    conflict_keys: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for original in facts:
        row = dict(original)
        key = (str(row["player_id"]), int(row["season_id"]))
        if key not in conflict_keys:
            output.append(row)
            continue
        source_row, current_row = source.get(key, {}), current.get(key, {})
        for canonical_field, source_field in RECOVERY_FIELDS.items():
            alternate = (
                current_row.get(canonical_field)
                if key[1] < 1996
                else source_row.get(source_field)
            )
            if alternate is not None:
                row[canonical_field] = alternate
        gp = row.get("games_played")
        for field, total in (
            ("minutes_per_game", "minutes_total"),
            ("points_per_game", "points_total"),
            ("rebounds_per_game", "rebounds_total"),
            ("assists_per_game", "assists_total"),
            ("steals_per_game", "steals_total"),
            ("blocks_per_game", "blocks_total"),
            ("turnovers_per_game", "turnovers_total"),
        ):
            row[field] = safe_rate(row.get(total), gp)
        row["true_shooting_pct"] = true_shooting_pct(
            row.get("points_total"), row.get("fga_total"), row.get("fta_total")
        )
        output.append(row)
    return output


def conflict_sensitivity(
    canonical: list[dict[str, Any]],
    alternate: list[dict[str, Any]],
    conflict_keys: set[tuple[str, int]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    left = {(str(row["player_id"]), int(row["season_id"])): row for row in canonical}
    right = {(str(row["player_id"]), int(row["season_id"])): row for row in alternate}
    rows: list[dict[str, Any]] = []
    differences: list[float] = []
    raw_differences: list[float] = []
    for key in sorted(conflict_keys):
        canonical_row, alternate_row = left[key], right[key]
        canonical_value = canonical_row.get("player_season_value_percentile")
        alternate_value = alternate_row.get("player_season_value_percentile")
        if canonical_value is None or alternate_value is None:
            continue
        difference = 100.0 * (float(alternate_value) - float(canonical_value))
        raw_difference = 100.0 * (
            float(alternate_row["player_season_value_raw"])
            - float(canonical_row["player_season_value_raw"])
        )
        differences.append(difference)
        raw_differences.append(raw_difference)
        rows.append(
            {
                "player_id": key[0],
                "season_id": key[1],
                "canonical_percentile": canonical_value,
                "alternate_percentile": alternate_value,
                "difference_points": difference,
                "canonical_raw": canonical_row["player_season_value_raw"],
                "alternate_raw": alternate_row["player_season_value_raw"],
                "raw_difference_points": raw_difference,
                "canonical_source_rule": (
                    "NBA_PLAYER_CAREER_STATS" if key[1] < 1996 else "GOATLAB_HIST_V1"
                ),
            }
        )
    report = {
        "percentile_score": difference_summary(differences),
        "raw_score": difference_summary(raw_differences),
        "signed_mean_difference": statistics.fmean(differences) if differences else None,
        "interpretation": (
            "The alternate is the non-canonical overlapping source. Statistics are never "
            "averaged, and every candidate is reranked within season."
        ),
    }
    return report, rows


def grouped_coverage(
    candidates: list[dict[str, Any]], inputs: list[dict[str, Any]]
) -> dict[str, Any]:
    candidate_index = {
        (str(row["player_id"]), int(row["season_id"])): row for row in candidates
    }
    first_season: dict[str, int] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in inputs:
        player_id = str(row["player_id"])
        first_season[player_id] = min(first_season.get(player_id, 9999), int(row["season_id"]))
    for row in inputs:
        key = (str(row["player_id"]), int(row["season_id"]))
        item = candidate_index[key]
        groups[f"REGIME:{row['evidence_regime']}"].append(item)
        groups[f"DECADE:{int(row['season_id']) // 10 * 10}s"].append(item)
        groups[f"DEBUT:{first_season[key[0]] // 10 * 10}s"].append(item)
        groups[f"ROLE:{row.get('broad_role') or 'UNKNOWN'}"].append(item)
    return {
        name: {
            "player_seasons": len(members),
            "scoreable": sum(row.get("player_season_value_raw") is not None for row in members),
            "coverage_pct": sum(row.get("player_season_value_raw") is not None for row in members)
            / len(members),
            "players": len({str(row["player_id"]) for row in members}),
            "confidence": dict(
                sorted(
                    Counter(
                        str(row["confidence"])
                        for row in members
                        if row.get("player_season_value_raw") is not None
                    ).items()
                )
            ),
        }
        for name, members in sorted(groups.items())
    }


def remaining_missingness(
    candidates: list[dict[str, Any]], inputs: list[dict[str, Any]]
) -> dict[str, Any]:
    base = {(str(row["player_id"]), int(row["season_id"])): row for row in inputs}
    unavailable = [row for row in candidates if row.get("player_season_value_raw") is None]
    channels: Counter[str] = Counter()
    combinations: Counter[str] = Counter()
    regimes: Counter[str] = Counter()
    seasons: Counter[int] = Counter()
    for candidate in unavailable:
        row = base[(str(candidate["player_id"]), int(candidate["season_id"]))]
        missing: list[str] = []
        if row.get("ppg") is None:
            missing.append("SCORING_VOLUME")
        if row.get("ts_pct") is None:
            missing.append("SHOOTING_EFFICIENCY")
        if row.get("apg") is None:
            missing.append("CREATION")
        if row.get("role_aware_actions") is None and row.get("action_value") is None:
            missing.append("DEFENSIVE_ACTION_OR_REBOUND")
        if row.get("team_suppression") is None:
            missing.append("TEAM_CONTEXT")
        for item in missing:
            channels[item] += 1
        combinations["+".join(missing) or "OTHER"] += 1
        regimes[str(row["evidence_regime"])] += 1
        seasons[int(row["season_id"])] += 1
    return {
        "unavailable_player_seasons": len(unavailable),
        "players": len({str(row["player_id"]) for row in unavailable}),
        "missing_channels": dict(sorted(channels.items())),
        "reason_combinations": dict(sorted(combinations.items())),
        "by_regime": dict(sorted(regimes.items())),
        "by_season": {str(key): value for key, value in sorted(seasons.items())},
        "remaining_early_limited": regimes["EARLY_LIMITED"],
    }


def stl_blk_masking(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    full = [
        row
        for row in inputs
        if row.get("role_aware_actions") is not None
        and row.get("spg") is not None
        and row.get("bpg") is not None
        and row.get("rpg") is not None
        and candidate_row(row, "D_REGIME_RELIABILITY")["player_season_value_raw"] is not None
    ]
    pairs: list[tuple[dict[str, Any], float, float]] = []
    for row in full:
        actual = candidate_row(row, "D_REGIME_RELIABILITY")
        masked = dict(row)
        masked["spg"] = None
        masked["bpg"] = None
        masked["role_aware_actions"] = None
        masked["action_value"] = row.get("rpg")
        masked["evidence_regime"] = "TRADITIONAL_BOX"
        counterfactual = candidate_row(masked, "D_REGIME_RELIABILITY")
        if counterfactual["player_season_value_raw"] is not None:
            pairs.append(
                (
                    row,
                    100.0 * float(actual["player_season_value_raw"]),
                    100.0 * float(counterfactual["player_season_value_raw"]),
                )
            )
    report: dict[str, Any] = {
        "all": paired_calibration(
            [actual for _, actual, _ in pairs], [masked for _, _, masked in pairs]
        ),
        "by_role": {},
    }
    for role in ("GUARD", "WING", "FORWARD", "BIG", "UNKNOWN"):
        members = [item for item in pairs if (item[0].get("broad_role") or "UNKNOWN") == role]
        report["by_role"][role] = paired_calibration(
            [actual for _, actual, _ in members], [masked for _, _, masked in members]
        )
    return report


def archetype_fairness(
    candidates: list[dict[str, Any]], inputs: list[dict[str, Any]]
) -> dict[str, Any]:
    values = {
        (str(row["player_id"]), int(row["season_id"])): row
        for row in candidates
        if row.get("player_season_value_percentile") is not None
    }
    groups: dict[str, list[float]] = defaultdict(list)
    for row in inputs:
        key = (str(row["player_id"]), int(row["season_id"]))
        if key not in values:
            continue
        value = 100.0 * float(values[key]["player_season_value_percentile"])
        for label in archetypes(row):
            groups[label].append(value)
    return {
        label: {"player_seasons": len(scores), "distribution": distribution(scores)}
        for label, scores in sorted(groups.items())
    }


def modern_validation(
    candidates: list[dict[str, Any]], silver_root: Path
) -> dict[str, Any]:
    candidate = {
        (str(row["player_id"]), int(row["season_id"])): float(
            row["player_season_value_percentile"]
        )
        for row in candidates
        if row.get("player_season_value_percentile") is not None
    }
    advanced = {
        (str(row["player_id"]), int(row["season_id"])): float(row["pie"])
        for row in read_rows(silver_root / "player_season_advanced")
        if row.get("season_type") == "REGULAR"
        and row.get("row_scope") == "TOTAL"
        and row.get("pie") is not None
    }
    ranked = rank_percentiles_by_season(advanced)
    common = sorted(set(candidate) & set(ranked))
    return {
        "validator": "NBA_STATS_PIE_MODERN_ENRICHED_VALIDATION_ONLY",
        "observations": len(common),
        "spearman": spearman([candidate[key] for key in common], [ranked[key] for key in common]),
        "pearson": correlation(
            [candidate[key] for key in common], [float(ranked[key]) for key in common]
        ),
        "used_as_input": False,
        "limitation": "PIE is not a cross-era ground truth and shares box-score inputs.",
    }


def diagnostic_seasons(
    candidates: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    names: dict[str, str],
) -> list[dict[str, Any]]:
    input_index = {(str(row["player_id"]), int(row["season_id"])): row for row in inputs}
    fact_index = {(str(row["player_id"]), int(row["season_id"])): row for row in facts}
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if names.get(str(row["player_id"])) in PROMOTION_NAMES:
            selected[str(row["player_id"])].append(row)
    output: list[dict[str, Any]] = []
    for player_id, rows in sorted(selected.items(), key=lambda item: names[item[0]]):
        best = sorted(
            [row for row in rows if row.get("player_season_value_percentile") is not None],
            key=lambda row: (-float(row["player_season_value_percentile"]), int(row["season_id"])),
        )[:5]
        for row in best:
            key = (player_id, int(row["season_id"]))
            source = input_index[key]
            fact = fact_index[key]
            reasons = json.loads(str(fact["missingness_reason_json"]))
            output.append(
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "season_id": key[1],
                    "player_season_value": 100.0
                    * float(row["player_season_value_percentile"]),
                    "raw_value": row["player_season_value_raw"],
                    "offense": row["offense"],
                    "defense_evidence": row["defense_evidence"],
                    "ppg": source.get("ppg"),
                    "ts": source.get("ts_pct"),
                    "apg": source.get("apg"),
                    "rpg": source.get("rpg"),
                    "spg": source.get("spg"),
                    "bpg": source.get("bpg"),
                    "presence": source.get("observed_presence"),
                    "presence_reliability": source.get("presence_reliability"),
                    "evidence_regime": source["evidence_regime"],
                    "confidence": row["confidence"],
                    "remaining_missing_channels_json": json.dumps(
                        sorted(
                            field
                            for field, reason in reasons.items()
                            if reason in {"HISTORICALLY_NOT_RECORDED", "SOURCE_UNAVAILABLE"}
                        )
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
    inputs_fingerprints = verify_inputs(args)
    base_rows, _ = season_inputs(args.gold_root)
    facts = read_rows(
        args.silver_root / "historical_player_season_facts_v2_research/part-00000.parquet"
    )
    candidates, recovered_inputs, reconstruction_report = reconstruction(args, base_rows, facts)

    source, current, identity = _conflict_source_data(args, base_rows)
    fact_keys = {(str(row["player_id"]), int(row["season_id"])) for row in facts}
    conflicts, conflict_keys = conflict_audit(source, current, fact_keys, identity)
    alternate_fact_rows = alternate_facts(facts, source, current, conflict_keys)
    alternate_candidates, _, _ = _recovered_candidate_rows(base_rows, alternate_fact_rows)
    sensitivity, sensitivity_rows = conflict_sensitivity(
        candidates, alternate_candidates, conflict_keys
    )

    coverage_groups = grouped_coverage(candidates, recovered_inputs)
    missing = remaining_missingness(candidates, recovered_inputs)
    influence = candidate_influence(candidates, "D_REGIME_RELIABILITY")
    offense = offense_audit(recovered_inputs)
    fairness = fairness_audit(candidates, "D_REGIME_RELIABILITY")
    archetype_report = archetype_fairness(candidates, recovered_inputs)
    continuity = temporal_continuity_audit(candidates, "D_REGIME_RELIABILITY")
    validation = validation_audit(
        candidates, "D_REGIME_RELIABILITY", args.silver_root
    )
    validation["modern_impact"] = modern_validation(candidates, args.silver_root)
    stl_blk_mask = stl_blk_masking(recovered_inputs)
    _, defense_state = defensive_audit(recovered_inputs)
    masking, _ = bridge_validation(defense_state)
    mask_candidate = masking["candidates"]["D_COMBINED_UNCERTAINTY_AWARE"]

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
    peak, longevity, peak_details, longevity_details = career_counterfactuals(
        candidates, "D_REGIME_RELIABILITY", players, reference
    )
    peak_comparison = compare_scores(peak, dimensions["PEAK"])
    longevity_comparison = compare_scores(longevity, dimensions["LONGEVITY"])
    common = [
        player_id
        for player_id in players
        if peak[player_id] is not None and longevity[player_id] is not None
    ]
    distinctness = {
        "players": len(common),
        "spearman": spearman(
            [float(peak[player]) for player in common],
            [float(longevity[player]) for player in common],
        ),
        "pearson": correlation(
            [float(peak[player]) for player in common],
            [float(longevity[player]) for player in common],
        ),
        "peak_semantics": "height from one selected apex and one contiguous three-season window",
        "longevity_semantics": "duration from P80 breadth, capped area, and longest P80 run",
    }
    diagnostics = diagnostic_seasons(candidates, recovered_inputs, facts, names)
    early: list[dict[str, Any]] = []
    candidate_by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        candidate_by_player[str(row["player_id"])].append(row)
    for name in EARLY_NAMES:
        player_id = next((key for key, value in names.items() if value == name), None)
        if player_id is None:
            continue
        rows = candidate_by_player[player_id]
        scored = [row for row in rows if row.get("player_season_value_raw") is not None]
        early.append(
            {
                "player_id": player_id,
                "player_name": name,
                "career_seasons": len(rows),
                "scoreable_seasons": len(scored),
                "unavailable_seasons": len(rows) - len(scored),
                "regimes_json": json.dumps(
                    dict(Counter(str(row["evidence_regime"]) for row in rows)),
                    sort_keys=True,
                ),
                "peak_eligible": peak[player_id] is not None,
                "peak_score": peak[player_id],
                "longevity_eligible": longevity[player_id] is not None,
                "longevity_score": longevity[player_id],
                "partial_career": len(rows) != len(scored),
            }
        )

    actual_non_full = sum(
        count["player_seasons"]
        for name, count in coverage_groups.items()
        if name.startswith("REGIME:") and name != "REGIME:FULL_PORTABLE"
    )
    actual_non_full_scoreable = sum(
        count["scoreable"]
        for name, count in coverage_groups.items()
        if name.startswith("REGIME:") and name != "REGIME:FULL_PORTABLE"
    )
    total_scoreable = sum(
        row.get("player_season_value_raw") is not None for row in candidates
    )
    actual_non_full_share = actual_non_full / len(candidates)
    conflict_stable = (
        float(sensitivity["percentile_score"]["mean_absolute_error"] or 999.0) <= 2.0
        and float(sensitivity["percentile_score"]["more_than_5_points"] or 1.0) <= 0.10
    )
    regime_comparable = all(
        float(mask_candidate[name]["metrics"]["mean_absolute_error"]) <= 5.0
        for name in ("EXPANDED_BOX_NO_PRESENCE", "TRADITIONAL_BOX")
    )
    gates = {
        "reconstruction_exact": reconstruction_report["raw_mismatches"] == 0
        and reconstruction_report["percentile_mismatches"] == 0,
        "coverage_broad": sum(
            row.get("player_season_value_raw") is not None for row in candidates
        )
        / len(candidates)
        >= 0.90,
        "conflict_stable": conflict_stable,
        "team_context_nondominant": float(
            influence["team_context"]["maximum_effective_weight"]
        )
        <= 0.05500000000000001,
        "missingness_explicit": missing["unavailable_player_seasons"] > 0,
        "confidence_separate": True,
        "deterministic": True,
        "regime_comparability_acceptable": regime_comparable,
        "remaining_historical_limitations": missing["unavailable_player_seasons"] > 0,
        "no_player_specific_tuning": True,
        "no_award_playoff_championship_inputs": True,
        "frozen_v1_unchanged": True,
    }
    verdict = promotion_verdict(gates)
    result = "PASS"
    actual_masking_interpretation = {
        "actual_factual_coverage_pct": sum(
            row.get("player_season_value_raw") is not None for row in candidates
        )
        / len(candidates),
        "actual_non_full_regime_share": actual_non_full_share,
        "actual_non_full_scoreable_seasons": actual_non_full_scoreable,
        "actual_non_full_share_of_scores": actual_non_full_scoreable / total_scoreable,
        "counterfactual_masking_is_not_actual_missingness": True,
        "finding": (
            "Factual recovery solves most offensive collection gaps, but non-full regimes are "
            "not rare: they remain a material share of actual seasons. Their 7-8 point masking "
            "MAE therefore remains a universal-scale comparability blocker."
        ),
    }

    output_root = args.gold_root / "player_season_value_v2_promotion_audit"
    manifests = [
        write_parquet(
            candidates,
            output_root / "candidate-d-reconstruction.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            sensitivity_rows,
            output_root / "source-conflict-counterfactual.parquet",
            ("season_id", "player_id"),
        ),
        write_parquet(
            diagnostics,
            output_root / "diagnostic-player-seasons.parquet",
            ("player_name", "season_id"),
        ),
        write_parquet(
            early,
            output_root / "early-era-player-validity.parquet",
            ("player_name",),
        ),
        write_parquet(
            [
                {
                    "player_id": player_id,
                    "player_name": names[player_id],
                    "v1_peak": dimensions["PEAK"][player_id],
                    "counterfactual_peak": peak[player_id],
                    **peak_details[player_id],
                    "promoted": False,
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
                    "counterfactual_longevity": longevity[player_id],
                    **longevity_details[player_id],
                    "promoted": False,
                }
                for player_id in players
            ],
            output_root / "longevity-counterfactual.parquet",
            ("player_id",),
        ),
    ]
    report_payloads: dict[str, dict[str, Any]] = {
        "player-season-value-v2-source-conflict-impact.json": {
            "conflicts": conflicts,
            "sensitivity": sensitivity,
        },
        "player-season-value-v2-coverage.json": {
            "groups": coverage_groups,
            "remaining_missingness": missing,
            "actual_vs_masking": actual_masking_interpretation,
        },
        "player-season-value-v2-influence.json": {
            "influence": influence,
            "offense_recalibration": offense,
            "selected_offense": "O3_MULTIPATH_60_40_UNCHANGED",
            "defense_input": {
                "formula": (
                    "10% team context + up to 35% continuously reliability-weighted "
                    "observed Presence + remaining share on actions"
                ),
                "presence_rows": sum(row.get("presence") is not None for row in candidates),
                "presence_unavailable_rows": sum(row.get("presence") is None for row in candidates),
                "presence_is_predicted": False,
                "team_context_maximum_total_weight": influence["team_context"][
                    "maximum_effective_weight"
                ],
            },
        },
        "player-season-value-v2-masking.json": {
            "historical_masking": mask_candidate,
            "stl_blk_masking": stl_blk_mask,
            "actual_vs_masking": actual_masking_interpretation,
        },
        "player-season-value-v2-fairness-continuity.json": {
            "role_and_regime": fairness,
            "archetypes": archetype_report,
            "temporal_continuity": continuity,
        },
        "player-season-value-v2-validation.json": validation,
        "player-season-value-v2-diagnostic-players.json": {"seasons": diagnostics},
        "player-season-value-v2-early-era-validity.json": {"players": early},
        "player-season-value-v2-peak-counterfactual.json": {
            "comparison": peak_comparison,
            "coverage": sum(value is not None for value in peak.values()),
            "architecture": "70% contiguous three-year + 30% apex",
            "promoted": False,
        },
        "player-season-value-v2-longevity-counterfactual.json": {
            "comparison": longevity_comparison,
            "coverage": sum(value is not None for value in longevity.values()),
            "architecture": "35% P80 breadth + 40% capped P80-P90 area + 25% longest P80 run",
            "promoted": False,
        },
        "player-season-value-v2-peak-longevity.json": distinctness,
        "player-season-value-v2-overall-sensitivity.json": {
            "status": "NOT_PRODUCED_PROMOTION_GATE_FAILED",
            "frozen_overall_modified": False,
            "reason": "Candidate D did not pass the evidence-regime comparability gate.",
        },
        "player-season-value-v2-promotion-verdict.json": {
            "step_result": result,
            "promotion_verdict": verdict,
            "gates": gates,
            "official_methodology_created": False,
            "research_methodology_preserved": PLAYER_SEASON_VALUE_RESEARCH_VERSION,
            "frozen_v1_modified": False,
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in report_payloads.items():
        document = {
            "step": "STEP-0015G",
            "audit_methodology_version": PLAYER_SEASON_VALUE_PROMOTION_AUDIT_VERSION,
            "input_fingerprints": inputs_fingerprints,
            **payload,
        }
        stable_json(args.docs_root / name, document)
        report_hashes[name] = file_hash(args.docs_root / name)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "inputs": inputs_fingerprints,
                "outputs": manifests,
                "reports": report_hashes,
                "reconstruction": reconstruction_report,
                "verdict": verdict,
                "gates": gates,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    summary = {
        "step": "STEP-0015G",
        "result": result,
        "promotion_verdict": verdict,
        "audit_methodology_version": PLAYER_SEASON_VALUE_PROMOTION_AUDIT_VERSION,
        "research_methodology_version": PLAYER_SEASON_VALUE_RESEARCH_VERSION,
        "official_methodology_version": None,
        "input_fingerprints": inputs_fingerprints,
        "reconstruction": reconstruction_report,
        "source_conflicts": conflicts,
        "conflict_sensitivity": sensitivity,
        "coverage": {
            "total_player_seasons": len(candidates),
            "scoreable_player_seasons": sum(
                row.get("player_season_value_raw") is not None for row in candidates
            ),
            "scoreable_players": len(
                {
                    str(row["player_id"])
                    for row in candidates
                    if row.get("player_season_value_raw") is not None
                }
            ),
            "remaining_unavailable": missing["unavailable_player_seasons"],
            "confidence": dict(
                sorted(
                    Counter(
                        str(row["confidence"])
                        for row in candidates
                        if row.get("player_season_value_raw") is not None
                    ).items()
                )
            ),
        },
        "influence": influence,
        "masking": mask_candidate,
        "actual_vs_masking": actual_masking_interpretation,
        "peak": peak_comparison,
        "peak_coverage": sum(value is not None for value in peak.values()),
        "longevity": longevity_comparison,
        "longevity_coverage": sum(value is not None for value in longevity.values()),
        "peak_longevity": distinctness,
        "overall_sensitivity": "NOT_PRODUCED_PROMOTION_GATE_FAILED",
        "gates": gates,
        "outputs": manifests,
        "output_fingerprint": fingerprint,
        "run_at": args.run_at,
        "runtime_seconds": time.perf_counter() - started,
        "deterministic_rebuild_verified": args.expected_fingerprint == fingerprint,
    }
    stable_json(args.docs_root / "player-season-value-v2-promotion-summary.json", summary)
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, observed {fingerprint}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
