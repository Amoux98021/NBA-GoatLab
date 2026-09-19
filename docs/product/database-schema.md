# STEP-0016 PostgreSQL database design

The committed [DDL](probabilistic-ranking-schema.sql) is PostgreSQL-compatible and suitable for
Neon, but STEP-0016 does not provision a database or require credentials. Load order is:

1. `ranking_versions` ← `db/ranking_versions.parquet`;
2. `players` ← `db/players.parquet`;
3. `player_rankings` ← `db/player_rankings.parquet`;
4. `player_rank_probabilities` ← `db/player_rank_probabilities.parquet`;
5. `player_dimensions` ← `db/player_dimensions.parquet`.

The release and canonical player ID form composite identity keys. `players` is a release-scoped
identity snapshot, so a later correction to a name cannot silently rewrite a historical
leaderboard. `player_rankings` contains only the 1,882 distribution-rankable players, while
`players` and `player_dimensions` cover all 5,103. Probability and status constraints are in
the database as well as Pydantic validation. `overall_json` and `rank_json` retain complete
versioned summaries without fragmenting every interval bound into its own SQL column.

The transactional import procedure is intentionally a next-phase implementation: verify the
release manifest hashes, load under a new `release_id`, check exact row counts and foreign keys,
then publish by changing an application-level active-release pointer. Never update rows for an
already published release. Historical releases remain addressable. The generated Parquet files
are DB-load artifacts, not raw NBA or vendor response payloads.

The paired empirical distribution artifact remains in versioned object/file storage, keyed by
release and SHA-256. Postgres holds summaries and its reference, not 4.7 million draw cells or
1.77 million redundant pairwise rows. A service can cache the compressed draw matrix after a
fingerprint check.

## STEP-0017 implementation note

The executable schema is now migration-managed in
`db/migrations/0001_probabilistic_ranking_release.sql` (ADR-0041). It extends the STEP-0016 design
snapshot with release fingerprint/hash/version metadata, exact `player_profiles` and
`top100_entries` payloads, rank-band projections copied from frozen `rank_json`, and immutable
row triggers. The loader and read-only API use this migration; the above five Parquet tables
remain unchanged and are still the normalized bulk-load inputs. See
`docs/product/database-loading.md` for the transactional import procedure.
