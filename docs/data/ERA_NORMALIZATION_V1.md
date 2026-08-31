# Era normalization V1

## Purpose and scope

STEP-0007 transforms frozen GOATLAB-HIST-V1 Silver facts into coverage-aware Gold league context and primitive player-season features. It does not score greatness, combine metrics, rank players, or optimize against conventional player ordering.

The offline build verifies the frozen corpus ID, 2025-26 cutoff, aggregate fingerprint, and all 380 Silver partition hashes. The input fingerprint is 283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c; feature methodology is era-normalized-player-season-v1.

## Qualified comparison population

Only canonical TOTAL player-season rows participate, and season types are independent. Opportunity is the greatest distinct game count for any team in the partition.

| Season type | Selected rule |
|---|---|
| Regular Season | games_played >= max(5, ceil(20% × opportunity games)) |
| Playoffs | games_played >= max(2, ceil(10% × opportunity games)) |

All players remain in Gold. Non-qualified observations retain NOT_QUALIFIED and a reason. ADR-0009 and qualification-sensitivity-analysis.json govern the choice.

## Normalization definitions

- Standard z-score uses the qualified population mean and population standard deviation (ddof=0).
- Robust z-score is 0.6744897501960817 × (value - median) / MAD.
- Percentile uses midrank ties: (values below + 0.5 × equal values) / population size, yielding [0,1].
- Relative index is 100 × value / league reference only when the ratio is meaningful and the reference is positive.

Zero standard deviation, zero MAD, invalid denominators, missing player inputs, and ineligible coverage remain NULL with status metadata. Extreme valid results are not clipped.

## Coverage and rate policy

ADR-0007 RELIABLE coverage is the base gate. Column presence is insufficient.

- Per game requires a qualified numerator and positive games.
- Per 36 requires qualified totals, RELIABLE player-game minutes, and at least 99% positive minute observations. This exposed early placeholder zeros and limited per-36 to 100 of 160 partitions.
- Per 75 uses 75 × total / official advanced possessions only when at least 99% are positive. It is available in 60 partitions from 1996-97 and never estimated earlier.
- TS% uses PTS / (2 × (FGA + 0.44 × FTA)); eFG% uses (FGM + 0.5 × FG3M) / FGA. Required inputs must be reliable.

League pace is an official player-minutes-weighted Advanced/Totals context in the same 60 partitions. Average team possessions is NULL because V1 has no canonical team-possession fact. Team scoring context is withheld in 18 partitions with source-game quarantine rather than representing an incomplete aggregate as league complete.

## Physical outputs

Generated deterministic Parquet is ignored by Git:

- data/gold/league_season_context/season=YYYY/season_type=.../part-00000.parquet
- data/gold/player_season_feature_long/season=YYYY/season_type=.../part-00000.parquet
- data/gold/player_season_normalized/season=YYYY/season_type=.../part-00000.parquet

There are 160 partitions per entity, 480 total, covering 37,472 TOTAL player-seasons. Long Gold has 599,552 rows (16 definitions per player-season). Wide Gold offers common features without replacing the long provenance contract.

## Availability summary

| Feature | Available season/type partitions |
|---|---:|
| Games played, PPG | 160 each |
| FT% | 157 |
| RPG | 110 |
| FG%, TS% | 109 each |
| APG | 105 |
| Minutes, points/rebounds per 36 | 100 each |
| Assists per 36 | 99 |
| eFG% | 92 |
| 3P% | 89 |
| SPG, BPG | 87 each |
| Points per 75 | 60 |

Availability is empirical and not necessarily continuous. The eligibility matrix has one row for every season × season type × feature × normalization method.

## Validation and reproducibility

Mathematical checks span 1961-62, 1971-72, 1984-85, 1990-91, 1999-00, 2008-09, 2012-13, 2015-16, 2021-22, and 2023-24. Across 263 eligible groups, qualified z-score means were zero at recorded precision and standard deviations one. Percentile ordering, bounds, partition isolation, provenance, TOTAL-row usage, finite-value, orphan, duplicate, leakage, and NULL-preservation checks had zero failures.

The second fixed-input execution reproduced all 480 partition hashes and output fingerprint a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852 without network access.

## Interpretation limits

Case studies are diagnostics, not rankings. A player can be extraordinary in an available metric while other metrics correctly remain unavailable. Per-game, per-minute, and per-possession rates answer different questions. Later composite methodology must consume eligibility metadata and must not coerce NULL into zero.
