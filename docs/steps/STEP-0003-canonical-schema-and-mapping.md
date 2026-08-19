# STEP-0003 — Canonical schema and mapping

## 1. Objective

Implement typed canonical Silver schema V1, deterministic provider normalization and project identity, batch-level integrity validation, a machine-readable schema export, and an explicit field mapping grounded in the physically audited nbadb v238 snapshot.

## 2. Motivation

Downstream analytics must depend on stable project-owned names, types, identifiers, provenance, and missingness semantics rather than vendor columns. The source mismatch discovered in STEP-0002 makes explicit “unavailable” mappings essential.

## 3. Inputs

- STEP-0002 commit `112fbe9` and its source manifest/audit.
- Physical SQLite schemas and coverage from Kaggle version 238.
- Canonical V1 requirements in the Phase 1 brief.
- ADR-0001 through ADR-0004.
- Committed source-faithful fixture records for one player, two teams, and one game.

## 4. Work performed

- Added strict immutable Pydantic contracts for players, seasons, franchises, versioned teams, games, traditional player-game facts, traditional player-season facts, advanced player-season facts, award events, and metric coverage.
- Added canonical vocabularies for season type, award type, row scope, metric origin, and coverage status.
- Implemented deterministic UUIDv5-derived canonical IDs, season-label parsing, nbadb season-ID parsing, provider season-type normalization, unit conversion, player transformation, season transformation, and game transformation.
- Added cross-record uniqueness and referential-integrity validation.
- Replaced Hatchling with the minimal setuptools backend. The local macOS filesystem marks generated editable `.pth` files hidden and Python 3.14 skips them, so packaging validation uses a normal wheel install while pytest loads `src/` explicitly.
- Exported deterministic JSON Schema for all Silver V1 entities.
- Added ADR-0005 for canonical identifier strategy.
- Expanded the data dictionary and methodology summary.
- Mapped every canonical field to a physical source, deterministic derivation, project metadata, or explicit unavailability in `NBADB_TO_CANONICAL_MAPPING.md`.
- Added tests for schema invariants, required uniqueness, referential integrity, historical null semantics, duplicate canonical keys, standardized season types, season-label parsing, player identity mapping, provenance, and deterministic transformations.

## 5. Files created or changed

- `src/goatlab/schemas/canonical.py`
- `src/goatlab/schemas/validation.py`
- `src/goatlab/schemas/__init__.py`
- `src/goatlab/data/canonical.py`
- `pipelines/silver/export_schema.py`
- `data/fixtures/nbadb_v238_sample.json`
- `tests/test_canonical_schema.py`
- `docs/data/canonical-schema-v1.json`
- `docs/data/NBADB_TO_CANONICAL_MAPPING.md`
- `docs/decisions/ADR-0005-canonical-identifier-strategy.md`
- `docs/DATA_DICTIONARY.md`
- `docs/METHODOLOGY.md`
- `docs/PROJECT_LOG.md`
- This step record.

## 6. Data observations

- Player core identity maps from `player`, but optional biography/draft fields depend on an incomplete `common_player_info` join (3,632 versus 4,815 player rows).
- Current team identity is available, while historical team windows are stale/incomplete: for example, Lakers history ends in 2019 although games continue through 2023.
- The source's five-digit season ID encodes a type prefix plus four-digit start year; canonical V1 separates type and uses the start year as `season_id`.
- Both `All Star` and `All-Star` occur and cause source game duplicates; both normalize to `ALL_STAR`.
- No physical player box-score, player-season, advanced, or award table exists, so those canonical rows cannot be produced from v238.
- First non-null metric observations cannot be treated as first reliable seasons because sparse anomalous pre-introduction values exist.

## 7. Decisions made

- Accepted ADR-0005: deterministic project-owned identifiers based on provider IDs, never names.
- Use Pydantic as the typed/schema-validation equivalent in this phase; no separate direct Pandera dependency is added because GOAT Lab does not yet import it.
- Use setuptools as the minimal build backend and validate a normal wheel install. This avoids a local macOS hidden-file interaction with Python 3.14 editable `.pth` loading and does not change runtime dependencies.
- Add provenance/timestamp fields to every canonical entity, including dimensions, to make record lineage explicit.
- Model `started` and `did_play` as nullable booleans to distinguish unknown from observed false.
- Use nullable traditional/advanced metric fields plus `metric_coverage` rather than value sentinels.
- Support `TEAM` and `TOTAL` player-season rows with a structural validator (`TEAM` requires a team; `TOTAL` forbids one).
- Do not seed purported reliability windows in STEP-0003; the table contract exists, but reliable-season claims require a dedicated coverage study.
- Do not infer player facts from team box scores or play-by-play.

## 8. Validation/tests executed

- Normal wheel package installation and fresh-process imports verified; source-path test execution is configured separately.
- Deterministic Silver JSON Schema export run twice with matching SHA-256.
- `pytest`: 13 tests passed.
- Ruff formatting and lint checks passed across the repository.
- Mypy strict type checks passed across source and pipeline code.
- Mapping field coverage was compared against exported schema property names.
- Git diff whitespace checks passed.
- The optional integration audit command completed against local nbadb SQLite and matched the committed inventory.

## 9. Results

Silver V1 is implemented and importable, with strict types, null-preserving facts, deterministic normalization, identity stability, and batch integrity checks. The mapping is honest about the acquired source: player/game/team dimensions are partly usable, while the central player performance and award facts remain unavailable from this version.

## 10. Known limitations

- No Silver dataset is materialized in this phase; only contracts and deterministic record transforms are implemented.
- Full historical team-version reconciliation and conflict quarantine remain to be built.
- Source game deduplication policy is documented but a full bulk ingestion job is not implemented.
- `metric_coverage` has no seeded reliability claims yet.
- Player-game, player-season, advanced, and awards require a corrected nbadb publication or separately audited official-source acquisition.
- The local runtime is Python 3.14.6; automated CI across the supported Python 3.12+ range is not yet configured.

## 11. Next step

Recommended STEP-0004: resolve or reacquire a physically complete nbadb snapshot (or run an evidence-bounded official `nba_api` backfill), then implement Bronze-to-Silver identity/team/game transforms with conflict quarantine and integration-level coverage tests before any GOAT feature work.
