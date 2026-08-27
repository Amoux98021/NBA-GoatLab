# STEP-0005 — Bronze-to-Silver player-fact ingestion pilot

## 1. Objective

Validate a reproducible, resumable Bronze-to-Silver path for representative official NBA player facts without performing a complete historical backfill or implementing GOAT methodology.

## 2. Motivation

STEP-0004 established bulk endpoint feasibility but also showed severe early-era metric sparsity. This step had to prove that official facts could be resolved, qualified, transformed, aggregated, reconciled, and partitioned without confusing API row availability with statistical reliability.

## 3. Inputs

- Clean `main` after STEP-0004 (`9a66650`).
- The ignored, source-faithful NBA API cache created in STEP-0004.
- Audited Kaggle/nbadb v238 legacy identity, team, and game tables.
- Existing Silver V1 typed contracts and deterministic identifier policy.
- Eight representative seasons: 1946-47, 1961-62, 1973-74, 1979-80, 1984-85, 1996-97, 2022-23, and 2025-26.
- Regular Season and Playoffs for every pilot season.
- The user-specified fixed PASS criteria and scope limits.

## 4. Work performed

- Accepted ADR-0007 for conservative metric qualification, defensible aggregation, official-ID resolution, versioned teams, and source-conflict quarantine.
- Implemented source-faithful Bronze artifact normalization with request provenance, payload fingerprints, idempotent cache reuse, and explicit outcome handling.
- Implemented deterministic official player and team business-key resolvers; preserved provisional identities and stale-window conflicts.
- Transformed 16 bulk `PlayerGameLogs` partitions into canonical `player_game_stats`, preserving historical NULLs.
- Empirically classified every traditional metric by season/type and aggregated only qualified, complete observations into TEAM and TOTAL `player_season_stats` rows.
- Reconciled derived totals to six official Base/Totals partitions.
- Mapped six Advanced/Totals partitions to nullable canonical `player_season_advanced`.
- Added deterministic quality gates, conflict quarantine, partitioned Parquet output, machine-readable reports, and offline unit tests.

## 5. Files created or changed

- `src/goatlab/data/player_fact_ingestion.py`
- `pipelines/silver/ingest_player_fact_pilot.py`
- `tests/test_player_fact_ingestion.py`
- `docs/decisions/ADR-0007-player-fact-qualification-and-aggregation.md`
- `docs/data/PLAYER_FACT_INGESTION_PILOT.md`
- `docs/data/player-fact-pilot-summary.json`
- `docs/data/metric-coverage-pilot.json`
- `docs/data/player-identity-reconciliation.json`
- `docs/data/team-crosswalk-report.json`
- `docs/data/source-manifest.yaml`
- `docs/DATA_DICTIONARY.md`
- `docs/METHODOLOGY.md`
- `docs/PROJECT_LOG.md`
- `pyproject.toml`
- This step record.

Ignored outputs include the Bronze pilot manifest and 38 generated Silver Parquet files.

## 6. Probe matrix

Player-game rows are Bronze / accepted Silver. Base and Advanced are Bronze rows.

| Season | Regular player-game | Playoff player-game | Regular Base / Advanced | Playoff Base / Advanced |
|---|---:|---:|---:|---:|
| 1946-47 | 6,508 / 6,507 | 360 / 360 | — | — |
| 1961-62 | 6,812 / 6,812 | 515 / 515 | — | — |
| 1973-74 | 13,380 / 13,380 | 743 / 743 | — | — |
| 1979-80 | 17,782 / 17,782 | 918 / 918 | — | — |
| 1984-85 | 19,249 / 19,249 | 1,359 / 1,359 | — | — |
| 1996-97 | 23,757 / 23,757 | 1,412 / 1,412 | 441 / 441 | 189 / 189 |
| 2022-23 | 25,894 / 25,894 | 1,728 / 1,728 | 539 / 539 | 217 / 217 |
| 2025-26 | 26,651 / 26,651 | 1,921 / 1,921 | 582 / 582 | 230 / 230 |

## 7. Data observations

- The pilot resumed all 28 bulk requests from cache; no API call or per-player request was made.
- 148,989 source player-game rows produced 148,988 canonical rows after one explicit quarantine.
- All 2,138 official player IDs and 38 official team IDs resolved; 249 players required provenance-bearing provisional canonical identities and eight early team IDs were absent from legacy teams.
- Stale legacy team windows generated 27 reported conflicts but did not invalidate official facts.
- The 7,982 traditional season rows comprise 4,153 TEAM and 3,829 TOTAL rows. Advanced mapping produced 2,198 rows.
- Six Base/Totals reconciliations compared 43,493 values: 38,531 exact, 4,962 within documented tolerance, and zero mismatches.
- Of 304 metric/partition coverage records, 190 were RELIABLE, 24 PARTIAL, 26 SPARSE, 54 UNAVAILABLE, and 10 UNKNOWN.
- The earliest partitions demonstrate extreme column sparsity despite valid player-game rows. No missing value was interpreted as zero.

## 8. Decisions

- Use a conservative, configurable V1 empirical threshold of 99% for `RELIABLE`; use 80% for the lower `PARTIAL` boundary.
- Aggregate a metric only from a RELIABLE partition and a complete player group.
- Use official numeric IDs as source business keys. Names and abbreviations remain diagnostic.
- Represent official team-name changes as deterministic versions without allowing stale legacy validity windows to reject valid facts.
- Count games from distinct appearances; calculate percentages from summed makes/attempts with positive denominators.
- Preserve contradictory source rows in Bronze and quarantine them before Silver.
- Keep generated Bronze and Silver data out of Git; explicitly declare PyArrow because deterministic Parquet output is a direct project requirement.

## 9. Validation/tests

- Offline pilot: all 28 requests resumed successfully from cache.
- Deterministic artifact validation: repeated fixed-timestamp execution produced identical reports and Parquet SHA-256 fingerprints.
- Official reconciliation: all six partitions passed; zero unexplained value or player-set mismatches.
- Quality gates: zero accepted-Silver failures across duplicates, orphans, dates, nonnegative counts, shooting relationships, rebounds, provenance, total-row uniqueness, and NULL preservation.
- Pytest offline, Ruff, strict Mypy, and Git whitespace validation passed. Network tests remained opt-in.
- Unit coverage includes Bronze normalization, provenance, identity/team mapping, historical NULLs, canonical mapping, season aggregation, percentages, total rows, coverage classification, duplicate/integrity gates, official reconciliation, and deterministic Parquet output.

## 10. Result

The pilot provides a resumable and auditable acquisition path from official bulk responses to source-faithful Bronze and deterministic canonical Silver facts. It correctly limits early-era aggregates to empirically supportable metrics and independently validates modern totals.

## 11. Known limitations

- Eight representative seasons do not prove uninterrupted behavior across all 80 historical seasons.
- V1 coverage thresholds are conservative methodological defaults, not permanent empirical truths.
- Provisional player records preserve identity and facts but do not yet contain complete biographical attributes.
- Observed team-name evidence is a practical version boundary, not a completed franchise-history research product.
- `PlayerGameLogs` cannot populate `started`.
- The single quarantined 1946-47 contradiction remains unresolved.
- The 2025-26 source reflects the endpoint state at the STEP-0004 retrieval time; future reruns may legitimately add rows.
- Awards, rankings, era normalization, and ML remain out of scope.

## 12. Decision: PASS

**PASS.** All nine fixed criteria are met: reproducible bulk ingestion; defensible player and team resolution; duplicate-safe canonical player games; deterministic season aggregation; sufficient post-1996 official reconciliation; preserved historical NULLs; metric-level sparse/unavailable detection; explicit conflict quarantine; and resumable controlled expansion.

## 13. Recommended STEP-0006

Run a controlled, resumable full-history Bronze-to-Silver player-fact backfill using the validated bulk request matrix and per-partition quality gates. Freeze a retrieval cutoff, checkpoint each partition, review provisional identity/team versions, and stop the expansion on schema drift or reconciliation failure. Keep GOAT features, era adjustment, awards valuation, rankings, and ML out of that acquisition step.
