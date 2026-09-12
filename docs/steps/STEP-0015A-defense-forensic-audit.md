# STEP-0015A — Defensive methodology forensic audit

## 1. Objective

Determine whether frozen V1 Defense measures player-attributable opponent value prevention, quantify role/team/scale effects, and test a historically portable player-presence alternative without changing published V1 outputs.

## 2. Motivation

V1 assigns 65% to team suppression. Diagnostic player scores prompted a construction audit, not targeted correction. The Constitution requires individual defensive value, multiple evidence channels, missingness protection, regular-season ownership, and awards used only for validation.

## 3. Constitutional requirements and inputs

The binding machine Constitution, STEP-0014 fingerprint `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`, and STEP-0015 fingerprint `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa` were verified. Frozen Silver/player-game/team facts and regular-season Gold were used offline. DPOY/All-Defense and modern advanced Defense were validation only.

## 4. Work performed

- Reconstructed all V1 Defense intermediates and scores.
- Added season/player decomposition, broad-role distribution, modern residual, team ICC/variance, and teammate-collision audits.
- Built an opponent-strength-adjusted, shrinkage-stabilized game-presence model with explicit minimum samples.
- Compared V1 with reduced-team, triangulated-presence, coverage-adaptive, and no-modern-correction families.
- Audited award enrichment, ECDF dispersion, predetermined player cases, and frozen-weight Overall counterfactual effects.

## 5. Files created or changed

Implementation: `src/goatlab/rankings/defense_forensics.py` and `pipelines/rankings/audit_defense_v1.py`. Tests: `tests/test_defense_forensics.py` and `tests/test_defense_forensic_artifacts.py`. Decision: ADR-0029. Generated Gold stays ignored under `data/gold/defense_forensic_audit/`. Committed reports include the forensic narrative, position/team/presence/candidate/scale/stress/counterfactual JSON, and summary.

## 6. V1 reconstruction and forensic result

All 5,103 outputs reproduce exactly with zero score difference. The implementation uses total RPG, not DREB. The team channel has ICC 1.0 and zero teammate differentiation; 89.92% of final player-season composite variance is between teams. Career raw Defense is more associated with team suppression (0.8661) than action evidence (0.4450). Of 9,171 substantial teammate-overlap pairs, 4,257 have action gaps >=0.25 but identical shared team credit.

## 7. Position, presence, and action evidence

Broad-role metadata covers 69.9%. Guards have a lower V1 mean (41.07) than bigs (50.51), but modern residual effects by role are small; the audit does not claim definitive residual positional bias. It does identify unequal observable evidence: DREB/BLK favor frontcourt roles while historical perimeter actions are absent.

The presence model qualifies 17,089 player-seasons. It requires 10 with/five without games and applies effective-sample shrinkage. Another 9,867 player-team-seasons remain insufficient/NULL. It is opponent-strength and season adjusted, trade-safe, and reproducible, but not home/away adjusted or possession-level RAPM.

## 8. Candidate formulas and decision

Candidate B is selected as experimental `goatlab-v1-defense-v2`: 30% team suppression, 30% action context, 40% Defensive Presence Impact. Action context is 40% DREB (total-rebound proxy only when DREB unavailable), 30% steals, 30% blocks, with a 65/35 global/broad-role evidence blend. Missing channels are explicitly reweighted and recorded; team context is required.

Alternatives were rejected because actions alone remain incomplete, heavier team anchors do not sufficiently solve attribution, modern defensive rating lacks a bridge, and full RAPM is not identifiable from game participation.

## 9. Validation, sensitivity, and scale

V1 modern defensive-rating Spearman is 0.2813 versus 0.2501 for B; neither is strong and the validator is team-dependent. B improves post-construction award enrichment without using awards. V1 Defense is the most dispersed dimension overall (SD 31.87) and within the Top 100 (SD 9.50). The V2 Overall counterfactual preserves Spearman 0.9958 but Top-10/25/50/100 overlaps are 0.70/0.88/0.94/0.95, large enough to require an explicit promotion step.

At the Defense-score level, B is materially distinct from V1 (Spearman 0.7876; Top-25/50/100 overlap 0.40/0.52/0.52). Counterfactual Overall mean rank shifts favor guards by 3.71 and wings by 2.15 while moving bigs -3.83 and forwards -3.39; this is reported as sensitivity, not treated as a fairness target.

## 10. Tests and reproducibility

Tests cover exact frozen reconstruction, missing action semantics, minimum presence samples, shrinkage, opponent-adjustment direction, role mapping, regular-season ownership, awards exclusion, bounded V2 scores, team attribution, and counterfactual-only status. The full offline suite passed with 164 tests and one opt-in network test skipped. Strict Mypy passed for 25 source files, Ruff lint passed repository-wide, all four STEP-0015A Python files passed Ruff format validation, and historical formatting drift in ten unrelated pre-existing files was left unchanged. A second offline run reproduced all six Gold partitions and committed analytical report hashes at fingerprint `07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324`. It made zero network requests. Gold size is 2,969,085 bytes and the certification run took 12.92 seconds on the recorded host.

## 11. Result

**PASS.** The forensic audit is complete and reproducible. The separate constitutional verdict is **REQUIRES_REVISION**. Published `goatlab-v1-dimension-scores-v1` and `goatlab-v1-overall-v1` remain unchanged; `goatlab-v1-defense-v2` is a counterfactual candidate only.

## 12. Known limitations

Historical role metadata is incomplete; defensive actions omit unrecorded positioning; game-presence contrasts retain teammate/selection confounding; low missed-game samples block estimates; venue is not in the portable game contract; modern/award validators are imperfect; V2 weights remain a documented judgment.

## 13. Next step

Recommended STEP-0015B: independently audit score-scale/effective-influence behavior and decide whether Defense V2 should be promoted. It should add venue/context sensitivity if feasible, re-run full Overall eligibility and effective-influence audits, and require an explicit new Dimension/Overall version rather than overwrite V1.
