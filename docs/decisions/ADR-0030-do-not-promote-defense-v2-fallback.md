# ADR-0030: Do not promote Defense V2 until missing-Presence comparability is solved

## Context

STEP-0015A proved that frozen Defense V1 is dominated by a team-season constant and therefore requires revision. Its strongest replacement candidate assigned 30% to team context, 30% to role-aware actions, and 40% to shrunk Defensive Presence Impact. Presence was unavailable for many seasons, and Candidate B redistributed the missing 40% over team and action evidence.

STEP-0015B reconstructed Candidate B exactly and masked Presence on 12,875 player-seasons where all three channels were known. Simple renormalization had 10.72 Defense-point MAE. A grouped five-fold ridge fallback using only portable team, action, interaction, and broad-role evidence improved MAE to 9.90, but its direct Presence prediction had only 0.0174 out-of-fold R-squared; 49.40% of masked season estimates still missed the full score by more than 10 points. Career aggregation reduced MAE to 6.38, but did not establish season-level construct equivalence.

## Decision

Do not promote `goatlab-v1-defense-v2`. Keep frozen V1 and Overall V1 as historical baselines, while continuing to classify V1 Defense as `REQUIRES_REVISION`.

Retain the 30/30/40 architecture and the STEP-0015B continuous-reliability experiment as research candidates only. The continuous experiment removes the former 10-with/five-without eligibility cliff by blending observed Presence into an expected portable value. It is not a production solution because the expected-Presence model has insufficient predictive signal.

No new official Defense or Overall methodology version is created. The counterfactual Overall remains diagnostic and cannot replace `goatlab-v1-overall-v1`.

## Alternatives considered

- Promote Candidate B with direct renormalization: rejected because withholding Presence changes the construct and produces large errors.
- Promote the grouped-ridge expected-Presence fallback: rejected because its apparent full-score improvement mainly reflects retained team/action inputs; it explains too little independent Presence variance.
- Treat unavailable Presence as zero: prohibited by the Constitution.
- Use awards or modern advanced defense to fill the gap: prohibited as universal inputs without a bridge, and empirically weak as validation.
- Remove hard thresholds but otherwise retain the fallback: useful for continuity, but insufficient to solve comparability.

## Consequences

GOATLab has no launch-ready replacement Defense formula after this step. The audit is nevertheless complete and reproducible. A future Defense architecture must either obtain a more portable individual signal, model a latent defensive construct with explicit measurement regimes, or publish evidence-regime-specific estimates that are not falsely presented as one interchangeable scale.

## Status

Accepted in STEP-0015B. Promotion verdict: `DO_NOT_PROMOTE`.
