# ADR-0043 — Immutable production deployment topology

Date: 2026-09-21

Status: Accepted for deployment preparation; provider resources not yet provisioned.

## Context

STEP-0016 froze a 61 MB product release. PostgreSQL holds queryable summaries, while a 29.6 MB
NPZ preserves paired draws for exact on-demand comparisons. STEP-0017 made database loading
transactional and the API read-only. STEP-0018/0019 created a server-rendered Next.js product.
The release artifacts are intentionally ignored by Git and must not be silently rebuilt in a
production container. Public launch is separately blocked by `PUBLICATION_RIGHTS_REVIEW_REQUIRED`.

## Decision

- The frontend targets Vercel as a Next.js project rooted at `frontend/`.
- The FastAPI application targets a conventional OCI container service; `render.yaml` is the
  checked-in reference deployment, but the image remains portable to Railway, Fly, or another
  host that supports a pre-deploy job and health check.
- PostgreSQL targets a Neon-compatible pooled TLS connection. Standard PostgreSQL features only
  are used. The migration/loader credential and SELECT-only runtime credential are distinct.
- The immutable product release is transported as a deterministic, SHA-256-pinned tar.gz from
  controlled object storage. Runtime materialization validates the transport hash, safe archive
  paths, the release fingerprint, and every manifest-declared artifact before the API starts.
- The database is not used for the paired draw matrix. Each API instance loads the verified NPZ
  lazily once and uses the existing bounded process cache.
- Vercel and API origins remain non-indexable/not publicly announced until publication rights are
  approved. Approval is operational governance, not a code or methodology change.

## Consequences

The API image is small and contains no generated ranking data. A bad/missing bundle, release
fingerprint mismatch, database mismatch, or incomplete Top 100 prevents readiness. Deployment
requires an external bundle URL and provider credentials that are not present in the repository.
Provider pooling avoids opening unbounded direct PostgreSQL backends; application queries also
have connect and statement timeouts. Rollback selects a previous immutable deployment/release;
it never rewrites a release ID.

No basketball formula, ranking probability, product release byte, or publication status changes
under this ADR.
