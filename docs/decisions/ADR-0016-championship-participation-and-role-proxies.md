# ADR-0016 — Player championship participation and factual role proxies

## Context

A player may represent multiple teams in one season, leave an eventual champion before the playoffs, appear in the playoffs but not the Finals, or receive an official NBA Champion event without a recorded Finals appearance. Candidate-scoped STEP-0009 awards also leave 2,963 players `NOT_QUERIED`. Collapsing these states into a ring or championship flag would erase evidence and assign subjective credit.

## Decision

Join team outcomes at player × team × season before career aggregation. Preserve four distinct observations: regular-season membership on the champion, playoff participation for the champion, Finals participation for the champion, and an official NBA Champion award event. The award-event field is NULL for `NOT_QUERIED`, never false. A Finals appearance requires an accepted player-game row in a validated Finals game.

Use only measurable opportunity proxies: team-game share and, where empirical minute coverage is `RELIABLE` with at least 99% positive observations, team-minute share. Missing or placeholder minutes produce NULL. Do not label roles and do not combine the proxies into credit, rings, Winning, or team-success scores.

## Alternatives considered

- Credit every regular-season member of the champion: rejected because traded and released players create false playoff/Finals participation.
- Define champions from PlayerAwards: rejected because acquisition was candidate-scoped and describes player events, not team outcomes.
- Treat missing award events as zero: rejected because `NOT_QUERIED` has no negative meaning.
- Infer subjective roles from minute share: rejected because measurement is not interpretation.

## Consequences

Traded-team outcomes cannot leak across team rows. Later methodologies may explicitly select a participation definition, but none is privileged here. Early historical minute proxies remain unavailable rather than zero. Official award discrepancies remain visible diagnostic evidence.

## Status

Accepted in STEP-0010.
