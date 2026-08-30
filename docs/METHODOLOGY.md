# Methodology

## Research position

GOAT Lab models multiple definitions of basketball greatness; it does not assert that one statistical or machine-learning procedure can establish an objective GOAT. Ranking formulas and ML are out of scope for Phase 1.

## Data principles

1. Source facts and GOAT methodology are separate concerns.
2. Every canonical fact retains source provenance.
3. Internal identifiers, not player names, are relational keys.
4. Historical absence is not performance: `NULL != 0`.
5. Coverage eligibility is explicit and metric-specific.
6. Transformations should be deterministic and tested.
7. Source-specific names end at the ingestion/canonicalization boundary.

## Layer contract

- Bronze stores source-faithful data and retrieval metadata.
- Silver stores canonical entities and basketball facts without opinions or GOAT weights.
- Gold will store versioned derived features, era normalization, dimension scores, and model-ready inputs.

This living summary may be extended, but methodology changes must also receive a permanent step record and an ADR when material.

## Silver schema V1 policy

- Season start year is the canonical `season_id` and labels use `YYYY-YY`.
- Canonical entity identifiers are deterministic UUIDv5-derived strings governed by ADR-0005; names are never relational keys.
- Season types use a closed canonical vocabulary. Provider synonyms are normalized before duplicate resolution.
- Player-season traditional and advanced facts are separate tables with team-specific and total-season row scopes.
- Traditional/advanced fields are nullable. A nullable value is interpreted only with `metric_coverage`; it is never automatically zero.
- The acquired nbadb v238 bundle cannot populate player game, player season, advanced, or award facts.
- Under ADR-0006, official NBA Stats is the audited player-fact source. `PlayerGameLogs` is the preferred player-game input; official Base/Totals is used from its empirical 1996-97 boundary, while earlier season totals may be deterministically aggregated from official game facts after metric-specific coverage validation.
- NBA's documented statistic-introduction dates and empirically observed endpoint behavior are separate evidence. A pre-introduction placeholder (including zero) maps to NULL, not an observed performance value.
- Raw NBA responses and request metadata are Bronze. Canonical mappings use stable NBA player/game business keys, quarantine source conflicts, and never join on a name.

## Player-fact qualification and aggregation V1

- Endpoint success and column presence do not establish metric reliability. STEP-0005 qualifies each canonical metric for each season, season type, and source endpoint.
- Empirical coverage labels are `RELIABLE` (at least 99% non-null), `PARTIAL` (80% to less than 99%), `SPARSE` (above 0% to less than 80%), `UNAVAILABLE` (historically or contractually inapplicable), and `UNKNOWN` (no usable observation despite conceptual applicability). Thresholds are configurable, conservative V1 methodology governed by ADR-0007.
- Observed-zero percentage is calculated over non-null observations. Missing observations never enter its denominator and never become zeros.
- A player-season metric is aggregated only when its source partition is `RELIABLE` and all contributing rows for that player/group are non-null.
- TEAM rows retain team-specific facts. A single TOTAL row combines qualified appearances across teams for player × season × season type. `games_played` counts distinct official game appearances.
- Shooting percentages use summed makes divided by summed attempts only when the attempt denominator is positive. Per-game values use qualified `games_played`; unavailable totals or denominators produce NULL.
- Official numeric player, team, and game identifiers are source business keys. Team name supplies version evidence, never the primary join. Stale legacy windows are reported but cannot invalidate official player facts.
- Contradictory source rows remain unchanged in Bronze and enter an explicit quarantine rather than an automatic repair path.

## Frozen historical corpus V1

- `GOATLAB-HIST-V1` freezes 1946-47 through 2025-26 for `REGULAR` and `PLAYOFF`. It contains 80 seasons and excludes every later season.
- The frozen identity includes the request matrix, source/client versions, canonicalization timestamp, schema and methodology versions, per-partition hashes, and aggregate corpus fingerprint. It is governed by ADR-0008.
- Future current-season refreshes must use separate versioned outputs. Neither new games nor upstream corrections may silently mutate this research release.
- All 280 intended bulk scopes are checkpointed independently. Successful cache entries and output partitions survive later failures; API failure is never interpreted as an empty result.
- Full-history identity and team enrichment cannot change an already assigned canonical ID merely because more metadata becomes available.
- Reconciliation blocks the corpus when a field has at least a 1% mismatch rate or mismatches in at least three partitions. Rounding-tolerance matches are reported separately from exact matches.
- Quality reporting distinguishes `SOURCE_ANOMALY` from `PIPELINE_ERROR`. Source-faithful Bronze remains untouched; contradictory source rows are quarantined before Silver without repair.
- The complete V1 coverage matrix preserves the ADR-0007 thresholds. It is eligibility evidence for later research, not a GOAT feature or score.
