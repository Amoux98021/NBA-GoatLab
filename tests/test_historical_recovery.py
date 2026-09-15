from __future__ import annotations

import pytest

from goatlab.data.historical_recovery import (
    MissingReason,
    canonical_regular_season_rows,
    missing_reason,
    named_result_rows,
    reconcile_number,
    safe_percentage,
    safe_rate,
    true_shooting_pct,
)


def fixture_payload() -> dict[str, object]:
    headers = [
        "PLAYER_ID",
        "SEASON_ID",
        "LEAGUE_ID",
        "TEAM_ID",
        "TEAM_ABBREVIATION",
        "GP",
        "MIN",
        "FGM",
        "FGA",
        "FG_PCT",
        "FG3M",
        "FG3A",
        "FG3_PCT",
        "FTM",
        "FTA",
        "FT_PCT",
        "OREB",
        "DREB",
        "REB",
        "AST",
        "STL",
        "BLK",
        "TOV",
        "PF",
        "PTS",
    ]
    return {
        "resultSets": [
            {
                "name": "SeasonTotalsRegularSeason",
                "headers": headers,
                "rowSet": [
                    [
                        1,
                        "1946-47",
                        "00",
                        10,
                        "AAA",
                        40,
                        None,
                        100,
                        300,
                        1 / 3,
                        None,
                        None,
                        None,
                        50,
                        75,
                        2 / 3,
                        None,
                        None,
                        None,
                        80,
                        None,
                        None,
                        None,
                        90,
                        250,
                    ]
                ],
            }
        ]
    }


def test_player_career_totals_preserve_historical_observations() -> None:
    source = named_result_rows(fixture_payload(), "SeasonTotalsRegularSeason")
    rows = canonical_regular_season_rows(source, nba_player_id="1")
    assert len(rows) == 1
    assert rows[0]["AST"] == 80
    assert rows[0]["FGA"] == 300
    assert rows[0]["FTA"] == 75
    assert rows[0]["selection_method"] == "SINGLE_TEAM_ROW"


def test_traded_season_requires_authoritative_total_row() -> None:
    source = named_result_rows(fixture_payload(), "SeasonTotalsRegularSeason")
    source.append({**source[0], "TEAM_ID": 11, "TEAM_ABBREVIATION": "BBB"})
    with pytest.raises(ValueError, match="ambiguous traded season"):
        canonical_regular_season_rows(source, nba_player_id="1")
    source.append({**source[0], "TEAM_ID": 0, "TEAM_ABBREVIATION": "TOT"})
    rows = canonical_regular_season_rows(source, nba_player_id="1")
    assert rows[0]["selection_method"] == "AUTHORITATIVE_TOTAL_ROW"


def test_observed_totals_support_exact_rates_and_standard_ts_derivation() -> None:
    assert safe_rate(80, 40) == 2.0
    assert safe_rate(None, 40) is None
    assert safe_percentage(100, 300) == pytest.approx(1 / 3)
    assert safe_percentage(0, 0) is None
    assert true_shooting_pct(250, 300, 75) == pytest.approx(250 / (2 * (300 + 0.44 * 75)))
    assert true_shooting_pct(0, 0, 0) is None
    assert true_shooting_pct(250, None, 75) is None


def test_historical_missingness_is_not_zero() -> None:
    assert missing_reason("REB", 1949, None) is MissingReason.HISTORICALLY_NOT_RECORDED
    assert missing_reason("STL", 1972, 0) is MissingReason.HISTORICALLY_NOT_RECORDED
    assert missing_reason("AST", 1946, None) is MissingReason.SOURCE_UNAVAILABLE
    assert missing_reason("AST", 1946, 0) is None


def test_identity_mismatch_is_rejected() -> None:
    rows = named_result_rows(fixture_payload(), "SeasonTotalsRegularSeason")
    with pytest.raises(ValueError, match="identity differs"):
        canonical_regular_season_rows(rows, nba_player_id="2")


def test_reconciliation_never_averages_conflicting_facts() -> None:
    assert reconcile_number(10, 10) == "MATCH"
    assert reconcile_number(10, 11) == "CONFLICT"
    assert reconcile_number(None, 11) == "NOT_COMPARED"
