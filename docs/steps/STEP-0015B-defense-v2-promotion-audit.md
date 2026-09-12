# STEP-0015B — Defense V2 promotion audit

## 1. Objective

Determine whether STEP-0015A Candidate B can replace frozen Defense V1 without introducing evidence-regime discontinuity, missing-Presence bias, or non-reproducible ranking changes.

## 2. Motivation

STEP-0015A showed that V1 requires revision because its majority input is a team-season constant. Candidate B improved individual attribution but explicitly renormalized its remaining channels whenever 40% Presence evidence was unavailable. Promotion therefore required a direct masking and continuity audit.

## 3. Inputs and constitutional requirements

Verified fingerprints: Dimension `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`, Overall `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`, and STEP-0015A `07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324`. The Constitution requires missingness protection, separate confidence, regular-season ownership, no awards, no modern leakage, and no player-specific optimization.

## 4. Work performed

- Reconstructed Candidate B and every recorded intermediate exactly.
- Masked known Presence overall, by role, and by evidence archetype.
- Simulated early evidence regimes and audited 9/10-with and 4/5-without threshold boundaries.
- Tested direct renormalization, continuous reliability, cross-validated expected Presence, and a conservative continuous hybrid.
- Rechecked team attribution, teammate collisions, role distributions, modern/award validation, temporal jumps, predetermined players, and Top-15/Top-10 effects.
- Produced dedicated counterfactual Gold without mutating V1.

## 5. Files created or changed

Implementation: `src/goatlab/rankings/defense_promotion.py` and `pipelines/rankings/audit_defense_v2_promotion.py`. Tests: `tests/test_defense_promotion.py` and `tests/test_defense_promotion_artifacts.py`. Decision: ADR-0030. Generated Gold stays ignored under `data/gold/defense_v2_promotion_audit/`.

## 6. Reconstruction and masking

All 5,103 Candidate B player outputs reproduce exactly; raw, score, Presence, stress-case, and eligibility differences are zero. Masking Presence on 12,875 full-evidence seasons yields 10.72-point MAE for renormalization. The best simple expected-Presence fallback yields 9.90-point MAE but 49.40% of estimates still differ by more than 10 points. At career level its MAE is 6.38.

The grouped five-fold ridge fallback has direct Presence R-squared 0.0174 and Spearman 0.1366. It is interpretable and leakage-free but does not adequately predict the missing channel.

## 7. Role, era, and threshold sensitivity

Expected-fallback mean signed errors are within 1.3 points across the four broad roles, so no large mean role bias is detected. Error dispersion remains substantial within each role. Pre-STL/BLK masking has 2.50-point MAE; reduced DREB/position metadata has 1.00; removing Presence has 10.72. The unresolved portability problem is specifically Presence.

Continuous blending reduces the maximum simulated threshold jump from 14.0 to 3.6 points and expands mathematical Presence estimates from 17,089 hard-eligible to 21,786 player-seasons. It improves continuity but not fallback identifiability.

## 8. Attribution, validation, and ranking effects

Career team-context correlation falls from 0.9165 V1 to 0.6572 Candidate B and 0.6317 continuous candidate. Between-team variance falls from 0.9037 to 0.5421 and 0.4485. Teammate near-collisions fall from 1,332 to 142 and 78. Attribution materially improves.

Modern validation remains weak and effectively unchanged; awards remain validation-only. The final counterfactual has Overall Spearman 0.9946 and Top-10/25/50/100 overlap 0.80/0.84/0.90/0.92. These are diagnostics, not a promoted ranking.

## 9. Decision and rejected alternatives

**DO_NOT_PROMOTE.** Direct renormalization changes the construct. The cross-validated expected-Presence model is slightly better in aggregate but explains too little Presence variance and produces too many large season errors. Smooth reliability fixes the threshold cliff but cannot supply missing information. Treating missing Presence as zero, using awards, or injecting modern metrics is constitutionally prohibited.

No official Defense V2 or Overall V2 version is created. `goatlab-v1-defense-v2` remains a research candidate; V1 remains the frozen historical baseline while retaining its `REQUIRES_REVISION` verdict.

## 10. Validation and reproducibility

Tests cover exact reconstruction, continuous reliability, missing-not-zero semantics, grouped deterministic ridge fallback, score bounds, confidence separation, Regular Season ownership, no award/modern/postseason input, frozen outputs, and deterministic counterfactual handling. The full suite passed with 177 tests and one opt-in network test skipped. Strict Mypy passed for 26 source files, Ruff lint passed, and all four STEP-0015B Python files passed format validation. A second offline build reproduced all five Gold hashes and committed report hashes exactly at fingerprint `103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f` with zero network requests. Generated Gold totals 2,473,859 bytes; the certification run took 18.21 seconds.

## 11. Result

**PASS.** The promotion audit is complete and reproducible. The separate promotion verdict is **DO_NOT_PROMOTE**.

## 12. Known limitations

Game presence is not lineup RAPM; venue and possession context remain unavailable; missing-game selection and teammate confounding remain; broad role covers only 69.9%; the modern validator is noisy and team-dependent; the portable fallback has minimal predictive power; some large temporal jumps coincide with coverage transitions.

## 13. Next step

STEP-0015C should audit Peak as requested while leaving Defense V1/V2 frozen. A subsequent dedicated Defense architecture step should test latent evidence-regime calibration or additional project-owned portable attribution evidence before revisiting promotion.
