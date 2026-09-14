# Historical Evidence Bridge Audit V1

Methodology: `goatlab-v1-historical-evidence-bridge-audit-v1`

Upstream research methodology: `goatlab-v1-player-season-value-v2-research`

## Verdict

`NO_VALID_BRIDGE`

No tested sparse-evidence regime passes every predeclared point-score gate. The best result is
expanded box evidence without Presence: Spearman 0.9531, but MAE 7.27 and 29.87% of observations
more than ten points from the full-evidence score. The traditional-box mask has MAE 8.00 and
Spearman 0.9405. Early evidence with Presence has MAE 8.41; early-minimal evidence has MAE 11.35.

The bridge therefore cannot claim that the same latent player-season value has been recovered.
Candidate D remains research-only and unchanged.

## What is missing

The 5,881 early-limited rows include 5,863 without APG creation evidence, 5,242 without even a
rebound/action proxy, 5,321 without TS, and 2,074 without observed Presence. In 4,311 rows the
only usable individual performance anchor is PPG; team suppression is shared context and cannot
stand in for individual defense. Another 783 rows lack team context as well.

These are mostly structural source gaps, not random missing cells.

## Creation bridge

PPG alone predicts era-relative APG only moderately. Player-grouped ridge gives R² 0.5043,
Spearman 0.7097, and APG-percentile MAE 16.63. Adding TS moves R² to 0.5313 and MAE to 16.13.
Decade-block results are essentially unchanged, showing that the limitation is information rather
than same-player leakage. These estimates can support uncertainty analysis but not substitute for
observed creation.

## Defensive bridge and invariance

Actions alone have only Spearman 0.7315 against the complete defensive measurement; adding team
context raises it to 0.7515. Player-grouped predicted defense has Spearman 0.7606 without Presence,
0.6808 in the traditional mask, 0.7204 with only Presence plus team context, and 0.1710 with team
context alone.

The pooled one-factor model explains only 36.51% of channel variance. Its loadings are not stable:
the cosine similarity with the pooled loading vector falls to 0.5933 in the 2000s, and the team
loading changes sign in the 1990s. This is direct evidence against measurement invariance, not a
reason to force a latent score into every era.

## Uncertainty

Empirical grouped-mask residual intervals attain their nominal calibration by construction, but
they are wide. Mean 90% widths are 26.92 points for expanded box, 30.21 for traditional box,
33.37 for early evidence with Presence, and 42.30 for early-minimal evidence. Interval coverage
does not make the midpoint a valid point score.

Of 22,457 qualified seasons, 16,576 retain observed Candidate D research scores, 5,098 receive
diagnostic interval-only records, and 783 remain unavailable.

## Continuity and era behavior

Candidate D itself has 2,543 adjacent same-player regime transitions. Their mean absolute change
is 14.30 points versus 14.58 within the same regime. This does not show an average transition
cliff, but individual transitions can be large and the scored-regime distributions differ
materially. The result is diagnostic because performance, team changes, and missingness can move
together.

## Downstream effect

No failed bridge midpoint enters Peak or Longevity. Reproduced Candidate D yields 1,761 Peak
scores (Spearman 0.9057 to V1) and 2,950 Longevity scores (Spearman 0.7832 to V1). These remain the
unchanged STEP-0015D counterfactuals, not publishable replacements.

## Policy

Full research scores, provisional evidence, interval-only estimates, and unavailable rows remain
separate states. The next methodology step should investigate additional historically factual
individual evidence or an interval-native cross-era framework; it should not tune the current
models until they barely cross numeric gates.
