# STEP-0007 — League context and era-normalized player-season features

## 1. Objective

Create deterministic, coverage-aware Gold league context and primitive era-normalized player-season features from frozen GOATLAB-HIST-V1, without composite GOAT dimensions, rankings, awards values, career scoring, or machine learning.

## 2. Motivation

Raw statistics depend on season environment, opportunity, schedule length, and historical stat availability. STEP-0006 supplied stable facts and empirical coverage; STEP-0007 translates eligible facts into transparent within-season comparisons while refusing fabricated cross-era uniformity.

## 3. Inputs

- Clean main after STEP-0006 (678e66b).
- Frozen GOATLAB-HIST-V1, 1946-47 through 2025-26, Regular Season and Playoffs.
- Silver fingerprint 283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c and all 380 partition hashes.
- Canonical TOTAL player-season, player-game, advanced TOTAL, metric-coverage, and quality/quarantine artifacts.
- ADR-0003 missingness, ADR-0007 empirical qualification, and ADR-0008 corpus immutability.

## 4. Work performed

- Accepted ADR-0009 for season-length-scaled comparison populations and ADR-0010 for normalization/rate availability.
- Implemented reusable qualification, distribution, z-score, robust z-score, percentile, ratio, efficiency, and rate primitives.
- Evaluated seven qualification candidates over all applicable partitions.
- Built 160 league contexts from TOTAL rows, accepted games, and eligible official advanced facts.
- Produced 16 feature definitions for every one of 37,472 TOTAL player-seasons in generic long and curated wide representations.
- Materialized 10,240 eligibility records spanning season × type × feature × normalization method.
- Added explicit minute-positive and official-possession gates after empirical inspection exposed placeholder zeros.
- Validated ten representative seasons and seven famous player-season diagnostics without using player ordering as a target.
- Rebuilt all Gold outputs from frozen Silver and verified identical partition hashes.

## 5. Files created or changed

- src/goatlab/features/era_normalization.py
- pipelines/features/build_era_normalization_v1.py
- tests/test_era_normalization.py
- docs/decisions/ADR-0009-player-season-comparison-population.md
- docs/decisions/ADR-0010-coverage-aware-era-normalization.md
- docs/data/ERA_NORMALIZATION_V1.md
- docs/data/era-normalization-summary.json
- docs/data/era-normalization-gold-manifest.json
- docs/data/era-normalized-feature-definitions.yaml
- docs/data/feature-eligibility-matrix.json
- docs/data/normalization-case-studies.json
- docs/data/qualification-sensitivity-analysis.json
- docs/METHODOLOGY.md
- docs/DATA_DICTIONARY.md
- docs/EXPERIMENTS.md
- docs/PROJECT_LOG.md
- This step record.

Ignored outputs comprise 480 deterministic Gold Parquet partitions under data/gold.

## 6. Qualification sensitivity analysis

| Candidate | Mean qualified share | Minimum share |
|---|---:|---:|
| Regular 10% games | 93.15% | 84.13% |
| Regular 20% games — selected | 88.31% | 75.87% |
| Regular 30% games | 83.94% | 69.75% |
| Playoff all appearances | 100.00% | 100.00% |
| Playoff 10% games — selected | 92.38% | 72.66% |
| Playoff 20% games | 73.77% | 49.73% |
| Selected games plus 10% max minutes | 69.00% | 52.90% |

The Regular rule balances removal of fringe samples against meaningful participation. The Playoff rule avoids one-game observations without eliminating roughly one quarter of players. Minutes were rejected as a universal rule because the combined candidate over-excluded and was evaluable in only 100 partitions.

## 7. Data observations

- 33,180 of 37,472 TOTAL player-seasons qualified; 4,292 remain as non-qualified.
- PPG and games are eligible in all 160 partitions. Official per-75 is eligible only in 60 post-1996 partitions.
- Non-null minutes were insufficient evidence: early rows were frequently zero placeholders. The 99% positive-minute gate reduced apparent per-36 eligibility from 150 partitions to 100.
- Team-scoring context is available in 142 partitions and withheld in 18 with source quarantine. Official advanced league pace is available in 60; canonical team possessions are unavailable in all 160.
- Eligibility-method records comprise 6,890 AVAILABLE, 2,944 UNAVAILABLE_COVERAGE, 400 UNAVAILABLE_POSSESSIONS, and 6 UNAVAILABLE_ZERO_MAD.
- Regular Season and Playoffs remained separate; traded players enter distributions once through TOTAL rows.

## 8. Decisions made

- Select season-scaled games qualification under ADR-0009.
- Use population z-score, scaled median/MAD robust z-score, midrank percentile, and restricted ratio indexes under ADR-0010.
- Require 99% positive observations for minute and possession denominators in addition to coverage status.
- Derive no historical pace or possessions and withhold context made incomplete by source quarantine.
- Keep long Gold authoritative for feature provenance and wide Gold as a convenience materialization.

## 9. Validation/tests executed

- Verified corpus ID, cutoff, aggregate fingerprint, and all 380 input hashes.
- Checked qualification, shortened-season scaling, formulas, ties, denominators, coverage gates, TOTAL selection, season-type isolation, provenance, and deterministic fingerprinting offline.
- Validated z-score properties over 263 groups with zero failure.
- Observed zero duplicate keys, orphans, non-finite values, percentile violations, TEAM-row consumption, unavailable leakage, NULL-to-zero conversion, or season-type mixing.
- Re-executed the build with an expected fingerprint and reproduced all 480 partition hashes.
- Ran the complete offline Pytest suite, Ruff, strict Mypy, artifact validation, JSON/YAML parsing, Git-ignore checks, and whitespace validation successfully.

## 10. Result

The build created 160 league-context rows, 599,552 long feature rows, and 37,472 wide player-season rows across 480 ignored Gold partitions (30,189,330 bytes). Output fingerprint a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852 reproduced exactly without network access; the verification run completed in 29.42 seconds.

## 11. Known limitations

- Availability is intentionally non-uniform; primitive NULLs are expected and cannot be read as poor performance.
- Per-75 uses official player possessions and begins only in 1996-97.
- The fixed 0.44 TS free-throw factor is a consistent estimate and does not distinguish every free-throw possession type.
- Qualification controls distribution membership but does not model estimate uncertainty; playoff sample sizes remain explicit.
- Player-distribution means and aggregate attempt-weighted league rates answer different questions.
- Wide Gold exposes only common features; long Gold and the registry are the complete contract.
- No composite, career, award, playoff weighting, ranking, or ML conclusion is produced.

## 12. Explicit decision: PASS

**PASS.** All 160 contexts exist; qualification was sensitivity-tested; eligible values produce reproducible normalization; efficiency and rates are coverage-gated; missing history remains NULL; per-75 is blocked without official possessions; season types remain isolated; features carry provenance; diagnostic cases are interpretive only; and the second offline run reproduced every Gold hash.

## 13. Recommended STEP-0008

Perform an official awards/accolades source feasibility and canonical event-ingestion step. Populate evidence-based player_awards facts and historical coverage without assigning weights, championship values, composite dimensions, or rankings.
