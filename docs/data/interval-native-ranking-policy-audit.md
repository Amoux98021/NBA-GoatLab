# Interval-Native Ranking Policy Audit

Methodology: `goatlab-v1-ranking-policy-v2-uncertainty-research`

Result: `PASS + VALID_PROBABILISTIC_RANKING_ONLY`

Overall decision: `OVERALL_V2_STILL_NOT_READY`

## What is supported

GOATLab can compare all 1,882 players with calibrated Overall distributions using rank bands,
Top-N probabilities, and pairwise probabilities. This includes 1,286 interval-native players;
their uncertainty widens their plausible placement but never lowers their quality score.

Rank-band 90% coverage is 90.14%–92.23% across the six validation forms. Top-100 Brier scores are
0.0021–0.0233. Pairwise directional Brier scores are 0.0080–0.0503. These outputs are conditional
on the frozen STEP-0015N measurement architecture.

## What is not supported

No central Overall, median-rank, expected-rank, or expected-wins ordering passes every predeclared
Spearman and Top-10/25/50/100 overlap gate. Weak historical forms especially fail exact Top-N
membership preservation. GOATLab therefore may not describe a deterministic V2 ordering as the
official permanent Top 100.

## Display contract

A probabilistic research leaderboard may show a clearly labeled median-rank diagnostic, 80% and
90% rank bands, Top-10/25/50/100 membership probabilities, Overall interval, and evidence status.
An interval-native status is not a lower score. Close ranks should be described as indeterminate
when pairwise probability is 35%–65%.

Unavailable players remain unranked with an insufficient-evidence explanation. Active players use
completed evidence through 2025-26 with no future projection.

## Publication boundary

No V2 Top 100 is generated. Overall V2 remains a research candidate and Overall V1 remains the
immutable published baseline. The unresolved choice is whether the product accepts a
probabilistic-first leaderboard or continues to require a validated exact Top 100.

Full evidence and detailed metrics are in the STEP-0015O record and machine-readable JSON reports.
