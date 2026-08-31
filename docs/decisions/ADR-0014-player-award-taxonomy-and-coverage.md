# ADR-0014 — Evidence-based award taxonomy and source-gap policy

## Context

The representative `PlayerAwards` probe returned more categories than the initial Silver vocabulary, including recurring honors, team accomplishments, external honors, and later full-run strings. Season representation and structured team level also differ across event types. All-Star rows do not encode original selection, replacement, injury, and participation semantics separately; statistical titles are absent.

## Decision

Use `official-player-awards-canonical-v1`. Map exact empirically observed descriptions into `CANONICAL_CORE`, `CANONICAL_SECONDARY`, `MINOR_RECURRING`, `NON_PLAYER_COMPETITIVE`, or `UNKNOWN`. Preserve every raw field and description. Use `ALL_NBA_TEAM_NUMBER` for First/Second/Third levels. Parse only valid `YYYY-YY` NBA seasons; leave calendar-only labels with NULL `season_id` and `SEASON_MAPPING_UNKNOWN`. Mark All-Star coverage `PARTIAL`. Mark statistical titles `REQUIRES_SEPARATE_SOURCE`, with future derivation from GOATLAB-HIST-V1 preferred. No category carries value or weight.

## Alternatives considered

- Infer every category from description substrings: rejected as unstable and over-broad.
- Discard minor/external events: rejected because it destroys source evidence.
- Treat All-Star rows as complete selection history: rejected because the endpoint lacks selection/replacement semantics.
- Add another provider for missing titles: rejected as out of STEP-0009 scope.

## Consequences

All 33 observed descriptions are exhaustively registered and no event disappears. New descriptions remain `UNKNOWN` until reviewed. Silver can represent non-season calendar honors without guessing an NBA season. Later methodology may choose which factual categories to use, but must do so outside Silver.

## Status

Accepted in STEP-0009.
