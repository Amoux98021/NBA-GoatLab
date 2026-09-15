"""Deterministic primitives for the STEP-0015G promotion audit."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

PLAYER_SEASON_VALUE_PROMOTION_AUDIT_VERSION = (
    "goatlab-v1-player-season-value-v2-promotion-audit-v1"
)
PLAYER_SEASON_VALUE_PRODUCTION_VERSION = "goatlab-v1-player-season-value-v2"


def classify_source_conflict(
    *, field: str, difference: float, traded_total: bool, season_id: int
) -> str:
    """Assign a reproducible diagnostic cause without pretending to resolve provenance."""
    if traded_total:
        return "TRADED_TOTAL_VS_GAME_OR_TEAM_AGGREGATION"
    if field == "MIN":
        return "MINUTE_PRECISION_OR_SOURCE_VERSION"
    if field == "GP":
        return "GAME_SCOPE_OR_HISTORICAL_CORRECTION"
    if difference >= 25.0:
        return "LIKELY_INCOMPLETE_GAME_LOG_AGGREGATION"
    if season_id <= 1949:
        return "BAA_EARLY_RECORD_REVISION_OR_SCOPE"
    return "HISTORICAL_CORRECTION_OR_SOURCE_VERSION"


def difference_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    """Summarize absolute score differences on a 0-100 scale."""
    finite = [abs(float(value)) for value in values if math.isfinite(float(value))]
    if not finite:
        return {
            "observations": 0,
            "mean_absolute_error": None,
            "maximum_absolute_difference": None,
            "more_than_2_points": None,
            "more_than_5_points": None,
            "more_than_10_points": None,
        }
    return {
        "observations": len(finite),
        "mean_absolute_error": statistics.fmean(finite),
        "maximum_absolute_difference": max(finite),
        "more_than_2_points": sum(value > 2.0 for value in finite) / len(finite),
        "more_than_5_points": sum(value > 5.0 for value in finite) / len(finite),
        "more_than_10_points": sum(value > 10.0 for value in finite) / len(finite),
    }


def promotion_verdict(gates: dict[str, bool]) -> str:
    """Apply the predeclared audit logic; coverage cannot override comparability failures."""
    required = (
        "reconstruction_exact",
        "coverage_broad",
        "conflict_stable",
        "team_context_nondominant",
        "missingness_explicit",
        "confidence_separate",
        "deterministic",
    )
    if not all(gates.get(name, False) for name in required):
        return "DO_NOT_PROMOTE"
    if not gates.get("regime_comparability_acceptable", False):
        return "DO_NOT_PROMOTE"
    if gates.get("remaining_historical_limitations", False):
        return "PROMOTE_WITH_LIMITATIONS"
    return "PROMOTE"


def safe_rate(total: Any, games: Any) -> float | None:
    """Derive a per-game value only from two observed facts."""
    if total is None or games is None or float(games) <= 0:
        return None
    value = float(total) / float(games)
    return value if math.isfinite(value) else None
