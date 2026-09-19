#!/usr/bin/env python3
"""Package the frozen STEP-0015O distributions into an immutable STEP-0016 release.

Run offline: PYTHONPATH=src:. .venv/bin/python -m pipelines.product.build_probabilistic_leaderboard
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.dataset as ds
import yaml

from goatlab.product.build import (
    DIMENSION_NAMES,
    OVERALL_VERSION,
    POLICY_VERSION,
    PRODUCT_VERSION,
    RELEASE_GENERATED_AT,
    RELEASE_ID,
    build_records,
    canonical_json,
    canonical_jsonl,
    immutable_write,
    paired_draw_bytes,
    parquet_bytes,
    sha256,
)
from goatlab.product.models import RankingRelease
from goatlab.rankings.interval_native import rank_draw_matrix
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_interval_native_ranking_policy import (
    STEP_N_FINGERPRINT,
    actual_ranking_audit,
    verify_step_n,
)
from pipelines.rankings.audit_overall_v2_promotion import (
    actual_audit,
    dimension_index,
    reconstruct_and_load,
    target_matrices,
    validation,
)
from pipelines.rankings.audit_peak_longevity_uncertainty import _load_reference_flags
from pipelines.rankings.audit_peak_v1 import file_hash

ROOT = Path(__file__).resolve().parents[2]
FROZEN_RANK_FINGERPRINT = "544843af8d316c6b5d54786b29562451ce01e3f6b5c35a0fe936e27fa2290a15"
FROZEN_RANK_PARQUET_HASH = "dcda3c3a94ca3a9a866f3de0a8ced0d9411383ca30682b789eb42c259c7c9af4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/product")
    parser.add_argument("--expected-fingerprint")
    return parser.parse_args()


def _frozen_checks(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, str]]:
    governance = json.loads((args.docs_root / "step-0015p-governance-summary.json").read_text())
    if governance["ranking_policy_version"] != POLICY_VERSION:
        raise ValueError("STEP-0015P governance version differs")
    for relative, expected in governance["frozen_file_sha256"].items():
        if file_hash(ROOT / relative) != expected:
            raise ValueError(f"frozen upstream hash mismatch: {relative}")
    rank_summary = json.loads(
        (args.docs_root / "interval-native-ranking-policy-summary.json").read_text()
    )
    rank_path = (
        args.gold_root
        / "interval_native_ranking_policy_audit/distribution-rankable-player-ranks.parquet"
    )
    if rank_summary["output_fingerprint"] != FROZEN_RANK_FINGERPRINT:
        raise ValueError("STEP-0015O audit fingerprint differs")
    if file_hash(rank_path) != FROZEN_RANK_PARQUET_HASH:
        raise ValueError("STEP-0015O rank rows differ")
    if rank_summary["rankability"]["ALL_PLAYERS"] != {
        "population": 5103,
        "distribution_rankable": 1882,
        "not_rankable": 3221,
    }:
        raise ValueError("STEP-0015O frozen population differs")
    with (args.docs_root / "goatlab-v1-ranking-policy-v2-probabilistic.yaml").open() as handle:
        policy = yaml.safe_load(handle)
    if policy["policy_version"] != POLICY_VERSION or policy["navigation"]["sort"] != (
        "median_rank_ascending_then_canonical_player_id"
    ):
        raise ValueError("publication policy registry differs")
    n = verify_step_n(args)
    frozen = reconstruct_and_load(args)
    hashes = {
        "step_0015n_fingerprint": STEP_N_FINGERPRINT,
        "step_0015o_fingerprint": FROZEN_RANK_FINGERPRINT,
        "step_0015p_governance_fingerprint": governance["governance_fingerprint"],
        "step_0015o_rank_parquet": FROZEN_RANK_PARQUET_HASH,
        **{key: value for key, value in frozen["hashes"].items()},
        "step_0015n_player_parquet": file_hash(n["paths"]["players"]),
        "career_summary_tree": _directory_fingerprint(args.gold_root / "player_career_summary"),
    }
    return {"n": n, "frozen": frozen, "rank_path": rank_path, "policy": policy}, hashes


def _directory_fingerprint(path: Path) -> str:
    files = sorted(path.rglob("*.parquet"))
    if not files:
        raise ValueError(f"missing canonical career source: {path}")
    pairs = [(str(file.relative_to(path)), file_hash(file)) for file in files]
    return sha256(canonical_json(pairs))


def _exact_reconstruction(
    reconstructed: list[dict[str, Any]], stored: list[dict[str, Any]]
) -> dict[str, int | float]:
    expected = {str(row["player_id"]): row for row in stored}
    observed = {str(row["player_id"]): row for row in reconstructed}
    if len(expected) != len(stored) or set(expected) != set(observed):
        raise ValueError("frozen STEP-0015O population cannot be reconstructed")
    mismatch_count = 0
    max_numeric_difference = 0.0
    for player_id, original in expected.items():
        current = observed[player_id]
        if not set(current) <= set(original):
            raise ValueError(f"reconstructed columns add unknown fields for {player_id}")
        for key, value in original.items():
            compare = current.get(key)
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                if compare is None:
                    mismatch_count += 1
                    continue
                difference = abs(float(compare) - float(value))
                max_numeric_difference = max(max_numeric_difference, difference)
                mismatch_count += difference != 0.0
            else:
                mismatch_count += compare != value
    if mismatch_count:
        raise ValueError(
            f"STEP-0015O exact reconstruction failed: {mismatch_count} mismatches; "
            f"maximum numeric difference {max_numeric_difference}"
        )
    return {
        "players": len(expected),
        "field_mismatches": mismatch_count,
        "maximum_numeric_difference": max_numeric_difference,
    }


def _replay_frozen_draws(
    args: argparse.Namespace, frozen: dict[str, Any], rank_path: Path
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray], dict[str, int | float]]:
    paths = frozen["paths"]
    anchors = read_rows(paths["anchors"])
    dimensions = dimension_index(read_rows(paths["dimensions"]))
    defense_validation = read_rows(paths["defense_validation"])
    selected_linkers = json.loads(
        (args.docs_root / "player-season-value-measurement-linking-summary.json").read_text()
    )["selected_linkers"]
    matrices, _ = target_matrices(args.docs_root)
    _, _, point_eligible, overall_interval_deployment, internals = validation(
        anchors, selected_linkers, dimensions, defense_validation, matrices
    )
    season_contract = read_rows(paths["season_contract"])
    peaks = {str(row["player_id"]): row for row in read_rows(paths["peak"])}
    longevity = {str(row["player_id"]): row for row in read_rows(paths["longevity"])}
    defense = {str(row["player_id"]): row for row in read_rows(paths["defense"])}
    l_index = {str(row["player_id"]): row for row in read_rows(paths["overall_l"])}
    _, flags = _load_reference_flags(args.gold_root)
    actual_rows, actual_draws, _ = actual_audit(
        season_contract,
        peaks,
        longevity,
        defense,
        dimensions,
        flags,
        internals["library"],
        internals["residual_pools"],
        matrices,
        point_eligible,
        overall_interval_deployment,
        l_index,
    )
    stored_n = read_rows(
        args.gold_root / "overall_v2_promotion_audit/overall-v2-player-scores.parquet"
    )
    reconstruction_n = _exact_reconstruction(actual_rows, stored_n)
    report = json.loads((args.docs_root / "rank-band-calibration.json").read_text())
    deployment = {
        pattern: {
            int(level): float(value)
            for level, value in details["deployment_offsets_percentile"].items()
        }
        for pattern, details in report["patterns"].items()
    }
    rank_rows, _, _, _ = actual_ranking_audit(actual_rows, actual_draws, deployment)
    reconstruction_o = _exact_reconstruction(rank_rows, read_rows(rank_path))
    return (
        rank_rows,
        actual_draws,
        {
            "step_0015n_players": reconstruction_n["players"],
            "step_0015n_mismatches": reconstruction_n["field_mismatches"],
            "step_0015n_max_difference": reconstruction_n["maximum_numeric_difference"],
            "step_0015o_rankable_players": reconstruction_o["players"],
            "step_0015o_mismatches": reconstruction_o["field_mismatches"],
            "step_0015o_max_difference": reconstruction_o["maximum_numeric_difference"],
        },
    )


def _model_rows(models: list[Any]) -> list[dict[str, Any]]:
    return [model.model_dump(mode="json") for model in models]


def _build_product_bytes(
    args: argparse.Namespace,
    rank_rows: list[dict[str, Any]],
    actual_draws: dict[str, np.ndarray],
    frozen: dict[str, Any],
    policy: dict[str, Any],
    upstream: dict[str, str],
    reconstruction: dict[str, int | float],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    paths = frozen["paths"]
    draw_ids = sorted(actual_draws)
    overall_draws = np.vstack([actual_draws[player_id] for player_id in draw_ids])
    rank_draws = rank_draw_matrix(overall_draws)
    paired = paired_draw_bytes(draw_ids, overall_draws, rank_draws)
    paired_hash = sha256(paired)
    career_rows = (
        ds.dataset(args.gold_root / "player_career_summary", format="parquet")
        .to_table()
        .to_pylist()
    )
    overall_rows = read_rows(
        args.gold_root / "overall_v2_promotion_audit/overall-v2-player-scores.parquet"
    )
    identities, entries, profiles = build_records(
        rank_rows,
        overall_rows,
        career_rows,
        read_rows(paths["peak"]),
        read_rows(paths["longevity"]),
        read_rows(paths["defense"]),
        read_rows(paths["dimensions"]),
        paired_hash,
    )
    if draw_ids != sorted(entry.player_id for entry in entries):
        raise ValueError("paired serving draws do not match leaderboard player IDs")
    v1_top100 = {str(row["player_id"]) for row in read_rows(paths["top100_v1"])}
    if len(v1_top100) != 100 or not v1_top100 <= set(draw_ids):
        raise ValueError("archived V1 Top 100 are not all distribution-rankable")
    entry_rows = _model_rows(entries)
    profile_rows = _model_rows(profiles)
    identity_rows = _model_rows(identities)
    top100 = [
        {
            "release_id": row["release_id"],
            "display_position": row["display_position"],
            "display_position_semantics": row["display_position_semantics"],
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "active": row["active"],
            "median_rank": row["rank"]["median_rank"],
            "rank_lower_80": row["rank"]["lower_80"],
            "rank_upper_80": row["rank"]["upper_80"],
            "rank_lower_90": row["rank"]["lower_90"],
            "rank_upper_90": row["rank"]["upper_90"],
            "top_10_probability": row["top_n"]["top_10"],
            "top_25_probability": row["top_n"]["top_25"],
            "top_50_probability": row["top_n"]["top_50"],
            "top_100_probability": row["top_n"]["top_100"],
            "top100_membership": row["top100_membership"],
            "ranking_status": row["ranking_status"],
            "overall_lower_90": row["overall"]["lower_90"],
            "overall_upper_90": row["overall"]["upper_90"],
            "overall_center": row["overall"]["center"],
            "overall_center_semantics": row["overall"]["center_semantics"],
            "ranking_policy_version": row["ranking_policy_version"],
            "cutoff_season": row["cutoff_season"],
        }
        for row in entry_rows[:100]
    ]
    if len(top100) != 100 or [row["display_position"] for row in top100] != list(range(1, 101)):
        raise ValueError("Top-100 navigation view is incomplete")
    bubble = [
        {
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "display_position": row["display_position"],
            "top_100_probability": row["top_n"]["top_100"],
            "membership_label": row["top100_membership"],
            "rank_lower_90": row["rank"]["lower_90"],
            "rank_upper_90": row["rank"]["upper_90"],
            "in_display_top100": row["display_position"] <= 100,
        }
        for row in entry_rows
        if 0.10 <= row["top_n"]["top_100"] < 0.90
        and row["rank"]["lower_90"] <= 100 <= row["rank"]["upper_90"]
    ]
    methodology = {
        "release_id": RELEASE_ID,
        "product_contract_version": PRODUCT_VERSION,
        "overall_substrate_version": OVERALL_VERSION,
        "overall_exact_point_promoted": False,
        "ranking_policy": policy,
        "dimension_methodology_versions": profiles[0].methodology_versions,
        "cutoff_season": "2025-26",
        "active_career_policy": "TO_DATE_NO_PROJECTION",
        "probabilities_conditional_on_frozen_architecture": True,
        "shared_cross_player_calibration_uncertainty_modeled": False,
        "distribution_storage": (
            "versioned paired-overall-rank-draws.npz with compact database summaries"
        ),
        "pairwise_strategy": "on-demand shared-draw comparison; symmetric half-tie convention",
        "source_corpus_fingerprint": read_rows(paths["dimensions"], ["corpus_fingerprint"])[0][
            "corpus_fingerprint"
        ],
        "disclosures": {
            "display_rank": (
                "Display rank summarizes a probability distribution; nearby players may not be "
                "definitively ordered."
            ),
            "rank_band_90": (
                "Under GOATLab's measurement uncertainty, rank falls in this band in 90% of "
                "simulated outcomes, conditional on the frozen methodology."
            ),
            "wider_uncertainty": (
                "Wider uncertainty reflects weaker historical measurement, "
                "not lower player quality."
            ),
            "interval_native": (
                "A range is shown because the evidence does not support an exact point claim."
            ),
            "unavailable": (
                "Insufficient evidence for a calibrated Overall distribution; not ranked."
            ),
            "product_position": (
                "Top-100 display positions are navigational summaries, not exact scientific "
                "ordering."
            ),
        },
    }
    db_players = [
        {
            "release_id": RELEASE_ID,
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "search_name": row["search_name"],
            "career_state": row["career_state"],
            "career_start_season": row["career_start_season"],
            "career_end_season": row["career_end_season"],
            "latest_season_used": row["latest_season_used"],
        }
        for row in identity_rows
    ]
    db_versions = [
        {
            "release_id": RELEASE_ID,
            "generated_at_utc": RELEASE_GENERATED_AT,
            "cutoff_season": "2025-26",
            "ranking_policy_version": POLICY_VERSION,
            "overall_substrate_version": OVERALL_VERSION,
            "source_ranking_fingerprint": upstream["step_0015o_fingerprint"],
            "exact_overall_point_promoted": False,
        }
    ]
    db_rankings = [
        {
            "release_id": RELEASE_ID,
            "player_id": row["player_id"],
            "display_position": row["display_position"],
            "ranking_status": row["ranking_status"],
            "overall_source_status": row["overall_source_status"],
            "overall_center": row["overall"]["center"],
            "overall_json": json.dumps(row["overall"], sort_keys=True, separators=(",", ":")),
            "rank_json": json.dumps(row["rank"], sort_keys=True, separators=(",", ":")),
            "distribution_ref": row["overall"]["distribution_ref"],
            "distribution_fingerprint": row["overall"]["distribution_fingerprint"],
        }
        for row in entry_rows
    ]
    db_probabilities = [
        {
            "release_id": RELEASE_ID,
            "player_id": row["player_id"],
            **row["top_n"],
            "top100_membership": row["top100_membership"],
        }
        for row in entry_rows
    ]
    db_dimensions = [
        {
            "release_id": RELEASE_ID,
            "player_id": profile["identity"]["player_id"],
            "dimension": name,
            "status": details["status"],
            "point_value": details["point_value"],
            "diagnostic_center": details["diagnostic_center"],
            "lower_90": details["lower_90"],
            "upper_90": details["upper_90"],
            "methodology_version": details["methodology_version"],
            "confidence": details["confidence"],
            "reason_codes_json": json.dumps(details["reason_codes"], separators=(",", ":")),
            "evidence_metadata_json": json.dumps(
                details["evidence_metadata"], sort_keys=True, separators=(",", ":")
            ),
        }
        for profile in profile_rows
        for name, details in profile["dimensions"].items()
    ]
    if len(db_dimensions) != len(profile_rows) * len(DIMENSION_NAMES):
        raise ValueError("database dimension count differs")
    unranked = [
        {
            "player_id": profile["identity"]["player_id"],
            "player_name": profile["identity"]["player_name"],
            "ranking_status": "UNAVAILABLE",
            "overall_source_status": "OVERALL_UNAVAILABLE",
            "reason_codes": profile["reason_codes"],
        }
        for profile in profile_rows
        if profile["leaderboard"] is None
    ]
    files = {
        "paired-overall-rank-draws.npz": paired,
        "players.jsonl": canonical_jsonl(identity_rows),
        "leaderboard.json": canonical_json(entry_rows),
        "leaderboard-v2-probabilistic.json": canonical_json(top100),
        "top100-bubble.json": canonical_json(bubble),
        "player-profiles.jsonl": canonical_jsonl(profile_rows),
        "unranked.jsonl": canonical_jsonl(unranked),
        "methodology-metadata.json": canonical_json(methodology),
        "db/players.parquet": parquet_bytes(db_players),
        "db/ranking_versions.parquet": parquet_bytes(db_versions),
        "db/player_rankings.parquet": parquet_bytes(db_rankings),
        "db/player_rank_probabilities.parquet": parquet_bytes(db_probabilities),
        "db/player_dimensions.parquet": parquet_bytes(db_dimensions),
    }
    summary = {
        "release_id": RELEASE_ID,
        "upstream_reconstruction": reconstruction,
        "total_players": len(identities),
        "distribution_rankable": len(entries),
        "unavailable": len(unranked),
        "archived_v1_top100_rankable": len(v1_top100),
        "top100_entries": len(top100),
        "top100_statuses": dict(sorted(Counter(row["ranking_status"] for row in top100).items())),
        "top100_membership_classes": dict(
            sorted(Counter(row["top100_membership"] for row in top100).items())
        ),
        "top100_probability_min": min(row["top_100_probability"] for row in top100),
        "top100_probability_max": max(row["top_100_probability"] for row in top100),
        "top100_90_band_mean_width": float(
            np.mean([row["rank_upper_90"] - row["rank_lower_90"] for row in top100])
        ),
        "boundary_rows": len(bubble),
        "boundary_outside_display_top100": sum(not row["in_display_top100"] for row in bubble),
        "pairwise_unique_unordered_pairs": len(entries) * (len(entries) - 1) // 2,
        "network_requests": 0,
        "research_draws_exposed_by_api": False,
        "production_contains_raw_vendor_payloads": False,
        "artifact_sizes_bytes": {name: len(data) for name, data in sorted(files.items())},
    }
    return files, summary


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    frozen, upstream = _frozen_checks(args)
    rank_rows, draws, reconstruction = _replay_frozen_draws(
        args, frozen["frozen"], frozen["rank_path"]
    )
    files, summary = _build_product_bytes(
        args, rank_rows, draws, frozen["frozen"], frozen["policy"], upstream, reconstruction
    )
    artifact_hashes = {name: sha256(data) for name, data in sorted(files.items())}
    release_body = {
        "release_id": RELEASE_ID,
        "generated_at_utc": RELEASE_GENERATED_AT,
        "cutoff_season": "2025-26",
        "player_count": 5103,
        "rankable_count": 1882,
        "unavailable_count": 3221,
        "ranking_policy_version": POLICY_VERSION,
        "overall_substrate_version": OVERALL_VERSION,
        "exact_overall_point_promoted": False,
        "artifact_sha256": artifact_hashes,
        "upstream_sha256": upstream,
    }
    release_fingerprint = sha256(canonical_json(release_body))
    release = RankingRelease.model_validate(
        {**release_body, "release_fingerprint": release_fingerprint}
    )
    files["ranking-release-manifest.json"] = canonical_json(release.model_dump(mode="json"))
    summary["release_fingerprint"] = release_fingerprint
    summary["artifact_sizes_bytes"]["ranking-release-manifest.json"] = len(
        files["ranking-release-manifest.json"]
    )
    files["product-build-summary.json"] = canonical_json(summary)
    release_dir = args.output_root / RELEASE_ID
    if args.expected_fingerprint and release_fingerprint != args.expected_fingerprint:
        raise ValueError("release fingerprint differs from requested fingerprint")
    new_files = sum(
        immutable_write(release_dir / name, data) for name, data in sorted(files.items())
    )
    print(
        json.dumps(
            {
                "release_id": RELEASE_ID,
                "release_fingerprint": release_fingerprint,
                "new_files": new_files,
                "artifact_count": len(files),
                "runtime_seconds": round(time.perf_counter() - started, 3),
                "summary": summary,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
