# ADR-0019: Dimension feature ownership and shared evidence

## Context

The eight proposed GOAT dimensions naturally share factual lineage. PPG can inform Offense, Peak, and Era Dominance; DPOY can inform Defense and Accolades; postseason participation can inform Playoffs and Winning. Reusing a primitive without disclosure would give it multiple implicit votes.

## Decision

Maintain a versioned primitive ownership registry with `PRIMARY`, `SECONDARY`, `DIAGNOSTIC`, and `EXCLUDED` roles. STEP-0012 evaluates strict ownership, shared evidence with a `1 / dimension-count` penalty, and raw-evidence separation. Raw-evidence separation is selected only as the default policy for later experiments: individual defensive performance belongs primarily to Defense, award events to Accolades, playoff performance to Playoffs, and team outcomes/participation to Winning. Secondary use remains visible and audited; it is never silent.

## Alternatives considered

- Strict ownership eliminates duplication but can remove semantically relevant context.
- Unrestricted sharing preserves context but creates hidden multiple voting.
- A shared-evidence penalty is transparent but introduces another weighting convention.

## Consequences

Every candidate exposes primitive lineage and overlap. Cross-dimension correlations remain expected basketball evidence, not a target to force toward zero. A later final methodology must choose and version an ownership policy; STEP-0012 does not finalize one.

## Status

Accepted for methodology experimentation; no dimension formula is final.
