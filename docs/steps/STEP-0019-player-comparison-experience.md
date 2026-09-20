# STEP-0019 — Probabilistic Player Comparison Experience

Date: 2026-09-20

Step status: `PASS`.

Product verdict: `PLAYER_COMPARISON_READY` for local product preview.

Recommendation: `READY_FOR_DEPLOYMENT_AND_PRODUCTION_QA`, subject to the existing
`PUBLICATION_RIGHTS_REVIEW_REQUIRED` gate.

## Frozen input and boundary

Input HEAD was `9911c394072eac4a29ff103170ee61b0db8fc982`. The immutable STEP-0016
release remains `goatlab-ranking-release-2026-v2-probabilistic`, fingerprint
`2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.
STEP-0019 changes only frontend presentation/client validation and product documentation. It
does not change the API, paired draws, basketball formulas, rankings, calibration gates,
statuses, product release, or V1 history. ADR-0039/0040/0041/0042 remain binding.

## Experience and source of truth

`/compare` has two canonical player searches, duplicate prevention, keyboard selection, swap,
and optional profile preselection. Search uses the existing read-only leaderboard endpoint via
a narrow same-origin Next.js route; it returns only the rankable 1,882 players and does not
invent a second identity system. Every profile, including an unavailable profile, offers a
Compare entry. A selected matchup resolves to the stable canonical-ID URL
`/compare/[playerA]/[playerB]`. URL order is display order; the server requests that order from
the backend rather than inverting probabilities in the browser.

The result page renders the backend's aligned-draw `P(A>B)`, complementary direction,
`ordering_label`, tie semantics, and frozen release/policy metadata. Strong, lean, and
indeterminate wording follows the backend label; there is no frontend threshold decision.
It shows both 80/90 rank bands, Top-10/25/50/100 probabilities, Overall 90% ranges,
seven dimension values/statuses, and range-overlap context. Interval-native dimensions remain
ranges, missing values remain “Insufficient evidence”, and neither is substituted with zero or
midpoint. The qualitative interpretation names higher displayed point summaries only when
both players have point values. It does not claim causal attribution or compute new weighted
dimension contributions from uncertain centers.

Historical measurement, active-career cutoff, confidence-versus-quality, and conditional
probability caveats are visible. Cross-era messaging is informational, not a formula change.
Player photography is omitted because no permitted image pipeline exists. No analytics system
was introduced. Comparison data use the immutable release's one-hour server fetch cache;
the server validates release ID and response shape. Only the search selector and share-link
feedback need browser-side interactivity.

The page handles same-player selection, known-unavailable comparisons (API 422), unknown IDs
(API 404), and backend failure without manufacturing a probability. Next App Router may send a
200 streaming shell before the final not-found UI; the displayed state is still a dedicated
not-found page with no substitute matchup. This HTTP streaming behavior is a product/deployment
QA note, not a change to the backend's 404 contract.

## Verification

Frontend typecheck, ESLint, unit tests, live API/SSR contract tests, and production build pass.
The live contract suite reconciles Jordan–LeBron, Curry–Kobe, Russell–Wilt, Kareem–Duncan,
and Curry–Gobert with the API; reverse probabilities agree within floating tolerance.
Unavailable, same-player, unknown-player, profile-entry, and canonical search paths are
checked. Existing Top-100 and profile regression tests remain green.

Browser inspection covered the selector and keyboard selection, lean/strong/indeterminate
result states, unavailable disclosure, canonical reverse link, seven-dimensional table, and
mobile/desktop layouts at 375, 768, 1024, and 1440 px. There was no page-level horizontal
overflow at those widths. The probability bar has a textual equivalent, status is not conveyed
by color alone, and the comparison table retains semantic headings and row labels.
Warm local illustrative response times were about 4 ms for the artifact-backed pairwise API,
52 ms for the Next.js comparison HTML, and 6 ms for the canonical search proxy; these are
development observations, not a deployment SLA.

The backend Python suite passed (386 passed, 3 skipped); Ruff and targeted product-package mypy
passed. The repository-wide mypy command still reports two pre-existing redundant-cast errors
in `src/goatlab/rankings/overall_v2.py`, which STEP-0019 does not modify. Local browser checks
use the read-only artifact-backed API; no live production database or public deployment was
touched.

## Remaining limitations

The frozen API supplies pairwise Overall probability but not dimension-specific pairwise
probabilities or exact contribution attribution; the UI intentionally does not invent them.
Search only covers rankable careers, while unavailable profiles can still open the 422
explanation path. Paired-draw probabilities are conditional on the frozen measurement
architecture and do not model all shared cross-player calibration uncertainty. Public launch
still requires publication-rights review and production QA.
