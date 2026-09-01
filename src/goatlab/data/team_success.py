"""Coverage-aware team outcome and player participation primitives."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, cast

from goatlab.data.awards import AWARDS_METHODOLOGY_VERSION, AwardAcquisitionStatus
from goatlab.schemas import (
    FinalsGame,
    PlayerTeamSeasonParticipation,
    PostseasonFormatStatus,
    TeamSeasonResult,
)

TEAM_SUCCESS_METHODOLOGY_VERSION = "team-success-postseason-v1"
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
AWARDS_FINGERPRINT = "666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258"
SOURCE_ID = "derived:GOATLAB-HIST-V1:team-success-postseason-v1"


class TeamSuccessCoverage(StrEnum):
    RELIABLE = "RELIABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    FORMAT_BLOCKED = "FORMAT_BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TeamIdentity:
    team_id: str
    nba_team_id: str
    franchise_id: str
    team_name: str


@dataclass(frozen=True)
class CanonicalGameEvidence:
    game_id: str
    nba_game_id: str
    season_id: int
    season_type: str
    game_date: date
    home_team_id: str
    away_team_id: str
    home_score: int | None
    away_score: int | None
    winner_team_id: str
    venue_assignment_status: str
    score_reliable: bool
    source_id: str

    def __post_init__(self) -> None:
        teams = {self.home_team_id, self.away_team_id}
        if len(teams) != 2:
            raise ValueError("game must contain two different teams")
        if self.winner_team_id not in teams:
            raise ValueError("winner must be a participating team")
        if self.score_reliable:
            if self.home_score is None or self.away_score is None:
                raise ValueError("reliable score must be observed")
            expected = self.home_team_id if self.home_score > self.away_score else self.away_team_id
            if self.home_score == self.away_score or self.winner_team_id != expected:
                raise ValueError("game score and winner are inconsistent")


@dataclass(frozen=True)
class FinalsOutcome:
    season_id: int
    champion_team_id: str
    finalist_team_id: str
    deciding_game_id: str
    deciding_game_date: date


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def population_z(value: float, population: Sequence[float]) -> float | None:
    if not population:
        return None
    standard_deviation = statistics.pstdev(population)
    if standard_deviation == 0:
        return None
    return (value - statistics.fmean(population)) / standard_deviation


def midrank_percentile(value: float, population: Sequence[float]) -> float:
    if not population:
        raise ValueError("percentile population cannot be empty")
    below = sum(candidate < value for candidate in population)
    equal = sum(candidate == value for candidate in population)
    return (below + 0.5 * equal) / len(population)


def descending_competition_rank(value: float, population: Sequence[float]) -> int:
    return 1 + sum(candidate > value for candidate in population)


def infer_finals_outcome(playoff_games: Sequence[CanonicalGameEvidence]) -> FinalsOutcome:
    if not playoff_games:
        raise ValueError("cannot infer Finals from an empty postseason")
    seasons = {game.season_id for game in playoff_games}
    types = {game.season_type for game in playoff_games}
    if len(seasons) != 1 or types != {"PLAYOFF"}:
        raise ValueError("Finals inference requires one isolated playoff season")
    last_date = max(game.game_date for game in playoff_games)
    last_games = [game for game in playoff_games if game.game_date == last_date]
    if len(last_games) != 1:
        raise ValueError("chronologically final playoff game is not unique")
    final_game = last_games[0]
    finalist = (
        final_game.away_team_id
        if final_game.winner_team_id == final_game.home_team_id
        else final_game.home_team_id
    )
    return FinalsOutcome(
        season_id=final_game.season_id,
        champion_team_id=final_game.winner_team_id,
        finalist_team_id=finalist,
        deciding_game_id=final_game.game_id,
        deciding_game_date=final_game.game_date,
    )


def identify_finals_games(
    playoff_games: Sequence[CanonicalGameEvidence], outcome: FinalsOutcome, *, updated_at: datetime
) -> list[FinalsGame]:
    participants = {outcome.champion_team_id, outcome.finalist_team_id}
    selected = sorted(
        [game for game in playoff_games if {game.home_team_id, game.away_team_id} == participants],
        key=lambda game: (game.game_date, game.nba_game_id),
    )
    if not selected or selected[-1].game_id != outcome.deciding_game_id:
        raise ValueError("Finals matchup does not contain the deciding game")
    if any(not game.score_reliable for game in selected):
        raise ValueError("Finals score evidence is not reliable")
    return [
        FinalsGame(
            game_id=game.game_id,
            nba_game_id=game.nba_game_id,
            season_id=game.season_id,
            game_date=game.game_date,
            home_team_id=game.home_team_id,
            away_team_id=game.away_team_id,
            home_score=cast(int, game.home_score),
            away_score=cast(int, game.away_score),
            winner_team_id=game.winner_team_id,
            venue_assignment_status=game.venue_assignment_status,
            champion_team_id=outcome.champion_team_id,
            finalist_team_id=outcome.finalist_team_id,
            finals_game_number=index,
            corpus_id=CORPUS_ID,
            corpus_fingerprint=CORPUS_FINGERPRINT,
            methodology_version=TEAM_SUCCESS_METHODOLOGY_VERSION,
            source_id=game.source_id,
            updated_at=updated_at,
        )
        for index, game in enumerate(selected, start=1)
    ]


def postseason_format_for_season(season_id: int) -> tuple[PostseasonFormatStatus, bool, bool]:
    """Return format class, pair-series eligibility, and modern-label eligibility."""
    if season_id == 1953:
        return PostseasonFormatStatus.ROUND_ROBIN_OR_MIXED, False, False
    if season_id < 1983:
        return PostseasonFormatStatus.NONSTANDARD_SERIES_FORMAT, True, False
    return PostseasonFormatStatus.STANDARD_SERIES_BRACKET, True, True


def series_records(
    playoff_games: Sequence[CanonicalGameEvidence], *, series_inference_allowed: bool
) -> dict[str, tuple[int, int, int] | None]:
    teams = {team for game in playoff_games for team in (game.home_team_id, game.away_team_id)}
    if not series_inference_allowed:
        return {team: None for team in teams}
    pairs: dict[tuple[str, str], list[CanonicalGameEvidence]] = defaultdict(list)
    for game in playoff_games:
        ordered = sorted((game.home_team_id, game.away_team_id))
        pair = (ordered[0], ordered[1])
        pairs[pair].append(game)
    totals: dict[str, list[int]] = {team: [0, 0, 0] for team in teams}
    for pair, games in pairs.items():
        wins = Counter(game.winner_team_id for game in games)
        if wins[pair[0]] == wins[pair[1]]:
            raise ValueError(f"playoff opponent pair has no series winner: {pair}")
        winner = pair[0] if wins[pair[0]] > wins[pair[1]] else pair[1]
        loser = pair[1] if winner == pair[0] else pair[0]
        totals[winner][0] += 1
        totals[winner][1] += 1
        totals[loser][0] += 1
        totals[loser][2] += 1
    return {team: (values[0], values[1], values[2]) for team, values in totals.items()}


def derive_team_season_results(
    regular_games: Sequence[CanonicalGameEvidence],
    playoff_games: Sequence[CanonicalGameEvidence],
    identities: Mapping[str, TeamIdentity],
    outcome: FinalsOutcome,
    *,
    updated_at: datetime,
) -> list[TeamSeasonResult]:
    seasons = {game.season_id for game in (*regular_games, *playoff_games)}
    if len(seasons) != 1:
        raise ValueError("team-season derivation requires one season")
    season_id = next(iter(seasons))
    teams = sorted(
        {team for game in regular_games for team in (game.home_team_id, game.away_team_id)}
    )
    regular: dict[str, dict[str, int]] = {
        team: {"games": 0, "wins": 0, "losses": 0, "for": 0, "against": 0} for team in teams
    }
    scoring_reliable = all(game.score_reliable for game in regular_games)
    for game in regular_games:
        for team, scored, allowed in (
            (game.home_team_id, game.home_score, game.away_score),
            (game.away_team_id, game.away_score, game.home_score),
        ):
            item = regular[team]
            item["games"] += 1
            item["wins" if team == game.winner_team_id else "losses"] += 1
            if scoring_reliable:
                item["for"] += cast(int, scored)
                item["against"] += cast(int, allowed)
    playoff: dict[str, dict[str, int]] = defaultdict(lambda: {"games": 0, "wins": 0, "losses": 0})
    for game in playoff_games:
        for team in (game.home_team_id, game.away_team_id):
            playoff[team]["games"] += 1
            playoff[team]["wins" if team == game.winner_team_id else "losses"] += 1

    win_pcts = [regular[team]["wins"] / regular[team]["games"] for team in teams]
    point_diffs = (
        [
            (regular[team]["for"] - regular[team]["against"]) / regular[team]["games"]
            for team in teams
        ]
        if scoring_reliable
        else []
    )
    mean_wins = statistics.fmean(regular[team]["wins"] for team in teams)
    format_status, series_allowed, _ = postseason_format_for_season(season_id)
    series = series_records(playoff_games, series_inference_allowed=series_allowed)
    output: list[TeamSeasonResult] = []
    for team in teams:
        identity = identities[team]
        item = regular[team]
        post = playoff[team]
        win_pct = item["wins"] / item["games"]
        point_diff = item["for"] - item["against"] if scoring_reliable else None
        point_diff_pg = point_diff / item["games"] if point_diff is not None else None
        is_finalist = team == outcome.finalist_team_id
        opponent = None
        if team == outcome.champion_team_id:
            opponent = outcome.finalist_team_id
        elif team == outcome.finalist_team_id:
            opponent = outcome.champion_team_id
        series_values = series.get(team)
        output.append(
            TeamSeasonResult(
                team_id=team,
                nba_team_id=identity.nba_team_id,
                franchise_id=identity.franchise_id,
                season_id=season_id,
                regular_games=item["games"],
                regular_wins=item["wins"],
                regular_losses=item["losses"],
                regular_win_pct=round(win_pct, 12),
                regular_points_for=item["for"] if scoring_reliable else None,
                regular_points_against=item["against"] if scoring_reliable else None,
                regular_point_diff=point_diff,
                regular_point_diff_per_game=(
                    round(point_diff_pg, 12) if point_diff_pg is not None else None
                ),
                league_size=len(teams),
                win_pct_rank=descending_competition_rank(win_pct, win_pcts),
                win_pct_percentile=round(midrank_percentile(win_pct, win_pcts), 12),
                point_diff_rank=(
                    descending_competition_rank(point_diff_pg, point_diffs)
                    if point_diff_pg is not None
                    else None
                ),
                point_diff_percentile=(
                    round(midrank_percentile(point_diff_pg, point_diffs), 12)
                    if point_diff_pg is not None
                    else None
                ),
                wins_relative_to_league_mean=round(item["wins"] - mean_wins, 12),
                win_pct_z_score=_rounded(population_z(win_pct, win_pcts)),
                point_diff_z_score=(
                    _rounded(population_z(point_diff_pg, point_diffs))
                    if point_diff_pg is not None
                    else None
                ),
                made_playoffs=post["games"] > 0,
                playoff_games=post["games"],
                playoff_wins=post["wins"],
                playoff_losses=post["losses"],
                playoff_win_pct=_rounded(safe_ratio(post["wins"], post["games"])),
                finalist=is_finalist,
                champion=team == outcome.champion_team_id,
                finals_opponent_team_id=opponent,
                series_played=None if series_values is None else series_values[0],
                series_won=None if series_values is None else series_values[1],
                series_lost=None if series_values is None else series_values[2],
                postseason_format_status=format_status,
                postseason_stage_confidence="OFFICIAL_HISTORY_VALIDATED",
                corpus_id=CORPUS_ID,
                corpus_fingerprint=CORPUS_FINGERPRINT,
                methodology_version=TEAM_SUCCESS_METHODOLOGY_VERSION,
                source_id=SOURCE_ID,
                updated_at=updated_at,
            )
        )
    return output


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 12)


def minutes_are_eligible(
    rows: Sequence[Mapping[str, Any]], *, empirical_classification: str
) -> bool:
    if empirical_classification != TeamSuccessCoverage.RELIABLE.value or not rows:
        return False
    values = [row.get("minutes") for row in rows]
    if any(value is None for value in values):
        return False
    observed = cast(list[float | int], values)
    return sum(float(value) > 0 for value in observed) / len(observed) >= 0.99


def build_player_team_participation(
    regular_rows: Sequence[Mapping[str, Any]],
    playoff_rows: Sequence[Mapping[str, Any]],
    team_results: Sequence[TeamSeasonResult],
    finals_game_ids: set[str],
    playoff_game_winners: Mapping[str, str],
    award_status: Mapping[str, str],
    champion_award_seasons: set[tuple[str, int]],
    *,
    regular_minutes_eligible: bool,
    playoff_minutes_eligible: bool,
    updated_at: datetime,
) -> list[PlayerTeamSeasonParticipation]:
    if not team_results:
        return []
    season_id = team_results[0].season_id
    result_by_team = {row.team_id: row for row in team_results}
    keyed_regular: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    keyed_playoff: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in regular_rows:
        keyed_regular[(str(row["player_id"]), str(row["team_id"]))].append(row)
    for row in playoff_rows:
        keyed_playoff[(str(row["player_id"]), str(row["team_id"]))].append(row)
    keys = sorted(set(keyed_regular) | set(keyed_playoff))

    regular_team_minutes = _team_minutes(regular_rows, regular_minutes_eligible)
    playoff_team_minutes = _team_minutes(playoff_rows, playoff_minutes_eligible)
    finals_rows = [row for row in playoff_rows if str(row["game_id"]) in finals_game_ids]
    finals_team_minutes = _team_minutes(finals_rows, playoff_minutes_eligible)
    finals_team_games: Counter[str] = Counter()
    for row in finals_rows:
        finals_team_games[str(row["team_id"])] = max(
            finals_team_games[str(row["team_id"])] + 0,
            len(
                {
                    str(item["game_id"])
                    for item in finals_rows
                    if str(item["team_id"]) == str(row["team_id"])
                }
            ),
        )

    output: list[PlayerTeamSeasonParticipation] = []
    for player_id, team_id in keys:
        result = result_by_team[team_id]
        regular = keyed_regular.get((player_id, team_id), [])
        playoff = keyed_playoff.get((player_id, team_id), [])
        finals = [row for row in playoff if str(row["game_id"]) in finals_game_ids]
        regular_games = len({str(row["game_id"]) for row in regular})
        playoff_games = len({str(row["game_id"]) for row in playoff})
        finals_games = len({str(row["game_id"]) for row in finals})
        player_regular_minutes = _player_minutes(regular, regular_minutes_eligible)
        player_playoff_minutes = _player_minutes(playoff, playoff_minutes_eligible)
        player_finals_minutes = _player_minutes(finals, playoff_minutes_eligible)
        status = award_status[player_id]
        official_event = (
            None
            if status == AwardAcquisitionStatus.NOT_QUERIED.value
            else (player_id, season_id) in champion_award_seasons
        )
        playoff_wins = sum(
            playoff_game_winners.get(str(row["game_id"])) == team_id for row in playoff
        )
        output.append(
            PlayerTeamSeasonParticipation(
                player_id=player_id,
                team_id=team_id,
                season_id=season_id,
                regular_games=regular_games,
                regular_minutes=player_regular_minutes,
                playoff_games=playoff_games,
                playoff_wins_while_participating=playoff_wins,
                playoff_minutes=player_playoff_minutes,
                finals_games=finals_games,
                finals_minutes=player_finals_minutes,
                team_regular_games=result.regular_games,
                team_playoff_games=result.playoff_games,
                team_finals_games=finals_team_games[team_id],
                regular_game_share=_rounded(safe_ratio(regular_games, result.regular_games)),
                playoff_game_share=_rounded(safe_ratio(playoff_games, result.playoff_games)),
                finals_game_share=_rounded(safe_ratio(finals_games, finals_team_games[team_id])),
                regular_minutes_share=_rounded(
                    safe_ratio(player_regular_minutes or 0, regular_team_minutes.get(team_id, 0))
                    if player_regular_minutes is not None
                    else None
                ),
                playoff_minutes_share=_rounded(
                    safe_ratio(player_playoff_minutes or 0, playoff_team_minutes.get(team_id, 0))
                    if player_playoff_minutes is not None
                    else None
                ),
                finals_minutes_share=_rounded(
                    safe_ratio(player_finals_minutes or 0, finals_team_minutes.get(team_id, 0))
                    if player_finals_minutes is not None
                    else None
                ),
                regular_minutes_coverage=(
                    TeamSuccessCoverage.RELIABLE.value
                    if regular_minutes_eligible
                    else TeamSuccessCoverage.UNAVAILABLE.value
                ),
                playoff_minutes_coverage=(
                    TeamSuccessCoverage.RELIABLE.value
                    if playoff_minutes_eligible
                    else TeamSuccessCoverage.UNAVAILABLE.value
                ),
                finals_minutes_coverage=(
                    TeamSuccessCoverage.RELIABLE.value
                    if playoff_minutes_eligible
                    else TeamSuccessCoverage.UNAVAILABLE.value
                ),
                team_made_playoffs=result.made_playoffs,
                team_finalist=result.finalist,
                team_champion=result.champion,
                regular_season_member_of_champion_team=result.champion and regular_games > 0,
                played_playoffs_for_champion_team=result.champion and playoff_games > 0,
                played_finals_for_champion_team=result.champion and finals_games > 0,
                official_nba_champion_award_event=official_event,
                award_acquisition_status=status,
                corpus_id=CORPUS_ID,
                corpus_fingerprint=CORPUS_FINGERPRINT,
                awards_methodology_version=AWARDS_METHODOLOGY_VERSION,
                methodology_version=TEAM_SUCCESS_METHODOLOGY_VERSION,
                source_id=SOURCE_ID,
                updated_at=updated_at,
            )
        )
    return output


def _player_minutes(rows: Sequence[Mapping[str, Any]], eligible: bool) -> float | None:
    if not eligible:
        return None
    values = [row.get("minutes") for row in rows]
    if any(value is None for value in values):
        return None
    observed = cast(list[float | int], values)
    return round(sum(float(value) for value in observed), 12)


def _team_minutes(rows: Sequence[Mapping[str, Any]], eligible: bool) -> dict[str, float]:
    if not eligible:
        return {}
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        value = row.get("minutes")
        if value is None:
            raise ValueError("eligible minutes partition contains NULL")
        totals[str(row["team_id"])] += float(value)
    return {key: round(value, 12) for key, value in totals.items()}


def career_team_context(
    master_players: Sequence[Mapping[str, Any]],
    participation: Sequence[Mapping[str, Any]],
    team_results: Mapping[tuple[str, int], Mapping[str, Any]],
    accolade_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_player: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in participation:
        by_player[str(row["player_id"])].append(row)
    output: list[dict[str, Any]] = []
    for player in sorted(master_players, key=lambda item: str(item["player_id"])):
        player_id = str(player["player_id"])
        rows = by_player.get(player_id, [])
        regular = [row for row in rows if int(row["regular_games"]) > 0]
        playoff = [row for row in rows if int(row["playoff_games"]) > 0]
        finals = [row for row in rows if int(row["finals_games"]) > 0]
        contexts = [team_results[(str(row["team_id"]), int(row["season_id"]))] for row in regular]
        percentiles = [float(row["win_pct_percentile"]) for row in contexts]
        weights = [int(row["regular_games"]) for row in regular]
        accolade = accolade_rows[player_id]
        output.append(
            {
                "player_id": player_id,
                "nba_player_id": str(player["nba_player_id"]),
                "display_name": str(player["display_name"]),
                "career_status": player.get("career_status"),
                "playoff_seasons": len({int(row["season_id"]) for row in playoff}),
                "playoff_games": sum(int(row["playoff_games"]) for row in playoff),
                "playoff_wins_while_participating": sum(
                    int(row["playoff_wins_while_participating"]) for row in playoff
                ),
                "finals_seasons": len({int(row["season_id"]) for row in finals}),
                "finals_games": sum(int(row["finals_games"]) for row in finals),
                "seasons_on_finalist_teams_regular": len(
                    {int(row["season_id"]) for row in regular if bool(row["team_finalist"])}
                ),
                "seasons_on_champion_teams_regular": len(
                    {
                        int(row["season_id"])
                        for row in regular
                        if bool(row["regular_season_member_of_champion_team"])
                    }
                ),
                "seasons_played_playoffs_for_champion": len(
                    {
                        int(row["season_id"])
                        for row in playoff
                        if bool(row["played_playoffs_for_champion_team"])
                    }
                ),
                "seasons_played_finals_for_champion": len(
                    {
                        int(row["season_id"])
                        for row in finals
                        if bool(row["played_finals_for_champion_team"])
                    }
                ),
                "official_nba_champion_award_count": accolade.get("nba_champion_count"),
                "award_acquisition_status": accolade["award_acquisition_status"],
                "mean_team_win_percentile": _mean(percentiles),
                "regular_games_weighted_team_win_percentile": _weighted_mean(percentiles, weights),
                "regular_team_affiliations": len(regular),
                "seasons_on_90th_percentile_regular_teams": len(
                    {
                        int(row["season_id"])
                        for row, context in zip(regular, contexts, strict=True)
                        if float(context["win_pct_percentile"]) >= 0.90
                    }
                ),
                "regular_minutes_covered_affiliations": sum(
                    row["regular_minutes_coverage"] == TeamSuccessCoverage.RELIABLE.value
                    for row in regular
                ),
                "playoff_minutes_covered_affiliations": sum(
                    row["playoff_minutes_coverage"] == TeamSuccessCoverage.RELIABLE.value
                    for row in playoff
                ),
                "finals_minutes_covered_affiliations": sum(
                    row["finals_minutes_coverage"] == TeamSuccessCoverage.RELIABLE.value
                    for row in finals
                ),
                "methodology_version": TEAM_SUCCESS_METHODOLOGY_VERSION,
                "awards_methodology_version": AWARDS_METHODOLOGY_VERSION,
                "corpus_id": CORPUS_ID,
                "corpus_fingerprint": CORPUS_FINGERPRINT,
            }
        )
    return output


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else round(statistics.fmean(values), 12)


def _weighted_mean(values: Sequence[float], weights: Sequence[int]) -> float | None:
    denominator = sum(weights)
    if not values or denominator <= 0:
        return None
    return round(
        sum(value * weight for value, weight in zip(values, weights, strict=True)) / denominator, 12
    )


def stable_json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_finite_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        for key, value in row.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"non-finite value in {key}")
