# ADR-0007: Player-fact qualification and aggregation

## Context

STEP-0004 established that an official endpoint can return historical player rows while individual metric columns remain sparse or contain pre-introduction placeholders. STEP-0005 also requires deterministic season aggregation and historical team resolution despite incomplete legacy identities and stale team validity windows. Row presence alone therefore cannot authorize aggregation or cross-era use.

## Decision

Adopt a configurable empirical coverage classifier for each season, season type, endpoint, and canonical metric. V1 uses `RELIABLE` at at least 99% non-null, `PARTIAL` at 80% to less than 99%, `SPARSE` above 0% to less than 80%, `UNAVAILABLE` when the metric is historically or contractually inapplicable, and `UNKNOWN` when no usable observation exists despite conceptual applicability. Observed-zero percentage uses non-null observations as its denominator. These are qualification labels, not performance scores, and are separate from the canonical `metric_coverage.coverage_status` vocabulary.

Aggregate a metric from player games only when the source partition is `RELIABLE` and every row in the player aggregation group is observed. Produce `TEAM` rows and one canonical `TOTAL` row per player, season, and season type. Count games from distinct qualified appearances. Derive shooting percentages from summed makes divided by summed attempts only when attempts are positive; otherwise leave the percentage NULL. Do not infer games started from `PlayerGameLogs`.

Resolve players using official `PLAYER_ID`. Resolve teams using official `TEAM_ID` plus observed official team-name version evidence; abbreviation is diagnostic only. Retain stale legacy-window conflicts as evidence and do not reject valid official facts. Preserve invalid or contradictory source rows in Bronze and quarantine them before Silver rather than repairing or overwriting them.

## Alternatives considered

- Treat every returned endpoint column as reliable.
- Sum non-null values while treating missing observations as zero.
- Use player names or team abbreviations to fill identity gaps.
- Trust legacy team validity windows as the sole temporal authority.
- Automatically repair contradictory source box-score facts.

## Consequences

Early-era season facts are intentionally narrower than the source payload. Conservative thresholds may temporarily classify nearly complete metrics as `PARTIAL`; later validation may change the thresholds only through a new documented methodology step. Provisional identities and team versions remain traceable to official numeric business keys. Aggregates are reproducible and cannot silently convert historical absence into performance. Source anomalies require explicit quarantine review.

## Status

Accepted — 2026-08-27.
