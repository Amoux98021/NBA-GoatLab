# GOATLab V1 dimension scores

## Contract

`goatlab-v1-dimension-scores-v1` operationalizes the seven binding dimensions in `docs/constitution/GOATLAB_V1_CONSTITUTION.md`. It runs offline from the frozen GOATLAB-HIST-V1 analytical stack. It creates no official Overall score, no default dimension weights, no Top 100, and no player-specific adjustment.

All component calculations use era-normalized season evidence. The final scalar for each dimension is a midrank empirical-CDF score against the frozen 2,656-player STEP-0012 `BROAD_HIGH_RECALL` reference population. The mapping avoids raw min-max compression. Approximately: 0 is the bottom observed reference value, 50 the median, 90/95/99 those observed percentiles, and 100 the top observed value. Ties share a midrank. These are ordinal population positions, not ratio units.

## Final formulas

| Dimension | V1 formula | Required ownership boundary |
|---|---|---|
| Peak | 70% best complete contiguous three-season overall-quality percentile + 30% apex | Regular season only; no awards, outcomes, or five-year universal anchor |
| Longevity | 35% seasons at/above P80 + 40% area above P80 capped at P90 + 25% longest P80 run | No career length alone, uncapped apex, or award points |
| Offense | Career mean of season Global Value Creation: joint scoring (65% PPG + 35% TS when available; PPG required), then 65% stronger scoring/creation axis + 35% secondary axis | Regular season; no titles or postseason |
| Defense | Career mean of 65% era-relative team scoring suppression + 35% qualified rebound/steal/block action context | Regular season; no DPOY, All-Defense, awards, or championships |
| Playoffs | 65% absolute individual postseason quality + 20% bounded resilience/lift + 15% repeated elite postseason evidence | No advancement, Finals outcome, or championship signal |
| Accolades | 60% bundled Major Honors + 35% bundled Sustained Recognition + 5% title support | No champion events; within-season and cross-axis caps prevent stacking |
| Winning | 65% one highest participation-conditioned postseason tier + 25% sustained elite team context + 10% playoff breadth | No individual playoff quality, Finals MVP, or champion-award count |

Overall season quality used by Peak/Longevity is a regular-season-only blend of portable Offense and Defense season evidence. A stronger/secondary construction allows different archetypes to express quality without defining an Overall career score.

## Formula selection evidence

Peak 60/40, 70/30, and 80/20 are nearly rank-identical (Spearman 0.9996; top-100 overlap 0.97–0.98 around the selected formula). The middle 70/30 version is selected because three-year evidence remains decisively primary while the apex remains material.

Longevity thresholds were calibrated against whether a season received All-NBA recognition, strictly as external calibration rather than score input. P80 produced the best Youden J (0.6781), capturing 84.97% of 985 observed All-NBA seasons while 82.84% of non-All-NBA seasons fell below it. P85/P90/P95 produced J values of 0.6496/0.5883/0.4364. Season credit caps at P90, so P99.9 cannot recreate Peak.

Offense volume weights 60%, 65%, and 70% have Spearman at least 0.9996 and top-100 overlap at least 0.99. The selected 65% preserves a meaningful efficiency contribution without allowing sparse efficiency to replace the required scoring-volume anchor. Playoff, Accolades, and Winning perturbations are similarly stable. Every alternative also reports active-career, debut-era, STEP-0013 archetype, missingness, top-N, and largest-rank-mover diagnostics; historical position coverage remains explicitly unqualified. Complete results are in `dimension-score-sensitivity.json`.

## Coverage and confidence

Every one of 5,103 players has seven output rows. A row may have a NULL score. Coverage states distinguish `AVAILABLE`, `PARTIAL_EVIDENCE`, `INSUFFICIENT_SAMPLE`, `SOURCE_UNAVAILABLE`, and `NOT_QUERIED`. Confidence states are `STRONG`, `MODERATE`, `LIMITED`, and `UNAVAILABLE`; confidence describes evidence and is never multiplied into score quality.

| Dimension | Scored | Full available | Partial | Insufficient / unavailable |
|---|---:|---:|---:|---:|
| Peak | 2,456 | 1,588 | 868 | 2,647 insufficient |
| Longevity | 4,187 | 4,187 | 0 | 916 unavailable |
| Offense | 4,187 | 2,601 | 1,586 | 916 unavailable |
| Defense | 4,130 | 2,628 | 1,502 | 973 unavailable |
| Playoffs | 2,768 | 2,684 | 84 | 2,335 insufficient |
| Accolades | 2,140 | 2,140 | 0 | 2,963 not queried |
| Winning | 5,102 | 5,102 | 0 | 1 unavailable |

Missing optional evidence is renormalized only when the required conceptual anchor remains. This is always exposed as partial coverage. Missing evidence never becomes zero. Because PlayerAwards acquisition was candidate-scoped, 2,963 Accolades scores remain `NOT_QUERIED`, not zero.

## Anti-stacking and ownership audit

- Peak and Longevity share season-quality infrastructure, but Longevity clips each season and uses breadth/persistence. Their Spearman correlation is 0.9304; high overlap is explicit and deferred to effective-weight analysis.
- Offense/Defense are regular-season only; Playoffs is postseason individual evidence only.
- Playoffs contains no team outcome; Winning contains no individual performance signal.
- Winning assigns exactly one highest postseason tier per player-team-season.
- Defense excludes DPOY and All-Defense; Offense excludes statistical-title credit.
- Accolades bundled 154 major-honor seasons and 2,196 sustained-recognition seasons; 142 related major/sustained season combinations hit the cross-axis cap. NBA Champion events and a unanimous-MVP bonus are absent.
- Generic WOWY is absent. Team suppression is defense-specific; team outcomes remain Winning.

## Structural audit

The complete seven-score audit population is 1,882 players. Spearman correlations include Peak–Offense 0.8027, Peak–Longevity 0.9304, Winning–Accolades 0.4128, Defense–Playoffs 0.2515, and Playoffs–Winning 0.3126. Incremental residual variance after regressing each dimension on the other six is 8.3% Peak, 18.0% Longevity, 19.8% Offense, 38.8% Defense, 50.2% Playoffs, 53.2% Accolades, and 65.8% Winning. This quantifies overlap; it does not repeal a constitutional dimension.

The first PCA component explains 60.18% of standardized complete-score variance; the next three explain 15.46%, 8.58%, and 6.83%. Five hundred deterministic random-simplex Overall diagnostics have mean Spearman 0.9599 and minimum 0.7404 relative to an equal-weight diagnostic; mean/minimum top-50 overlap are 0.821/0.56. No sampled or equal-weight combination is an official ranking.

## Era fairness and enrichment

Era-debut cohorts are reported descriptively with no quota or score correction. Median-score ranges across known debut cohorts are widest for Winning (9.0–27.3) and narrower for Offense (24.3–37.8), Defense (37.8–52.2), and Playoffs (33.7–49.5). Peak availability is lowest for 2020s debuts because many active careers do not yet have a complete qualified three-season window; this is incomplete-to-cutoff evidence, not a score penalty.

The portable/action Defense bridge passes its predeclared thresholds (n=3,368, Spearman 0.9883, median raw delta 0.0153). Modern per-75 Offense is strongly correlated with universal Offense (n=2,308, Spearman 0.9322, R² 0.8778), but cohort residuals prevent a universal correction. Modern advanced defensive rating is not a valid bridge (n=2,337, Spearman 0.2813, R² 0.0840). Neither modern diagnostic changes a universal score, and position-bias evaluation remains blocked by unqualified position coverage.

## Reproducibility and limitations

The build writes deterministic Parquet for player scores, component breakdowns, and sensitivity. The final data fingerprint is `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`.

Rebuild from repository root with `PYTHONPATH=src python pipelines/rankings/build_dimension_scores_v1.py --run-at 2026-09-08T20:00:00Z`. Certify a second run by adding `--expected-fingerprint 0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`. Both commands are offline and read only the frozen local Silver/Gold inputs.

Important limitations:

- Overall season quality is intentionally portable and does not capture every form of creation, gravity, or defense.
- Early Defense confidence is limited because direct actions were not recorded.
- Accolades remain unavailable outside the audited PlayerAwards acquisition set.
- Playoff evidence is unavailable for players without qualifying postseason samples; sample size affects confidence, not score quality.
- Active players are accomplishments through 2025-26 only.
- Score ECDFs depend on the versioned reference population and must be re-versioned if that definition changes.
