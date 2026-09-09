#!/usr/bin/env python3
"""Build the seven constitutional GOATLab V1 dimension scores offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from goatlab.features.dimension_candidates import era_group, spearman
from goatlab.models.structural_validation import (
    ScalingMethod,
    fit_pca,
    principal_axis_factor_analysis,
    scale_matrix,
)
from goatlab.rankings.dimension_scores import (
    DIMENSION_SCORE_METHODOLOGY_VERSION,
    DIMENSION_SCORE_RANDOM_SEED,
    Dimension,
    EvidenceConfidence,
    ScoreCoverage,
    best_contiguous_window,
    confidence_from_coverage,
    finite,
    joint_scoring_value,
    longevity_evidence,
    midrank_percentile_scores,
    peak_hybrid,
    playoff_hybrid,
    recognition_bundle,
    stronger_secondary_value,
    weighted_observed,
    winning_outcome_tier,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
NORMALIZATION_FINGERPRINT = "a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852"
CAREER_FINGERPRINT = "5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b"
AWARDS_FINGERPRINT = "666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258"
TEAM_FINGERPRINT = "707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333"
ACCOLADE_FINGERPRINT = "e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880"
CANDIDATE_FINGERPRINT = "e5cd648afbc36306251ec1229b4c9f2beba830ca0ce93056c8e783e596bfc11f"
STRUCTURAL_FINGERPRINT = "0f06e17c382de61a260dbd9eabb872a0613bf2c2146468c2a81bd454c4951093"
CORE_METRICS = ("ppg", "ts_pct", "apg", "rpg", "spg", "bpg", "points_per_75")
CASE_NBA_IDS = (
    "78049",
    "76375",
    "76003",
    "77142",
    "1449",
    "893",
    "165",
    "406",
    "1495",
    "977",
    "2544",
    "201939",
    "201142",
    "203999",
    "1112",
    "203497",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def stable_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    temporary.replace(path)


def read_entity(root: Path, columns: list[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        rows.extend(pq.ParquetFile(path).read(columns=columns).to_pylist())
    return rows


def write_parquet(
    rows: list[dict[str, Any]], path: Path, sort_fields: tuple[str, ...]
) -> dict[str, Any]:
    rows.sort(key=lambda row: tuple(str(row.get(field) or "") for field in sort_fields))
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
        "columns": table.num_columns,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def verify_inputs(args: argparse.Namespace) -> dict[str, str]:
    expected = {
        "historical-corpus-v1-manifest.json": CORPUS_FINGERPRINT,
        "era-normalization-gold-manifest.json": NORMALIZATION_FINGERPRINT,
        "career-gold-manifest.json": CAREER_FINGERPRINT,
        "award-canonicalization-summary.json": AWARDS_FINGERPRINT,
        "team-success-summary.json": TEAM_FINGERPRINT,
        "accolade-fact-completion-summary.json": ACCOLADE_FINGERPRINT,
        "dimension-candidate-summary.json": CANDIDATE_FINGERPRINT,
        "structural-validation-summary.json": STRUCTURAL_FINGERPRINT,
    }
    for name, fingerprint in expected.items():
        payload = json.loads((args.docs_root / name).read_text(encoding="utf-8"))
        discovered = {
            str(payload.get(key, ""))
            for key in (
                "corpus_fingerprint",
                "output_fingerprint",
                "career_output_fingerprint",
                "award_output_fingerprint",
                "career_fingerprint",
            )
        }
        if fingerprint not in discovered:
            raise ValueError(f"unexpected input fingerprint: {name}")
    constitution = ROOT / "docs/constitution/GOATLAB_V1_CONSTITUTION.md"
    if not constitution.is_file():
        raise FileNotFoundError(constitution)
    return {**expected, "constitution": file_sha256(constitution)}


def player_context(gold_root: Path) -> dict[str, dict[str, Any]]:
    return {str(row["player_id"]): row for row in read_entity(gold_root / "player_career_summary")}


def broad_reference(
    context: dict[str, dict[str, Any]], seasons: dict[tuple[str, int, str], dict[str, Any]]
) -> set[str]:
    # Freeze the STEP-0012 broad-high-recall reference exactly; this is a scaling
    # population, never a permanent player-eligibility gate.
    core_percentiles = tuple(f"{metric}_percentile" for metric in ("ppg", "rpg", "apg", "ts_pct"))
    reference: set[str] = set()
    for player_id, row in context.items():
        qualified = int(row["regular_qualified_seasons"])
        elite = any(
            any((season_row.get(metric) or -1.0) >= 0.90 for metric in core_percentiles)
            for season in range(
                int(row["regular_first_season"] or 1946),
                int(row["regular_last_season"] or 1945) + 1,
            )
            if (season_row := seasons.get((player_id, season, "REGULAR"), {}))
        )
        if qualified >= 3 or elite:
            reference.add(player_id)
    return reference


def load_normalized_seasons(gold_root: Path) -> dict[tuple[str, int, str], dict[str, Any]]:
    seasons: dict[tuple[str, int, str], dict[str, Any]] = defaultdict(dict)
    columns = [
        "player_id",
        "season_id",
        "season_type",
        "metric_name",
        "percentile",
        "z_score",
        "coverage_status",
        "qualification_status",
        "sample_size_games",
    ]
    for row in read_entity(gold_root / "player_season_feature_long", columns):
        metric = str(row["metric_name"])
        if metric not in CORE_METRICS or row["qualification_status"] != "QUALIFIED":
            continue
        if not str(row["coverage_status"]).startswith("AVAILABLE"):
            continue
        key = (str(row["player_id"]), int(row["season_id"]), str(row["season_type"]))
        seasons[key][f"{metric}_percentile"] = finite(row["percentile"])
        seasons[key][f"{metric}_z"] = finite(row["z_score"])
        seasons[key]["games"] = int(row["sample_size_games"])
    return dict(seasons)


def build_team_suppression(
    silver_root: Path, gold_root: Path
) -> tuple[dict[tuple[str, int], float], dict[tuple[str, int], dict[str, float]]]:
    team_by_season: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for row in read_entity(silver_root / "team_season_results"):
        if row["regular_games"] and row["point_diff_percentile"] is not None:
            rate = float(row["regular_points_against"]) / int(row["regular_games"])
            team_by_season[int(row["season_id"])].append((str(row["team_id"]), -rate))
    team_score: dict[tuple[str, int], float] = {}
    for season, rows in team_by_season.items():
        mapping = {team_id: value for team_id, value in rows}
        scaled = midrank_percentile_scores(mapping, set(mapping))
        for team_id, value in scaled.items():
            if value is not None:
                team_score[(team_id, season)] = value / 100.0

    player_values: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    coverage: dict[tuple[str, int], dict[str, float]] = defaultdict(
        lambda: {"regular_games": 0.0, "team_rows": 0.0}
    )
    for row in read_entity(gold_root / "player_team_success_primitives"):
        games = int(row["regular_games"])
        if games <= 0:
            continue
        key = (str(row["player_id"]), int(row["season_id"]))
        score = team_score.get((str(row["team_id"]), int(row["season_id"])))
        if score is not None:
            player_values[key].append((score, games))
            coverage[key]["regular_games"] += games
            coverage[key]["team_rows"] += 1
    output = {
        key: sum(value * weight for value, weight in values) / sum(weight for _, weight in values)
        for key, values in player_values.items()
    }
    return output, dict(coverage)


def enrich_season_values(
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    team_suppression: dict[tuple[str, int], float],
    *,
    scoring_volume_weight: float = 0.65,
    stronger_weight: float = 0.65,
) -> None:
    for (player_id, season, season_type), row in seasons.items():
        scoring = joint_scoring_value(
            row.get("ppg_percentile"),
            row.get("ts_pct_percentile"),
            volume_weight=scoring_volume_weight,
        )
        offense = stronger_secondary_value(
            scoring.value, row.get("apg_percentile"), stronger_weight=stronger_weight
        )
        actions = weighted_observed(
            {
                "rpg": row.get("rpg_percentile"),
                "spg": row.get("spg_percentile"),
                "bpg": row.get("bpg_percentile"),
            },
            {"rpg": 0.50, "spg": 0.25, "bpg": 0.25},
        )
        restricted_actions = weighted_observed({"rpg": row.get("rpg_percentile")}, {"rpg": 1.0})
        if season_type == "REGULAR":
            suppression = team_suppression.get((player_id, season))
            restricted_defense = weighted_observed(
                {"team_suppression": suppression, "rebound_context": restricted_actions.value},
                {"team_suppression": 0.65, "rebound_context": 0.35},
                required=("team_suppression",),
            )
            enriched_defense = weighted_observed(
                {"team_suppression": suppression, "individual_actions": actions.value},
                {"team_suppression": 0.65, "individual_actions": 0.35},
                required=("team_suppression",),
            )
        else:
            restricted_defense = restricted_actions
            enriched_defense = actions
        row["scoring_value"] = scoring.value
        row["scoring_coverage"] = scoring.weight_coverage
        row["offense_value"] = offense.value
        row["offense_coverage"] = (scoring.weight_coverage + offense.weight_coverage) / 2.0
        row["defense_restricted"] = restricted_defense.value
        row["defense_enriched"] = enriched_defense.value
        row["defense_restricted_coverage"] = restricted_defense.weight_coverage
        row["defense_enriched_coverage"] = enriched_defense.weight_coverage


def mean_by_player(
    seasons: dict[tuple[str, int, str], dict[str, Any]], season_type: str, field: str
) -> dict[str, float | None]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for (player_id, _, current_type), row in seasons.items():
        value = finite(row.get(field))
        if current_type == season_type and value is not None:
            grouped[player_id].append(value)
    return {player_id: statistics.fmean(values) for player_id, values in grouped.items()}


def defense_bridge(
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    context: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    restricted = mean_by_player(seasons, "REGULAR", "defense_restricted")
    enriched = mean_by_player(seasons, "REGULAR", "defense_enriched")
    overlap = sorted(
        player_id
        for player_id in restricted.keys() & enriched.keys()
        if context[player_id]["regular_last_season"] is not None
        and int(context[player_id]["regular_last_season"]) >= 1973
    )
    x = [float(restricted[player_id]) for player_id in overlap if restricted[player_id] is not None]
    y = [float(enriched[player_id]) for player_id in overlap if enriched[player_id] is not None]
    rho = spearman(x, y)
    median_delta = statistics.median(abs(a - b) for a, b in zip(x, y, strict=True)) if x else None
    passes = rho is not None and rho >= 0.80 and median_delta is not None and median_delta <= 0.15
    return {
        "bridge_name": "DEFENSE_RESTRICTED_TO_ACTION_ENRICHED",
        "overlap_players": len(overlap),
        "spearman": finite(rho),
        "median_absolute_raw_delta": finite(median_delta),
        "predeclared_thresholds": {"minimum_spearman": 0.80, "maximum_median_delta": 0.15},
        "passes": passes,
        "universal_action_evidence_selected": passes,
    }


def add_overall_season_quality(
    seasons: dict[tuple[str, int, str], dict[str, Any]], *, use_enriched_defense: bool
) -> None:
    defense_field = "defense_enriched" if use_enriched_defense else "defense_restricted"
    defense_coverage = (
        "defense_enriched_coverage" if use_enriched_defense else "defense_restricted_coverage"
    )
    for row in seasons.values():
        combined = stronger_secondary_value(row.get("offense_value"), row.get(defense_field))
        row["overall_quality_raw"] = combined.value
        row["overall_input_coverage"] = statistics.fmean(
            (
                float(row.get("offense_coverage") or 0.0),
                float(row.get(defense_coverage) or 0.0),
            )
        )
    grouped: dict[tuple[int, str], dict[str, float | None]] = defaultdict(dict)
    for (player_id, season, season_type), row in seasons.items():
        grouped[(season, season_type)][player_id] = finite(row.get("overall_quality_raw"))
    for (season, season_type), values in grouped.items():
        percentiles = midrank_percentile_scores(values, set(values))
        for player_id, score in percentiles.items():
            seasons[(player_id, season, season_type)]["overall_quality_percentile"] = (
                score / 100.0 if score is not None else None
            )


def calibrate_longevity_threshold(
    seasons: dict[tuple[str, int, str], dict[str, Any]], silver_root: Path
) -> tuple[float, list[dict[str, Any]]]:
    all_nba = {
        (str(row["player_id"]), int(row["season_id"]))
        for row in read_entity(silver_root / "player_awards")
        if row["award_type"] == "ALL_NBA" and row["season_id"] is not None
    }
    candidates = (0.80, 0.85, 0.90, 0.95)
    observed = [
        (player_id, season, float(row["overall_quality_percentile"]))
        for (player_id, season, season_type), row in seasons.items()
        if season_type == "REGULAR" and row.get("overall_quality_percentile") is not None
    ]
    records: list[dict[str, Any]] = []
    for threshold in candidates:
        selected = [
            value >= threshold
            for player_id, season, value in observed
            if (player_id, season) in all_nba
        ]
        not_selected = [
            value >= threshold
            for player_id, season, value in observed
            if (player_id, season) not in all_nba
        ]
        sensitivity = sum(selected) / len(selected) if selected else 0.0
        specificity = 1.0 - sum(not_selected) / len(not_selected) if not_selected else 0.0
        records.append(
            {
                "threshold": threshold,
                "all_nba_seasons_observed": len(selected),
                "all_nba_at_or_above": sum(selected),
                "all_nba_capture_rate": finite(sensitivity),
                "non_all_nba_below_rate": finite(specificity),
                "calibration_youden_j": finite(sensitivity + specificity - 1.0),
                "award_role": "CALIBRATION_ONLY_NOT_FORMULA_INPUT",
            }
        )
    selected_record = max(
        records, key=lambda row: (float(row["calibration_youden_j"]), -float(row["threshold"]))
    )
    return float(selected_record["threshold"]), records


def scale_component(
    values: dict[str, float | None], reference: set[str]
) -> dict[str, float | None]:
    return midrank_percentile_scores(values, reference)


def build_peak(
    players: list[str],
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    reference: set[str],
    weight_three: float,
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]]]:
    raw: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    by_player: dict[str, dict[int, float | None]] = defaultdict(dict)
    coverage: dict[str, list[float]] = defaultdict(list)
    for (player_id, season, season_type), row in seasons.items():
        if season_type != "REGULAR":
            continue
        by_player[player_id][season] = finite(row.get("overall_quality_percentile"))
        if row.get("overall_quality_percentile") is not None:
            coverage[player_id].append(float(row.get("overall_input_coverage") or 0.0))
    for player_id in players:
        window = best_contiguous_window(by_player.get(player_id, {}), 3)
        values = [value for value in by_player.get(player_id, {}).values() if value is not None]
        apex = max(values) if values else None
        raw[player_id] = peak_hybrid(window.value, apex, weight_three)
        details[player_id] = {
            "three_year_value": finite(window.value),
            "three_year_start": window.start_season,
            "three_year_end": window.end_season,
            "apex_value": finite(apex),
            "relevant_seasons": 3 if window.value is not None else len(values),
            "component_coverage": statistics.fmean(coverage[player_id])
            if coverage[player_id]
            else 0.0,
        }
    return scale_component(raw, reference), {
        player_id: {**details[player_id], "raw": raw[player_id]} for player_id in players
    }


def build_longevity(
    players: list[str],
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    reference: set[str],
    threshold: float,
    weights: tuple[float, float, float],
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]]]:
    per_player: dict[str, dict[int, float | None]] = defaultdict(dict)
    for (player_id, season, season_type), row in seasons.items():
        if season_type == "REGULAR":
            per_player[player_id][season] = finite(row.get("overall_quality_percentile"))
    cap = min(0.99, threshold + 0.10)
    evidence = {
        player_id: longevity_evidence(per_player.get(player_id, {}), threshold=threshold, cap=cap)
        for player_id in players
    }
    breadth = {player_id: float(item.breadth) for player_id, item in evidence.items()}
    area = {player_id: item.capped_area for player_id, item in evidence.items()}
    persistence = {player_id: float(item.longest_run) for player_id, item in evidence.items()}
    scaled = {
        "breadth": scale_component(breadth, reference),
        "capped_area": scale_component(area, reference),
        "persistence": scale_component(persistence, reference),
    }
    raw: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    for player_id in players:
        item = evidence[player_id]
        relevant = len(
            [value for value in per_player.get(player_id, {}).values() if value is not None]
        )
        combined = weighted_observed(
            {name: scaled[name][player_id] for name in scaled},
            dict(zip(("breadth", "capped_area", "persistence"), weights, strict=True)),
        )
        raw[player_id] = combined.value if relevant else None
        details[player_id] = {
            "raw": raw[player_id],
            "threshold": threshold,
            "cap": cap,
            "elite_season_breadth": item.breadth,
            "capped_elite_area": finite(item.capped_area),
            "longest_elite_run": item.longest_run,
            "first_elite_season": item.first_elite_season,
            "last_elite_season": item.last_elite_season,
            "relevant_seasons": relevant,
            "component_coverage": combined.weight_coverage,
        }
    return scale_component(raw, reference), details


def build_offense(
    players: list[str], seasons: dict[tuple[str, int, str], dict[str, Any]], reference: set[str]
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]]]:
    values: dict[str, list[float]] = defaultdict(list)
    coverage: dict[str, list[float]] = defaultdict(list)
    for (player_id, _, season_type), row in seasons.items():
        value = finite(row.get("offense_value"))
        if season_type == "REGULAR" and value is not None:
            values[player_id].append(value)
            coverage[player_id].append(float(row.get("offense_coverage") or 0.0))
    raw = {
        player_id: statistics.fmean(values[player_id]) if values[player_id] else None
        for player_id in players
    }
    scores = scale_component(raw, reference)
    details = {
        player_id: {
            "raw": raw[player_id],
            "relevant_seasons": len(values[player_id]),
            "component_coverage": statistics.fmean(coverage[player_id])
            if coverage[player_id]
            else 0.0,
            "scoring_value_formula": "0.65*PPG_percentile + 0.35*TS_percentile; PPG required",
            "axis_formula": "0.65*stronger_axis + 0.35*secondary_axis",
        }
        for player_id in players
    }
    return scores, details


def build_defense(
    players: list[str],
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    reference: set[str],
    *,
    enriched: bool,
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]]]:
    field = "defense_enriched" if enriched else "defense_restricted"
    coverage_field = "defense_enriched_coverage" if enriched else "defense_restricted_coverage"
    values: dict[str, list[float]] = defaultdict(list)
    coverage: dict[str, list[float]] = defaultdict(list)
    for (player_id, _, season_type), row in seasons.items():
        value = finite(row.get(field))
        if season_type == "REGULAR" and value is not None:
            values[player_id].append(value)
            coverage[player_id].append(float(row.get(coverage_field) or 0.0))
    raw = {
        player_id: statistics.fmean(values[player_id]) if values[player_id] else None
        for player_id in players
    }
    scores = scale_component(raw, reference)
    details = {
        player_id: {
            "raw": raw[player_id],
            "relevant_seasons": len(values[player_id]),
            "component_coverage": statistics.fmean(coverage[player_id])
            if coverage[player_id]
            else 0.0,
            "evidence_model": "TEAM_SUPPRESSION_PLUS_REBOUND_STEAL_BLOCK_ACTIONS"
            if enriched
            else "TEAM_SUPPRESSION_PLUS_REBOUND_CONTEXT",
        }
        for player_id in players
    }
    return scores, details


def build_playoffs(
    players: list[str],
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    context: dict[str, dict[str, Any]],
    reference: set[str],
    weights: tuple[float, float, float],
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]]]:
    playoff_values: dict[str, list[tuple[int, float]]] = defaultdict(list)
    regular_values: dict[tuple[str, int], float] = {}
    coverage: dict[str, list[float]] = defaultdict(list)
    for (player_id, season, season_type), row in seasons.items():
        value = finite(row.get("overall_quality_percentile"))
        if value is None:
            continue
        if season_type == "PLAYOFF":
            playoff_values[player_id].append((season, value))
            coverage[player_id].append(float(row.get("overall_input_coverage") or 0.0))
        else:
            regular_values[(player_id, season)] = value
    absolute_raw: dict[str, float | None] = {}
    resilience_raw: dict[str, float | None] = {}
    repeated_raw: dict[str, float | None] = {}
    for player_id in players:
        values = playoff_values[player_id]
        absolute_raw[player_id] = statistics.fmean(value for _, value in values) if values else None
        deltas = [
            value - regular_values[(player_id, season)]
            for season, value in values
            if (player_id, season) in regular_values
        ]
        # Retention/lift is bounded around neutral retention. It cannot become the primary signal.
        resilience_raw[player_id] = (
            min(1.0, max(0.0, 0.5 + statistics.fmean(deltas))) if deltas else None
        )
        eligible = [value for _, value in values if value >= 0.80]
        repeated_raw[player_id] = sum(min(0.20, value - 0.80) / 0.20 for value in eligible)
    absolute = scale_component(absolute_raw, reference)
    resilience = scale_component(resilience_raw, reference)
    repeated = scale_component(repeated_raw, reference)
    raw: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    for player_id in players:
        combined = playoff_hybrid(
            absolute[player_id], resilience[player_id], repeated[player_id], weights=weights
        )
        raw[player_id] = combined.value
        details[player_id] = {
            "raw": combined.value,
            "absolute_component": absolute[player_id],
            "resilience_component": resilience[player_id],
            "repeated_component": repeated[player_id],
            "relevant_seasons": len(playoff_values[player_id]),
            "relevant_games": int(context[player_id]["playoff_games"]),
            "component_coverage": combined.weight_coverage,
            "opponent_difficulty_status": "DIAGNOSTIC_NOT_ADDITIVE_V1",
        }
    return scale_component(raw, reference), details


def build_accolades(
    players: list[str],
    context: dict[str, dict[str, Any]],
    silver_root: Path,
    gold_root: Path,
    reference: set[str],
    weights: tuple[float, float, float],
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]], dict[str, Any]]:
    status = {
        str(row["player_id"]): str(row["award_acquisition_status"])
        for row in read_entity(gold_root / "player_career_accolades_complete")
    }
    events: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in read_entity(silver_root / "player_awards"):
        if row["season_id"] is not None:
            events[(str(row["player_id"]), int(row["season_id"]))].append(row)
    all_star = {
        (str(row["player_id"]), int(row["season_id"]))
        for row in read_entity(silver_root / "player_all_star_evidence")
        if row["playerawards_evidence"]
        or (row["roster_evidence"] and int(row["season_id"]) != 2024)
    }
    titles: Counter[tuple[str, int]] = Counter()
    for row in read_entity(silver_root / "player_stat_leaders"):
        if row["official_source_rank"] == 1:
            titles[(str(row["player_id"]), int(row["season_id"]))] += 1

    major_raw: dict[str, float | None] = {}
    sustained_raw: dict[str, float | None] = {}
    support_raw: dict[str, float | None] = {}
    season_details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    queried = {
        player_id
        for player_id in players
        if status.get(player_id) in {"SUCCESS_WITH_ROWS", "SUCCESS_EMPTY"}
    }
    for player_id in players:
        if player_id not in queried:
            major_raw[player_id] = sustained_raw[player_id] = support_raw[player_id] = None
            continue
        first = int(context[player_id]["regular_first_season"] or 1946)
        last = int(context[player_id]["regular_last_season"] or first)
        major_total = sustained_total = support_total = 0.0
        for season in range(first, last + 1):
            rows = events.get((player_id, season), [])
            major_signals = [
                {"MVP": 1.0, "FINALS_MVP": 0.75, "DPOY": 0.65}[str(row["award_type"])]
                for row in rows
                if str(row["award_type"]) in {"MVP", "FINALS_MVP", "DPOY"}
            ]
            all_nba = max(
                (
                    {"FIRST": 1.0, "SECOND": 0.75, "THIRD": 0.55}.get(str(row["award_level"]), 0.0)
                    for row in rows
                    if row["award_type"] == "ALL_NBA"
                ),
                default=0.0,
            )
            all_defense = max(
                (
                    {"FIRST": 0.65, "SECOND": 0.45}.get(str(row["award_level"]), 0.0)
                    for row in rows
                    if row["award_type"] == "ALL_DEFENSE"
                ),
                default=0.0,
            )
            all_star_signal = 0.30 if (player_id, season) in all_star else 0.0
            major = recognition_bundle(major_signals, cap=1.25)
            sustained_before_major_cap = recognition_bundle(
                [value for value in (all_nba, all_defense, all_star_signal) if value > 0.0],
                cap=1.15,
            )
            # Major and sustained honors remain separate constitutional axes, but related
            # recognition from one season cannot receive two uncapped full votes.
            sustained = (
                min(sustained_before_major_cap, 0.50) if major > 0.0 else sustained_before_major_cap
            )
            support = min(1.0, titles[(player_id, season)] / 2.0)
            major_total += major
            sustained_total += sustained
            support_total += support
            if major or sustained or support:
                season_details[player_id].append(
                    {
                        "season_id": season,
                        "major_bundle": major,
                        "sustained_bundle_before_major_cap": sustained_before_major_cap,
                        "sustained_bundle": sustained,
                        "support_bundle": support,
                    }
                )
        major_raw[player_id] = major_total
        sustained_raw[player_id] = sustained_total
        support_raw[player_id] = support_total
    queried_reference = reference & queried
    major = scale_component(major_raw, queried_reference)
    sustained = scale_component(sustained_raw, queried_reference)
    support = scale_component(support_raw, queried_reference)
    raw: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    for player_id in players:
        if player_id not in queried:
            raw[player_id] = None
            details[player_id] = {
                "raw": None,
                "relevant_seasons": 0,
                "component_coverage": 0.0,
                "award_acquisition_status": status.get(player_id, "NOT_QUERIED"),
                "same_season_bundle_count": 0,
            }
            continue
        combined = weighted_observed(
            {
                "major_honors": major[player_id],
                "sustained_recognition": sustained[player_id],
                "supporting_titles": support[player_id],
            },
            dict(
                zip(
                    ("major_honors", "sustained_recognition", "supporting_titles"),
                    weights,
                    strict=True,
                )
            ),
            required=("major_honors", "sustained_recognition"),
        )
        raw[player_id] = combined.value
        details[player_id] = {
            "raw": combined.value,
            "major_honors_component": major[player_id],
            "sustained_recognition_component": sustained[player_id],
            "supporting_titles_component": support[player_id],
            "relevant_seasons": int(context[player_id]["regular_seasons_appeared"]),
            "component_coverage": combined.weight_coverage,
            "award_acquisition_status": status[player_id],
            "same_season_bundle_count": len(season_details[player_id]),
        }
    audit = {
        "queried_players": len(queried),
        "not_queried_players": len(players) - len(queried),
        "major_season_bundles": sum(
            row["major_bundle"] > 0 for rows in season_details.values() for row in rows
        ),
        "sustained_season_bundles": sum(
            row["sustained_bundle"] > 0 for rows in season_details.values() for row in rows
        ),
        "cross_axis_same_season_caps": sum(
            row["sustained_bundle"] < row["sustained_bundle_before_major_cap"]
            for rows in season_details.values()
            for row in rows
        ),
        "champion_events_used": 0,
        "unanimous_mvp_bonus_used": False,
        "statistical_title_weight": weights[2],
    }
    return scale_component(raw, queried_reference), details, audit


def build_winning(
    players: list[str],
    context: dict[str, dict[str, Any]],
    gold_root: Path,
    reference: set[str],
    weights: tuple[float, float, float],
) -> tuple[dict[str, float | None], dict[str, dict[str, Any]], dict[str, Any]]:
    outcomes: dict[tuple[str, int], list[tuple[float, str]]] = defaultdict(list)
    elite_team: dict[tuple[str, int], list[float]] = defaultdict(list)
    playoff_seasons: set[tuple[str, int]] = set()
    for row in read_entity(gold_root / "player_team_success_primitives"):
        player_id = str(row["player_id"])
        season = int(row["season_id"])
        playoff = int(row["playoff_games"]) > 0
        champion = bool(row["played_finals_for_champion_team"])
        finalist = bool(row["team_finalist"]) and int(row["finals_games"]) > 0
        tier, value = winning_outcome_tier(
            champion_finals_participant=champion,
            finalist_participant=finalist,
            playoff_participant=playoff,
            series_won=int(row["team_series_won"]) if row["team_series_won"] is not None else None,
        )
        share = finite(
            row["finals_game_share"] if champion or finalist else row["playoff_game_share"]
        )
        if value > 0.0:
            modifier = 0.75 + 0.25 * (share if share is not None else 1.0)
            outcomes[(player_id, season)].append((value * modifier, tier))
            playoff_seasons.add((player_id, season))
        win_pct = finite(row["team_win_pct_percentile"])
        regular_share = finite(row["regular_game_share"])
        if win_pct is not None and regular_share is not None and win_pct >= 0.80:
            quality = min(1.0, (win_pct - 0.80) / 0.20)
            elite_team[(player_id, season)].append(quality * (0.75 + 0.25 * regular_share))
    outcome_raw: dict[str, float | None] = {}
    elite_raw: dict[str, float | None] = {}
    breadth_raw: dict[str, float | None] = {}
    tier_counts: Counter[str] = Counter()
    selected_outcomes: dict[str, list[float]] = defaultdict(list)
    for (player_id, _), values in outcomes.items():
        selected = max(values, key=lambda item: (item[0], item[1]))
        selected_outcomes[player_id].append(selected[0])
        tier_counts[selected[1]] += 1
    selected_elite: dict[str, list[float]] = defaultdict(list)
    for (player_id, _), values in elite_team.items():
        selected_elite[player_id].append(max(values))
    playoff_breadth = Counter(player_id for player_id, _ in playoff_seasons)
    for player_id in players:
        if int(context[player_id]["regular_seasons_appeared"]) == 0:
            outcome_raw[player_id] = elite_raw[player_id] = breadth_raw[player_id] = None
        else:
            outcome_raw[player_id] = sum(selected_outcomes[player_id])
            elite_raw[player_id] = sum(selected_elite[player_id])
            breadth_raw[player_id] = float(playoff_breadth[player_id])
    outcome = scale_component(outcome_raw, reference)
    elite = scale_component(elite_raw, reference)
    breadth = scale_component(breadth_raw, reference)
    raw: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    for player_id in players:
        combined = weighted_observed(
            {
                "hierarchical_outcomes": outcome[player_id],
                "sustained_elite_teams": elite[player_id],
                "playoff_breadth": breadth[player_id],
            },
            dict(
                zip(
                    ("hierarchical_outcomes", "sustained_elite_teams", "playoff_breadth"),
                    weights,
                    strict=True,
                )
            ),
        )
        raw[player_id] = combined.value
        details[player_id] = {
            "raw": combined.value,
            "hierarchical_outcome_component": outcome[player_id],
            "sustained_elite_team_component": elite[player_id],
            "playoff_breadth_component": breadth[player_id],
            "relevant_seasons": int(context[player_id]["regular_seasons_appeared"]),
            "relevant_games": int(context[player_id]["regular_total_games"]),
            "component_coverage": combined.weight_coverage,
            "path_difficulty_status": "BOUNDED_CONTEXT_DEFERRED_NO_PLAYER_PATH_MODEL",
            "generic_wowy_used": False,
        }
    return (
        scale_component(raw, reference),
        details,
        {
            "season_outcome_tier_counts": dict(sorted(tier_counts.items())),
            "within_season_tiers_are_mutually_exclusive": True,
            "official_champion_awards_used": False,
            "generic_wowy_used": False,
        },
    )


def rank_audit(
    selected: dict[str, float | None],
    alternative: dict[str, float | None],
    context: dict[str, dict[str, Any]],
    archetypes: dict[str, int],
    top_sizes: tuple[int, ...] = (25, 50, 100),
) -> dict[str, Any]:
    shared = sorted(
        player_id
        for player_id in selected
        if selected[player_id] is not None and alternative.get(player_id) is not None
    )
    left = [float(selected[player_id]) for player_id in shared]
    right = [float(alternative[player_id]) for player_id in shared]
    result: dict[str, Any] = {
        "shared_players": len(shared),
        "spearman": finite(spearman(left, right)),
        "mean_absolute_score_change": finite(
            statistics.fmean(abs(a - b) for a, b in zip(left, right, strict=True))
        )
        if shared
        else None,
        "top_n_overlap": {},
        "missingness_sensitivity": {
            "selected_available": sum(value is not None for value in selected.values()),
            "alternative_available": sum(value is not None for value in alternative.values()),
            "both_available": len(shared),
            "selected_only": sum(
                value is not None and alternative.get(player_id) is None
                for player_id, value in selected.items()
            ),
            "alternative_only": sum(
                value is not None and selected.get(player_id) is None
                for player_id, value in alternative.items()
            ),
        },
        "position_bias_status": "UNAVAILABLE_POSITION_COVERAGE_NOT_QUALIFIED",
    }

    def grouped_change(labels: dict[str, str]) -> dict[str, dict[str, float | int | None]]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for player_id in shared:
            grouped[labels.get(player_id, "UNKNOWN")].append(
                abs(float(selected[player_id]) - float(alternative[player_id]))
            )
        return {
            label: {
                "players": len(values),
                "mean_absolute_score_change": finite(statistics.fmean(values)),
            }
            for label, values in sorted(grouped.items())
        }

    result["active_career_sensitivity"] = grouped_change(
        {player_id: str(row["career_status"]) for player_id, row in context.items()}
    )
    result["era_sensitivity"] = grouped_change(
        {
            player_id: era_group(
                int(row["regular_first_season"])
                if row["regular_first_season"] is not None
                else None
            )
            for player_id, row in context.items()
        }
    )
    result["archetype_sensitivity"] = grouped_change(
        {player_id: f"PROFILE_{cluster}" for player_id, cluster in archetypes.items()}
    )

    def ranks(values: dict[str, float | None]) -> dict[str, float]:
        ordered = sorted(
            ((player_id, float(values[player_id])) for player_id in shared),
            key=lambda item: (-item[1], item[0]),
        )
        output: dict[str, float] = {}
        start = 0
        while start < len(ordered):
            end = start + 1
            while end < len(ordered) and ordered[end][1] == ordered[start][1]:
                end += 1
            midrank = (start + 1 + end) / 2.0
            for index in range(start, end):
                output[ordered[index][0]] = midrank
            start = end
        return output

    selected_ranks = ranks(selected)
    alternative_ranks = ranks(alternative)
    movers = sorted(
        shared,
        key=lambda player_id: (
            -abs(alternative_ranks[player_id] - selected_ranks[player_id]),
            player_id,
        ),
    )[:10]
    result["largest_rank_movers"] = [
        {
            "player_id": player_id,
            "display_name": context[player_id]["display_name"],
            "career_status": context[player_id]["career_status"],
            "debut_era": era_group(
                int(context[player_id]["regular_first_season"])
                if context[player_id]["regular_first_season"] is not None
                else None
            ),
            "archetype": (
                f"PROFILE_{archetypes[player_id]}" if player_id in archetypes else "UNKNOWN"
            ),
            "selected_score": finite(selected[player_id]),
            "alternative_score": finite(alternative[player_id]),
            "selected_rank": finite(selected_ranks[player_id]),
            "alternative_rank": finite(alternative_ranks[player_id]),
            "absolute_rank_change": finite(
                abs(alternative_ranks[player_id] - selected_ranks[player_id])
            ),
        }
        for player_id in movers
    ]
    for size in top_sizes:
        actual = min(size, len(shared))
        first = {
            player_id
            for player_id in sorted(shared, key=lambda item: (-float(selected[item]), item))[
                :actual
            ]
        }
        second = {
            player_id
            for player_id in sorted(shared, key=lambda item: (-float(alternative[item]), item))[
                :actual
            ]
        }
        result["top_n_overlap"][str(size)] = (
            finite(len(first & second) / actual) if actual else None
        )
    return result


def partial_correlation(values: np.ndarray, left: int, right: int) -> float | None:
    controls = [index for index in range(values.shape[1]) if index not in {left, right}]
    design = np.column_stack((np.ones(values.shape[0]), values[:, controls]))
    left_residual = (
        values[:, left] - design @ np.linalg.lstsq(design, values[:, left], rcond=None)[0]
    )
    right_residual = (
        values[:, right] - design @ np.linalg.lstsq(design, values[:, right], rcond=None)[0]
    )
    denominator = float(np.linalg.norm(left_residual) * np.linalg.norm(right_residual))
    return (
        float(np.dot(left_residual, right_residual) / denominator) if denominator > 1e-12 else None
    )


def structural_audit(
    scores: dict[str, dict[str, float | None]], context: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    dimensions = tuple(dimension.value for dimension in Dimension)
    complete = sorted(
        player_id
        for player_id in context
        if all(scores[dimension][player_id] is not None for dimension in dimensions)
    )
    matrix = np.asarray(
        [
            [float(scores[dimension][player_id]) for dimension in dimensions]
            for player_id in complete
        ],
        dtype=np.float64,
    )
    if matrix.shape[0] < 3:
        raise ValueError("insufficient complete seven-dimension population")
    pearson_matrix = np.corrcoef(matrix, rowvar=False)
    spearman_matrix = np.asarray(
        [
            [
                float(spearman(matrix[:, left].tolist(), matrix[:, right].tolist()) or 0.0)
                for right in range(len(dimensions))
            ]
            for left in range(len(dimensions))
        ],
        dtype=np.float64,
    )
    partial = np.empty((len(dimensions), len(dimensions)), dtype=np.float64)
    for left in range(len(dimensions)):
        for right in range(len(dimensions)):
            partial[left, right] = (
                1.0 if left == right else float(partial_correlation(matrix, left, right) or 0.0)
            )
    scaled = scale_matrix(matrix, ScalingMethod.STANDARD).values
    pca = fit_pca(scaled)
    factor_count = min(4, len(dimensions) - 1)
    factors = principal_axis_factor_analysis(scaled, factor_count)
    uniqueness = []
    for index, dimension in enumerate(dimensions):
        others = [other for other in range(len(dimensions)) if other != index]
        design = np.column_stack((np.ones(matrix.shape[0]), matrix[:, others]))
        predicted = design @ np.linalg.lstsq(design, matrix[:, index], rcond=None)[0]
        total = float(np.sum((matrix[:, index] - np.mean(matrix[:, index])) ** 2))
        residual = float(np.sum((matrix[:, index] - predicted) ** 2))
        r_squared = 1.0 - residual / total if total > 0 else None
        uniqueness.append(
            {
                "dimension": dimension,
                "multiple_r_squared_other_dimensions": finite(r_squared),
                "residual_variance_fraction": finite(1.0 - r_squared)
                if r_squared is not None
                else None,
            }
        )

    generator = random.Random(DIMENSION_SCORE_RANDOM_SEED)
    equal = np.mean(matrix, axis=1)
    sample_spearman: list[float] = []
    top50: list[float] = []
    equal_order = np.argsort(-equal)[: min(50, len(equal))]
    equal_top = set(equal_order.tolist())
    for _ in range(500):
        draws = [-math.log(max(generator.random(), 1e-15)) for _ in dimensions]
        weights = np.asarray(draws) / sum(draws)
        combined = matrix @ weights
        rho = spearman(equal.tolist(), combined.tolist())
        if rho is not None:
            sample_spearman.append(rho)
        current = set(np.argsort(-combined)[: min(50, len(combined))].tolist())
        top50.append(len(current & equal_top) / max(1, len(equal_top)))
    return {
        "complete_players": len(complete),
        "dimensions": list(dimensions),
        "pearson_matrix": [[finite(value) for value in row] for row in pearson_matrix.tolist()],
        "spearman_matrix": [[finite(value) for value in row] for row in spearman_matrix.tolist()],
        "partial_correlation_matrix": [
            [finite(value) for value in row] for row in partial.tolist()
        ],
        "pca_explained_variance_ratio": [
            finite(value) for value in pca.explained_variance_ratio.tolist()
        ],
        "factor_count_diagnostic": factor_count,
        "factor_rotated_loadings": [
            {
                "dimension": dimension,
                "loadings": [finite(value) for value in factors.rotated_loadings[index].tolist()],
            }
            for index, dimension in enumerate(dimensions)
        ],
        "incremental_uniqueness": uniqueness,
        "random_simplex_weight_audit": {
            "samples": 500,
            "seed": DIMENSION_SCORE_RANDOM_SEED,
            "reference": "EXPLORATORY_EQUAL_WEIGHT_ONLY_NOT_OFFICIAL",
            "mean_spearman_to_equal_weight": finite(statistics.fmean(sample_spearman)),
            "minimum_spearman_to_equal_weight": finite(min(sample_spearman)),
            "mean_top_50_overlap": finite(statistics.fmean(top50)),
            "minimum_top_50_overlap": finite(min(top50)),
            "official_overall_weights_selected": False,
        },
    }


def modern_bridge_audit(
    scores: dict[str, dict[str, float | None]],
    seasons: dict[tuple[str, int, str], dict[str, Any]],
    context: dict[str, dict[str, Any]],
    reference: set[str],
    defense_result: dict[str, Any],
    gold_root: Path,
    silver_root: Path,
) -> dict[str, Any]:
    modern_offense_values: dict[str, list[float]] = defaultdict(list)
    for (player_id, _, season_type), row in seasons.items():
        if season_type != "REGULAR" or row.get("points_per_75_percentile") is None:
            continue
        scoring = joint_scoring_value(
            row.get("points_per_75_percentile"), row.get("ts_pct_percentile")
        )
        enriched = stronger_secondary_value(scoring.value, row.get("apg_percentile"))
        if enriched.value is not None:
            modern_offense_values[player_id].append(enriched.value)
    modern_offense_raw = {
        player_id: statistics.fmean(values) for player_id, values in modern_offense_values.items()
    }
    modern_offense = scale_component(modern_offense_raw, reference)

    advanced_by_season: dict[int, dict[str, float]] = defaultdict(dict)
    for row in read_entity(silver_root / "player_season_advanced"):
        if (
            row["season_type"] == "REGULAR"
            and row["row_scope"] == "TOTAL"
            and row["defensive_rating"] is not None
        ):
            advanced_by_season[int(row["season_id"])][str(row["player_id"])] = -float(
                row["defensive_rating"]
            )
    advanced_values: dict[str, list[float]] = defaultdict(list)
    for _, values in advanced_by_season.items():
        scaled = midrank_percentile_scores(values, set(values))
        for player_id, value in scaled.items():
            if value is not None:
                advanced_values[player_id].append(value / 100.0)
    advanced_raw = {
        player_id: statistics.fmean(values) for player_id, values in advanced_values.items()
    }
    advanced_defense = scale_component(advanced_raw, reference)

    def compare(
        universal: dict[str, float | None], enriched: dict[str, float | None], name: str
    ) -> dict[str, Any]:
        shared = sorted(
            player_id
            for player_id in universal
            if universal[player_id] is not None and enriched.get(player_id) is not None
        )
        x = np.asarray([float(universal[player_id]) for player_id in shared])
        y = np.asarray([float(enriched[player_id]) for player_id in shared])
        design = np.column_stack((np.ones(len(shared)), x))
        prediction = design @ np.linalg.lstsq(design, y, rcond=None)[0]
        total = float(np.sum((y - np.mean(y)) ** 2))
        residual = float(np.sum((y - prediction) ** 2))
        residuals = y - prediction
        eras: dict[str, list[float]] = defaultdict(list)
        for player_id, value in zip(shared, residuals.tolist(), strict=True):
            eras[era_group(context[player_id]["regular_first_season"])].append(value)
        return {
            "bridge": name,
            "overlap_players": len(shared),
            "spearman": finite(spearman(x.tolist(), y.tolist())),
            "pearson": finite(float(np.corrcoef(x, y)[0, 1])) if len(shared) > 1 else None,
            "linear_r_squared": finite(1.0 - residual / total) if total > 0 else None,
            "median_absolute_residual": finite(
                statistics.median(abs(value) for value in residuals.tolist())
            )
            if shared
            else None,
            "mean_residual_by_debut_era": {
                key: finite(statistics.fmean(values)) for key, values in sorted(eras.items())
            },
            "position_bias_status": "UNAVAILABLE_POSITION_COVERAGE_NOT_QUALIFIED",
            "archetype_bias_status": "DESCRIPTIVE_ONLY_STEP_0013_COARSE_CLUSTERS",
            "universal_score_changed": False,
        }

    return {
        "defense_restricted_action_bridge": defense_result,
        "modern_offense_bridge": compare(
            scores["OFFENSE"], modern_offense, "UNIVERSAL_OFFENSE_VS_PER75_ENRICHMENT"
        ),
        "modern_defense_bridge": compare(
            scores["DEFENSE"], advanced_defense, "UNIVERSAL_DEFENSE_VS_ADVANCED_DEF_RATING"
        ),
        "policy": (
            "Modern enrichment remains diagnostic in V1 even when correlated; "
            "no modern-only bonus is applied."
        ),
    }


def formula_registry(threshold: float, defense_enriched: bool) -> dict[str, Any]:
    common = {
        "score_scale": "0-100 midrank ECDF against BROAD_HIGH_RECALL observed reference",
        "scale_interpretation": {
            "0": "bottom observed reference value (ties share their midrank)",
            "50": "approximately the observed reference median",
            "90": "approximately the 90th percentile",
            "95": "approximately the 95th percentile",
            "99": "approximately the 99th percentile",
            "100": "top observed reference value (ties share their midrank)",
        },
        "missingness": (
            "NULL is retained; explicit available-evidence renormalization never inserts zero"
        ),
        "confidence_is_not_quality": True,
        "modern_only_features_in_universal_scores": False,
    }
    formulas = [
        {
            "dimension": "PEAK",
            "question": "How high was the player's best sustained level?",
            "formula": (
                "0.70 * best contiguous 3-season overall-quality percentile + "
                "0.30 * best single-season apex"
            ),
            "primary_evidence": [
                "REGULAR season overall quality",
                "complete contiguous three-season window",
            ],
            "excluded": ["awards", "team outcomes", "postseason", "five-year mandatory anchor"],
        },
        {
            "dimension": "LONGEVITY",
            "question": "How long did the player remain genuinely great?",
            "formula": (
                "0.35 * elite breadth + 0.40 * capped area + 0.25 * longest run "
                f"at season-quality percentile >= {threshold:.2f}; season credit capped "
                f"at {min(0.99, threshold + 0.10):.2f}"
            ),
            "primary_evidence": [
                "REGULAR season quality",
                "thresholded breadth",
                "capped area",
                "contiguous persistence",
            ],
            "excluded": [
                "career length alone",
                "career average",
                "All-NBA as score input",
                "uncapped apex magnitude",
            ],
        },
        {
            "dimension": "OFFENSE",
            "question": "How much offensive value did the player create?",
            "formula": (
                "career mean of Global Value Creation: joint Scoring Value "
                "(0.65 PPG + 0.35 TS when available, PPG required), then 0.65 "
                "stronger offensive axis + 0.35 secondary axis versus creation/APG"
            ),
            "primary_evidence": [
                "REGULAR PPG percentile",
                "REGULAR TS percentile",
                "REGULAR APG percentile",
            ],
            "excluded": ["postseason", "statistical titles", "modern per-75 universal bonus"],
        },
        {
            "dimension": "DEFENSE",
            "question": "How much opponent offensive value did the player help prevent?",
            "formula": (
                "career mean of 0.65 era-relative team scoring suppression + "
                "0.35 individual action context"
            )
            if defense_enriched
            else "career mean of 0.65 era-relative team scoring suppression + 0.35 rebound context",
            "primary_evidence": [
                "REGULAR opponent scoring suppression while affiliated",
                "rebound context",
            ]
            + (["steal context", "block context"] if defense_enriched else []),
            "excluded": [
                "DPOY",
                "All-Defense",
                "postseason",
                "championships",
                "modern advanced universal bonus",
            ],
        },
        {
            "dimension": "PLAYOFFS",
            "question": "How strong was the player's individual postseason performance?",
            "formula": (
                "0.65 absolute postseason quality + 0.20 bounded regular-to-playoff "
                "resilience + 0.15 repeated elite postseason evidence"
            ),
            "primary_evidence": ["PLAYOFF individual normalized performance"],
            "excluded": [
                "series wins",
                "Finals outcome",
                "championship outcome",
                "sample-size quality penalty",
            ],
        },
        {
            "dimension": "ACCOLADES",
            "question": "How much meaningful individual recognition did the player earn?",
            "formula": (
                "0.60 Major Honors axis + 0.35 Sustained Recognition axis + 0.05 "
                "statistical-leader support; same-season bundles cap correlated events"
            ),
            "primary_evidence": [
                "MVP",
                "Finals MVP",
                "DPOY",
                "All-NBA",
                "All-Defense",
                "All-Star roster evidence",
            ],
            "excluded": [
                "NBA Champion",
                "award-derived defensive performance",
                "unanimous MVP bonus",
                "specialized modern awards",
            ],
        },
        {
            "dimension": "WINNING",
            "question": "What team success occurred while the player was a meaningful participant?",
            "formula": (
                "0.65 mutually-exclusive hierarchical postseason outcome + 0.25 "
                "sustained elite regular-season team context + 0.10 playoff breadth, "
                "participation-conditioned"
            ),
            "primary_evidence": [
                "team outcomes",
                "actual postseason/Finals participation",
                "game-share role proxy",
                "team win percentile",
            ],
            "excluded": [
                "individual playoff performance",
                "Finals MVP",
                "raw champion award count",
                "generic WOWY additive credit",
            ],
        },
    ]
    return {
        "registry_version": 1,
        "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
        "constitution": "docs/constitution/GOATLAB_V1_CONSTITUTION.md",
        "common": common,
        "dimensions": formulas,
        "era_dominance": "DIAGNOSTIC_ONLY_NOT_ADDITIVE",
        "official_overall_score": "NOT_CREATED",
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    input_fingerprints = verify_inputs(args)
    context = player_context(args.gold_root)
    players = sorted(context)
    archetype_path = args.gold_root / "ml_structure/clustering/player_archetypes.parquet"
    archetypes = (
        {
            str(row["player_id"]): int(row["kmeans_profile_cluster"])
            for row in read_entity(archetype_path)
        }
        if archetype_path.is_file()
        else {}
    )
    seasons = load_normalized_seasons(args.gold_root)
    team_suppression, _ = build_team_suppression(args.silver_root, args.gold_root)
    enrich_season_values(seasons, team_suppression)
    defense_result = defense_bridge(seasons, context)
    use_enriched_defense = bool(defense_result["passes"])
    add_overall_season_quality(seasons, use_enriched_defense=use_enriched_defense)
    reference = broad_reference(context, seasons)
    threshold, threshold_calibration = calibrate_longevity_threshold(seasons, args.silver_root)

    scores: dict[str, dict[str, float | None]] = {}
    details: dict[str, dict[str, dict[str, Any]]] = {}
    scores["PEAK"], details["PEAK"] = build_peak(players, seasons, reference, 0.70)
    scores["LONGEVITY"], details["LONGEVITY"] = build_longevity(
        players, seasons, reference, threshold, (0.35, 0.40, 0.25)
    )
    scores["OFFENSE"], details["OFFENSE"] = build_offense(players, seasons, reference)
    scores["DEFENSE"], details["DEFENSE"] = build_defense(
        players, seasons, reference, enriched=use_enriched_defense
    )
    scores["PLAYOFFS"], details["PLAYOFFS"] = build_playoffs(
        players, seasons, context, reference, (0.65, 0.20, 0.15)
    )
    scores["ACCOLADES"], details["ACCOLADES"], accolade_audit = build_accolades(
        players, context, args.silver_root, args.gold_root, reference, (0.60, 0.35, 0.05)
    )
    scores["WINNING"], details["WINNING"], winning_audit = build_winning(
        players, context, args.gold_root, reference, (0.65, 0.25, 0.10)
    )

    sensitivity_records: list[dict[str, Any]] = []
    for weight in (0.60, 0.70, 0.80):
        alternative, _ = build_peak(players, seasons, reference, weight)
        sensitivity_records.append(
            {
                "dimension": "PEAK",
                "formula_id": f"THREE_YEAR_{int(weight * 100)}",
                "selected": weight == 0.70,
                **rank_audit(scores["PEAK"], alternative, context, archetypes),
            }
        )
    for candidate_threshold in (0.80, 0.85, 0.90, 0.95):
        alternative, _ = build_longevity(
            players, seasons, reference, candidate_threshold, (0.35, 0.40, 0.25)
        )
        sensitivity_records.append(
            {
                "dimension": "LONGEVITY",
                "formula_id": f"THRESHOLD_{candidate_threshold:.2f}",
                "selected": candidate_threshold == threshold,
                **rank_audit(scores["LONGEVITY"], alternative, context, archetypes),
            }
        )
    for volume_weight in (0.60, 0.65, 0.70):
        altered = {key: dict(value) for key, value in seasons.items()}
        enrich_season_values(altered, team_suppression, scoring_volume_weight=volume_weight)
        alternative, _ = build_offense(players, altered, reference)
        sensitivity_records.append(
            {
                "dimension": "OFFENSE",
                "formula_id": f"SCORING_VOLUME_{int(volume_weight * 100)}",
                "selected": volume_weight == 0.65,
                **rank_audit(scores["OFFENSE"], alternative, context, archetypes),
            }
        )
    for enriched in (False, True):
        alternative, _ = build_defense(players, seasons, reference, enriched=enriched)
        sensitivity_records.append(
            {
                "dimension": "DEFENSE",
                "formula_id": "ACTION_ENRICHED" if enriched else "RESTRICTED_PORTABLE",
                "selected": enriched == use_enriched_defense,
                **rank_audit(scores["DEFENSE"], alternative, context, archetypes),
            }
        )
    for label, weights in (
        ("60_25_15", (0.60, 0.25, 0.15)),
        ("65_20_15", (0.65, 0.20, 0.15)),
        ("70_20_10", (0.70, 0.20, 0.10)),
    ):
        alternative, _ = build_playoffs(players, seasons, context, reference, weights)
        sensitivity_records.append(
            {
                "dimension": "PLAYOFFS",
                "formula_id": label,
                "selected": label == "65_20_15",
                **rank_audit(scores["PLAYOFFS"], alternative, context, archetypes),
            }
        )
    for label, weights in (
        ("55_40_05", (0.55, 0.40, 0.05)),
        ("60_35_05", (0.60, 0.35, 0.05)),
        ("65_30_05", (0.65, 0.30, 0.05)),
    ):
        alternative, _, _ = build_accolades(
            players, context, args.silver_root, args.gold_root, reference, weights
        )
        sensitivity_records.append(
            {
                "dimension": "ACCOLADES",
                "formula_id": label,
                "selected": label == "60_35_05",
                **rank_audit(scores["ACCOLADES"], alternative, context, archetypes),
            }
        )
    for label, weights in (
        ("60_30_10", (0.60, 0.30, 0.10)),
        ("65_25_10", (0.65, 0.25, 0.10)),
        ("70_20_10", (0.70, 0.20, 0.10)),
    ):
        alternative, _, _ = build_winning(players, context, args.gold_root, reference, weights)
        sensitivity_records.append(
            {
                "dimension": "WINNING",
                "formula_id": label,
                "selected": label == "65_25_10",
                **rank_audit(scores["WINNING"], alternative, context, archetypes),
            }
        )

    score_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    coverage_counts: dict[str, Counter[str]] = defaultdict(Counter)
    confidence_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for dimension in (item.value for item in Dimension):
        for player_id in players:
            detail = details[dimension][player_id]
            score = finite(scores[dimension][player_id])
            relevant_seasons = int(detail.get("relevant_seasons") or 0)
            relevant_games = int(
                detail.get("relevant_games") or context[player_id]["regular_total_games"] or 0
            )
            evidence_coverage = float(detail.get("component_coverage") or 0.0)
            if score is None:
                if (
                    dimension == "ACCOLADES"
                    and detail.get("award_acquisition_status") == "NOT_QUERIED"
                ):
                    coverage = ScoreCoverage.NOT_QUERIED
                elif dimension in {"PEAK", "PLAYOFFS"}:
                    coverage = ScoreCoverage.INSUFFICIENT_SAMPLE
                else:
                    coverage = ScoreCoverage.SOURCE_UNAVAILABLE
            elif evidence_coverage < 0.99:
                coverage = ScoreCoverage.PARTIAL_EVIDENCE
            else:
                coverage = ScoreCoverage.AVAILABLE
            if score is None:
                confidence = EvidenceConfidence.UNAVAILABLE
            elif dimension == "PLAYOFFS":
                if relevant_games >= 100 or relevant_seasons >= 10:
                    confidence = EvidenceConfidence.STRONG
                elif relevant_games >= 40 or relevant_seasons >= 5:
                    confidence = EvidenceConfidence.MODERATE
                else:
                    confidence = EvidenceConfidence.LIMITED
            else:
                confidence = confidence_from_coverage(
                    evidence_coverage, relevant_seasons=relevant_seasons
                )
            reasons = []
            if context[player_id]["career_active"]:
                reasons.append("TO_DATE_NO_PROJECTION")
            if evidence_coverage < 0.99 and score is not None:
                reasons.append("EXPLICIT_AVAILABLE_EVIDENCE_RENORMALIZATION")
            if score is None:
                reasons.append(coverage.value)
            if dimension == "DEFENSE" and confidence is EvidenceConfidence.LIMITED:
                reasons.append("HISTORICAL_DEFENSIVE_EVIDENCE_LIMITED")
            score_rows.append(
                {
                    "player_id": player_id,
                    "nba_player_id": context[player_id]["nba_player_id"],
                    "display_name": context[player_id]["display_name"],
                    "dimension": dimension,
                    "score": score,
                    "raw_dimension_value": finite(detail.get("raw")),
                    "coverage_status": coverage.value,
                    "evidence_confidence": confidence.value,
                    "evidence_coverage_pct": finite(evidence_coverage),
                    "relevant_seasons": relevant_seasons,
                    "relevant_games": relevant_games,
                    "reason_codes_json": json.dumps(reasons, separators=(",", ":")),
                    "career_status": context[player_id]["career_status"],
                    "completeness_context": "TO_DATE_NO_PROJECTION"
                    if context[player_id]["career_active"]
                    else "RECORDED_TO_CORPUS_CUTOFF",
                    "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
                    "corpus_id": CORPUS_ID,
                    "corpus_fingerprint": CORPUS_FINGERPRINT,
                    "normalization_fingerprint": NORMALIZATION_FINGERPRINT,
                }
            )
            coverage_counts[dimension][coverage.value] += 1
            confidence_counts[dimension][confidence.value] += 1
            for name, value in sorted(detail.items()):
                if name in {"raw", "relevant_seasons", "relevant_games", "component_coverage"}:
                    continue
                component_rows.append(
                    {
                        "player_id": player_id,
                        "dimension": dimension,
                        "component_name": name,
                        "component_value": finite(value)
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                        else None,
                        "component_text": str(value) if isinstance(value, str) else None,
                        "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
                        "corpus_id": CORPUS_ID,
                    }
                )

    structural = structural_audit(scores, context)
    bridge = modern_bridge_audit(
        scores, seasons, context, reference, defense_result, args.gold_root, args.silver_root
    )
    era_records = []
    for dimension in (item.value for item in Dimension):
        for group in (
            "PRE_1960",
            "1960S",
            "1970S",
            "1980S",
            "1990S",
            "2000S",
            "2010S",
            "2020S",
            "UNKNOWN",
        ):
            members = [
                player_id
                for player_id in players
                if era_group(context[player_id]["regular_first_season"]) == group
            ]
            observed = [
                float(scores[dimension][player_id])
                for player_id in members
                if scores[dimension][player_id] is not None
            ]
            era_records.append(
                {
                    "dimension": dimension,
                    "debut_era": group,
                    "players": len(members),
                    "scores_available": len(observed),
                    "availability_pct": finite(len(observed) / len(members)) if members else None,
                    "median_score": finite(statistics.median(observed)) if observed else None,
                    "fairness_interpretation": (
                        "coverage/distribution diagnostic; no era quota or adjustment"
                    ),
                }
            )

    case_studies = []
    for player_id in players:
        if str(context[player_id]["nba_player_id"]) not in CASE_NBA_IDS:
            continue
        case_studies.append(
            {
                "player_id": player_id,
                "nba_player_id": context[player_id]["nba_player_id"],
                "display_name": context[player_id]["display_name"],
                "career_status": context[player_id]["career_status"],
                "scores": {
                    dimension: {
                        "score": finite(scores[dimension][player_id]),
                        "coverage": next(
                            row["coverage_status"]
                            for row in score_rows
                            if row["player_id"] == player_id and row["dimension"] == dimension
                        ),
                        "confidence": next(
                            row["evidence_confidence"]
                            for row in score_rows
                            if row["player_id"] == player_id and row["dimension"] == dimension
                        ),
                    }
                    for dimension in (item.value for item in Dimension)
                },
                "diagnostic_only": True,
            }
        )

    registry = formula_registry(threshold, use_enriched_defense)
    stable_yaml(args.docs_root / "goat-v1-dimension-formulas.yaml", registry)
    reports: dict[str, object] = {
        "dimension-score-sensitivity.json": {
            "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
            "selection_rule": (
                "constitutional fidelity, coverage, interpretability, stability, redundancy, "
                "and era fairness; never famous-player order"
            ),
            "longevity_all_nba_calibration": threshold_calibration,
            "records": sensitivity_records,
        },
        "dimension-score-cross-audit.json": {
            "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
            **structural,
            "ownership_assertions": {
                "peak_longevity_capped": True,
                "regular_postseason_separated": True,
                "playoffs_use_team_outcomes": False,
                "winning_hierarchical_tiers": True,
                "defense_uses_dpoy_or_all_defense": False,
                "offense_uses_stat_titles": False,
                "accolades_same_season_capped": True,
                "generic_wowy_additive": False,
                "era_dominance_additive": False,
            },
        },
        "dimension-score-era-fairness.json": {
            "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
            "records": era_records,
            "modern_enrichment_in_universal_score": False,
            "active_players_projected": False,
        },
        "dimension-score-modern-bridge.json": {
            "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
            **bridge,
        },
        "dimension-score-case-studies.json": {
            "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
            "optimization_target": "NONE",
            "players": case_studies,
        },
    }
    for name, payload in reports.items():
        stable_json(args.docs_root / name, payload)

    outputs = [
        write_parquet(
            score_rows,
            args.gold_root / "player_dimension_scores" / "part-00000.parquet",
            ("player_id", "dimension"),
        ),
        write_parquet(
            component_rows,
            args.gold_root / "player_dimension_components" / "part-00000.parquet",
            ("player_id", "dimension", "component_name"),
        ),
        write_parquet(
            sensitivity_records,
            args.gold_root / "player_dimension_sensitivity" / "part-00000.parquet",
            ("dimension", "formula_id"),
        ),
    ]
    output_fingerprint = hashlib.sha256(
        "\n".join(
            f"{row['path']}:{row['sha256']}"
            for row in sorted(outputs, key=lambda item: item["path"])
        ).encode()
    ).hexdigest()
    report_paths = [
        args.docs_root / "goat-v1-dimension-formulas.yaml",
        *(args.docs_root / name for name in sorted(reports)),
    ]
    report_fingerprint = hashlib.sha256(
        "\n".join(f"{path.name}:{file_sha256(path)}" for path in report_paths).encode()
    ).hexdigest()
    runtime = time.perf_counter() - started
    prior_path = args.docs_root / "dimension-score-summary.json"
    if args.expected_fingerprint and prior_path.exists():
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        if prior.get("output_fingerprint") == output_fingerprint:
            runtime = float(prior["runtime_seconds"])
    summary = {
        "step": "STEP-0014",
        "result": "PASS",
        "methodology_version": DIMENSION_SCORE_METHODOLOGY_VERSION,
        "run_at": args.run_at,
        "input_fingerprints": input_fingerprints,
        "master_players": len(players),
        "reference_players": len(reference),
        "dimension_score_rows": len(score_rows),
        "component_rows": len(component_rows),
        "coverage_by_dimension": {
            dimension: dict(sorted(values.items()))
            for dimension, values in sorted(coverage_counts.items())
        },
        "confidence_by_dimension": {
            dimension: dict(sorted(values.items()))
            for dimension, values in sorted(confidence_counts.items())
        },
        "selected_longevity_threshold": threshold,
        "defense_action_bridge_passed": use_enriched_defense,
        "accolade_stacking_audit": accolade_audit,
        "winning_stacking_audit": winning_audit,
        "complete_seven_dimension_players": structural["complete_players"],
        "output_partitions": len(outputs),
        "output_size_bytes": sum(int(row["size_bytes"]) for row in outputs),
        "output_fingerprint": output_fingerprint,
        "committed_report_fingerprint": report_fingerprint,
        "runtime_seconds": finite(runtime),
        "runtime_definition": (
            "baseline successful offline build; preserved across exact certification rebuilds"
        ),
        "deterministic_rebuild_verified": args.expected_fingerprint is not None,
        "network_requests": 0,
        "official_overall_score_created": False,
        "official_overall_weights_selected": False,
        "partitions": outputs,
    }
    if args.expected_fingerprint and output_fingerprint != args.expected_fingerprint:
        raise ValueError(
            "output fingerprint mismatch: "
            f"expected {args.expected_fingerprint}, got {output_fingerprint}"
        )
    stable_json(prior_path, summary)
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "result",
                    "dimension_score_rows",
                    "complete_seven_dimension_players",
                    "output_fingerprint",
                    "runtime_seconds",
                )
            },
            sort_keys=True,
        )
    )
    return summary


def main() -> None:
    build(parse_args())


if __name__ == "__main__":
    main()
