# ADR-0032: Do not infer a universal historical point score from sparse evidence

- Status: Accepted
- Date: 2026-09-14
- Decision owners: GOATLab methodology
- Supersedes: none
- Related: ADR-0020, ADR-0029, ADR-0030, ADR-0031

## Context

STEP-0015D produced a promising research-only PlayerSeasonValue measure, but 5,881
early-limited player-seasons lacked the creation and individual defensive evidence required by
the construct. STEP-0015E tested whether the missing channels could be reconstructed from the
portable evidence actually present in those regimes.

Player-grouped and era-blocked validation found that scoring volume does not identify creation
well enough, and team context plus recorded actions does not identify missing defensive Presence.
All four historical masking regimes failed at least two predeclared PlayerSeasonValue point-score
gates. Even expanded box evidence without Presence had 7.27 points of MAE and 29.87% of errors
above ten points. Early-minimal evidence had 11.35 points of MAE and 47.10% above ten points.

## Decision

GOATLab will not fill sparse historical PlayerSeasonValue with a universal point estimate.

- `FULL_PORTABLE` retains its observed research score.
- `EXPANDED_BOX_NO_PRESENCE` and `TRADITIONAL_BOX` remain research scores under STEP-0015D,
  but the bridge audit does not certify them as construct-equivalent to full evidence.
- `EARLY_LIMITED` may receive an explicitly labeled diagnostic interval where PPG and bounded
  team context exist. The interval midpoint is not an official score.
- Rows without even the minimum portable anchors remain `UNAVAILABLE`.
- Confidence and interval width remain separate from estimated quality.
- No bridge output may promote PlayerSeasonValue, Peak, Longevity, Defense, or Overall.

## Consequences

The historical record remains epistemically incomplete. Peak and Longevity cannot yet be
replaced universally with Candidate D. Future work must either acquire additional factual early
evidence, develop and validate a genuinely invariant measurement architecture, or publish
multi-regime/interval comparisons rather than one falsely precise all-era point score.

This sacrifices apparent coverage to preserve the Constitution's rule that missing evidence is
not zero and cannot silently change the meaning of a score.
