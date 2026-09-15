from __future__ import annotations

import pytest

from goatlab.rankings.peak_longevity_policy import (
    LONGEVITY_POINT_STATUSES,
    PEAK_POINT_STATUSES,
    has_contiguous_three_season_window,
    overall_eligibility_class,
    peak_coverage_class,
    ranking_grade_point,
)


def test_contiguous_peak_window_requires_three_calendar_seasons() -> None:
    assert has_contiguous_three_season_window([2001, 2002, 2003])
    assert has_contiguous_three_season_window([2003, 2001, 2002, 2002])
    assert not has_contiguous_three_season_window([2001, 2002, 2004])


@pytest.mark.parametrize(
    ("qualified", "measured", "expected"),
    [
        (2, [2000, 2001], "CONSTITUTIONALLY_INELIGIBLE_FEWER_THAN_THREE_QUALIFIED_SEASONS"),
        (4, [2000, 2001], "MEASUREMENT_UNAVAILABLE_FEWER_THAN_THREE_USABLE_SEASONS"),
        (3, [2000, 2002, 2004], "CONSTITUTIONALLY_INELIGIBLE_NO_CONTIGUOUS_QUALIFYING_WINDOW"),
        (3, [2000, 2001, 2002], "MEASUREMENT_UNAVAILABLE_OTHER"),
    ],
)
def test_peak_coverage_separates_career_eligibility_from_measurement(
    qualified: int, measured: list[int], expected: str
) -> None:
    assert (
        peak_coverage_class(
            "PEAK_UNAVAILABLE", qualified_seasons=qualified, measured_seasons=measured
        )
        == expected
    )


def test_interval_midpoint_is_never_exposed_as_ranking_grade_point() -> None:
    assert ranking_grade_point(88.0, "PEAK_INTERVAL_ONLY", PEAK_POINT_STATUSES) is None
    assert ranking_grade_point(88.0, "LONGEVITY_INTERVAL_ONLY", LONGEVITY_POINT_STATUSES) is None
    assert ranking_grade_point(88.0, "PROVISIONAL_PEAK_POINT", PEAK_POINT_STATUSES) == 88.0


def test_ranking_grade_status_requires_a_value() -> None:
    with pytest.raises(ValueError, match="has no point value"):
        ranking_grade_point(None, "OFFICIAL_PEAK_POINT", PEAK_POINT_STATUSES)


def test_overall_eligibility_does_not_renormalize_around_intervals() -> None:
    eligibility, reasons = overall_eligibility_class(
        peak_status="OFFICIAL_PEAK_POINT",
        longevity_status="LONGEVITY_INTERVAL_ONLY",
        other_dimension_available={"OFFENSE": True, "DEFENSE": True},
    )
    assert eligibility == "INTERVAL_DIMENSION_PRESENT"
    assert reasons == ("LONGEVITY",)


def test_overall_eligibility_prioritizes_required_unavailable_dimension() -> None:
    eligibility, reasons = overall_eligibility_class(
        peak_status="PEAK_INTERVAL_ONLY",
        longevity_status="LONGEVITY_INTERVAL_ONLY",
        other_dimension_available={"OFFENSE": False, "DEFENSE": True},
    )
    assert eligibility == "REQUIRED_DIMENSION_UNAVAILABLE"
    assert reasons == ("OFFENSE",)
