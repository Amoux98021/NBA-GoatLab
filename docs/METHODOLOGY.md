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
- The acquired nbadb v238 bundle cannot populate player game, player season, advanced, or award facts. Those mappings remain explicitly unavailable until a separately audited source supplies them.
