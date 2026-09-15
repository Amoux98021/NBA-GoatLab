"""Production-facing Peak V2 and tiered Longevity policy primitives.

The helpers in this module classify evidence. They never calculate an Overall
score, redistribute a missing dimension weight, or turn an interval midpoint
into a ranking-grade point.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

PEAK_POINT_STATUSES = frozenset({"OFFICIAL_PEAK_POINT", "PROVISIONAL_PEAK_POINT"})
LONGEVITY_POINT_STATUSES = frozenset({"OFFICIAL_LONGEVITY_POINT"})


def has_contiguous_three_season_window(seasons: Sequence[int]) -> bool:
    """Return whether unique seasons contain one complete three-season window."""

    ordered = sorted(set(seasons))
    return any(
        ordered[index + 1] == ordered[index] + 1 and ordered[index + 2] == ordered[index] + 2
        for index in range(len(ordered) - 2)
    )


def peak_coverage_class(
    peak_status: str,
    *,
    qualified_seasons: int,
    measured_seasons: Sequence[int],
) -> str:
    """Refine Peak coverage without treating short careers as missing data."""

    if peak_status == "OFFICIAL_PEAK_POINT":
        return "OFFICIAL_POINT"
    if peak_status == "PROVISIONAL_PEAK_POINT":
        return "PROVISIONAL_POINT"
    if peak_status == "PEAK_INTERVAL_ONLY":
        return "INTERVAL_ONLY"
    if peak_status != "PEAK_UNAVAILABLE":
        raise ValueError(f"unknown Peak status: {peak_status}")
    if qualified_seasons < 3:
        return "CONSTITUTIONALLY_INELIGIBLE_FEWER_THAN_THREE_QUALIFIED_SEASONS"
    if len(set(measured_seasons)) < 3:
        return "MEASUREMENT_UNAVAILABLE_FEWER_THAN_THREE_USABLE_SEASONS"
    if not has_contiguous_three_season_window(measured_seasons):
        return "CONSTITUTIONALLY_INELIGIBLE_NO_CONTIGUOUS_QUALIFYING_WINDOW"
    return "MEASUREMENT_UNAVAILABLE_OTHER"


def ranking_grade_point(value: float | None, status: str, allowed: frozenset[str]) -> float | None:
    """Expose a point only when its evidence status is ranking-grade."""

    if status not in allowed:
        return None
    if value is None:
        raise ValueError(f"ranking-grade status {status} has no point value")
    return float(value)


def overall_eligibility_class(
    *,
    peak_status: str,
    longevity_status: str,
    other_dimension_available: Mapping[str, bool],
) -> tuple[str, tuple[str, ...]]:
    """Classify seven-dimension eligibility without scoring or reweighting."""

    unavailable = sorted(
        dimension for dimension, available in other_dimension_available.items() if not available
    )
    if peak_status == "PEAK_UNAVAILABLE":
        unavailable.append("PEAK")
    if longevity_status == "LONGEVITY_UNAVAILABLE":
        unavailable.append("LONGEVITY")
    if unavailable:
        return "REQUIRED_DIMENSION_UNAVAILABLE", tuple(sorted(set(unavailable)))

    intervals: list[str] = []
    if peak_status == "PEAK_INTERVAL_ONLY":
        intervals.append("PEAK")
    elif peak_status not in PEAK_POINT_STATUSES:
        raise ValueError(f"unknown Peak status: {peak_status}")
    if longevity_status == "LONGEVITY_INTERVAL_ONLY":
        intervals.append("LONGEVITY")
    elif longevity_status not in LONGEVITY_POINT_STATUSES:
        raise ValueError(f"unknown Longevity status: {longevity_status}")
    if intervals:
        return "INTERVAL_DIMENSION_PRESENT", tuple(intervals)
    return "COMPLETE_POINT_DIMENSIONS", ()
