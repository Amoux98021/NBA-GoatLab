# GOAT dimension candidate audit V1

## Scope

`goat-dimension-candidates-v1` is an offline diagnostic layer over the frozen factual and primitive artifacts. It evaluates 38 candidate definitions for Peak, Longevity, Offense, Defense, Playoffs, Accolades, Winning, and Era Dominance. It creates no overall score, no final 0–100 dimension, no player ordering, and no Top 100.

Inputs are fingerprinted GOATLAB-HIST-V1, era normalization, career, awards, team-success, All-Star, and statistical-leader outputs. Silver and earlier Gold are immutable.

## Evaluation populations

All 5,103 players remain in every output. Four reference populations were audited:

| Population | Rule | Players |
|---|---|---:|
| All players | Every canonical identity | 5,103 |
| Participation-qualified | At least five qualified Regular Season seasons | 1,891 |
| Career-signal | At least three qualified seasons or a core 95th-percentile season | 2,606 |
| Broad high-recall | At least three qualified seasons or a core 90th-percentile season | 2,656 |

The broad population is the V1 diagnostic scaling reference. It is not permanent GOAT eligibility and does not reuse the 2,140-player award-acquisition set as a ranking gate.

## Common methods

Each primitive is separately transformed by career-universe midrank percentile, robust standardization, population z-score, and empirical CDF. Candidate values are weighted means of transformed available components and are always labeled by scale and missingness policy.

The missingness experiments are core-only, available-feature renormalization, two-thirds evidence threshold, and era-specific enrichment. None imputes, zero-fills, or assumes average performance. Coverage confidence is evidence metadata only.

Equal component weights are a baseline, not a judgment. Two hundred uniform-simplex samples per candidate use deterministic seed 120012. The audit records score/percentile variance, player percentile IQR, and sampled ordering stability.

## Feature ownership

The registry assigns primary and secondary ownership and evaluates three policies. Raw-evidence separation is the recommended policy for future experiments: defensive box evidence remains Defense while DPOY/All-Defense events remain Accolades; normalized playoff performance remains Playoffs while team outcomes and participation remain Winning. Fifteen primitives have cross-dimension use and are explicitly listed. Shared evidence is never hidden.

## Candidate findings

### Peak

Single-season, three-year, multi-horizon, and availability-aware candidates remain valid experiments. The five-year candidate is rejected at the broad-population gate because only 47.06% have sufficient evidence. Three-year quality and availability-aware candidates correlate at Spearman 0.991, showing that availability changes cases without creating a distinct general signal. Peak candidates strongly overlap Era Dominance.

### Longevity

Elite counts, cumulative dominance, prime persistence, participation-plus-quality, and high-bar longevity remain experiments. Threshold families are highly correlated. High-bar longevity and Era percentile separation correlate at 0.998; cumulative dominance and career Era Dominance correlate at 0.996. These are likely competing definitions rather than additive dimensions.

### Offense

Cross-era core, scoring/playmaking balance, and efficiency-adjusted production remain experiments. Modern enriched offense is deferred from universal comparison: pre-1960 and 1960s availability is zero, with the empirical post-1996 boundary visible in later cohorts. It may be an era-specific enrichment only.

### Defense

No single universal defensive composite is established. Box Defense is unavailable under the primary threshold for essentially all pre-1970 careers because steals and blocks did not exist. Honors-augmented Defense is rejected as near-duplicate signal and overlaps Accolades. Modern advanced Defense is deferred because it is structurally post-1996. Coverage-bridged Defense remains only a cautious experiment; honors cannot retroactively create individual box evidence.

### Playoffs

Absolute performance, postseason longevity, playoff change, and sample-aware evidence were tested. Contiguous playoff peak is rejected because only 37.31% of the broad population qualifies. Sample-aware postseason impact is rejected as a near duplicate of postseason longevity (Spearman 0.990 with shared playoff-games lineage). Regular-to-playoff change uses normalized differences, never unstable ratios.

### Accolades

Raw profile, empirical scarcity, opportunity, honor persistence, and major-winner candidates remain diagnostic experiments. Raw, scarcity, and opportunity variants correlate above 0.996, so they must not be stacked. PlayerAwards-sourced evidence remains unavailable for 2,963 `NOT_QUERIED` players; roster All-Star and statistical-title evidence remain separately named and do not erase that status.

### Winning

Team outcome, playoff-qualified, Finals-participation, opportunity-aware, and sustained-success candidates remain factual experiments. Regular champion membership, playoff participation for a champion, Finals participation for a champion, and official champion event remain separate primitives. No rings multiplier or championship credit allocation exists.

### Era Dominance

All five variants were computed, but redundancy is the central finding. Single/multi-season variants correlate strongly with Peak; breadth and percentile separation correlate at 0.997; career dominance correlates at 0.996 with cumulative Longevity. Era Dominance should be treated as a possible alternative lens or diagnostic, not assumed to deserve an independent vote.

## Era, active-career, and coverage audit

Era fairness means structural comparability, not equal decade representation. Modern offense and defense are explicitly incomparable before their source boundary. Candidate-scoped award coverage varies by cohort and is not converted to zero. Defensive box coverage rises only after official steals/blocks introduction. Every candidate retains coverage rates by debut-era group.

Active-to-cutoff careers carry `TO_DATE_NO_PROJECTION`. Peak is valid to date; Longevity, Accolades, and Winning remain incomplete to date. No completion penalty or projection is applied.

## Weight sensitivity and rejection

Monte Carlo sampled ordering stability ranges from 0.830 to 1.000. No candidate crosses the predeclared instability rejection threshold of 0.75. Modern advanced Defense is the most weight-sensitive tested formulation and also has the widest median player percentile IQR (0.236). Playoff change, five-year Peak, single-season Peak, modern offense, box Defense, single-season Era Dominance, and role-aware Winning show the next-largest sensitivity and remain cautioned.

Rejected: `PEAK-C` (coverage), `DEFENSE-B` (near duplicate), `PLAYOFFS-B` (coverage), and `PLAYOFFS-E` (near duplicate). Deferred: `OFFENSE-D` and `DEFENSE-C` (modern-era dependency). Thirty-two candidates remain `VALIDATED_FOR_EXPERIMENT`; none is `FINAL`.

## Reproducibility

The build uses no network. Generated diagnostic Gold is partitioned by candidate, ignored by Git, and hash-cataloged in `dimension-candidate-summary.json`. A second run with the expected fingerprint must reproduce all Parquet hashes, the registry, and committed audit reports exactly.

## Limitations

- Equal and random weights are sensitivity devices, not value judgments.
- Correlation does not prove conceptual identity; it identifies shared empirical signal.
- Candidate-scoped PlayerAwards coverage prevents universal accolade completeness.
- Early Defense remains intrinsically limited by factual source history.
- Career-universe scaling depends on the explicitly labeled reference population.
- PCA, factor analysis, clustering, final selection, and all player rankings remain deferred.
