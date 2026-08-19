"""Typed Silver schema V1 for project-owned canonical NBA facts."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanonicalModel(BaseModel):
    """Strict immutable base for canonical records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    @field_validator("source_id", check_fields=False)
    @classmethod
    def source_id_must_be_present(cls, value: str) -> str:
        if not value:
            raise ValueError("source_id must preserve provenance")
        return value

    @field_validator("updated_at", check_fields=False)
    @classmethod
    def updated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value


class SeasonType(StrEnum):
    REGULAR = "REGULAR"
    PLAYOFF = "PLAYOFF"
    PLAY_IN = "PLAY_IN"
    ALL_STAR = "ALL_STAR"
    PRESEASON = "PRESEASON"


class SeasonRowScope(StrEnum):
    TEAM = "TEAM"
    TOTAL = "TOTAL"


class AwardType(StrEnum):
    MVP = "MVP"
    FINALS_MVP = "FINALS_MVP"
    DPOY = "DPOY"
    ROY = "ROY"
    MIP = "MIP"
    SIXTH_MAN = "SIXTH_MAN"
    ALL_NBA = "ALL_NBA"
    ALL_DEFENSE = "ALL_DEFENSE"
    ALL_STAR = "ALL_STAR"
    SCORING_TITLE = "SCORING_TITLE"
    REBOUND_TITLE = "REBOUND_TITLE"
    ASSIST_TITLE = "ASSIST_TITLE"
    STEAL_TITLE = "STEAL_TITLE"
    BLOCK_TITLE = "BLOCK_TITLE"


class CoverageStatus(StrEnum):
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    HISTORICALLY_UNAVAILABLE = "HISTORICALLY_UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class MetricOrigin(StrEnum):
    RAW = "RAW"
    DERIVED = "DERIVED"


class Player(CanonicalModel):
    player_id: str
    nba_player_id: str | None
    full_name: str
    first_name: str | None
    last_name: str | None
    birth_date: date | None
    country: str | None
    height_cm: float | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, gt=0)
    primary_position: str | None
    draft_year: int | None = Field(default=None, ge=1946)
    draft_round: int | None = Field(default=None, ge=1)
    draft_pick: int | None = Field(default=None, ge=1)
    career_start_year: int | None = Field(default=None, ge=1946)
    career_end_year: int | None = Field(default=None, ge=1946)
    is_active: bool
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def career_years_are_ordered(self) -> Self:
        if (
            self.career_start_year is not None
            and self.career_end_year is not None
            and self.career_end_year < self.career_start_year
        ):
            raise ValueError("career_end_year cannot precede career_start_year")
        return self


class Season(CanonicalModel):
    season_id: int = Field(ge=1946)
    season_label: str
    start_year: int = Field(ge=1946)
    end_year: int = Field(ge=1947)
    games_scheduled: int | None = Field(default=None, ge=0)
    league: str
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def identifiers_are_consistent(self) -> Self:
        expected_label = f"{self.start_year}-{str(self.end_year)[-2:]}"
        if self.season_id != self.start_year:
            raise ValueError("season_id must equal start_year in schema V1")
        if self.end_year != self.start_year + 1:
            raise ValueError("end_year must be start_year + 1")
        if self.season_label != expected_label:
            raise ValueError(f"season_label must be {expected_label}")
        return self


class Franchise(CanonicalModel):
    franchise_id: str
    current_name: str
    source_id: str
    updated_at: datetime


class Team(CanonicalModel):
    team_id: str
    nba_team_id: str | None
    franchise_id: str
    team_name: str
    abbreviation: str | None
    city: str | None
    valid_from_year: int = Field(ge=1946)
    valid_to_year: int | None = Field(default=None, ge=1946)
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def validity_window_is_ordered(self) -> Self:
        if self.valid_to_year is not None and self.valid_to_year < self.valid_from_year:
            raise ValueError("valid_to_year cannot precede valid_from_year")
        return self


class Game(CanonicalModel):
    game_id: str
    nba_game_id: str | None
    season_id: int = Field(ge=1946)
    game_date: date
    season_type: SeasonType
    playoff_round: str | None
    home_team_id: str
    away_team_id: str
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)
    winner_team_id: str | None
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def game_teams_and_result_are_consistent(self) -> Self:
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away teams must differ")
        if self.winner_team_id not in {None, self.home_team_id, self.away_team_id}:
            raise ValueError("winner_team_id must be one of the participating teams")
        if self.home_score is not None and self.away_score is not None:
            expected_winner = (
                self.home_team_id
                if self.home_score > self.away_score
                else self.away_team_id
                if self.away_score > self.home_score
                else None
            )
            if self.winner_team_id != expected_winner:
                raise ValueError("winner_team_id conflicts with final scores")
        return self


class PlayerGameStats(CanonicalModel):
    game_id: str
    player_id: str
    team_id: str
    season_id: int = Field(ge=1946)
    season_type: SeasonType
    minutes: float | None = Field(default=None, ge=0)
    points: int | None = Field(default=None, ge=0)
    fgm: int | None = Field(default=None, ge=0)
    fga: int | None = Field(default=None, ge=0)
    fg3m: int | None = Field(default=None, ge=0)
    fg3a: int | None = Field(default=None, ge=0)
    ftm: int | None = Field(default=None, ge=0)
    fta: int | None = Field(default=None, ge=0)
    oreb: int | None = Field(default=None, ge=0)
    dreb: int | None = Field(default=None, ge=0)
    rebounds: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)
    steals: int | None = Field(default=None, ge=0)
    blocks: int | None = Field(default=None, ge=0)
    turnovers: int | None = Field(default=None, ge=0)
    personal_fouls: int | None = Field(default=None, ge=0)
    plus_minus: float | None = None
    started: bool | None
    did_play: bool | None
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def made_counts_do_not_exceed_attempts(self) -> Self:
        for made, attempted in ((self.fgm, self.fga), (self.fg3m, self.fg3a), (self.ftm, self.fta)):
            if made is not None and attempted is not None and made > attempted:
                raise ValueError("made shots cannot exceed attempts")
        return self


class PlayerSeasonStats(CanonicalModel):
    player_id: str
    season_id: int = Field(ge=1946)
    season_type: SeasonType
    row_scope: SeasonRowScope
    team_id: str | None
    games_played: int | None = Field(default=None, ge=0)
    games_started: int | None = Field(default=None, ge=0)
    minutes_total: float | None = Field(default=None, ge=0)
    points_total: int | None = Field(default=None, ge=0)
    fgm_total: int | None = Field(default=None, ge=0)
    fga_total: int | None = Field(default=None, ge=0)
    fg3m_total: int | None = Field(default=None, ge=0)
    fg3a_total: int | None = Field(default=None, ge=0)
    ftm_total: int | None = Field(default=None, ge=0)
    fta_total: int | None = Field(default=None, ge=0)
    oreb_total: int | None = Field(default=None, ge=0)
    dreb_total: int | None = Field(default=None, ge=0)
    rebounds_total: int | None = Field(default=None, ge=0)
    assists_total: int | None = Field(default=None, ge=0)
    steals_total: int | None = Field(default=None, ge=0)
    blocks_total: int | None = Field(default=None, ge=0)
    turnovers_total: int | None = Field(default=None, ge=0)
    personal_fouls_total: int | None = Field(default=None, ge=0)
    minutes_per_game: float | None = Field(default=None, ge=0)
    points_per_game: float | None = Field(default=None, ge=0)
    rebounds_per_game: float | None = Field(default=None, ge=0)
    assists_per_game: float | None = Field(default=None, ge=0)
    steals_per_game: float | None = Field(default=None, ge=0)
    blocks_per_game: float | None = Field(default=None, ge=0)
    turnovers_per_game: float | None = Field(default=None, ge=0)
    fg_pct: float | None = Field(default=None, ge=0, le=1)
    fg3_pct: float | None = Field(default=None, ge=0, le=1)
    ft_pct: float | None = Field(default=None, ge=0, le=1)
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def scope_matches_team(self) -> Self:
        if self.row_scope is SeasonRowScope.TEAM and self.team_id is None:
            raise ValueError("TEAM rows require team_id")
        if self.row_scope is SeasonRowScope.TOTAL and self.team_id is not None:
            raise ValueError("TOTAL rows must not carry team_id")
        return self


class PlayerSeasonAdvanced(CanonicalModel):
    player_id: str
    season_id: int = Field(ge=1946)
    season_type: SeasonType
    row_scope: SeasonRowScope
    team_id: str | None
    games_played: int | None = Field(default=None, ge=0)
    minutes: float | None = Field(default=None, ge=0)
    offensive_rating: float | None
    defensive_rating: float | None
    net_rating: float | None
    pace: float | None = Field(default=None, ge=0)
    usage_pct: float | None = Field(default=None, ge=0)
    true_shooting_pct: float | None = Field(default=None, ge=0)
    effective_fg_pct: float | None = Field(default=None, ge=0)
    assist_pct: float | None = Field(default=None, ge=0)
    oreb_pct: float | None = Field(default=None, ge=0)
    dreb_pct: float | None = Field(default=None, ge=0)
    rebound_pct: float | None = Field(default=None, ge=0)
    turnover_pct: float | None = Field(default=None, ge=0)
    pie: float | None
    possessions: float | None = Field(default=None, ge=0)
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def scope_matches_team(self) -> Self:
        if self.row_scope is SeasonRowScope.TEAM and self.team_id is None:
            raise ValueError("TEAM rows require team_id")
        if self.row_scope is SeasonRowScope.TOTAL and self.team_id is not None:
            raise ValueError("TOTAL rows must not carry team_id")
        return self


class PlayerAward(CanonicalModel):
    award_id: str
    player_id: str
    season_id: int = Field(ge=1946)
    award_type: AwardType
    award_level: str | None
    source_id: str
    updated_at: datetime


class MetricCoverage(CanonicalModel):
    canonical_entity: str
    metric: str
    provider: str
    first_reliable_season: int | None = Field(default=None, ge=1946)
    last_reliable_season: int | None = Field(default=None, ge=1946)
    season_type: SeasonType
    coverage_status: CoverageStatus
    metric_origin: MetricOrigin
    cross_era_eligible: bool
    methodology: str
    notes: str | None
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def reliable_window_is_ordered(self) -> Self:
        if (
            self.first_reliable_season is not None
            and self.last_reliable_season is not None
            and self.last_reliable_season < self.first_reliable_season
        ):
            raise ValueError("last_reliable_season cannot precede first_reliable_season")
        if self.coverage_status in {
            CoverageStatus.HISTORICALLY_UNAVAILABLE,
            CoverageStatus.SOURCE_UNAVAILABLE,
            CoverageStatus.UNKNOWN,
        } and (self.first_reliable_season is not None or self.last_reliable_season is not None):
            raise ValueError("unavailable/unknown coverage cannot claim a reliable season window")
        return self
