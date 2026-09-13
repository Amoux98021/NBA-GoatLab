# Player-Season Value Measurement Audit

Methodology: `goatlab-v1-player-season-value-audit-v1`

Research candidate: `goatlab-v1-player-season-value-v2-research`

Status: **PASS + PROMISING_BUT_NOT_READY**

## Target construct

PlayerSeasonValue means **overall regular-season individual basketball value for one
player-season**. It is a shared analytical primitive for future Peak and Longevity work, not an
eighth GOAT dimension. It excludes postseason performance, team outcomes, awards, championship
events, player identity, reputation, and future projection.

## Inputs and preservation

The offline audit verifies the frozen Constitution, STEP-0014 dimension, STEP-0015 Overall,
STEP-0015B Defense-promotion, and STEP-0015C Peak-forensic fingerprints before work begins. It
uses 22,457 qualified Regular Season rows for 5,103 players. Published V1 SeasonQuality, Peak,
Longevity, Defense, and Overall outputs are unchanged.

## Evidence inventory and regimes

PPG is observed on all 22,457 rows. Team suppression covers 96.51% but is team-shared. Observed
Presence covers 80.93%; role-aware actions 75.82%; RPG 76.66%; TS 76.31%; APG 73.89%; SPG
72.62%; and BPG 72.73%. Games affect qualification/confidence only. Minutes remain coverage-gated
and do not enter value.

Regimes are assigned from observed channels, not a hard-coded season date:

| Regime | Player-seasons | Players | Share | Observed seasons |
|---|---:|---:|---:|---|
| Early limited | 5,881 | 1,589 | 26.19% | 1946–1990 |
| Traditional box | 55 | 53 | 0.24% | 1982–1983 |
| Expanded box/no Presence | 2,153 | 887 | 9.59% | 1983–2025 |
| Full portable | 14,368 | 2,940 | 63.98% | 1982–2025 |

Date ranges overlap because row-level source availability and Presence identifiability vary within
a season. `EARLY_LIMITED` means the candidate cannot observe the channels required to place that
row on its proposed common scale; it does not mean low performance.

## Candidate families

1. **A — corrected transparent portable.** V1 stronger/secondary offense; defense is 75% current
   actions and 25% team context; total is fixed 65% offense/35% defense. Coverage is 17,027 rows
   (75.82%), with team context at 8.75% of total value.
2. **B — multi-path bounded team.** Offense uses 60/40 stronger/secondary scoring and creation;
   defense is 75% role-aware actions/25% team; total is 60/40 stronger/secondary offense and
   defense. Coverage is 16,576 rows (73.81%), but team context can reach 15% of total value.
3. **C — complete-evidence measurement benchmark.** Offense uses 60/40 scoring/creation; defense
   is 50% role-aware actions, 10% team context, and 40% observed Presence; total uses 55/45
   stronger/secondary axes. It is observed-only, not a latent estimate. Coverage is 14,368 rows
   (63.98%).
4. **D — evidence-regime reliability research candidate.** Offense uses 60/40 scoring/creation.
   Defense reserves 10% for team context, assigns up to 35% to observed Presence continuously by
   reliability, and leaves unused Presence weight on individual action evidence. Offense and
   defense combine at bounded 55/45 stronger/secondary weights. Coverage is 16,576 rows (73.81%).

Candidates are highly related (pairwise Spearman 0.946–0.995 on common rows), but this does not
establish cross-regime equivalence. Candidate D is retained only because it caps total team
context at 5.5%, uses continuous Presence reliability, and keeps confidence separate. It is not
promoted.

## Offensive and defensive findings

O1 can fall back to scoring alone and therefore covers all rows, but that changes the offense
construct when creation is absent. O2 and O3 require both scoring and APG and cover 73.89%. Across
their observed overlap, O3 realizes approximately 50.33% scoring and 49.67% creation weight because
the stronger axis varies by player-season.

The earlier expected-Presence bridge remains invalid: player-grouped out-of-fold R-squared is
0.0174. Candidate C therefore serves only as the full-observation benchmark. Candidate D does not
claim missing Presence is observed or latent; it uses weaker action evidence with lower confidence.
That approach improves attribution but does not solve historical comparability.

## Masking and calibration

The 14,155 richest player-seasons form the controlled masking set. Against Candidate C's
full-evidence value:

| Mask | MAE | RMSE | Spearman | Pearson | >5 | >10 | >15 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full portable | 0.00 | 0.00 | 1.000 | 1.000 | 0.00% | 0.00% | 0.00% |
| Expanded box/no Presence | 5.73 | 7.11 | 0.949 | 0.945 | 49.14% | 16.91% | 3.27% |
| Traditional box | 8.48 | 10.36 | 0.904 | 0.901 | 65.80% | 35.93% | 15.42% |
| Early limited | unavailable | unavailable | — | — | — | — | — |

The no-Presence mask is negatively biased for guards (-1.54 points) and wings (-0.53), nearly
neutral for bigs, and modestly negative for forwards. Traditional-box masking instead biases bigs
upward by 4.29 points and guards downward by 5.67. Archetype and team-context bands show further
non-uniform errors in the machine-readable report. Simple fallback therefore does not establish a
single historical construct.

## Effective influence and team context

Candidate D realizes 50.11% offense and 49.89% defense weight on average. Their covariance-allocated
variance shares are 63.47% and 36.53%. Mean primitive formula weights are APG 25.01%, PPG 16.31%,
Presence 14.39%, RPG allocation 12.21%, SPG allocation 9.15%, BPG allocation 9.15%, TS 8.78%, and
team context 4.99%. The action allocations explain the role-aware composite and are not causal raw
event shares.

Team context has only 0.13% covariance-allocated variance share, 0.071 correlation with value, and
a 5.5% maximum total coefficient. Candidate D materially fixes V1's team-context domination at the
formula level, but the weak Presence bridge prevents production use.

## Fairness and continuity

Season-relative ECDF means remain 50 by decade, as expected. Within mixed coverage regimes,
full-portable rows average 46.78 while no-Presence rows average 71.13; this is partly an
identifiability/participation selection pattern and is a warning against reading regime differences
as player quality. Observed role means are guard 54.19, wing 51.14, forward 47.52, and big 46.66;
the audit does not enforce equal role means.

Across 12,754 adjacent observed seasons, value Spearman is 0.7700. Mean absolute change is 14.53
points overall, 14.30 across regime changes, and 14.58 within the same regime. Team-change pairs
move more (16.64) than same-team pairs (13.47). Large regime-transition examples remain flagged;
the report does not claim those changes are entirely measurement artifacts.

## Validation and downstream diagnostics

Validation was performed only after formulas were frozen. The 43 observed MVP seasons average the
98.60th percentile and 97.67% are at or above P90. The 215 observed All-NBA First Team seasons
average 97.22 and 93.95% are at or above P90. Awards never enter scoring.

The unchanged 70/30 Peak architecture yields 1,761 candidate Peak scores. Against V1 Peak,
Spearman is 0.9057 and Top-25/50/100 overlap is 52%/54%/59%. The unchanged 35/40/25 Longevity
architecture yields 2,950 scores; Spearman is 0.7832 and Top-25/50/100 overlap is 68%/68%/71%.
Candidate Peak–Longevity Spearman is 0.8691 versus 0.8957 under V1; the constructs remain related
but are not identical.

The Peak-only frozen-weight Overall counterfactual is available for 1,391 common ranked players.
It has 0.9937 Spearman and Top-10/25/50/100 overlap of 90%/96%/90%/95%. This is diagnostic and does
not replace Overall V1.

Predetermined player traces are published whether or not their movement resembles conventional
opinion. Early careers such as Bill Russell, Wilt Chamberlain, and the pre-1980 portion of Kareem
Abdul-Jabbar remain unscored by the candidate; that coverage failure is decisive.

## Verdict

**PROMISING_BUT_NOT_READY.** Candidate D better represents individual evidence and sharply bounds
team inheritance. It fails production gates because early-mask coverage is 0%, total candidate
coverage is only 73.81%, no valid latent defensive bridge exists, and mask errors are role- and
evidence-regime-dependent. No production methodology version, Peak V2, Longevity V2, Defense
change, or Overall change is created.

The deterministic output fingerprint is
`f96ee13b7aa7ba6101e2ad80b757cc28179a52b378cbd961ceb3f739bdcae282`. Five ignored Gold files
contain 37,788 rows in total and occupy 2,275,129 bytes. The certification run took 7.15 seconds
and reproduced every Gold/report hash with zero network requests. The full suite passed 206 tests
with one opt-in network test skipped; Ruff and strict Mypy passed.

## Next step

Develop a dedicated evidence-regime bridge for the historically missing creation and defensive
channels. The next audit should test whether uncertainty-aware calibration can map sparse-era
evidence to the full construct without simple weight renormalization. Peak and Longevity promotion
must wait for broad coverage and passed masking gates.
