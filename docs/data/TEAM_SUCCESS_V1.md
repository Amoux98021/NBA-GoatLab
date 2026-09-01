# Team Success and Postseason Facts V1

## Purpose

`team-success-postseason-v1` derives factual team outcomes and player participation from frozen `GOATLAB-HIST-V1`. It creates no championship value, role label, rings score, Winning score, or GOAT ranking.

## Inputs and provenance

- Corpus: `GOATLAB-HIST-V1`
- Corpus fingerprint: `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`
- Awards fingerprint: `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258`
- Game evidence: canonical legacy `game` partitions where present; frozen NBA API `PlayerGameLogs` Bronze evidence for 23 missing legacy partitions and seasons after 2022-23
- Player evidence: frozen canonical `player_game_stats`
- Official validation: NBA championship history, plus specific official season reviews for format qualification

No network access is required. The official history fixture is small, source-attributed validation evidence and is not allowed to overwrite derived facts.

## Game evidence qualification

Legacy game partitions are preferred when complete. The frozen API fallback is accepted only at complete season/type partition grain. In the 2022-23 overlap, all 1,230 Regular Season and 84 Playoff game IDs, dates, team IDs, scores, and winners matched exactly.

Some historical API rows contain contradictory team point sums even though W/L is consistent. Regular W/L therefore uses explicit game outcome evidence. Point totals and point-differential context are withheld for all teams in 1960-61, 1970-71, 1975-76, and 1976-77. No score is repaired or imputed.

## Team-season facts

`team_season_results` contains one row per canonical team × season. Regular games, wins, losses, and win percentage come from isolated Regular Season game evidence. Playoff facts come only from Playoff games. The runner-up `finalist` flag is distinct from `champion`; either flag plus its opponent establishes a Finals participant.

Within-season strength context includes competition ranks, midrank percentiles, population z-scores, wins relative to the league mean, and point-differential equivalents where qualified. These are descriptive primitives, not a composite.

## Championship and Finals method

For each isolated playoff season, the unique chronologically final game identifies its winner as champion and its other participant as runner-up. Every playoff game between those two team IDs is a Finals game. This hypothesis was tested and reconciled against the official NBA champion, runner-up, and series result in all 80 seasons.

The official reference is `https://www.nba.com/news/history-nba-champions`, retrieved into a source-attributed fixture at `2026-09-01T12:00:00Z`. Official season reviews qualify 1953-54 as round-robin/mixed and 1983-84 as the start of the standardized 16-team, four-series title path used by this V1 classification.

## Postseason formats

- `STANDARD_SERIES_BRACKET`: 1983-84 through 2025-26; opponent-pair series and modern round labels allowed.
- `NONSTANDARD_SERIES_FORMAT`: 36 seasons before 1983-84; opponent-pair series facts allowed, modern round labels blocked.
- `ROUND_ROBIN_OR_MIXED`: 1953-54; pair-series and round inference blocked.

Opponent-pair grouping provides series played/won/lost only when the format registry allows it. `rounds_advanced` is deliberately absent.

## Player participation semantics

`player_team_season_participation` is keyed by player × team × season and retains traded-player rows. It distinguishes:

- `regular_season_member_of_champion_team`
- `played_playoffs_for_champion_team`
- `played_finals_for_champion_team`
- `official_nba_champion_award_event`

The first three derive from accepted player-game rows. The fourth comes from STEP-0009 and remains NULL for `NOT_QUERIED`. None is renamed a ring or used as credit.

Game share is player distinct games divided by the team's games for that phase. Minute share is available only when the existing empirical metric matrix classifies minutes `RELIABLE` and at least 99% of observations are positive. This prevents historical placeholder zeros from becoming role evidence.

## Gold career context

Gold outputs retain playoff/Finals seasons and games, champion participation counts by each definition, official champion award count where queried, mean team win percentile, Regular Season game-weighted team win percentile, and seasons on teams at or above the 90th percentile. These factual features remain separate.

## Findings and limits

- 1,723 team-seasons, 68,529 Regular Season games, and 4,606 Playoff games were processed.
- 461 Finals games were identified.
- 28,839 player-team-season rows and 5,103 player-career context rows were built.
- Series inference is available in 79 seasons and format-blocked in 1953-54.
- Regular minute shares are eligible in 44 of 80 partitions; playoff and Finals minute shares in 56 of 80 playoff partitions.
- Candidate-scoped award comparison found 845 official champion player-seasons: 808 have observed champion Finals participation, 37 do not, and none lack all player-game participation. Two queried champion Finals participants have no corresponding award event. These are factual differences, not pipeline repairs.
- Neutral-site evidence may not establish which participating team was formally home; team outcomes are unaffected and venue assignment is explicitly labeled.

## Deterministic outputs

The build writes 304 ignored Parquet partitions across factual Silver and descriptive Gold. All partition hashes roll into output fingerprint `707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333`. A second offline execution must match every partition hash.
