# STEP-0004 — Official NBA player data feasibility and coverage probe

## 1. Objective

Determine whether bounded, season-scoped official NBA Stats requests provide a defensible bulk acquisition path for missing historical player-game, player-season, and advanced player facts, then reconcile the overlap with audited nbadb v238.

## 2. Motivation

STEP-0002/0003 proved that Kaggle version 238 contains only a legacy 16-table snapshot and cannot populate the central player fact tables. A complete nbadb warehouse reconstruction is disproportionate to project needs. The official source needed empirical testing rather than reliance on endpoint contracts alone.

## 3. Inputs

- Clean `main` after STEP-0003 (`2888155`).
- Audited Kaggle `wyattowalsh/basketball` v238 SQLite snapshot.
- `nba_api` 1.11.4 endpoint request contracts.
- Twelve representative seasons from 1946-47 through 2025-26 and six advanced-boundary seasons.
- The user-specified PASS/PARTIAL PASS/FAIL semantics and scope limits.
- NBA Stats FAQ documentation for historical statistic and advanced-data introductions.

## 4. Work performed

- Accepted ADR-0006, adopting audited Kaggle reference facts plus direct official NBA player facts, with modern nbadb optional.
- Implemented a timeout-bounded, retry-bounded, exponentially backed-off, jittered, paced, resumable NBA Stats client.
- Added deterministic request contracts/cache keys, raw-response hashes, outcome classification, and ignored Bronze caching.
- Executed 24 bulk `PlayerGameLogs`, 24 Base/Totals `LeagueDashPlayerStats`, and 12 Advanced/Totals requests. `PlayerID` remained unset; no per-player calls were made.
- Measured rows, players, games, dates, fields, null rates, duplicate candidate keys, timing, retries, and plausibility.
- Reconciled all 2022-23 regular-season and playoff API games to Kaggle NBA `GAME_ID`, date, participating team IDs, and matchup direction.
- Compared official `PLAYER_ID` values with legacy `player`, `common_player_info`, and the committed canonical fixture.
- Added source-to-canonical mapping helpers with historical NULL guards and explicit team crosswalk resolution.
- Added machine-readable reports and a small source-faithful fixture; retained full responses only in ignored Bronze.

## 5. Files created or changed

- `src/goatlab/data/nba_api_client.py`
- `src/goatlab/data/nba_api_probe.py`
- `pipelines/ingest/probe_nba_player_facts.py`
- `data/fixtures/nba_api_player_fact_probe_sample.json`
- `tests/test_nba_api_client.py`
- `tests/test_nba_api_probe.py`
- `tests/test_nba_api_network.py`
- `docs/decisions/ADR-0006-direct-nba-api-player-facts.md`
- `docs/data/NBA_API_PLAYER_FACT_PROBE.md`
- `docs/data/nba-api-player-fact-probe.json`
- `docs/data/nba-api-kaggle-reconciliation.json`
- `docs/data/source-manifest.yaml`
- `docs/DATA_DICTIONARY.md`
- `docs/METHODOLOGY.md`
- `docs/PROJECT_LOG.md`
- `pyproject.toml`
- This step record.

## 6. Probe matrix

Row counts are Regular Season / Playoffs.

| Season | PlayerGameLogs | Base/Totals |
|---|---:|---:|
| 1946-47 | 6,508 / 360 | 0 / 0 |
| 1955-56 | 5,622 / 401 | 0 / 0 |
| 1961-62 | 6,812 / 515 | 0 / 0 |
| 1973-74 | 13,380 / 743 | 0 / 0 |
| 1979-80 | 17,782 / 918 | 0 / 0 |
| 1984-85 | 19,249 / 1,359 | 0 / 0 |
| 1996-97 | 23,757 / 1,412 | 441 / 189 |
| 2009-10 | 24,813 / 1,674 | 442 / 199 |
| 2022-23 | 25,894 / 1,728 | 539 / 217 |
| 2023-24 | 26,401 / 1,685 | 572 / 214 |
| 2024-25 | 26,306 / 1,804 | 569 / 219 |
| 2025-26 | 26,651 / 1,921 | 582 / 230 |

Advanced/Totals returned 0 / 0 rows for 1995-96, then Regular Season / Playoffs rows of 441 / 189 (1996-97), 439 / 190 (1997-98), 442 / 199 (2009-10), 539 / 217 (2022-23), and 582 / 230 (2025-26). Every call returned HTTP 200; successful empty result sets remain distinct from failures.

## 7. Data observations

- One season-and-type request with unset `PlayerID` returned all-player game rows for every representative scope, including 1946-47.
- PlayerGameLogs candidate (`PLAYER_ID`, `GAME_ID`, `TEAM_ID`) had zero duplicates in every probe.
- Row availability does not imply metric completeness. In 1946-47 Regular Season, PTS was complete while FGA was 92.12% NULL and AST was 97.99% NULL. Pre-introduction fields were NULL; `MIN` contained zero placeholders despite minutes not being officially available and is forced to canonical NULL.
- Base/Totals has an empirical tested boundary of 1996-97, not 1946-47. Earlier probes were valid `SUCCESS_EMPTY`, not errors or zero-valued seasons.
- Advanced/Totals exactly matched the tested documented boundary: empty in 1995-96 and populated from 1996-97.
- 2022-23 reconciled 1,230/1,230 regular-season games and 84/84 playoff games with exact dates, team sets, and `vs.`/`@` interpretation. No conflict rows were produced.
- Kaggle contains two physical 2022-23 All-Star rows (`All Star` and `All-Star`); they remain documented artifacts outside the modeled Regular/Playoff overlap.
- Across all probes, 2,444 of 2,753 official player IDs (88.78%) existed in legacy `player`; the lower rate reflects post-snapshot and legacy gaps. In the 2022-23 overlap, 536 of 541 (99.08%) matched. Five unmatched IDs are listed in the machine report.
- `common_player_info` coverage is lower: 1,867/2,753 overall and 420/541 in 2022-23, consistent with the known incomplete legacy table.
- All 60 calls completed without retry. Total measured response time was 71.18 seconds; individual calls ranged from 0.046 to 4.826 seconds under one-second pacing.

## 8. Decisions

- Use `PlayerGameLogs` as the preferred official player-game bulk source.
- Use Base/Totals directly from its empirically observed 1996-97 boundary. Earlier season totals may be derived only from official game facts after metric-specific coverage qualification.
- Use Advanced/Totals from the empirically confirmed 1996-97 boundary; keep every advanced field nullable.
- Preserve documented introductions separately from empirical source response. Never interpret endpoint placeholders as observations.
- Map identity by official numeric business keys and resolve team versions through a canonical crosswalk; names are diagnostics only.
- Keep source precedence unchanged and quarantine rather than auto-resolve conflicts.
- Keep the modern nbadb star warehouse optional and awards unresolved.

## 9. Validation/tests

- Live bounded matrix: 60/60 HTTP 200; 0 retries; no unrestricted extraction.
- 2022-23 reconciliation: 1,314/1,314 shared modeled games; zero conflicts.
- Ruff: passed repository-wide.
- Mypy strict: passed for all source packages.
- Pytest offline: 22 passed; 1 opt-in network test deselected.
- Tests cover cache-key determinism, retry/error classification, provenance/resumability, season normalization, both endpoint mappings, historical NULL preservation, ID mapping, duplicate detection, conflict quarantine, and deterministic JSON report generation.

## 10. Result

Official NBA Stats supplies a practical, resumable bulk player-game path across every representative era and season type. It also supplies player-season Base and Advanced rows from 1996-97 onward. The source is suitable for staged Bronze acquisition and canonical Silver transformation, provided that coverage is assessed per metric rather than inferred from row presence.

## 11. Known limitations

- Twelve representative seasons do not prove uninterrupted season-by-season availability.
- Early player-game metrics are materially sparse; no blanket “complete since 1946-47” claim is justified.
- `PlayerGameLogs` does not return games started; it remains NULL there.
- Historical team-version crosswalks remain incomplete and were not repaired in this step.
- Official NBA Stats has no project-owned uptime or schema-stability guarantee.
- Only one local runtime (Python 3.14.6, within the 3.12+ policy) was tested.
- Awards remain unavailable.

## 12. Decision: PASS

**PASS.** Official endpoints provide a defensible bulk acquisition path for required player-level historical facts: player-game rows span all tested eras and can support deterministic season aggregation where direct season totals are absent; advanced data is empirically available from 1996-97. PASS does not mean every historical metric is complete. Missingness remains metric- and era-specific and must be enforced through `metric_coverage`.

## 13. Recommended STEP-0005

STEP-0005 should implement a staged, resumable Bronze-to-Silver player-fact ingestion pilot with explicit team-version crosswalks and season-by-season/metric-by-metric coverage qualification. Validate a small set of early, boundary, and modern seasons first; only then authorize a controlled full backfill. Do not add rankings, weights, awards values, or ML.
