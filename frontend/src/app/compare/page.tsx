import type { Metadata } from "next";
import { ApiError, getPlayer } from "@/lib/api";
import { ComparisonSelector } from "@/components/comparison-selector";
import type { PlayerSearchResult } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Compare players",
  description: "Compare two NBA careers using GOATLab's frozen probabilistic evidence and uncertainty-aware rankings.",
};

export default async function CompareSelectorPage({ searchParams }: { searchParams: Promise<{ playerA?: string }> }) {
  const { playerA } = await searchParams;
  let initialA: PlayerSearchResult | null = null;
  let notice = "";
  if (typeof playerA === "string" && playerA.length > 0) {
    try {
      const profile = await getPlayer(playerA);
      initialA = {
        player_id: profile.identity.player_id,
        player_name: profile.identity.player_name,
        active: profile.identity.career_state === "ACTIVE",
        ranking_status: profile.identity.ranking_status,
        display_position: profile.leaderboard?.display_position ?? null,
      };
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) notice = "That player ID is not in this release. Search for a canonical player record below.";
      else throw error;
    }
  }
  return <div className="shell interior-page compare-selector-page"><header className="interior-header" data-reveal><p className="eyebrow">PLAYER VS PLAYER · UNCERTAINTY INCLUDED</p><h1>Compare two careers.</h1><p>Choose two canonical player records. GOATLab will show how often each ranks higher under its frozen probabilistic methodology—not an objective verdict.</p></header>
    {notice && <p className="compare-selector-page__notice" role="status">{notice}</p>}
    <ComparisonSelector initialA={initialA} />
    <div className="comparison-intro" data-reveal><div><span className="comparison-intro__number">01</span><h2>See the probability.</h2><p>The backend compares aligned Overall simulation draws and supplies the ordering label. This page never estimates the probability itself.</p></div><div><span className="comparison-intro__number">02</span><h2>Read the ranges.</h2><p>Rank bands, Overall intervals, and evidence statuses help explain where a close result remains uncertain.</p></div><div><span className="comparison-intro__number">03</span><h2>Share the matchup.</h2><p>Every pair receives a stable canonical-ID URL. Swapping players reverses the displayed direction through the backend.</p></div></div>
    <p className="comparison-foot">Search currently covers the 1,882 distribution-rankable careers. An unavailable player profile may still start a comparison to explain why no pairwise probability can be reported. Public publication remains subject to rights review.</p>
  </div>;
}
