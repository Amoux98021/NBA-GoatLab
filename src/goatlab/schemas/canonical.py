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
    CONFERENCE_FINALS_MVP = "CONFERENCE_FINALS_MVP"
    DPOY = "DPOY"
    ROY = "ROY"
    MIP = "MIP"
    SIXTH_MAN = "SIXTH_MAN"
    CLUTCH_PLAYER = "CLUTCH_PLAYER"
    COMEBACK_PLAYER = "COMEBACK_PLAYER"
    ALL_NBA = "ALL_NBA"
    ALL_DEFENSE = "ALL_DEFENSE"
    ALL_ROOKIE = "ALL_ROOKIE"
    ALL_STAR = "ALL_STAR"
    ALL_STAR_MVP = "ALL_STAR_MVP"
    NBA_CUP_MVP = "NBA_CUP_MVP"
    NBA_CUP_ALL_TOURNAMENT = "NBA_CUP_ALL_TOURNAMENT"
    NBA_CHAMPION = "NBA_CHAMPION"
    PLAYER_OF_MONTH = "PLAYER_OF_MONTH"
    PLAYER_OF_WEEK = "PLAYER_OF_WEEK"
    ROOKIE_OF_MONTH = "ROOKIE_OF_MONTH"
    DEFENSIVE_PLAYER_OF_MONTH = "DEFENSIVE_PLAYER_OF_MONTH"
    SCORING_TITLE = "SCORING_TITLE"
    REBOUND_TITLE = "REBOUND_TITLE"
    ASSIST_TITLE = "ASSIST_TITLE"
    STEAL_TITLE = "STEAL_TITLE"
    BLOCK_TITLE = "BLOCK_TITLE"
    OTHER = "OTHER"


class AwardScope(StrEnum):
    LEAGUE = "LEAGUE"
    CONFERENCE = "CONFERENCE"
    TEAM = "TEAM"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


class AwardTaxonomyStatus(StrEnum):
    CANONICAL_CORE = "CANONICAL_CORE"
    CANONICAL_SECONDARY = "CANONICAL_SECONDARY"
    MINOR_RECURRING = "MINOR_RECURRING"
    NON_PLAYER_COMPETITIVE = "NON_PLAYER_COMPETITIVE"
    UNKNOWN = "UNKNOWN"


class AllStarSelectionStatus(StrEnum):
    ROSTER_LISTED = "ROSTER_LISTED"
    PLAYERAWARDS_EVENT = "PLAYERAWARDS_EVENT"
    MULTIPLE_EVIDENCE = "MULTIPLE_EVIDENCE"
    PARTICIPATION_ONLY = "PARTICIPATION_ONLY"


class AllStarParticipationStatus(StrEnum):
    GAME_PARTICIPANT = "GAME_PARTICIPANT"
    DNP_ROSTERED = "DNP_ROSTERED"
    NO_PARTICIPATION_EVIDENCE = "NO_PARTICIPATION_EVIDENCE"


class StatLeaderCategory(StrEnum):
    PTS = "PTS"
    REB = "REB"
    AST = "AST"
    STL = "STL"
    BLK = "BLK"


class StatLeaderReconciliationStatus(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    TIE_MATCH = "TIE_MATCH"
    VALUE_MATCH = "VALUE_MATCH"
    QUALIFICATION_DIFFERENCE = "QUALIFICATION_DIFFERENCE"
    SOURCE_COVERAGE_GAP = "SOURCE_COVERAGE_GAP"
    DERIVED_COVERAGE_GAP = "DERIVED_COVERAGE_GAP"
    UNRESOLVED = "UNRESOLVED"


class PostseasonFormatStatus(StrEnum):
    STANDARD_SERIES_BRACKET = "STANDARD_SERIES_BRACKET"
    NONSTANDARD_SERIES_FORMAT = "NONSTANDARD_SERIES_FORMAT"
    ROUND_ROBIN_OR_MIXED = "ROUND_ROBIN_OR_MIXED"
    UNCERTAIN = "UNCERTAIN"


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
    nba_player_id: str
    season_id: int | None = Field(default=None, ge=1946)
    season_label_raw: str | None
    season_mapping_status: str
    award_type: AwardType
    award_level: str | None
    award_scope: AwardScope
    team_number: int | None = Field(default=None, ge=1, le=3)
    conference: str | None
    month: str | None
    week: str | None
    source_description: str
    source_type: str | None
    source_subtype1: str | None
    source_subtype2: str | None
    source_subtype3: str | None
    source_team: str | None
    taxonomy_status: AwardTaxonomyStatus
    source_event_fingerprint: str
    source_id: str
    retrieved_at: datetime
    methodology_version: str
    updated_at: datetime

    @model_validator(mode="after")
    def season_and_team_level_are_consistent(self) -> Self:
        if self.season_mapping_status == "MAPPED" and self.season_id is None:
            raise ValueError("mapped award season requires season_id")
        if self.season_mapping_status != "MAPPED" and self.season_id is not None:
            raise ValueError("unmapped award season cannot carry season_id")
        if self.team_number is None and self.award_level is not None:
            raise ValueError("award_level requires team_number")
        if self.team_number is not None:
            expected = {1: "FIRST", 2: "SECOND", 3: "THIRD"}[self.team_number]
            if self.award_level != expected:
                raise ValueError("award_level conflicts with team_number")
        return self


class PlayerAllStarEvidence(CanonicalModel):
    all_star_event_id: str
    player_id: str
    nba_player_id: str
    season_id: int = Field(ge=1950)
    source_game_ids: tuple[str, ...]
    roster_evidence: bool
    participation_evidence: bool
    playerawards_evidence: bool | None
    playerawards_acquisition_status: str
    selection_status: AllStarSelectionStatus
    participation_status: AllStarParticipationStatus
    all_star_games_played: int = Field(ge=0)
    minutes: float | None = Field(default=None, ge=0)
    points: int | None = Field(default=None, ge=0)
    rebounds: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)
    steals: int | None = Field(default=None, ge=0)
    blocks: int | None = Field(default=None, ge=0)
    source_roster_labels: tuple[str, ...]
    roster_scope: str
    starter_status: str | None
    replacement_status: str | None
    coverage_status: str
    corpus_id: str
    methodology_version: str
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def evidence_is_consistent(self) -> Self:
        if not (self.roster_evidence or self.participation_evidence or self.playerawards_evidence):
            raise ValueError("All-Star record requires factual evidence")
        if self.participation_evidence != (self.all_star_games_played > 0):
            raise ValueError("participation evidence must agree with games played")
        if self.participation_status is AllStarParticipationStatus.DNP_ROSTERED and not (
            self.roster_evidence and self.all_star_games_played == 0
        ):
            raise ValueError("DNP status requires roster evidence and zero games")
        return self


class PlayerStatLeader(CanonicalModel):
    stat_leader_event_id: str
    player_id: str
    nba_player_id: str
    season_id: int = Field(ge=1946)
    stat_category: StatLeaderCategory
    official_source_rank: int | None = Field(default=None, ge=1)
    official_source_value: float | None
    derived_per_game_value: float | None
    derived_total_value: float | None
    is_derived_raw_per_game_leader: bool
    is_derived_raw_total_leader: bool
    is_derived_qualified_leader: bool
    leader_semantics: tuple[str, ...]
    qualification_status: str
    reconciliation_status: StatLeaderReconciliationStatus
    source_coverage_status: str
    corpus_id: str
    methodology_version: str
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def leader_evidence_is_present(self) -> Self:
        if self.official_source_rank is None and not (
            self.is_derived_raw_per_game_leader
            or self.is_derived_raw_total_leader
            or self.is_derived_qualified_leader
        ):
            raise ValueError("stat leader event requires source or derived leader evidence")
        if not self.leader_semantics:
            raise ValueError("stat leader semantics cannot be empty")
        return self


class TeamSeasonResult(CanonicalModel):
    team_id: str
    nba_team_id: str
    franchise_id: str
    season_id: int = Field(ge=1946)
    regular_games: int = Field(ge=0)
    regular_wins: int = Field(ge=0)
    regular_losses: int = Field(ge=0)
    regular_win_pct: float | None = Field(default=None, ge=0, le=1)
    regular_points_for: int | None = Field(default=None, ge=0)
    regular_points_against: int | None = Field(default=None, ge=0)
    regular_point_diff: int | None
    regular_point_diff_per_game: float | None
    league_size: int = Field(ge=1)
    win_pct_rank: int = Field(ge=1)
    win_pct_percentile: float = Field(ge=0, le=1)
    point_diff_rank: int | None = Field(default=None, ge=1)
    point_diff_percentile: float | None = Field(default=None, ge=0, le=1)
    wins_relative_to_league_mean: float
    win_pct_z_score: float | None
    point_diff_z_score: float | None
    made_playoffs: bool
    playoff_games: int = Field(ge=0)
    playoff_wins: int = Field(ge=0)
    playoff_losses: int = Field(ge=0)
    playoff_win_pct: float | None = Field(default=None, ge=0, le=1)
    finalist: bool
    champion: bool
    finals_opponent_team_id: str | None
    series_played: int | None = Field(default=None, ge=0)
    series_won: int | None = Field(default=None, ge=0)
    series_lost: int | None = Field(default=None, ge=0)
    postseason_format_status: PostseasonFormatStatus
    postseason_stage_confidence: str
    corpus_id: str
    corpus_fingerprint: str
    methodology_version: str
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def records_and_postseason_are_consistent(self) -> Self:
        if self.regular_wins + self.regular_losses != self.regular_games:
            raise ValueError("regular wins + losses must equal games")
        if self.playoff_wins + self.playoff_losses != self.playoff_games:
            raise ValueError("playoff wins + losses must equal games")
        if self.champion and self.finalist:
            raise ValueError("champion and runner-up finalist must be distinct")
        reached_finals = self.champion or self.finalist
        if reached_finals != (self.finals_opponent_team_id is not None):
            raise ValueError("Finals participant status and opponent must agree")
        if not self.made_playoffs and self.playoff_games:
            raise ValueError("playoff games require postseason participation")
        return self


class FinalsGame(CanonicalModel):
    game_id: str
    nba_game_id: str
    season_id: int = Field(ge=1946)
    game_date: date
    home_team_id: str
    away_team_id: str
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    winner_team_id: str
    venue_assignment_status: str
    champion_team_id: str
    finalist_team_id: str
    finals_game_number: int = Field(ge=1)
    corpus_id: str
    corpus_fingerprint: str
    methodology_version: str
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def finals_game_is_consistent(self) -> Self:
        teams = {self.home_team_id, self.away_team_id}
        if teams != {self.champion_team_id, self.finalist_team_id}:
            raise ValueError("Finals game teams must be champion and finalist")
        if self.winner_team_id not in teams:
            raise ValueError("Finals winner must participate in the game")
        return self


class PlayerTeamSeasonParticipation(CanonicalModel):
    player_id: str
    team_id: str
    season_id: int = Field(ge=1946)
    regular_games: int = Field(ge=0)
    regular_minutes: float | None = Field(default=None, ge=0)
    playoff_games: int = Field(ge=0)
    playoff_wins_while_participating: int = Field(ge=0)
    playoff_minutes: float | None = Field(default=None, ge=0)
    finals_games: int = Field(ge=0)
    finals_minutes: float | None = Field(default=None, ge=0)
    team_regular_games: int = Field(ge=0)
    team_playoff_games: int = Field(ge=0)
    team_finals_games: int = Field(ge=0)
    regular_game_share: float | None = Field(default=None, ge=0, le=1)
    playoff_game_share: float | None = Field(default=None, ge=0, le=1)
    finals_game_share: float | None = Field(default=None, ge=0, le=1)
    regular_minutes_share: float | None = Field(default=None, ge=0, le=1)
    playoff_minutes_share: float | None = Field(default=None, ge=0, le=1)
    finals_minutes_share: float | None = Field(default=None, ge=0, le=1)
    regular_minutes_coverage: str
    playoff_minutes_coverage: str
    finals_minutes_coverage: str
    team_made_playoffs: bool
    team_finalist: bool
    team_champion: bool
    regular_season_member_of_champion_team: bool
    played_playoffs_for_champion_team: bool
    played_finals_for_champion_team: bool
    official_nba_champion_award_event: bool | None
    award_acquisition_status: str
    corpus_id: str
    corpus_fingerprint: str
    awards_methodology_version: str
    methodology_version: str
    source_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def shares_and_champion_variants_are_consistent(self) -> Self:
        if self.regular_games > self.team_regular_games:
            raise ValueError("player regular games cannot exceed team games")
        if self.playoff_games > self.team_playoff_games:
            raise ValueError("player playoff games cannot exceed team playoff games")
        if self.finals_games > self.team_finals_games:
            raise ValueError("player Finals games cannot exceed team Finals games")
        if self.played_playoffs_for_champion_team != (
            self.team_champion and self.playoff_games > 0
        ):
            raise ValueError("playoff champion participation flag conflicts with facts")
        if self.played_finals_for_champion_team != (self.team_champion and self.finals_games > 0):
            raise ValueError("Finals champion participation flag conflicts with facts")
        return self


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
