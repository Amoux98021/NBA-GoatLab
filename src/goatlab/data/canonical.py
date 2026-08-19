"""Deterministic transforms from audited nbadb v238 records into Silver V1."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime

from goatlab.schemas import Game, Player, Season, SeasonType

CANONICAL_NAMESPACE = uuid.UUID("7aca1fe2-42e1-4b76-b725-05126aabdc6c")
NBADB_V238_SOURCE_ID = "nbadb:kaggle:wyattowalsh/basketball:v238"

_SEASON_LABEL = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{2})$")
_SEASON_TYPE_MAP = {
    "regular season": SeasonType.REGULAR,
    "regular": SeasonType.REGULAR,
    "playoffs": SeasonType.PLAYOFF,
    "playoff": SeasonType.PLAYOFF,
    "play-in": SeasonType.PLAY_IN,
    "play in": SeasonType.PLAY_IN,
    "play-in tournament": SeasonType.PLAY_IN,
    "all star": SeasonType.ALL_STAR,
    "all-star": SeasonType.ALL_STAR,
    "pre season": SeasonType.PRESEASON,
    "preseason": SeasonType.PRESEASON,
}


def canonical_id(entity: str, provider: str, provider_id: str) -> str:
    """Build a stable project-owned identifier without using a display name."""
    if not entity.strip() or not provider.strip() or not provider_id.strip():
        raise ValueError("canonical ID inputs must be non-empty")
    value = uuid.uuid5(CANONICAL_NAMESPACE, f"{entity}:{provider}:{provider_id}")
    return f"{entity}_{value.hex}"


def parse_season_label(label: str) -> int:
    """Return the season start year after validating an NBA `YYYY-YY` label."""
    match = _SEASON_LABEL.fullmatch(label.strip())
    if match is None:
        raise ValueError(f"invalid NBA season label: {label!r}")
    start_year = int(match.group("start"))
    expected_end = str(start_year + 1)[-2:]
    if match.group("end") != expected_end:
        raise ValueError(f"season label end year must be {expected_end}")
    return start_year


def season_label(start_year: int) -> str:
    if start_year < 1946:
        raise ValueError("NBA season start year cannot precede 1946")
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_start_year_from_nbadb_id(raw_season_id: str) -> int:
    """Extract the four-digit start year from nbadb's type-prefixed season ID."""
    raw = raw_season_id.strip()
    if not re.fullmatch(r"\d{5}", raw):
        raise ValueError(f"invalid nbadb season_id: {raw_season_id!r}")
    start_year = int(raw[-4:])
    if start_year < 1946:
        raise ValueError(f"invalid NBA start year in season_id: {raw_season_id!r}")
    return start_year


def normalize_season_type(raw_value: str) -> SeasonType:
    """Map observed provider labels to the closed canonical vocabulary."""
    normalized = " ".join(raw_value.strip().lower().split())
    try:
        return _SEASON_TYPE_MAP[normalized]
    except KeyError as error:
        raise ValueError(f"unsupported source season type: {raw_value!r}") from error


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    if not numeric.is_integer():
        return None
    return int(numeric)


def _optional_date(value: object) -> date | None:
    if value is None or not str(value).strip():
        return None
    return datetime.fromisoformat(str(value)).date()


def _height_cm(value: object) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(r"(?P<feet>\d+)-(?P<inches>\d+)", str(value).strip())
    if match is None:
        return None
    total_inches = int(match.group("feet")) * 12 + int(match.group("inches"))
    return round(total_inches * 2.54, 2)


def _weight_kg(value: object) -> float | None:
    if value is None:
        return None
    try:
        pounds = float(str(value).strip())
    except ValueError:
        return None
    return round(pounds * 0.45359237, 3)


def transform_nbadb_player(
    player_row: Mapping[str, object],
    common_info_row: Mapping[str, object] | None,
    *,
    updated_at: datetime,
    source_id: str = NBADB_V238_SOURCE_ID,
) -> Player:
    """Transform joined physical `player`/`common_player_info` evidence."""
    nba_player_id = str(player_row["id"])
    info: Mapping[str, object] = common_info_row or {}
    return Player(
        player_id=canonical_id("player", "nba", nba_player_id),
        nba_player_id=nba_player_id,
        full_name=str(player_row["full_name"]),
        first_name=str(player_row["first_name"]) if player_row.get("first_name") else None,
        last_name=str(player_row["last_name"]) if player_row.get("last_name") else None,
        birth_date=_optional_date(info.get("birthdate")),
        country=str(info["country"]) if info.get("country") else None,
        height_cm=_height_cm(info.get("height")),
        weight_kg=_weight_kg(info.get("weight")),
        primary_position=str(info["position"]) if info.get("position") else None,
        draft_year=_optional_int(info.get("draft_year")),
        draft_round=_optional_int(info.get("draft_round")),
        draft_pick=_optional_int(info.get("draft_number")),
        career_start_year=_optional_int(info.get("from_year")),
        career_end_year=_optional_int(info.get("to_year")),
        is_active=bool(player_row["is_active"]),
        source_id=source_id,
        updated_at=updated_at,
    )


def transform_nbadb_season(
    raw_season_id: str,
    *,
    updated_at: datetime,
    source_id: str = NBADB_V238_SOURCE_ID,
) -> Season:
    start_year = season_start_year_from_nbadb_id(raw_season_id)
    return Season(
        season_id=start_year,
        season_label=season_label(start_year),
        start_year=start_year,
        end_year=start_year + 1,
        games_scheduled=None,
        league="NBA",
        source_id=source_id,
        updated_at=updated_at,
    )


def transform_nbadb_game(
    game_row: Mapping[str, object],
    team_id_by_nba_id: Mapping[str, str],
    *,
    updated_at: datetime,
    source_id: str = NBADB_V238_SOURCE_ID,
) -> Game:
    """Transform one deduplicated physical `game` row."""
    nba_game_id = str(game_row["game_id"])
    home_nba_id = str(game_row["team_id_home"])
    away_nba_id = str(game_row["team_id_away"])
    try:
        home_team_id = team_id_by_nba_id[home_nba_id]
        away_team_id = team_id_by_nba_id[away_nba_id]
    except KeyError as error:
        raise ValueError(f"unresolved NBA team ID: {error.args[0]}") from error
    home_score = _optional_int(game_row.get("pts_home"))
    away_score = _optional_int(game_row.get("pts_away"))
    winner_team_id = None
    if home_score is not None and away_score is not None:
        if home_score > away_score:
            winner_team_id = home_team_id
        elif away_score > home_score:
            winner_team_id = away_team_id
    game_date = _optional_date(game_row.get("game_date"))
    if game_date is None:
        raise ValueError("game_date is required for canonical games")
    return Game(
        game_id=canonical_id("game", "nba", nba_game_id),
        nba_game_id=nba_game_id,
        season_id=season_start_year_from_nbadb_id(str(game_row["season_id"])),
        game_date=game_date,
        season_type=normalize_season_type(str(game_row["season_type"])),
        playoff_round=None,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=home_score,
        away_score=away_score,
        winner_team_id=winner_team_id,
        source_id=source_id,
        updated_at=updated_at,
    )


def utc_datetime(value: str) -> datetime:
    """Parse a fixed UTC timestamp for deterministic pipelines and fixtures."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)
