# STEP-0014 — Operationalize the GOAT Constitution into V1 dimension scores

## 1. Objective

Operationalize Peak, Longevity, Offense, Defense, Playoffs, Accolades, and Winning as interpretable, coverage-aware player scores on a common 0–100 scale without selecting an official Overall formula.

## 2. Motivation

STEP-0012 and STEP-0013 supplied candidate definitions and structural diagnostics but intentionally left normative choices open. The audited Constitution now binds those choices and requires reproducible formulas, explicit ownership, historical missingness protection, sensitivity analysis, and a modern-enrichment bridge test.

## 3. Constitutional requirements

- Preserve Silver facts and derive scoring artifacts only downstream.
- Use era-normalized evidence; never convert missingness to zero.
- Keep regular-season Offense/Defense distinct from individual postseason Playoffs and team-outcome Winning.
- Keep DPOY/All-Defense in Accolades, titles out of Offense, and championships out of Accolades.
- Make three-year Peak primary, cap extreme season influence in Longevity, bundle recognition within season, and apply one highest Winning tier per season.
- Treat confidence as evidence metadata, active careers as to-date, modern-only data as diagnostic absent a passing bridge, and Era Dominance as diagnostic only.
- Create no official Overall score, dimension weights, ranking, or player-specific adjustment.

The source attachment SHA-256 is `5aed7e5803f4045598c5fce57c58e95ef59d63627be5fc5736c2b7602c16b79b`. Its binding rules are preserved in `docs/constitution/GOATLAB_V1_CONSTITUTION.md`.

## 4. Inputs and fingerprints

- Corpus: `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`
- Era normalization: `a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852`
- Career: `5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b`
- Awards: `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258`
- Team success: `707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333`
- All-Star/stat leaders: `e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880`
- STEP-0012 candidates: `e5cd648afbc36306251ec1229b4c9f2beba830ca0ce93056c8e783e596bfc11f`
- STEP-0013 structural audit: `0f06e17c382de61a260dbd9eabb872a0613bf2c2146468c2a81bd454c4951093`
- Machine Constitution: `f7a67adb161de086e9d47b0eaa3b9606cfb42cc70f15341c2a225586403c6ad5`

No network request, source mutation, external ranking, target label, or player-specific correction was used.

## 5. Candidate formula families

Peak evaluated 60/40, 70/30, and 80/20 three-year/apex weights. Longevity evaluated P80/P85/P90/P95 thresholds with P90 season-credit cap and All-NBA calibration used only to assess meaningful season quality. Offense evaluated 60/40, 65/35, and 70/30 volume/efficiency. Defense compared portable suppression/rebounding with coverage-qualified action enrichment. Playoffs evaluated 60/25/15, 65/20/15, and 70/20/10. Accolades evaluated 55/40/5, 60/35/5, and 65/30/5. Winning evaluated 60/30/10, 65/25/10, and 70/20/10.

All candidate values were converted to 0–100 with midrank ECDF against the frozen 2,656-player broad-high-recall population.

## 6. Chosen V1 formulas

- Peak: 70% best complete contiguous three-year season-quality window, 30% apex.
- Longevity: 35% P80 breadth, 40% capped area P80–P90, 25% longest P80 run.
- Offense: 65% PPG + 35% TS joint scoring, followed by 65% stronger / 35% secondary scoring-versus-creation blend; qualified regular-season career mean.
- Defense: 65% team scoring suppression + 35% qualified individual action context; qualified regular-season career mean.
- Playoffs: 65% absolute quality + 20% bounded lift + 15% repeated elite evidence.
- Accolades: 60% bundled Major Honors + 35% bundled Sustained Recognition + 5% title support, with within-season and major/sustained cross-axis caps.
- Winning: 65% one highest participation-conditioned outcome tier + 25% sustained elite team context + 10% playoff breadth.

ADR-0025 governs the scale and constitutional authority. ADR-0026 governs formulas, ownership, and bridge decisions.

## 7. Rejected alternatives

Raw min-max scores, five-year universal Peak, uncapped Longevity positive-z, separate top-level volume/efficiency votes, STL+BLK or award-driven Defense, lift-primary Playoffs, flat award points, uncapped same-season awards, cumulative within-season playoff-tier credit, and universal modern-advanced bonuses were rejected for constitutional, coverage, redundancy, or era-fairness reasons. The selected formula was never chosen from famous-player ordering.

## 8. Coverage and confidence

The build creates 35,721 score records (5,103 players × seven dimensions), 133,995 component records, and 21 formula-sensitivity records. Available scores are Peak 2,456; Longevity 4,187; Offense 4,187; Defense 4,130; Playoffs 2,768; Accolades 2,140; and Winning 5,102. Exactly 1,882 players have all seven scores.

Every row carries coverage status, evidence confidence, relevant season/game counts, reason codes, career status, input fingerprints, and methodology version. The 2,963 unqueried Accolades records remain NULL/`NOT_QUERIED`. Confidence never changes quality.

## 9. Sensitivity

Peak alternatives have Spearman 0.9996; Offense alternatives at least 0.9996; Playoffs 0.9977–0.9997; Accolades at least 0.99998; and Winning at least 0.9992. Longevity is appropriately more sensitive: P85/P90/P95 correlations to selected P80 are 0.9275/0.8040/0.6332, with top-100 overlap 0.86/0.79/0.68. The calibration evidence selects P80 on a prespecified discrimination criterion, not player identity. Each alternative includes largest movers plus active-career, era, STEP-0013 archetype, and missingness diagnostics; position bias is explicitly unavailable because historical position coverage is not qualified.

## 10. Cross-dimension audit

On 1,882 complete players, key Spearman relationships are Peak–Longevity 0.9304, Peak–Offense 0.8027, Winning–Accolades 0.4128, Defense–Playoffs 0.2515, and Playoffs–Winning 0.3126. Residual variance unique to each dimension ranges from 8.3% Peak to 65.8% Winning. PCA's first four standardized-score components explain 60.18%, 15.46%, 8.58%, and 6.83%.

Five hundred fixed-seed random-simplex diagnostics show mean/minimum Spearman 0.9599/0.7404 versus an equal-weight diagnostic and mean/minimum top-50 overlap 0.821/0.56. These quantify effective-weight risk for STEP-0015; no diagnostic combination is official.

## 11. Era fairness and stress tests

All universal evidence is portable and already era-normalized. The action-enriched Defense bridge passes; modern per-75 Offense and advanced Defense remain non-scoring diagnostics. Position-bias testing remains blocked because historical position coverage is not qualified. Cohort score distributions and availability are reported without quota adjustments.

Bill Russell, Wilt Chamberlain, Kareem Abdul-Jabbar, Magic Johnson, Larry Bird, Michael Jordan, Hakeem Olajuwon, Shaquille O'Neal, Kobe Bryant, Tim Duncan, LeBron James, Stephen Curry, Kevin Durant, Nikola Jokic, Ben Wallace, and Rudy Gobert are diagnostic case studies only. Notable results reflect formula structure: defense specialists can be elite on Defense without strong Offense; early stars carry partial defensive/offensive evidence; active players are to-date; and team Winning remains distinct from individual Playoffs. No case changed a formula.

## 12. Known limitations

- Accolades remain candidate-scoped and block a complete seven-score output for 2,963 players.
- Portable Offense does not directly observe gravity/off-ball creation; portable Defense remains a proxy triangulation rather than an individual causal estimate.
- Peak and Longevity remain highly correlated despite clipping, because both legitimately derive from sustained season quality.
- Playoff evidence is sparse for many careers; sample size changes confidence, not quality.
- The common ECDF is reference-population relative and is versioned rather than metaphysically absolute.
- Position and detailed archetype bias tests are incomplete because the canonical position evidence has not passed historical qualification.

## 13. Tests and validation

Added unit and artifact assertions for deterministic scaling, ties, NULL semantics, complete/gapped Peak windows, Longevity clipping, playoff dominance, recognition capping, Winning hierarchy, score ranges, source ownership, regular/postseason separation, active-career cutoff semantics, modern leakage, sensitivity-bias completeness, report fingerprints, and structural audits. Validation completed with 140 tests passed and one opt-in network test skipped; Ruff passed; strict Mypy passed for all 23 package source files; changed files passed formatting checks; JSON, YAML, Parquet, Git-ignore, and whitespace validation passed. A second complete offline build reproduced fingerprint `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a` exactly with zero network requests.

## 14. Result

**PASS.** All seven constitutional dimensions are operationalized with explicit evidence ownership, score/coverage separation, full master-player rows, sensitivity and structural audits, and deterministic offline outputs. This status is valid only with the recorded successful validation run.

## 15. Next step

Recommended STEP-0015: audit effective influence and redundancy across the seven finalized scores, define provisional/unranked eligibility for missing dimensions, and select a transparent default Overall weighting methodology. It must not redistribute missing-dimension weight and must keep user-custom weighting separate from the default.
