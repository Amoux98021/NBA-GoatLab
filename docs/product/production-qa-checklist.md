# Production QA checklist

Record every item for Preview and, after rights approval, Production.

## Integrity

- [ ] Commit is the approved STEP-0020 commit.
- [ ] Release ID and fingerprint match the frozen release.
- [ ] Draw and migration hashes match the deployment record.
- [ ] DB load counts: 5,103 players; 1,882 rankable; 3,221 unavailable; 100 Top-100 entries.
- [ ] Repeated loader invocation reports `ALREADY_LOADED`.
- [ ] API role cannot INSERT, UPDATE, DELETE, CREATE, or run migrations.

## API

- [ ] Health is 200 and reports DB/release/draw readiness without secrets.
- [ ] Releases, leaderboard, Top 100, methodology, profile, and compare endpoints pass smoke tests.
- [ ] Same-player is 400; unknown is 404; unrankable comparison is 422.
- [ ] CORS permits only configured HTTPS frontend origins.
- [ ] HSTS, `nosniff`, frame denial, referrer, and permissions headers are present.
- [ ] Cold/warm response timings are recorded; no pairwise request reloads the NPZ.

## Frontend

- [ ] Home, Top 100, all-player leaderboard, search/filter/pagination, profile, methodology, compare,
      unknown, and unavailable states render against the deployed API.
- [ ] Desktop widths 1024/1440 and mobile widths 375/768 have no page-level horizontal overflow.
- [ ] Keyboard navigation, labels, focus, contrast, status text, and disclosure tooltips are usable.
- [ ] Rank/interval/Top-N values reconcile with direct API responses.
- [ ] Comparison reversal is complementary and unknown/unavailable states never invent values.
- [ ] `robots.txt`, metadata robots, and `X-Robots-Tag` block indexing before rights approval.

## Reliability and operations

- [ ] API cold start and first draw load are measured.
- [ ] DB timeout, draw missing/corrupt, backend unavailable, and invalid release configuration fail
      closed with no fabricated data.
- [ ] Rollback is rehearsed using immutable deployment history.
- [ ] No secrets appear in source, built browser JavaScript, logs, or API payloads.
- [ ] Dependency/vulnerability scan findings are triaged.
- [ ] Publication-rights owner has explicitly signed off before public launch.

STEP-0020 local verification satisfies code/build checks only. Provider, browser-on-deployed-URL,
failure-injection, and rights-review boxes remain open until authorized resources exist.
