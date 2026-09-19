# STEP-0016 probabilistic leaderboard data contract

Release ID: `goatlab-ranking-release-2026-v2-probabilistic`. Policy:
`goatlab-v1-ranking-policy-v2-probabilistic` (ADR-0039). The archived V1 Top 100 remains distinct.

`leaderboard.json` contains exactly one `LeaderboardEntry` per player with a calibrated Overall
distribution: 1,882 rows. `leaderboard-v2-probabilistic.json` is the first 100 rows in the
frozen navigational order. It is **not** an exact scientific Top-100 ordering. A 100th display
position and a 101st position may be statistically indistinguishable.

The only navigation sort is `(median_rank ASC, canonical player_id ASC)`. The frozen STEP-0015O
`median_rank_sort_position` is reproduced exactly; no center, expected rank, or status is an
additional tie-breaker. Display position is an integer 1–1,882 with mandatory
`NAVIGATIONAL_MEDIAN_RANK_SORT` semantics.

Each row carries identity, active state, 80/90/95 Overall ranges, explicitly labeled diagnostic
center, median/mean rank, nested 50/80/90/95 rank bands, monotone Top-1/5/10/25/50/100
probabilities, source Overall and product evidence status, Top-100 probability class, cutoff,
release/policy versions, and disclosure codes. No status or uncertainty width changes a score.

`top100-bubble.json` is a separate disclosure set, not extra display slots. It contains players
whose Top-100 probability is at least 10% but below 90% **and** whose 90% rank band includes rank
100. Players outside the first 100 can therefore appear in the boundary artifact. Membership
labels use the frozen ≥90/≥65/≥35/≥10 probability thresholds; they do not set display order.

All probabilities are conditional on the frozen measurement architecture. Shared global
calibration-model uncertainty remains unmodeled. The production build does not generate, tune,
or alter any basketball quantity.

`data/product/<release_id>/` is generated and ignored by Git. The committed step record, SQL,
models, tests, and release fingerprint document how to reproduce it from frozen Gold files.
