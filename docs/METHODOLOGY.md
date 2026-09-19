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

## Constitutional dimension scores V1

- `docs/constitution/GOATLAB_V1_CONSTITUTION.md` is the machine-facing binding V1 Constitution. `goatlab-v1-dimension-scores-v1` is its versioned scoring implementation.
- Seven dimensions are operational: Peak, Longevity, Offense, Defense, Playoffs, Accolades, and Winning. Era Dominance remains diagnostic and is not an eighth additive score.
- Each dimension's final value uses a midrank ECDF on a 0–100 scale against the frozen 2,656-player `BROAD_HIGH_RECALL` reference population. This is outlier-resistant and ordinal; it is not raw min-max scaling.
- Peak is 70% best complete contiguous three-season quality and 30% apex. Longevity is 35% P80 breadth, 40% capped P80–P90 area, and 25% longest P80 run. All-NBA calibrates the P80 threshold but never enters the Longevity score.
- Offense combines scoring volume and efficiency before joining creation, then uses qualified Regular Season career evidence. Defense triangulates Regular Season team suppression and coverage-qualified recorded actions; DPOY and All-Defense are excluded.
- Playoffs is individual postseason evidence led by absolute quality. Winning is participation-conditioned team evidence with one mutually exclusive highest outcome tier per season. The two dimensions share no outcome/performance signal.
- Accolades separates Major Honors and Sustained Recognition, bundles related within-season evidence, caps related cross-axis stacking, and assigns only 5% support to statistical leaders. NBA Champion events are excluded.
- Required anchors block a score. Permitted optional-evidence renormalization is explicit and produces partial coverage; NULL and `NOT_QUERIED` never become zero.
- Confidence describes coverage, relevant seasons, and sample only. It does not multiply or otherwise penalize the dimension score. Active careers are to-date through 2025-26 without projection.
- Recorded defensive actions pass a portable/action bridge. Modern per-75 Offense and advanced Defense remain diagnostics and never change the universal score.
- No official Overall score or weights exist in STEP-0014. Cross-dimension correlations and random-simplex combinations exist solely to inform a later effective-weight audit.

## Overall rating and effective influence V1

- `goatlab-v1-overall-v1` is a weighted arithmetic sum of the seven frozen STEP-0014 scores: Peak 17%, Longevity 14%, Offense 16%, Defense 14%, Playoffs 18%, Accolades 10%, and Winning 11%.
- All seven inputs are mandatory. An unavailable dimension yields NULL Overall and `UNRANKED_INCOMPLETE_REQUIRED_DIMENSION`; no weight is redistributed.
- Candidate selection uses constitutional fidelity, coverage, interpretability, covariance/redundancy, stability, and descriptive cohort fairness. Player names and external rankings are never optimization inputs.
- Exact effective influence uses the Shapley allocation for a linear score: `w_i × Cov(X_i, Overall) / Var(Overall)`. This assigns pairwise covariance symmetrically and sums exactly to total variance.
- Accolades query eligibility uses a maximum-score upper bound across 10,000 fixed-seed admissible vectors and all named candidate methods. `NOT_QUERIED` remains unknown even when the player is safely below every Top-100 cutoff.
- Official ranks use descending score with canonical player ID as the deterministic ordinal tie breaker. Rank sensitivity metadata never changes score or rank.
- Era Dominance, confidence, modern diagnostics, active-career projections, manual bonuses, and player-specific weights are excluded. Active careers are accomplishments through 2025-26 only.
- The internal Top 100 is a reproducible consequence of the declared definition, not an assertion that the GOAT debate has an objective answer.

## Defense V1 forensic audit and V2 counterfactual

- `goatlab-v1-defense-forensic-audit-v1` reproduces all frozen V1 Defense scores exactly and never mutates `goatlab-v1-dimension-scores-v1` or `goatlab-v1-overall-v1`.
- V1 season evidence is 65% team scoring-suppression percentile and 35% coverage-qualified total-rebound/steal/block context. The implemented rebound input is total rebounds, not defensive rebounds.
- Team suppression is a team-season constant (within-team variance 0, ICC 1.0). The final V1 season composite has 89.9% between-team-season variance. This is a material individual-attribution problem under the Constitution.
- Defensive Presence Impact compares opponent-strength-adjusted scoring residuals in games with versus without the player by team-season. It requires 10 games with and five without, uses effective sample `n_with*n_without/(n_with+n_without)`, and shrinks by `n_eff/(n_eff+20)`.
- Insufficient presence evidence is NULL. It does not become zero, and games missed do not enter quality as an additive reward. The estimate is WOWY-style game presence, not lineup RAPM.
- Experimental `goatlab-v1-defense-v2` uses 30% team context, 30% role-aware actions, and 40% stabilized presence. DREB replaces total rebounds when observed; the fallback is explicitly labeled. Role evidence blends 65% global and 35% broad-role rank and does not impose equal final ceilings.
- Modern defensive rating and DPOY/All-Defense remain validation only. The modern relationship is weak for all candidates; award enrichment improves for V2 but is not an optimization target.
- Defense V2 and its frozen-weight Overall result are counterfactual. Promotion requires a later explicit versioned decision.

## Defense V2 promotion audit

- `goatlab-v1-defense-v2-promotion-audit-v1` exactly reconstructs STEP-0015A Candidate B, then masks known Presence evidence to evaluate universal comparability.
- Direct 30/30/40 Candidate B remains a counterfactual. Without Presence, team/action renormalization has 10.72 Defense-point season MAE and changes the construct.
- The expected-Presence experiment is a grouped five-fold ridge using only era-relative team context, role-aware actions, their interaction, and broad role. Awards, postseason, player names, and modern-only metrics are excluded.
- Expected Presence is not promotable: out-of-fold R-squared is 0.0174, direct Presence-percentile MAE is 0.2475, and 49.40% of masked full-score estimates miss by more than 10 points.
- Continuous reliability is `min(1, games_with/10) × min(1, games_without/5)`. It smoothly blends observed Presence into the expected fallback and removes the hard eligibility cliff, but does not make weak fallback evidence informative.
- Confidence is reported separately as `STRONG`, `MODERATE`, `LIMITED`, or `UNAVAILABLE`; it never changes score quality. Expected and reliability-blended seasons carry explicit reason codes.
- STEP-0015B is `PASS + DO_NOT_PROMOTE`. No new official Defense or Overall version is created. Frozen V1 remains unchanged but retains its `REQUIRES_REVISION` constitutional verdict.

## Peak V1 forensic audit and research counterfactual

- `goatlab-v1-peak-forensic-audit-v1` reconstructs frozen Peak V1 without modifying `goatlab-v1-dimension-scores-v1` or `goatlab-v1-overall-v1`.
- V1 season quality is a nested Regular Season construct: Scoring is PPG/TS at 65/35; Offense is the stronger of Scoring/APG at 65/35; Actions is RPG/STL/BLK at 50/25/25; Defense is TeamSuppression/Actions at 65/35; season quality is the stronger of Offense/Defense at 65/35.
- Observed-feature weights renormalize and missing evidence remains NULL. This preserves `NULL != 0` but does not guarantee construct equivalence across evidence regimes.
- Peak remains 70% best complete contiguous three-season season quality plus 30% apex. Gaps and nonqualified seasons invalidate the three-year window; the earliest equal window wins deterministically.
- Games determine qualification and evidence confidence, not season-quality magnitude. Minutes, career duration outside the selected window, postseason, awards, winning, and modern-only evidence do not enter Peak.
- Team suppression is a shared team-season constant with 34.34% mean realized season-quality weight, 30.17% covariance-allocated variance share, and the largest component leave-one-out error. Frozen Peak V1 is therefore classified `REQUIRES_REVISION`.
- `goatlab-v1-peak-v2-research` is a non-promoted counterfactual: require both season Offense and role-aware individual action evidence, combine stronger/secondary at 65/35, and retain the 70/30 Peak window. It cannot replace V1 because historical defensive-action/role coverage is insufficient and actions do not represent total defensive impact.
- ADR-0031 preserves V1 as the reproducible baseline and requires a later evidence-regime-calibrated season-value promotion audit.

## Player-season value measurement audit

- `goatlab-v1-player-season-value-audit-v1` defines the target as overall Regular Season
  individual basketball value for one player-season. It is infrastructure for Peak/Longevity, not
  an eighth dimension.
- Empirical evidence regimes are determined row by row from observed TS, creation, rebound,
  steal/block, role-aware action, and Presence channels. No date-based availability is invented.
- The retained research candidate builds scoring from PPG/TS, uses a 60/40 stronger/secondary
  scoring-creation offense, and a defensive measurement with 10% team context, up to 35%
  continuously reliability-weighted observed Presence, and remaining weight on individual action
  evidence. Offense and defense combine at bounded 55/45 stronger/secondary weights.
- Total team-context weight is at most 5.5%. Confidence is derived separately from regime,
  Presence reliability, role metadata, and games; it never multiplies quality.
- Missing Presence is not zero or an inferred observation. Unused Presence weight remains on
  weaker individual action evidence for research masking, and the resulting construct error is
  measured explicitly.
- The selected candidate is `goatlab-v1-player-season-value-v2-research`, not production. It covers
  73.81% of rows, cannot score the early mask, and has 5.73/8.48-point MAE under no-Presence and
  traditional-box masks. The expected-Presence bridge remains invalid at OOF R-squared 0.0174.
- Peak 70/30 and Longevity 35/40/25 architectures are held fixed in diagnostic counterfactuals.
  Published V1 dimensions, Defense, and Overall are unchanged.

## Historical evidence bridge audit

- `goatlab-v1-historical-evidence-bridge-audit-v1` reconstructs all 22,457 STEP-0015D rows and
  16,576 research scores with zero difference, then tests missing-channel recovery without
  changing Candidate D or any published V1 output.
- Creation bridges use player-grouped and decade-blocked ridge models. PPG-only creation reaches
  R-squared 0.5043 and Spearman 0.7097; adding TS reaches R-squared 0.5313. Neither identifies
  observed APG well enough to replace it.
- Defensive tests compare actions, bounded team context, Presence, and an interpretable one-factor
  measurement model. The factor explains 36.51% of channel variance and has materially unstable
  decade loadings, so it is not measurement invariant.
- Full-evidence seasons are masked into expanded, traditional, early-with-Presence, and
  early-minimal regimes. Their PlayerSeasonValue MAEs are 7.27, 8.00, 8.41, and 11.35 points;
  no regime passes every predeclared point-score gate.
- Partial-identification intervals preserve unknown quality without converting it to zero. Mean
  90% widths range from 26.92 to 42.30 points. An interval midpoint is diagnostic, not an official
  score.
- STEP-0015E is `PASS + NO_VALID_BRIDGE`. Full Candidate D research scores, interval-only sparse
  estimates, and unavailable rows remain distinct. Peak, Longevity, Defense, and Overall are not
  promoted or overwritten.

## Historical factual player-season recovery audit

- `goatlab-historical-data-recovery-audit-v1` first reproduces STEP-0015E's exact sparse-evidence
  counts, then audits whether each NULL is historically unrecorded, absent from the selected bulk
  source, exactly derivable, conflicting, or currently unavailable.
- The official NBA Stats `PlayerCareerStats` `SeasonTotalsRegularSeason` result is acquired for the
  deterministic set of players with any qualified pre-1996 Candidate D season. Official NBA
  `PLAYER_ID` is the only primary join key; names are diagnostic.
- A source TOTAL row is mandatory for traded seasons. Otherwise only a single-team row is accepted.
  Multi-team seasons without a total are rejected rather than speculatively summed.
- Official player-career season totals take precedence over conflicting pre-1996 bulk
  `PlayerGameLogs` aggregates only in the versioned research artifact. The frozen corpus and every
  V1 score remain unchanged; disagreements are retained and never averaged.
- Historical introduction guards are authoritative. Rebounds before 1950-51, minutes before
  1951-52, OREB/DREB/STL/BLK before 1973-74, and turnovers before 1977-78 remain NULL even if an
  endpoint exposes placeholder values.
- Per-game statistics and shooting percentages are exact derivations from observed totals. TS is
  the standard `PTS / (2 * (FGA + 0.44 * FTA))` estimate. It is labeled derived and retains a
  historical free-throw-rule comparability caveat; it is not a reconstructed possession fact.
- Recovered observations are rerun through the unchanged Candidate D, fixed 70/30 Peak, and fixed
  35/40/25 Longevity architectures. This isolates data recovery from methodology changes and does
  not promote any counterfactual.

## PlayerSeasonValue V2 recalibration and promotion audit

- `goatlab-v1-player-season-value-v2-promotion-audit-v1` exactly reconstructs the recovered
  Candidate D research output before testing production suitability.
- Candidate D remains: PPG/TS scoring; 60/40 stronger/secondary scoring-creation offense; defense
  with 10% team context, up to 35% continuously reliability-weighted observed Presence, and the
  unused Presence share retained on actions; then 55/45 stronger/secondary offense-defense.
- Official PlayerCareerStats and frozen source conflicts are never averaged. A source-choice
  counterfactual reranks every affected season and quantifies score sensitivity.
- Actual factual coverage and artificial masking robustness are separate tests. Recovery raises
  observed coverage to 21,107/22,457 seasons, but 6,420 scored seasons still use traditional-box
  or expanded-box/no-Presence defensive evidence.
- Missing STL/BLK, missing Presence, missing team context, and historically unavailable rebounds
  remain NULL with explicit regimes and confidence. Confidence never multiplies quality.
- Candidate D is not promoted because the actual non-full regimes retain 7–8 point controlled
  masking MAE. No official PlayerSeasonValue, Peak, Longevity, or Overall version is changed.

## PlayerSeasonValue measurement linking and uncertainty

- `goatlab-v1-player-season-value-measurement-linking-audit-v1` treats each factual evidence
  regime as a measurement form of the frozen Candidate D research instrument.
- `FULL_PORTABLE` is the reference form, not basketball truth. Weaker forms are created by masking
  the same full-evidence player-season, so linking does not rely on equal actual-era talent
  distributions.
- Linear, equipercentile, isotonic, and optional broad-role isotonic linkers are evaluated with
  player-grouped, random, leave-decade-out, and directional era-transfer validation. A linker maps
  an observed form score; it never predicts a missing basketball statistic.
- Split-conformal 80/90/95% intervals use disjoint player-grouped fit, calibration, and test folds.
  Confidence and interval width never multiply or penalize quality.
- `PROVISIONAL_POINT` requires MAE <= 5, Spearman >= 0.95, absolute overall bias <= 2, major-role
  bias <= 3, at most 15% errors above ten points, and 87%–93% empirical coverage for the nominal
  90% interval. A calibrated form failing a point gate is `INTERVAL_ONLY`.
- Expanded proxy-action and traditional forms with observed Presence, plus the no-Team-Context
  form, pass point gates. No-Presence and sparse offense forms remain interval-only.
- The research status distribution is 14,687 `OFFICIAL_POINT`, 3,831 `PROVISIONAL_POINT`, 3,937
  `INTERVAL_ONLY`, and two `UNAVAILABLE`. These labels do not promote Candidate D.
- Interval-aware Peak and Longevity outputs are diagnostics only. Peak uses correlated draws under
  the frozen 70/30 window; Longevity retains probabilistic P80/P90 evidence pending a dedicated
  aggregation audit.
- **Outcome:** `PASS + LIMITED_TIERED_ARCHITECTURE`; next audit Peak/Longevity uncertainty.

## Peak and Longevity uncertainty propagation

- `goatlab-v1-peak-longevity-uncertainty-audit-v1` consumes the frozen STEP-0015H measurement
  architecture without changing Candidate D or any published V1 output.
- Empirical residual paths retain a player-level component and are sampled within evidence form,
  role, archetype, and score band. Independent season draws are a rejected baseline because
  adjacent and within-player residual dependence is material.
- Peak reselects the best complete contiguous three-season window and apex in every draw, then
  applies the frozen 70/30 weights. Window probability/status never changes quality.
- Longevity calculates exact P80 breadth, capped P80-P90 area, and longest consecutive P80 run in
  every draw, then applies the frozen 35/40/25 weights. P80/P90 remain common fixed thresholds.
- Every draw is mapped through a fixed `BROAD_HIGH_RECALL` ECDF; the reference distribution is not
  redrawn. Active careers are to-date through 2025-26 only.
- Aggregate point gates use MAE, rank correlation, bias, large-error share, and 90% coverage.
  Failing patterns remain interval-only; confidence and interval width do not penalize quality.
- Result: `PASS + PEAK_UNCERTAINTY_LIMITED + LONGEVITY_UNCERTAINTY_LIMITED`. The methods remain
  research-only and no official Peak, Longevity, PlayerSeasonValue, or Overall version is created.

## Longevity threshold, run, and aggregate calibration

- `goatlab-v1-longevity-threshold-run-calibration-audit-v1` reproduces STEP-0015I exactly and
  preserves the 35/40/25 architecture, P80/P90, U3 dependence model, 2,500 draws, and fixed ECDF.
- Error is not isolated to longest-run discreteness. Run has the weakest isolated rank signal,
  capped area causes the most pairwise reversals, and P80 uncertainty affects breadth, area, and
  run simultaneously.
- A `RUN_BRIDGE_EVENT` is a borderline season with 25%–75% P80 probability connecting credible
  consecutive elite sequences. It is diagnostic metadata and never changes quality by itself.
- The selected central estimate remains the median of fully aggregated fixed-scale draws.
  Transforming expected components is rejected because nonlinear thresholds and tied ECDF regions
  introduce large positive bias.
- Player-grouped aggregate conformal intervals replace overconservative propagated intervals in
  the research-2 output. Intervals are calibrated separately by evidence pattern and do not alter
  central score quality.
- No non-full pattern passes all ranking-grade point gates. Research statuses remain 1,976
  official-form, 2,210 interval-only, and 917 unavailable; no provisional point is manufactured.
- Result: `PASS + LONGEVITY_AGGREGATION_LIMITED`. No official Longevity methodology is created.

## Peak V2 promotion and tiered Longevity policy

- `goatlab-v1-tiered-player-season-value-input-v1` freezes the season contract consumed by both
  dimensions: raw Candidate D, an eligible linked point, nested intervals, evidence regime,
  confidence, Presence reliability, observed/missing channels, and reason codes remain separate.
- `goatlab-v1-peak-v2` is the promoted Peak successor. It preserves the 70/30 three-year/apex
  architecture, uses 2,500 deterministic `U3_STRATIFIED_BLOCK` career draws, reselects the Peak
  window within every draw, and transforms draws through one fixed `BROAD_HIGH_RECALL` ECDF.
- Peak output is tiered. Reference, mixed, and partial-Presence aggregate patterns may receive
  ranking-grade points; weak traditional/no-Presence patterns remain interval-only. A player with
  fewer than three qualifying seasons is constitutionally ineligible, not measurement-missing.
- `goatlab-v1-longevity-v2-tiered` freezes P80/P90 and the 35/40/25 breadth/area/run philosophy.
  Only reference-grade evidence currently receives an official point. A central estimate retained
  for `LONGEVITY_INTERVAL_ONLY` is diagnostic and cannot be consumed as an official point.
- An interval is not a lower score, and confidence never penalizes quality. Active careers are
  accomplishments through 2025-26 only.
- Overall V1 remains frozen. A required interval/unavailable dimension cannot be dropped, have its
  weight redistributed, or be replaced by a midpoint. STEP-0015K performs eligibility only and
  creates no Overall score or rank.

## Overall joint uncertainty architecture

- `goatlab-v1-overall-v2-uncertainty-research` preserves the frozen 17/14/16/14/18/10/11 weights
  and applies them inside 2,500 paired Peak/Longevity `U3_STRATIFIED_BLOCK` draws.
- Peak and Longevity are never independently recombined in the primary architecture. Their
  positive covariance is material; independence narrows intervals and understates uncertainty.
- The central estimate is the median of paired Overall draws. Player-grouped cross-fit calibration
  produces nested 80/90/95 measurement intervals. Offense, Defense, Playoffs, Accolades, and
  Winning remain fixed in this audit.
- An interval-only Longevity distribution may support a provisional Overall point when the
  complete weighted distribution passes the Overall gate. Its midpoint does not become official.
- Missing required evidence makes Overall unavailable. Weights are never renormalized; confidence
  never changes quality; Accolades `NOT_QUERIED` remains unknown.
- Rank bands and Top-N probabilities are conditional research diagnostics. Shared cross-player
  calibration-model uncertainty is not modeled.
- Outcome: `PASS + LIMITED_OVERALL_UNCERTAINTY_ARCHITECTURE`. Overall V1 remains frozen, no Top
  100 is published, and every row carries `DEFENSE_V1_FROZEN_PENDING_REVISION`.

## Tiered Defense V2

- **Decision:** `PASS + PROMOTE_DEFENSE_V2_WITH_LIMITATIONS` under
  `goatlab-v1-defense-v2-tiered`; Defense V1 remains reproducible.
- **Rich form:** 10% Team Context, 38.5714% role-aware actions, and 51.4286% observed Presence.
  The action/Presence ratio preserves Candidate B's 3:4 balance after bounding team inheritance.
- **Actions:** 40% rebound evidence, 30% steals, 30% blocks; 65% global and 35% broad-role
  interpretation where role metadata are reliable. Role does not impose equal ceilings.
- **Presence:** continuously reliability-weighted, opponent/context-adjusted game-participation
  evidence. Missing Presence is never predicted, zero-filled, or reallocated.
- **Measurement:** weaker factual forms are linked with player-grouped cross-fitting. Split-conformal
  80/90/95 intervals and explicit gates produce official, provisional, interval-only, or
  unavailable status.
- **Career validation:** no-Team-Context and partial-Presence patterns pass (MAE/rho 3.19/0.9889
  and 4.61/0.9766). No-Presence and traditional-only patterns remain interval-only.
- **Coverage:** 1,746 official career points, 336 provisional points, 2,093 interval-only, and 928
  unavailable. Universal point coverage is not manufactured.
- **Attribution:** Team Context has 4.34% effective covariance share. Presence has 90.29%, an
  explicit observational limitation rather than a causal claim.
- **Ownership:** Regular Season only; awards and modern defensive rating are validation-only.
- **Overall boundary:** no ranking is promoted. Future Overall work must preserve empirical
  Defense–Peak–Longevity error dependence.

## Final Overall V2 promotion audit

- `goatlab-v1-overall-v2-tiered` is a non-promoted research candidate built from the frozen
  17/14/16/14/18/10/11 Overall weights. It keeps the exact 2,500 paired Peak/Longevity paths and
  couples the complete Defense marginal through a preselected evidence-pattern Gaussian copula.
- The selected coupling reproduces the empirical Defense–Peak and Defense–Longevity latent-rank
  dependence while preserving every Peak/Longevity draw and every sorted Defense draw. The four
  other dimensions remain fixed within each player's simulation.
- Full-reference and partial-Presence patterns support point estimates. Mixed, early-transition,
  no-Presence, and traditional-only patterns remain interval-only under the frozen calibration
  gates. An interval center is diagnostic and never becomes an official ranking point.
- Statuses are `OFFICIAL_OVERALL_POINT`, `PROVISIONAL_OVERALL_POINT`, `OVERALL_INTERVAL_ONLY`,
  and `OVERALL_UNAVAILABLE`. No required weight is dropped or redistributed, and confidence never
  changes player quality.
- The audit produced 312 official, 284 provisional, 1,286 interval-only, and 3,221 unavailable
  player outputs. Only 17 archived V1 Top-100 players are point-eligible; 83 are interval-only.
  A V2 Top 100 would therefore be structurally selected by evidence regime, so Overall V2 is not
  promoted and no new ranking is published. Overall V1 remains the frozen official baseline.

## Interval-native ranking policy audit

- `goatlab-v1-ranking-policy-v2-uncertainty-research` ranks every player with a calibrated Overall
  distribution inside each of the frozen 2,500 STEP-0015N draws. Exact point eligibility is not a
  distribution-rankability requirement.
- The distribution-rankable population is 1,882 players: 312 official, 284 provisional, and 1,286
  interval-only Overall distributions. The other 3,221 players remain unranked because a required
  usable Overall distribution is unavailable.
- Central Overall sort, median rank, expected rank, and pairwise expected wins are tested as
  deterministic summaries. None passes the frozen Spearman and Top-10/25/50/100 overlap gates
  across all historical evidence patterns.
- Rank bands use player-grouped signed conformalized-quantile calibration in percentile-rank space.
  The 50/80/90/95 bands are nested and contain the median-rank diagnostic. Calibration may contract
  conservative raw bands or expand under-covering bands without changing scores or rank centers.
- Top-N and pairwise probabilities pass their Brier and expected-calibration-error gates. Strong
  order means at least 90%, lean order means 65%–90%, and 35%–65% is indeterminate.
- Interval-native evidence widens rank uncertainty and never penalizes quality. A diagnostic center
  may be displayed only with a range and non-official label; unavailable players remain unranked.
- Result: `PASS + VALID_PROBABILISTIC_RANKING_ONLY`. No exact V2 Top 100 is generated, Overall V2
  remains unpromoted, and Overall V1 remains frozen.

## Probabilistic-first ranking governance (STEP-0015P)

- The permanent publication-policy version is `goatlab-v1-ranking-policy-v2-probabilistic`.
  Canonical comparison is a player's calibrated Overall distribution and derived rank
  distribution, conditional on the frozen measurement architecture. A point score or ordinal rank
  alone is not the scientific result.
- `goatlab-v1-overall-v2-tiered` remains the frozen **research probabilistic substrate** and is
  **not promoted as an exact-point Overall methodology**. The STEP-0015N MAE gate and STEP-0015O
  exact-order failures stand. Overall V1 and the archived Top 100 remain reproducible and unchanged.
- Players with official, provisional, or interval-native Overall distributions may participate
  without confidence/uncertainty quality penalties. Players with an unavailable required
  distribution are unranked; required weights are never redistributed or filled with midpoints.
- A future *GOATLab Top 100 — Probabilistic Leaderboard* may use ascending median rank with
  canonical-player-ID ties for **navigation**. Its `#N` is a display position rather than an exact
  quality ordering; every entry needs median rank, 80%/90% rank bands, Top-100 probability,
  Overall range, and evidence status. Profiles additionally expose 50%/95% bands, Top-10/25/50
  probabilities, and pairwise context. STEP-0016 builds the dataset; none is generated here.
- Pairwise at least 90% is strong, 65%–90% is lean, and 35%–65% is indeterminate; reverse labels
  are symmetric. Top-100 membership at least 90% is robust, 65%–90% likely, 35%–65% bubble,
  10%–35% likely outside, and below 10% robustly outside. These labels never alter quality.
- For interval-native players, show Overall range and uncertainty metadata. A center is optional
  but must be labeled a diagnostic summary beside its range, never an official exact score.
- GOATLab cannot eliminate unequal historical measurement environments. Calibrated uncertainty
  represents that limitation rather than fabricated precision; wider uncertainty does not imply
  lower player quality. Shared global calibration-model uncertainty is not fully modeled.
- Active careers use completed evidence through 2025-26 (`TO_DATE_NO_PROJECTION`). Formula
  retuning is not authorized merely because a display ordering looks unconventional.
