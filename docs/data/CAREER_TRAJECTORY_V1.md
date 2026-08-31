# Career trajectory, peak, prime, and longevity primitives V1

## Scope

STEP-0008 derives descriptive career Gold from GOATLAB-HIST-V1 and era-normalized-player-season-v1. It uses no network, does not mutate Silver or STEP-0007 Gold, and produces no final Peak, Longevity, Playoff, or GOAT score.

Inputs:

- Corpus fingerprint: 283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c
- Normalization fingerprint: a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852
- Career methodology: career-trajectory-peak-longevity-v1

## Career sequencing and participation

Every frozen player has one career summary. Trajectories are separate by season type and include explicit gap rows between first and last appearance. season_number measures elapsed NBA seasons in the span; appearance_number advances only on appearances.

The 5,103 careers average 5.04 Regular Season appearances, 4.40 qualified Regular Seasons, and 272.34 games. Medians are three appearances, three qualified seasons, and 130 games. Playoff careers average 2.30 appeared seasons, 2.10 qualified seasons, and 18.02 games; medians are one, one, and three.

Career status is evidence-qualified: 582 ACTIVE_TO_CUTOFF, 4,250 SOURCE_CONFIRMED_COMPLETE, and 271 INDETERMINATE. Active careers are accomplishments through 2025-26 only.

## Metric career summaries

For each player, season type, STEP-0007 metric, and normalization method, Gold records available qualified season count, distribution statistics, best season, top three/five values, explicitly non-contiguous best-three/best-five sets, cumulative measures, elite counts where applicable, and provenance.

Of 519,360 metric-normalization summaries, 347,420 are AVAILABLE and 171,940 are UNAVAILABLE_NO_QUALIFIED_VALUES. Unavailable combinations retain NULL values. Bill Russell's SPG primitives, for example, are unavailable rather than zero.

## Contiguous peaks

A valid window contains every expected consecutive NBA season and each season must be appeared, qualified, and feature-available.

| Window | Valid quality records | Valid availability-adjusted records |
|---|---:|---:|
| 1 year | 347,420 | 347,420 |
| 3 years | 177,472 | 177,472 |
| 5 years | 110,971 | 110,971 |

Across all 3,116,160 peak records, 1,271,726 are available, 812,794 fail contiguous completeness, and 1,031,640 have no qualified feature value. Invalid windows remain explicit with NULL values.

QUALITY averages normalized season values. AVAILABILITY_ADJUSTED shrinks each season toward the method's league baseline by games/opportunity before averaging. The adjusted choice changed the selected PPG peak for 18.39% of eligible one-year, 18.12% of three-year, and 16.26% of five-year comparisons. APG changes were 27.43%, 23.91%, and 25.68%; TS% changes were approximately 12%.

## Prime and longevity primitives

Percentile thresholds remain plural: 80th, 90th, 95th, and 99th. Each player/metric/season-type record carries count, career proportion, first/last qualifying season, longest consecutive run, run span, mean/minimum percentile, mean z where available, and games. A missed or below-threshold season breaks the run.

Unique players with at least one qualifying season in any available metric:

| Threshold | Regular Season | Playoffs |
|---|---:|---:|
| 80th | 3,133 | 2,382 |
| 90th | 2,596 | 2,092 |
| 95th | 1,930 | 1,506 |
| 99th | 815 | 535 |

Metric-specific cumulative primitives include sum of positive standard z, games/opportunity-weighted positive z, and area above percentile baselines 0.50, 0.80, and 0.90 with unweighted and weighted variants. These have different longevity/elite-season biases and none is named career value.

Late-career persistence is the count of 80th-percentile seasons among the final five observed appearances for the same metric/type. It is descriptive, not age-imputed.

## Age coverage

Audited birth dates support age features for 3,612 players (70.78%); 1,491 remain unavailable. Age is measured on February 1 of the season-ending year and appears on best-season and peak-window records only when supported. No age feature is imputed.

## Playoffs

Playoff trajectories, metric summaries, non-contiguous best-season sets, elite counts, cumulative dominance, and prime runs are separate from Regular Season. Peak rows retain games and opportunity metadata. A short run is not assigned the same sample size as a long run, and no Playoff Score is created.

## Candidate universes for STEP-0009

All 5,103 players remain in the master corpus.

| Proposal | Players |
|---|---:|
| At least 3 qualified Regular Seasons | 2,574 |
| At least 5 | 1,891 |
| At least 8 | 1,227 |
| At least 10 | 867 |
| Any core metric season at 90th percentile | 1,491 |
| Any core metric season at 95th percentile | 984 |
| At least two core metrics reaching 90th percentile | 756 |
| Union: 3 qualified or core 95th | 2,617 |
| Union: 5 qualified or core 90th — recommended | 2,140 |
| Union: 8 qualified or core 90th | 1,767 |

The recommended 2,140-player union is deliberately broad and controls only player-scoped award acquisition. It is not a ranking or permanent eligibility filter.

## Physical outputs and reproducibility

Generated, Git-ignored Parquet is bucketed deterministically into 32 player buckets for each entity:

- player_career_summary: 5,103 rows
- player_career_trajectory: 42,886 rows
- player_career_features: 519,360 rows
- player_peak_windows: 3,116,160 rows
- player_prime_runs: 519,360 rows

The 160 partitions occupy 68,583,568 bytes. A second full offline execution reproduced output fingerprint 5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b exactly in 153.97 seconds.

## Limitations

- Qualification and feature eligibility are inherited from STEP-0007.
- Sparse early statistics can support PPG peaks while blocking efficiency or defensive peaks.
- Playoff qualification does not eliminate small-sample uncertainty; games remain attached for later modeling.
- The legacy active flag and identity birth-date surface are incomplete/stale, so status and age remain qualified.
- Opportunity adjustment is one transparent durability primitive, not an endorsed definition of peak.
- No awards, team success, composite dimension, overall ordering, or ML target exists here.
