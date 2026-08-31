# ADR-0009: Player-season comparison population

## Context

Era-relative distributions are distorted if every one-game appearance receives the same influence as a meaningful season. A fixed games cutoff would also treat shortened seasons inconsistently, while a minutes-only rule cannot operate where historical minute values are unavailable or encoded as non-positive placeholders. Playoff opportunity is structurally smaller and more variable than regular-season opportunity.

## Decision

Define qualification separately within each season and season type. Season opportunity is the maximum number of distinct games played by any team in that canonical game partition, not the maximum games on an individual player record.

- Regular Season: games_played >= max(5, ceil(0.20 × season opportunity games)).
- Playoffs: games_played >= max(2, ceil(0.10 × season opportunity games)).

The selected rule uses games rather than minutes so it remains historically applicable. Every TOTAL player-season is retained with qualification status, reason, threshold, opportunity, and sample-size metadata. Only qualified TOTAL rows define normalization distributions. TEAM rows never enter comparison populations.

The decision is supported by the complete-corpus sensitivity analysis in docs/data/qualification-sensitivity-analysis.json. Candidates included 10%, 20%, and 30% regular-season thresholds; all playoff appearances and 10% and 20% playoff thresholds; and the selected games rule combined with a minutes requirement where minutes qualified.

## Alternatives considered

- Include every player who appeared.
- Use a fixed games minimum across every season.
- Require a share of the maximum player-season minutes.
- Use one threshold for both Regular Season and Playoffs.
- Remove non-qualified player-seasons from Gold.

## Consequences

The rule scales with shortened seasons and excludes the smallest-opportunity observations without depending on incomplete minutes. It retains a mean 88.31% of regular-season players and 92.38% of playoff players. A stricter minutes supplement retained only 69.00% on average in the 100 partitions where it could be evaluated and cannot be applied uniformly, so it was rejected. Qualification is population design, not a player quality score; later changes require a new ADR and methodology version.

## Status

Accepted — 2026-08-31.
