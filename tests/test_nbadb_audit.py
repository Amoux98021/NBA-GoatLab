import sqlite3
from pathlib import Path

from goatlab.data.nbadb_audit import audit_sqlite


def _build_source_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE game (
                season_id TEXT,
                game_id TEXT,
                game_date TIMESTAMP,
                season_type TEXT,
                pts_home REAL,
                fgm_home REAL,
                fga_home REAL,
                fg3m_home REAL,
                fg3a_home REAL,
                ftm_home REAL,
                fta_home REAL,
                oreb_home REAL,
                dreb_home REAL,
                reb_home REAL,
                ast_home REAL,
                stl_home REAL,
                blk_home REAL,
                tov_home REAL,
                pf_home REAL,
                plus_minus_home REAL
            )
            """
        )
        connection.executemany(
            "INSERT INTO game VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "21978",
                    "game-1",
                    "1978-10-01",
                    "Regular Season",
                    90,
                    35,
                    80,
                    None,
                    None,
                    20,
                    25,
                    None,
                    None,
                    50,
                    20,
                    None,
                    None,
                    None,
                    18,
                    -5,
                ),
                (
                    "21979",
                    "game-2",
                    "1979-10-01",
                    "Regular Season",
                    100,
                    40,
                    82,
                    2,
                    5,
                    18,
                    22,
                    10,
                    30,
                    40,
                    25,
                    8,
                    5,
                    14,
                    20,
                    5,
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_audit_preserves_null_observation_semantics(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _build_source_fixture(source)

    audit = audit_sqlite(source, display_path="fixture.sqlite")
    metric = next(item for item in audit.game_metric_observations if item.metric == "fg3m_home")

    assert metric.first_observed_start_year == 1979
    assert metric.null_count == 1
    assert metric.row_count == 2
    assert audit.game_coverage.distinct_start_years == 2


def test_audit_reports_duplicate_candidate_keys(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    _build_source_fixture(source)
    connection = sqlite3.connect(source)
    try:
        connection.execute("INSERT INTO game SELECT * FROM game WHERE game_id = 'game-2'")
        connection.commit()
    finally:
        connection.close()

    audit = audit_sqlite(source)
    duplicate = next(item for item in audit.duplicate_checks if item.table == "game")

    assert duplicate.candidate_key == ("game_id",)
    assert duplicate.duplicate_groups == 1
