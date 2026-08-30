# STEP-0006 — Full historical player-fact backfill

## 1. Objective

Build and freeze a reproducible official NBA player-fact corpus spanning 1946-47 through 2025-26, with complete request accounting, canonical Silver facts, empirical coverage, reconciliation, anomaly quarantine, and cache-only reproducibility.

## 2. Motivation

STEP-0005 proved the pipeline on eight representative seasons. Research and later feature work require a complete, fixed statistical substrate rather than a rolling endpoint snapshot. The expansion had to preserve historical NULL semantics and expose source anomalies without introducing GOAT methodology.

## 3. Inputs

- Clean `main` after STEP-0005 (`501533f`).
- The STEP-0004 bounded NBA API client and deterministic raw cache.
- STEP-0005 Bronze-to-Silver transforms, ADR-0007 qualification rules, identity resolver, team crosswalk, reconciliation logic, and quality gates.
- Audited Kaggle/nbadb v238 legacy identity, team, and game reference tables.
- Official `nba_api` 1.11.4 bulk endpoints.
- Frozen user-specified cutoff of 2025-26 and fixed PASS criteria.

## 4. Work performed

- Accepted ADR-0008, separating immutable historical research releases from future current-season refreshes.
- Froze `GOATLAB-HIST-V1`, its 80-season scope, two included season types, and deterministic 280-scope request matrix.
- Implemented an atomic, resumable checkpoint with explicit request and output states.
- Executed 160 bulk `PlayerGameLogs`, 60 Base/Totals, and 60 Advanced/Totals scopes without per-player calls.
- Resolved the full player and team universes while preserving all STEP-0005 canonical identifiers.
- Built 160 `player_game_stats`, 160 `player_season_stats`, and 60 `player_season_advanced` Parquet partitions.
- Reconciled every post-1996 derived TOTAL partition with official Base/Totals.
- Computed 3,040 empirical metric-coverage records and a complete quality/quarantine report.
- Recorded source, storage, performance, partition hashes, and an aggregate corpus fingerprint.
- Rebuilt from cache with zero network calls and checked deterministic Silver and report outputs.

## 5. Files created or changed

- `src/goatlab/data/historical_corpus.py`
- `src/goatlab/data/player_fact_ingestion.py`
- `pipelines/silver/build_historical_corpus_v1.py`
- `tests/test_historical_corpus.py`
- `tests/test_historical_corpus_artifacts.py`
- `tests/test_player_fact_ingestion.py`
- `docs/decisions/ADR-0008-frozen-historical-corpus.md`
- `docs/data/HISTORICAL_CORPUS_V1.md`
- `docs/data/historical-corpus-v1-manifest.json`
- `docs/data/full-backfill-summary.json`
- `docs/data/full-metric-coverage.json`
- `docs/data/full-identity-reconciliation.json`
- `docs/data/full-team-crosswalk.json`
- `docs/data/full-base-reconciliation.json`
- `docs/data/full-data-quality-report.json`
- `docs/data/source-manifest.yaml`
- `docs/DATA_DICTIONARY.md`
- `docs/METHODOLOGY.md`
- `docs/PROJECT_LOG.md`
- This step record.

Ignored outputs include 560 selected Bronze payload/metadata files, the mutable checkpoint, and 380 generated Silver Parquet partitions.

## 6. Acquisition and output matrix

| Scope | Seasons | Types | Requests | Rows / output |
|---|---:|---:|---:|---:|
| PlayerGameLogs Bronze | 80 | 2 | 160 | 1,481,850 |
| Base/Totals Bronze | 30 | 2 | 60 | 20,668 |
| Advanced/Totals Bronze | 30 | 2 | 60 | 20,668 |
| Silver player games | 80 | 2 | 160 partitions | 1,481,725 |
| Silver player seasons | 80 | 2 | 160 partitions | 78,025 |
| Silver advanced seasons | 30 | 2 | 60 partitions | 20,668 |

Every one of the 280 request scopes finished `SUCCESS_WITH_ROWS`. No scope finished empty, unsupported, retryable-failed, or permanent-failed. The acquisition made 234 new requests, reused 46 cache entries, and recovered one retry.

## 7. Data observations

- The full corpus contains 5,103 players, 45 official team IDs represented by 74 historical name versions, and 73,135 games.
- All player/team business keys resolved. The 311 official-source-only players retain deterministic provisional identities; no valid fact row was discarded due to incomplete biography data.
- The traditional season build contains 40,553 TEAM rows and 37,472 canonical TOTAL rows.
- All 60 official reconciliation partitions passed: 408,047 values compared, 362,422 exact, 45,625 within tolerance, and zero mismatches or one-sided players.
- Advanced/Totals produced 20,668 nullable canonical rows across every 1996-97–2025-26 season/type partition.
- Coverage classifications were 2,072 RELIABLE, 113 PARTIAL, 167 SPARSE, 588 UNAVAILABLE, and 100 UNKNOWN.
- Early endpoint rows contain historically impossible makes/attempts and pre-introduction placeholders. Endpoint availability therefore remains distinct from metric reliability.
- The broad date-window gate correctly surfaced the 2019-20/2020-21 delayed schedules; those valid rows were retained.

## 8. Decisions made

- Treat `GOATLAB-HIST-V1` as immutable at 2025-26; future refreshes require a distinct version and pipeline behavior.
- Preserve the STEP-0005/ADR-0007 thresholds and NULL-safe aggregation rules unchanged.
- Use a fixed systematic reconciliation blocker: at least a 1% field mismatch rate or mismatches across at least three partitions.
- Preserve stable canonical IDs when fuller corpus evidence adds metadata.
- Classify upstream contradictions separately from locally introduced pipeline errors.
- Retain source-faithful contradictions in Bronze and exclude them from canonical Silver only through explicit quarantine.

## 9. Validation/tests executed

- Network acquisition completed all 280 frozen scopes with bounded retries and no unresolved failure.
- All 160 player-game partitions passed canonical duplicate, relationship, identity, team, game, provenance, season, and historical NULL gates.
- All 60 Base/Totals reconciliation partitions passed with zero unexplained mismatch.
- All 60 expected advanced partitions were written.
- Cache-only rebuild used zero network calls and reproduced all 380 partition hashes and the aggregate fingerprint.
- A repeated fixed-input generation reproduced all seven committed machine-readable reports byte-for-byte.
- Offline Pytest, Ruff, strict Mypy, artifact validation, JSON/YAML parsing, Git ignore checks, and whitespace validation passed.

## 10. Results

The complete frozen corpus is reproducible and suitable as the statistical basis for later research. It contains 1,481,725 accepted player-game rows, 78,025 player-season rows, and 20,668 advanced rows. Its Silver fingerprint is `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`.

## 11. Known limitations

- The 311 provisional player identities need biography enrichment but have stable, non-ambiguous official business keys.
- The 74 team versions are empirical source-name windows, not a fully researched legal/franchise history.
- The 125 quarantined early-era source contradictions remain unresolved and are excluded from Silver aggregation.
- The date gate is intentionally broad; its 3,743 COVID-era flags require contextual interpretation rather than repair.
- Advanced statistics are unavailable before 1996-97 and remain nullable afterward.
- `started` is unavailable from PlayerGameLogs.
- The 2025-26 partition is frozen at the recorded source retrieval, so later official corrections belong in a new corpus version.
- Awards/accolades, GOAT features, rankings, era normalization, ML, and product UI remain out of scope.

## 12. Decision: PASS

**PASS.** Every fixed criterion was met: complete request accounting; no uncontrolled failure; resolved player/team identities; unique game facts; preserved NULL semantics; complete season aggregation and advanced partitions; zero unexplained systematic Base mismatch; full metric qualification; explicit source-anomaly accounting; cache-only hash reproduction; and enforced exclusion of post-2025-26 seasons.

## 13. Recommended STEP-0007

Perform an official awards/accolades source feasibility and canonical event-ingestion step. Build evidence-based `player_awards` facts and coverage without assigning GOAT weights or values. This closes the largest known factual gap before Gold feature eligibility and era-normalization methodology are designed.
