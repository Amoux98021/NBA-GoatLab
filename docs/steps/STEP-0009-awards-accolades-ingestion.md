# STEP-0009 — Official awards and accolades acquisition and canonicalization

## 1. Objective

Acquire the bounded STEP-0008 candidate universe from official NBA Stats `PlayerAwards`, preserve the complete master identity universe and raw taxonomy, create factual canonical Silver events and descriptive Gold counts, and introduce no award weighting or ranking.

## 2. Motivation

The legacy nbadb snapshot has no awards. `PlayerAwards` is official and structured but player-scoped, historically heterogeneous, and broader than the initial vocabulary. The project requires facts and source gaps before any future accolade methodology.

## 3. Inputs

- Clean main after STEP-0008 (`e19dec6`).
- GOATLAB-HIST-V1 fingerprint `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`.
- STEP-0008 candidate universe: 2,140 of 5,103 players under `union_q5_or_p90_recommended`.
- Existing `nba_api` 1.11.4 bounded client and ignored Bronze cache.
- Official NBA history pages used only for limited validation.

## 4. Work performed

- Probed 20 era/accolade-diverse official IDs before final taxonomy definition.
- Accepted ADR-0013 for candidate-scoped acquisition semantics and ADR-0014 for taxonomy/coverage policy.
- Evolved the canonical `PlayerAward` contract while retaining project-owned identifiers and raw provenance.
- Preserved the V1 schema artifact and exported the evolved contract as canonical schema V2.
- Acquired all 2,140 candidates serially with checkpointing and bounded retries.
- Inventoried and mapped every observed raw description and subtype combination.
- Normalized seasons and structured team numbers without text inference.
- Generated deterministic Silver event and Gold count Parquet.
- Audited All-NBA, All-Defense, major awards, All-Star, statistical titles, duplicates, identity, and non-candidate semantics.
- Rebuilt from cache and verified byte-identical partition/report hashes.

## 5. Files created or changed

Implementation, canonical schemas/export, fixture tests, ADR-0013/0014, `AWARDS_ACCOLADES_V1.md`, award taxonomy/coverage/acquisition/canonicalization/case/reference/output/quarantine reports, source manifest, methodology, data dictionary, experiments, project log, mapping document, and this record. Generated Bronze/Silver/Gold remains ignored.

## 6. Probe and acquisition matrix

The 20-player probe returned 1,220 rows across 19 populated and one empty response with zero retries. Full acquisition accounted for 2,140 candidates: 1,187 `SUCCESS_WITH_ROWS`, 953 `SUCCESS_EMPTY`, zero failed, zero retried, and 2,963 `NOT_QUERIED` master players. It issued 2,121 new requests and reused 19 probe caches.

## 7. Data observations

- Actual schema has the 14 documented fields; all observed `TYPE` values are `Award`.
- Full taxonomy has 33 descriptions and 8,137 events; final unknown descriptions are zero.
- Integral-float source IDs affected 37 rows and normalize exactly to requested official IDs.
- All-NBA has 400 First, 395 Second, and 190 Third events. All-Defense has 297 First and 295 Second.
- Major boundaries empirically match official introduction history.
- All-Star rows are present but cannot encode selection/replacement/participation semantics completely.
- Statistical titles are absent from `PlayerAwards`.

## 8. Decisions

- Candidate scope controls acquisition only; every master player remains visible.
- `NOT_QUERIED` count fields are NULL; `SUCCESS_EMPTY` count fields are observed zero.
- Exact raw descriptions plus structured fields define taxonomy; new descriptions default to `UNKNOWN`.
- Calendar-only labels never become speculative NBA seasons.
- Minor, team, external, and non-performance events remain preserved without value.
- Statistical titles should later be derived from the frozen corpus rather than added from a new provider here.

## 9. Validation/tests

Validated identity, statuses, season mapping, taxonomy completeness, controlled vocabulary, structured team levels, deterministic IDs, recurring-event preservation, duplicate safety, pre-introduction semantics, provenance, factual counts, case studies, and non-candidate NULL behavior. Official count checks exactly matched MVP, Finals MVP, DPOY, Sixth Man, MIP, and Conference Finals MVP. The cache-only certification issued zero network calls and reproduced fingerprint `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258` plus all committed report hashes. Complete Pytest, Ruff, strict Mypy, schema/artifact validation, and whitespace checks passed.

## 10. Result

Silver contains 8,137 unique award events in 32 partitions. Gold contains one accolade-count row for all 5,103 master players in 32 partitions. Generated output occupies 1,554,774 bytes. Raw PlayerAwards cache occupies 2,685,108 bytes; the ignored checkpoint is 3,335,461 bytes.

## 11. Known limitations

- The source run is candidate-scoped; it is not a complete league-wide inventory for non-candidates.
- All-Star semantics remain partial and need a separate official roster acquisition.
- Statistical titles require later frozen-corpus derivation.
- Calendar-only Hall of Fame/Olympic events cannot join to an NBA season without additional methodology.
- Candidate-based Gold counts are facts through the retrieval cutoff, not value judgments.

## 12. Explicit decision: PASS

**PASS.** All 2,140 candidates have successful terminal status; failures are never empty; taxonomy is exhaustive; major awards and structured levels normalize deterministically; nonexistence, non-selection, queried-empty, and not-queried remain distinct; Silver keys are duplicate-safe; Gold contains counts only; All-Star/statistical-title gaps are explicit; and cache-only rebuilds reproduce every output hash.

## 13. Recommended STEP-0010

Build a coverage-aware team-success and postseason-outcome factual foundation from the frozen game/team corpus, separating player participation from franchise results and assigning no championship or winning value. A small separate official All-Star roster feasibility step may instead precede it if complete selection semantics are required before composite methodology.
