from __future__ import annotations

import numpy as np
import pytest

from goatlab.rankings.overall_uncertainty import (
    DEFENSE_CAVEAT,
    FROZEN_WEIGHTS,
    fixed_other_contribution,
    overall_draws,
    overall_status,
    robust_order_label,
    uncertainty_decomposition,
    validate_frozen_weights,
)


def test_frozen_weights_are_valid_and_unchanged() -> None:
    assert FROZEN_WEIGHTS == {
        "PEAK": 0.17,
        "LONGEVITY": 0.14,
        "OFFENSE": 0.16,
        "DEFENSE": 0.14,
        "PLAYOFFS": 0.18,
        "ACCOLADES": 0.10,
        "WINNING": 0.11,
    }
    assert sum(validate_frozen_weights()) == pytest.approx(1.0)
    assert DEFENSE_CAVEAT == "DEFENSE_V1_FROZEN_PENDING_REVISION"


def test_paired_overall_draws_preserve_nominal_weights() -> None:
    peak = np.asarray([80.0, 90.0, 100.0])
    longevity = np.asarray([60.0, 70.0, 80.0])
    fixed = 40.0
    expected = 0.17 * peak + 0.14 * longevity + fixed
    assert np.array_equal(overall_draws(peak, longevity, fixed), expected)


def test_unpaired_draws_are_rejected() -> None:
    with pytest.raises(ValueError, match="paired"):
        overall_draws(np.asarray([80.0, 90.0]), np.asarray([60.0]), 40.0)


def test_fixed_dimensions_are_not_renormalized_around_missingness() -> None:
    complete = {
        "OFFENSE": 80.0,
        "DEFENSE": 70.0,
        "PLAYOFFS": 90.0,
        "ACCOLADES": 60.0,
        "WINNING": 50.0,
    }
    assert fixed_other_contribution(complete) == pytest.approx(50.3)
    incomplete = dict(complete)
    incomplete["ACCOLADES"] = None
    assert fixed_other_contribution(incomplete) is None


def test_covariance_is_retained_in_variance_decomposition() -> None:
    peak = np.asarray([70.0, 80.0, 90.0, 100.0])
    longevity = np.asarray([55.0, 65.0, 75.0, 85.0])
    result = uncertainty_decomposition(peak, longevity)
    assert result["covariance_contribution"] > 0.0
    assert result["analytic_total"] == pytest.approx(result["empirical_total"])


@pytest.mark.parametrize(
    ("peak", "longevity", "other", "eligible", "expected"),
    [
        (
            "OFFICIAL_PEAK_POINT",
            "OFFICIAL_LONGEVITY_POINT",
            True,
            True,
            "OFFICIAL_OVERALL_POINT",
        ),
        (
            "PROVISIONAL_PEAK_POINT",
            "LONGEVITY_INTERVAL_ONLY",
            True,
            True,
            "PROVISIONAL_OVERALL_POINT",
        ),
        (
            "PEAK_INTERVAL_ONLY",
            "LONGEVITY_INTERVAL_ONLY",
            True,
            False,
            "OVERALL_INTERVAL_ONLY",
        ),
        (
            "PEAK_UNAVAILABLE",
            "OFFICIAL_LONGEVITY_POINT",
            True,
            True,
            "OVERALL_UNAVAILABLE",
        ),
    ],
)
def test_status_taxonomy_is_evidence_based(
    peak: str, longevity: str, other: bool, eligible: bool, expected: str
) -> None:
    assert (
        overall_status(
            peak_status=peak,
            longevity_status=longevity,
            other_dimensions_available=other,
            evidence_pattern_point_eligible=eligible,
        )
        == expected
    )


def test_pairwise_labels_are_symmetric_and_deterministic() -> None:
    assert robust_order_label(0.95) == "ROBUST_ORDER"
    assert robust_order_label(0.75) == "LEAN_ORDER"
    assert robust_order_label(0.50) == "UNCERTAIN_ORDER"
    assert robust_order_label(0.25) == "LEAN_REVERSE"
    assert robust_order_label(0.05) == "ROBUST_REVERSE"
