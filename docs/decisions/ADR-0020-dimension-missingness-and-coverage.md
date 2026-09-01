# ADR-0020: Dimension missingness and evidence coverage

## Context

Historical metric availability differs sharply by era. Available-feature averaging can inadvertently advantage sparse records, while complete-case rules can erase early careers. Coverage confidence describes evidence quality and must not become player quality.

## Decision

Evaluate four explicit policies for every candidate: core-feature only, available-feature renormalization, a two-thirds coverage threshold, and era-specific enrichment. No policy imputes a missing primitive, converts it to zero, or inserts an average. The all-era core and modern enrichment remain separate. Coverage is reported as `STRONG` (100%), `MODERATE` (75% to under 100%), `LIMITED` (above zero to under 75%), or `UNAVAILABLE` (zero). These labels never apply score penalties.

The two-thirds threshold is a diagnostic convention, not a final product rule. Candidates with under 50% availability in the broad high-recall population are rejected for severe coverage limitation. Modern-only candidates are deferred from universal comparison.

## Alternatives considered

- Zero or mean imputation was rejected because it invents historical evidence.
- One universal complete-case population was rejected because it structurally favors modern eras.
- Silent available-case averaging was rejected because it hides differing evidence bundles.

## Consequences

All 5,103 players remain present. A candidate value may be NULL while other candidates for the same player remain valid. Defense and candidate-scoped accolades retain visible limitations. Later modeling must consume both value and coverage metadata.

## Status

Accepted for STEP-0012 diagnostics; final missingness policy remains open.
