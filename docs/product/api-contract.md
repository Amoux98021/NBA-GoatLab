# STEP-0016 read-only API contract

STEP-0016 implements typed domain models and an artifact-backed `RankingRepository`, not a new
FastAPI application or live database. A future FastAPI adapter should be thin and return the
Pydantic models in `src/goatlab/product/models.py` without reading research JSON ad hoc.

| Route | Repository operation | Response / errors |
|---|---|---|
| `GET /api/v1/leaderboard` | `get_leaderboard(limit, offset, search, active, status)` | Release-scoped `LeaderboardEntry[]` plus pagination/release metadata. Maximum limit 1,882. |
| `GET /api/v1/players/{player_id}` | `get_player` | `PlayerProfile`; 404 for unknown canonical ID. An unavailable player still has a profile. |
| `GET /api/v1/compare/{a}/{b}` | `compare_players` | `PairwiseResponse`; 400 for same ID, 404 for unknown, 422 for known unavailable. |
| `GET /api/v1/methodology` | `get_methodology` | Frozen policy, versions, caveats, and disclosure copy. |
| `GET /api/v1/rankings/{version}` | `get_release` | Fingerprinted `RankingRelease`; 404 for unknown release. |

For `ranking_version`, the first adapter must accept only the immutable built release ID; it
must not silently substitute another release. Search uses a normalized name token over
canonical names and never merges similarly named players. Status and active filters select
rows but never reorder or rescore them. A client receives ready-to-render bands, probabilities,
and labels; it must not reconstruct methodology from dimension numbers.

`get_leaderboard` defaults to 100 rows. The full 1,882-player navigation list remains available
through pagination. `get_player` also works for all 3,221 unranked identities, preserving
missingness reasons and dimension evidence. All API results include cutoff/release context;
active careers are observed to date without future projection.

## STEP-0017 implementation

The read-only FastAPI adapter now implements this contract and adds `/api/v1/health`,
`/api/v1/releases`, and `/api/v1/top100`. The leaderboard response is a typed page envelope
with `total`, `limit`, `offset`, `release_id`, and entries. The exact Top-100 artifact appears as
the `entries` array of a release-scoped response. The release route is
`/api/v1/releases/{release_id}` rather than the preliminary STEP-0016
`/api/v1/rankings/{version}` spelling. See `docs/product/api-runtime.md` for settings, errors,
readiness behavior, and deployment constraints. These engineering additions do not change the
frozen probabilistic ranking policy.
