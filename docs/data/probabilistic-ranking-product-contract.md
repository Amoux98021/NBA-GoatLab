# Probabilistic Ranking Product Contract — STEP-0015P

Status: governance frozen; API and leaderboard datasets are **not** built in this step.

Policy: `goatlab-v1-ranking-policy-v2-probabilistic`

Product contract: `goatlab-v1-probabilistic-product-contract-v1`

Typed schema: `src/goatlab/rankings/publication_policy.py`

## Canonical versus display objects

The canonical object is the calibrated Overall distribution plus its conditional rank
distribution. The joint substrate is `goatlab-v1-overall-v2-tiered`, still research-only as an
**exact-point** Overall methodology. The display position is a deterministic navigational sort of
median rank with canonical `player_id` tie breaking, not proof of exact superiority. STEP-0016
will create production datasets and endpoints after checking provenance, row counts, and UI
disclosures. This document does not publish a successor Top 100.

`distribution_ref` and `distribution_fingerprint` identify the complete versioned simulation
source. Do not use an interval center as a replacement for missing per-draw evidence. API arrays,
persisted draws, or a reproducible read path must back pairwise and Top-N probabilities. All
probabilities are conditional on the frozen measurement architecture; shared cross-player
calibration-model uncertainty remains unmodeled.

## Player leaderboard record

Required typed fields in `PlayerLeaderboardRecord`:

| Group | Fields and rules |
|---|---|
| Identity/provenance | `player_id`, `player_name`, `distribution_ref`, SHA-256 `distribution_fingerprint`, ranking and Overall-substrate versions, all seven dimension versions. |
| Overall | Optional `overall_center` only with `DIAGNOSTIC_SUMMARY` label, nested 80%/90% ranges; never an exact-point claim. |
| Rank | `median_rank`, nested 50%/80%/90%/95% bands. Optional positive `display_position` only with `NAVIGATIONAL_MEDIAN_RANK_SORT`. |
| Membership | Top-10/25/50/100 probabilities in [0,1], nondecreasing with Top-N size. |
| Status | `ranking_status` and the unmapped source Overall status; `OFFICIAL`, `PROVISIONAL`, and `INTERVAL_NATIVE` may appear; `UNAVAILABLE` may not. |
| Dimensions | Peak, Longevity, Offense, Defense, Playoffs, Accolades, Winning each retain value/status/optional 90% range and whether the value is an official point. An interval/unavailable center is never labeled official. |
| Career/limits | `career_state`, 2025-26 cutoff, `TO_DATE_NO_PROJECTION`, conditional architecture flag, explicit false flags for shared model-uncertainty coverage, quality penalty, and exact Overall point claim. |

The leaderboard's first 100 display positions, when built in STEP-0016, form the *GOATLab Top
100 — Probabilistic Leaderboard*. That is a navigational product selection, not a scientifically
validated exact ordinal Top 100. It must include calibrated interval-native players rather than
filtering them out for failing the point gate.

An `UnrankedPlayerRecord` contains identity, `UNAVAILABLE`, source `OVERALL_UNAVAILABLE`, and
nonempty reason codes. It has no display position, probabilities, or inferred score.

## Pairwise comparison

`PairwiseComparison` takes two distinct distribution-rankable player IDs and their ranking
statuses, `P(A > B)` in [0,1], a matching ordering label, all seven dimension comparisons with
evidence status, uncertainty context, versions, and the conditional-architecture flag. An
unavailable player cannot enter the comparison. The reverse request must satisfy
`P(B > A) = 1 − P(A > B)`
under a tie-free pairwise draw interpretation; STEP-0016 must verify this in its service tests.

Thresholds: at least 90% is strong; 65%–90% is lean; 35%–65% is indeterminate; below 35% are
symmetrical reverse labels. Close nominal display ranks must not be described as a meaningful
quality difference without pairwise support.

## Display and human language

Suggested list entry: `#N` (navigation), player name, median rank, 80%/90% rank bands, Top-100
probability, Overall range, and `Official`/`Provisional`/`Interval-native` status. A profile
additionally exposes the full 50%/95% bands, Top-10/25/50 probabilities, dimension statuses, and
pairwise comparison.

> GOATLab ranks players using the full uncertainty distribution of their measured performance.
> Display position is a useful summary, not proof that neighboring players are definitively
> ordered. A wider range describes less precise evidence, not a lower-quality player.

Historical measurement environments are unequal. GOATLab represents that difference with
calibrated uncertainty, not predicted missing statistics or false exactness. Active careers are
to-date only, never projected.

## STEP-0016 implementation checklist

1. Materialize reproducible distribution-backed leaderboard, profile, and pairwise datasets from
   versioned Gold output without moving source-specific fields into model or API contracts.
2. Validate every card against `PlayerLeaderboardRecord` and every insufficient-evidence entry
   against `UnrankedPlayerRecord`; reject missing ranges, status mismatches, and exact-point claims.
3. Serve a navigation list and accompanying bubble context. Preserve the archived V1 Top 100
   separately; do not overwrite it or call the new display positions exact ranks.
4. Prepare FastAPI endpoints and Next.js display requirements with version, cutoff, conditional
   calibration, and uncertainty disclosures visible; verify pairwise symmetry and no projection.
5. Record a new STEP-0016 fingerprint, full suite, lineage, and publication review. Basketball
   formulas, frozen weights, point-calibration gates, and output fingerprints remain unchanged.
