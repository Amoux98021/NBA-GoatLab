# Runtime resource limits

Snapshot date: **2026-09-22**

Provider quotas in this document are a date-stamped operational snapshot. They can change without a
repository update. Reverify every value against the linked official provider documentation before
an infrastructure, traffic, build, storage, or pricing decision.

GOATLab's current operational target is **$0/month**. No coding agent may upgrade a provider plan,
enable a billable feature, add a paid external service, or add keepalive traffic without explicit
human approval. If proposed work may exceed a free-tier limit, stop and explain the expected
resource impact before implementing it.

## Vercel Hobby

- 1,000,000 Edge Requests per month
- 100 GB Fast Data Transfer per month
- 1,000,000 Function Invocations per month
- 4 active CPU-hours per month
- 360 GB-hours provisioned memory per month
- 100 deployments per day per account
- 45-minute maximum build duration

Official references:

- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [Vercel limits](https://vercel.com/docs/limits)
- [Vercel pricing](https://vercel.com/pricing)

## Render

Workspace: **Hobby**  
Compute: **one Free Docker web service**

- 750 free instance-hours per workspace per calendar month
- spins down after 15 minutes without inbound traffic
- ephemeral local filesystem
- 5 GB included outbound bandwidth per month
- 500 standard build-pipeline minutes per month
- free services can restart
- do **not** implement external keepalive traffic merely to prevent spin-down

Official references:

- [Render free services](https://render.com/docs/free)
- [Render outbound bandwidth](https://render.com/docs/outbound-bandwidth)
- [Render build pipeline](https://render.com/docs/build-pipeline)
- [Render pricing](https://render.com/pricing)

## Neon Free

Use the newest known 2026 plan values where older Neon material conflicts:

- 100 CU-hours per project per month
- 0.5 GB database storage per project
- 10 branches per project

Official latest reference:

- [Neon Backend is GA](https://neon.com/blog/neon-backend-is-ga)

The production FastAPI runtime uses the **direct/unpooled** Neon endpoint with the dedicated
SELECT-only `goatlab_api` role. GOATLab's PostgreSQL startup options are not compatible with the
Neon pooled endpoint. Do not silently change this connection mode. A privileged direct connection
remains reserved for controlled migrations and immutable release loads.

## Cloudflare R2 Standard

- 10 GB-month storage per month free
- 1,000,000 Class A operations per month free
- 10,000,000 Class B operations per month free
- Internet egress free

Official reference:

- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)

## GOATLab application API contract

### `GET /api/v1/leaderboard`

- default limit: 100
- maximum limit: 1,882
- includes distribution-rankable careers only

### `GET /api/v1/top100`

- exactly 100 entries

### `GET /api/v1/players/{player_id}`

- profiles exist for the complete canonical set of 5,103 players

### `GET /api/v1/compare/{a}/{b}`

- players must differ
- both players must be distribution-rankable
- unavailable comparisons retain the existing explicit failure semantics

There is currently **no application-level global request rate limiter**. Frontend and product code
must not introduce:

- periodic API polling or automatic refresh loops
- keepalive requests
- one API request per leaderboard row, card, or animation
- API requests triggered continuously by scrolling
- unnecessary repeated release downloads
- unnecessary remote image or API dependencies

Preserve server rendering, bulk endpoint use, and existing caching/revalidation behavior. Animation
must use already-rendered values and must not generate backend traffic.

## Production snapshot

- release: `goatlab-ranking-release-2026-v2-probabilistic`
- release fingerprint: `2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`
- player profiles: 5,103
- distribution-rankable careers: 1,882
- Overall-ranking unavailable: 3,221
- dimension records: 35,721
- Top-100 entries: 100
- paired draws per rankable career: 2,500
