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
