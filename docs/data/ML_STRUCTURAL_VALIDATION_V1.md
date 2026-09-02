# Unsupervised structural validation V1

## Scope

`unsupervised-structural-validation-v1` is an entirely offline diagnostic over frozen GOATLAB-HIST-V1 and the STEP-0012 candidate audit. It uses no external ranking, labels, supervised targets, overall GOAT score, Top 100, or public 0–100 dimension values.

The implementation uses Python 3.12+ and NumPy 2.5.2. NumPy is an explicit project dependency because STEP-0013 directly uses its deterministic linear-algebra and random-generator APIs; no new runtime dependency was downloaded during this offline step.

## Analytical matrices and missingness

Five labeled matrix views were audited: 32 surviving dimension candidates, 16 independently assembled cross-era career primitives, seven post-1996 modern-enriched primitives, seven magnitude-preserving profile features, and the corresponding row-centered/RMS-scaled profile shape. Every view uses coverage-qualified complete intersections without imputation.

The full candidate matrix retains 1,391 of 2,656 broad-high-recall players (52.37%), 1,311 of 1,891 participation-qualified players (69.33%), and 1,391 of 5,103 master players (27.26%). Its retained debut cohorts contain only one 1960s player and no pre-1960 player. This is a severe selection limitation, not a hidden claim of cross-era completeness. The independent cross-era primitive matrix retains 1,547 broad players; the modern-enriched matrix retains 1,657 broad players and is explicitly not universal.

Standard and robust scaling are separate runs. Constant robust-scaled columns are excluded and reported rather than synthesized.

## PCA and factor structure

On the primary 1,391 × 32 standard-scaled candidate matrix, PCA explains 59.15%, 11.05%, 7.86%, and 5.11% in the first four components (83.17% cumulative). Fixed-seed 95th-percentile parallel analysis retains four components. The first axis is broad candidate covariance, the second is team-success heavy, the third is accolade-heavy, and the fourth separates playoff-change from high-bar longevity/era breadth. These are neutral covariance descriptions; signs are arbitrary.

Across 24 bootstrap samples, mean loading correlations for the four matched components are 0.989–0.994 and mean subspace similarity is 0.994. Excluding active careers leaves matched loading correlations of 0.992–0.999. Standard scaling needs four components for 80% variance; robust scaling needs three.

Iterated principal-axis factoring was run separately for two through ten factors with five-fold held-out correlation-reconstruction diagnostics. The selected seven-factor Varimax solution reflects diminishing held-out error after seven and yields interpretable groups centered on peak/offense, winning, accolades, longevity/era breadth, playoff change, defense, and efficiency offense. Its bootstrap matched-loading correlations average above 0.997. Seven is not a forced copy of the proposed framework and is not a final dimension count.

## Candidate uniqueness and pruning

Each candidate receives maximum cross-family correlation, multiple R², residual variance, PCA/factor loading evidence, and an incremental-variance proxy. Uniqueness means residual structure, not importance.

Era candidates have other-family multiple R² from 0.934 to 0.992. They directly summarize already era-normalized peak/cumulative evidence, so Era Dominance is recommended as `USE_AS_DIAGNOSTIC_ONLY`, not an eighth additive vote.

PEAK-B and PEAK-E correlate 0.985; both remain because quality and opportunity adjustment have distinct semantics, while multi-horizon PEAK-D is redundant. ACCOLADES-B and ACCOLADES-C correlate 0.996 and are redundant with each other; the shortlist retains raw profile, honor persistence, and major-winner lenses. All-era Defense remains rebounding-led and historically limited; DEFENSE-A is retained only for coverage-qualified finalization, DEFENSE-D is insufficient as a universal bridge, and modern DEFENSE-C remains deferred.

The 38-candidate audit becomes an 18-candidate non-final shortlist: three Peak, three Longevity, two Offense, one coverage-qualified Defense, three Playoffs, three Accolades, and three Winning candidates. Four prior rejections and two modern deferrals are preserved.

## Player-profile archetypes

K-means was evaluated for k=2 through 12 with 20 starts. The profile-shape solution selects two coarse clusters (680 and 711 players; silhouette 0.270). One emphasizes Winning/Accolades relative to Peak/Offense; the other shows the reverse relative profile. These are neither greatness tiers nor ordered groups.

K-means is stable across seeds (mean ARI 0.996) and bootstraps (mean ARI 0.938). Era association is weak (Cramér's V 0.088), and active-career exclusion yields ARI 0.909. However, method agreement is only moderate with hierarchical clustering (ARI 0.615) and weak with the selected ten-component diagonal GMM (ARI 0.110). GMM uncertainty and the alternative spherical covariance results are retained. The defensible conclusion is a stable coarse K-means profile split, not a settled player taxonomy.

## Outputs and reproducibility

Generated, ignored Gold lives under `data/gold/ml_structure/` and contains PCA scores, factor loadings, cluster membership/probability diagnostics, hierarchical merges, candidate pruning, and deterministic SVG diagnostics. Forty generated artifacts occupy 4,502,934 bytes and fingerprint to `0f06e17c382de61a260dbd9eabb872a0613bf2c2146468c2a81bd454c4951093`.

The required second offline build issued zero network requests and reproduced every Gold/figure hash exactly. Committed analytical reports fingerprint to `5bc5bf4750c0d59fb30523fcb32bb2ef9cd4d56688f39066702b1274360720bc`. The certified baseline runtime is approximately 35.59 seconds.

## Limitations

- The full candidate intersection heavily selects later cohorts and cannot establish universal historical factor structure.
- Candidate-scoped award evidence contributes to that selection.
- Principal-axis factoring is not probabilistic maximum-likelihood factor analysis; held-out correlation reconstruction is used instead of likelihood.
- The hierarchical audit uses a deterministic 300-player subset for computational transparency.
- Two shape clusters are coarse, and cross-model disagreement blocks stronger archetype claims.
- Position is not modeled because full-corpus canonical position coverage has not been qualified.
- Active careers are to-date and unprojected.
