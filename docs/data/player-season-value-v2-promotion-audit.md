# PlayerSeasonValue V2 Promotion Audit

Methodology: `goatlab-v1-player-season-value-v2-promotion-audit-v1`

Result: **PASS + DO_NOT_PROMOTE**

Candidate D reconstructs exactly and factual recovery raises coverage to 93.99%. Source conflicts
are low-impact after season reranking (0.321 point MAE), and team context remains capped at 5.5% of
total value. Those facts clear the reconstruction, provenance, source-stability, coverage, and
attribution gates.

Promotion is withheld because measurement equivalence does not clear its gate. Traditional-box
and expanded-box/no-Presence masks have 7.96 and 7.25 point MAE; 32.48% and 29.67% exceed ten
points. These regimes contain 6,420 actual scored seasons, not a negligible hypothetical tail.

No official `goatlab-v1-player-season-value-v2` output is created. Candidate D remains
`goatlab-v1-player-season-value-v2-research`; all V1 artifacts remain frozen.
