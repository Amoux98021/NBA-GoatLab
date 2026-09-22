# Production deployment

## Target architecture

| Layer | Target | Contract |
|---|---|---|
| Web | Vercel, `frontend/` root | Next.js 16; server-rendered API consumption; explicit backend URL and release ID |
| API | OCI container; Render reference blueprint | FastAPI, read-only routes, `/api/v1/health`, one immutable configured release |
| Database | Neon-compatible PostgreSQL | pooled TLS runtime URL; migration/loader URL is privileged and temporary |
| Release files | private Cloudflare R2/S3-compatible storage | deterministic tar.gz, pinned transport SHA-256, manifest/release re-verification |
| Paired draws | API local ephemeral disk | verified NPZ loaded lazily once per process; never stored in relational rows |

The release is `goatlab-ranking-release-2026-v2-probabilistic` with fingerprint
`2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`. The draw artifact SHA-256
is `1fa326cf9a5bbece581e5e1b253ebcb5d40b30bcc2bcea3268752583e54b7f26`. The migration SHA-256 is
`1673c24e0f120662ab6529328b1f14cab50a5fba6dfab99eff3e0ecd236c880d`.
The deterministic STEP-0020 transport archive built twice locally was 31 MB with SHA-256
`95b1e39570d7e106b3153a1b1513316a5cf2eb6f3913c55a7912a8a90fb4f512`; an operator must verify
the uploaded object has these same bytes or record a newly generated deterministic transport hash.

## Required backend variables

| Variable | Production value/semantics |
|---|---|
| `GOATLAB_ENVIRONMENT` | `production` |
| `GOATLAB_BACKEND_MODE` | `postgres` |
| `DATABASE_URL` | SELECT-only pooled PostgreSQL URL for runtime; includes `sslmode=require` or stronger |
| `GOATLAB_RELEASE_ID` | frozen release ID above |
| `GOATLAB_RELEASE_FINGERPRINT` | frozen release fingerprint above |
| `GOATLAB_PRODUCT_ARTIFACT_ROOT` | writable ephemeral directory, e.g. `/tmp/goatlab-product` |
| `GOATLAB_R2_ENDPOINT_URL` | private R2 S3-compatible HTTPS endpoint |
| `GOATLAB_R2_BUCKET` | bucket containing the immutable deployment bundle |
| `GOATLAB_R2_OBJECT_KEY` | `releases/goatlab-ranking-release-2026-v2-probabilistic.tar.gz` |
| `GOATLAB_R2_ACCESS_KEY_ID` | private Object Read credential; secret |
| `GOATLAB_R2_SECRET_ACCESS_KEY` | private Object Read credential; secret |
| `GOATLAB_RELEASE_BUNDLE_SHA256` | transport hash printed by `package_ranking_release.py` |
| `GOATLAB_ALLOWED_CORS_ORIGINS` | exact HTTPS frontend origins, comma-separated |
| `GOATLAB_DATABASE_CONNECT_TIMEOUT_SECONDS` | default `5` |
| `GOATLAB_DATABASE_STATEMENT_TIMEOUT_MS` | default `10000` |
| `GOATLAB_FORWARDED_ALLOW_IPS` | trusted internal proxy address/range supplied by host |

If any R2 variable is present, the runtime requires the complete R2 configuration and uses it in
preference to the compatibility transport. `GOATLAB_RELEASE_BUNDLE_URL` plus the optional
`GOATLAB_RELEASE_BUNDLE_BEARER_TOKEN` remains supported for HTTPS/Bearer deployments, but those
compatibility variables are not prompted by the production Render blueprint.

The controlled one-shot load environment needs a privileged TLS `DATABASE_URL` only while it runs
migrations and the idempotent release loader. It is deliberately not a `render.yaml` pre-deploy
command, because provider pre-deploy variables would also expose that credential to the web service.
The web service must use a separate role granted `CONNECT`, schema `USAGE`, and `SELECT` only. Do
not give the API migration/insert privileges.

## Frontend variables

| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | exact HTTPS API origin |
| `GOATLAB_RELEASE_ID` | frozen release ID |
| `GOATLAB_PUBLICATION_RIGHTS_APPROVED` | `false` until the external rights gate is documented as approved |

Vercel project discovery returned no configured team in the STEP-0020 environment. No deployment
was created. Create/link the project only in an authorized account, set root directory to
`frontend`, configure Preview and Production variables separately, and keep Production protected
or undiscoverable until rights approval.

## Build and deploy commands

```bash
PYTHONPATH=src:. python pipelines/product/package_ranking_release.py \
  --output /secure/staging/goatlab-ranking-release-2026-v2-probabilistic.tar.gz
docker build -f Dockerfile.api -t goatlab-api:step-0020 .
```

Upload the archive without changing bytes to the configured private R2 object key, record its
printed SHA-256, configure secrets, then run
`deploy/api/load-release.sh` from an access-controlled operator/CI environment with the loader DB
credential. Destroy that job's credential after use. The API command is
`deploy/api/start.sh`. The checked-in `render.yaml` deliberately sets `autoDeployTrigger: off`.

Public DNS, search indexing, and public announcements are forbidden until the rights gate changes.

## STEP-0020B provider-access result

A fresh access audit on 2026-09-21 found no authorized live provider resources: the connected
Vercel integration returned zero teams, no cloud/database/container credential variables were
present, no deployment CLI was installed, and the repository had neither a Vercel project link nor
a Git remote. Therefore the table above remains the approved target architecture, not a claim that
those services are live. No production URL, database identifier, bucket, image, or domain exists in
the project record yet.

Do not substitute local preview results for deployment evidence. Resume with an authorized
provider account and preserve the frozen release, draw, migration, and transport hashes exactly.
