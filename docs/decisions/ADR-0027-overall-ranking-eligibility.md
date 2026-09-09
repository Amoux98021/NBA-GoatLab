# ADR-0027: Overall ranking eligibility and award-query upper bounds

## Context

The frozen dimension layer contains 1,882 complete seven-score profiles. Accolades are known for 2,140 players, while 2,963 remain `NOT_QUERIED`. Unknown award evidence cannot be treated as zero or silently bypassed by redistributing weights.

## Decision

An official Overall score requires all seven dimension scores. Incomplete profiles are `UNRANKED_INCOMPLETE_REQUIRED_DIMENSION` and retain a NULL Overall score.

Before publication, every six-dimension-complete `NOT_QUERIED` player is screened with Accolades set to 100 against the Top-100 cutoff under all four candidate methods and 10,000 fixed-seed admissible weight vectors. A player is `MUST_QUERY_FOR_RANKING_ELIGIBILITY` if any upper bound crosses a corresponding cutoff, `REVIEW_REQUIRED` if within five points, and otherwise `SAFE_TO_EXCLUDE_FROM_V1_QUERY`. Players also missing a non-Accolades dimension remain `REVIEW_REQUIRED`; award acquisition alone cannot make them rankable.

## Alternatives considered

- Query all remaining players: unnecessary after the deterministic high-recall bound and operationally wasteful.
- Treat `NOT_QUERIED` as zero: violates source semantics and the Constitution.
- Renormalize six known dimensions: violates the binding publication rule.
- Require a specific award to qualify: rejected because genuinely low Accolades may be overcome elsewhere.

## Consequences

No additional award query was required in STEP-0015. The 2,963 unknown statuses remain unknown. Exactly 1,882 players are officially rankable, and no six-complete unknown-award player can reach the Top 100 in the audited region.

## Status

Accepted for `goatlab-v1-overall-v1`.

