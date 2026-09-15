# Longevity V2 tiered policy

Policy version: `goatlab-v1-longevity-v2-tiered`

Verdict: **FREEZE_LONGEVITY_TIERED_POLICY**

The conceptual methodology remains:

- 35% elite-season breadth at or above P80;
- 40% capped quality area from P80 through P90;
- 25% longest consecutive P80 run;
- common thresholds P80 = 80 and P90 = 90.

STEP-0015J found that longest run is the weakest isolated component and capped area produces the
most pairwise reversals, but neither is the sole cause. P80 uncertainty simultaneously changes all
three components. Nearby thresholds and 20%–30% run-weight sensitivity do not repair the non-full
ranking failure. The philosophy is therefore retained while point precision becomes evidence
dependent.

## Status contract

- `OFFICIAL_LONGEVITY_POINT`: ranking-grade point supported by reference-grade evidence.
- `PROVISIONAL_LONGEVITY_POINT`: only an evidence pattern passing every aggregate point gate may
  use this state; none currently qualifies.
- `LONGEVITY_INTERVAL_ONLY`: a calibrated range exists, but the central diagnostic estimate is not
  an official ranking point.
- `LONGEVITY_UNAVAILABLE`: career/evidence support is insufficient for a useful interval.

Current counts are 1,976 official, zero provisional, 2,210 interval-only, and 917 unavailable.
Every usable record retains nested 80/90/95 intervals, expected breadth, capped-area distribution,
longest-run distribution, run-bridge diagnostics, confidence, and reason codes.

Downstream code must not substitute an interval midpoint, drop Longevity, redistribute its 14%
Overall weight, or apply a confidence penalty. Historical uncertainty widens the result; it does
not reduce player quality.
