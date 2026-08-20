# Official NBA API player-fact feasibility probe

Observed at: `2026-08-19T16:48:31Z`  
nba_api: `1.11.4`  
Decision: **PASS**

This is bounded endpoint evidence, not a historical backfill. PlayerID was unset for PlayerGameLogs; each request was scoped only by season and season type.

## Fixed decision criteria

- **PASS:** PlayerGameLogs returns plausible bulk rows for every representative regular and playoff season from 1946-47 through 2025-26, while Advanced/Totals works from 1996-97 onward. Player-season facts can therefore be acquired directly where exposed or deterministically aggregated from official game facts.
- **PARTIAL PASS:** Some representative game-level eras or season types have gaps, but official game or season endpoints still span the early and current eras and Advanced/Totals works for at least the tested modern seasons.
- **FAIL:** Official endpoints do not yield plausible player-level facts spanning the early and current eras, leaving no defensible official bulk acquisition path.

## Probe outcomes

| Endpoint / measure | Season | Type | Outcome | Rows | Players | Games | Plausible |
|---|---:|---|---|---:|---:|---:|---|
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 1995-96 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 1995-96 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 1996-97 | Playoffs | SUCCESS_WITH_ROWS | 189 | 189 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 1996-97 | Regular Season | SUCCESS_WITH_ROWS | 441 | 441 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 1997-98 | Playoffs | SUCCESS_WITH_ROWS | 190 | 190 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 1997-98 | Regular Season | SUCCESS_WITH_ROWS | 439 | 439 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 2009-10 | Playoffs | SUCCESS_WITH_ROWS | 199 | 199 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 2009-10 | Regular Season | SUCCESS_WITH_ROWS | 442 | 442 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 2022-23 | Playoffs | SUCCESS_WITH_ROWS | 217 | 217 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 2022-23 | Regular Season | SUCCESS_WITH_ROWS | 539 | 539 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 2025-26 | Playoffs | SUCCESS_WITH_ROWS | 230 | 230 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Advanced Totals | 2025-26 | Regular Season | SUCCESS_WITH_ROWS | 582 | 582 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1946-47 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1946-47 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1955-56 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1955-56 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1961-62 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1961-62 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1973-74 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1973-74 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1979-80 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1979-80 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1984-85 | Playoffs | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1984-85 | Regular Season | SUCCESS_EMPTY | 0 | 0 | 0 | False |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1996-97 | Playoffs | SUCCESS_WITH_ROWS | 189 | 189 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 1996-97 | Regular Season | SUCCESS_WITH_ROWS | 441 | 441 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2009-10 | Playoffs | SUCCESS_WITH_ROWS | 199 | 199 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2009-10 | Regular Season | SUCCESS_WITH_ROWS | 442 | 442 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2022-23 | Playoffs | SUCCESS_WITH_ROWS | 217 | 217 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2022-23 | Regular Season | SUCCESS_WITH_ROWS | 539 | 539 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2023-24 | Playoffs | SUCCESS_WITH_ROWS | 214 | 214 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2023-24 | Regular Season | SUCCESS_WITH_ROWS | 572 | 572 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2024-25 | Playoffs | SUCCESS_WITH_ROWS | 219 | 219 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2024-25 | Regular Season | SUCCESS_WITH_ROWS | 569 | 569 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2025-26 | Playoffs | SUCCESS_WITH_ROWS | 230 | 230 | 0 | True |
| LEAGUE_DASH_PLAYER_STATS / Base Totals | 2025-26 | Regular Season | SUCCESS_WITH_ROWS | 582 | 582 | 0 | True |
| PLAYER_GAME_LOGS | 1946-47 | Playoffs | SUCCESS_WITH_ROWS | 360 | 61 | 19 | True |
| PLAYER_GAME_LOGS | 1946-47 | Regular Season | SUCCESS_WITH_ROWS | 6508 | 161 | 331 | True |
| PLAYER_GAME_LOGS | 1955-56 | Playoffs | SUCCESS_WITH_ROWS | 401 | 60 | 21 | True |
| PLAYER_GAME_LOGS | 1955-56 | Regular Season | SUCCESS_WITH_ROWS | 5622 | 92 | 290 | True |
| PLAYER_GAME_LOGS | 1961-62 | Playoffs | SUCCESS_WITH_ROWS | 515 | 64 | 29 | True |
| PLAYER_GAME_LOGS | 1961-62 | Regular Season | SUCCESS_WITH_ROWS | 6812 | 113 | 360 | True |
| PLAYER_GAME_LOGS | 1973-74 | Playoffs | SUCCESS_WITH_ROWS | 743 | 89 | 41 | True |
| PLAYER_GAME_LOGS | 1973-74 | Regular Season | SUCCESS_WITH_ROWS | 13380 | 222 | 697 | True |
| PLAYER_GAME_LOGS | 1979-80 | Playoffs | SUCCESS_WITH_ROWS | 918 | 129 | 48 | True |
| PLAYER_GAME_LOGS | 1979-80 | Regular Season | SUCCESS_WITH_ROWS | 17782 | 287 | 902 | True |
| PLAYER_GAME_LOGS | 1984-85 | Playoffs | SUCCESS_WITH_ROWS | 1359 | 185 | 68 | True |
| PLAYER_GAME_LOGS | 1984-85 | Regular Season | SUCCESS_WITH_ROWS | 19249 | 320 | 943 | True |
| PLAYER_GAME_LOGS | 1996-97 | Playoffs | SUCCESS_WITH_ROWS | 1412 | 189 | 72 | True |
| PLAYER_GAME_LOGS | 1996-97 | Regular Season | SUCCESS_WITH_ROWS | 23757 | 441 | 1189 | True |
| PLAYER_GAME_LOGS | 2009-10 | Playoffs | SUCCESS_WITH_ROWS | 1674 | 199 | 82 | True |
| PLAYER_GAME_LOGS | 2009-10 | Regular Season | SUCCESS_WITH_ROWS | 24813 | 442 | 1230 | True |
| PLAYER_GAME_LOGS | 2022-23 | Playoffs | SUCCESS_WITH_ROWS | 1728 | 217 | 84 | True |
| PLAYER_GAME_LOGS | 2022-23 | Regular Season | SUCCESS_WITH_ROWS | 25894 | 539 | 1230 | True |
| PLAYER_GAME_LOGS | 2023-24 | Playoffs | SUCCESS_WITH_ROWS | 1685 | 214 | 82 | True |
| PLAYER_GAME_LOGS | 2023-24 | Regular Season | SUCCESS_WITH_ROWS | 26401 | 572 | 1230 | True |
| PLAYER_GAME_LOGS | 2024-25 | Playoffs | SUCCESS_WITH_ROWS | 1804 | 219 | 84 | True |
| PLAYER_GAME_LOGS | 2024-25 | Regular Season | SUCCESS_WITH_ROWS | 26306 | 569 | 1230 | True |
| PLAYER_GAME_LOGS | 2025-26 | Playoffs | SUCCESS_WITH_ROWS | 1921 | 230 | 85 | True |
| PLAYER_GAME_LOGS | 2025-26 | Regular Season | SUCCESS_WITH_ROWS | 26651 | 582 | 1230 | True |

## Interpretation

The JSON companion is authoritative for response hashes, complete returned field lists, null rates, candidate-key duplicates, timing, retries, and error classifications. A zero returned by an endpoint for a pre-introduction statistic is retained only as source audit evidence; the canonical mapping converts that value to NULL.

Official documented boundaries come from the NBA Stats FAQ: base statistics and digitized box scores begin in 1946-47; advanced statistics begin in 1996-97; individual traditional metrics have later introductions. Empirical response behavior is reported independently.

## Empirical boundaries and quality

- PlayerGameLogs returned rows for every tested Regular Season and Playoffs scope from 1946-47 through 2025-26.
- Base/Totals returned successful empty results through 1984-85 and rows from the next tested season, 1996-97, onward.
- Advanced/Totals returned successful empty results for 1995-96 and rows for every tested season from 1996-97 onward.
- Early player-game rows are metric-sparse: for example, 1946-47 Regular Season has 0% PTS nulls but 92.12% FGA nulls and 97.99% AST nulls. Availability of rows is not blanket metric reliability.

## Identity coverage

- Returned official IDs (all probes): 2753
- Legacy player matches (all probes): 2444 (88.78%)
- Legacy player matches (2022-23 overlap): 536 (99.08%)

Names are diagnostic only. `PLAYER_ID` maps to canonical `player_id` through the stable NBA business-key transform.

## Limitations

- This matrix samples representative seasons; it is not a complete season-by-season audit.
- NBA Stats is an operational web API without a project-owned availability guarantee.
- Empty and failed responses remain distinct; neither is interpreted as a season of zeros.
- Full raw responses remain in ignored Bronze storage.
