import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { ApiError, getPlayer } from "@/lib/api";
import { DIMENSIONS, DIMENSION_DESCRIPTIONS, rank, reasonLabel } from "@/lib/display";
import { DimensionCard, InfoTip, OverallRange, Probability, StatusBadge, UncertaintyInfo } from "@/components/primitives";

export const dynamic = "force-dynamic";
type Props = { params: Promise<{ playerId: string }> };
const profile = cache(getPlayer);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { playerId } = await params;
  try {
    const data = await profile(playerId);
    return { title: data.identity.player_name, description: `${data.identity.player_name}'s GOATLab probabilistic ranking profile and seven-dimension evidence.` };
  } catch {
    return { title: "Player profile" };
  }
}

export default async function PlayerPage({ params }: Props) {
  const { playerId } = await params;
  let data;
  try {
    data = await profile(playerId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const { identity, leaderboard, dimensions } = data;
  const career = `${identity.career_start_season ?? "?"}–${identity.career_end_season ?? (identity.career_state === "ACTIVE" ? "present" : "?")}`;
  return <div className="shell interior-page profile-page"><nav className="breadcrumb" aria-label="Breadcrumb"><Link href="/leaderboard">All players</Link><span aria-hidden="true">/</span><span>{identity.player_name}</span></nav>
    <header className="profile-hero"><div><p className="eyebrow">PLAYER PROFILE · {identity.cutoff_season} CUTOFF</p><h1>{identity.player_name}</h1><p className="profile-hero__sub">{career} · {identity.career_state === "ACTIVE" ? "Active · measured to date, no projection" : identity.career_state === "RETIRED" ? "Retired" : "Career status unknown"}</p><div className="profile-hero__actions"><StatusBadge status={identity.ranking_status} /><Link className="button button--light" href={`/compare?playerA=${encodeURIComponent(identity.player_id)}`}>Compare this player ↗</Link></div></div>
      {leaderboard ? <div className="profile-hero__rank"><span>DISPLAY POSITION <InfoTip label="display position">This navigational position is a summary of a rank distribution, not an exact scientific ordering.</InfoTip></span><strong>#{leaderboard.display_position}</strong><p>Typical rank {rank(leaderboard.rank.median_rank)}</p></div> : <div className="profile-hero__rank profile-hero__rank--empty"><span>RANKING STATUS</span><strong>Unavailable</strong><p>No calibrated Overall distribution</p></div>}
    </header>
    {leaderboard ? <>
      <UncertaintyInfo compact />
      <section className="profile-section"><div className="section-heading"><div><p className="eyebrow">DISTRIBUTION, NOT A VERDICT</p><h2>Where the evidence places this career</h2></div></div>
        <div className="ranking-grid"><div className="ranking-panel ranking-panel--main"><div className="ranking-panel__eyebrow">RANK DISTRIBUTION <InfoTip label="rank distribution">Rank bands are conditional on the frozen GOATLab methodology. Different historical evidence can yield different precision.</InfoTip></div><div className="large-rank">{rank(leaderboard.rank.median_rank)}<span>typical rank</span></div><div className="band-list"><div><span>50% rank band</span><strong>{rank(leaderboard.rank.lower_50)}–{rank(leaderboard.rank.upper_50)}</strong></div><div><span>80% rank band</span><strong>{rank(leaderboard.rank.lower_80)}–{rank(leaderboard.rank.upper_80)}</strong></div><div><span>90% rank band</span><strong>{rank(leaderboard.rank.lower_90)}–{rank(leaderboard.rank.upper_90)}</strong></div><div><span>95% rank band</span><strong>{rank(leaderboard.rank.lower_95)}–{rank(leaderboard.rank.upper_95)}</strong></div></div></div>
          <div className="ranking-panel"><div className="ranking-panel__eyebrow">TOP-N MEMBERSHIP CHANCE <InfoTip label="Top-N probability">The probability that this player belongs within the specified Top N under the frozen methodology; not a quality multiplier.</InfoTip></div><div className="probability-list"><Probability label="Top 1" value={leaderboard.top_n.top_1} bar /><Probability label="Top 5" value={leaderboard.top_n.top_5} bar /><Probability label="Top 10" value={leaderboard.top_n.top_10} bar /><Probability label="Top 25" value={leaderboard.top_n.top_25} bar /><Probability label="Top 50" value={leaderboard.top_n.top_50} bar /><Probability label="Top 100" value={leaderboard.top_n.top_100} bar /></div></div>
          <div className="ranking-panel ranking-panel--overall"><div className="ranking-panel__eyebrow">OVERALL MEASUREMENT <InfoTip label="Overall range">The 90% range represents uncertainty in the Overall measurement. A wider range is not a lower score.</InfoTip></div><OverallRange lower={leaderboard.overall.lower_90} upper={leaderboard.overall.upper_90} center={leaderboard.overall.center} status={leaderboard.ranking_status} /><p>{leaderboard.ranking_status === "INTERVAL_NATIVE" ? "The evidence supports an Overall range, not an exact point claim." : "A point summary is available, but the range remains essential context."}</p><small>Conditional on GOATLab’s frozen methodology · 2025–26 cutoff</small></div></div>
      </section>
    </> : <section className="unavailable-panel"><p className="eyebrow">INSUFFICIENT COMPARABLE EVIDENCE</p><h2>Ranking unavailable</h2><p>This player remains in GOATLab’s historical record, but there is no calibrated Overall distribution for a defensible cross-era comparison. Missing evidence is not a zero score.</p>{data.reason_codes.length > 0 && <details><summary>Evidence notes</summary><ul>{data.reason_codes.slice(0, 8).map((code) => <li key={code}>{reasonLabel(code)}</li>)}</ul></details>}</section>}
    <section className="profile-section"><div className="section-heading"><div><p className="eyebrow">THE SEVEN DIMENSIONS</p><h2>Performance, context & evidence</h2><p>Each dimension retains its own status. Ranges describe measurement uncertainty, not a discount on player quality.</p></div><Link className="text-link" href="/methodology">About these dimensions ↗</Link></div><div className="dimension-grid">{DIMENSIONS.map((dimension) => <DimensionCard key={dimension} value={dimensions[dimension]} description={DIMENSION_DESCRIPTIONS[dimension]} />)}</div></section>
    <div className="profile-foot"><p>All active careers stop at the {identity.cutoff_season} cutoff. No future seasons are projected.</p><Link href="/leaderboard">← Back to leaderboard</Link></div>
  </div>;
}
