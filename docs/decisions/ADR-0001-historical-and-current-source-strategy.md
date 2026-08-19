# ADR-0001: Historical and current data-source strategy

## Context

The project needs broad historical coverage and a maintainable path for refreshing current-season data without mixing arbitrary third-party CSV snapshots.

## Decision

Use Wyatt Walsh's official `nbadb`/Kaggle distribution as the primary historical bulk snapshot. Use NBA Stats through `nba_api` for current-season refreshes. Both sources enter Bronze and map into project-owned Silver schemas. Do not begin with Basketball Reference scraping or unrelated Kaggle CSV datasets.

## Alternatives considered

- Scrape Basketball Reference as the initial source.
- Combine unrelated Kaggle datasets.
- Query NBA Stats for the entire history on each build.

## Consequences

Historical builds are faster and provenance is concentrated, but the project inherits endpoint-specific coverage gaps and must audit every acquired snapshot. Current refresh code must reconcile to the same canonical keys and semantics.

## Status

Accepted — 2026-08-19.
