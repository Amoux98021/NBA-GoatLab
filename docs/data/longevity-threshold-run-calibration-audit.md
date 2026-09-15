# Longevity threshold/run calibration audit

Methodology: `goatlab-v1-longevity-threshold-run-calibration-audit-v1`

Research output: `goatlab-v1-longevity-v2-uncertainty-research-2`

Result: `PASS + LONGEVITY_AGGREGATION_LIMITED`

STEP-0015J preserves P80/P90, 35/40/25, `U3_STRATIFIED_BLOCK`, 2,500 draws, and the
fixed-reference ECDF. It selects the median of final transformed draws; alternative expected-value
summaries are materially biased by nonlinear threshold and ECDF operations.

Component forensics show no single failure source. Longest run has the weakest isolated rank
correlation, but capped-area error causes the most pairwise reversals, and P80 uncertainty affects
all three components simultaneously. The 827 validation `RUN_BRIDGE_EVENT`s change the run by
2.04 seasons and Longevity by 8.00 points on average when the connector crosses P80.

Mixed and partial-Presence central estimates retain MAE below four points but rank correlations of
0.9388 and 0.9417 remain below the 0.95 point gate. Cross-fitted aggregate conformal intervals are
well calibrated, so these regimes remain interval-only. No official methodology or additional
provisional point is created.

Machine-readable evidence:

- `longevity-component-error.json`
- `longevity-threshold-forensics.json`
- `longevity-run-instability.json`
- `longevity-central-estimator-comparison.json`
- `longevity-ecdf-order-audit.json`
- `longevity-career-length-audit.json`
- `longevity-interval-calibration.json`
- `longevity-pairwise-reversal.json`
- `longevity-aggregate-calibration.json`
- `longevity-status-output.json`
- `longevity-case-studies.json`
- `longevity-calibration-verdict.json`

Generated Parquet remains ignored under
`data/gold/longevity_threshold_run_calibration_audit/`.

