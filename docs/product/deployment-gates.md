# Production deployment gates

STEP-0017 created the local read-only backend and STEP-0020 hardened a deployable topology. Neither
authorizes publication of source-derived analytics. A deployment must explicitly track:

| Gate | Required evidence |
|---|---|
| `PUBLICATION_RIGHTS_REVIEW_REQUIRED` | Separate source-rights/legal review or permission before public/commercial release; unresolved in STEP-0017. |
| Immutable release | Configured release ID and SHA-256 equal the frozen manifest; never select another release silently. |
| Database integrity | Migrations applied by checksum; loader committed full reconciled release; repeat load is no-op. |
| Draw integrity | Paired NPZ present, SHA-256 verified, 1,882 × 2,500 aligned arrays. |
| Least privilege | API database role has SELECT only; controlled loader role alone can INSERT. No write HTTP routes. |
| Network | Explicit frontend CORS origins; TLS for remote DB; no credentials in logs or source. |
| Readiness | `/api/v1/health` reports DB/release/draw state; degraded connectivity returns HTTP 503. |
| Reproducibility | New releases get new IDs and fingerprints; historical published rows remain immutable. |

The SQL uses ordinary PostgreSQL data types, JSONB, standard indexes, and PL/pgSQL triggers; no
Neon-specific extension is required. STEP-0020 confirmed Neon compatibility in configuration but
did not provision or mutate a database. Full cross-player calibration uncertainty remains a
disclosed research limitation inherited from the frozen methodology; the API does not suppress it.
See [production-deployment.md](production-deployment.md),
[production-qa-checklist.md](production-qa-checklist.md), and
[publication-rights-gate.md](publication-rights-gate.md).
