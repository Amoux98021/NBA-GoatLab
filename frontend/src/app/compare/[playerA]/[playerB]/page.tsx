import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { ApiError, comparePlayers, getPlayer } from "@/lib/api";
import { ComparisonView } from "@/components/comparison-view";
import { reasonLabel } from "@/lib/display";
import type { PlayerProfile } from "@/lib/types";

export const dynamic = "force-dynamic";
type Props = { params: Promise<{ playerA: string; playerB: string }> };
const profile = cache(getPlayer);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { playerA, playerB } = await params;
  const [left, right] = await Promise.allSettled([profile(playerA), profile(playerB)]);
  if ((left.status === "rejected" && left.reason instanceof ApiError && left.reason.status === 404) || (right.status === "rejected" && right.reason instanceof ApiError && right.reason.status === 404)) notFound();
  if (left.status === "fulfilled" && right.status === "fulfilled") {
    return { title: `${left.value.identity.player_name} vs ${right.value.identity.player_name}`, description: `An uncertainty-aware GOATLab probabilistic comparison of ${left.value.identity.player_name} and ${right.value.identity.player_name}.` };
  }
  return { title: "Player comparison" };
}

function requireProfile(result: PromiseSettledResult<PlayerProfile>): PlayerProfile {
  if (result.status === "fulfilled") return result.value;
  if (result.reason instanceof ApiError && result.reason.status === 404) notFound();
  throw result.reason;
}

export default async function ComparisonPage({ params }: Props) {
  const { playerA, playerB } = await params;
  if (playerA === playerB) {
    const player = await profile(playerA).catch((error: unknown) => { if (error instanceof ApiError && error.status === 404) notFound(); throw error; });
    return <div className="shell interior-page empty-state"><p className="eyebrow">TWO PLAYERS REQUIRED</p><h1>Choose two different players.</h1><p>GOATLab does not compare a player against the same career.</p><Link className="button button--dark" href={`/compare?playerA=${encodeURIComponent(player.identity.player_id)}`}>Keep {player.identity.player_name} and choose another</Link></div>;
  }
  const [left, right, result] = await Promise.allSettled([profile(playerA), profile(playerB), comparePlayers(playerA, playerB)]);
  const a = requireProfile(left);
  const b = requireProfile(right);
  if (result.status === "fulfilled") return <ComparisonView a={a} b={b} comparison={result.value} />;
  const error: unknown = result.reason;
  if (error instanceof ApiError && error.status === 404) notFound();
  if (error instanceof ApiError && error.status === 422 && error.code === "COMPARISON_UNAVAILABLE") {
    const unavailable = [a, b].filter((player) => error.playerIds.includes(player.identity.player_id));
    return <div className="shell interior-page comparison-unavailable"><nav className="breadcrumb" aria-label="Breadcrumb"><Link href="/compare">Compare players</Link><span aria-hidden="true">/</span><span>Insufficient evidence</span></nav><p className="eyebrow">NO DEFENSIBLE PAIRWISE PROBABILITY</p><h1>{a.identity.player_name} vs {b.identity.player_name}</h1><p>GOATLab cannot produce a defensible pairwise probability for this matchup. {unavailable.map((player) => player.identity.player_name).join(" and ")} {unavailable.length === 1 ? "does" : "do"} not have a calibrated Overall distribution in this release.</p><p>Missing evidence is not a zero score, and no interval midpoint or alternate ranking is substituted.</p><div className="comparison-unavailable__players">{[a, b].map((player) => <article key={player.identity.player_id}><h2>{player.identity.player_name}</h2><p>Overall evidence: {player.identity.ranking_status.toLowerCase().replaceAll("_", " ")}</p>{player.reason_codes.length > 0 && <p>{reasonLabel(player.reason_codes[0])}</p>}<Link href={`/players/${encodeURIComponent(player.identity.player_id)}`}>View profile ↗</Link></article>)}</div><Link className="button button--dark" href={`/compare?playerA=${encodeURIComponent(a.identity.player_id)}`}>Change the matchup</Link></div>;
  }
  throw error;
}
