# ADR-0013 — Candidate-scoped official award acquisition semantics

## Context

Official NBA Stats `PlayerAwards` is player-scoped. STEP-0008 defined a deliberately broad 2,140-player acquisition universe, but GOATLAB-HIST-V1 retains 5,103 master identities. Treating the 2,963 unqueried players as having zero awards would manufacture facts and turn an acquisition optimization into permanent eligibility.

## Decision

Query only the STEP-0008 `union_q5_or_p90_recommended` universe in STEP-0009. Retain one acquisition state for every master player. `SUCCESS_EMPTY` means a successful official response with no rows; `NOT_QUERIED` means no claim about awards. Gold count fields are zero only for successfully queried players and NULL for non-candidates. Official numeric `PLAYER_ID` remains the business key. Checkpoint every player independently and permit later append-only acquisition for any non-candidate.

## Alternatives considered

- Query all 5,103 players now: complete but adds 2,963 requests outside the approved optimization.
- Materialize zero for non-candidates: rejected because source absence is not observed absence.
- Remove non-candidates from Gold: rejected because it obscures the master universe.

## Consequences

The source run is bounded to 2,140 requests and all 5,103 players remain visible. Candidate-scoped counts cannot be presented as complete league-wide award inventories for types whose winners may fall outside the candidate set. Future targeted acquisition can resolve any `NOT_QUERIED` player without changing canonical identity.

## Status

Accepted in STEP-0009.
