# STEP-0015M — Defense V2 tiered measurement and promotion audit

Date: 2026-09-16

Status: **PASS**

Defense verdict: **PROMOTE_DEFENSE_V2_WITH_LIMITATIONS**

Recommendation: **READY_FOR_FINAL_OVERALL_V2_PROMOTION_AUDIT**

## Objective

Determine whether the individual-attribution improvement from STEP-0015A/B can be promoted using
the later evidence-form linking and uncertainty infrastructure, without predicting missing
Presence, converting missing evidence to zero, or replacing published V1 outputs.

## Binding constraints

- Defense means Regular Season opponent offensive value helped prevent.
- Individual impact is primary; team suppression is context.
- DREB/TRB, steals, and blocks are action evidence interpreted by role without equal ceilings.
- Presence is observational and never predicted when missing.
- Awards and modern defensive metrics are validation only.
- Missing evidence changes uncertainty/status, not quality by penalty.
- Defense V1, Peak V2, tiered Longevity, Overall V1, Overall weights, and the archived Top 100 are
  immutable in this step.

## Inputs and reconstruction

Verified upstream fingerprints:

- STEP-0015A: `07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324`
- STEP-0015B: `103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f`
- STEP-0015H: `4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54`
- STEP-0015L: `cb740fc68a77df3cb30b68e854e413c670394638ff2bf7b47401b905c7a81580`

Defense V1 reconstructed across 5,103 players with zero mismatches and maximum numerical
difference 0.0. Candidate B also reconstructed with maximum difference 0.0. The STEP-0015B
continuous artifact (21,674 rows), STEP-0015H linking infrastructure, and STEP-0015L inputs were
fingerprint-verified.

## Evidence inventory

The factual recovered corpus contains 22,457 Regular Season player-seasons from 1946 through
2025. Coverage is Team Context 21,674; rebound/action 21,890; steals and blocks 19,173 each;
Presence 18,175; and reliable broad-role metadata 16,078. Presence is fully reliable in 15,616
rows, partially reliable in 2,559, and absent otherwise. Absence is never zero.

## Candidate architectures

- D0: V1's 65% Team Context / 35% actions; diagnostic and rejected because the team constant
  dominates individual attribution.
- D1: Candidate B's 30% Team / 30% actions / 40% Presence; improved individual attribution but
  retained material team inheritance and failed missing-Presence comparability.
- D2: bounded Team Context at 10%, 15%, or 20%, retaining the 3:4 action/Presence ratio.
- D3: the selected 10% bounded-team architecture with continuously reliability-weighted observed
  Presence; unavailable Presence weight becomes uncertainty and is never redistributed.

The selected rich form is:

`10% Team Context + 38.5714% Role-Aware Actions + 51.4286% observed Presence`

The action channel is 40% rebound evidence, 30% steals, and 30% blocks. Each primitive blends 65%
global era-relative percentile and 35% broad-role percentile when role metadata exist. Historical
TRB is an explicitly labeled proxy when DREB is unavailable.

## Team Context decision

Across the 13,923 rich-form anchors, score/team correlation rises from 0.186 at 10% Team Context to
0.272, 0.362, and 0.541 at 15%, 20%, and 30%. Between-team variance share rises from 10.93% to
14.36%, 19.34%, and 33.63%. Ten percent is selected on attribution grounds, not named-player order.

## Measurement forms and linking

Forms are factual combinations of full actions, rebound proxy, observed Presence, and Team
Context. `DEF_FULL` is the reference form, not truth. Weaker forms are measured without
renormalizing missing weights, then linked to the reference score scale.

Five-fold grouped-player cross-fitting is primary. Random-fold and era-block results are retained.
Candidate linkers are identity, linear, equipercentile, isotonic, and broad-role isotonic. The
simplest linker within 0.10 MAE of the best grouped result is selected.

Three season forms pass all point gates:

- actions + Presence but no Team Context: MAE 2.49, rho 0.9882;
- full actions + partial Presence: MAE 3.31, rho 0.9710;
- traditional rebound evidence + Presence: MAE 3.04, rho 0.9780.

No-Presence forms fail: full actions without Presence has MAE 12.78/rho 0.5764; traditional
without Presence has 13.32/0.5158. Context-only has 15.14/0.1760 and is unavailable because it
lacks individual evidence.

Split-conformal interval coverage is 89.91%–90.25% at the nominal 90% level across forms. Mean 90%
width ranges from 9.18 for action+Presence/no-context to 59.74 for context-only.

## Role and archetype audit

All point forms satisfy the absolute major-role bias gate of three points. Role conditioning is
selected only for traditional+Presence and context+Presence because it improves grouped-player
calibration. It does not constrain group means or final ceilings. Rebound-heavy, block-heavy,
steal-heavy, low-stock, Presence-heavy, strong-team/weak-action, and strong-action/weak-team
subgroups remain separately reported.

## Career aggregation and validation

Career Defense reuses the V1 aggregation interpretation: mean season Defense quality followed by a
fixed broad-high-recall ECDF. More seasons do not add Defense value, avoiding direct Longevity
credit. Player-grouped career conformal validation uses 1,984 rich-evidence careers.

No-Team-Context and partial-Presence patterns pass the career point gates at MAE/rho 3.19/0.9889
and 4.61/0.9766. Traditional+Presence narrowly fails MAE and >10-error gates at 5.71 and 18.25%.
No-Presence, traditional-only, and mixed-transition patterns fail clearly and remain interval-only.

Independent-season, evidence-form-block, and player-block uncertainty propagation were compared.
Their mean career 90% widths are 9.62, 13.34, and 15.77 points respectively. Player-block plus
player-grouped career conformal calibration is selected because repeated within-player measurement
error makes the independent baseline anti-conservative; status is decided by held-out career
calibration, not width alone.

Actual career statuses:

- `OFFICIAL_DEFENSE_POINT`: 1,746
- `PROVISIONAL_DEFENSE_POINT`: 336
- `DEFENSE_INTERVAL_ONLY`: 2,093
- `DEFENSE_UNAVAILABLE`: 928

Among 582 active-to-cutoff players, counts are 325 official, 68 provisional, 125 interval-only,
and 64 unavailable. Active status itself does not alter score or status rules.

Actual season statuses:

- `OFFICIAL_DEFENSE_POINT`: 13,923
- `PROVISIONAL_DEFENSE_POINT`: 3,812
- `DEFENSE_INTERVAL_ONLY`: 4,595
- `DEFENSE_UNAVAILABLE`: 127

## Effective influence and attribution

Rich-form covariance shares are Presence 90.29%, Team Context 4.34%, rebound 2.79%, blocks 1.47%,
and steals 1.11%. Team Context is non-dominant. Presence's effective dominance is documented as a
limitation: it is the principal individual-impact channel but remains observational.

Selected-V2 near-identical season credit is 3.52% among adjacent same-team-season comparisons;
actions differentiate 87.67% and Presence differentiates 62.30%. Prior common-pair near-collision
counts were V1 1,332, Candidate B 142, and continuous candidate 78 of 11,780.

## Validation

Modern defensive rating remains a weak and noisy validator. Spearman is 0.1355 for V2 and 0.2813
for V1, so modern agreement does not support strong causal claims. It did not select the formula.

DPOY and All-Defense remain validation-only. Among 27 resolved DPOY players, 85.19% are at or above
Defense P90 and 74.07% at or above P95. The 187 All-Defense players have median V2 Defense 91.26.

Mean adjacent-season movement is 13.19 points at form transitions and 14.99 within the same form.
Thus linking does not create a larger average transition cliff, though individual intervals widen.

## Diagnostic players

The frozen post-selection audit explains the prior examples mechanically:

- Stephen Curry: V1 61.64, Candidate B 75.73, continuous candidate 73.66, V2 center 86.22,
  provisional. Reduced inherited team credit and observed Presence/actions drive the change.
- Kobe Bryant: V1 61.53, Candidate B 64.96, continuous candidate 59.76, V2 center 71.80 with a
  68.58–73.32 90% interval, interval-only because his career mixes evidence forms.
- Rudy Gobert: V1 98.98, Candidate B 99.36, continuous candidate 99.59, V2 center 99.11 with a
  98.30–99.11 interval, interval-only under the conservative mixed-career policy.

These movements did not influence formula or status selection.

## Joint uncertainty and Overall sensitivity

Matched career residual correlations are Defense–Peak 0.345–0.576 and Defense–Longevity
0.144–0.267. Independent dimension draws are rejected. Direct U3/Defense draw alignment is not yet
available; the next step should use pattern-specific empirical copula rank alignment while
preserving marginal draws and these correlations.

Replacing fixed V1 Defense diagnostically in STEP-0015L changes the mean common-player Overall
center by +0.217, expands mean 90% width by 0.428, and produces rho 0.9840. This is sensitivity only.
No Overall weight, score, rank, or Top 100 is promoted.

## Tests and result

The pipeline is offline and deterministic. Tests cover V1/Candidate reconstruction, missing
Presence semantics, Team Context cap, form/status rules, point gates, nested intervals,
interval-only downstream protection, archived Top-100 order, and frozen V1 preservation.

**Result: PASS + PROMOTE_DEFENSE_V2_WITH_LIMITATIONS**

The next step is a final Overall V2 promotion audit that aligns Defense, Peak, and Longevity
uncertainty without renormalizing weights or publishing a ranking unless every promotion gate
passes.
