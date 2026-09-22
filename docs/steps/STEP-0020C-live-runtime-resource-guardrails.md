# STEP-0020C — Live runtime and resource guardrails

Date: 2026-09-22  
Status: PASS  
Scope: deployment closeout and operational governance only

## Outcome

GOATLab's live production runtime is functioning across Vercel, Render, Neon, and private
Cloudflare R2. This step closes the deployment implementation branch and records the operating
limits and cost controls needed to keep the service safe on free provider tiers.

No basketball formula, model, score, probability distribution, ranking policy, or frozen release
artifact changed.

## Live topology

| Layer | Live contract |
|---|---|
| Frontend | Vercel Hobby; Next.js server-rendered frontend |
| Backend | Render Hobby workspace; one Free Docker FastAPI web service |
| Database | Neon Postgres direct/unpooled endpoint; dedicated SELECT-only `goatlab_api` runtime role |
| Release storage | private Cloudflare R2 Standard bucket; immutable bundle fetched through S3 credentials |

The runtime remains pinned to release
`goatlab-ranking-release-2026-v2-probabilistic` and fingerprint
`2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.

## Reconciliation snapshot

- 5,103 canonical player profiles
- 1,882 distribution-rankable careers
- 3,221 Overall-ranking-unavailable careers
- 35,721 player-dimension records
- exactly 100 Top-100 entries
- 2,500 paired draws for each rankable career

## Database runtime decision

The production API uses the direct/unpooled Neon endpoint because GOATLab's PostgreSQL startup
options are incompatible with the Neon pooled endpoint. The dedicated runtime role can read the
published tables but cannot mutate them. The owner/admin role is preserved separately for
controlled migrations and immutable release loads.

ADR-0044 supersedes the pooled-endpoint portion of ADR-0043 without changing the remainder of the
deployment topology.

## Runtime and cost controls

`docs/product/RUNTIME_RESOURCE_LIMITS.md` records the 2026-09-22 Vercel, Render, Neon, and R2
operational snapshot with official references. The repository agent policy now permanently:

- targets `$0/month`;
- requires explicit human approval for plan upgrades, billable features, paid services, or
  keepalive traffic;
- requires a resource-impact explanation before work that may exceed a free tier;
- forbids polling, automatic refresh, per-row/per-animation API calls, scroll-triggered fetching,
  repeated release downloads, and unnecessary remote image/API dependencies;
- preserves server rendering, bulk endpoints, and existing cache/revalidation behavior.

The snapshot is deliberately date-stamped. Provider quotas must be checked again against official
documentation before an infrastructure change.

## API contract preserved

- `/api/v1/leaderboard`: default 100, maximum 1,882, rankable careers only
- `/api/v1/top100`: exactly 100 entries
- `/api/v1/players/{player_id}`: complete 5,103-player profile population
- `/api/v1/compare/{a}/{b}`: distinct rankable players only, with explicit unavailable semantics

There is no global application-level request limiter. The frontend therefore depends on disciplined
request behavior rather than synthetic traffic controls.

## Verification

- official provider documentation checked on 2026-09-22 for the recorded quota snapshot;
- live release identity and production counts recorded without modifying the release;
- deployment and runbook documentation corrected to the live direct/unpooled Neon behavior;
- documentation-only diff checked for formatting and secret exposure;
- no generated research/product data or credentials committed.
