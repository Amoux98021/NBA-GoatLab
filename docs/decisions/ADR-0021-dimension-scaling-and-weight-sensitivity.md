# ADR-0021: Dimension scaling and internal weight sensitivity

## Context

Candidate inputs include counts, z-scores, percentiles, rates, and participation totals. A single scale can hide outlier or tie behavior, and an equal-weight candidate can appear authoritative despite arbitrary internal weights.

## Decision

Compare four transparent component scales against the broad high-recall analytical population: career-universe midrank percentile, robust standardization using `1.4826 × MAD`, population standard z-score, and right-continuous empirical CDF. Ties remain ties; legitimate extremes are not clipped.

Equal weights are only a baseline. Each multi-component candidate receives 200 deterministic uniform-simplex weight samples using seed `120012` plus a stable candidate offset. Audits report score variance, percentile variance, median percentile, percentile IQR, and sampled pairwise ordering stability. No sampled result is combined across dimensions or published as a player ranking.

## Alternatives considered

- Min-max-only scaling was rejected because extreme historical values determine endpoints.
- One hand-picked weight vector was rejected because it conceals arbitrariness.
- Consensus-ranking calibration was rejected because it would turn opinion lists into targets.

## Consequences

Scaling and weight choice remain visible experimental axes. Candidates with ordering stability below 0.75 are rejected as weight-sensitive. STEP-0012 found no candidate below that threshold, but several have materially wider percentile IQRs and remain cautioned.

## Status

Accepted for candidate evaluation; no scale or weight vector is final.
