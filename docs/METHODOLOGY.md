# Methodology

## Research position

GOAT Lab models multiple definitions of basketball greatness; it does not assert that one statistical or machine-learning procedure can establish an objective GOAT. Ranking formulas and ML are out of scope for Phase 1.

## Data principles

1. Source facts and GOAT methodology are separate concerns.
2. Every canonical fact retains source provenance.
3. Internal identifiers, not player names, are relational keys.
4. Historical absence is not performance: `NULL != 0`.
5. Coverage eligibility is explicit and metric-specific.
6. Transformations should be deterministic and tested.
7. Source-specific names end at the ingestion/canonicalization boundary.

## Layer contract

- Bronze stores source-faithful data and retrieval metadata.
- Silver stores canonical entities and basketball facts without opinions or GOAT weights.
- Gold will store versioned derived features, era normalization, dimension scores, and model-ready inputs.

This living summary may be extended, but methodology changes must also receive a permanent step record and an ADR when material.

## Silver schema V1 policy

- Season start year is the canonical `season_id` and labels use `YYYY-YY`.
- Canonical entity identifiers are deterministic UUIDv5-derived strings governed by ADR-0005; names are never relational keys.
- Season types use a closed canonical vocabulary. Provider synonyms are normalized before duplicate resolution.
- Player-season traditional and advanced facts are separate tables with team-specific and total-season row scopes.
- Traditional/advanced fields are nullable. A nullable value is interpreted only with `metric_coverage`; it is never automatically zero.
- The acquired nbadb v238 bundle cannot populate player game, player season, advanced, or award facts.
- Under ADR-0006, official NBA Stats is the audited player-fact source. `PlayerGameLogs` is the preferred player-game input; official Base/Totals is used from its empirical 1996-97 boundary, while earlier season totals may be deterministically aggregated from official game facts after metric-specific coverage validation.
- NBA's documented statistic-introduction dates and empirically observed endpoint behavior are separate evidence. A pre-introduction placeholder (including zero) maps to NULL, not an observed performance value.
- Raw NBA responses and request metadata are Bronze. Canonical mappings use stable NBA player/game business keys, quarantine source conflicts, and never join on a name.

## Player-fact qualification and aggregation V1

- Endpoint success and column presence do not establish metric reliability. STEP-0005 qualifies each canonical metric for each season, season type, and source endpoint.
- Empirical coverage labels are `RELIABLE` (at least 99% non-null), `PARTIAL` (80% to less than 99%), `SPARSE` (above 0% to less than 80%), `UNAVAILABLE` (historically or contractually inapplicable), and `UNKNOWN` (no usable observation despite conceptual applicability). Thresholds are configurable, conservative V1 methodology governed by ADR-0007.
- Observed-zero percentage is calculated over non-null observations. Missing observations never enter its denominator and never become zeros.
- A player-season metric is aggregated only when its source partition is `RELIABLE` and all contributing rows for that player/group are non-null.
- TEAM rows retain team-specific facts. A single TOTAL row combines qualified appearances across teams for player × season × season type. `games_played` counts distinct official game appearances.
- Shooting percentages use summed makes divided by summed attempts only when the attempt denominator is positive. Per-game values use qualified `games_played`; unavailable totals or denominators produce NULL.
- Official numeric player, team, and game identifiers are source business keys. Team name supplies version evidence, never the primary join. Stale legacy windows are reported but cannot invalidate official player facts.
- Contradictory source rows remain unchanged in Bronze and enter an explicit quarantine rather than an automatic repair path.

## Frozen historical corpus V1

- `GOATLAB-HIST-V1` freezes 1946-47 through 2025-26 for `REGULAR` and `PLAYOFF`. It contains 80 seasons and excludes every later season.
- The frozen identity includes the request matrix, source/client versions, canonicalization timestamp, schema and methodology versions, per-partition hashes, and aggregate corpus fingerprint. It is governed by ADR-0008.
- Future current-season refreshes must use separate versioned outputs. Neither new games nor upstream corrections may silently mutate this research release.
- All 280 intended bulk scopes are checkpointed independently. Successful cache entries and output partitions survive later failures; API failure is never interpreted as an empty result.
- Full-history identity and team enrichment cannot change an already assigned canonical ID merely because more metadata becomes available.
- Reconciliation blocks the corpus when a field has at least a 1% mismatch rate or mismatches in at least three partitions. Rounding-tolerance matches are reported separately from exact matches.
- Quality reporting distinguishes `SOURCE_ANOMALY` from `PIPELINE_ERROR`. Source-faithful Bronze remains untouched; contradictory source rows are quarantined before Silver without repair.
- The complete V1 coverage matrix preserves the ADR-0007 thresholds. It is eligibility evidence for later research, not a GOAT feature or score.

## Era normalization V1

- era-normalized-player-season-v1 is an offline Gold derivation of immutable GOATLAB-HIST-V1; every output records corpus ID/fingerprint and methodology version.
- Comparison populations use TOTAL rows only and never mix season types. Regular Season qualification is games >= max(5, ceil(20% × team-opportunity games)); Playoffs use games >= max(2, ceil(10% × team-opportunity games)). All excluded rows remain and are labeled.
- Opportunity uses the maximum distinct games played by a team, allowing shortened-season scaling without incomplete minutes.
- Standard z-score uses population standard deviation. Robust z-score is 0.6744897501960817 × (value - median) / MAD. Percentiles use midrank ties in [0,1].
- Ratio indexes require a positive, meaningful league reference. Shooting references use aggregate qualified makes/attempts; TS uses points and FGA + 0.44 × FTA.
- Every source metric must be RELIABLE. Per-36 additionally requires at least 99% positive player-game minutes; per-75 requires at least 99% positive official Advanced/Totals possessions. No pre-1996 possession or pace reconstruction is allowed.
- Early placeholder zeros make per-36 unavailable even when a raw minute field exists.
- Gold NULL carries eligibility metadata. Zero variance, zero MAD, missing inputs, invalid references, unavailable possessions, and coverage failure remain distinct.
- Long Gold is the authoritative feature/provenance representation. Wide Gold is ergonomic and cannot redefine the registry.
- Primitive metrics remain separate; no Offense, Defense, Peak, Longevity, playoff impact, award, winning, or GOAT composite is created.

## Career trajectory and peak/longevity primitives V1

- career-trajectory-peak-longevity-v1 derives only from frozen STEP-0007 Gold, Silver participation facts, and fingerprinted identity evidence.
- Player careers are ordered separately by season type. Every season between first and last appearance is materialized; a missed season is a gap and breaks contiguity.
- A valid N-year peak requires N consecutive observed, qualified, feature-available seasons. Quality and availability-adjusted 1/3/5-year peaks remain separate under ADR-0011.
- Availability adjustment shrinks each season toward its normalization baseline by games/opportunity: 0 for z, 0.5 for percentile, and 100 for relative index.
- Best three/five season sets are explicitly NON_CONTIGUOUS and cannot be described as three-year/five-year peaks.
- Elite thresholds remain plural at 80th, 90th, 95th, and 99th percentile. Missed and below-threshold seasons break a prime run.
- Cumulative positive z and percentile area above 0.50/0.80/0.90 are descriptive alternatives. Opportunity-weighted variants remain separate and none is named career value.
- Active careers are observed through the 2025-26 cutoff without projection. Completion can remain indeterminate.
- Age is calculated on February 1 of the ending calendar year only for audited birth dates; missing age is never inferred.
- Award candidate flags are broad acquisition-planning evidence only and never remove a player from the master corpus.
- No metric categories are combined into a final Peak, Longevity, Playoff, or GOAT score.

## Official awards and accolades V1

- `official-player-awards-canonical-v1` queries only the broad 2,140-player STEP-0008 acquisition universe while retaining all 5,103 identities.
- `SUCCESS_EMPTY` is observed no rows; `NOT_QUERIED` is no claim. Gold counts are zero only for successfully queried players and NULL otherwise.
- Official numeric `PERSON_ID` is the only source identity key. Integral-float serialization is normalized mathematically; names cannot repair identity.
- Exact observed descriptions map through a versioned registry. Every raw field and any future unknown description remains preserved.
- All-NBA/All-Defense/All-Rookie levels use structured team number. Calendar-only event labels remain unjoined to NBA seasons.
- All-Star coverage is `PARTIAL`; statistical titles are `REQUIRES_SEPARATE_SOURCE` and should be derived from frozen facts later.
- Silver stores events. Gold stores factual counts. No event is weighted and no accolade score exists.

## Team success and postseason V1

- `team-success-postseason-v1` is an offline derivation from frozen `GOATLAB-HIST-V1` plus fingerprinted STEP-0009 award evidence. It does not mutate the corpus.
- Regular and playoff W/L derive from isolated canonical game evidence. Complete legacy game partitions are preferred; already frozen NBA API game evidence fills 23 missing legacy partitions after exact 2022-23 overlap validation.
- Champion and runner-up derive from the unique chronologically final playoff game. The complete Finals set is every playoff game between those team IDs. Official NBA history validates champion, runner-up, and series result for all 80 seasons without overwriting derived facts.
- Postseason formats are qualified under ADR-0015. Modern round labels start only with the standard 1983-84 bracket. Opponent-pair series facts are available in 79 seasons and blocked for the 1953-54 round-robin/mixed structure.
- Regular W/L remains valid when source team-point sums conflict with recorded outcomes. Point-differential context is withheld, not repaired, for 1960-61, 1970-71, 1975-76, and 1976-77.
- Player outcomes join at player × team × season before career aggregation. Regular champion membership, champion playoff participation, champion Finals participation, and official champion award evidence remain distinct.
- Award evidence is NULL for `NOT_QUERIED`; it is never interpreted as no championship event. Team championships never derive from candidate-scoped awards.
- Game share and coverage-qualified minute share are factual opportunity proxies. Minute shares require RELIABLE empirical coverage and at least 99% positive observations. No role label or credit score is created.
- Team ranks, percentiles, z-scores, career team context, and participation counts remain separate descriptive primitives. No Winning, team-success, championship-value, or rings composite exists.

## All-Star and statistical-leader fact completion V1

- `all-star-stat-leader-facts-v1` retains All-Star event-game roster listing, actual game participation, and candidate-scoped PlayerAwards evidence independently under ADR-0017.
- All-Star begins in 1950-51. Pre-introduction seasons are `NOT_APPLICABLE`; 1998-99 is `NO_GAME_HELD`. Multiple modern event games are preserved rather than collapsed into East/West assumptions.
- Official box-score V3 rows establish `OFFICIAL_EVENT_GAME_ROSTER`, not universally original selection or replacement status. Blank source placeholders are quarantined rather than assigned player identities.
- LeagueLeaders `RANK=1`, frozen raw per-game/total maxima, and STEP-0007-qualified leaders remain separate under ADR-0018. Current qualification rules are not retroactively applied.
- PTS/AST applicability begins in 1946-47, REB in 1950-51, and STL/BLK in 1973-74. A derived qualified leader additionally requires `RELIABLE` empirical metric coverage.
- `NOT_QUERIED` PlayerAwards absence remains NULL even when league-wide roster or participation evidence exists. League-wide evidence includes players outside the former candidate universe.
- Career outputs use exact evidence-family names. No ambiguous All-Star count, official-title inference, accolade value, or composite score is created.

## GOAT dimension candidate audit V1

- `goat-dimension-candidates-v1` consumes frozen factual and primitive layers without mutating Silver or previous Gold.
- All 5,103 players remain. The 2,656-player broad high-recall population is a diagnostic scaling reference, not ranking eligibility.
- The audit evaluates 38 definitions across Peak, Longevity, Offense, Defense, Playoffs, Accolades, Winning, and Era Dominance. Every value is labeled by candidate, scale, missingness policy, coverage, and methodology.
- Component scales are career-universe midrank percentile, robust standardization (`1.4826 × MAD`), population z-score, and right-continuous empirical CDF. Ties remain tied; extremes are not clipped.
- Missingness policies are core-only, available-feature renormalization, two-thirds coverage threshold, and era-specific enrichment. Missing evidence is never zero, average, or synthetic.
- Coverage confidence is `STRONG`, `MODERATE`, `LIMITED`, or `UNAVAILABLE`; it describes evidence, not performance, and applies no automatic penalty.
- Primitive ownership is explicit. Raw-evidence separation is the default future experimental policy: box performance, award events, playoff performance, and team outcomes retain distinct primary homes.
- Equal weights are only a baseline. Each multi-input candidate receives 200 deterministic uniform-simplex samples with seed 120012; score/percentile variance, IQR, and ordering stability are reported.
- Modern-only offense and defense are deferred from universal comparison. Five-year Peak and contiguous playoff Peak fail broad coverage; two augmented candidates fail near-duplicate checks.
- Cross-dimension correlations are findings, not optimization targets. Peak/Era and Longevity/Era overlap is substantial enough that Era Dominance cannot be assumed independent.
- Active careers are to-date with no projection or completion penalty. No candidate is final and no overall player ordering exists.

## Unsupervised structural validation V1

- `unsupervised-structural-validation-v1` consumes only frozen, fingerprinted Gold/Silver evidence and uses no network, external ranking, supervised target, GOAT score, or Top 100.
- Candidate, cross-era primitive, modern-enriched, magnitude, and profile-shape matrices remain separate. Every model uses an explicit complete intersection; missing historical evidence is never imputed.
- Standard and robust scaling are compared. PCA uses SVD and fixed-seed parallel analysis; factor analysis uses iterated principal axes with Varimax. Component signs and cluster IDs carry no quality order.
- Stability includes bootstrap loading alignment, subspace similarity, factor-loading stability, population/scaling sensitivity, active-career exclusion, seed/bootstrap ARI/AMI, and method agreement.
- Archetypes use row-centered/RMS-scaled profiles so magnitude alone cannot define groups. The selected two-cluster result is a coarse diagnostic because GMM and hierarchical agreement is limited.
- Era Dominance is recommended as a diagnostic over already normalized evidence, not an independent additive vote. The non-final shortlist retains 18 candidates across seven conceptual families.
- All pruning outcomes remain experimental and use coverage, lineage, residual uniqueness, component structure, and interpretability together; correlation alone is not a rejection rule.
