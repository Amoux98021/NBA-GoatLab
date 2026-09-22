# GOATLab production runbook

## Deploy a frozen release

1. Confirm a clean checkout at the approved commit and run repository checks.
2. Rebuild/verify the ignored STEP-0016 product directory. Confirm the release, draw, and migration
   hashes listed in [production-deployment.md](production-deployment.md).
3. Package the release with `package_ranking_release.py` twice; require identical SHA-256 values.
4. Upload the bundle to private Cloudflare R2 at
   `releases/goatlab-ranking-release-2026-v2-probabilistic.tar.gz`. Configure the S3-compatible
   endpoint, bucket, object key, Object Read credentials, and pinned hash as backend secrets.
5. Create a PostgreSQL database/branch. Apply migrations and load using a privileged one-shot role.
   Repeat the load and require `ALREADY_LOADED`.
6. Grant a separate API role only `CONNECT`, schema `USAGE`, and table `SELECT`; use the provider's
   pooled TLS endpoint. Revoke public schema creation where provider policy permits.
7. Deploy the API with `autoDeploy` disabled. Require `/api/v1/health` HTTP 200, correct release ID,
   database accessible, release present, and draw state verified.
8. Deploy a Vercel Preview from `frontend/`, pointing only to the deployed API. Keep
   `GOATLAB_PUBLICATION_RIGHTS_APPROVED=false`.
9. Run `smoke_production.py`, manual desktop/mobile QA, and the checklist. Record URLs, commit,
   environment, timings, and smoke output in the deployment record.
10. Only after a recorded rights approval may an operator enable indexing/custom public DNS and
    deliberately promote the validated preview. This does not alter ranking data.

## Smoke command

```bash
PYTHONPATH=src:. python pipelines/product/smoke_production.py \
  --api-base-url https://API_HOST \
  --frontend-base-url https://PREVIEW_HOST
```

The command verifies release identity, 1,882 rankable players, exact Top-100 reconciliation,
Jordan/LeBron canonical profiles and reversible comparison, expected 400/404 errors, frontend
routes, uncertainty language, and the pre-rights no-index policy.

## Rollback

- Frontend: use the provider's immutable deployment rollback to the last validated deployment.
- API: route traffic to the previous immutable image/config; do not mutate DB rows.
- Database: releases are append-only. Select a previous configured release only when that release's
  complete artifact bundle is also mounted and the frontend is configured for the same ID.
- If a bad release load failed, the transaction leaves no partial release. Diagnose and retry.
- Never delete/UPDATE a published release to make a rollback easier.

## Incident triage

| Symptom | First check | Safe response |
|---|---|---|
| Health 503 | DB state and configured release fingerprint | remove instance from service; restore DB connectivity/config |
| API startup failure | bundle URL/hash, artifact path, manifest log | restore exact bundle; do not bypass verification |
| Pairwise failure | draw state/hash and process memory | restart instance with verified bundle; no synthetic probability |
| Frontend 5xx | API origin/release ID and server logs | rollback frontend or API configuration |
| Top 100 mismatch | stop deployment immediately | compare immutable API artifact and DB; never repair rows manually |
| Rights concern | publication gate | retain no-index/private preview; suspend public access |

Logs must identify release ID and failure class but never include database URLs, bearer tokens, raw
draw arrays, or whole player distributions. Provider log retention and alerts remain deployment
configuration work because no provider account was available in STEP-0020.

## Authorization preflight

Before step 4, confirm all of the following without printing secret values:

1. an authorized Vercel team/project is visible;
2. a TLS PostgreSQL/Neon project exposes separate migration and runtime-role workflows;
3. a container host can build `Dockerfile.api` and preserve the configured proxy contract;
4. an immutable HTTPS object location can retain the pinned release bundle;
5. provider regions, budgets, retention, and alert owners are approved.

The STEP-0020B continuation found none of these resources. Stop at this preflight when authorization
is absent; do not create anonymous resources, invent credentials, or report local services as
production. Once access exists, continue with the existing deploy sequence rather than restarting
the local hardening work.
