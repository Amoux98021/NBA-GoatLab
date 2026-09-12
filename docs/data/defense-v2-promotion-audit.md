# Defense V2 Promotion Audit

Audit methodology: `goatlab-v1-defense-v2-promotion-audit-v1`  
Candidate: `goatlab-v1-defense-v2`  
STEP result: **PASS**  
Promotion verdict: **DO_NOT_PROMOTE**

Deterministic output fingerprint: `103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f`

## Reconstruction

Candidate B was recreated for all 5,103 players. Career raw values, final scores, 28,817 team-season Presence rows, 17 predetermined stress cases, and the 17,089-player-season hard-eligibility set match STEP-0015A exactly. Every maximum numerical difference is zero. The frozen Dimension and Overall fingerprints also match.

## Why promotion is blocked

On 12,875 known full-evidence player-seasons, hiding Presence and renormalizing team/actions creates 10.72 Defense-point MAE, 12.99 RMSE, and 1.20 points of downward bias. Errors exceed 10 points in 48.29% of cases and 15 points in 26.94%.

A player-grouped five-fold ridge fallback uses only team context, role-aware actions, their interaction, and broad role. It reduces full-score MAE to 9.90 and removes aggregate bias, but direct Presence prediction remains weak: Spearman 0.1366, Pearson 0.1321, out-of-fold R-squared 0.0174, and Presence-percentile MAE 0.2475. The fallback compresses the extremes and still misses by more than 10 score points in 49.40% of masked seasons. Career averaging improves MAE to 6.38, but cannot prove that unavailable and observed Presence seasons share one construct.

Role-specific expected-fallback signed errors are small—big +1.3, forward -0.9, guard +1.0, wing +0.8 points—but large individual errors remain within every role. There is no strong mean role bias, yet calibration is not sufficiently precise for promotion.

## Evidence regimes and continuity

- Removing steals/blocks while retaining rebound and Presence changes the full score by 2.50 points MAE with Spearman 0.983.
- Replacing DREB/role evidence with global total-rebound proxies changes it by 1.00 point MAE with Spearman 0.997.
- Removing Presence causes 10.72 points MAE with Spearman 0.707. Presence—not action-era variation—is the unresolved bridge.

The former hard eligibility rule can create a simulated jump as large as 14 points. Smooth reliability blending reduces the corresponding maximum neighboring-threshold jump to 3.6 points. This is a meaningful continuity improvement, but does not repair the weak fallback.

## Attribution, role, and external validation

Aligned career correlation with team context falls from 0.9165 under V1 to 0.6572 for Candidate B and 0.6317 for the continuous candidate. Between-team season variance falls from 0.9037 to 0.5421 and 0.4485. Teammate near-collisions below a 0.02 raw gap fall from 1,332 to 142 and 78. The individual-attribution defect is therefore materially reduced.

Role means do not become equal and no equal-ceiling constraint is used. Candidate role means remain approximately 48.79 big, 46.86 wing, 44.22 forward, and 41.56 guard. Existing modern defensive evidence remains weak: Spearman 0.2813 V1, 0.2501 Candidate B, and 0.2508 continuous candidate. Awards are post-construction validation only; the candidate places 77.78% of DPOY-recognized players and 51.34% of All-Defense-recognized players at or above P90.

## Ranking counterfactual

The continuous fallback counterfactual ranks the same 1,882 complete profiles and preserves Overall Spearman 0.9946. Top-10/25/50/100 overlaps are 0.80/0.84/0.90/0.92. Kevin Garnett and Chris Paul enter the diagnostic Top 10; Scottie Pippen and Kareem Abdul-Jabbar leave it. The changes are mechanically traceable to lower inherited team credit plus Presence/fallback evidence, but the fallback is not sufficiently validated to publish those changes.

No player identity, award, external ranking, or reputation entered formula or promotion selection.

## Conclusion

Defense V2 fixes the primary attribution problem but fails the universal fallback gate. Candidate B and the continuous blend remain experimental. The next Defense iteration should focus on a better portable individual-impact bridge or an explicit evidence-regime measurement model before any Defense/Overall promotion.
