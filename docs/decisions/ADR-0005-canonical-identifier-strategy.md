# ADR-0005: Canonical identifier strategy

## Context

Player and team names change, collide, and vary across sources. NBA provider IDs are useful source keys but should not become the only project identity contract. Rebuilds must assign the same identifiers deterministically without a mutable lookup service.

## Decision

Silver V1 uses project-owned string identifiers derived with UUIDv5 from a fixed repository namespace plus `(entity, provider, provider_id)`. Player identity is anchored to the NBA player ID, never a name. Game identity is anchored to the NBA game ID. Franchise identity is anchored to the NBA franchise/team lineage ID. A team identity includes the provider lineage ID and version/window identity so historical team-name versions can remain distinct while referencing one franchise.

Provider IDs remain separate nullable fields for traceability. Future cross-provider reconciliation will add explicit identity crosswalk evidence rather than changing identifiers silently.

## Alternatives considered

- Use names as relational keys.
- Expose NBA IDs directly as every canonical primary key.
- Allocate random UUIDv4 identifiers during each rebuild.
- Depend immediately on a mutable identity database/sequence.

## Consequences

The same audited input deterministically produces the same canonical IDs, and display-name corrections do not change identity. IDs are opaque and require preserved provider crosswalks. A change to the namespace or identity inputs is a breaking schema/methodology change requiring a new ADR and migration.

## Status

Accepted — 2026-08-19.
