# GOAT Lab

GOAT Lab is a reproducible NBA history and analytics project for studying how all-time player rankings change under different definitions of greatness. It will eventually support statistical, peak, longevity, offense, defense, playoff, accolade, winning, era-dominance, machine-learning, fan, and user-configured perspectives.

The project does **not** claim that a model can prove one objective GOAT. Phase 1 builds an auditable data foundation only; no player-ranking formula or ML model is implemented.

## Architecture

- **Bronze:** untouched/source-faithful records plus ingestion metadata.
- **Silver:** project-owned canonical basketball facts and identifiers.
- **Gold:** derived analytics, normalized features, and later ranking/model inputs.

Raw data and generated warehouses are local-only and Git-ignored. See `docs/PROJECT_LOG.md` for the chronological engineering record and `docs/decisions/` for architectural decisions.

## Local setup

Python 3.12 or newer is required. `uv` is preferred when available:

```bash
uv sync --extra dev
uv run pytest
```

Fallback with the standard library environment manager:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

The official `nbadb` project did not have a PyPI distribution at the STEP-0002 retrieval time. This project therefore pins the audited official Git revision in `pyproject.toml`; consult the source manifest before changing it.

## Scope status

Phase 1 stops after canonical Silver schema V1 and a source-to-canonical mapping based on the downloaded `nbadb` snapshot. Ranking models, arbitrary accolade weights, fan voting, a production frontend, and deployment remain deliberately out of scope.
