# ADR-0038 — Promote tiered Defense V2 with limitations

Status: Accepted

Date: 2026-09-16

## Context

Defense V1 assigned 65% nominal weight to a team-season constant. STEP-0015A found zero
within-team variance in that channel, ICC 1.0, career correlation 0.866 with team suppression, and
89.9% between-team variance in the season composite. STEP-0015B's 30/30/40 individual-attribution
candidate improved attribution but could not be promoted because missing Presence was either
renormalized into weaker channels or predicted by a model with out-of-fold R² 0.0174.

Later work established factual historical recovery, grouped measurement linking, calibrated
intervals, tiered point eligibility, and uncertainty-aware Overall infrastructure. Universal point
coverage is therefore no longer a prerequisite for a usable Defense method.

## Decision

Promote `goatlab-v1-defense-v2-tiered` with limitations. The rich reference form is:

`10% Team Context + 38.5714% Role-Aware Actions + 51.4286% observed Presence`

The action-to-Presence ratio preserves Candidate B's 3:4 individual-channel balance after Team
Context is capped at 10%. Actions remain 40% rebound evidence, 30% steals, and 30% blocks, with
65% global and 35% broad-role interpretation where role metadata are reliable. This role treatment
interprets evidence and does not force equal ceilings.

Presence is a continuously reliability-weighted, opponent/context-adjusted, game-participation
contrast. It is observational, not RAPM or a causal estimate. Missing Presence is never predicted,
zero-filled, or silently reallocated. Instead, factual evidence forms are linked to the rich-form
scale using player-grouped cross-validation and receive split-conformal 80/90/95 intervals.

Season and career outputs use `OFFICIAL_DEFENSE_POINT`, `PROVISIONAL_DEFENSE_POINT`,
`DEFENSE_INTERVAL_ONLY`, and `DEFENSE_UNAVAILABLE`. An interval center is diagnostic and cannot be
consumed downstream as an official point. Full, missing-team-context, and adequately calibrated
partial-Presence patterns may support points. No-Presence and traditional-only career patterns
remain interval-only.

Career Defense remains the mean of season Defense measurements followed by a fixed
`BROAD_HIGH_RECALL` midrank ECDF. Season count itself adds no quality credit. Defense remains
Regular Season only; awards and richer modern metrics remain validation-only.

## Consequences

- Team Context has 10% nominal weight and 4.34% rich-form covariance share; it no longer dominates.
- Presence has 51.43% nominal weight and 90.29% effective variance share. This is disclosed as a
  major limitation and reflects individual-impact primacy plus action/Presence covariance, not a
  causal claim.
- No-Presence season forms have MAE 12.78 and rho 0.576 after linking, and traditional-only forms
  have MAE 13.32 and rho 0.516. They cannot receive ranking-grade points.
- Career partial-Presence validation passes (MAE 4.61, rho 0.9766); career no-team-context passes
  (MAE 3.19, rho 0.9889). Career no-Presence and traditional-only patterns fail and remain ranges.
- Defense V1 and Overall V1 remain immutable historical baselines. No new Top 100 is created.
- A future Overall promotion must preserve empirical Defense–Peak–Longevity error dependence;
  independent draws are prohibited.
