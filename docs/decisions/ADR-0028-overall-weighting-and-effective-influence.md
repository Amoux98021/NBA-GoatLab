# ADR-0028: Overall weighting and effective influence

## Context

The seven constitutional dimensions are correlated. Equal nominal coefficients therefore do not provide equal effective influence. The product also requires the same transparent weighted-arithmetic architecture that future user sliders will use.

## Decision

Adopt `goatlab-v1-overall-v1` as a non-negative weighted arithmetic sum of the frozen STEP-0014 scores:

- Peak 17%
- Longevity 14%
- Offense 16%
- Defense 14%
- Playoffs 18%
- Accolades 10%
- Winning 11%

This redundancy-adjusted candidate preserves 79% nominal weight for direct basketball performance, 31% for the Peak/Longevity career-shape family, and 21% for recognition/outcome. Effective influence is measured with the exact linear-score Shapley variance allocation `w_i × Cov(X_i, Overall) / Var(Overall)`, which fairly assigns pairwise covariance.

Ranks are ordinal by descending score with canonical `player_id` as the deterministic tie breaker; the tie-group size remains auditable. Confidence is metadata and never changes score. Era Dominance, modern diagnostics, external rankings, and player identities are excluded from the formula-selection objective.

## Alternatives considered

- Equal nominal weights are retained as a benchmark but unintentionally give the correlated Peak/Longevity family 35.0% effective influence.
- The constitution-informed candidate gives Peak 25.1% effective influence and Winning only 5.9%, making its nominal hierarchy more uneven than intended.
- A numerically stability-oriented search candidate is stable but embeds a less interpretable objective tradeoff between variance concentration and cohort mean ranges.
- Geometric means, hidden penalties, manual overrides, and missing-dimension renormalization were rejected as constitutionally incompatible.

## Consequences

The selected vector is transparent and stable but is normative, not scientifically unique. Peak/Longevity still contribute 37.3% effective influence because their legitimate shared career signal cannot be removed merely by weights. Future slider configurations must disclose both nominal coefficients and effective influence.

## Status

Accepted for GOATLab V1 in STEP-0015.

