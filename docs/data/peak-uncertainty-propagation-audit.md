# Peak uncertainty propagation audit

Methodology: `goatlab-v1-peak-v2-uncertainty-research`

Verdict: **PEAK_UNCERTAINTY_LIMITED**

The frozen Peak architecture remains 70% best complete contiguous three-season value and 30%
single-season apex. The audit draws plausible PlayerSeasonValue seasons jointly, then reselects
both maxima in every draw. It never fixes a window from central estimates.

The validation population contains 1,270 careers with at least five full-portable seasons and a
complete three-season window. Mixed provisional/interval careers pass the point gates: MAE 3.93,
Spearman 0.9842, bias 0.07, 90% coverage 90.79%, and 5.91% of errors above ten points. Partial
Presence late careers also pass at MAE 3.10 and Spearman 0.9891. Traditional-only careers do not:
MAE is 6.66 and 25.20% exceed ten points. No-Presence careers narrowly miss because 90% coverage
is conservatively high at 93.39%.

Simulation-supported window selection modestly improves identification over the naive maximum:
79.13% versus 78.58% for mixed careers and 70.39% versus 69.21% for historical-transition
careers. It also reduces the traditional-career central bias from a naive -2.20 to -0.27 Peak
points. Winner selection remains consequential: only 1,994 of 2,456 real scored players have a
`STABLE_WINDOW`; 385 have competing windows and 77 have uncertain windows.

Actual research status counts are 974 `OFFICIAL_PEAK_POINT`, 1,411
`PROVISIONAL_PEAK_POINT`, 71 `PEAK_INTERVAL_ONLY`, and 2,647 `PEAK_UNAVAILABLE`. These are
research statuses and do not promote Peak V2.
