# STEP-0016 player profile contract

`player-profiles.jsonl` contains one `PlayerProfile` for each of the 5,103 canonical players,
including players with `UNAVAILABLE` Overall evidence. A profile is not a ranking-eligibility
assertion. `players.jsonl` is the release-scoped identity snapshot; it derives from the canonical
Gold career summary and retains the same `player_id`. `search_name` is a deterministic normalized
lookup token, never an alternate identity key or fuzzy merge.

Each profile includes identity/career state, the linked `LeaderboardEntry` only when
distribution-rankable, all seven dimension objects, methodology versions, source reason codes,
and `TO_DATE_NO_PROJECTION`. For an active career, `career_end_season` is null and
`latest_season_used` is the observed last season through 2025-26. Indeterminate career status
stays `UNKNOWN` rather than being guessed retired.

| Display status | Profile rule |
|---|---|
| Official point | Show the source value and status. |
| Provisional point | Show the source value with a provisional indicator; show a range when available. |
| Interval-native | Show the 90% range; retain any center as a separately named *diagnostic* value, never an official point. |
| Unavailable/unknown | Show “Insufficient evidence” or source-specific reason, never a fabricated zero. |

Peak preserves the frozen best-supported three-year window and its probability. Longevity
preserves expected elite breadth, capped area, longest run, and run-bridge count. Defense
preserves its evidence form, usable-season count, and observed Presence reliability. The four
remaining dimensions are passed through from frozen V1 dimension output, including Accolades
`NOT_QUERIED` semantics. No dimension is recomputed by the product build.

`reason_codes` combine frozen source reason codes with dimension prefixes and explicit
interval-native/not-queried markers. They explain evidence and coverage, not player quality.
The typed `PlayerProfile` and `DimensionProfile` schemas are in
`src/goatlab/product/models.py`; frontend should not infer status from null alone.
