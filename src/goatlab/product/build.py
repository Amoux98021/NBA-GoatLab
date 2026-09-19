"""Deterministic packaging of frozen Gold ranking research into product records."""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from goatlab.product.models import (
    DimensionProfile,
    LeaderboardEntry,
    OverallDistributionSummary,
    PlayerIdentity,
    PlayerProfile,
    RankDistributionSummary,
    TopNProbabilities,
)
from goatlab.product.repository import normalized_search_name
from goatlab.rankings.publication_policy import (
    DimensionDisplay,
    PlayerLeaderboardRecord,
    RankingStatus,
    ranking_status,
    top100_membership,
)

RELEASE_ID = "goatlab-ranking-release-2026-v2-probabilistic"
RELEASE_GENERATED_AT = "2026-09-19T00:00:00Z"  # fixed logical release timestamp
POLICY_VERSION: Literal["goatlab-v1-ranking-policy-v2-probabilistic"] = (
    "goatlab-v1-ranking-policy-v2-probabilistic"
)
OVERALL_VERSION: Literal["goatlab-v1-overall-v2-tiered"] = "goatlab-v1-overall-v2-tiered"
PRODUCT_VERSION = "goatlab-v1-probabilistic-product-contract-v1"
DIMENSION_NAMES = ("PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING")


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def canonical_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json(row) for row in rows)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def immutable_write(path: Path, data: bytes) -> bool:
    """Write once. A second build may verify equal bytes, never replace a release."""

    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"release artifact is immutable and differs: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    output = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), output, compression="zstd", version="2.6")
    return output.getvalue()


def paired_draw_bytes(player_ids: list[str], overall: np.ndarray, ranks: np.ndarray) -> bytes:
    if overall.shape != ranks.shape or overall.shape != (len(player_ids), 2500):
        raise ValueError("paired draw arrays have unexpected dimensions")
    if not np.isfinite(overall).all() or not np.isfinite(ranks).all():
        raise ValueError("draw arrays contain nonfinite values")
    output = io.BytesIO()
    np.savez_compressed(
        output,
        player_ids=np.asarray(player_ids, dtype="U40"),
        overall_draws=np.asarray(overall, dtype="<f8"),
        rank_draws=np.asarray(ranks, dtype="<u2"),
    )
    return output.getvalue()


def _reasons(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    parsed = json.loads(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError("invalid frozen reason code list")
    return tuple(parsed)


def _index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {str(row["player_id"]): row for row in rows}
    if len(output) != len(rows):
        raise ValueError("duplicate player ID in frozen source")
    return output


def _identity(career: dict[str, Any], status: RankingStatus) -> PlayerIdentity:
    career_active = career["career_active"]
    state: Literal["ACTIVE", "RETIRED", "UNKNOWN"] = (
        "ACTIVE" if career_active is True else "RETIRED" if career_active is False else "UNKNOWN"
    )
    return PlayerIdentity(
        player_id=str(career["player_id"]),
        player_name=str(career["display_name"]),
        search_name=normalized_search_name(str(career["display_name"])),
        career_state=state,
        career_start_season=career.get("regular_first_season"),
        career_end_season=None if state == "ACTIVE" else career.get("regular_last_season"),
        latest_season_used=career.get("regular_last_season"),
        ranking_status=status,
        ranking_eligible=status != RankingStatus.UNAVAILABLE,
    )


def _dimension_profiles(
    player_id: str,
    peaks: dict[str, dict[str, Any]],
    longevity: dict[str, dict[str, Any]],
    defense: dict[str, dict[str, Any]],
    fixed_dimensions: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, DimensionProfile]:
    peak, long, defend = peaks[player_id], longevity[player_id], defense[player_id]
    output = {
        "PEAK": DimensionProfile(
            dimension="PEAK",
            status=str(peak["peak_status"]),
            point_value=peak.get("ranking_grade_peak_point"),
            diagnostic_center=peak.get("peak_central"),
            lower_90=peak.get("peak_lower_90"),
            upper_90=peak.get("peak_upper_90"),
            methodology_version=str(peak["methodology_version"]),
            reason_codes=_reasons(peak.get("reason_codes_json")),
            evidence_metadata={
                "best_supported_window": peak.get("best_supported_window"),
                "best_window_probability": peak.get("best_window_probability"),
                "window_status": peak.get("window_status"),
                "coverage_class": peak.get("peak_coverage_class"),
            },
        ),
        "LONGEVITY": DimensionProfile(
            dimension="LONGEVITY",
            status=str(long["longevity_status"]),
            point_value=long.get("ranking_grade_longevity_point"),
            diagnostic_center=long.get("longevity_central"),
            lower_90=long.get("longevity_lower_90"),
            upper_90=long.get("longevity_upper_90"),
            methodology_version=str(long["methodology_version"]),
            reason_codes=_reasons(long.get("reason_codes_json")),
            evidence_metadata={
                "evidence_pattern": long.get("evidence_pattern"),
                "expected_elite_breadth": long.get("expected_elite_breadth"),
                "expected_capped_area": long.get("expected_capped_area"),
                "expected_longest_run": long.get("expected_longest_run"),
                "run_bridge_event_count": long.get("run_bridge_event_count"),
            },
        ),
        "DEFENSE": DimensionProfile(
            dimension="DEFENSE",
            status=str(defend["defense_status"]),
            point_value=(
                defend.get("defense_central") if defend.get("ranking_grade_defense_point") else None
            ),
            diagnostic_center=defend.get("defense_central"),
            lower_90=defend.get("defense_lower_90"),
            upper_90=defend.get("defense_upper_90"),
            methodology_version=str(defend["methodology_version"]),
            reason_codes=_reasons(defend.get("reason_codes_json")),
            evidence_metadata={
                "evidence_pattern": defend.get("evidence_pattern"),
                "mean_presence_reliability": defend.get("mean_presence_reliability"),
                "usable_seasons": defend.get("usable_seasons"),
            },
        ),
    }
    for name in ("OFFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"):
        source = fixed_dimensions[player_id][name]
        score = source.get("score")
        output[name] = DimensionProfile(
            dimension=name,
            status=str(source["coverage_status"]),
            point_value=score,
            diagnostic_center=score,
            methodology_version=str(source["methodology_version"]),
            confidence=source.get("evidence_confidence"),
            reason_codes=_reasons(source.get("reason_codes_json")),
            evidence_metadata={
                "evidence_coverage_pct": source.get("evidence_coverage_pct"),
                "relevant_seasons": source.get("relevant_seasons"),
                "relevant_games": source.get("relevant_games"),
            },
        )
    return {name: output[name] for name in DIMENSION_NAMES}


def _overall(row: dict[str, Any], distribution_hash: str) -> OverallDistributionSummary:
    return OverallDistributionSummary(
        center=row["overall_diagnostic_center"],
        center_semantics="DIAGNOSTIC_SUMMARY",
        lower_80=row["overall_lower_80"],
        upper_80=row["overall_upper_80"],
        lower_90=row["overall_lower_90"],
        upper_90=row["overall_upper_90"],
        lower_95=row["overall_lower_95"],
        upper_95=row["overall_upper_95"],
        distribution_ref="paired-overall-rank-draws.npz",
        distribution_fingerprint=distribution_hash,
    )


def _rank(row: dict[str, Any]) -> RankDistributionSummary:
    return RankDistributionSummary(
        median_rank=row["median_rank"],
        mean_rank=row["expected_rank"],
        **{
            f"{direction}_{level}": row[f"rank_{direction}_{level}"]
            for direction in ("lower", "upper")
            for level in (50, 80, 90, 95)
        },
    )


def _top_n(row: dict[str, Any]) -> TopNProbabilities:
    return TopNProbabilities(
        **{f"top_{n}": row[f"probability_top_{n}"] for n in (1, 5, 10, 25, 50, 100)}
    )


def _governance_dimension(source: DimensionProfile) -> DimensionDisplay:
    value = source.point_value
    return DimensionDisplay(
        value=value,
        lower_90=source.lower_90,
        upper_90=source.upper_90,
        source_status=source.status,
        value_is_official_point=source.status.startswith("OFFICIAL_")
        or (
            source.dimension in {"OFFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"}
            and value is not None
        ),
    )


def build_records(
    rank_rows: list[dict[str, Any]],
    overall_rows: list[dict[str, Any]],
    career_rows: list[dict[str, Any]],
    peak_rows: list[dict[str, Any]],
    longevity_rows: list[dict[str, Any]],
    defense_rows: list[dict[str, Any]],
    fixed_rows: list[dict[str, Any]],
    distribution_hash: str,
) -> tuple[list[PlayerIdentity], list[LeaderboardEntry], list[PlayerProfile]]:
    if len(overall_rows) != 5103 or len(rank_rows) != 1882:
        raise ValueError("frozen rankable population count differs")
    ranks, overall, careers = _index(rank_rows), _index(overall_rows), _index(career_rows)
    peaks, longevity, defense = _index(peak_rows), _index(longevity_rows), _index(defense_rows)
    fixed: dict[str, dict[str, dict[str, Any]]] = {}
    for row in fixed_rows:
        player = str(row["player_id"])
        dimension_name = str(row["dimension"])
        if dimension_name in fixed.setdefault(player, {}):
            raise ValueError("duplicate fixed dimension")
        fixed[player][dimension_name] = row
    population = set(overall)
    if any(set(index) != population for index in (careers, peaks, longevity, defense, fixed)):
        raise ValueError("frozen source player populations do not reconcile")
    if not set(ranks) <= population or len(population - set(ranks)) != 3221:
        raise ValueError("rankable/unavailable player IDs do not reconcile")
    order = sorted(ranks, key=lambda player: (float(ranks[player]["median_rank"]), player))
    if [int(ranks[player]["median_rank_sort_position"]) for player in order] != list(
        range(1, 1883)
    ):
        raise ValueError("frozen navigation order or tie-break disagrees with policy")
    positions = {player: index for index, player in enumerate(order, start=1)}
    identities: list[PlayerIdentity] = []
    entries: list[LeaderboardEntry] = []
    profiles: list[PlayerProfile] = []
    for player_id in sorted(population):
        source = overall[player_id]
        is_rankable = player_id in ranks
        status = ranking_status(str(source["overall_status"]), distribution_available=is_rankable)
        identity = _identity(careers[player_id], status)
        if identity.player_name != str(source["player_name"]):
            raise ValueError("canonical identity differs from frozen ranking source")
        identities.append(identity)
        dimensions = _dimension_profiles(player_id, peaks, longevity, defense, fixed)
        versions = {name.lower(): dimensions[name].methodology_version for name in DIMENSION_NAMES}
        entry: LeaderboardEntry | None = None
        if is_rankable:
            row = ranks[player_id]
            if row["player_name"] != identity.player_name:
                raise ValueError("STEP-0015O identity differs from canonical identity")
            probability = float(row["probability_top_100"])
            if top100_membership(probability).value != row["top100_membership_label"]:
                raise ValueError("frozen Top-100 probability label differs")
            disclosures = (
                "DISPLAY_POSITION_NAVIGATIONAL",
                "CONDITIONAL_ON_FROZEN_MEASUREMENT_ARCHITECTURE",
                "WIDER_UNCERTAINTY_NOT_LOWER_QUALITY",
            ) + (
                ("INTERVAL_CENTER_NOT_OFFICIAL",) if status == RankingStatus.INTERVAL_NATIVE else ()
            )
            entry = LeaderboardEntry(
                release_id=RELEASE_ID,
                display_position=positions[player_id],
                display_position_semantics="NAVIGATIONAL_MEDIAN_RANK_SORT",
                player_id=player_id,
                player_name=identity.player_name,
                active=careers[player_id]["career_active"],
                overall=_overall(row, distribution_hash),
                rank=_rank(row),
                top_n=_top_n(row),
                ranking_status=status,
                overall_source_status=str(row["overall_status"]),
                top100_membership=top100_membership(probability),
                disclosure_codes=disclosures,
                ranking_policy_version=POLICY_VERSION,
                overall_substrate_version=OVERALL_VERSION,
                cutoff_season="2025-26",
            )
            governance_payload: dict[str, Any] = {
                "player_id": player_id,
                "player_name": identity.player_name,
                "distribution_ref": entry.overall.distribution_ref,
                "distribution_fingerprint": distribution_hash,
                "overall_center": entry.overall.center,
                "overall_center_label": "DIAGNOSTIC_SUMMARY",
                "overall_lower_80": entry.overall.lower_80,
                "overall_upper_80": entry.overall.upper_80,
                "overall_lower_90": entry.overall.lower_90,
                "overall_upper_90": entry.overall.upper_90,
                "median_rank": entry.rank.median_rank,
                "ranking_status": status,
                "overall_source_status": entry.overall_source_status,
                "display_position": entry.display_position,
                "display_position_semantics": "NAVIGATIONAL_MEDIAN_RANK_SORT",
                "career_state": identity.career_state,
                "active_career_policy": "TO_DATE_NO_PROJECTION",
                "cutoff_season": "2025-26",
                "ranking_policy_version": POLICY_VERSION,
                "overall_substrate_version": OVERALL_VERSION,
                "dimension_methodology_versions": versions,
                "conditional_on_frozen_measurement_architecture": True,
                "shared_cross_player_calibration_uncertainty_modeled": False,
                "uncertainty_quality_penalty_applied": False,
                "overall_point_claimed_exact": False,
            }
            governance_payload.update(
                {
                    f"rank_{direction}_{level}": getattr(entry.rank, f"{direction}_{level}")
                    for direction in ("lower", "upper")
                    for level in (50, 80, 90, 95)
                }
            )
            governance_payload.update(
                {
                    f"top_{n}_probability": getattr(entry.top_n, f"top_{n}")
                    for n in (10, 25, 50, 100)
                }
            )
            governance_payload.update(
                {name.lower(): _governance_dimension(dimensions[name]) for name in DIMENSION_NAMES}
            )
            PlayerLeaderboardRecord.model_validate(governance_payload)
            entries.append(entry)
        reasons = set(_reasons(source.get("blocking_reasons_json")))
        for name, dimension in dimensions.items():
            reasons.update(f"{name}:{reason}" for reason in dimension.reason_codes)
            if "INTERVAL_ONLY" in dimension.status:
                reasons.add(f"{name}_INTERVAL_NATIVE")
            if dimension.status == "NOT_QUERIED":
                reasons.add(f"{name}_NOT_QUERIED")
        profiles.append(
            PlayerProfile(
                release_id=RELEASE_ID,
                identity=identity,
                leaderboard=entry,
                dimensions=dimensions,
                reason_codes=tuple(sorted(reasons)),
                methodology_versions={
                    **versions,
                    "overall": OVERALL_VERSION,
                    "ranking_policy": POLICY_VERSION,
                },
                active_career_policy="TO_DATE_NO_PROJECTION",
            )
        )
    entries.sort(key=lambda row: row.display_position)
    if len({row.player_id for row in entries}) != 1882 or len(profiles) != 5103:
        raise ValueError("product record coverage differs from frozen corpus")
    if Counter(row.ranking_status for row in entries) != Counter(
        {
            RankingStatus.OFFICIAL: 312,
            RankingStatus.PROVISIONAL: 284,
            RankingStatus.INTERVAL_NATIVE: 1286,
        }
    ):
        raise ValueError("frozen Overall status counts differ")
    return identities, entries, profiles
