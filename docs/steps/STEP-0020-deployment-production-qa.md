# STEP-0020 — Deployment & Production QA

Date: 2026-09-21

Step status: `PARTIAL`.

Deployment verdict: `DEPLOYMENT_PARTIAL`.

Recommendation: `DEPLOYMENT_REQUIRES_MORE_WORK`.

## Outcome

The immutable STEP-0016 product release was reconstructed locally from STEP-0019 HEAD. Release
fingerprint, draw hash, migration hash, counts, Top-100 order, profiles, and methodology remain
unchanged. STEP-0020 added production hardening, deterministic release transport/materialization,
an OCI API image, a Render-compatible reference blueprint, Vercel project configuration, strict
production settings, timeouts/security/no-index headers, CI, smoke tooling, runbooks, recovery, and
publication-gate documentation. No basketball methodology or product release byte changed.

A live deployment could not be performed: the execution environment had no Vercel team/project,
no Vercel CLI authentication, no Neon/PostgreSQL production URL, no API-host account/credentials,
no production domain, and no bundle object-store destination. No secrets were present or invented.
The Vercel connection returned an empty team list. Consequently deployed URLs, TLS/DNS checks,
provider log/alert inspection, live database load, deployed browser QA, rollback rehearsal, and
production latency/failure injection remain incomplete. The public-rights gate also remains open.

## Frozen integrity

- Release: `goatlab-ranking-release-2026-v2-probabilistic`
- Release fingerprint: `2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`
- Draw SHA-256: `1fa326cf9a5bbece581e5e1b253ebcb5d40b30bcc2bcea3268752583e54b7f26`
- Migration SHA-256: `1673c24e0f120662ab6529328b1f14cab50a5fba6dfab99eff3e0ecd236c880d`
- Expected rows: 5,103 profiles; 1,882 rankable; 3,221 unavailable; 100 Top-100 rows.
- Deployment artifact-set SHA-256: `1c9bb8f67a64e6901c9b9d9f7ef6325af6c0caf871a69651a881d65a59f81abf`

The deployment fingerprint manifest is
[`step-0020-deployment-fingerprints.json`](../data/step-0020-deployment-fingerprints.json).

## Architecture and safety

ADR-0043 selects Vercel + portable FastAPI OCI service + Neon-compatible pooled PostgreSQL and a
SHA-256-pinned external release bundle. Production requires PostgreSQL mode, explicit HTTPS CORS,
TLS DB configuration, connect/statement timeouts, and exact release identity. Runtime DB sessions
are read-only; provider pooling is required. The API remains fail-closed on database, bundle, draw,
release, or Top-100 mismatch. The controlled pre-deploy role alone migrates/loads.

The frontend defaults to `noindex, nofollow, noarchive`, exposes robots disallow, and cannot become
indexable without the explicit rights-approval environment flag. This gate changes discoverability,
not rankings. Security headers were added to API and frontend. Rate limiting and full CSP remain
host/deployment follow-ups rather than silently guessed settings.

## Verification scope

Automated checks cover deterministic bundle packaging, traversal rejection, atomic materialization,
strict production configuration, secret-free descriptors, security headers, frozen release
fingerprints, Python tests/lint/types, and frontend tests/lint/types/build. The actual 61 MB release
was packaged twice to the identical 31 MB transport hash and was materialized/verified twice
(`MATERIALIZED`, then `ALREADY_VERIFIED`). Docker is not installed on this host, so the image build
is defined and CI-gated but was not executed locally.
The repeatable smoke command checks API integrity/error semantics, UI routes/disclosures, compare
reversal, and pre-rights indexing protection. Local preview validation is not a substitute for the
unperformed deployed-environment checklist.

The complete Python suite reported 393 passed and 3 expected skips (live network and local
PostgreSQL integration were not configured in that run). A separate isolated PostgreSQL 17 run
passed all 15 deployment/backend integration tests, including migrations, rollback, immutable
load, database/artifact equivalence, and the preserved-schema-options regression. Frontend
typecheck, lint, 11 unit tests with 5
live-server tests skipped, and the Next production build passed. Local production-build smoke and
visual browser inspection passed. Illustrative local timings were: API Top 100 2.4 ms, leaderboard
100 2.1 ms, first paired-draw comparison 109.8 ms, warm reverse 1.6 ms; median frontend responses
were 18.5 ms home, 13.2 ms leaderboard, 4.5 ms profile, and 5.5 ms comparison. These are not
production SLAs.

The dependency review initially identified critical Next.js advisories against 16.3.1. The frontend
was upgraded to the official 16.3.5 patch release with matching `eslint-config-next`; no codemod or
application change was required. The production-only npm advisory scan then reported zero
vulnerabilities, and the post-upgrade type/lint/test/build plus end-to-end smoke passed. One low
development-dependency advisory remains outside the production dependency set.

## Open gates

1. Authorized provider projects, credentials, regions, budgets, and domains.
2. Upload and retention policy for the deterministic release bundle.
3. Live Neon migration/load/reconciliation and SELECT-only runtime role validation.
4. Deployed API/frontend smoke, browser, accessibility, TLS, CORS, cold-start, and failure QA.
5. Monitoring/alerts and a rehearsed rollback/restore.
6. Formal publication-rights approval.

No public launch is authorized by this step.
