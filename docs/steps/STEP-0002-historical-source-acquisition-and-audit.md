# STEP-0002 — Historical source acquisition and audit

## 1. Objective

Install and inspect the current official `nbadb` CLI, acquire its public historical snapshot reproducibly, preserve provenance, and audit the actual physical data before defining canonical mappings.

## 2. Motivation

Canonical schemas cannot be mapped defensibly from documentation or prior assumptions. The physical snapshot, its keys, missingness, duplication, and observed coverage must be evidence.

## 3. Inputs

- STEP-0001 commit `1cf8003`.
- Official repository `https://github.com/wyattowalsh/nbadb`.
- Installed revision `48abd9825ed6933b57dbac3f50f058523367b1f5` (`nbadb 4.0.0`).
- Kaggle dataset `wyattowalsh/basketball`, resolved version 238.
- Retrieval timestamp `2026-08-19T16:52:59Z`.

## 4. Work performed

- Verified that `uv` was unavailable and used the STEP-0001 virtual-environment fallback.
- Attempted the documented PyPI installation; PyPI returned no `nbadb` distribution.
- Installed the official repository at an immutable Git revision.
- Inspected `nbadb --help` and `nbadb download --help`; used the observed `--data-dir` option.
- Ran `.venv/bin/nbadb download --data-dir data/bronze/nbadb` without credentials.
- Audited SQLite in read-only/query-only mode, including all physical schemas, row counts, observed season coverage, important null counts, candidate keys, and duplicate groups.
- Reconciled metadata claims against physical SQLite, DuckDB, and CSV contents.
- Added a deterministic audit command, JSON inventory, human-readable report, and provenance manifest.

## 5. Files created or changed

- `src/goatlab/data/nbadb_audit.py`
- `pipelines/ingest/audit_nbadb.py`
- `tests/test_nbadb_audit.py`
- `docs/data/source-manifest.yaml`
- `docs/data/nbadb-inventory.json`
- `docs/data/NBADB_SOURCE_AUDIT.md`
- `docs/PROJECT_LOG.md`
- This step record.

Ignored local-only inputs occupy 4,660,601,876 bytes under `data/bronze/nbadb/`; no raw data is staged for Git.

## 6. Data observations

- The 697 MB Kaggle download resolved version 238 and expanded to a 4.66 GB local bundle.
- Metadata advertises 235 v4 star-schema outputs, but the physical SQLite contains 16 legacy tables, the DuckDB catalog contains zero user tables, and 16 CSVs mirror the legacy surface.
- No `dim_*`, `fact_*`, `agg_*`, or `analytics_*` tables are physically present.
- SQLite contains 65,698 game rows and 13,592,899 play-by-play rows.
- Observed games cover 1946-11-01 through 2023-06-12 (seasons 1946-47 through 2022-23), not the current season described in metadata.
- There is no player game box-score, player-season aggregate, advanced-stat, or awards table.
- `game.game_id` has 56 duplicate groups caused by duplicated All-Star rows under `All Star` and `All-Star` labels. Other source candidate keys also contain duplicates, including 7,360 `(game_id, eventnum)` play-by-play groups.
- Historical team-game metric null rates are substantial. Sparse anomalous pre-introduction non-null values mean first non-null season cannot be equated with first reliable season.
- `team_info_common` exists physically but is empty.

## 7. Decisions made

- Treat SQLite as the local audit format because the downloaded DuckDB catalog is empty.
- Treat Kaggle version 238 as a source snapshot with a material catalog/publication mismatch, not as the advertised v4 star schema.
- Base STEP-0003 mappings only on physical evidence. Mark missing source coverage unavailable rather than substituting metadata claims.
- Keep the complete bundle ignored and commit only code, manifests, and audit artifacts.

## 8. Validation/tests executed

- `pytest`: three tests passed, including null-preservation and duplicate-key audit behavior.
- Ruff formatting and lint checks passed.
- Mypy strict checking passed.
- The full audit completed against the 2.35 GB SQLite database.
- SHA-256 recorded for SQLite, DuckDB, and dataset metadata.
- Re-running the auditor with identical arguments produced deterministic committed outputs.
- Git ignored-file inspection confirmed the downloaded bundle is excluded.

## 9. Results

Historical acquisition succeeded without authentication. Provenance and actual physical limitations are recorded. The source is usable for player identity, team identity/history, draft facts, games, team-level game stats, officials, inactive players, and play-by-play, but it cannot supply the required player traditional/advanced/award facts in this version.

## 10. Known limitations

- The acquired dataset is stale relative to its metadata and lacks the advertised star-schema outputs.
- The underlying cause of the Kaggle publication mismatch is external and not repaired locally.
- Candidate keys are hypotheses validated for duplication, not declared source constraints; all SQLite columns are nullable and no physical primary keys exist.
- Endpoint reliability and first reliable season cannot be inferred solely from this snapshot.
- CSV parity was assessed by physical table/file names and bundle structure; SQLite is the authoritative audit surface.

## 11. Next step

STEP-0003: implement typed canonical Silver schema V1, deterministic normalization utilities, validation tests, and an explicit field-level mapping that distinguishes mapped, derived, and unavailable fields from this physical snapshot.
