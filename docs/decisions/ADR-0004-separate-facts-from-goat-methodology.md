# ADR-0004: Separate raw facts from GOAT methodology

## Context

All-time rankings depend on definitions and value judgments. Encoding those judgments in canonical facts would make the data circular and prevent meaningful comparison among methodologies.

## Decision

Silver contains only canonical entities, observations, derived factual aggregates with documented definitions, and coverage metadata. GOAT dimensions, weights, era-normalization policies, preference models, and ranking outputs belong in versioned Gold/experiment surfaces.

## Alternatives considered

- Add accolade weights to player-season facts.
- Tune canonical values until conventional rankings are reproduced.
- Maintain one authoritative ranking score in Silver.

## Consequences

Multiple defensible methodologies can share one factual base. The UI can explain why rankings change. Ranking outputs cannot silently rewrite source facts or rely on player-specific corrections.

## Status

Accepted — 2026-08-19.
