from __future__ import annotations

from goatlab.rankings.player_season_value_promotion import (
    classify_source_conflict,
    difference_summary,
    promotion_verdict,
    safe_rate,
)


def test_source_conflict_classification_is_deterministic() -> None:
    assert (
        classify_source_conflict(
            field="PTS", difference=100.0, traded_total=True, season_id=1980
        )
        == "TRADED_TOTAL_VS_GAME_OR_TEAM_AGGREGATION"
    )
    assert (
        classify_source_conflict(
            field="MIN", difference=2.0, traded_total=False, season_id=1980
        )
        == "MINUTE_PRECISION_OR_SOURCE_VERSION"
    )


def test_difference_summary_uses_score_points() -> None:
    report = difference_summary([0.0, -3.0, 6.0, 12.0])
    assert report["observations"] == 4
    assert report["mean_absolute_error"] == 5.25
    assert report["more_than_10_points"] == 0.25


def test_missing_fact_rate_is_not_zero() -> None:
    assert safe_rate(None, 82) is None
    assert safe_rate(100, None) is None
    assert safe_rate(100, 0) is None
    assert safe_rate(164, 82) == 2.0


def test_comparability_failure_blocks_promotion() -> None:
    gates = {
        "reconstruction_exact": True,
        "coverage_broad": True,
        "conflict_stable": True,
        "team_context_nondominant": True,
        "missingness_explicit": True,
        "confidence_separate": True,
        "deterministic": True,
        "regime_comparability_acceptable": False,
        "remaining_historical_limitations": True,
    }
    assert promotion_verdict(gates) == "DO_NOT_PROMOTE"

