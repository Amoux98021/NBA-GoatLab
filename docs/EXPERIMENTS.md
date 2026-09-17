# Experiments

No ranking or machine-learning experiments exist in Phase 1.

Future experiments must record the objective, input snapshot, feature version, code/commit, deterministic seed where applicable, evaluation procedure, results, limitations, and artifact/model version. Experiments must not rewrite raw facts or canonical Silver data.

## STEP-0007 qualification sensitivity analysis

- **Objective:** choose a cross-era comparison population that reduces one-game noise, scales with opportunity, and works when minutes are unavailable.
- **Input:** frozen GOATLAB-HIST-V1, fingerprint 283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c.
- **Methodology version:** era-normalized-player-season-v1.
- **Candidates:** Regular Season 10%, 20%, and 30% of team opportunity; Playoffs all appearances, 10%, and 20%; selected games plus 10% maximum player minutes where minutes qualified.
- **Evaluation:** complete-corpus retention, minimum partition retention, PPG distribution movement, shortened-season and playoff applicability, and input availability. No player ordering or target ranking was evaluated.
- **Result:** select 20% Regular Season with floor five and 10% Playoffs with floor two. Mean retention is 88.31% and 92.38%. The minutes supplement retained 69.00% and worked in only 100 partitions, so it was rejected as universal.
- **Random seed:** not applicable; all calculations are deterministic.
- **Artifacts:** docs/data/qualification-sensitivity-analysis.json, ADR-0009, and STEP-0007.
- **Limitations:** qualification controls distribution membership, not sampling uncertainty. Later changes require a new methodology version and preserve this record.

## STEP-0008 peak and longevity sensitivity analyses

- **Objective:** measure how availability policy, percentile threshold, cumulative baseline, and candidate-universe rules alter descriptive career primitives without selecting a preferred GOAT definition.
- **Input:** GOATLAB-HIST-V1 plus era-normalized-player-season-v1 at their frozen fingerprints.
- **Methodology version:** career-trajectory-peak-longevity-v1.
- **Peak candidates:** QUALITY and AVAILABILITY_ADJUSTED complete contiguous windows at one, three, and five seasons.
- **Peak result:** availability adjustment changes 16%–18% of eligible PPG window selections, about 12% of TS% selections, and 24%–27% of APG selections depending on window length. Both variants are retained.
- **Longevity candidates:** percentile thresholds 0.80/0.90/0.95/0.99; positive-z sums; weighted positive-z; percentile area above 0.50/0.80/0.90 with weighted variants.
- **Candidate-universe result:** proposals range from 867 players at ten qualified seasons to 2,617 in the broad three-season/core-95th union. The recommended five-season/core-90th union contains 2,140 and is an acquisition flag, not ranking eligibility.
- **Optimization target:** none. Famous careers are diagnostics only and no ordering was evaluated.
- **Random seed:** not applicable; every operation is deterministic.
- **Artifacts:** peak-window-sensitivity.json, longevity-sensitivity.json, award-candidate-universe-analysis.json, ADR-0011, ADR-0012, and STEP-0008.
- **Limitations:** opportunity shrinkage and thresholds represent multiple interpretable lenses, not endorsed Peak or Longevity weights.

## STEP-0009 award taxonomy and source-coverage audit

- **Objective:** establish reproducible official award facts and source gaps without valuing accolades.
- **Input:** STEP-0008 broad 2,140-player acquisition universe; full 5,103-player identity registry remains retained.
- **Methodology version:** official-player-awards-canonical-v1.
- **Probe:** 20 representative IDs, 1,220 events, 29 description mappings before full acquisition.
- **Full result:** 33 descriptions, 8,137 canonical events, zero unknowns after evidence review, zero quarantines, and zero request failures/retries.
- **Validation:** six official history count checks matched exactly; All-Star semantics remain partial and statistical titles absent.
- **Optimization target:** none. Counts are descriptive and no award value or player ordering was evaluated.
- **Random seed:** 9009 controls retry jitter only; no statistical experiment uses randomness.
- **Artifacts:** award taxonomy, coverage, acquisition/canonicalization, official-reference, case-study, output, and quarantine reports plus ADR-0013/0014.

## STEP-0010 postseason inference and participation audit

- **Objective:** test whether frozen game evidence supports universal team W/L, champion/runner-up inference, Finals identification, format-aware series facts, and trade-safe player participation.
- **Input:** GOATLAB-HIST-V1 plus official-player-awards-canonical-v1 at their frozen fingerprints.
- **Methodology version:** team-success-postseason-v1.
- **Hypothesis:** the winner and opponent in the unique chronologically final playoff game identify the champion and runner-up; all games between that team pair form the Finals.
- **Validation:** complete official NBA champion, runner-up, and series-result evidence across 80 seasons; 2022-23 legacy/API game overlap; W/L accounting and participation integrity gates.
- **Result:** champion 80/80, runner-up 80/80, and series result 80/80. Opponent-pair series inference is valid in 79 seasons and blocked for the documented 1953-54 round-robin/mixed format.
- **Coverage finding:** Regular W/L is universal. Four seasons with contradictory fallback point-sum evidence retain W/L but withhold scoring context. Minute shares qualify in 44 Regular and 56 Playoff partitions.
- **Participation finding:** 217 regular-season champion members have no observed champion playoff participation. Candidate-scoped award comparison retains 37 official champion events without Finals appearances and two queried Finals participants without an award event.
- **Optimization target:** none. No player ordering, championship credit, role label, or team-success composite was evaluated.
- **Random seed:** not applicable; every derivation is deterministic.
- **Artifacts:** TEAM_SUCCESS_V1, postseason format registry, championship reconciliation, player participation audit, case studies, ADR-0015, ADR-0016, and STEP-0010.

## STEP-0011 All-Star and statistical-leader source audit

- **Objective:** test league-wide official evidence for All-Star event rosters/participation and statistical leaders without assigning accolade value.
- **Inputs:** GOATLAB-HIST-V1, STEP-0007 qualification/coverage, and candidate-scoped official-player-awards-canonical-v1.
- **Methodology version:** all-star-stat-leader-facts-v1.
- **All-Star candidates:** PlayerGameLogs participation, V3 event-game roster listing, and PlayerAwards event evidence retained separately.
- **Leader candidates:** official-source rank one, raw per-game maximum, raw total maximum, and coverage-qualified frozen-corpus leader.
- **Result:** 1,852 All-Star evidence rows across 472 players; 422 leader event rows; 238 exact partition reconciliations, 10 qualification differences, 83 derived coverage gaps, and 11 source gaps.
- **Sensitivity finding:** modern All-Star multi-game formats prove why game appearances cannot be renamed selections. Early metric sparsity proves why source rank and derived qualified leader cannot be forced into uniform historical coverage.
- **Optimization target:** none. No player order, award value, title weight, or GOAT output was evaluated.
- **Random seed:** 9011 controls retry jitter only; transformations are deterministic.
- **Artifacts:** ACCOLADE_FACT_COMPLETION_V1, source/reconciliation/coverage reports, case studies, ADR-0017, ADR-0018, and STEP-0011.

## STEP-0012 dimension candidate and redundancy audit

- **Objective:** test multiple interpretable definitions for eight proposed GOAT dimensions while quantifying ownership overlap, missingness, era coverage, redundancy, and arbitrary internal-weight sensitivity.
- **Inputs:** frozen corpus, era normalization, career, awards, team-success, All-Star, and statistical-leader artifacts at their recorded fingerprints.
- **Methodology version:** `goat-dimension-candidates-v1`.
- **Populations:** all 5,103; participation-qualified 1,891; career-signal 2,606; broad high-recall 2,656. The broad population is a diagnostic scaling reference only.
- **Candidates:** 38 across eight dimensions. Thirty-two are validated for further experiment, four rejected, two deferred, zero final.
- **Scaling/missingness:** four scales crossed with four policies; no imputation or zero fill.
- **Redundancy result:** 15 shared primitives and 31 candidate pairs at absolute Spearman >= 0.95. Peak/Era and Longevity/Era exhibit the strongest cross-dimension overlap.
- **Coverage result:** five-year Peak and contiguous playoff Peak fail the 50% broad-availability gate. Modern offense/defense are structurally post-1996 and deferred from universal use.
- **Weight experiment:** 200 uniform-simplex samples per candidate, deterministic seed 120012. Sampled ordering stability ranges 0.830–1.000; none fails the 0.75 instability rule.
- **Optimization target:** none. No external ranking, player order, overall score, or Top 100 exists.
- **Artifacts:** GOAT_DIMENSION_CANDIDATES_V1, registry, coverage/redundancy/era/sensitivity/case-study reports, ADR-0019 through ADR-0021, and STEP-0012.
- **Limitations:** award evidence remains candidate-scoped, early Defense remains structurally limited, and scaling/ownership choices remain experimental.

## STEP-0013 unsupervised structural validation

- **Objective:** test latent candidate structure, incremental uniqueness, candidate redundancy, and player-profile archetypes without a target ranking.
- **Inputs:** frozen corpus, normalization, career, awards, team-success, accolade completion, and STEP-0012 fingerprints.
- **Methodology version:** `unsupervised-structural-validation-v1`.
- **Matrices:** 32-candidate, 16-feature cross-era primitive, seven-feature post-1996 enrichment, and seven-feature magnitude/profile-shape views across all, participation-qualified, career-signal, and broad-high-recall populations.
- **Missingness:** complete intersections only, with explicit exclusion/era audits and no imputation.
- **PCA result:** four parallel-analysis components; 83.17% cumulative variance; bootstrap loading correlations 0.989–0.994.
- **Factor result:** seven-factor principal-axis/Varimax solution selected from 2–10 using held-out correlation reconstruction plus parsimony; bootstrap loading correlations exceed 0.997 on average.
- **Clustering result:** profile-shape K-means selects two coarse groups, seed ARI 0.996 and bootstrap ARI 0.938. Era Cramér's V is 0.088; limited GMM/hierarchical agreement blocks a stronger taxonomy claim.
- **Pruning result:** 18 non-final candidates retained. Era Dominance is `USE_AS_DIAGNOSTIC_ONLY`; modern offense/defense stay deferred.
- **Random seed:** 130013 for parallel analysis, bootstrap sampling, K-means, and GMM initialization.
- **Optimization target:** none. Model-selected player examples were added only after fitting.
- **Artifacts:** structural reports/registry, ADR-0022 through ADR-0024, ignored Gold/figures, and STEP-0013.
- **Limitations:** later-era complete-case selection, candidate-scoped awards, early Defense, non-likelihood factor method, bounded hierarchical sample, and cross-model cluster disagreement.

## STEP-0014 constitutional formula finalization and effective-influence audit

- **Objective:** choose stable, interpretable formulas for seven constitutionally owned dimensions and quantify overlap without optimizing against a player ranking.
- **Inputs:** GOATLAB-HIST-V1, normalization, career, awards, team-success, accolade-completion, STEP-0012 candidate, STEP-0013 structural, and machine-Constitution fingerprints.
- **Methodology version:** `goatlab-v1-dimension-scores-v1`.
- **Scale/population:** 0–100 midrank ECDF against the frozen 2,656-player broad-high-recall population; all 5,103 players retain output rows.
- **Peak experiment:** 60/40, 70/30, and 80/20 three-year/apex blends. All have Spearman at least 0.9996; 70/30 is selected as the balanced constitutionally valid center.
- **Longevity experiment:** P80/P85/P90/P95 season-quality thresholds with P90 capped season influence. External All-NBA calibration selects P80 by maximum Youden J 0.6781; awards are not formula inputs. P85/P90/P95 Spearman to selected are 0.9275/0.8040/0.6332.
- **Other perturbations:** Offense volume 60/65/70%; Playoffs 60/25/15, 65/20/15, 70/20/10; Accolades 55/40/5, 60/35/5, 65/30/5; Winning 60/30/10, 65/25/10, 70/20/10. Selected-alternative Spearman is at least 0.9977 outside Longevity.
- **Bridge experiment:** portable-to-action Defense passes n=3,368, Spearman 0.9883, median raw delta 0.0153. Modern per-75 Offense is correlated (n=2,308, Spearman 0.9322, R² 0.8778) but not used. Advanced Defense fails (n=2,337, Spearman 0.2813, R² 0.0840).
- **Structural result:** 1,882 complete-score players; Peak–Longevity Spearman 0.9304, Peak–Offense 0.8027, Winning–Accolades 0.4128. Incremental residual variance ranges from 8.3% Peak to 65.8% Winning.
- **Overall-weight diagnostic:** 500 deterministic random-simplex samples, seed 140014. Mean/minimum Spearman versus an equal-weight diagnostic is 0.9599/0.7404; mean/minimum top-50 overlap is 0.821/0.56. No official Overall or weight vector was selected.
- **Optimization target:** none. Famous-player case studies were inspected only after formula selection and never altered a formula.
- **Artifacts:** GOAT_DIMENSION_SCORES_V1, formula registry, sensitivity/cross-audit/era/bridge/case-study reports, ADR-0025/0026, and STEP-0014.
- **Limitations:** candidate-scoped Accolades, early Defense confidence, sparse playoff evidence, incomplete historical position coverage, and genuine Peak/Longevity overlap.

## STEP-0015 Overall weighting and eligibility audit

- **Objective:** select a transparent Overall weighting method only after proving that unknown Accolades cannot exclude a plausible Top-100 candidate and quantifying covariance-driven effective influence.
- **Inputs:** 5,103 frozen player profiles, 1,882 complete seven-dimension profiles, STEP-0014 fingerprint `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`.
- **Eligibility experiment:** assign Accolades=100 to every six-complete `NOT_QUERIED` player and compare with the matching Top-100 cutoff under A–D plus 10,000 admissible vectors. Zero crossers and zero five-point-buffer reviews; no award request was needed.
- **Candidates:** equal nominal; constitution-informed 21/16/17/11/17/9/9; redundancy-adjusted 17/14/16/14/18/10/11; and a deterministic stability-oriented bounded-search vector.
- **Selection:** redundancy-adjusted C. It preserves round-number transparency and 79% direct-performance nominal weight while avoiding the greater Peak concentration of B and the opaque objective precision of D.
- **Effective influence:** default Peak/Longevity/Offense/Defense/Playoffs/Accolades/Winning shares are 20.72/16.56/17.07/11.07/18.77/8.13/7.68%. Career shape is 37.28%; direct performance 84.20%; recognition/outcome 15.80%.
- **Sensitivity:** 10,000 draws, seed 150015. Spearman versus default is 0.9946–0.9999; median/minimum Top-100 overlap 0.95/0.92. Local perturbations have minimum Spearman 0.9979 and Top-100 overlap 0.93.
- **Cohorts:** no equality target or quota. Complete-profile debut-era means range 52.02–63.78 and remain a monitored selection/cohort limitation. Active careers are to-date with no projection.
- **Optimization target:** none. External lists and case-study identities were excluded from formula selection.
- **Artifacts:** ignored Gold Overall/candidate/stability/eligibility partitions; committed eligibility, weight, effective-influence, leave-one-out, sensitivity, cohort, diagnostic, Top-100, and summary reports; ADR-0027/0028.

## STEP-0015A Defense forensic audit

- **Objective:** determine whether V1 Defense attributes opponent-value prevention to players rather than team identity, without using diagnostic player order as a target.
- **Inputs:** frozen STEP-0014 fingerprint `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a` and STEP-0015 fingerprint `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`.
- **Reconstruction:** 5,103/5,103 V1 Defense outputs match exactly; maximum absolute difference 0.
- **Attribution experiment:** suppression ICC 1.0; final player-season between-team eta-squared 0.8992; career raw correlation 0.8661 with team suppression versus 0.4450 with action context.
- **Role experiment:** position coverage 69.9%; V1 means are 50.51 big, 46.64 forward, 46.77 wing, 41.07 guard. Modern residual role effects are small and do not prove a conditional guard penalty.
- **Presence experiment:** 17,089 eligible player-seasons under 10-with/five-without gates and `n_eff/(n_eff+20)` shrinkage; 9,867 player-team-seasons remain insufficient/NULL.
- **Candidates:** V1 65/35; reduced-team 45/55; triangulated presence 30/30/40; coverage-adaptive 35/35/30; universal-core 40/35/25. Order is team/actions/presence.
- **Validation:** official advanced defensive-rating Spearman is weak (V1 0.2813; triangulated 0.2501). Post-construction DPOY/All-Defense enrichment is higher for triangulated presence; awards never enter formulas.
- **Scale finding:** Defense SD is 31.87 overall and 9.50 in the Top 100, the largest Top-100 dimension dispersion.
- **Counterfactual:** Defense-score Spearman to V1 is 0.7876 with Top-25/50/100 overlap 0.40/0.52/0.52. Frozen-weight Overall Spearman is 0.9958; Top-10/25/50/100 overlap 0.70/0.88/0.94/0.95. Published V1 remains unchanged.
- **Verdict:** audit PASS; V1 constitutional verdict `REQUIRES_REVISION`; experimental V2 selected for later promotion review.
- **Optimization target:** none. Player identities, awards, external rankings, and conventional expectations were excluded from candidate construction and selection.

## STEP-0015B Defense V2 promotion audit

- **Objective:** test whether Candidate B's observed and missing-Presence regimes can share one universal Defense scale.
- **Reconstruction:** all 5,103 scores, raw values, 28,817 Presence rows, 17 stress cases, and 17,089 eligible player-seasons reproduce with zero numerical difference.
- **Masking:** 12,875 full-evidence seasons. Direct renormalization MAE/RMSE is 10.72/12.99 points; grouped-ridge expected Presence improves this to 9.90/11.47 but leaves 49.40% above 10-point absolute error.
- **Fallback model:** player-grouped five-fold ridge, alpha 0.1 selected from 0.1/1/10/100; Presence R-squared 0.0174 and Spearman 0.1366. No award, modern, name, or postseason input.
- **Career masking:** expected fallback MAE 6.38, Pearson 0.8022, and 21.79% above 10 points after aggregation.
- **Evidence regimes:** no-STL/BLK MAE 2.50; reduced position/DREB MAE 1.00; no-Presence MAE 10.72. Presence is the blocking portability channel.
- **Continuity:** continuous reliability reduces the simulated boundary jump from 14.0 to 3.6 points and yields 21,786 mathematical Presence estimates.
- **Attribution:** V1/Candidate-B/continuous career team correlations 0.9165/0.6572/0.6317; between-team eta-squared 0.9037/0.5421/0.4485.
- **Ranking diagnostic:** frozen-weight counterfactual Spearman 0.9946; Top-10/25/50/100 overlap 0.80/0.84/0.90/0.92. Published Overall is unchanged.
- **Outcome:** audit `PASS`; promotion `DO_NOT_PROMOTE` because the fallback fails absolute calibration and predictive-signal gates.
- **Optimization target:** none. Promotion criteria exclude player names, awards, and external rankings.

## STEP-0015C Peak forensic audit

- **Objective:** determine whether frozen Peak V1 measures sustained individual overall basketball apex for the reasons required by the Constitution.
- **Inputs:** frozen dimension, Overall, Constitution, STEP-0015A, and STEP-0015B fingerprints; 22,457 qualified Regular Season player-seasons and all 5,103 player outputs.
- **Reconstruction:** all 5,103 Peak rows and every intermediate reproduce exactly; maximum numerical difference is zero.
- **Effective influence:** mean realized primitive weights are TeamSuppression 34.34%, PPG 26.63%, APG 19.10%, TS 7.02%, RPG 6.73%, BPG 3.10%, and SPG 3.09%. Corresponding covariance/Shapley shares are 30.17%, 32.26%, 24.67%, 4.26%, 4.83%, 1.11%, and 2.69%.
- **Attribution:** the team component has zero within-team-season variance, 97.65% between-team eta-squared, and 104,097 identical-credit teammate pairs. Its season-quality leave-one-out MAE is 14.28 points.
- **Masking:** among 16,308 rich-evidence seasons, no-STL/BLK MAE is 2.10, no-TS is 3.29, and no-team-context is 13.53; observed-feature renormalization is therefore not construct invariant.
- **Window test:** three-year/apex Spearman is 0.9512; 70/30 versus 60/40 and 80/20 is at least 0.99958. Complete-contiguous logic and deterministic ties pass.
- **Candidate test:** no-team current actions, explicit 60/40 role actions, multi-path 65/35 role actions, and unpromoted Defense-V2 channels were compared. Multi-path role actions is retained as research only; it has 1,761 reference scores and V1 Spearman 0.8787.
- **Counterfactual:** on 1,391 common eligible players, research-peak Overall Spearman is 0.9918 and Top-10/25/50/100 overlap is 0.90/0.96/0.86/0.94. Published Overall remains unchanged.
- **Result:** audit `PASS`; constitutional verdict `REQUIRES_REVISION`. No V2 is promoted.
- **Optimization target:** none. Diagnostic identities and external rankings were excluded from formula construction and selection.

## STEP-0015D Player-season value measurement audit

- **Objective:** test universal, era-relative individual Regular Season value candidates after the
  SeasonQuality attribution failure, without promoting Peak, Longevity, Defense, or Overall.
- **Population:** 22,457 qualified player-seasons and 5,103 master players; no network access.
- **Regimes:** 5,881 early-limited, 55 traditional-box, 2,153 expanded-box/no-Presence, and 14,368
  full-portable rows, assigned from actual evidence.
- **Candidates:** transparent portable, multi-path bounded team, complete-evidence measurement, and
  continuous-reliability Presence. Candidate D is retained for research with 16,576 scored rows.
- **Attribution:** Candidate D caps team context at 5.5% total realized weight; its correlation with
  value is 0.0707 and covariance share is 0.0013. Offense/defense covariance shares are
  0.6347/0.3653.
- **Masking:** on 14,155 full rows, no-Presence MAE/RMSE is 5.73/7.11; traditional-box is
  8.48/10.36; early-limited is unscorable. Error varies by role and archetype.
- **Continuity:** 12,754 adjacent pairs have Spearman 0.7700. Mean absolute movement is 14.30 at
  regime transitions versus 14.58 within regimes and 16.64 after team changes versus 13.47 on the
  same team.
- **Validation:** 97.67% of 43 available MVP seasons and 93.95% of 215 available All-NBA First
  seasons are at or above P90. Awards are validation-only.
- **Counterfactuals:** Peak Spearman 0.9057 (1,761 scores), Longevity 0.7832 (2,950), candidate
  Peak-Longevity 0.8691, and Peak-only Overall 0.9937 (1,391 common ranked players).
- **Result:** `PASS + PROMISING_BUT_NOT_READY`. No production method or ADR is created.
- **Optimization target:** none; names, awards, outcomes, and conventional ranking order are absent
  from formula selection.

## STEP-0015E Historical evidence bridge audit

- **Objective:** determine whether historically absent creation and defensive-impact channels can
  recover the same full-evidence PlayerSeasonValue construct.
- **Population:** 22,457 qualified Regular Season rows; 14,368 complete defensive-measurement rows
  form the controlled masking population.
- **Leakage controls:** deterministic player-grouped five-fold validation, decade-block transfer,
  fixed seed 15001505, and no identity, award, postseason, championship, or ranking predictors.
- **Creation:** PPG grouped R-squared 0.5043/Spearman 0.7097; PPG+TS grouped R-squared
  0.5313/Spearman 0.7286. Era-block results are essentially the same.
- **Defense:** grouped Spearman is 0.7606 without Presence, 0.6808 with traditional RPG/team,
  0.7204 with Presence/team only, and 0.1710 with team only. A one-factor model explains 36.51%
  and its loadings are not stable across decades.
- **Mask gates:** expanded/traditional/early-with-Presence/early-minimal MAEs are
  7.27/8.00/8.41/11.35; all fail the five-point MAE and 15%-over-ten-error gates.
- **Intervals:** empirical 90% widths are 26.92/30.21/33.37/42.30 points. They are retained as
  uncertainty evidence, not promoted point estimates.
- **Outcome:** `PASS + NO_VALID_BRIDGE`; 16,576 observed research scores, 5,098 interval-only
  diagnostics, and 783 unavailable rows. Candidate D and every V1 methodology remain unchanged.
- **Optimization target:** none. Named early and modern cases are inspected only after models and
  gates are frozen.

## STEP-0015F Historical factual data recovery audit

- **Objective:** determine whether STEP-0015E sparsity reflects unrecorded statistics, a source
  omission, or a recoverable aggregation problem before accepting interval-native history.
- **Source experiment:** acquire official PlayerCareerStats totals for 2,234 deterministic
  pre-1996 player scopes. 2,231 return rows and three are terminal source gaps; identity resolution
  is exact through official `PLAYER_ID`.
- **Aggregation result:** 9,532 field totals can be reproduced exactly from complete frozen
  player-game groups but were omitted by the partition-wide season aggregation gate. Another 7,666
  complete game aggregates materially differ from current official career totals and are retained
  as source conflicts.
- **Recovery:** 5,861/5,863 APG gaps, 5,319/5,321 TS-evidence gaps, and 4,675/5,242 action gaps are
  factually recovered. `EARLY_LIMITED` falls from 5,881 to 567 rows.
- **TS validation:** standard totals-derived TS differs from official advanced TS by 0.000250 on
  average and at most 0.000500 across 12,437 overlaps. Historical free-throw possession assumptions
  remain a documented limitation.
- **Candidate D isolation:** the formula is unchanged. Coverage rises from 16,576 to 21,107 rows
  and 2,950 to 3,893 players solely because observed facts improve.
- **Masking recheck:** expanded/traditional/early-with-Presence/early-minimal MAEs become
  7.25/7.96/8.41/11.34. Artificial evidence removal still fails bridge gates, so factual recovery
  does not solve missing Presence or historically unrecorded defense.
- **Downstream diagnostics:** fixed Peak coverage rises 1,761→2,326 players and fixed Longevity
  coverage 2,950→3,893. Neither is promoted.
- **Outcome:** `PASS + MATERIAL_RECOVERY`; rerun the PlayerSeasonValue measurement and historical
  bridge audits on the recovered factual corpus.
- **Optimization target:** none. No historical statistic is predicted, and named cases do not
  affect source scope, source precedence, or recovery logic.

## STEP-0015G PlayerSeasonValue V2 promotion audit

- **Objective:** determine whether factual recovery makes Candidate D production-comparable across
  historical evidence regimes.
- **Reconstruction:** all 22,457 rows, 21,107 scores, regimes, components, and percentiles reproduce
  STEP-0015F exactly; maximum numerical difference is zero.
- **Source sensitivity:** 9,299 material source-field conflicts affect 5,607 seasons. Among 4,631
  scoreable affected seasons, alternate-source percentile MAE is 0.321; 0.54% move by more than
  five points and 0.19% by more than ten.
- **Coverage:** 21,107 seasons and 3,893 players score; 1,350 seasons remain unavailable. Of those,
  567 lack rebound/action evidence and 783 lack team context.
- **Influence:** covariance shares are APG 32.96%, PPG 22.52%, RPG 16.49%, STL/BPG 11.13% each,
  TS 6.61%, Presence -1.02%, and team context 0.18%. The team channel remains capped at 5.5% total.
- **Masking:** expanded/no-Presence and traditional-box MAEs remain 7.25 and 7.96 points, with
  29.67% and 32.48% above ten points. Those regimes account for 6,420 actual scored seasons, so the
  failed invariance test is production-relevant.
- **Continuity:** regime-change MAE is 14.71 versus 14.69 within regime; recovery removes a mean
  cliff but does not establish score equivalence. Team changes remain more volatile than same-team
  transitions.
- **Validation:** MVP and All-NBA First seasons remain strongly enriched at the top; PIE Spearman
  is 0.7384. All are validation-only and were not used to select the verdict.
- **Outcome:** `PASS + DO_NOT_PROMOTE`. Candidate D remains research-only; Peak, Longevity,
  Defense, and Overall remain frozen.
- **Optimization target:** none. No player name, award, outcome, postseason, or external ranking
  enters Candidate D or the promotion gate.

## STEP-0015H Evidence-regime measurement linking

- **Reference:** 14,687 full-portable factual player-seasons, each paired with artificial weaker
  forms; Candidate D and V1 remain frozen.
- **Linkers:** identity, linear, equipercentile, isotonic, and broad-role isotonic. Primary
  validation is five-fold player-grouped; random and era transfer are secondary.
- **Point-grade forms:** expanded proxy action + Presence (MAE 1.60, Spearman 0.9972), traditional
  + Presence (3.53, 0.9867), and missing Team Context (2.07, 0.9960).
- **Interval-only forms:** expanded/no-Presence (6.13, 0.9640), traditional/no-Presence (7.62,
  0.9415), offense-only (8.55, 0.9271), and early offense + Presence (13.37, 0.8081).
- **Intervals:** split-conformal 90% empirical coverage is 89.83%–90.20%; mean widths range from
  6.72 to 51.84 points depending on form.
- **Actual statuses:** 14,687 official-form points, 3,831 provisional points, 3,937 interval-only,
  and two unavailable. `OFFICIAL_POINT` is a research measurement-form status, not promotion.
- **Pairwise:** weak-form order is unreliable for close scores; interval non-overlap is uncommon
  but highly accurate at wider separations.
- **Result:** `PASS + LIMITED_TIERED_ARCHITECTURE`. Missing-stat prediction remains prohibited.
- **Optimization target:** none; named players appear only after architecture and gates are frozen.

## STEP-0015I Peak/Longevity uncertainty propagation

- **Question:** can calibrated season measurement uncertainty be aggregated without changing
  Peak's height or Longevity's duration semantics?
- **Population:** 1,270 full-form validation careers, six realistic masked career patterns, and all
  5,103 canonical players for final research status assignment.
- **Candidates:** independent draws, player-block residual resampling, role-block resampling, and
  evidence-form/role/archetype/score-band stratified player-block simulation.
- **Selected:** `U3_STRATIFIED_BLOCK`, fixed seed, 2,500 draws, frozen ECDF references.
- **Peak:** mixed patterns pass the aggregate point gates (MAE 3.93, Spearman 0.9842); traditional
  careers remain interval-only (MAE 6.66). Window selection is repeated within every draw.
- **Longevity:** no non-full pattern passes all point gates; mixed Spearman is 0.9388 and
  traditional Spearman is 0.8773. Exact longest run is computed per correlated draw.
- **Outcome:** `PASS`; both dimension uncertainty methods are `LIMITED`; no promotion occurs.
- **Optimization target:** aggregate calibration only. Player names, awards, outcomes, postseason,
  championships, projections, and conventional rankings are excluded.

## STEP-0015J Longevity threshold/run calibration

- **Question:** why can uncertainty-aware Longevity preserve absolute score while missing the
  point-grade rank-correlation gate?
- **Frozen structure:** P80/P90, 35/40/25, U3 stratified player-block dependence, 2,500 draws, and
  one fixed reference ECDF.
- **Component result:** mixed breadth/area/run point MAEs are 4.60/4.59/5.11; traditional-only
  values are 7.09/7.28/7.64. No single component explains the aggregate failure.
- **Run bridges:** 827 validation events occur in 8.49% of career-pattern cases. Conditional run
  and final-score changes are 2.04 seasons and 8.00 points.
- **Estimator result:** final-draw median remains best. Final-draw means and expected-component
  transforms degrade rank calibration or introduce large positive bias.
- **Interval result:** cross-fitted player-grouped conformal 90% coverage is 90.08%–90.24% for
  mixed, partial-Presence, and traditional patterns, with widths appropriate to evidence strength.
- **Ranking result:** mixed/partial-Presence MAEs remain 3.72/3.44 but Spearman remains
  0.9388/0.9417. Traditional-only is 6.10/0.8773. No non-full provisional point passes.
- **Sensitivity:** P78/P88 through P82/P92 and 20%–30% run weights do not change the conclusion;
  constitutional thresholds and weights remain frozen.
- **Outcome:** `PASS + LONGEVITY_AGGREGATION_LIMITED`; Peak regression difference is zero.
- **Optimization target:** calibration gates only. No player identity, reputation, award,
  championship, postseason, or external ranking is used.

## STEP-0015K Peak promotion and Longevity policy freeze

- **Objective:** consolidate validated season and career uncertainty research into durable Peak,
  Longevity, and Overall eligibility contracts without another methodology search.
- **Inputs:** STEP-0015H/I/J fingerprints `4b1ff850...`, `4f44cf63...`, and `15dd0713...`.
- **Peak decision:** promote `goatlab-v1-peak-v2` with limitations. Mixed and partial-Presence
  validation retain MAE/rho 3.93/0.9842 and 3.10/0.9891; traditional-only evidence remains
  interval-only.
- **Peak coverage:** 974 official points, 1,411 provisional points, 71 interval-only, and 2,647
  unavailable. The unavailable population is fully explained by insufficient qualifying career
  length (2,529) or absence of a complete contiguous window (118), not measurement loss.
- **Longevity decision:** freeze `goatlab-v1-longevity-v2-tiered`; retain 1,976 official points,
  2,210 interval-only, and 917 unavailable, with no manufactured provisional points.
- **Overall audit:** 641 players have seven ranking-grade point dimensions, 1,241 include an
  interval-only required dimension, and 3,221 lack a required dimension. No score or rank is
  computed and no weight is redistributed.
- **Optimization target:** none. This is a reconstruction, promotion, and policy-freeze step;
  player order is never evaluated.
- **Fingerprint:** `3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f`.

## STEP-0015L Overall uncertainty architecture

- **Population:** 1,200 full-form validation careers, six historical mask patterns, and all 5,103
  canonical players for status assignment.
- **Architecture:** 2,500 paired Peak/Longevity U3 draws; fixed other dimensions; frozen Overall
  weights; median paired-draw center; player-grouped calibrated intervals.
- **Calibration:** mixed MAE/rho/bias 1.157/0.9957/+0.026; partial Presence
  0.970/0.9961/+0.125; traditional 1.935/0.9901/-0.158. Traditional-only fails the >5-point gate.
- **Dependence:** mean within-draw correlation is positive in every pattern. Independent marginal
  recombination narrows 90% intervals and is rejected.
- **Statuses:** all players 602 official, 1,280 provisional, zero interval-only, and 3,221
  unavailable. V1 Top 100 transition is 16 official and 84 provisional without reordering.
- **Ranking diagnostics:** mixed Top 10/25/50/100 overlap is 100/96/94/94%; no ranking is
  published.
- **Outcome:** `PASS + LIMITED_OVERALL_UNCERTAINTY_ARCHITECTURE`; next action is Defense revision
  before a dedicated Overall promotion decision.
- **Optimization target:** calibration only. No player identity, conventional rank, award outcome,
  confidence penalty, or player-specific adjustment enters the architecture.

## STEP-0015M Defense V2 tiered promotion

- Reconstructed Defense V1 and STEP-0015A Candidate B exactly (maximum difference 0.0) and
  fingerprint-verified STEP-0015B/H/L inputs.
- Compared predeclared Team Context weights of 10/15/20/30%. Score/team correlation was
  0.186/0.272/0.362/0.541; 10% was selected before named-player review.
- Paired 13,923 rich-form player-seasons with eight weaker factual forms. Tested identity, linear,
  equipercentile, isotonic, and role-isotonic linkers with player-grouped, era-block, and random
  folds.
- Actions+Presence/no-context, partial-Presence, and traditional+Presence season forms passed point
  gates. Every no-Presence form failed and remained interval-only; context-only is unavailable.
- Split-conformal 90% coverage was 89.91%–90.25%. Career validation used 1,984 rich-form careers;
  no-context and partial-Presence patterns passed, while traditional+Presence, no-Presence,
  traditional-only, and mixed patterns failed at least one point gate.
- Modern defensive rating remained weak and awards were validation-only. Neither selected weights
  nor linkers.
- Diagnostic Overall sensitivity changed no frozen weight and published no ranking.
- Output fingerprint: `a2056a6d793b2f82066c07bc4924787d3e95f8485ef37ff15911bfb7a321deb7`.

## STEP-0015N Final Overall V2 promotion audit

- **Reconstruction:** STEP-0015K/L/M fingerprints and frozen data hashes verified; exact
  Peak/Longevity path reconstruction maximum difference 0.0.
- **Coupling candidates:** independent, pooled Gaussian-copula, evidence-pattern Gaussian-copula,
  and empirical-rank diagnostic. Pattern-specific Gaussian coupling was frozen before rank output.
- **Dependence:** target/reproduced mean latent-rank correlations are 0.4328/0.4307 for
  Defense–Peak and 0.1937/0.1977 for Defense–Longevity. Sorted Defense marginals are exact.
- **Calibration population:** 1,197 rich-reference careers. Full-reference MAE/rho/bias is
  0.457/0.9995/-0.028; partial Presence is 1.383/0.9950/+0.240. Mixed evidence is
  2.003/0.9914/+0.111 and misses the MAE gate without rounding.
- **Status result:** 312 official, 284 provisional, 1,286 interval-only, 3,221 unavailable.
  The archived V1 Top 100 contains 3 official, 14 provisional, and 83 interval-only cases.
- **Decision:** `PASS + DO_NOT_PROMOTE_OVERALL_V2`. No V2 Top 100 or transition table is
  published; Overall V1 remains frozen.
- **Optimization target:** calibration and evidence semantics only. No player names, conventional
  ordering, confidence penalties, or player-specific adjustments enter selection.
- **Output fingerprint:** `b6248062490ca6b2d63e616af5ac759a59abc9ea3e9dc15dd4f2bd264741bb95`.

## STEP-0015O Interval-native ranking policy audit

- **Question:** can calibrated Overall distributions support honest cross-era ranking statements
  even when an exact point or exact ordinal rank is not ranking-grade?
- **Population:** 1,197 reference careers under six controlled evidence patterns; 1,882 actual
  distribution-rankable careers; all 100 archived V1 Top-100 players are distribution-rankable.
- **Deterministic candidates:** central Overall sort, median rank, expected rank, and probabilistic
  Borda/expected wins. No method passed all frozen rank-correlation and Top-N overlap gates.
- **Uncertainty:** player-grouped signed conformal calibration achieved 90% rank-band coverage from
  90.14% to 92.23% across patterns. Mean width increased with weaker evidence.
- **Membership probabilities:** Top-10/25/50/100 Brier scores remained below 0.024 and weighted
  expected calibration error below 0.009 across patterns.
- **Pairwise probabilities:** directional Brier ranged from 0.0080 to 0.0503; calibrated thresholds
  are 90% strong, 65% lean, and 35%–65% indeterminate. The bounded cycle audit found no lean or
  strong cycles.
- **Fairness:** mixed-evidence broad-role signed bias remained below 0.75 percentile rank;
  traditional-only evidence retained approximately 1.8-percentile guard/big distortion and is not
  suitable for exact rank publication.
- **Outcome:** `PASS + VALID_PROBABILISTIC_RANKING_ONLY`; Overall V2 remains not ready under the
  binding permanent exact-Top-100 product requirement. No Top 100 is emitted.
- **Optimization target:** calibration only. Player names, V1/conventional ordering, awards,
  championships, and outcomes never select the policy.
- **Output fingerprint:** `544843af8d316c6b5d54786b29562451ce01e3f6b5c35a0fe936e27fa2290a15`.
