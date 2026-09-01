# STEP-0012 — GOAT dimension candidate design and redundancy audit

## 1. Objective

Create, compare, and stress-test multiple traceable candidate definitions for eight intended GOAT dimensions without selecting final formulas or producing any overall player ordering.

## 2. Motivation

The factual foundation supports many plausible definitions of greatness. Combining those facts prematurely would conceal shared evidence, historical missingness, arbitrary scaling, and internal weight choice. This step makes those choices measurable before model validation.

## 3. Inputs

- GOATLAB-HIST-V1: `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`
- Era normalization: `a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852`
- Career primitives: `5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b`
- Awards: `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258`
- Team success: `707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333`
- All-Star/stat leaders: `e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880`

No network access or factual source acquisition was used.

## 4. Work performed

- Defined 38 candidates across Peak (5), Longevity (5), Offense (4), Defense (4), Playoffs (5), Accolades (5), Winning (5), and Era Dominance (5).
- Retained all 5,103 players and evaluated four broad population rules.
- Implemented four scaling and four missingness policies.
- Built a primitive ownership registry and evaluated strict, penalized-sharing, and raw-evidence-separation policies.
- Calculated within-candidate primitive, within-dimension candidate, and cross-dimension Pearson/Spearman correlations.
- Ran 200 deterministic uniform-simplex weight samples per candidate with seed 120012.
- Audited debut-era coverage, active-career semantics, missing evidence, and modern-only dependency.
- Applied predeclared coverage, redundancy, and instability rejection rules.
- Wrote partitioned ignored Gold candidate, coverage, and sensitivity artifacts.

## 5. Files created or changed

- `src/goatlab/features/dimension_candidates.py`
- `pipelines/features/build_dimension_candidates_v1.py`
- `tests/test_dimension_candidates.py`
- ADR-0019 through ADR-0021
- `docs/data/GOAT_DIMENSION_CANDIDATES_V1.md`
- `docs/data/goat-dimension-candidates.yaml`
- `docs/data/dimension-{candidate-summary,redundancy-audit,era-fairness,weight-sensitivity,coverage-audit,case-studies}.json`
- `docs/PROJECT_LOG.md`, `docs/METHODOLOGY.md`, `docs/DATA_DICTIONARY.md`, and `docs/EXPERIMENTS.md`
- Ignored Gold under `data/gold/dimension_candidate_{scores,coverage,sensitivity}/`

## 6. Data observations

- Analytical population sizes are 5,103 all players, 1,891 participation-qualified, 2,606 career-signal, and 2,656 broad high-recall.
- The build emits 3,102,624 labeled score rows, 193,914 coverage rows, and 38 sensitivity rows.
- Fifteen primitives have cross-dimension lineage and 31 candidate pairs have absolute Spearman correlation at least 0.95.
- `LONGEVITY-E` versus `ERA-D` is 0.998; `LONGEVITY-B` versus `ERA-E` is 0.996; `PEAK-D` versus `ERA-B` is 0.991.
- Five-year Peak is available for 47.06% of the broad population; contiguous playoff Peak is available for 37.31%.
- Modern enriched Offense and Defense have zero availability for pre-1960 and 1960s debut cohorts.
- PlayerAwards-dependent candidates retain `NOT_QUERIED` gaps; All-Star roster and statistical-title evidence remains separate.
- Monte Carlo ordering stability ranges from 0.830 to 1.000; no candidate crosses the 0.75 instability threshold.

## 7. Decisions made

- Use raw-evidence separation as the default policy for future experiments, without finalizing it.
- Treat coverage confidence as metadata, never a score penalty.
- Use the 2,656-player broad high-recall population as the V1 scaling reference, not as permanent eligibility.
- Reject `PEAK-C` and `PLAYOFFS-B` for coverage; reject `DEFENSE-B` and `PLAYOFFS-E` for near-duplicate signal.
- Defer `OFFENSE-D` and `DEFENSE-C` from universal use because of post-1996 dependency.
- Keep Era Dominance under explicit redundancy review rather than assuming it is an independent dimension.

## 8. Validation/tests executed

- Offline unit tests for catalog completeness, ownership overlap, scaling/ties, missingness, thresholds, candidate combination, award applicability, defensive coverage, playoff/winning semantics, All-Star/title separation, correlations, deterministic Monte Carlo, era groups, and rejection rules.
- Full existing `pytest` suite.
- Ruff formatting/lint.
- Strict Mypy for the complete `goatlab` package.
- Machine-readable artifact integrity validation.
- Two complete offline builds with exact expected output fingerprint comparison.

## 9. Results

**PASS.** All eight dimensions have multiple traceable candidates. Missingness, era fairness, active careers, shared evidence, redundancy, and weight sensitivity are explicit. Thirty-two candidates remain experimental, four are rejected, two are deferred, and none is final. No overall score, dimension ranking, player ranking, consensus target, or Top 100 was created.

## 10. Known limitations

- Defensive evidence remains structurally sparse for early eras.
- PlayerAwards acquisition remains candidate-scoped.
- Scaling-reference choice changes diagnostic transforms and is not final.
- Simplex sampling tests weight arbitrariness but does not define plausible basketball priors.
- Candidate correlations reveal empirical overlap but do not decide conceptual ownership.
- Active careers remain incomplete to the frozen cutoff.

## 11. Next step

Recommended STEP-0013: unsupervised structural validation of the primitive/candidate space (factor analysis/PCA and clustering as diagnostics), plus candidate-family pruning under frozen ownership and coverage contracts. It must not train against consensus rankings or create an overall GOAT ordering.
