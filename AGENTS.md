# Repository instructions for coding agents

This repository is both production software and a reproducible research record.

Before making substantial changes:

1. Read `docs/PROJECT_LOG.md`.
2. Read the ADRs relevant to the proposed change.
3. Identify the next permanent `STEP-XXXX` identifier.
4. Before any scoring, ranking, or methodology work, read and obey `docs/constitution/GOATLAB_V1_CONSTITUTION.md`.

Required working rules:

- Preserve the Bronze/Silver/Gold separation described in ADR-0002.
- Never silently modify the canonical schema. Document material schema changes in a new step and ADR when appropriate.
- Create or update a `docs/steps/STEP-XXXX-*.md` record for every completed logical task and index it in `docs/PROJECT_LOG.md`.
- Create an ADR for material architecture or methodology decisions. Never rewrite an accepted historical ADR to hide a later change; supersede it with a new ADR.
- Never treat missing historical statistics as zero. Preserve observed zero, missing, historically unavailable, and source-coverage gaps as distinct states where practical.
- Preserve source provenance through every data layer.
- Never commit raw downloaded NBA datasets, generated Bronze/Silver/Gold data, DuckDB/SQLite warehouses, caches, credentials, or large model artifacts. Small deterministic fixtures are allowed.
- Never directly train models from vendor/source-specific column names. Route all model inputs through versioned canonical/Gold features.
- Run relevant tests, lint, type, and data-validation checks before declaring work complete.
- Keep implementations deterministic where practical.
- Record random seeds for every ML experiment that uses randomness.
- Version feature definitions and trained models.
- Prefer clear, typed, tested code over shortcuts.
- Do not implement a ranking formula merely to make conventional GOAT rankings look correct.
- Do not manually insert player-specific corrections into ranking results unless explicitly documented as a separate experiment.
- Use one logical Git commit per completed step with the step identifier in the subject.
- Never commit secrets.

## Runtime & Cost Guardrails

- The operating target is `$0/month`. Never upgrade Vercel, Render, Neon, or Cloudflare; enable a
  billable feature or paid service; or add external keepalive traffic without explicit human
  approval.
- Before implementing work that may exceed a provider free-tier limit, stop and explain the
  expected request, compute, storage, bandwidth, or build impact.
- Preserve bulk API use and existing caching/revalidation. Do not add polling, automatic refresh,
  per-row or per-animation requests, scroll-triggered fetching, repeated release downloads, or
  unnecessary remote image/API dependencies.
- Production uses the documented direct/unpooled Neon runtime endpoint with the SELECT-only
  `goatlab_api` role. Do not silently change the connection mode.
- Provider quotas are a dated operational snapshot, not permanent facts. Reverify the official
  provider documentation before infrastructure changes. See
  `docs/product/RUNTIME_RESOURCE_LIMITS.md` for the current snapshot and API guardrails.

If a required source field is unavailable or ambiguous, represent and document the limitation rather than inventing a value or speculative mapping.
