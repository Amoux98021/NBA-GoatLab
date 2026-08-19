import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from goatlab.data.canonical import (
    NBADB_V238_SOURCE_ID,
    canonical_id,
    normalize_season_type,
    parse_season_label,
    transform_nbadb_game,
    transform_nbadb_player,
    transform_nbadb_season,
    utc_datetime,
)
from goatlab.schemas import (
    CoverageStatus,
    Franchise,
    Game,
    MetricCoverage,
    MetricOrigin,
    Player,
    PlayerAward,
    PlayerGameStats,
    PlayerSeasonAdvanced,
    PlayerSeasonStats,
    Season,
    SeasonType,
    Team,
)
from goatlab.schemas.validation import (
    CanonicalBatch,
    CanonicalIntegrityError,
    validate_canonical_batch,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source_fixture() -> dict[str, object]:
    path = REPOSITORY_ROOT / "data/fixtures/nbadb_v238_sample.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _transformed_batch(source_fixture: dict[str, object]) -> CanonicalBatch:
    updated_at = utc_datetime(str(source_fixture["retrieved_at"]))
    raw_teams = source_fixture["teams"]
    assert isinstance(raw_teams, list)
    teams = []
    team_lookup: dict[str, str] = {}
    franchises = []
    for raw_team in raw_teams:
        assert isinstance(raw_team, dict)
        nba_team_id = str(raw_team["id"])
        franchise_id = canonical_id("franchise", "nba", nba_team_id)
        team_id = canonical_id("team", "nba", f"{nba_team_id}:current")
        team_lookup[nba_team_id] = team_id
        franchises.append(
            Franchise(
                franchise_id=franchise_id,
                current_name=str(raw_team["full_name"]),
                source_id=NBADB_V238_SOURCE_ID,
                updated_at=updated_at,
            )
        )
        teams.append(
            Team(
                team_id=team_id,
                nba_team_id=nba_team_id,
                franchise_id=franchise_id,
                team_name=str(raw_team["full_name"]),
                abbreviation=str(raw_team["abbreviation"]),
                city=str(raw_team["city"]),
                valid_from_year=int(float(str(raw_team["year_founded"]))),
                valid_to_year=None,
                source_id=NBADB_V238_SOURCE_ID,
                updated_at=updated_at,
            )
        )
    raw_player = source_fixture["player"]
    raw_info = source_fixture["common_player_info"]
    raw_game = source_fixture["game"]
    assert isinstance(raw_player, dict)
    assert isinstance(raw_info, dict)
    assert isinstance(raw_game, dict)
    player = transform_nbadb_player(raw_player, raw_info, updated_at=updated_at)
    season = transform_nbadb_season(str(raw_game["season_id"]), updated_at=updated_at)
    game = transform_nbadb_game(raw_game, team_lookup, updated_at=updated_at)
    return CanonicalBatch(
        players=(player,),
        seasons=(season,),
        franchises=tuple(franchises),
        teams=tuple(teams),
        games=(game,),
    )


def test_season_label_parsing_and_schema_validation() -> None:
    assert parse_season_label("2022-23") == 2022
    with pytest.raises(ValueError, match="end year"):
        parse_season_label("2022-24")
    with pytest.raises(ValueError, match="invalid NBA season label"):
        parse_season_label("2022")


def test_source_season_types_are_standardized() -> None:
    assert normalize_season_type("Regular Season") is SeasonType.REGULAR
    assert normalize_season_type("Playoffs") is SeasonType.PLAYOFF
    assert normalize_season_type("All Star") is SeasonType.ALL_STAR
    assert normalize_season_type("All-Star") is SeasonType.ALL_STAR
    assert normalize_season_type("Pre Season") is SeasonType.PRESEASON
    with pytest.raises(ValueError, match="unsupported"):
        normalize_season_type("Exhibition")


def test_player_identity_mapping_is_name_independent_and_stable(
    source_fixture: dict[str, object],
) -> None:
    raw_player = source_fixture["player"]
    raw_info = source_fixture["common_player_info"]
    assert isinstance(raw_player, dict)
    assert isinstance(raw_info, dict)
    updated_at = utc_datetime(str(source_fixture["retrieved_at"]))
    player = transform_nbadb_player(raw_player, raw_info, updated_at=updated_at)
    renamed = {**raw_player, "full_name": "A display-name change"}
    renamed_player = transform_nbadb_player(renamed, raw_info, updated_at=updated_at)

    assert player.player_id == "player_ee62fde09b405fa18c2516d1f5cd4e81"
    assert renamed_player.player_id == player.player_id
    assert player.nba_player_id == "76003"


def test_transforms_are_deterministic_and_referentially_valid(
    source_fixture: dict[str, object],
) -> None:
    first = _transformed_batch(source_fixture)
    second = _transformed_batch(source_fixture)

    assert first == second
    validate_canonical_batch(first)
    assert first.games[0].winner_team_id == first.games[0].home_team_id
    assert first.games[0].season_type is SeasonType.REGULAR


def test_required_uniqueness_rejects_duplicate_canonical_keys(
    source_fixture: dict[str, object],
) -> None:
    batch = _transformed_batch(source_fixture)
    duplicate_batch = CanonicalBatch(
        players=(batch.players[0], batch.players[0]),
        seasons=batch.seasons,
        franchises=batch.franchises,
        teams=batch.teams,
        games=batch.games,
    )

    with pytest.raises(CanonicalIntegrityError, match="duplicate players key"):
        validate_canonical_batch(duplicate_batch)


def test_referential_integrity_rejects_missing_team(source_fixture: dict[str, object]) -> None:
    batch = _transformed_batch(source_fixture)
    incomplete = CanonicalBatch(
        players=batch.players,
        seasons=batch.seasons,
        franchises=batch.franchises,
        teams=batch.teams[:1],
        games=batch.games,
    )

    with pytest.raises(CanonicalIntegrityError, match="unknown team"):
        validate_canonical_batch(incomplete)


def test_historical_null_is_distinct_from_observed_zero() -> None:
    timestamp = datetime(2026, 8, 19, tzinfo=UTC)
    base = {
        "game_id": "game_fixture",
        "player_id": "player_fixture",
        "team_id": "team_fixture",
        "season_id": 1978,
        "season_type": SeasonType.REGULAR,
        "started": None,
        "did_play": True,
        "source_id": "fixture:historical-null",
        "updated_at": timestamp,
    }
    unavailable = PlayerGameStats(**base, fg3m=None, fg3a=None)
    observed_zero = PlayerGameStats(**{**base, "game_id": "game_fixture_2"}, fg3m=0, fg3a=0)

    assert unavailable.fg3m is None
    assert unavailable.model_dump()["fg3m"] is None
    assert observed_zero.fg3m == 0
    assert unavailable.fg3m != observed_zero.fg3m


def test_metric_coverage_rejects_reliable_window_for_unavailable_metric() -> None:
    with pytest.raises(ValidationError, match="cannot claim a reliable season window"):
        MetricCoverage(
            canonical_entity="player_game_stats",
            metric="fg3m",
            provider="nbadb-v238",
            first_reliable_season=1979,
            last_reliable_season=None,
            season_type=SeasonType.REGULAR,
            coverage_status=CoverageStatus.SOURCE_UNAVAILABLE,
            metric_origin=MetricOrigin.RAW,
            cross_era_eligible=False,
            methodology="Physical table absent from acquired bundle.",
            notes=None,
            source_id=NBADB_V238_SOURCE_ID,
            updated_at=datetime(2026, 8, 19, tzinfo=UTC),
        )


def test_source_provenance_is_required_and_manifest_is_audited() -> None:
    with pytest.raises(ValidationError, match="preserve provenance"):
        Franchise(
            franchise_id="franchise_fixture",
            current_name="Fixture",
            source_id="",
            updated_at=datetime(2026, 8, 19, tzinfo=UTC),
        )
    manifest_path = REPOSITORY_ROOT / "docs/data/source-manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["dataset"]["kaggle_version"] == 238
    assert manifest["source"]["installed_revision"] == ("48abd9825ed6933b57dbac3f50f058523367b1f5")
    assert manifest["reconciliation"]["status"] == ("bundle_does_not_match_published_v4_catalog")


def test_mapping_documents_every_canonical_field() -> None:
    mapping_path = REPOSITORY_ROOT / "docs/data/NBADB_TO_CANONICAL_MAPPING.md"
    mapping = mapping_path.read_text(encoding="utf-8")
    sections = {
        "players": Player,
        "seasons": Season,
        "franchises": Franchise,
        "teams": Team,
        "games": Game,
        "player_game_stats": PlayerGameStats,
        "player_season_stats": PlayerSeasonStats,
        "player_season_advanced": PlayerSeasonAdvanced,
        "player_awards": PlayerAward,
        "metric_coverage": MetricCoverage,
    }
    headings = list(sections)
    for heading in headings:
        start = mapping.index(f"## `{heading}`")
        end = mapping.find("\n## ", start + 1)
        section = mapping[start : end if end != -1 else None]
        missing = [name for name in sections[heading].model_fields if f"`{name}`" not in section]
        assert not missing, f"{heading} mapping is missing fields: {missing}"
