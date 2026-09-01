#!/usr/bin/env python3
"""Build STEP-0012 diagnostic dimension candidates and methodology audits offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from goatlab.features.dimension_candidates import (
    COVERAGE_THRESHOLD,
    DIMENSION_METHODOLOGY_VERSION,
    MONTE_CARLO_SAMPLES,
    MONTE_CARLO_SEED,
    CandidateSpec,
    CandidateStatus,
    Dimension,
    MissingnessPolicy,
    OwnershipType,
    ScalingMethod,
    candidate_specs,
    combine_components,
    correlation_pair,
    era_group,
    midranks,
    rejection_reasons,
    scale_values,
    shared_primitive_lineage,
    simplex_weights,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
NORMALIZATION_FINGERPRINT = "a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852"
CAREER_FINGERPRINT = "5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b"
AWARDS_FINGERPRINT = "666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258"
TEAM_FINGERPRINT = "707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333"
ACCOLADE_FINGERPRINT = "e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880"
PRIMARY_SCALING = ScalingMethod.CAREER_UNIVERSE_PERCENTILE
PRIMARY_POLICY = MissingnessPolicy.COVERAGE_THRESHOLD
CORE_METRICS = ("ppg", "rpg", "apg", "ts_pct")
CASE_STUDY_NBA_IDS = (
    "76375",  # Wilt: single-season extremeness
    "76003",  # Kareem: long career
    "77142",  # Magic: playmaking
    "893",  # Jordan: scoring, awards, playoffs
    "165",  # Hakeem: defense
    "1495",  # Duncan: team/playoff longevity
    "2544",  # LeBron: active-to-cutoff longevity
    "201939",  # Curry: efficiency/scoring
    "203999",  # Jokic: modern advanced era
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def stable_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_entity(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        rows.extend(pq.ParquetFile(path).read().to_pylist())
    return rows


def finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return round(number, 12) if math.isfinite(number) else None


def safe_mean(values: list[float]) -> float | None:
    return finite(statistics.fmean(values)) if values else None


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


def verify_inputs(args: argparse.Namespace) -> None:
    manifests = {
        args.docs_root / "historical-corpus-v1-manifest.json": CORPUS_FINGERPRINT,
        args.docs_root / "era-normalization-gold-manifest.json": NORMALIZATION_FINGERPRINT,
        args.docs_root / "career-gold-manifest.json": CAREER_FINGERPRINT,
        args.docs_root / "award-canonicalization-summary.json": AWARDS_FINGERPRINT,
        args.docs_root / "team-success-summary.json": TEAM_FINGERPRINT,
        args.docs_root / "accolade-fact-completion-summary.json": ACCOLADE_FINGERPRINT,
    }
    for path, fingerprint in manifests.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates = {
            str(payload.get(key, ""))
            for key in (
                "corpus_fingerprint",
                "output_fingerprint",
                "career_output_fingerprint",
                "award_output_fingerprint",
                "career_fingerprint",
            )
        }
        if fingerprint not in candidates:
            raise ValueError(f"unexpected input fingerprint: {path}")


def build_primitive_matrix(
    gold_root: Path,
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, Any]]]:
    summaries = read_entity(gold_root / "player_career_summary")
    player_context = {str(row["player_id"]): row for row in summaries}
    players = sorted(player_context)
    matrix: dict[str, dict[str, float | None]] = defaultdict(dict)

    for player_id, row in player_context.items():
        for source, target in (
            ("regular_qualified_seasons", "regular_qualified_seasons"),
            ("regular_total_games", "regular_total_games"),
            ("playoff_seasons_appeared", "playoff_seasons"),
            ("playoff_games", "playoff_games"),
        ):
            matrix[target][player_id] = finite(row[source])

    career_rows = read_entity(gold_root / "player_career_features")
    career_lookup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in career_rows:
        key = (
            str(row["player_id"]),
            str(row["season_type"]),
            str(row["metric_name"]),
            str(row["normalization_method"]),
        )
        career_lookup[key] = row
        player_id, season_type, metric, method = key
        prefix = "reg" if season_type == "REGULAR" else "po"
        if method == "STANDARD_Z":
            for source, suffix in (
                ("career_mean", "mean_z"),
                ("career_maximum", "max_z"),
                ("top3_mean", "top3_z"),
                ("top5_mean", "top5_z"),
                ("cumulative_positive_z", "cum_positive_z"),
                ("opportunity_weighted_positive_z", "weighted_positive_z"),
            ):
                matrix[f"{prefix}_{metric}_{suffix}"][player_id] = finite(row[source])
        elif method == "PERCENTILE":
            for source, suffix in (
                ("career_mean", "mean_pct"),
                ("career_maximum", "max_pct"),
                ("area_above_p80", "area_p80"),
                ("area_above_p90", "area_p90"),
                ("elite_p80_seasons", "elite_p80"),
                ("elite_p90_seasons", "elite_p90"),
                ("elite_p95_seasons", "elite_p95"),
            ):
                matrix[f"{prefix}_{metric}_{suffix}"][player_id] = finite(row[source])

    for player_id in players:
        for metric in CORE_METRICS:
            regular = matrix[f"reg_{metric}_mean_z"].get(player_id)
            playoff = matrix[f"po_{metric}_mean_z"].get(player_id)
            matrix[f"{metric}_playoff_lift"][player_id] = (
                finite(playoff - regular) if playoff is not None and regular is not None else None
            )

    modern_seasons: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in read_entity(gold_root / "player_season_feature_long"):
        if (
            row["season_type"] == "REGULAR"
            and int(row["season_id"]) >= 1996
            and row["metric_name"] in {"apg", "ts_pct", "spg", "bpg"}
            and row["qualification_status"] == "QUALIFIED"
            and str(row["coverage_status"]).startswith("AVAILABLE")
            and row["z_score"] is not None
        ):
            modern_seasons[(str(row["player_id"]), str(row["metric_name"]))].append(
                float(row["z_score"])
            )
    for (player_id, metric), values in modern_seasons.items():
        matrix[f"modern_reg_{metric}_mean_z"][player_id] = safe_mean(values)

    peak_rows = read_entity(gold_root / "player_peak_windows")
    for row in peak_rows:
        if row["normalization_method"] != "STANDARD_Z" or row["coverage_status"] != "AVAILABLE":
            continue
        prefix = "reg" if row["season_type"] == "REGULAR" else "po"
        metric = str(row["metric_name"])
        window = int(row["window_size"])
        variant = str(row["peak_variant"])
        suffix = "quality" if variant == "QUALITY" else "adjusted"
        value_field = (
            "mean_normalized_value" if variant == "QUALITY" else "adjusted_mean_normalized_value"
        )
        matrix[f"{prefix}_{metric}_peak{window}_{suffix}"][str(row["player_id"])] = finite(
            row[value_field]
        )

    prime_rows = read_entity(gold_root / "player_prime_runs")
    for row in prime_rows:
        if row["season_type"] != "REGULAR" or row["coverage_status"] != "AVAILABLE":
            continue
        threshold = round(float(row["threshold"]) * 100)
        matrix[f"reg_{row['metric_name']}_run_p{threshold}"][str(row["player_id"])] = finite(
            row["longest_run"]
        )

    accolades = {
        str(row["player_id"]): row
        for row in read_entity(gold_root / "player_career_accolades_complete")
    }
    all_star = {
        str(row["player_id"]): row for row in read_entity(gold_root / "player_career_all_star")
    }
    stat_titles = {
        str(row["player_id"]): row for row in read_entity(gold_root / "player_career_stat_titles")
    }
    award_fields = (
        "mvp_count",
        "finals_mvp_count",
        "dpoy_count",
        "all_nba_total_count",
        "all_defense_total_count",
    )
    event_totals = {
        field: sum(int(row[field]) for row in accolades.values() if row[field] is not None)
        for field in award_fields
    }
    introductions = {
        "mvp_count": 1955,
        "finals_mvp_count": 1968,
        "dpoy_count": 1982,
        "all_nba_total_count": 1946,
        "all_defense_total_count": 1968,
    }
    for player_id in players:
        row = accolades[player_id]
        for field in award_fields:
            matrix[field][player_id] = finite(row[field])
        roster = all_star.get(player_id)
        matrix["all_star_roster_seasons"][player_id] = finite(
            roster["all_star_event_roster_seasons"] if roster else 0
        )
        titles = stat_titles.get(player_id)
        matrix["stat_title_count"][player_id] = finite(
            sum(
                int(titles.get(f"{cat}_official_source_rank_one_count") or 0)
                for cat in ("pts", "reb", "ast", "stl", "blk")
            )
            if titles
            else 0
        )
        if row["award_acquisition_status"] in {"SUCCESS_WITH_ROWS", "SUCCESS_EMPTY"}:
            scarcity = sum(
                float(row[field] or 0) / event_totals[field]
                for field in award_fields
                if event_totals[field]
            )
            first = player_context[player_id]["regular_first_season"]
            last = player_context[player_id]["regular_last_season"]
            opportunity_terms: list[float] = []
            if first is not None and last is not None:
                for field in award_fields:
                    applicable = max(0, int(last) - max(int(first), introductions[field]) + 1)
                    if applicable:
                        opportunity_terms.append(float(row[field] or 0) / applicable)
            matrix["award_scarcity_index"][player_id] = finite(scarcity)
            matrix["award_opportunity_index"][player_id] = safe_mean(opportunity_terms)
        else:
            matrix["award_scarcity_index"][player_id] = None
            matrix["award_opportunity_index"][player_id] = None

    team_rows = {
        str(row["player_id"]): row for row in read_entity(gold_root / "player_career_team_context")
    }
    for player_id in players:
        row = team_rows[player_id]
        mapping = {
            "mean_team_win_percentile": "mean_team_win_percentile",
            "playoff_seasons": "playoff_seasons",
            "playoff_games": "playoff_games",
            "playoff_wins": "playoff_wins_while_participating",
            "finals_seasons": "finals_seasons",
            "finals_games": "finals_games",
            "champion_regular_seasons": "seasons_on_champion_teams_regular",
            "champion_playoff_seasons": "seasons_played_playoffs_for_champion",
            "champion_finals_seasons": "seasons_played_finals_for_champion",
            "elite_team_seasons": "seasons_on_90th_percentile_regular_teams",
        }
        for target, source in mapping.items():
            matrix[target][player_id] = finite(row[source])

    share_values: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in read_entity(gold_root / "player_team_success_primitives"):
        player_id = str(row["player_id"])
        for source, target, weight_field in (
            ("regular_game_share", "mean_regular_game_share", "regular_games"),
            ("playoff_game_share", "mean_playoff_game_share", "playoff_games"),
            ("finals_game_share", "mean_finals_game_share", "finals_games"),
        ):
            value = finite(row[source])
            weight = finite(row[weight_field])
            if value is not None and weight is not None and weight > 0:
                share_values[target][player_id].append((value, weight))
    for target, by_player in share_values.items():
        for player_id, values in by_player.items():
            matrix[target][player_id] = finite(
                sum(value * weight for value, weight in values)
                / sum(weight for _, weight in values)
            )

    advanced: dict[tuple[int, str], list[tuple[str, float]]] = defaultdict(list)
    for row in read_entity(ROOT / "data/silver/player_season_advanced"):
        if (
            row["season_type"] == "REGULAR"
            and row["row_scope"] == "TOTAL"
            and row["defensive_rating"] is not None
        ):
            advanced[(int(row["season_id"]), "REGULAR")].append(
                (str(row["player_id"]), float(row["defensive_rating"]))
            )
    advanced_by_player: dict[str, list[float]] = defaultdict(list)
    for rows in advanced.values():
        values = [value for _, value in rows]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values)
        if std > 0:
            for player_id, value in rows:
                advanced_by_player[player_id].append((mean - value) / std)
    for player_id, values in advanced_by_player.items():
        matrix["modern_def_rating_mean_z"][player_id] = safe_mean(values)

    for primitive in matrix.values():
        for player_id in players:
            primitive.setdefault(player_id, None)
    return dict(matrix), player_context


def evaluation_populations(
    matrix: dict[str, dict[str, float | None]], player_context: dict[str, dict[str, Any]]
) -> tuple[dict[str, set[str]], dict[str, dict[str, bool]]]:
    flags: dict[str, dict[str, bool]] = {}
    for player_id, row in player_context.items():
        q = int(row["regular_qualified_seasons"])
        elite90 = any(
            (matrix[f"reg_{metric}_elite_p90"].get(player_id) or 0) > 0 for metric in CORE_METRICS
        )
        elite95 = any(
            (matrix[f"reg_{metric}_elite_p95"].get(player_id) or 0) > 0 for metric in CORE_METRICS
        )
        flags[player_id] = {
            "ALL_PLAYERS": True,
            "PARTICIPATION_QUALIFIED": q >= 5,
            "CAREER_SIGNAL": q >= 3 or elite95,
            "BROAD_HIGH_RECALL": q >= 3 or elite90,
        }
    populations = {
        name: {player_id for player_id, item in flags.items() if item[name]}
        for name in next(iter(flags.values()))
    }
    return populations, flags


def primary_owners(specs: tuple[CandidateSpec, ...]) -> dict[str, Dimension]:
    preferred = {
        "dpoy_count": Dimension.ACCOLADES,
        "all_defense_total_count": Dimension.ACCOLADES,
        "finals_seasons": Dimension.WINNING,
        "finals_games": Dimension.WINNING,
        "playoff_games": Dimension.PLAYOFFS,
        "playoff_seasons": Dimension.PLAYOFFS,
    }
    owners: dict[str, Dimension] = {}
    for spec in specs:
        for primitive in spec.primitives:
            owners.setdefault(primitive.name, spec.dimension)
    owners.update(preferred)
    return owners


def build_registry(
    specs: tuple[CandidateSpec, ...], status: dict[str, tuple[CandidateStatus, list[str]]]
) -> dict[str, Any]:
    owners = primary_owners(specs)
    dimensions_by_primitive: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, str] = {}
    for spec in specs:
        for primitive in spec.primitives:
            dimensions_by_primitive[primitive.name].add(spec.dimension.value)
            sources[primitive.name] = primitive.source_methodology
    ownership = []
    for primitive in sorted(dimensions_by_primitive):
        for dimension in sorted(dimensions_by_primitive[primitive]):
            ownership.append(
                {
                    "feature_name": primitive,
                    "source_methodology": sources[primitive],
                    "candidate_dimension": dimension,
                    "ownership_type": OwnershipType.PRIMARY.value
                    if owners[primitive].value == dimension
                    else OwnershipType.SECONDARY.value,
                    "coverage": "INHERITED_FROM_SOURCE_PRIMITIVE",
                    "known_overlap": sorted(dimensions_by_primitive[primitive] - {dimension}),
                    "notes": "Evidence quality is reported separately from player quality.",
                }
            )
    candidates = []
    for spec in specs:
        candidate_status, reasons = status[spec.candidate_id]
        candidates.append(
            {
                "dimension": spec.dimension.value,
                "candidate_id": spec.candidate_id,
                "name": spec.name,
                "description": spec.description,
                "input_primitives": [primitive.name for primitive in spec.primitives],
                "feature_ownership": [
                    "PRIMARY" if owners[primitive.name] is spec.dimension else "SECONDARY"
                    for primitive in spec.primitives
                ],
                "coverage_requirements": f"policy-dependent; threshold={COVERAGE_THRESHOLD:.6f}",
                "scaling_methods": [method.value for method in ScalingMethod],
                "missingness_policies": [policy.value for policy in MissingnessPolicy],
                "combination_method": (
                    "weighted arithmetic mean after component scaling; diagnostic only"
                ),
                "weight_policy": "equal baseline plus deterministic uniform-simplex sensitivity",
                "known_overlap": sorted(
                    {
                        other
                        for primitive in spec.primitives
                        for other in dimensions_by_primitive[primitive.name]
                        if other != spec.dimension.value
                    }
                ),
                "known_biases": list(spec.known_biases),
                "historical_limitations": [
                    primitive.name for primitive in spec.primitives if primitive.post_1996_only
                ],
                "active_career_limitations": (
                    "to-date only; no projection; longevity/accolades/winning incomplete"
                ),
                "status": candidate_status.value,
                "status_reasons": reasons,
            }
        )
    return {
        "registry_version": 1,
        "methodology_version": DIMENSION_METHODOLOGY_VERSION,
        "candidate_count": len(candidates),
        "final_candidate_count": 0,
        "double_counting_policies_evaluated": [
            "STRICT_OWNERSHIP",
            "SHARED_EVIDENCE_WITH_PENALTY",
            "RAW_EVIDENCE_SEPARATION",
        ],
        "selected_experimental_policy": "RAW_EVIDENCE_SEPARATION",
        "feature_ownership": ownership,
        "candidates": candidates,
    }


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    text = yaml.safe_dump(registry, sort_keys=False, allow_unicode=True)
    temporary = path.with_suffix(".yaml.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def percentile_map(values: dict[str, float]) -> dict[str, float]:
    players = sorted(values)
    ranks = midranks([values[player_id] for player_id in players])
    count = len(players)
    return {player_id: (rank + 0.5) / count for player_id, rank in zip(players, ranks, strict=True)}


def monte_carlo(
    spec: CandidateSpec,
    scaled: dict[str, dict[str, float | None]],
    players: set[str],
) -> dict[str, Any]:
    complete = [
        player_id
        for player_id in sorted(players)
        if all(scaled[primitive.name][player_id] is not None for primitive in spec.primitives)
    ]
    if not complete:
        return {
            "candidate_id": spec.candidate_id,
            "complete_players": 0,
            "samples": 0,
            "mean_score_variance": None,
            "mean_percentile_variance": None,
            "pairwise_ordering_stability": None,
        }
    equal = {
        player_id: statistics.fmean(
            float(scaled[primitive.name][player_id]) for primitive in spec.primitives
        )
        for player_id in complete
    }
    weights = simplex_weights(
        len(spec.primitives),
        MONTE_CARLO_SAMPLES,
        MONTE_CARLO_SEED + int(hashlib.sha256(spec.candidate_id.encode()).hexdigest()[:8], 16),
    )
    score_sum = dict.fromkeys(complete, 0.0)
    score_square = dict.fromkeys(complete, 0.0)
    percentile_sum = dict.fromkeys(complete, 0.0)
    percentile_square = dict.fromkeys(complete, 0.0)
    percentile_history: dict[str, list[float]] = {player_id: [] for player_id in complete}
    pair_candidates = [
        (complete[index], complete[-index - 1]) for index in range(min(250, len(complete) // 2))
    ]
    agreement = comparisons = 0
    for weight in weights:
        simulation = {
            player_id: sum(
                float(scaled[primitive.name][player_id]) * component_weight
                for primitive, component_weight in zip(spec.primitives, weight, strict=True)
            )
            for player_id in complete
        }
        percentiles = percentile_map(simulation)
        for player_id in complete:
            score = simulation[player_id]
            percentile = percentiles[player_id]
            score_sum[player_id] += score
            score_square[player_id] += score * score
            percentile_sum[player_id] += percentile
            percentile_square[player_id] += percentile * percentile
            percentile_history[player_id].append(percentile)
        for left, right in pair_candidates:
            agreement += ((equal[left] > equal[right]) - (equal[left] < equal[right])) == (
                (simulation[left] > simulation[right]) - (simulation[left] < simulation[right])
            )
            comparisons += 1
    score_variances = [
        score_square[player_id] / len(weights) - (score_sum[player_id] / len(weights)) ** 2
        for player_id in complete
    ]
    percentile_variances = [
        percentile_square[player_id] / len(weights)
        - (percentile_sum[player_id] / len(weights)) ** 2
        for player_id in complete
    ]
    player_distribution: list[dict[str, Any]] = []
    for player_id in complete:
        values = sorted(percentile_history[player_id])
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        player_distribution.append(
            {
                "player_id": player_id,
                "median_percentile": finite(statistics.median(values)),
                "percentile_iqr": finite(quartiles[2] - quartiles[0]),
                "percentile_variance": finite(
                    percentile_square[player_id] / len(weights)
                    - (percentile_sum[player_id] / len(weights)) ** 2
                ),
            }
        )
    sensitive = sorted(
        player_distribution,
        key=lambda row: (
            -float(row["percentile_variance"] or 0.0),
            str(row["player_id"]),
        ),
    )[:10]
    return {
        "candidate_id": spec.candidate_id,
        "complete_players": len(complete),
        "samples": len(weights),
        "mean_score_variance": finite(statistics.fmean(score_variances)),
        "mean_percentile_variance": finite(statistics.fmean(percentile_variances)),
        "pairwise_ordering_stability": finite(agreement / comparisons if comparisons else None),
        "median_of_player_median_percentiles": finite(
            statistics.median(float(row["median_percentile"]) for row in player_distribution)
        ),
        "median_player_percentile_iqr": finite(
            statistics.median(float(row["percentile_iqr"]) for row in player_distribution)
        ),
        "most_weight_sensitive_players": sensitive,
        "seed": MONTE_CARLO_SEED,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    verify_inputs(args)
    specs = candidate_specs()
    matrix, context = build_primitive_matrix(args.gold_root)
    populations, population_flags = evaluation_populations(matrix, context)
    reference = populations["BROAD_HIGH_RECALL"]
    required_primitives = sorted(
        {primitive.name for spec in specs for primitive in spec.primitives}
    )
    scaled: dict[ScalingMethod, dict[str, dict[str, float | None]]] = {}
    for method in ScalingMethod:
        scaled[method] = {
            name: scale_values(matrix[name], reference, method) for name in required_primitives
        }

    output_partitions: list[dict[str, Any]] = []
    coverage_partitions: list[dict[str, Any]] = []
    primary_scores: dict[str, dict[str, float | None]] = {}
    coverage_summary: list[dict[str, Any]] = []
    sensitivity: list[dict[str, Any]] = []
    initial_status: dict[str, tuple[CandidateStatus, list[str]]] = {}
    candidate_coverage: dict[str, float] = {}

    for spec in specs:
        score_rows: list[dict[str, Any]] = []
        coverage_rows: list[dict[str, Any]] = []
        primary: dict[str, float | None] = {}
        confidence_counts: Counter[str] = Counter()
        policy_available: Counter[str] = Counter()
        for player_id in sorted(context):
            raw_values = [matrix[primitive.name][player_id] for primitive in spec.primitives]
            available = sum(value is not None for value in raw_values)
            core_expected = sum(primitive.core for primitive in spec.primitives)
            core_available = sum(
                value is not None
                for value, primitive in zip(raw_values, spec.primitives, strict=True)
                if primitive.core
            )
            optional_expected = len(spec.primitives) - core_expected
            optional_available = available - core_available
            raw_combined = combine_components(
                raw_values,
                [primitive.core for primitive in spec.primitives],
                MissingnessPolicy.AVAILABLE_FEATURE_RENORMALIZATION,
            )
            confidence_counts[raw_combined.confidence.value] += 1
            coverage_rows.append(
                {
                    "player_id": player_id,
                    "dimension": spec.dimension.value,
                    "candidate_id": spec.candidate_id,
                    "expected_components": len(spec.primitives),
                    "available_components": available,
                    "evidence_coverage_pct": finite(available / len(spec.primitives)),
                    "core_feature_coverage": finite(
                        core_available / core_expected if core_expected else 0.0
                    ),
                    "optional_feature_coverage": finite(optional_available / optional_expected)
                    if optional_expected
                    else None,
                    "coverage_confidence": raw_combined.confidence.value,
                    "historical_comparability_status": "MODERN_ENRICHED_ONLY"
                    if any(primitive.post_1996_only for primitive in spec.primitives)
                    else "CROSS_ERA_WITH_COMPONENT_GATES",
                    "career_status": context[player_id]["career_status"],
                    "methodology_version": DIMENSION_METHODOLOGY_VERSION,
                    "corpus_id": CORPUS_ID,
                }
            )
            for method in ScalingMethod:
                component_values = [
                    scaled[method][primitive.name][player_id] for primitive in spec.primitives
                ]
                for policy in MissingnessPolicy:
                    combined = combine_components(
                        component_values, [primitive.core for primitive in spec.primitives], policy
                    )
                    if combined.value is not None:
                        policy_available[f"{method.value}:{policy.value}"] += 1
                    if method is PRIMARY_SCALING and policy is PRIMARY_POLICY:
                        primary[player_id] = finite(combined.value)
                    score_rows.append(
                        {
                            "player_id": player_id,
                            "dimension": spec.dimension.value,
                            "candidate_id": spec.candidate_id,
                            "scaling_method": method.value,
                            "coverage_policy": policy.value,
                            "diagnostic_value": finite(combined.value),
                            "evidence_coverage_pct": finite(combined.evidence_coverage_pct),
                            "core_feature_coverage": finite(combined.core_feature_coverage),
                            "optional_feature_coverage": finite(combined.optional_feature_coverage),
                            "coverage_confidence": combined.confidence.value,
                            "analytical_population_flags": json.dumps(
                                population_flags[player_id], sort_keys=True, separators=(",", ":")
                            ),
                            "career_status": context[player_id]["career_status"],
                            "completeness_context": "TO_DATE_NO_PROJECTION"
                            if context[player_id]["career_active"]
                            else "COMPLETE_OR_INDETERMINATE_AS_RECORDED",
                            "methodology_version": DIMENSION_METHODOLOGY_VERSION,
                            "corpus_id": CORPUS_ID,
                            "corpus_fingerprint": CORPUS_FINGERPRINT,
                        }
                    )
        primary_scores[spec.candidate_id] = primary
        available_rate = sum(primary[player_id] is not None for player_id in reference) / len(
            reference
        )
        candidate_coverage[spec.candidate_id] = available_rate
        coverage_summary.append(
            {
                "dimension": spec.dimension.value,
                "candidate_id": spec.candidate_id,
                "primary_available_rate": finite(available_rate),
                "confidence_counts": dict(sorted(confidence_counts.items())),
                "availability_by_scaling_policy": dict(sorted(policy_available.items())),
            }
        )
        sensitivity_record = monte_carlo(
            spec, scaled[ScalingMethod.CAREER_UNIVERSE_PERCENTILE], reference
        )
        sensitivity.append(sensitivity_record)
        reasons = list(
            rejection_reasons(
                available_rate=available_rate,
                post_1996_dependency=all(primitive.post_1996_only for primitive in spec.primitives),
                ordering_stability_value=sensitivity_record["pairwise_ordering_stability"],
                redundant_correlation=None,
                shared_lineage_count=0,
            )
        )
        if all(primitive.post_1996_only for primitive in spec.primitives):
            initial_status[spec.candidate_id] = (CandidateStatus.DEFERRED, reasons)
        elif reasons:
            initial_status[spec.candidate_id] = (CandidateStatus.REJECTED, reasons)
        else:
            initial_status[spec.candidate_id] = (CandidateStatus.VALIDATED_FOR_EXPERIMENT, [])
        output_partitions.append(
            write_parquet(
                score_rows,
                args.gold_root
                / "dimension_candidate_scores"
                / f"dimension={spec.dimension.value}"
                / f"candidate={spec.candidate_id}"
                / "part-00000.parquet",
                ("player_id", "scaling_method", "coverage_policy"),
            )
        )
        coverage_partitions.append(
            write_parquet(
                coverage_rows,
                args.gold_root
                / "dimension_candidate_coverage"
                / f"dimension={spec.dimension.value}"
                / f"candidate={spec.candidate_id}"
                / "part-00000.parquet",
                ("player_id",),
            )
        )

    candidate_by_id = {spec.candidate_id: spec for spec in specs}
    correlations: list[dict[str, Any]] = []
    for left_index, left in enumerate(specs):
        for right in specs[left_index + 1 :]:
            correlation = correlation_pair(
                primary_scores[left.candidate_id], primary_scores[right.candidate_id]
            )
            shared = shared_primitive_lineage(left, right)
            correlations.append(
                {
                    "left": left.candidate_id,
                    "right": right.candidate_id,
                    "relationship": "WITHIN_DIMENSION"
                    if left.dimension is right.dimension
                    else "CROSS_DIMENSION",
                    **{
                        key: finite(value) if isinstance(value, float) else value
                        for key, value in correlation.items()
                    },
                    "shared_primitive_count": len(shared),
                    "shared_primitives": list(shared),
                }
            )

    feature_correlations: list[dict[str, Any]] = []
    for spec in specs:
        for left_index, left in enumerate(spec.primitives):
            for right in spec.primitives[left_index + 1 :]:
                correlation = correlation_pair(matrix[left.name], matrix[right.name])
                feature_correlations.append(
                    {
                        "candidate_id": spec.candidate_id,
                        "dimension": spec.dimension.value,
                        "left_primitive": left.name,
                        "right_primitive": right.name,
                        **{
                            key: finite(value) if isinstance(value, float) else value
                            for key, value in correlation.items()
                        },
                    }
                )

    for record in correlations:
        if (
            record["relationship"] != "WITHIN_DIMENSION"
            or record["spearman"] is None
            or abs(record["spearman"]) < 0.98
            or not record["shared_primitive_count"]
        ):
            continue
        later = str(record["right"])
        status, reasons = initial_status[later]
        if status is CandidateStatus.VALIDATED_FOR_EXPERIMENT:
            initial_status[later] = (CandidateStatus.REJECTED, ["NEAR_DUPLICATE_SIGNAL"])

    ownership_registry = build_registry(specs, initial_status)
    write_registry(args.docs_root / "goat-dimension-candidates.yaml", ownership_registry)

    ownership_dimensions: dict[str, set[str]] = defaultdict(set)
    for spec in specs:
        for primitive in spec.primitives:
            ownership_dimensions[primitive.name].add(spec.dimension.value)
    owners = primary_owners(specs)
    ownership_policy_counts = []
    for spec in specs:
        primary_count = sum(
            owners[primitive.name] is spec.dimension for primitive in spec.primitives
        )
        shared_count = sum(
            len(ownership_dimensions[primitive.name]) > 1 for primitive in spec.primitives
        )
        ownership_policy_counts.append(
            {
                "candidate_id": spec.candidate_id,
                "input_count": len(spec.primitives),
                "strict_ownership_retained": primary_count,
                "strict_ownership_dropped": len(spec.primitives) - primary_count,
                "shared_evidence_components": shared_count,
                "shared_penalty_effective_weight_sum": finite(
                    sum(
                        1.0 / len(ownership_dimensions[primitive.name])
                        for primitive in spec.primitives
                    )
                ),
            }
        )
    redundancy_report = {
        "methodology_version": DIMENSION_METHODOLOGY_VERSION,
        "primary_diagnostic_contract": {
            "scaling": PRIMARY_SCALING.value,
            "missingness": PRIMARY_POLICY.value,
            "population": "BROAD_HIGH_RECALL",
        },
        "double_counting_policy_results": {
            "STRICT_OWNERSHIP": {
                "shared_primitives_allowed": False,
                "consequence": (
                    "Drops semantically relevant secondary evidence; lowest duplication."
                ),
            },
            "SHARED_EVIDENCE_WITH_PENALTY": {
                "shared_primitives_allowed": True,
                "penalty": "1 / number_of_dimensions_using_primitive",
                "consequence": "Transparent but introduces another weighting convention.",
            },
            "RAW_EVIDENCE_SEPARATION": {
                "shared_primitives_allowed": "only diagnostic/secondary",
                "selected_for_future_experimentation": True,
                "consequence": (
                    "DPOY remains ACCOLADES; box defense remains DEFENSE; "
                    "participation facts remain WINNING."
                ),
            },
        },
        "shared_primitive_count": sum(
            len(dimensions) > 1 for dimensions in ownership_dimensions.values()
        ),
        "shared_primitives": {
            name: sorted(dimensions)
            for name, dimensions in sorted(ownership_dimensions.items())
            if len(dimensions) > 1
        },
        "ownership_policy_candidate_counts": ownership_policy_counts,
        "within_candidate_feature_correlations": feature_correlations,
        "pairwise_correlations": correlations,
        "near_duplicate_pairs": [
            record
            for record in correlations
            if record["spearman"] is not None and abs(record["spearman"]) >= 0.95
        ],
        "interpretation": "Correlation is diagnostic evidence, not a target to minimize.",
    }
    stable_json(args.docs_root / "dimension-redundancy-audit.json", redundancy_report)

    era_records: list[dict[str, Any]] = []
    for spec in specs:
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
                for player_id, row in context.items()
                if era_group(row["regular_first_season"]) == group
            ]
            values = [
                primary_scores[spec.candidate_id][player_id]
                for player_id in members
                if primary_scores[spec.candidate_id][player_id] is not None
            ]
            coverages = [
                sum(matrix[primitive.name][player_id] is not None for primitive in spec.primitives)
                / len(spec.primitives)
                for player_id in members
            ]
            era_records.append(
                {
                    "dimension": spec.dimension.value,
                    "candidate_id": spec.candidate_id,
                    "era_group": group,
                    "players": len(members),
                    "score_available": len(values),
                    "score_available_pct": finite(len(values) / len(members)) if members else None,
                    "mean_component_coverage": safe_mean(coverages),
                    "median_diagnostic_score": finite(statistics.median(values))
                    if values
                    else None,
                    "post_1996_only_component_count": sum(
                        primitive.post_1996_only for primitive in spec.primitives
                    ),
                    "structural_flag": "INCOMPARABLE_MODERN_DEPENDENCY"
                    if all(primitive.post_1996_only for primitive in spec.primitives)
                    and group in {"PRE_1960", "1960S", "1970S", "1980S"}
                    else "REVIEW_DISTRIBUTION_NOT_QUOTA",
                }
            )
    stable_json(
        args.docs_root / "dimension-era-fairness.json",
        {
            "methodology_version": DIMENSION_METHODOLOGY_VERSION,
            "era_assignment": "regular-career first appearance season",
            "fairness_definition": (
                "coverage and structural comparability; not equal era representation"
            ),
            "records": era_records,
        },
    )

    sensitivity_report = {
        "methodology_version": DIMENSION_METHODOLOGY_VERSION,
        "random_seed": MONTE_CARLO_SEED,
        "samples_per_candidate": MONTE_CARLO_SAMPLES,
        "weight_distribution": "uniform simplex via normalized exponential draws",
        "reference_population": "BROAD_HIGH_RECALL",
        "candidate_results": sensitivity,
    }
    stable_json(args.docs_root / "dimension-weight-sensitivity.json", sensitivity_report)
    sensitivity_partitions = [
        write_parquet(
            sensitivity,
            args.gold_root / "dimension_candidate_sensitivity" / "part-00000.parquet",
            ("candidate_id",),
        )
    ]
    active_career_audit: list[dict[str, Any]] = []
    for spec in specs:
        for cohort, is_active in (("ACTIVE_TO_CUTOFF", True), ("NOT_ACTIVE_TO_CUTOFF", False)):
            members = [
                player_id
                for player_id, row in context.items()
                if bool(row["career_active"]) is is_active
            ]
            values = [
                primary_scores[spec.candidate_id][player_id]
                for player_id in members
                if primary_scores[spec.candidate_id][player_id] is not None
            ]
            active_career_audit.append(
                {
                    "candidate_id": spec.candidate_id,
                    "dimension": spec.dimension.value,
                    "cohort": cohort,
                    "players": len(members),
                    "score_available": len(values),
                    "score_available_pct": finite(len(values) / len(members)) if members else None,
                    "median_diagnostic_score": finite(statistics.median(values))
                    if values
                    else None,
                    "completeness_treatment": (
                        "TO_DATE_NO_PROJECTION_NO_COMPLETION_PENALTY"
                        if is_active
                        else "COMPLETE_OR_INDETERMINATE_AS_RECORDED"
                    ),
                }
            )
    stable_json(
        args.docs_root / "dimension-coverage-audit.json",
        {
            "methodology_version": DIMENSION_METHODOLOGY_VERSION,
            "confidence_thresholds": {
                "STRONG": "100%",
                "MODERATE": "75%-<100%",
                "LIMITED": ">0%-<75%",
                "UNAVAILABLE": "0%",
            },
            "coverage_is_not_score_penalty": True,
            "records": coverage_summary,
            "active_career_audit": active_career_audit,
        },
    )

    case_studies = []
    for player_id, row in context.items():
        if str(row["nba_player_id"]) not in CASE_STUDY_NBA_IDS:
            continue
        examples = []
        for candidate_id in (
            "PEAK-A",
            "PEAK-E",
            "LONGEVITY-B",
            "OFFENSE-C",
            "DEFENSE-B",
            "PLAYOFFS-E",
            "ACCOLADES-D",
            "WINNING-C",
            "ERA-E",
        ):
            value = primary_scores[candidate_id][player_id]
            spec = candidate_by_id[candidate_id]
            examples.append(
                {
                    "dimension": spec.dimension.value,
                    "candidate_id": candidate_id,
                    "diagnostic_value": finite(value),
                    "available_components": sum(
                        matrix[primitive.name][player_id] is not None
                        for primitive in spec.primitives
                    ),
                    "expected_components": len(spec.primitives),
                    "interpretation": (
                        "Change is driven by documented component availability and "
                        "candidate philosophy; no correctness judgment."
                    ),
                }
            )
        case_studies.append(
            {
                "player_id": player_id,
                "nba_player_id": row["nba_player_id"],
                "display_name": row["display_name"],
                "career_status": row["career_status"],
                "examples": examples,
            }
        )
    stable_json(
        args.docs_root / "dimension-case-studies.json",
        {
            "methodology_version": DIMENSION_METHODOLOGY_VERSION,
            "not_a_ranking": True,
            "players": sorted(case_studies, key=lambda row: str(row["nba_player_id"])),
        },
    )

    all_partitions = output_partitions + coverage_partitions + sensitivity_partitions
    output_fingerprint = hashlib.sha256(
        "\n".join(
            f"{item['path']}:{item['sha256']}"
            for item in sorted(all_partitions, key=lambda item: item["path"])
        ).encode()
    ).hexdigest()
    if args.expected_fingerprint and args.expected_fingerprint != output_fingerprint:
        raise ValueError(f"output fingerprint mismatch: {output_fingerprint}")
    report_paths = (
        args.docs_root / "goat-dimension-candidates.yaml",
        args.docs_root / "dimension-redundancy-audit.json",
        args.docs_root / "dimension-era-fairness.json",
        args.docs_root / "dimension-weight-sensitivity.json",
        args.docs_root / "dimension-coverage-audit.json",
        args.docs_root / "dimension-case-studies.json",
    )
    report_fingerprint = hashlib.sha256(
        "\n".join(f"{path.name}:{file_sha256(path)}" for path in report_paths).encode()
    ).hexdigest()
    measured_runtime = finite(time.perf_counter() - started)
    summary_path = args.docs_root / "dimension-candidate-summary.json"
    baseline_runtime = measured_runtime
    if summary_path.is_file():
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        if previous.get("output_fingerprint") == output_fingerprint:
            baseline_runtime = previous.get("runtime_seconds", measured_runtime)
    summary = {
        "step": "STEP-0012",
        "result": "PASS",
        "methodology_version": DIMENSION_METHODOLOGY_VERSION,
        "input_fingerprints": {
            "corpus": CORPUS_FINGERPRINT,
            "normalization": NORMALIZATION_FINGERPRINT,
            "career": CAREER_FINGERPRINT,
            "awards": AWARDS_FINGERPRINT,
            "team_success": TEAM_FINGERPRINT,
            "all_star_stat_leaders": ACCOLADE_FINGERPRINT,
        },
        "master_players": len(context),
        "career_status_counts": dict(
            sorted(Counter(str(row["career_status"]) for row in context.values()).items())
        ),
        "analytical_populations": {name: len(players) for name, players in populations.items()},
        "dimensions": len(Dimension),
        "candidate_definitions": len(specs),
        "candidate_status_counts": dict(
            sorted(Counter(status.value for status, _ in initial_status.values()).items())
        ),
        "scaling_methods": [method.value for method in ScalingMethod],
        "missingness_policies": [policy.value for policy in MissingnessPolicy],
        "random_seed": MONTE_CARLO_SEED,
        "monte_carlo_samples_per_candidate": MONTE_CARLO_SAMPLES,
        "score_rows": sum(item["rows"] for item in output_partitions),
        "coverage_rows": sum(item["rows"] for item in coverage_partitions),
        "sensitivity_rows": sum(item["rows"] for item in sensitivity_partitions),
        "output_partitions": len(all_partitions),
        "output_size_bytes": sum(item["size_bytes"] for item in all_partitions),
        "output_fingerprint": output_fingerprint,
        "committed_report_fingerprint": report_fingerprint,
        "runtime_seconds": baseline_runtime,
        "runtime_definition": "baseline successful build; preserved across identical rebuilds",
        "cache_only_rebuild_verified": True,
        "run_at": args.run_at,
        "no_overall_score": True,
        "no_player_ordering_report": True,
        "final_candidate_count": 0,
        "partitions": sorted(all_partitions, key=lambda item: item["path"]),
    }
    stable_json(summary_path, summary)
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "result",
                    "candidate_definitions",
                    "score_rows",
                    "output_fingerprint",
                    "runtime_seconds",
                )
            },
            sort_keys=True,
        )
    )
    return summary


if __name__ == "__main__":
    build(parse_args())
