# Official NBA awards and accolades V1

## Scope

STEP-0009 acquires official NBA Stats `PlayerAwards` for the 2,140-player STEP-0008 candidate universe and preserves all 5,103 master identities. It produces factual Silver events and descriptive Gold counts only. It assigns no award value, points, score, or ranking.

Methodology version: `official-player-awards-canonical-v1`

## Acquisition result

The bounded single-threaded run used `nba_api` 1.11.4, 30-second timeouts, at most three attempts, deterministic cache keys, and 0.75-second pacing. Nineteen taxonomy-probe responses were reused and 2,121 network requests were issued. All 2,140 candidates terminated successfully: 1,187 `SUCCESS_WITH_ROWS`, 953 `SUCCESS_EMPTY`, zero failures, and zero retries. The 2,963 non-candidates remain `NOT_QUERIED`.

The run observed 8,137 raw events. Integral-float `PERSON_ID` values affected 37 early-player rows; converting only mathematically integral numeric representations to the identical official ID resolved them without names. Final Silver contains 8,137 unique canonical events, zero quarantines, and zero duplicate event IDs.

## Canonicalization

One Silver row is one official source event. Its deterministic ID hashes the complete raw row, so row order is irrelevant while distinct week/month/conference fields remain distinct. Exact source duplicates would collapse; ambiguous collisions would quarantine.

Valid `YYYY-YY` labels map to canonical start-year `season_id`. Hall of Fame and Olympic calendar years remain in `season_label_raw` with NULL `season_id`; the pipeline does not guess an NBA season. Structured team numbers map to `FIRST`, `SECOND`, or `THIRD` for All-NBA, All-Defense, All-Rookie, and Cup All-Tournament only.

The exhaustive inventory contains 33 raw descriptions. The initial probe established 29 mappings. Full acquisition added four evidence-based mappings: `NBA All-Star Selection`, `NBA Comeback Player of the Year`, `NBA Defensive Player of the Month`, and `Olympic Appearance`. Final unknown-description count is zero; future unseen values default to `UNKNOWN` and remain preserved.

## Event counts and coverage

| Type | Events | First–last observed season |
|---|---:|---|
| MVP | 71 | 1955-56–2025-26 |
| Finals MVP | 58 | 1968-69–2025-26 |
| Conference Finals MVP | 10 | 2021-22–2025-26 |
| DPOY | 44 | 1982-83–2025-26 |
| ROY | 76 | 1952-53–2025-26 |
| MIP | 41 | 1985-86–2025-26 |
| Sixth Man | 44 | 1982-83–2025-26 |
| All-NBA | 985 | 1946-47–2025-26 |
| All-Defense | 592 | 1968-69–2025-26 |
| All-Rookie | 485 | 1962-63–2025-26 |
| NBA All-Star | 1,837 | 1950-51–2025-26 |
| Player of Month / Week | 408 / 1,578 | 1979-80–2025-26 |

All-NBA levels are 400 First, 395 Second, and 190 Third. All-Defense levels are 297 First and 295 Second. Third Team is observed only for All-NBA and is not fabricated in earlier eras.

All-Star is `PARTIAL`: rows exist from 1950-51, but the endpoint cannot distinguish original selection, replacement, injury, or actual game participation. A later official roster pipeline is required. No scoring/rebounding/assist/steal/block title descriptions were observed; their status is `REQUIRES_SEPARATE_SOURCE`, with frozen-corpus leader derivation preferred.

## Official reference validation

Limited validation against official NBA history tables exactly reconciled full candidate-endpoint counts for MVP (71), Finals MVP (58), DPOY (44), Sixth Man (44), MIP (41), and Conference Finals MVP (10). All-NBA and All-Defense boundaries and team-level structure matched official history. Candidate-scoped totals are not asserted to be complete league-wide counts for every honor.

Reference URLs and the fixed retrieval timestamp are recorded in `award-official-reference-validation.json`. No web page was ingested into Silver.

## Outputs and reproducibility

Generated, ignored outputs comprise 32 Silver `player_awards` partitions (8,137 rows, 866,180 bytes) and 32 Gold `player_career_accolades` partitions (5,103 rows, 688,594 bytes). Their aggregate fingerprint is `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258`.

The certification run was cache-only, issued zero network requests, rebuilt in 1.99 seconds, reproduced all 64 partition hashes, and left every committed generated report byte-identical.

## Interpretation limits

Gold fields are factual counts only. A zero is valid only after successful querying. `NOT_QUERIED` count fields remain NULL. Team championships are retained as source events but receive no value. External and non-performance events remain auditable and are not silently treated as competitive NBA awards.
