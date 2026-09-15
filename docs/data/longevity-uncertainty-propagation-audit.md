# Longevity uncertainty propagation audit

Methodology: `goatlab-v1-longevity-v2-uncertainty-research`

Verdict: **LONGEVITY_UNCERTAINTY_LIMITED**

The frozen Longevity architecture remains 35% P80 breadth, 40% capped P80-P90 area, and 25%
longest consecutive P80 run. P80 and P90 stay fixed at 80 and 90 on the STEP-0015H linked
full-portable scale. Every simulation draw calculates exact threshold classifications, capped
area, and longest run; season events are not assumed independent.

On 1,270 masked full-form careers, mixed careers have MAE 3.72 and bias 0.16, but Spearman is only
0.9388 and 90% coverage is conservatively high at 95.28%. Partial-Presence careers similarly
miss the rank gate at Spearman 0.9417. Traditional careers have MAE 6.10, Spearman 0.8773, and
18.27% of errors above ten points. Thus no non-full pattern meets every point-score gate, although
empirical intervals remain useful.

Actual research status counts are 1,976 `OFFICIAL_LONGEVITY_POINT`, 2,210
`LONGEVITY_INTERVAL_ONLY`, and 917 `LONGEVITY_UNAVAILABLE`; there are no provisional Longevity
points. Each scored row preserves expected P80 count, capped-area expectation, the full simulated
longest-run distribution, and nested 80/90/95 intervals. Active players use observed seasons only
through the frozen cutoff.
