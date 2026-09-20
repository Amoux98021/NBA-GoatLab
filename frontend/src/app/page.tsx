import Link from "next/link";
import { getLeaderboard, getTop100 } from "@/lib/api";
import { percent } from "@/lib/display";
import { LeaderboardTable } from "@/components/leaderboard";
import { UncertaintyInfo } from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [entries, boundary] = await Promise.all([getTop100(), getLeaderboard({ limit: 12, offset: 94 })]);
  return <>
    <section className="hero"><div className="shell hero__inner"><div className="hero__eyebrow"><span className="live-dot" /> THE 2026 PROBABILISTIC RELEASE <span className="hero__line" /> 1,882 RANKABLE CAREERS</div><h1>The NBA GOAT debate,<br /><em>modeled.</em></h1><div className="hero__bottom"><p>Seven dimensions. One explicit set of assumptions. A ranking that shows what the evidence supports—and where it doesn’t.</p><div className="hero__actions"><a className="button button--light" href="#top100">Explore Top 100 <span aria-hidden="true">↘</span></a><Link className="button button--ghost" href="/methodology">Read the methodology ↗</Link></div></div></div></section>
    <section id="top100" className="shell content-section"><div className="section-heading"><div><p className="eyebrow">THE LIST · 2025–26 CUTOFF</p><h2>Top 100 <span>probabilistic leaderboard</span></h2><p>One hundred display slots, ordered for navigation. The rank bands and probabilities tell the fuller story.</p></div><Link className="text-link" href="/leaderboard">Explore all 1,882 players ↗</Link></div>
      <UncertaintyInfo compact /><LeaderboardTable entries={entries} compact />
      <div className="boundary"><div><p className="eyebrow">THE CUTOFF ISN’T A CLIFF</p><h3>Around the Top-100 line</h3><p>Players near the display boundary can have overlapping rank distributions. These neighboring positions are not a separate Top-100 list.</p></div><div className="boundary__players">{boundary.entries.filter((entry) => entry.display_position >= 98 && entry.display_position <= 105).map((entry) => <Link key={entry.player_id} href={`/players/${encodeURIComponent(entry.player_id)}`}><span>#{entry.display_position}</span><strong>{entry.player_name}</strong><small>{percent(entry.top_n.top_100)} Top-100 chance</small></Link>)}</div></div>
    </section>
  </>;
}
