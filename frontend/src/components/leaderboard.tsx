import Link from "next/link";
import { membershipLabel, number, percent, rank } from "@/lib/display";
import type { LeaderboardEntry, Top100Entry } from "@/lib/types";
import { InfoTip, StatusBadge } from "./primitives";

type Row = {
  playerId: string; name: string; position: number; active: boolean | null;
  median: number; lower80: number; upper80: number; top10: number; top25: number; top100: number;
  overallLower: number; overallUpper: number; status: string; membership: Top100Entry["top100_membership"];
};

function fromTop100(entry: Top100Entry): Row {
  return { playerId: entry.player_id, name: entry.player_name, position: entry.display_position, active: entry.active,
    median: entry.median_rank, lower80: entry.rank_lower_80, upper80: entry.rank_upper_80,
    top10: entry.top_10_probability, top25: entry.top_25_probability, top100: entry.top_100_probability,
    overallLower: entry.overall_lower_90, overallUpper: entry.overall_upper_90,
    status: entry.ranking_status, membership: entry.top100_membership };
}

function fromLeaderboard(entry: LeaderboardEntry): Row {
  return { playerId: entry.player_id, name: entry.player_name, position: entry.display_position, active: entry.active,
    median: entry.rank.median_rank, lower80: entry.rank.lower_80, upper80: entry.rank.upper_80,
    top10: entry.top_n.top_10, top25: entry.top_n.top_25, top100: entry.top_n.top_100,
    overallLower: entry.overall.lower_90, overallUpper: entry.overall.upper_90,
    status: entry.ranking_status, membership: entry.top100_membership };
}

function PlayerCard({ row }: { row: Row }) {
  return <Link className="player-card" prefetch={false} href={`/players/${encodeURIComponent(row.playerId)}`} aria-label={`View ${row.name} profile, display position ${row.position}`}>
    <div className="player-card__head"><span className="display-number">#{row.position}</span><div><strong>{row.name}</strong><span>{row.active ? "Active · to date · " : ""}{membershipLabel(row.membership)}</span></div><StatusBadge status={row.status} /></div>
    <div className="player-card__metrics"><span><small>Typical rank</small><strong>{rank(row.median)}</strong></span><span><small>80% rank band</small><strong>{rank(row.lower80)}–{rank(row.upper80)}</strong></span><span><small>Top 100</small><strong>{percent(row.top100)}</strong></span></div>
    <p>Overall 90% range <strong>{number(row.overallLower)}–{number(row.overallUpper)}</strong></p>
  </Link>;
}

export function LeaderboardTable({ entries, compact = false }: { entries: Top100Entry[] | LeaderboardEntry[]; compact?: boolean }) {
  const rows = entries.map((entry) => "median_rank" in entry ? fromTop100(entry) : fromLeaderboard(entry));
  return <>
    <div className="leaderboard-table-wrap" role="region" aria-label="Leaderboard table, scroll horizontally if needed" tabIndex={0}><table className="leaderboard-table"><thead><tr>
      <th scope="col">Display <InfoTip label="display position">Display position is a navigation summary, not a definitive ordering.</InfoTip></th>
      <th scope="col">Player</th>
      <th scope="col">Typical rank <InfoTip label="typical rank">The median of the player’s simulated rank distribution.</InfoTip></th>
      <th scope="col">80% rank band <InfoTip label="rank band">The player’s rank falls in this range in 80% of simulated outcomes, conditional on GOATLab’s frozen methodology.</InfoTip></th>
      {!compact && <th scope="col">Top 10</th>}
      <th scope="col">Top 100 <InfoTip label="Top 100 probability">The probability of membership in the Top 100, not a quality multiplier.</InfoTip></th>
      <th scope="col">Overall · 90% range</th><th scope="col">Evidence</th>
    </tr></thead><tbody>{rows.map((row) => <tr key={row.playerId}>
      <td className="display-number">#{row.position}</td>
      <td className="player-name"><Link prefetch={false} href={`/players/${encodeURIComponent(row.playerId)}`}>{row.name}<span className="row-arrow" aria-hidden="true">↗</span></Link><small>{row.active ? "Active · to date · " : ""}{membershipLabel(row.membership)}</small></td>
      <td className="metric-strong">{rank(row.median)}</td><td className="metric-band">{rank(row.lower80)}–{rank(row.upper80)}</td>
      {!compact && <td>{percent(row.top10)}</td>}<td className="metric-strong">{percent(row.top100)}</td>
      <td>{number(row.overallLower)}–{number(row.overallUpper)}</td><td><StatusBadge status={row.status} /></td>
    </tr>)}</tbody></table></div>
    <div className="leaderboard-cards">{rows.map((row) => <PlayerCard row={row} key={row.playerId} />)}</div>
  </>;
}
