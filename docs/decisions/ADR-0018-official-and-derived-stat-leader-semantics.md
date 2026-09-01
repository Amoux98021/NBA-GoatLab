# ADR-0018 — Official-source and derived statistical-leader semantics

## Context

NBA Stats `LeagueLeaders` returns ranked historical rows, but its first empirical player rows begin in 1951-52 and exact qualification rules changed historically. The current NBA minimums page documents modern rules; applying them retroactively would manufacture history. The frozen corpus can independently identify raw per-game, raw total, and STEP-0007-qualified leaders, but those are not automatically official titles.

## Decision

Preserve `OFFICIAL_SOURCE_RANK_ONE`, `DERIVED_RAW_PER_GAME_LEADER`, `DERIVED_RAW_TOTAL_LEADER`, and `DERIVED_QUALIFIED_LEADER` as separate semantics. Source rank-one ties are all retained. Derived qualification uses the already documented STEP-0007 comparison-population threshold only when the category's empirical Silver coverage is `RELIABLE`; this is a research qualification, not a claim about historical NBA rules. Reconciliation is recorded for every applicable season/category. No record is labeled `OFFICIAL_TITLE` solely from a source rank or a derived maximum.

Category applicability starts with the underlying official statistic: PTS/AST in 1946-47, REB in 1950-51, and STL/BLK in 1973-74. Source gaps and derived coverage gaps remain explicit.

## Alternatives considered

- Apply today's 70-percent qualification rule to all seasons: rejected because historical rules are not established by that page.
- Call every raw maximum a title: rejected because opportunity qualification matters.
- Prefer the source whenever it differs from the frozen corpus: rejected because this would hide coverage and qualification differences.
- Break ties deterministically: rejected because tied rank-one evidence is factual.

## Consequences

Later accolade methodologies can choose an explicitly named evidence family. Statistical-title-like counts remain factual counts by semantics rather than subjective values. Early source gaps and sparse derived metrics do not become zero titles.

## Status

Accepted in STEP-0011.
