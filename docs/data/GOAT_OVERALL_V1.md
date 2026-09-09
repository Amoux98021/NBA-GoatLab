# GOATLab Overall V1

## Scope

`goatlab-v1-overall-v1` combines the seven frozen `goatlab-v1-dimension-scores-v1` scores. It does not change any STEP-0014 formula. The build is offline, uses `GOATLAB-HIST-V1`, and contains no external-ranking target, projection, era quota, positional quota, or player-specific adjustment.

## Default formula

`Overall = .17 Peak + .14 Longevity + .16 Offense + .14 Defense + .18 Playoffs + .10 Accolades + .11 Winning`

The arithmetic architecture is deliberately identical to the future slider model. All seven inputs must exist; an unavailable input produces no official Overall score and the missing weight is not redistributed.

Candidate A is equal nominal weighting. Candidate B emphasizes the stated constitutional hierarchy. Candidate C adjusts for observed redundancy while keeping a transparent round-number vector and is selected. Candidate D is a fixed-seed search result minimizing effective-influence concentration plus descriptive era/profile mean spread inside the prior admissible bands. Candidate D is diagnostic because its optimized decimals and objective tradeoff are less interpretable than C.

## Eligibility

There are 1,882 complete profiles. Of 2,963 `NOT_QUERIED` Accolades players, 303 have the other six scores. Setting Accolades to 100 for each and testing 10,000 admissible vectors plus candidates A–D yields zero potential Top-100 crossers and zero players within the five-point review buffer. The closest optimistic case remains 15.23 points below its paired cutoff. The remaining 2,660 unknown-award players also lack another required dimension and remain review-required rather than zero-award.

No network request or award-source mutation was needed. Confirmed `SUCCESS_EMPTY` and `NOT_QUERIED` remain distinct.

## Effective influence

Exact Shapley variance influence under the default is Peak 20.72%, Longevity 16.56%, Offense 17.07%, Defense 11.07%, Playoffs 18.77%, Accolades 8.13%, and Winning 7.68%. Direct basketball performance accounts for 84.20% effective variance, Peak/Longevity for 37.28%, and recognition/outcome for 15.80%. These are empirical variance shares on the 1,882-player eligible population, not additional weights.

## Stability

Across 10,000 fixed-seed admissible vectors, Spearman correlation to the default ranges from 0.9946 to 0.9999. Median Top-10/25/50/100 overlap is 1.00/0.92/0.96/0.95; minimum overlap is 0.90/0.84/0.90/0.92. Local ±1, ±2.5, and ±5 percentage-point perturbations retain minimum Spearman 0.9979 and minimum Top-100 overlap 0.93. Player-level intervals describe sensitivity and never alter the official rank.

Leave-one-out diagnostics show each dimension has ranking effect. Defense and Playoffs have the largest removal effects (Top-100 overlaps 0.82 and 0.90); removing Accolades or Peak retains 0.96 and 0.97. This reflects both nominal weight and covariance, not a recommendation to delete any constitutional dimension.

## Era, archetype, and active careers

All score inputs are era-normalized, and no era receives a quota. Eligible-population mean scores vary by debut cohort (52.0 for 2020s through 63.8 pre-1960), partly reflecting selection into the complete-profile population and incomplete to-date modern careers. This remains a limitation to monitor, not a target to equalize. Every dimension-profile archetype has rankable observations; historical position coverage remains unqualified and is not asserted.

Active players use `TO_DATE_NO_PROJECTION`. Their accomplishments through 2025-26 count normally; future longevity, awards, games, and titles are never projected.

## Outputs and interpretation

Generated ignored Gold includes all-player eligibility/score rows, the official internal Top 100, four candidate rankings, and player-level sensitivity metadata. Committed JSON/YAML reports preserve the Top 100, methods, audits, and fingerprints.

The ranking is a deterministic consequence of the frozen dimensions and declared weights. Surprising placements are not manually corrected. It is an internal V1 methodology output, not a claim that one definition objectively resolves the GOAT debate.

