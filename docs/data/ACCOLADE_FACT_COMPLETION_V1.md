# All-Star and statistical-leader fact completion V1

## Scope and versions

STEP-0011 closes the two factual gaps left by `official-player-awards-canonical-v1`. It uses methodology `all-star-stat-leader-facts-v1`, frozen corpus `GOATLAB-HIST-V1` (`283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`), and `nba_api` 1.11.4. No accolade value, composite, ranking, or player-name join exists.

## All-Star evidence

All-Star applicability begins in 1950-51. The 1998-99 lockout season is `NO_GAME_HELD`; 1946-47 through 1949-50 are `NOT_APPLICABLE`. Seventy-five applicable season requests to bulk `PlayerGameLogs` yielded actual game participation, including 20 players in 1950-51. `LeagueDashPlayerStats` All Star Base/Totals was also audited but did not return early-era rows; it begins empirically at 1996-97 and is supporting evidence only.

Eighty distinct All-Star game IDs were observed because 2024-25 contains three event games and 2025-26 contains four. Official `BoxScoreTraditionalV3` responses provide event-game roster listings keyed by official player ID. This establishes `OFFICIAL_EVENT_GAME_ROSTER`, not universally original selection or replacement status. A blank zero-stat `PERSON_ID=1302` row in the 1997 game was quarantined as a source placeholder because it has no player identity evidence.

The canonical evidence contains 1,852 player-seasons across 472 players: 1,767 with roster evidence, 1,746 with participation evidence, and 1,799 game appearances. Reconciliation with candidate-scoped PlayerAwards produced 1,730 award+roster+played, 21 award+roster+DNP, 85 award-only, six played without an award event after successful querying, and ten player-season rows for eight formerly unqueried players. `NOT_QUERIED` remains NULL, never false.

Modern format caution is explicit. The 2025 mini-tournament includes Rising Stars participants in event game evidence; the table does not promote all such participants to original NBA All-Star selections. The 2026 round-robin format similarly retains multiple game IDs without pretending that games equal selections.

## Statistical leader evidence

The regular-season `LeagueLeaders` matrix contains 342 applicable PerGame requests: PTS and AST from 1946-47, REB from 1950-51, and STL/BLK from 1973-74. Forty-three representative Totals requests audit rate-versus-total behavior. PTS/REB/AST source rows begin empirically in 1951-52; STL and BLK return rows at their 1973-74 introduction.

Every applicable season/category also receives an independent frozen-corpus calculation: raw per-game leader, raw total leader, and—only with `RELIABLE` empirical metric coverage—the established STEP-0007 qualified-population leader. The qualification is research evidence, not a retroactive claim about NBA title rules. Current NBA minimums are validation context only.

Silver contains 422 union evidence events: 330 official-source rank-one events and 253 derived-qualified events. Partition reconciliation is 238 exact matches, 10 qualification differences, 83 derived coverage gaps, and 11 source gaps. No rank-one ties were returned empirically; tie-preserving logic is tested and no arbitrary tiebreak exists. No event is labeled `OFFICIAL_TITLE` merely from a raw maximum.

## Outputs and reproducibility

Generated ignored outputs are `player_all_star_evidence` (1,852 rows), `player_stat_leaders` (422), `player_career_all_star` (472), `player_career_stat_titles` (157), and `player_career_accolades_complete` (5,103). Together they occupy 312,434 bytes and fingerprint to `e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880`.

The controlled source matrix contains 615 requests: 75 PlayerGameLogs, 75 LeagueDashPlayerStats, 80 BoxScoreTraditionalV3, and 385 LeagueLeaders. Across the probe and completion run, 606 network requests supplied missing cache entries and nine scopes reused valid cache; recorded response time was 453.32 seconds. The acquisition required no retries or terminal failures. The certification rebuild issued zero network requests, ran in 2.1 seconds, and reproduced every output hash.

## Interpretation limits

Event-game roster listing is not a universal original-selection roster. Historical replacement/starter semantics remain unavailable. Exact historical leader qualification rules are not inferred from current rules. Early player-game metric sparsity blocks derived REB/AST/STL/BLK leaders in many seasons even when LeagueLeaders returns source rows. These NULL/gap states are evidence, not zero accolades.
