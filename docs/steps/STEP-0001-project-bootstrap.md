# STEP-0001 — Repository bootstrap

## 1. Objective

Create the production-quality repository, Python packaging, persistent agent instructions, documentation framework, layer directories, Git hygiene, and an executable test skeleton.

## 2. Motivation

The project must operate as both software and an append-only research record before external data or methodology is introduced.

## 3. Inputs

- Phase 1 project brief dated 2026-08-19.
- Empty local workspace.
- Python 3.14.6 runtime (project compatibility floor remains Python 3.12).
- No installed `uv` executable.

## 4. Work performed

- Initialized the planned directory structure without selecting a frontend framework.
- Added package metadata and minimal direct runtime dependencies.
- Added persistent contributor/agent rules and Git exclusions.
- Established the project log, methodology, data dictionary, experiment registry, step records, and four initial ADRs.
- Added an importable package and smoke test.

Dependency policy: packages the project imports or directly invokes (`duckdb`, `nba-api`, `nbadb`, `pydantic`, and `PyYAML`) are explicit. Heavy transitive analytics packages supplied by `nbadb` (including Polars, PyArrow, Pandera, and Pandas) are not duplicated until GOAT Lab imports them directly. The official `nbadb` Git revision is pinned because no PyPI distribution was available during inspection.

## 5. Files created or changed

Root configuration and instructions, `src/goatlab/`, layer and pipeline directories, test skeleton, documentation indexes, four ADRs, and this step record.

## 6. Data observations

No NBA data was acquired in this step. Raw/generated data directories are ignored except for placeholder files.

## 7. Decisions made

- ADR-0001 historical/current source strategy.
- ADR-0002 Bronze/Silver/Gold architecture.
- ADR-0003 missing historical statistic semantics.
- ADR-0004 separation of facts from GOAT methodology.
- Use Python 3.12 as the compatibility floor; use the available 3.14 runtime locally.
- Use a standard virtual environment fallback because `uv` is unavailable.

## 8. Validation/tests executed

- Package installation in an isolated local environment.
- `pytest` smoke test.
- Ruff lint checks.
- Mypy strict type checks.
- Git ignored-file inspection.

## 9. Results

The repository is ready for reproducible source acquisition. Validation passed before commit.

## 10. Known limitations

- No dependency lock was generated because `uv` is unavailable.
- The local Python version is newer than the minimum supported version; CI across Python 3.12/3.13 is not yet configured.
- Data integration and domain validation tests are intentionally deferred to later steps.

## 11. Next step

STEP-0002: install/inspect the pinned official `nbadb` source, run its actual download workflow, and audit the acquired snapshot without committing raw data.
