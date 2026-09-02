# ADR-0024: Structural candidate pruning and Era Dominance treatment

## Context

STEP-0012 left 32 candidates validated for experiment, four rejected, and two modern-only candidates deferred. Correlation alone cannot decide conceptual identity, but retaining near-identical definitions would create hidden multiple voting in later ranking work.

## Decision

Pruning uses predeclared contextual evidence: prior status, broad-population coverage, shared or derivative lineage, within/cross-family correlation, multiple R², residual variance, PCA/factor loadings, and interpretability of a simpler alternative. Allowed outcomes are `RETAIN_FOR_FINALIZATION`, `REDUNDANT`, `REJECTED`, `DEFER_MODERN_ONLY`, and `INSUFFICIENT_ALL_ERA_EVIDENCE`. No outcome is `FINAL`.

Era Dominance is retained as `USE_AS_DIAGNOSTIC_ONLY`, not an independent additive dimension. The underlying player-season statistics are already era-normalized, and Era candidates show very high predictability from Peak/Longevity/Offense/Defense candidates. This is a structural statement, not a judgment that era context is unimportant.

## Alternatives considered

- Retaining all candidates was rejected because it would preserve demonstrated duplicate votes.
- A universal correlation cutoff was rejected because empirical overlap without lineage does not prove conceptual duplication.
- Removing era normalization was rejected; the diagnostic conclusion concerns a separate Era vote, not the upstream normalization method.
- Declaring a final formula was rejected as outside STEP-0013.

## Consequences

The experimental shortlist has 18 candidates across seven conceptual families. Defense remains coverage-qualified and its modern enrichment remains separate. STEP-0014 must perform finalization sensitivity without treating the shortlist as an established public score.

## Status

Accepted as a STEP-0013 recommendation; final dimension methodology remains open.
