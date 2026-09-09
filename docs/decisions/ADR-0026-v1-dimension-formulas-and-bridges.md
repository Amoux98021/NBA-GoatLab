# ADR-0026: V1 dimension formulas, ownership, and enrichment bridges

## Context

The Constitution requires seven distinct scores without turning correlated facts into repeated votes. Historical metric coverage differs sharply, while modern advanced evidence cannot automatically raise modern players' universal scores. STEP-0012 and STEP-0013 provided candidate and structural evidence but no final formulas.

## Decision

Adopt `goatlab-v1-dimension-scores-v1`:

- Peak: 70% best complete contiguous three-season quality and 30% single-season apex.
- Longevity: 35% elite-season breadth, 40% capped area above the empirically selected 80th-percentile season-quality threshold, and 25% longest contiguous run; season credit caps at the 90th percentile.
- Offense: season-level joint scoring value (65% PPG percentile, 35% TS percentile when available, with PPG required), combined with creation/APG through 65% stronger axis and 35% secondary axis; career mean over qualified regular seasons.
- Defense: career mean of 65% era-relative team scoring suppression and 35% coverage-qualified individual action context from rebounding, steals, and blocks. DPOY and All-Defense are excluded.
- Playoffs: 65% absolute individual postseason quality, 20% bounded regular-to-playoff resilience, and 15% repeated elite postseason evidence. Team advancement is excluded.
- Accolades: 60% Major Honors, 35% Sustained Recognition, and 5% statistical-title support. Related events are bundled within season; when a major honor exists, the same season's sustained-recognition bundle is capped at 0.50. Champion events are excluded.
- Winning: 65% mutually exclusive highest postseason outcome tier, 25% sustained elite regular-season team context, and 10% playoff breadth, conditioned on player participation. Individual playoff quality and champion-award counts are excluded.

Missing optional inputs use explicit observed-evidence renormalization only where the Constitution permits it. Required anchors block a score. Defense's portable-versus-action bridge passed its predeclared thresholds (3,368 overlapping players, Spearman 0.9883, median raw delta 0.0153), so recorded action evidence may enrich the universal concept while missing actions remain missing rather than zero.

Modern per-75 Offense and advanced defensive-rating bridges remain diagnostics. Neither changes a universal score. The Offense bridge is strongly associated (Spearman 0.9322; R² 0.8778) but has cohort residual structure. The advanced Defense bridge fails comparability (Spearman 0.2813; R² 0.0840).

## Alternatives considered

- Peak 60/40 and 80/20 were stable but rejected in favor of the center of the constitutionally valid range; 70/30 keeps the sustained window clearly primary without making the apex ornamental.
- A five-year Peak anchor was rejected for insufficient universal coverage.
- Longevity thresholds 85th, 90th, and 95th percentile were rejected for V1 because the 80th percentile produced the best prespecified All-NBA calibration discrimination while the formula itself uses no award inputs.
- Uncapped positive-z longevity was rejected because it recreates Peak height.
- Separate top-level Offense votes for volume and efficiency were rejected because they double-count scoring.
- STL+BLK Defense and award-based Defense were rejected as incomplete and cross-owned.
- Playoff lift as primary was rejected because improvement cannot outrank absolute excellence.
- Flat award points and uncapped same-season event sums were rejected as correlated stacking.
- Cumulative championship/Finals/round credit within one season was rejected; only the highest outcome tier applies.

## Consequences

The formulas are interpretable and deterministic but remain limited by the evidence. Accolades are available only for the 2,140 queried PlayerAwards candidates, Playoff scores require individual postseason evidence, early Defense often has lower confidence, and active-player longevity is explicitly to-date. Correlations are reported for STEP-0015 effective-weight analysis rather than used to delete constitutional dimensions.

## Status

Accepted for GOATLab V1 in STEP-0014.
