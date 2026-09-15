# ADR-0033: Use official player-career totals for versioned historical recovery

- Status: Accepted
- Date: 2026-09-14
- Decision owners: GOATLab data methodology
- Supersedes: none
- Related: ADR-0001, ADR-0003, ADR-0006, ADR-0007, ADR-0008, ADR-0032

## Context

`GOATLAB-HIST-V1` uses the official bulk `PlayerGameLogs` source. Its early rows are valid but
metric-level sparse: for example, early assists and shot attempts are absent from most individual
game rows even though the league recorded those statistics and official player career records
contain exact season totals. The conservative STEP-0005/0006 partition-wide 99% aggregation rule
correctly withheld partial sums, but the resulting Silver table cannot distinguish a statistic
that was unrecorded from one that was simply unavailable through that bulk endpoint.

STEP-0015E consequently classified many seasons as analytically sparse. Before treating that
sparsity as fundamental, GOATLab needs a factual source that is keyed by official player ID and
exposes the historical season totals.

## Decision

Use the official NBA Stats `PlayerCareerStats` endpoint, in `Totals` mode, as a supplemental
player-scoped recovery source for all 2,234 players with a qualified pre-1996 Candidate D season.
This broader deterministic scope permits both recovery and an audit of already populated values;
it is not a player-quality filter.

- Requests use official `PLAYER_ID`; names remain diagnostic only.
- Only the `SeasonTotalsRegularSeason` result set and NBA/BAA `LEAGUE_ID=00` rows are eligible.
- A source `TOT`/team-zero row is authoritative for a traded season. An unexpected multi-team
  season without such a row is rejected rather than summed speculatively.
- From 1946-47 through 1995-96, dedicated official player-career season totals take precedence over
  a conflicting aggregate from the empirically incomplete `PlayerGameLogs` source. Existing facts
  remain unchanged in V1 and every conflict is retained in the reconciliation report. From 1996-97
  onward, the already Base/Totals-reconciled frozen facts retain precedence.
- Previously absent values may enter only a new research Silver artifact with field-level source
  and recovery semantics.
- Percentages are exact ratios of observed makes and attempts. TS remains the documented
  `PTS / (2 * (FGA + 0.44 * FTA))` analytical estimate and is labeled derived, not source-direct.
- The frozen corpus and all published V1 scoring artifacts remain immutable.

## Alternatives considered

- Treat every early null as historically unrecorded.
- Sum sparse player-game rows while treating missing games as zero.
- Predict assists, rebounds, or shooting evidence.
- Scrape a third-party statistics site before exhausting the official player-scoped source.
- Mutate `GOATLAB-HIST-V1` in place.

## Consequences

Historical factual coverage can improve without imputation or name matching, and the recovery is
fully cacheable and replayable. The decision also documents a real V1 pipeline limitation: a
partition-wide non-null threshold can accept non-null placeholders or incomplete game coverage and
therefore does not independently validate a season total. Acquisition is more expensive than a bulk
request because it is player-scoped. The new table is explicitly research-versioned; promoting it
into a future frozen corpus requires a separate release decision. Statistics the NBA did not record
remain unavailable, and source conflicts are never averaged.
