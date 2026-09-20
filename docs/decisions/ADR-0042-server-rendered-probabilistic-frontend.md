# ADR-0042 — Server-rendered probabilistic leaderboard frontend

Status: Accepted

Date: 2026-09-20

Related: ADR-0039, ADR-0040, ADR-0041, STEP-0016, STEP-0017, STEP-0018

## Context

STEP-0017 exposes immutable, typed read-only ranking summaries. The repository's `frontend/`
was a placeholder. A public-facing presentation must retain the calibrated distribution and
evidence-status semantics without implementing ranking logic or transferring 2,500-draw arrays
to browsers. The API's Top-100 endpoint has the frozen display order; its leaderboard endpoint
supports search, filters, and pagination.

## Decision

Use a small Next.js App Router / TypeScript application in `frontend/`, with custom CSS and
Server Components for all read-only ranking pages. A single typed server-side API client checks
release identity and response shape. The Top 100 is rendered in API order, and the full list's
GET form delegates search/filter/pagination to the backend. Only Next's error boundary needs a
Client Component. API reads are release-scoped where supported and revalidated hourly; a
mismatched release is an error, never a silent fallback. No raw paired draws reach the client.

Use a desktop table and responsive cards below tablet widths. Display position is navigational;
80%/90% rank bands, Overall range, Top-N probability, and neutral evidence status remain visible.
The interval-native center is never shown alone. The `PUBLICATION_RIGHTS_REVIEW_REQUIRED` gate
continues to block public deployment despite local frontend readiness.

## Consequences

- A frozen release change requires a new API/release configuration and explicit validation.
- The current API has no bubble endpoint; the home page shows nearby display positions from
  `/leaderboard` as a clearly labeled cutoff preview, not the complete STEP-0016 bubble artifact.
- Methodology weights are display-only frozen documentation copy because the public
  `/methodology` response currently provides versions and disclosures, not numeric weights.
  The frontend never uses them for computation.
- Future pairwise UX can consume `/compare` in STEP-0019; no dead compare control is shipped.
