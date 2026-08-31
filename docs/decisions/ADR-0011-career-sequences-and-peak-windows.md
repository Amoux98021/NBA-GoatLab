# ADR-0011: Career sequences and peak-window completeness

## Context

Career summaries must distinguish sustained consecutive performance from a collection of isolated seasons. A player who appears in 1998 and 2000 did not produce a contiguous two-season run. Peak calculations also need a transparent relationship to STEP-0007 qualification, historical feature availability, and games opportunity.

## Decision

Create career methodology version career-trajectory-peak-longevity-v1. Build a separate sequence for each player and season type, ordered by canonical season start year. Materialize every season from first through last appearance; a non-appearance is an explicit GAP_NO_APPEARANCE row. Regular Season and Playoffs never mix.

A valid N-year peak requires N observed, STEP-0007-qualified, feature-available seasons whose season IDs are exactly consecutive. Missing, unqualified, or feature-unavailable seasons invalidate that candidate window. Retain separate 1-, 3-, and 5-year QUALITY and AVAILABILITY_ADJUSTED peaks.

QUALITY uses the arithmetic mean of normalized values. AVAILABILITY_ADJUSTED first shrinks each season toward the normalization-specific league baseline using games played divided by team opportunity: zero for standard/robust z, 0.5 for percentile, and 100 for relative index. It then averages the adjusted values. Values are never imputed for a missing season.

Separately retain the best three and five qualified seasons regardless of contiguity and label them NON_CONTIGUOUS. Never call those records three-year or five-year peaks.

## Alternatives considered

- Select the best N seasons and call them an N-year peak.
- Ignore missed seasons between observed records.
- Permit partially covered windows and average the available seasons.
- Choose either quality or availability-adjusted peak as the official definition.
- Multiply every normalized method directly by games opportunity without a neutral baseline.

## Consequences

Career Gold is intentionally sparse where history or qualification does not support a complete window. Players with interrupted careers can still have non-contiguous best-season sets while lacking a valid contiguous window. Quality and availability-adjusted selections differ materially and remain separate evidence for later preference methodologies. No peak composite or player ordering is created.

## Status

Accepted — 2026-08-31.
