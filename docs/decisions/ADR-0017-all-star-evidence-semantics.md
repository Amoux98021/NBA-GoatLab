# ADR-0017 — All-Star roster, participation, and award-event semantics

## Context

`PlayerAwards` is candidate-scoped and its 1,837 All-Star events do not prove game participation. `PlayerGameLogs` supplies league-wide game participation, while official `BoxScoreTraditionalV3` responses list the players attached to each event game. Modern 2025 and 2026 formats contain multiple games and, in 2025, Rising Stars participants whose event participation is not necessarily an NBA All-Star selection. Historical box scores do not consistently identify original selection, replacement, or DNP reasons.

## Decision

Keep three independent signals: `PLAYERAWARDS_EVENT`, official event-game `ROSTER_LISTED`, and `GAME_PARTICIPANT`. Aggregate them at player × season while retaining the contributing game IDs. Call box-score evidence `OFFICIAL_EVENT_GAME_ROSTER`, not universally `ORIGINAL_SELECTION`. A rostered player without a PlayerGameLogs row is `DNP_ROSTERED`; a candidate-scoped awards absence is false only after a successful PlayerAwards request and remains NULL for `NOT_QUERIED` players. Pre-1950-51 is `NOT_APPLICABLE`; 1998-99 is `NO_GAME_HELD`.

## Alternatives considered

- Treat PlayerAwards as complete selections: rejected because the source is candidate-scoped and has unmatched events.
- Treat game participation as selection: rejected because DNP roster members disappear and the 2025 event includes Rising Stars participants.
- Scrape a third-party roster history: rejected because official structured event evidence is available and finer selection semantics are not consistently supported.
- Infer replacement status from names or absence: rejected as unsupported.

## Consequences

Career outputs use explicitly named roster-season, game-participation, and PlayerAwards-event counts. They do not expose one ambiguous `all_star_count`. Original/replacement semantics remain unavailable where official evidence does not say. Modern format changes remain observable rather than forced into East/West assumptions.

## Status

Accepted in STEP-0011.
