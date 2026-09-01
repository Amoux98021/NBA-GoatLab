# ADR-0015 — Championship derivation and postseason-format qualification

## Context

GOATLAB-HIST-V1 has complete playoff player-game evidence but its legacy canonical game table omits 23 whole season/type partitions. NBA postseason structures also changed materially: opponent-pair series exist in most seasons, while 1953-54 included a round-robin stage and cannot be represented as a simple series bracket. A uniform modern round model would manufacture history.

## Decision

Use frozen canonical game evidence when a partition exists and reconstruct only the missing game-result partitions from the already frozen, fingerprinted `PlayerGameLogs` Bronze cache. Validate the 2022-23 overlap before accepting this fallback. Infer champion and runner-up from the unique chronologically final playoff game, identify every Finals game by the validated champion/runner-up team-ID pairing, and reconcile champion, runner-up, and series result against the official NBA history record for all 80 seasons.

Classify 1983-84 onward as `STANDARD_SERIES_BRACKET`; classify earlier seasons as `NONSTANDARD_SERIES_FORMAT`, except 1953-54 as `ROUND_ROBIN_OR_MIXED`. Opponent-pair series counts are permitted in 79 seasons but blocked in 1953-54. Modern round labels are unavailable before 1983-84. Point-differential context is withheld for a whole season when fallback score evidence contradicts recorded W/L.

## Alternatives considered

- Require the incomplete legacy `game` table alone: rejected because 23 frozen corpus partitions would disappear.
- Treat the final playoff game as sufficient without validation: rejected because historical formats require empirical confirmation.
- Force all seasons into a modern four-round bracket: rejected as historically false.
- Overwrite derived results from the official list: rejected because official history is validation evidence, not a silent replacement for corpus facts.
- Repair contradictory team-point totals: rejected because evidence does not identify a defensible repair.

## Consequences

Every season has deterministic team results, champion, runner-up, and Finals-game evidence. Championship and series-result reconciliation is 80/80. Series counts remain NULL for 1953-54 and modern round labels are not fabricated. Regular-season W/L remains universal, while scoring context is explicitly partial in four seasons.

## Status

Accepted in STEP-0010.
