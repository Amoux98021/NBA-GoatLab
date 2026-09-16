# STEP-0015N — Final Overall V2 promotion audit

Date: 2026-09-17

Step result: **PASS**

Promotion verdict: **DO_NOT_PROMOTE_OVERALL_V2**

Recommendation: **OVERALL_ELIGIBILITY_POLICY_REQUIRES_REVIEW**

## Objective

Test whether promoted Peak V2, tiered Longevity, and tiered Defense V2 can be propagated through
the frozen seven-dimension Overall formula with their dependence and uncertainty intact. The audit
also determines whether the resulting point-eligible population is broad enough to support a
defensible deterministic V2 ranking.

## Frozen inputs

- STEP-0015K fingerprint: `3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f`
- STEP-0015L fingerprint: `cb740fc68a77df3cb30b68e854e413c670394638ff2bf7b47401b905c7a81580`
- STEP-0015M fingerprint: `a2056a6d793b2f82066c07bc4924787d3e95f8485ef37ff15911bfb7a321deb7`

All frozen Peak, Longevity, Defense, Overall V1, and V1 Top-100 inputs were hash-verified. The exact
2,500 paired Peak/Longevity path from STEP-0015L was reconstructed with maximum difference 0.0.

## Coupling candidates

The audit compared independent Defense, pooled Gaussian-copula rank coupling, pattern-specific
Gaussian-copula rank coupling, and an empirical-rank diagnostic. Pattern-specific Gaussian-copula
rank coupling was selected before inspecting ranking outputs. It preserves Peak/Longevity draws
exactly and only permutes the empirical Defense marginal.

Target versus reproduced mean latent-rank correlations were 0.4328 versus 0.4307 for
Defense–Peak and 0.1937 versus 0.1977 for Defense–Longevity. All matrices were symmetric and PSD;
no material correction was required. Defense marginal medians and sorted values were preserved to
deterministic numerical tolerance.

## Joint validation

The reference population contains 1,197 careers with richer Peak, Longevity, Defense, and all four
fixed dimensions. Frozen point gates are MAE <=2, Spearman >=0.98, absolute bias <=1, <=10% above
five points, and 87–93% nominal 90% coverage.

| Pattern | MAE | Spearman | Bias | >5 | 90% coverage | Point gate |
|---|---:|---:|---:|---:|---:|---|
| Full reference | 0.457 | 0.9995 | -0.028 | 0.00% | 90.06% | pass |
| Partial Presence | 1.383 | 0.9950 | +0.240 | 5.35% | 90.06% | pass |
| Mixed provisional/interval | 2.003 | 0.9914 | +0.111 | 6.93% | 90.06% | **fail** |
| Early transition | 2.416 | 0.9876 | +0.105 | 11.19% | 90.06% | fail |
| No Presence | 2.937 | 0.9831 | +0.175 | 18.30% | 89.81% | fail |
| Traditional only | 3.853 | 0.9711 | -0.192 | 30.24% | 89.81% | fail |

The mixed pattern misses the MAE gate by 0.0027. The gate was not rounded or relaxed.

## Status and eligibility result

All-player Overall statuses are 312 official points, 284 provisional points, 1,286 interval-only,
and 3,221 unavailable. `BROAD_HIGH_RECALL` contains the same point and interval counts with 774
unavailable.

Among the archived V1 Top 100, only three have official Overall points and 14 provisional points;
83 are interval-only. A deterministic V2 ranking would therefore exclude 83% of the previously
plausible Top-100 population because of measurement form, not basketball quality.

This fails the objective that Overall V2 support a defensible ranking population. The audit is
complete and reproducible, but Overall V2 is not promoted and no V2 Top 100 is published.

The complete output fingerprint is
`b6248062490ca6b2d63e616af5ac759a59abc9ea3e9dc15dd4f2bd264741bb95`.

## Uncertainty policy

The candidate architecture retains exact weights: Peak 17%, Longevity 14%, Offense 16%, Defense
14%, Playoffs 18%, Accolades 10%, Winning 11%. It applies weights within every aligned draw. It
never drops a dimension, renormalizes weights, substitutes an interval midpoint as exact, or
multiplies quality by confidence.

## Diagnostics

Jordan versus LeBron is diagnostic only: under the unpromoted research distributions,
`P(Jordan > LeBron) = 0.102` and the reverse is 0.898. This result did not influence coupling or
promotion policy. Early-era and mixed-form players are predominantly interval-only because the
joint evidence pattern fails the frozen Overall gate.

## Result

**PASS + DO_NOT_PROMOTE_OVERALL_V2**

The next step should review Overall ranking eligibility and publication semantics for a population
where calibrated intervals are common. It must not lower calibration gates or treat interval
centers as official points merely to increase ranking coverage.
