# ADR-0029: Defense attribution and V2 counterfactual

## Context

GOATLab V1 Defense assigns 65% of each qualified season to an era-relative team scoring-suppression percentile and 35% to total rebounds, steals, and blocks. STEP-0015A reconstructed every frozen V1 score exactly, then found that the majority channel is a team-season constant: its within-team variance is zero and its intraclass correlation is 1.0. The final season composite has 89.9% between-team-season variance, while career raw Defense correlates 0.866 with team suppression and 0.445 with action context. The action channel also uses total rebounds—not defensive rebounds—and therefore includes offensive-rebounding evidence.

The Constitution asks how much opponent offensive value the player helped prevent. Team context is valid evidence, but it cannot be the dominant individual attribution mechanism without stronger player-presence evidence.

## Decision

Classify frozen `goatlab-v1-dimension-scores-v1` Defense as `REQUIRES_REVISION`. Preserve it and `goatlab-v1-overall-v1` unchanged as published comparison baselines.

Define the experimental `goatlab-v1-defense-v2` counterfactual as a qualified Regular Season career mean of season-level:

- 30% team scoring-suppression context;
- 30% action evidence: 40% defensive-rebound evidence when available (otherwise explicitly labeled total-rebound proxy), 30% steals, and 30% blocks; each action percentile blends 65% all-player era rank with 35% broad-role rank when position metadata exists;
- 40% Defensive Presence Impact: opponent-strength-adjusted with-player minus without-player game residual, requiring at least 10 games with and five without, shrunk by `n_eff / (n_eff + 20)`, and ranked within season.

Unavailable channels are never zero. Available weights are explicitly renormalized and retained as coverage metadata; team context remains required. The career raw value is mapped through the frozen 2,656-player midrank ECDF. Confidence never changes quality.

This counterfactual is not promoted to the public V1 dimension or Overall. A later explicit promotion audit must address venue adjustment, teammate collinearity, modern-validation uncertainty, and score-scale/effective-influence consequences.

## Alternatives considered

- Retain V1 unchanged: rejected as the forward recommendation because a literal team constant dominates an individual-impact construct.
- Reduce team weight and give the balance only to actions: rejected because box events remain an incomplete and role-sensitive proxy.
- Treat the game-presence contrast as RAPM: rejected because game participation lacks possession-level lineup information and cannot identify full teammate effects.
- Use modern defensive rating directly: rejected because it is post-1996, noisy, and not a validated cross-era bridge.
- Equalize positions: rejected because the Constitution permits unequal defensive ceilings by role.
- Use DPOY or All-Defense in the score: prohibited; they remain validation evidence only.

## Consequences

The V2 candidate materially improves individual attribution and defensive-recognition enrichment, but the presence channel is unavailable for low-without samples and its modern defensive-rating association remains weak. The counterfactual Overall is highly correlated with V1 but changes membership near elite cutoffs. It therefore requires an explicit promotion decision rather than silent replacement.

## Status

Accepted in STEP-0015A as an experimental replacement candidate; public V1 remains frozen.
