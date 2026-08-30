# ADR-0008: Frozen historical corpus and separate current-season refreshes

## Context

STEP-0006 creates the first complete player-fact research corpus. A rolling rebuild could silently change historical results whenever the NBA endpoint corrects old data or the current season gains games. That behavior would make later rankings and experiments difficult to reproduce. The project also needs a future current-season path, but live refresh behavior must not mutate the evidence used by a frozen research release.

## Decision

Freeze `GOATLAB-HIST-V1` at seasons 1946-47 through 2025-26, including only Regular Season and Playoffs. Identify the corpus by its version, fixed scope, source versions, canonicalization timestamp, per-partition SHA-256 fingerprints, and aggregate corpus fingerprint.

Future current-season refreshes will use a separate pipeline and versioned outputs. They may be promoted into a new historical corpus only through a new documented step with new manifests and fingerprints. They must never silently overwrite or redefine `GOATLAB-HIST-V1`. Upstream corrections to a frozen partition likewise require a new corpus version rather than mutation of this release.

## Alternatives considered

- Maintain one rolling historical dataset whose latest source response is always authoritative.
- Mix a mutable current-season partition into an otherwise frozen corpus.
- Freeze only a copy of Silver data without freezing its request matrix, methods, and provenance.
- Stop at 2024-25 and omit the explicitly requested 2025-26 snapshot.

## Consequences

Later research can cite one stable corpus and reproduce every generated partition from its retained Bronze cache. The 2025-26 partition represents the endpoint state at the recorded retrieval cutoff, not a claim that the season can never receive later corrections. Source corrections and new seasons require an explicit new corpus release, which adds storage and release-management overhead. Live product views will eventually need a separate freshness indicator and cannot be presented as the frozen V1 research corpus.

## Status

Accepted — 2026-08-30.
