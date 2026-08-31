# STEP-0008 — Career trajectory, peak, prime, and longevity primitives

## 1. Objective

Transform frozen normalized player-season facts into descriptive, metric-specific career sequences, peak windows, prime runs, cumulative dominance, longevity primitives, and broad future award-acquisition candidate universes without producing a GOAT score or ranking.

## 2. Motivation

STEP-0007 made season performance comparable within historical context. Later methodologies need transparent ways to describe single-season quality, sustained contiguous performance, collections of elite seasons, availability, and career length without silently deciding how those ideas should be weighted.

## 3. Inputs

- Clean main after STEP-0007 (803ff61).
- GOATLAB-HIST-V1 and corpus fingerprint 283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c.
- era-normalized-player-season-v1 and fingerprint a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852.
- All 480 verified STEP-0007 Gold partitions.
- Audited nbadb v238 player/common-player identity tables at fingerprint 65b6412234d2d8817678d04f7cd2548aec82fec02b6c5b86679cade7572c21c7.
- Existing qualification, feature eligibility, games/opportunity, and NULL semantics.

## 4. Work performed

- Accepted ADR-0011 for gap-aware sequences, complete contiguous windows, and separate quality/availability variants.
- Accepted ADR-0012 for active/completed/indeterminate status, non-imputed age, and broad award-candidate policy.
- Implemented deterministic career sequence, window, non-contiguous best-season, prime-run, cumulative dominance, age, candidate-universe, and hashing primitives.
- Materialized career summaries for all 5,103 players and explicit gap rows between first and last appearance.
- Calculated metric/normalization career distributions and non-contiguous top-three/top-five sets.
- Calculated 1-, 3-, and 5-year QUALITY and AVAILABILITY_ADJUSTED peaks with completeness metadata.
- Calculated 80th/90th/95th/99th-percentile counts and consecutive runs.
- Calculated positive-z and percentile-area cumulative primitives with unweighted and opportunity-weighted variants.
- Repeated relevant playoff analyses separately with games/sample metadata.
- Evaluated 12 award-acquisition universe proposals while preserving every player.
- Produced 14 diagnostic career case studies without an overall ordering.
- Rebuilt all career Gold and verified every output hash.

## 5. Files created or changed

- src/goatlab/features/career_trajectory.py
- pipelines/features/build_career_trajectory_v1.py
- tests/test_career_trajectory.py
- docs/decisions/ADR-0011-career-sequences-and-peak-windows.md
- docs/decisions/ADR-0012-career-status-age-and-award-candidate-policy.md
- docs/data/CAREER_TRAJECTORY_V1.md
- docs/data/career-feature-definitions.yaml
- docs/data/career-feature-summary.json
- docs/data/career-gold-manifest.json
- docs/data/peak-window-sensitivity.json
- docs/data/longevity-sensitivity.json
- docs/data/career-case-studies.json
- docs/data/award-candidate-universe-analysis.json
- docs/METHODOLOGY.md
- docs/DATA_DICTIONARY.md
- docs/EXPERIMENTS.md
- docs/PROJECT_LOG.md
- This step record.

Generated Gold comprises 160 ignored Parquet partitions under data/gold.

## 6. Career participation and status observations

- All 5,103 players received deterministic career summaries.
- Regular Season appearances average 5.04 with median three; qualified seasons average 4.40 with median three.
- Regular Season games average 272.34 with median 130 and maximum 1,622.
- Playoff appearances average 2.30 seasons with median one; playoff games average 18.02 with median three and maximum 302.
- Career status is 582 ACTIVE_TO_CUTOFF, 4,250 SOURCE_CONFIRMED_COMPLETE, and 271 INDETERMINATE.
- Audited birth dates support age features for 3,612 players; 1,491 remain unavailable.

## 7. Peak, prime, and longevity observations

- 519,360 metric-normalization career summaries include 347,420 AVAILABLE and 171,940 explicitly unavailable combinations.
- Valid peak records per variant are 347,420 one-year, 177,472 three-year, and 110,971 five-year.
- Of 3,116,160 total peak records, 812,794 fail contiguous completeness and 1,031,640 lack any qualified feature value; neither condition produces a synthetic value.
- Availability adjustment changed the selected PPG window in 18.39% of eligible one-year, 18.12% of three-year, and 16.26% of five-year cases.
- Across any eligible metric, 3,133 Regular Season players have at least one 80th-percentile season, 2,596 have a 90th, 1,930 a 95th, and 815 a 99th. Playoff counts are 2,382, 2,092, 1,506, and 535.
- Prime runs retain threshold, span, mean/minimum percentile, mean z, and games. Missed and below-threshold seasons break runs.
- Cumulative primitives remain separate: positive-z sum, opportunity-weighted positive-z, and area above 0.50/0.80/0.90 percentile baselines with weighted variants.

## 8. Candidate-universe analysis

Participation proposals range from 2,574 players at three qualified seasons to 867 at ten. Core-metric elite proposals contain 1,491 players at any 90th-percentile season and 984 at any 95th. The recommended broad union—at least five qualified seasons OR one core 90th-percentile season—contains 2,140 players. It is an acquisition planning flag only; all 5,103 remain in the corpus.

## 9. Decisions made

- A missing NBA season breaks a contiguous window.
- Require every expected season to be observed, qualified, and feature-available.
- Preserve QUALITY and AVAILABILITY_ADJUSTED peak variants instead of choosing one.
- Shrink availability-adjusted values toward the normalization-specific league baseline.
- Label top-three/top-five best seasons NON_CONTIGUOUS.
- Keep multiple elite thresholds and cumulative baselines rather than selecting an official prime or longevity definition.
- Treat Regular Season and Playoffs independently.
- Do not impute age or infer retirement from cutoff absence.
- Prefer false positives for player-scoped awards acquisition and never convert candidate flags into permanent exclusions.

## 10. Validation/tests executed

- Verified all 480 normalization partitions and the audited identity SQLite fingerprint.
- Tested career ordering, gap preservation, 1/3/5-year completeness, quality/availability divergence, non-contiguous sets, thresholds, prime runs, cumulative formulas, age NULLs, candidate rules, provenance, and deterministic hashing.
- Observed zero duplicate career-feature keys, duplicate peak keys, invalid available windows, non-finite values, case identity failures, or network requests.
- Validated all 160 output partition hashes, row/column counts, JSON/YAML reports, Gold ignore behavior, and corpus/normalization provenance.
- Rebuilt the full outputs and reproduced fingerprint 5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b exactly.
- Complete offline Pytest, Ruff, strict Mypy, artifact validation, and whitespace validation passed.

## 11. Result

The build produced 5,103 career summaries, 42,886 trajectory rows, 519,360 metric-career summaries, 3,116,160 peak-window records, and 519,360 prime-run records. The 160 partitions occupy 68,583,568 bytes. The certification run completed in 153.97 seconds without network access.

## 12. Known limitations

- Historical feature sparsity remains metric-specific; early scoring can be available while defense or efficiency is not.
- A qualification gate controls inclusion but is not a full uncertainty model.
- Playoff sample sizes remain heterogeneous and are not converted to a final impact weight.
- Availability shrinkage is one descriptive policy, not a declared definition of peak.
- Legacy career status is stale for some players; 271 careers remain indeterminate.
- Birth-date coverage is 70.78%; age features remain NULL otherwise.
- Candidate universes use statistical evidence only and can miss award-relevant role players; the broad union is intentionally over-inclusive.
- No awards, championships, team success, composite Peak/Longevity, dimension score, ranking, or ML is implemented.

## 13. Explicit decision: PASS

**PASS.** Every player has deterministic career representation; season types remain separate; valid 1/3/5-year windows obey gap and coverage rules; quality and availability variants remain distinct; multiple elite thresholds, prime runs, longevity, and cumulative primitives exist; historical NULLs are preserved; active careers are unprojected; provenance is complete; all candidate proposals retain the master corpus; and the second offline build reproduced all Gold hashes without optimizing against GOAT ordering.

## 14. Recommended STEP-0009

Perform bounded official awards/accolades source feasibility and canonical event ingestion for the broad 2,140-player acquisition universe, with full historical coverage audit and identity reconciliation. Do not assign award values, championship weights, composite dimensions, or rankings.
