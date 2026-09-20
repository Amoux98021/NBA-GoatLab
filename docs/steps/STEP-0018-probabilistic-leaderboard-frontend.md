# STEP-0018 — Probabilistic Leaderboard Frontend

Date: 2026-09-20

Step status: `PASS`

Frontend verdict: `FRONTEND_LEADERBOARD_READY` for local product preview.

Recommendation: `READY_FOR_PLAYER_COMPARISON_EXPERIENCE`.

## Frozen boundary and structure

The verified input commit is `1494f1dfb472031ac51e33ccce2e32c5f9940146`; the release
manifest fingerprint is `2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.
No basketball formula, ranking policy, backend endpoint, generated product release, or
research artifact changed. `frontend/` previously contained only a placeholder README, so this
step added a Next.js 16 / React 19 / TypeScript App Router app with compact custom CSS, rather
than duplicating an existing frontend. ADR-0042 records the serving/rendering choice.

## Product experience

`/` displays the exact frozen `/top100` order, an uncertainty-first hero, 80% rank bands,
Top-100 probabilities, Overall 90% ranges, neutral evidence statuses, and nearby API-sourced
positions around the Top-100 cutoff. `/leaderboard` server-renders the full paginated field
with normalized backend search, active and status filters. `/players/[playerId]` uses canonical
IDs, shows all six Top-N probabilities and 50/80/90/95 rank bands, plus seven dimension cards.
Unavailable players remain profile-accessible without a fabricated rank or zero. `/methodology`
explains the fixed weights, evidence statuses, conditional probabilities, historical limits,
cutoff, and release fingerprint. No dead comparison button is shipped; pairwise UX is a later
product step.

Display position is explicitly labeled navigational. Interval-native Overall and dimension
values are presented as ranges, never standalone diagnostic centers. Active careers remain
to-date through 2025-26. Wider uncertainty is described as lower measurement precision, not
lower player quality. The API client checks the frozen release and response shape. No ranking,
Top-N, status, or pairwise logic is reimplemented in the UI.

## Verification

Production build, frontend typecheck and lint pass. Frontend unit/component tests cover Top-100
order, uncertainty/status display, missing-not-zero, search/filter delegation, malformed
responses, and percentage formatting. Live local API integration checked exact 100-player
HTML/API order plus sampled Jordan, LeBron, Curry, Kobe, Gobert, Russell, Mikan, and one
unavailable profile, including identities, evidence statuses, and Overall ranges.

Browser inspection covered home/Top 100, full leaderboard search, an active provisional
profile, an interval-native profile, an unavailable profile, methodology, and the official
status filter (312 API results). Unknown player IDs show a dedicated not-found state. With
the API stopped, a cache-miss request showed the service-unavailable boundary and did not
substitute a ranking. At 375, 768,
1024, and 1440 px there was no page-level horizontal overflow. The 1024 px table uses an
intentional keyboard-focusable inner scroll; 375/768 px use cards. No runtime error overlay was
observed during normal operation. Mobile navigation keeps all three destination links visible.
A Next.js smooth-scroll warning was corrected. Keyboard/touch disclosures use native
`details` controls; focus states and semantic headings/table markup are present.

Backend test and lint/type results are recorded in the final step handoff. Generated
screenshots are QA evidence only and are not committed.

## Remaining product boundaries

The API does not expose the complete frozen bubble artifact; the home page labels its
API-derived cutoff preview accordingly. A full compare experience remains for STEP-0019.
Source/publication rights remain `PUBLICATION_RIGHTS_REVIEW_REQUIRED`; local preview is not
authorization for public deployment. Shared cross-player calibration-model uncertainty remains
outside the frozen research model; the frontend does not claim to remove it.
