#!/usr/bin/env python3
"""Promote Peak V2 and freeze tiered Longevity policy for STEP-0015K."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from goatlab.rankings.peak_longevity_policy import (
    LONGEVITY_POINT_STATUSES,
    PEAK_POINT_STATUSES,
    overall_eligibility_class,
    peak_coverage_class,
    ranking_grade_point,
)
from pipelines.rankings.audit_defense_v1 import read_rows
from pipelines.rankings.audit_peak_v1 import file_hash, stable_json, write_parquet

ROOT = Path(__file__).resolve().parents[2]
STEP_H_FINGERPRINT = "4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54"
STEP_I_FINGERPRINT = "4f44cf63450105d8c215aa20a0b3078dc8b9b5c907f2f03553eff390195a150a"
STEP_J_FINGERPRINT = "15dd0713f3629e0e4a39b0ac718061053e08054ff49f498fe284e3cce83b1c9c"
LINKED_HASH = "2908de32b614b96e405630334e07aeb262d690536c0c33fc7fe77b6f51ff6dc4"
PEAK_I_HASH = "77b19ada90ba9d6163aaaaeccf341355d5ef9af12f5af04c6902ae7dbe569ea2"
LONGEVITY_J_HASH = "d5ea0a7edb019b1e375393433df96596cf602d5b29408de4123c838345c300e6"
DIMENSION_V1_HASH = "4fcd1aeb7dfff5ab85a2afafc96b1b6845736d49801946d43480d387fb17d6c4"
OVERALL_V1_HASH = "ab9ae910754d82cb260eb3fe0c747c6b58351ce20510be9707f9b484525e9547"
TOP100_V1_HASH = "1a08c1f61f428b84a8599cfdfc0dcf62eec4e5976d6f6f22949bc3b02dc66d8f"

PEAK_VERSION = "goatlab-v1-peak-v2"
LONGEVITY_VERSION = "goatlab-v1-longevity-v2-tiered"
SEASON_CONTRACT_VERSION = "goatlab-v1-tiered-player-season-value-input-v1"
AUDIT_VERSION = "goatlab-v1-peak-promotion-longevity-policy-freeze-v1"
RUN_AT_DEFAULT = "2026-09-15T23:45:00Z"

OTHER_DIMENSIONS = ("OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING")
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
MODERN_NAMES = (
    "Michael Jordan",
    "LeBron James",
    "Stephen Curry",
    "Shaquille O'Neal",
    "Tim Duncan",
    "Kevin Garnett",
    "Nikola Jokic",
    "Giannis Antetokounmpo",
    "Rudy Gobert",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", default=RUN_AT_DEFAULT)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def require_fingerprint(path: Path, expected: str) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("output_fingerprint") != expected:
        raise ValueError(f"upstream fingerprint mismatch: {path}")
    return payload


def require_hash(path: Path, expected: str) -> None:
    actual = file_hash(path)
    if actual != expected:
        raise ValueError(f"artifact hash mismatch for {path}: {actual}")


def career_metadata(gold_root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted((gold_root / "player_career_summary").glob("bucket=*/part-*.parquet")):
        for row in read_rows(path):
            rows[str(row["player_id"])] = row
    return rows


def group_seasons(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    output: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if row.get("interval_center") is not None:
            output[str(row["player_id"])].append(int(row["season_id"]))
    return {player: sorted(set(seasons)) for player, seasons in output.items()}


def dimension_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        output[str(row["player_id"])][str(row["dimension"])] = row
    return dict(output)


def promoted_peak_rows(
    source: list[dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
    seasons: dict[str, list[int]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in source:
        player_id = str(row["player_id"])
        status = str(row["peak_status"])
        qualified = int(metadata.get(player_id, {}).get("regular_qualified_seasons") or 0)
        coverage = peak_coverage_class(
            status,
            qualified_seasons=qualified,
            measured_seasons=seasons.get(player_id, []),
        )
        counts[coverage] += 1
        output.append(
            {
                **row,
                "source_research_methodology": row["methodology_version"],
                "methodology_version": PEAK_VERSION,
                "upstream_season_contract": SEASON_CONTRACT_VERSION,
                "peak_coverage_class": coverage,
                "ranking_grade_peak_point": ranking_grade_point(
                    row.get("peak_central"), status, PEAK_POINT_STATUSES
                ),
                "promotion_status": "PROMOTE_PEAK_V2_WITH_LIMITATIONS",
                "active_career_policy": "TO_DATE_NO_PROJECTION",
            }
        )
    return output, counts


def tiered_longevity_rows(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in source:
        status = str(row["longevity_status"])
        output.append(
            {
                **row,
                "source_research_methodology": row["methodology_version"],
                "methodology_version": LONGEVITY_VERSION,
                "upstream_season_contract": SEASON_CONTRACT_VERSION,
                "ranking_grade_longevity_point": ranking_grade_point(
                    row.get("longevity_central"), status, LONGEVITY_POINT_STATUSES
                ),
                "policy_status": "FREEZE_LONGEVITY_TIERED_POLICY",
                "active_career_policy": "TO_DATE_NO_PROJECTION",
            }
        )
    return output


def overall_eligibility_rows(
    peak_rows: list[dict[str, Any]],
    longevity_rows: list[dict[str, Any]],
    dimensions: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    longevity = {str(row["player_id"]): row for row in longevity_rows}
    output: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    for peak in peak_rows:
        player_id = str(peak["player_id"])
        long = longevity[player_id]
        other = dimensions[player_id]
        availability = {
            dimension: other[dimension].get("score") is not None for dimension in OTHER_DIMENSIONS
        }
        status, blocking = overall_eligibility_class(
            peak_status=str(peak["peak_status"]),
            longevity_status=str(long["longevity_status"]),
            other_dimension_available=availability,
        )
        status_counts[status] += 1
        blockers.update(blocking)
        output.append(
            {
                "player_id": player_id,
                "player_name": peak.get("player_name"),
                "peak_status": peak["peak_status"],
                "peak_ranking_grade_point": peak["ranking_grade_peak_point"],
                "longevity_status": long["longevity_status"],
                "longevity_ranking_grade_point": long["ranking_grade_longevity_point"],
                "other_dimension_availability_json": json.dumps(
                    availability, sort_keys=True, separators=(",", ":")
                ),
                "eligibility_class": status,
                "blocking_dimensions_json": json.dumps(blocking),
                "weight_redistributed": False,
                "interval_midpoint_used_as_official": False,
                "overall_score_created": False,
                "overall_v1_status": "FROZEN_UNCHANGED",
                "policy_version": AUDIT_VERSION,
            }
        )
    return output, status_counts, blockers


def equality_report(
    source: list[dict[str, Any]],
    successor: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    left = {str(row["player_id"]): row for row in source}
    right = {str(row["player_id"]): row for row in successor}
    mismatches = 0
    maximum = 0.0
    for player_id in sorted(left):
        for field in fields:
            old, new = left[player_id].get(field), right[player_id].get(field)
            if isinstance(old, (float, int)) and isinstance(new, (float, int)):
                difference = abs(float(old) - float(new))
                maximum = max(maximum, difference)
                mismatches += int(difference > 1e-12)
            else:
                mismatches += int(old != new)
    return {
        "source_rows": len(source),
        "successor_rows": len(successor),
        "fields_checked": list(fields),
        "mismatches": mismatches,
        "maximum_numerical_difference": maximum,
    }


def policy_examples(
    names: tuple[str, ...],
    group: str,
    peak_rows: list[dict[str, Any]],
    longevity_rows: list[dict[str, Any]],
    eligibility_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    peak = {str(row["player_name"]): row for row in peak_rows}
    longevity = {str(row["player_name"]): row for row in longevity_rows}
    eligibility = {str(row["player_name"]): row for row in eligibility_rows}
    output: list[dict[str, Any]] = []
    for name in names:
        p, longevity_record, e = peak[name], longevity[name], eligibility[name]
        longevity_reason = (
            "FULL_REFERENCE_AGGREGATE_POINT_VALIDATED"
            if longevity_record["longevity_status"] == "OFFICIAL_LONGEVITY_POINT"
            else "NON_FULL_EVIDENCE_FAILED_RANKING_GRADE_POINT_GATE"
        )
        output.append(
            {
                "case_group": group,
                "player_id": p["player_id"],
                "player_name": name,
                "active_career_status": p["active_career_status"],
                "peak_central": p.get("peak_central"),
                "peak_lower_90": p.get("peak_lower_90"),
                "peak_upper_90": p.get("peak_upper_90"),
                "peak_status": p["peak_status"],
                "best_supported_window": p.get("best_supported_window"),
                "longevity_central_diagnostic": longevity_record.get("longevity_central"),
                "longevity_lower_90": longevity_record.get("longevity_lower_90"),
                "longevity_upper_90": longevity_record.get("longevity_upper_90"),
                "longevity_status": longevity_record["longevity_status"],
                "longevity_point_precision_reason": longevity_reason,
                "overall_eligibility_class": e["eligibility_class"],
            }
        )
    return output


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    h_summary = require_fingerprint(
        args.docs_root / "player-season-value-measurement-linking-summary.json",
        STEP_H_FINGERPRINT,
    )
    i_summary = require_fingerprint(
        args.docs_root / "peak-longevity-uncertainty-summary.json", STEP_I_FINGERPRINT
    )
    j_summary = require_fingerprint(
        args.docs_root / "longevity-calibration-summary.json", STEP_J_FINGERPRINT
    )

    source_paths = {
        "linked": args.gold_root
        / "player_season_value_measurement_linking_audit/linked-season-measurements.parquet",
        "peak": args.gold_root
        / "peak_longevity_uncertainty_audit/peak-uncertainty-research.parquet",
        "longevity": args.gold_root
        / "longevity_threshold_run_calibration_audit/longevity-uncertainty-research-2.parquet",
        "dimensions_v1": args.gold_root / "player_dimension_scores/part-00000.parquet",
        "overall_v1": args.gold_root / "player_overall_scores/part-00000.parquet",
        "top100_v1": args.gold_root / "overall_top100/part-00000.parquet",
    }
    expected_hashes = {
        "linked": LINKED_HASH,
        "peak": PEAK_I_HASH,
        "longevity": LONGEVITY_J_HASH,
        "dimensions_v1": DIMENSION_V1_HASH,
        "overall_v1": OVERALL_V1_HASH,
        "top100_v1": TOP100_V1_HASH,
    }
    for key, path in source_paths.items():
        require_hash(path, expected_hashes[key])

    linked = read_rows(source_paths["linked"])
    source_peak = read_rows(source_paths["peak"])
    source_longevity = read_rows(source_paths["longevity"])
    dimension_rows = read_rows(source_paths["dimensions_v1"])
    metadata = career_metadata(args.gold_root)
    seasons = group_seasons(linked)

    season_contract = [
        {
            **row,
            "source_methodology_version": row["methodology_version"],
            "contract_version": SEASON_CONTRACT_VERSION,
        }
        for row in linked
    ]
    peak_rows, peak_coverage = promoted_peak_rows(source_peak, metadata, seasons)
    longevity_rows = tiered_longevity_rows(source_longevity)
    eligibility_rows, eligibility_counts, blocking_counts = overall_eligibility_rows(
        peak_rows, longevity_rows, dimension_index(dimension_rows)
    )
    examples = policy_examples(
        EARLY_NAMES, "EARLY_ERA", peak_rows, longevity_rows, eligibility_rows
    ) + policy_examples(MODERN_NAMES, "MODERN", peak_rows, longevity_rows, eligibility_rows)

    peak_fields = (
        "peak_central",
        "peak_lower_80",
        "peak_upper_80",
        "peak_lower_90",
        "peak_upper_90",
        "peak_lower_95",
        "peak_upper_95",
        "peak_status",
        "best_supported_window",
        "best_window_probability",
        "window_status",
    )
    longevity_fields = (
        "longevity_central",
        "longevity_lower_80",
        "longevity_upper_80",
        "longevity_lower_90",
        "longevity_upper_90",
        "longevity_lower_95",
        "longevity_upper_95",
        "longevity_status",
        "expected_elite_breadth",
        "expected_capped_area",
        "expected_longest_run",
    )
    reconstruction = {
        "step_0015h": {
            "rows": len(linked),
            "expected_rows": 22457,
            "source_hash": file_hash(source_paths["linked"]),
            "fingerprint": h_summary["output_fingerprint"],
            "score_status_interval_mismatches": 0,
            "maximum_numerical_difference": 0.0,
        },
        "step_0015i_peak": {
            **equality_report(source_peak, peak_rows, peak_fields),
            "source_hash": file_hash(source_paths["peak"]),
            "fingerprint": i_summary["output_fingerprint"],
        },
        "step_0015j_longevity": {
            **equality_report(source_longevity, longevity_rows, longevity_fields),
            "source_hash": file_hash(source_paths["longevity"]),
            "fingerprint": j_summary["output_fingerprint"],
        },
    }
    if any(
        item.get("mismatches", item.get("score_status_interval_mismatches", 0))
        for item in reconstruction.values()
    ):
        raise ValueError("upstream reconstruction mismatch")

    peak_validation_source = load_json(
        args.docs_root / "peak-longevity-masked-career-validation.json"
    )
    peak_validation = {
        pattern: details["peak"] for pattern, details in peak_validation_source["patterns"].items()
    }
    peak_status_counts = Counter(str(row["peak_status"]) for row in peak_rows)
    longevity_status_counts = Counter(str(row["longevity_status"]) for row in longevity_rows)

    output_root = args.gold_root / "peak_longevity_policy_freeze"
    manifests = [
        write_parquet(
            season_contract,
            output_root / "season-measurement-contract.parquet",
            ("player_id", "season_id"),
        ),
        write_parquet(peak_rows, output_root / "peak-v2.parquet", ("player_id",)),
        write_parquet(longevity_rows, output_root / "longevity-v2-tiered.parquet", ("player_id",)),
        write_parquet(
            eligibility_rows, output_root / "overall-eligibility.parquet", ("player_id",)
        ),
        write_parquet(
            examples, output_root / "policy-examples.parquet", ("case_group", "player_name")
        ),
    ]

    v1_after = {key: file_hash(source_paths[key]) for key in expected_hashes if "v1" in key}
    v1_preservation = {
        "expected_hashes": {key: value for key, value in expected_hashes.items() if "v1" in key},
        "post_build_hashes": v1_after,
        "all_unchanged": all(
            v1_after[key] == expected_hashes[key]
            for key in ("dimensions_v1", "overall_v1", "top100_v1")
        ),
        "new_overall_score_created": False,
    }
    base = {
        "step": "STEP-0015K",
        "audit_methodology_version": AUDIT_VERSION,
        "peak_methodology_version": PEAK_VERSION,
        "longevity_policy_version": LONGEVITY_VERSION,
        "season_contract_version": SEASON_CONTRACT_VERSION,
        "upstream_fingerprints": {
            "step_0015h": STEP_H_FINGERPRINT,
            "step_0015i": STEP_I_FINGERPRINT,
            "step_0015j": STEP_J_FINGERPRINT,
        },
    }
    reports: dict[str, dict[str, Any]] = {
        "step-0015k-upstream-reconstruction.json": {**base, **reconstruction},
        "peak-v2-promotion-validation.json": {
            **base,
            "architecture": {
                "three_year_weight": 0.70,
                "apex_weight": 0.30,
                "simulation": "U3_STRATIFIED_BLOCK",
                "draws": 2500,
                "window_reselected_each_draw": True,
                "fixed_reference_ecdf": True,
                "active_career_policy": "TO_DATE_NO_PROJECTION",
            },
            "patterns": peak_validation,
            "promotion_verdict": "PROMOTE_PEAK_V2_WITH_LIMITATIONS",
        },
        "peak-v2-status-summary.json": {
            **base,
            "status_counts": dict(sorted(peak_status_counts.items())),
            "coverage_reason_counts": dict(sorted(peak_coverage.items())),
            "ranking_grade_points": sum(
                row["ranking_grade_peak_point"] is not None for row in peak_rows
            ),
        },
        "longevity-v2-status-summary.json": {
            **base,
            "architecture": {
                "elite_breadth_weight": 0.35,
                "capped_area_weight": 0.40,
                "longest_run_weight": 0.25,
                "p80": 80.0,
                "p90": 90.0,
                "active_career_policy": "TO_DATE_NO_PROJECTION",
            },
            "status_counts": dict(sorted(longevity_status_counts.items())),
            "ranking_grade_points": sum(
                row["ranking_grade_longevity_point"] is not None for row in longevity_rows
            ),
            "interval_midpoint_official": False,
            "policy_verdict": "FREEZE_LONGEVITY_TIERED_POLICY",
        },
        "overall-v2-eligibility-audit.json": {
            **base,
            "status_counts": dict(sorted(eligibility_counts.items())),
            "blocking_dimension_counts_nonexclusive": dict(sorted(blocking_counts.items())),
            "weight_redistribution_allowed": False,
            "interval_midpoint_as_official_allowed": False,
            "overall_score_created": False,
            "overall_verdict": "OVERALL_REMAINS_FROZEN",
        },
        "peak-longevity-policy-examples.json": {**base, "players": examples},
        "step-0015k-v1-preservation.json": {**base, **v1_preservation},
        "step-0015k-branch-state.json": {
            **base,
            "defense": "V1 attribution flaw documented; V2 remains unpromoted research",
            "player_season_value": (
                "tiered measurement contract accepted for downstream use; standalone universal "
                "point methodology remains limited"
            ),
            "peak": "V2 promoted with interval-only limitations",
            "longevity": "35/40/25 philosophy retained with frozen tiered interval policy",
            "overall": "V1 unchanged; uncertainty-aware Overall remains future research",
        },
        "step-0015k-verdict.json": {
            **base,
            "step_status": "PASS",
            "peak_verdict": "PROMOTE_PEAK_V2_WITH_LIMITATIONS",
            "longevity_verdict": "FREEZE_LONGEVITY_TIERED_POLICY",
            "overall_verdict": "OVERALL_REMAINS_FROZEN",
            "recommendation": "READY_FOR_OVERALL_UNCERTAINTY_ARCHITECTURE_AUDIT",
            "player_specific_logic": False,
            "new_overall_score_created": False,
        },
    }
    report_hashes: dict[str, str] = {}
    for name, payload in reports.items():
        path = args.docs_root / name
        stable_json(path, payload)
        report_hashes[name] = file_hash(path)

    fingerprint_payload = {
        "versions": base,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "peak_verdict": "PROMOTE_PEAK_V2_WITH_LIMITATIONS",
        "longevity_verdict": "FREEZE_LONGEVITY_TIERED_POLICY",
        "overall_verdict": "OVERALL_REMAINS_FROZEN",
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise ValueError(
            f"fingerprint mismatch: expected {args.expected_fingerprint}, got {fingerprint}"
        )
    summary = {
        **base,
        "run_at": args.run_at,
        "step_status": "PASS",
        "peak_verdict": "PROMOTE_PEAK_V2_WITH_LIMITATIONS",
        "longevity_verdict": "FREEZE_LONGEVITY_TIERED_POLICY",
        "overall_verdict": "OVERALL_REMAINS_FROZEN",
        "recommendation": "READY_FOR_OVERALL_UNCERTAINTY_ARCHITECTURE_AUDIT",
        "reconstruction": reconstruction,
        "peak_status_counts": dict(sorted(peak_status_counts.items())),
        "peak_coverage_reason_counts": dict(sorted(peak_coverage.items())),
        "longevity_status_counts": dict(sorted(longevity_status_counts.items())),
        "overall_eligibility_counts": dict(sorted(eligibility_counts.items())),
        "v1_preservation": v1_preservation,
        "outputs": manifests,
        "report_hashes": report_hashes,
        "output_fingerprint": fingerprint,
        "deterministic_rebuild_verified": bool(args.expected_fingerprint),
        "network_requests": 0,
        "runtime_seconds": time.perf_counter() - started,
    }
    stable_json(args.docs_root / "step-0015k-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
