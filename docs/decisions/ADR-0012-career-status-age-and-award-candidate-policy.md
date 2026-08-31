# ADR-0012: Career status, age, and broad award-candidate policy

## Context

The frozen corpus ends at 2025-26, while the audited legacy identity snapshot ends at 2022-23 and lacks birth dates for many players. STEP-0009 award acquisition may require player-scoped requests, so it needs a broad planning universe without converting that flag into a permanent ranking exclusion.

## Decision

Classify a player as ACTIVE_TO_CUTOFF when they appear in 2025-26 Regular Season. Classify SOURCE_CONFIRMED_COMPLETE only when the audited legacy player identity marks the player inactive and no cutoff appearance overrides it. All other careers are INDETERMINATE. Active accomplishments are measured through the cutoff without projection; indeterminate status is not treated as retirement.

Calculate age on February 1 of the season-ending calendar year only when common_player_info provides an audited birth date. Missing birth dates produce unavailable age features; no age is inferred from draft or debut year.

Retain all 5,103 players in the master corpus. For award-acquisition planning, evaluate participation, elite-season, multi-category, and union proposals. Recommend the broad union of at least five qualified Regular Seasons OR at least one 90th-percentile season in a reliable core category (PPG, RPG, APG, SPG, BPG, or TS%). Candidate status is an acquisition flag only, designed to prefer false positives over false negatives.

## Alternatives considered

- Treat every player absent in 2025-26 as retired.
- Trust the stale legacy active flag without a current-cutoff override.
- Infer missing ages from first season, draft year, or typical debut age.
- Acquire awards only for a statistically selected Top 100.
- Permanently exclude players outside one candidate rule.

## Consequences

Career completion remains nullable for 271 indeterminate cases, 582 cutoff-active careers are not projected, and age features are available only for 3,612 players. The recommended award candidate universe contains 2,140 players, while every player remains eligible for later research. Future authoritative identity refreshes require a new documented version rather than silent status mutation.

## Status

Accepted — 2026-08-31.
