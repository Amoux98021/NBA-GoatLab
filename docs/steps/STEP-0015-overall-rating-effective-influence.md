# STEP-0015 — Overall rating, effective influence, redundancy, and ranking eligibility

## 1. Objective

Audit award-related ranking eligibility, quantify nominal versus effective dimension influence, evaluate defensible weight families, and publish an internal Overall V1 ranking only if all constitutional gates pass.

## 2. Motivation

STEP-0014 froze seven dimension scores but showed substantial covariance. A transparent Overall needs both a normative coefficient vector and an empirical account of how correlated inputs affect rankings.

## 3. Inputs and constitutional requirements

The build verifies `goatlab-v1-dimension-scores-v1` fingerprint `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`, corpus fingerprint `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`, and award fingerprint `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258`.

The machine Constitution requires seven complete dimensions, no missing-weight redistribution, no Era Dominance input, no confidence penalty, no projection, and no player-specific or external-ranking optimization. Frozen dimension formulas were not changed.

## 4. Work performed

- Screened all 2,963 unknown-award players with a deterministic optimistic bound.
- Evaluated equal, constitution-informed, redundancy-adjusted, and stability-oriented weight methods.
- Computed exact Shapley variance allocations, candidate comparisons, leave-one-out audits, local elasticity, group/family influence, and 10,000 random-simplex draws.
- Audited debut eras, dimension-profile archetypes, STEP-0013 clusters, and active status.
- Produced complete-player rankings, the internal Top 100, rank intervals, and mechanical player diagnostics.
- Rebuilt the complete Gold output twice without network access.

## 5. Files created or changed

Implementation: `src/goatlab/rankings/overall.py`, `pipelines/rankings/build_overall_v1.py`. Tests: `tests/test_overall.py`, `tests/test_overall_artifacts.py`. Decisions: ADR-0027 and ADR-0028. Reports include `GOAT_OVERALL_V1.md`, weight, eligibility, influence, leave-one-out, local/random sensitivity, cohort, diagnostics, Top-100, and summary artifacts. Living project documentation was extended without rewriting earlier step records.

## 6. Accolades eligibility result

Exactly 303 `NOT_QUERIED` players have all other six scores. With Accolades fixed optimistically to 100, none crosses any paired Top-100 cutoff across 10,000 admissible vectors or A–D. The maximum optimistic score is 76.22 and the closest paired-cutoff gap is -15.23. They are `SAFE_TO_EXCLUDE_FROM_V1_QUERY`. The other 2,660 also lack another dimension and remain `REVIEW_REQUIRED`. Additional award requests: zero. Complete profiles remain 1,882.

## 7. Candidate formulas and selected V1

- A: equal 1/7 benchmark.
- B: 21/16/17/11/17/9/9 constitution-informed emphasis.
- C: 17/14/16/14/18/10/11 redundancy-adjusted balance, selected.
- D: deterministic bounded search result, retained as a stability diagnostic.

Order is Peak/Longevity/Offense/Defense/Playoffs/Accolades/Winning. C is selected because it is round-number transparent, keeps 79% nominal direct-performance influence, restores material Defense/Winning influence, reduces correlated Peak/Longevity dominance relative to B, and is highly stable. No player name or external list entered selection.

## 8. Effective influence and redundancy

Default exact Shapley shares are 20.72%, 16.56%, 17.07%, 11.07%, 18.77%, 8.13%, and 7.68%. Peak/Longevity together explain 37.28% of Overall variance; direct performance 84.20%; recognition/outcome 15.80%. Equal nominal weights are not equal effective influence: their Peak/Longevity family reaches 35.01%.

## 9. Stability and structural audit

Ten thousand fixed-seed draws yield Spearman 0.9946–0.9999 against C. Median Top-100 overlap is 0.95 and minimum is 0.92. Local perturbations retain minimum Spearman 0.9979 and minimum Top-100 overlap 0.93. Leave-one-out Top-100 overlap ranges from 0.82 without Defense to 0.97 without Peak/Longevity. These removals are diagnostics only and never rank incomplete profiles.

## 10. Era, archetype, and active-player audit

No manual equality constraint is imposed. Eligible cohort means range from 52.02 (2020s debuts) to 63.78 (pre-1960), reflecting both real profiles and selection/completion structure; this is reported as residual cohort sensitivity. All dimension-profile archetypes occur in the eligible population. Historical position data remains insufficiently qualified for a defensible position audit. Active players are accomplishments-to-cutoff only and receive no completion penalty or future projection.

## 11. Outputs and fingerprints

Five ignored deterministic Gold partitions contain 5,103 player score/eligibility rows, 100 Top-100 rows, 1,882 stability rows, 7,528 candidate rows, and 5,103 eligibility rows. Their combined fingerprint is `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`; the committed analytical-report fingerprint is `b6c7003bd53d6fd4d280f5244eda6beac50dda8583f2153404b905ce402b38e2`. Output size is 638,689 bytes.

## 12. Tests and validation

Tests cover weight simplex rules, score range, NULL behavior, no redistribution, deterministic tie handling, exact variance accounting, eligibility bounds, resolved Top-100 Accolades, active cutoffs, constitutional exclusions, sensitivity completeness, and fingerprints. The final full suite passed 152 tests with one opt-in network test skipped; Ruff passed; strict Mypy passed across 24 source files; 79 JSON and 10 YAML artifacts parsed; Parquet schemas, Git-ignore, whitespace, and the exact second-build check passed.

## 13. Known limitations

- Only 1,882 players have all seven required scores; incomplete profiles remain unranked.
- Peak/Longevity covariance is substantial and cannot be erased without changing the constitutional concepts.
- Effective influence is population-dependent and should be recalculated for user slider selections.
- Cohort comparisons inherit complete-case selection effects; 2020s careers are incomplete to date.
- Canonical historical position coverage remains unqualified.
- Exact nominal weights remain a transparent normative choice, not a uniquely estimable scientific truth.

## 14. Result

**PASS.** Eligibility, influence, stability, missingness, era/archetype, active-career, and reproducibility gates support `goatlab-v1-overall-v1` and the internal V1 Top 100.

## 15. Next step

Recommended STEP-0016: design the public, user-adjustable ranking contract and explanation layer. It should recompute nominal/effective influence for slider choices, preserve unranked semantics, expose dimension/coverage breakdowns, and avoid retraining or altering the frozen V1 methodology.
