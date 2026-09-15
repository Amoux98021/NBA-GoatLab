# ADR-0036: Promote uncertainty-aware Peak and freeze tiered Longevity policy

- Status: Accepted
- Date: 2026-09-15
- Related: ADR-0031, ADR-0034, ADR-0035, STEP-0015H through STEP-0015K

## Context

V1 Peak inherits material team-context contamination from its V1 SeasonQuality input. The
STEP-0015H measurement layer and STEP-0015I career simulations replace that input with factual,
tiered PlayerSeasonValue evidence while preserving the constitutional 70/30 Peak architecture.
Mixed and partial-Presence careers pass the declared aggregate point gates; traditional-only
careers do not.

The 35/40/25 Longevity architecture remains constitutionally coherent, but STEP-0015J found that
P80 uncertainty affects breadth, capped area, and run simultaneously. No non-full evidence pattern
passes every ranking-grade point gate. A central estimate can therefore be useful diagnostically
without being an official point score.

## Decision

1. Promote `goatlab-v1-peak-v2` with tiered output semantics. It uses U3 stratified player-block
   dependence, 2,500 deterministic draws, reselects the best contiguous three-season window and
   apex inside every draw, applies 70/30 weights, and uses a fixed `BROAD_HIGH_RECALL` ECDF.
2. Freeze `goatlab-v1-longevity-v2-tiered`: P80/P90 and 35/40/25 remain unchanged; non-full
   evidence receives an official point only after its evidence pattern passes the aggregate gates.
3. A reported interval is not a lower score. Confidence and uncertainty describe measurement,
   never player quality.
4. An interval midpoint or diagnostic central Longevity estimate is not an official point.
5. Overall may not drop an interval/unavailable required dimension, redistribute its weight, or
   treat a midpoint as exact. `goatlab-v1-overall-v1` remains frozen.
6. Active careers are evaluated only through the 2025-26 cutoff (`TO_DATE_NO_PROJECTION`).

## Consequences

- Peak V1 remains immutable for reproducibility; Peak V2 is its versioned successor.
- Peak statuses are official point, provisional point, interval only, or unavailable.
- Longevity's tiered policy is durable, but it creates no provisional points in this release.
- Players lacking three qualifying contiguous seasons are constitutionally ineligible for Peak,
  not victims of historical measurement failure.
- The next methodology problem is uncertainty-aware seven-dimension Overall aggregation; this ADR
  does not authorize a new Overall score or ranking.
