import Link from "next/link";
import { ComparisonSelector } from "./comparison-selector";
import { CopyComparisonLink } from "./copy-comparison-link";
import { OverallRange, Probability, StatusBadge } from "./primitives";
import { DIMENSIONS, dimensionDisplay, percent, rank, reasonLabel } from "@/lib/display";
import type { PairwiseOrder, PairwiseResponse, PlayerProfile, PlayerSearchResult } from "@/lib/types";

function choice(profile: PlayerProfile): PlayerSearchResult {
  return {
    player_id: profile.identity.player_id,
    player_name: profile.identity.player_name,
    active: profile.identity.career_state === "ACTIVE",
    ranking_status: profile.identity.ranking_status,
    display_position: profile.leaderboard?.display_position ?? null,
  };
}

export function orderingCopy(order: PairwiseOrder, a: string, b: string, probabilityA: number, probabilityB: number) {
  switch (order) {
    case "STRONG_A_OVER_B": return { heading: `Strong ordering evidence for ${a}`, detail: `GOATLab places ${a} above ${b} in ${percent(probabilityA)} of simulated outcomes.` };
    case "LEAN_A_OVER_B": return { heading: `GOATLab leans ${a}`, detail: `${a} ranks above ${b} in ${percent(probabilityA)} of simulated outcomes. This is a lean, not a definitive ordering.` };
    case "STRONG_B_OVER_A": return { heading: `Strong ordering evidence for ${b}`, detail: `GOATLab places ${b} above ${a} in ${percent(probabilityB)} of simulated outcomes.` };
    case "LEAN_B_OVER_A": return { heading: `GOATLab leans ${b}`, detail: `${b} ranks above ${a} in ${percent(probabilityB)} of simulated outcomes. This is a lean, not a definitive ordering.` };
    case "INDETERMINATE": return { heading: "Too close to separate confidently", detail: `GOATLab places ${a} above ${b} in ${percent(probabilityA)} of simulations and ${b} above ${a} in ${percent(probabilityB)}. Neither ordering has strong support.` };
  }
}

function PlayerSummary({ profile, side }: { profile: PlayerProfile; side: "A" | "B" }) {
  const entry = profile.leaderboard;
  if (!entry) return null;
  return <article className="comparison-player"><div className="comparison-player__top"><span>PLAYER {side}</span><StatusBadge status={entry.ranking_status} /></div>
    <h2><Link href={`/players/${encodeURIComponent(profile.identity.player_id)}`}>{profile.identity.player_name} ↗</Link></h2>
    <p>{profile.identity.career_state === "ACTIVE" ? "Active · measured to date" : "Retired"} · display position #{entry.display_position}</p>
    <div className="comparison-player__rank"><strong>{rank(entry.rank.median_rank)}</strong><span>typical rank · 80% band {rank(entry.rank.lower_80)}–{rank(entry.rank.upper_80)}</span></div>
    <OverallRange lower={entry.overall.lower_90} upper={entry.overall.upper_90} center={entry.overall.center} status={entry.ranking_status} />
  </article>;
}

function DimensionValue({ profile, dimension }: { profile: PlayerProfile; dimension: typeof DIMENSIONS[number] }) {
  const value = profile.dimensions[dimension];
  return <span className="comparison-dimension__value"><strong>{dimensionDisplay(value)}</strong><StatusBadge status={value.status} /></span>;
}

export function ComparisonView({ a, b, comparison }: { a: PlayerProfile; b: PlayerProfile; comparison: PairwiseResponse }) {
  const first = a.leaderboard;
  const second = b.leaderboard;
  if (!first || !second) throw new Error("A publishable comparison requires two rankable profiles.");
  const copy = orderingCopy(comparison.ordering_label, a.identity.player_name, b.identity.player_name, comparison.probability_a_above_b, comparison.probability_b_above_a);
  const rankBandsOverlap = first.rank.lower_90 <= second.rank.upper_90 && second.rank.lower_90 <= first.rank.upper_90;
  const crossEra = (
    a.identity.career_end_season !== null &&
    b.identity.career_start_season !== null &&
    a.identity.career_end_season < b.identity.career_start_season
  ) || (
    b.identity.career_end_season !== null &&
    a.identity.career_start_season !== null &&
    b.identity.career_end_season < a.identity.career_start_season
  );
  const factualPointHigherA: string[] = [];
  const factualPointHigherB: string[] = [];
  for (const dimension of DIMENSIONS) {
    const left = comparison.dimensions[dimension].player_a.point_value;
    const right = comparison.dimensions[dimension].player_b.point_value;
    if (left !== null && right !== null && left !== right) {
      (left > right ? factualPointHigherA : factualPointHigherB).push(dimension.charAt(0) + dimension.slice(1).toLowerCase());
    }
  }
  return <div className="shell interior-page comparison-page">
    <nav className="breadcrumb" aria-label="Breadcrumb"><Link href="/compare">Compare players</Link><span aria-hidden="true">/</span><span>{a.identity.player_name} vs {b.identity.player_name}</span></nav>
    <header className="interior-header"><p className="eyebrow">A COMPARISON, WITH UNCERTAINTY</p><h1>{a.identity.player_name} <span className="comparison-vs">vs</span> {b.identity.player_name}</h1><p>A probability under GOATLab’s frozen methodology—not a verdict on who is objectively better.</p></header>
    <div className="comparison-toolbar"><Link className="button button--outline" href={`/compare/${encodeURIComponent(b.identity.player_id)}/${encodeURIComponent(a.identity.player_id)}`}>⇄ Swap players</Link><CopyComparisonLink /><Link className="text-link" href="/methodology">How comparisons work ↗</Link></div>
    <div className="comparison-hero"><PlayerSummary profile={a} side="A" /><section className="comparison-verdict" aria-label="Overall pairwise probability"><p className="eyebrow">PROBABILITY OF RANKING HIGHER</p><h2>{copy.heading}</h2><p>{copy.detail}</p><div className="probability-split" role="img" aria-label={`${a.identity.player_name} ${percent(comparison.probability_a_above_b)} probability of ranking higher; ${b.identity.player_name} ${percent(comparison.probability_b_above_a)}`}><span style={{ width: `${comparison.probability_a_above_b * 100}%` }} /><span style={{ width: `${comparison.probability_b_above_a * 100}%` }} /></div><div className="probability-split__labels"><span>{a.identity.player_name}<strong>{percent(comparison.probability_a_above_b)}</strong></span><span>{b.identity.player_name}<strong>{percent(comparison.probability_b_above_a)}</strong></span></div><small>Close comparisons can remain indeterminate. Exact draw ties are shared symmetrically.</small></section><PlayerSummary profile={b} side="B" /></div>
    <div className="comparison-note"><strong>{rankBandsOverlap ? "Their 90% rank bands overlap." : "Their 90% rank bands do not overlap."}</strong><span>{comparison.overall_90_ranges_overlap ? "Their 90% Overall ranges overlap." : "Their 90% Overall ranges do not overlap."}</span><span>Median rank is a summary position; it is not proof of an exact ordering.</span>{crossEra && <span>These careers span different eras. GOATLab’s era-relative evidence has unequal historical precision.</span>}</div>
    <section className="profile-section"><div className="section-heading"><div><p className="eyebrow">THE RANK DISTRIBUTIONS</p><h2>Placement is a range.</h2><p>Top-N chances and rank bands come from the frozen release, not from the comparison display.</p></div></div><div className="comparison-rank-grid">{[a, b].map((profile) => { const entry = profile.leaderboard!; return <article key={profile.identity.player_id} className="comparison-rank-card"><h3>{profile.identity.player_name}</h3><dl><div><dt>Median rank</dt><dd>{rank(entry.rank.median_rank)}</dd></div><div><dt>80% rank band</dt><dd>{rank(entry.rank.lower_80)}–{rank(entry.rank.upper_80)}</dd></div><div><dt>90% rank band</dt><dd>{rank(entry.rank.lower_90)}–{rank(entry.rank.upper_90)}</dd></div></dl><div className="comparison-rank-card__probabilities"><Probability label="Top 10" value={entry.top_n.top_10} /><Probability label="Top 25" value={entry.top_n.top_25} /><Probability label="Top 50" value={entry.top_n.top_50} /><Probability label="Top 100" value={entry.top_n.top_100} /></div></article>; })}</div></section>
    <section className="profile-section"><div className="section-heading"><div><p className="eyebrow">THE SEVEN FROZEN DIMENSIONS</p><h2>Where the summaries differ.</h2><p>Point values and 90% ranges retain their evidence status. These are not per-dimension head-to-head probabilities.</p></div></div><div className="comparison-dimension-table" role="table" aria-label="Seven-dimension player comparison"><div className="comparison-dimension-table__head" role="row"><span role="columnheader">{a.identity.player_name}</span><span role="columnheader">Dimension</span><span role="columnheader">{b.identity.player_name}</span></div>{DIMENSIONS.map((dimension) => { const pair = comparison.dimensions[dimension]; const rangeA = pair.player_a.lower_90 !== null && pair.player_a.upper_90 !== null; const rangeB = pair.player_b.lower_90 !== null && pair.player_b.upper_90 !== null; const overlap = rangeA && rangeB && pair.player_a.lower_90! <= pair.player_b.upper_90! && pair.player_b.lower_90! <= pair.player_a.upper_90!; return <div className="comparison-dimension-row" role="row" key={dimension}><span role="cell" data-player={a.identity.player_name}><DimensionValue profile={a} dimension={dimension} /></span><span className="comparison-dimension-row__name" role="rowheader">{dimension.charAt(0) + dimension.slice(1).toLowerCase()}<small>{rangeA && rangeB ? overlap ? "90% ranges overlap" : "90% ranges do not overlap" : "Evidence precision differs"}</small></span><span role="cell" data-player={b.identity.player_name}><DimensionValue profile={b} dimension={dimension} /></span></div>; })}</div></section>
    <section className="comparison-interpretation"><div><p className="eyebrow">WHAT THE EVIDENCE DOES—AND DOESN’T—SAY</p><h2>Why does GOATLab lean this way?</h2><p>The pairwise probability comes from aligned Overall simulation draws across all seven dimensions. It is not a direct sum of the displayed point differences.</p>{factualPointHigherA.length > 0 && <p>Among dimensions with point summaries for both players, {a.identity.player_name} has a higher displayed point in {factualPointHigherA.join(", ")}.</p>}{factualPointHigherB.length > 0 && <p>{b.identity.player_name} has a higher displayed point in {factualPointHigherB.join(", ")}.</p>}<p>Interval-native dimensions are shown as ranges. GOATLab does not assign a precise numerical contribution or causal “driver” where that would imply unsupported precision.</p></div><div><h3>Measurement context</h3><p>Pairwise probability reflects modeled measurement uncertainty. Historical evidence differs across eras, so close comparisons may remain uncertain even when central summaries differ. Wider uncertainty does not mean a player is worse.</p><p>All probabilities are conditional on the frozen measurement architecture; shared cross-player calibration-model uncertainty is not fully represented.</p></div></section>
    <section className="profile-section"><div className="section-heading"><div><p className="eyebrow">EVIDENCE STATUS</p><h2>What supports each side?</h2></div></div><div className="comparison-evidence-grid">{[a, b].map((profile) => <article key={profile.identity.player_id}><h3>{profile.identity.player_name}</h3><dl>{["Overall", "Peak", "Longevity", "Defense"].map((name) => <div key={name}><dt>{name}</dt><dd><StatusBadge status={name === "Overall" ? profile.identity.ranking_status : profile.dimensions[name.toUpperCase() as "PEAK" | "LONGEVITY" | "DEFENSE"].status} /></dd></div>)}</dl>{profile.reason_codes.length > 0 && <p>Evidence note: {reasonLabel(profile.reason_codes[0])}</p>}</article>)}</div></section>
    <details className="comparison-change"><summary>Change either player</summary><ComparisonSelector initialA={choice(a)} initialB={choice(b)} /></details>
    <p className="comparison-foot">Release {comparison.release_id} · {comparison.ranking_policy_version} · active careers measured through 2025–26, no projection. <Link href="/methodology">Read the methodology ↗</Link></p>
  </div>;
}
