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
