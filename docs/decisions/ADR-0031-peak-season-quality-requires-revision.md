# ADR-0031: Peak V1 requires season-quality revision before promotion

## Context

The frozen V1 Peak score asks for the highest sustained overall basketball level and combines 70% best complete contiguous three-season quality with 30% single-season apex. STEP-0015C reconstructed every one of the 5,103 frozen Peak rows exactly and found no implementation error in the window or ECDF layers.

The underlying season-quality construct, however, is a nested stronger/secondary combination of Offense and V1 Defense. V1 Defense contains 65% era-relative team scoring suppression. Because the stronger outer axis receives 65%, the same team-season constant can realize either 22.75% or 42.25% of season quality. Across observed seasons its mean realized weight is 34.34%, its covariance-allocated variance share is 30.17%, and removing it changes season-quality percentiles by 13.53 points MAE. Its within-team-season variance is zero, while 104,097 of 133,105 audited teammate pairs receive identical team credit.

Observed-feature renormalization also changes the construct by evidence regime. Masking steals and blocks on rich-data seasons changes percentiles by 2.10 points MAE; masking shooting efficiency changes them by 3.29; removing team context changes them by 13.53. Missing values are not converted to zero, but the weights of the remaining evidence expand.

## Decision

Classify frozen Peak V1 as `REQUIRES_REVISION`. Keep `goatlab-v1-dimension-scores-v1` and `goatlab-v1-overall-v1` unchanged as reproducible historical baselines.

Preserve the 70/30 three-year/apex architecture for future work unless a separate audit demonstrates a window-layer defect. The material problem is the season-quality measurement layer, not the window blend or monotone ECDF mapping.

Retain `goatlab-v1-peak-v2-research` only as a counterfactual. Its strongest tested architecture requires both season Offense and role-aware individual action evidence, combines the stronger channel at 65% with the secondary at 35%, then applies the unchanged 70/30 Peak window blend. It removes team context and award/postseason leakage, but it is not promoted because only 1,761 reference players receive scores, historical action evidence remains a proxy for total defense, and missing role/action coverage produces implausible window selection for some long careers.

## Alternatives considered

- Keep V1 unchanged: rejected as a future production method because a team-season constant is the largest realized primitive in an individual Peak measure.
- Change only the 70/30 window blend: rejected because 60/40, 70/30, and 80/20 are rank-near-identical and the existing implementation correctly requires complete contiguous windows.
- Remove team context and retain current unadjusted actions: useful diagnostic, but the same action-proxy and historical-coverage limitations remain.
- Substitute unpromoted Defense V2: rejected because STEP-0015B did not establish a portable fallback for missing Presence evidence.
- Promote the role-aware action research candidate: rejected because it materially reduces cross-era coverage and does not yet measure the full defensive side of season value.
- Use awards or postseason evidence: constitutionally prohibited as Peak inputs.

## Consequences

No published Peak or Overall score changes in STEP-0015C. A future promotion step must construct and validate a portable individual season-value measurement model, explicitly calibrate evidence regimes, and then audit its coverage before replacing Peak V1. The 70/30 window layer may be reused.

## Status

Accepted in STEP-0015C. Audit result: `PASS`. Constitutional verdict: `REQUIRES_REVISION`.
