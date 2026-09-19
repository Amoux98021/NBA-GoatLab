# STEP-0016 pairwise comparison contract

The artifact-backed `RankingRepository.compare_players(A, B)` uses the same-index paired Overall
draws stored for the release. It does not compare two independent marginal distributions. Return
`P(A > B)`, `P(B > A)`, tie probability, the frozen ordering label, both Overall and rank ranges,
90% Overall-range overlap, seven dimension statuses/diagnostic differences, release/policy
versions, and a conditional-uncertainty explanation.

There are `1,882 × 1,881 / 2 = 1,770,021` possible unordered pairs. No large pairwise table is
precomputed. An on-demand comparison reads two 2,500-draw vectors from a lazily loaded,
fingerprinted serving artifact. If exact draws tie, half the tie mass is assigned symmetrically
to each direction for complementary probabilities; `tie_probability` is also exposed. Draws
and source quality are unchanged. Reverse requests must complement to 1 within floating
tolerance.

Labels: ≥90% strong A-over-B, ≥65% lean A-over-B, 35–65% indeterminate, then symmetric reverse
labels. A close navigation position is not itself evidence that the earlier player is better.

Errors: identical IDs produce a validation error; unknown or `UNAVAILABLE` players produce an
insufficient-comparable-evidence response (API 404 for unknown ID, 422 for known but unavailable
when HTTP is implemented). The endpoint must never substitute a zero/midpoint or drop a
dimension. Dimension differences are diagnostic center differences only when both centers
exist; they are not exact superiority claims.
