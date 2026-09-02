# ADR-0022: Coverage-qualified matrices for unsupervised structural analysis

## Context

GOATLab's candidate and primitive features have historically uneven availability. A single complete-case matrix would substantially favor later eras, while zero or mean imputation would invent evidence. PCA and factor analysis also answer different questions and must not be treated as interchangeable.

## Decision

STEP-0013 uses multiple labeled matrices: the surviving dimension candidates, an independently assembled cross-era primitive matrix, a post-1996 modern-enriched matrix, and magnitude/profile clustering matrices. Each matrix uses an explicit coverage-qualified complete intersection and records every retained/excluded player, missing-feature count, debut-era distribution, and active-career status. No missing value is imputed.

Standard and robust column scaling are compared. PCA uses deterministic SVD. Factor analysis uses iterated principal-axis factoring with orthogonal Varimax rotation. Parallel analysis, bootstrap loading alignment, held-out correlation reconstruction, population sensitivity, and active-career sensitivity are reported. Component signs are arbitrary and no component score is a greatness score.

## Alternatives considered

- Zero/mean imputation was rejected because it fabricates historical evidence.
- One universal modern feature matrix was rejected because advanced evidence begins in 1996-97.
- One all-candidate complete intersection without selection reporting was rejected because it hides severe early-era exclusion.
- Treating PCA as factor analysis was rejected because total-variance compression and common-factor modeling have different objectives.

## Consequences

Results are matrix-conditional, and the 32-candidate intersection is explicitly selection-biased toward later careers. Cross-era and modern findings remain separate. Later work may use shortlisted candidates but must preserve missingness and population provenance.

## Status

Accepted for structural diagnostics; no latent component or candidate is final.
