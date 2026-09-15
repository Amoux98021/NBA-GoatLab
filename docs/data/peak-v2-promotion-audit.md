# Peak V2 promotion audit

Methodology: `goatlab-v1-peak-v2`

Verdict: **PROMOTE_PEAK_V2_WITH_LIMITATIONS**

Peak V2 preserves the constitutional formula:

`70% best contiguous three-year PlayerSeasonValue + 30% single-season apex`

It consumes the frozen tiered season-measurement contract, preserves within-career error through
`U3_STRATIFIED_BLOCK`, runs 2,500 deterministic simulations, reselects the best window and apex in
every draw, and maps draws through one fixed `BROAD_HIGH_RECALL` ECDF. Uncertainty and confidence
never multiply or reduce quality. Active careers use completed seasons only through 2025-26.

## Promotion validation

| Evidence pattern | Bias | MAE | Spearman | 90% coverage | Decision |
|---|---:|---:|---:|---:|---|
| Full/reference | -0.00 | 0.38 | 0.9999 | 100.00% | official point |
| Mixed | +0.07 | 3.93 | 0.9842 | 90.79% | point gate passes |
| Partial Presence | +0.54 | 3.10 | 0.9891 | 91.73% | point gate passes |
| No Presence | +0.26 | 4.40 | 0.9806 | 93.39% | interval gate fails |
| Traditional only | -0.27 | 6.66 | 0.9548 | 91.34% | point gate fails |
| Early transition | +0.23 | 5.24 | 0.9720 | 92.52% | point gate fails |

The full/reference interval is conservative, but its point and ordering behavior are excellent.
Weak traditional/no-Presence patterns remain interval-native. This is the stated limitation, not a
reason to force point coverage.

## Status and coverage

- 974 `OFFICIAL_PEAK_POINT`
- 1,411 `PROVISIONAL_PEAK_POINT`
- 71 `PEAK_INTERVAL_ONLY`
- 2,647 `PEAK_UNAVAILABLE`

The unavailable rows are not measurement failures: 2,529 players have fewer than three qualifying
seasons and 118 have no complete qualifying three-calendar-season window. No Peak row is classified
as unavailable solely because the measurement layer lacks three usable seasons.

Historical players are not assigned lower quality because evidence is sparse. When aggregate
calibration cannot support a ranking-grade point, GOATLab reports a range. A range is not a lower
score, and confidence is not player quality.
