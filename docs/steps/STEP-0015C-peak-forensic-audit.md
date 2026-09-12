# STEP-0015C — Peak methodology forensic audit

## 1. Objective

Determine whether frozen Peak V1 measures the highest sustained overall basketball level for constitutionally valid reasons, without changing Defense, published dimensions, or Overall V1.

## 2. Motivation

Diagnostic output placed Rudy Gobert Peak (`97.39`) above Stephen Curry (`95.56`) and Shaquille O'Neal (`92.75`). Player order was not a target. The audit traced the result from regular-season primitives through missingness, season quality, contiguous windows, and ECDF to determine what the model actually values.

## 3. Inputs and fingerprints

The audit verified Constitution `f7a67adb161de086e9d47b0eaa3b9606cfb42cc70f15341c2a225586403c6ad5`, STEP-0014 dimensions `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`, Overall V1 `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`, STEP-0015A `07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324`, and STEP-0015B `103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f`.

## 4. Work performed

- Reconstructed the nested V1 season-quality, 70/30 Peak, and ECDF chain exactly for all players.
- Materialized player-season primitive weights and contributions.
- Audited component covariance influence, leave-one-out changes, team inheritance, teammate collisions, missingness, evidence-regime and role masks.
- Validated contiguous windows, apex behavior, availability, specialist profiles, regular-season ownership, ECDF tail behavior, and awards as external evidence only.
- Traced 20 predetermined players and decomposed Gobert/Curry/Shaq component-by-component.
- Compared four research-only season-quality candidates and produced a non-published Overall counterfactual.

## 5. Exact season-quality methodology

V1 uses era-percentile PPG/TS to form Scoring at 65/35, combines the stronger of Scoring/APG at 65/35 into Offense, combines RPG/STL/BLK at 50/25/25 into Actions, combines TeamSuppression/Actions at 65/35 into Defense, and combines the stronger of Offense/Defense at 65/35 into season quality. Observed-feature renormalization applies at every eligible layer. Peak is then 70% best complete contiguous three-year mean and 30% apex.

## 6. Reconstruction result

All 5,103 rows match. Maximum differences for season raw value, season percentile, selected window, raw Peak, and final score are `0.0`. Frozen dimensions and Overall were not mutated. Five ignored Gold files record 22,457 season rows, 5,103 player decompositions, candidate scores, stress cases, and the Overall counterfactual.

## 7. Component and team-context findings

Mean realized weights are TeamSuppression 34.34%, PPG 26.63%, APG 19.10%, TS 7.02%, RPG 6.73%, BPG 3.10%, and SPG 3.09%. Covariance/Shapley shares are 30.17%, 32.26%, 24.67%, 4.26%, 4.83%, 1.11%, and 2.69% respectively.

Team suppression is a team-season constant with zero within-team variance, 97.65% between-team eta-squared, and 104,097 identical-credit teammate pairs. It has the largest leave-one-out season-percentile effect (14.28 points MAE). This is material individual-attribution contamination.

## 8. Missingness and era fairness

NULL never becomes zero, but renormalization changes realized meaning. On 16,308 full-evidence seasons, masking STL/BLK gives 2.10-point MAE, masking TS gives 3.29, and removing team context gives 13.53. Role-signed errors show that missing channels do not act neutrally across archetypes. V1 uses no modern advanced/possession inputs, so modern-portable and current-full masks are identical.

## 9. Window, apex, availability, and scale

The 70/30 layer is soundly implemented. Three-year/apex Spearman is `0.9512`; alternative 60/40 and 80/20 blends are rank-near-identical (`0.9996`). Gaps and nonqualified seasons invalidate windows. Games affect qualification/confidence only; minutes and total career duration do not enter quality. ECDF is monotone and preserves raw ordering, though it compresses the extreme tail.

## 10. Diagnostic player result

Gobert exceeds Curry and Shaq because his stronger defensive axis makes shared team suppression 42.25% of season quality through three elite Utah suppression seasons. Curry and Shaq have stronger offense, reducing the same component to 22.75%; Curry's team context declines across his window and Shaq has a `0.2143` middle-season suppression percentile. Removing team context flips both comparisons. No reputation or award evidence was used.

## 11. Candidate methodologies

- V1 baseline: current nested quality plus 70/30.
- A: current action evidence, no team context, stronger/secondary 65/35.
- B: explicit 60% Offense and 40% role-aware actions.
- C: stronger/secondary 65/35 Offense and role-aware actions.
- D: Offense plus the unpromoted Defense V2 diagnostic.

Candidate C best follows the multi-path individual-performance concept and removes the known team constant, but it scores only 1,761 reference players and lacks a complete defensive-impact bridge. It remains `goatlab-v1-peak-v2-research`, not a promoted method. No Overall version is changed.

## 12. Constitutional verdict and decision

**REQUIRES_REVISION.** V1's 70/30 window and ECDF layers are not the defect. Its season-quality layer gives a team-season constant the largest realized weight, inherits the known V1 Defense attribution limitation, and changes construct through evidence-dependent renormalization. ADR-0031 freezes that finding and explicitly declines to promote the incomplete research candidate.

## 13. Validation and tests

Offline tests cover exact formula reconstruction, missingness, required context, complete/gap-aware windows, deterministic ties, ownership, candidate non-promotion, frozen output preservation, bounded scores, and fingerprints. The full repository suite passed with 192 tests and one opt-in network test skipped. Ruff passed, strict Mypy passed for 27 source files, and all four STEP-0015C Python files passed format validation. The audit pipeline supplies artifact/data validation through exact upstream-fingerprint, reconstruction, schema, bounds, ownership, and deterministic-hash gates.

A second zero-network run reproduced all five Gold partition hashes and committed analytical report hashes exactly. The output fingerprint is `a9db1e7f75b3f3b8af9474bf556917b98f8aceeeb890fdc9ba36bdf7c3de7287`; generated Gold is 3,001,220 bytes across five files, and the certification run took 35.09 seconds.

## 14. Result

**PASS.** The forensic audit is complete. PASS describes audit execution; the separate Peak constitutional verdict is **REQUIRES_REVISION**.

## 15. Known limitations

Role-aware defensive actions are not total defensive impact; early-era role/box evidence remains incomplete; V1 team context is measured at a primary-team level for traded seasons; the research candidate sacrifices substantial historical coverage; awards are imperfect validators; ECDF tail compression remains a cross-dimension scale issue rather than a Peak-only fix.

## 16. Recommended next step

Run a dedicated Peak V2 promotion/measurement audit. Preserve the validated 70/30 window architecture, develop a portable individual season-value construct with explicit evidence-regime calibration, test offense/defense multi-path ceilings, and require broad historical coverage before promotion. Do not substitute the unpromoted Defense V2 directly.
