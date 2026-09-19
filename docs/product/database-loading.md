# Transactional ranking-release database loading

STEP-0017 consumes the immutable STEP-0016 release
`goatlab-ranking-release-2026-v2-probabilistic`. Do not edit its generated files or copy raw
research/Gold rows into this database. `DATABASE_URL` is read from the environment; never pass a
credential in a command argument or commit it to Git.

```bash
export DATABASE_URL='postgresql://USER@HOST:PORT/DB?sslmode=require'
PYTHONPATH=src:. .venv/bin/python -m pipelines.product.migrate_product_database
PYTHONPATH=src:. .venv/bin/python -m pipelines.product.load_ranking_release --dry-run
PYTHONPATH=src:. .venv/bin/python -m pipelines.product.load_ranking_release
```

For an ordinary local Postgres, omit `sslmode=require` as appropriate. The migration runner
applies sorted `db/migrations/*.sql` files in a transaction, records SHA-256 checksums in
`product_schema_migrations`, and refuses an edited migration. It uses a transaction-scoped
advisory lock. This is the project's minimal migration mechanism; no manual production DDL is
required. The checked-in STEP-0016 SQL remains a design snapshot; migration 0001 is the
executable, documented extension (ADR-0041).

The loader verifies the release manifest and every declared artifact SHA-256, validates all five
Parquet schemas, 5,103 identities/profiles, 1,882 rankable rows, 3,221 unavailable rows, 35,721
dimension rows, Top-100 order, and 2,500 aligned draws before connecting. One PostgreSQL
transaction inserts release metadata, COPY-loads normalized tables and exact response payloads,
reconciles every canonical ID/status/probability/dimension/profile/Top-100 row, then commits.
On any error it rolls back. A same-ID/same-fingerprint rerun reconciles and returns
`ALREADY_LOADED`; a same-ID/different-fingerprint rerun fails. Database triggers reject
UPDATE/DELETE of published rows. Changed content requires a new release ID.

Import order: `ranking_versions`, `players`, `player_rankings`,
`player_rank_probabilities`, `player_dimensions`, `player_profiles`, `top100_entries`.
The last two are derived from the already-frozen profile and compact Top-100 artifacts, not
new basketball inputs. Rank bands in `player_rank_probabilities` are copied from frozen
`rank_json`; no rank calculation occurs in SQL.

Only the loader credential should have INSERT rights. The API's `DATABASE_URL` should use a
separate SELECT-only role. No live Neon project is provisioned by STEP-0017.
