# ADR-0006: Direct NBA API player facts

## Context

The audited Kaggle `wyattowalsh/basketball` version 238 artifact is a legacy physical snapshot. It provides useful identities, games, teams, reference data, and play-by-play through 2022-23, but it has no player game box scores, player-season aggregates, advanced player statistics, or awards. Current nbadb documentation describes a richer v4 star warehouse than the acquired artifact. Rebuilding that complete warehouse would be substantially broader than GOAT Lab's required player-fact acquisition.

## Decision

Use a hybrid acquisition strategy:

1. Retain the audited Kaggle/nbadb legacy snapshot for historical identities, games, teams where reliable, and existing reference facts.
2. Use official NBA Stats through `nba_api` for missing bulk player-game facts, player-season facts where exposed, advanced player-season facts where exposed, and seasons later than 2022-23.
3. Treat the modern nbadb star warehouse as optional future enrichment, not a blocking dependency.

Both sources enter source-faithful Bronze storage and map through project-owned Silver contracts. `nba_player_id` and NBA `GAME_ID` are business keys; names are diagnostic only. Source conflicts are quarantined and source precedence is not changed implicitly.

## Alternatives considered

- Run an unrestricted full `nbadb init` reconstruction.
- Reconstruct player statistics from team totals or play-by-play.
- Scrape Basketball Reference or acquire an unrelated Kaggle player-stat dataset.
- Block all work until a modern nbadb warehouse artifact becomes available.

## Consequences

The required historical player-game path no longer depends on the mismatched Kaggle publication, and current seasons can use the same official interface. Acquisition must tolerate NBA Stats rate limits and operational changes through bounded retry, pacing, caching, resumability, and provenance. Historical metric coverage remains uneven even when rows exist; canonical transforms must preserve NULL and coverage evidence. Player-season Base/Totals is empirically absent before 1996-97 and must be derived from official game facts where reliable. Awards remain unresolved and out of scope for this decision.

## Status

Accepted — 2026-08-20.
