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
