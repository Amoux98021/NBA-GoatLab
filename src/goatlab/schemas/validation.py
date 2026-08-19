"""Cross-record uniqueness and referential-integrity validation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from goatlab.schemas import (
    Franchise,
    Game,
    MetricCoverage,
    Player,
    PlayerAward,
    PlayerGameStats,
    PlayerSeasonAdvanced,
    PlayerSeasonStats,
    Season,
    Team,
)


class CanonicalIntegrityError(ValueError):
    """Raised when records are valid individually but inconsistent as a batch."""


@dataclass(frozen=True)
class CanonicalBatch:
    players: Sequence[Player] = field(default_factory=tuple)
    seasons: Sequence[Season] = field(default_factory=tuple)
    franchises: Sequence[Franchise] = field(default_factory=tuple)
    teams: Sequence[Team] = field(default_factory=tuple)
    games: Sequence[Game] = field(default_factory=tuple)
    player_game_stats: Sequence[PlayerGameStats] = field(default_factory=tuple)
    player_season_stats: Sequence[PlayerSeasonStats] = field(default_factory=tuple)
    player_season_advanced: Sequence[PlayerSeasonAdvanced] = field(default_factory=tuple)
    player_awards: Sequence[PlayerAward] = field(default_factory=tuple)
    metric_coverage: Sequence[MetricCoverage] = field(default_factory=tuple)


def validate_unique(records: Iterable[Any], fields: tuple[str, ...], entity: str) -> None:
    seen: set[tuple[object, ...]] = set()
    for record in records:
        key = tuple(getattr(record, name) for name in fields)
        if key in seen:
            raise CanonicalIntegrityError(f"duplicate {entity} key {fields}: {key}")
        seen.add(key)


def validate_canonical_batch(batch: CanonicalBatch) -> None:
    """Validate canonical keys and cross-entity references for one Silver batch."""
    validate_unique(batch.players, ("player_id",), "players")
    validate_unique(batch.seasons, ("season_id",), "seasons")
    validate_unique(batch.franchises, ("franchise_id",), "franchises")
    validate_unique(batch.teams, ("team_id",), "teams")
    validate_unique(batch.games, ("game_id",), "games")
    validate_unique(
        batch.player_game_stats,
        ("game_id", "player_id", "team_id"),
        "player_game_stats",
    )
    validate_unique(
        batch.player_season_stats,
        ("player_id", "season_id", "season_type", "row_scope", "team_id"),
        "player_season_stats",
    )
    validate_unique(
        batch.player_season_advanced,
        ("player_id", "season_id", "season_type", "row_scope", "team_id"),
        "player_season_advanced",
    )
    validate_unique(batch.player_awards, ("award_id",), "player_awards")
    validate_unique(
        batch.metric_coverage,
        ("canonical_entity", "metric", "provider", "season_type"),
        "metric_coverage",
    )

    player_ids = {record.player_id for record in batch.players}
    season_ids = {record.season_id for record in batch.seasons}
    franchise_ids = {record.franchise_id for record in batch.franchises}
    team_ids = {record.team_id for record in batch.teams}
    game_by_id = {record.game_id: record for record in batch.games}

    errors: list[str] = []
    for team in batch.teams:
        if team.franchise_id not in franchise_ids:
            errors.append(f"team {team.team_id} references unknown franchise {team.franchise_id}")
    for game in batch.games:
        if game.season_id not in season_ids:
            errors.append(f"game {game.game_id} references unknown season {game.season_id}")
        for team_id in (game.home_team_id, game.away_team_id):
            if team_id not in team_ids:
                errors.append(f"game {game.game_id} references unknown team {team_id}")
    for stat in batch.player_game_stats:
        referenced_game = game_by_id.get(stat.game_id)
        if stat.player_id not in player_ids:
            errors.append(f"player_game_stats references unknown player {stat.player_id}")
        if stat.team_id not in team_ids:
            errors.append(f"player_game_stats references unknown team {stat.team_id}")
        if referenced_game is None:
            errors.append(f"player_game_stats references unknown game {stat.game_id}")
        elif stat.team_id not in {referenced_game.home_team_id, referenced_game.away_team_id}:
            errors.append(f"player_game_stats team {stat.team_id} did not play in {stat.game_id}")
        if stat.season_id not in season_ids:
            errors.append(f"player_game_stats references unknown season {stat.season_id}")
        if referenced_game is not None and (
            stat.season_id != referenced_game.season_id
            or stat.season_type != referenced_game.season_type
        ):
            errors.append(f"player_game_stats season context conflicts with game {stat.game_id}")
    for entity, records in (
        ("player_season_stats", batch.player_season_stats),
        ("player_season_advanced", batch.player_season_advanced),
    ):
        for record in records:
            if record.player_id not in player_ids:
                errors.append(f"{entity} references unknown player {record.player_id}")
            if record.season_id not in season_ids:
                errors.append(f"{entity} references unknown season {record.season_id}")
            if record.team_id is not None and record.team_id not in team_ids:
                errors.append(f"{entity} references unknown team {record.team_id}")
    for award in batch.player_awards:
        if award.player_id not in player_ids:
            errors.append(f"player_awards references unknown player {award.player_id}")
        if award.season_id not in season_ids:
            errors.append(f"player_awards references unknown season {award.season_id}")
    if errors:
        raise CanonicalIntegrityError("; ".join(errors))
