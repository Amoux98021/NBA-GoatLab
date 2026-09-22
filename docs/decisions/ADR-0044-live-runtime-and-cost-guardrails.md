# ADR-0044: Live runtime and cost guardrails

Status: Accepted  
Date: 2026-09-22

## Context

GOATLab is live on Vercel Hobby, one Render Free Docker service, Neon Free, and private Cloudflare
R2 Standard. The immutable ranking release and read-only FastAPI service are functioning. The
initial deployment topology in ADR-0043 preferred a pooled Neon runtime connection, but the
PostgreSQL startup options used by GOATLab are not compatible with Neon's pooled endpoint.

The free provider tiers also have finite, changeable quotas. Product behavior can consume those
quotas accidentally through polling, keepalive traffic, per-row requests, repeated downloads, or
unnecessary third-party services.

## Decision

1. The production API uses the direct/unpooled Neon endpoint with a dedicated `goatlab_api` LOGIN
   role limited to database `CONNECT`, public-schema `USAGE`, and `SELECT` on required production
   tables.
2. The existing owner/admin role remains intact and is used only for controlled migrations and
   immutable release loads.
3. ADR-0044 supersedes ADR-0043 only where ADR-0043 requires a pooled runtime endpoint. All other
   immutable-release and least-privilege decisions remain accepted.
4. GOATLab's operating target is `$0/month`. Paid plan changes, billable features, paid services,
   and keepalive traffic require explicit human approval.
5. The dated numeric quota snapshot lives in
   `docs/product/RUNTIME_RESOURCE_LIMITS.md` and must be reverified against official sources before
   infrastructure changes.
6. Product code preserves bulk API use and caching. It must not add polling, per-row/per-animation
   requests, scroll-triggered fetching, automatic refresh loops, or repeated release downloads.

## Consequences

- The API does not gain pooling benefits and must stay within Neon's direct-connection limits.
- Render cold starts remain an accepted Free-service behavior; GOATLab will not generate synthetic
  traffic to prevent them.
- Visual and interaction work must operate on data already present in rendered responses.
- Future work that may exceed a free-tier limit pauses for an explicit resource/cost decision.
- No basketball methodology, ranking output, release artifact, or publication policy changes.
