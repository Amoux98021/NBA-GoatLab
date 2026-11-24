"use client";

import { CopyComparisonLink } from "./copy-comparison-link";
import { useEffect, useRef, useState } from "react";
import type { PlayerProfile } from "@/lib/types";
import { comparisonPath, DEFAULT_WEIGHTS, dimensionRange, displayWeightShares, encodeWeights, isDefault, normalizedWeights, scoreEvidence, parseWeights, rebalanceWeights, WEIGHT_DIMENSIONS, type Weights } from "@/lib/custom-weights";
import { dimensionDisplay, percent } from "@/lib/display";

export function CustomWeightComparison({ a, b, initialWeights = DEFAULT_WEIGHTS, invalidLink = false, defaultProbability }: {
  a: PlayerProfile; b: PlayerProfile; initialWeights?: Weights; invalidLink?: boolean; defaultProbability?: number;
}) {
  const [weights, setWeights] = useState<Weights>(initialWeights);
  const [invalid, setInvalid] = useState(invalidLink);
  const gesture = useRef<{ index: number; basis: Weights } | null>(null);
  useEffect(() => {
    const restore = () => {
      // The server initializes links; history traversal restores the exact same vector.
      const raw = new URL(window.location.href).searchParams.getAll("weights");
      const parsed = parseHistoryWeights(raw);
      gesture.current = null;
      setWeights(parsed.weights); setInvalid(parsed.invalid);
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  function update(next: Weights) {
    setWeights(next); setInvalid(false);
    const url = new URL(window.location.href);
    url.searchParams.set("weights", encodeWeights(next));
    window.history.replaceState(window.history.state, "", url);
  }
  function adjust(index: number, selected: number) {
    // Keep the other categories' baseline ratio during consecutive edits of this slider.
    // Basing each event on rounded thumbs would make the result depend on drag speed.
    if (gesture.current?.index !== index) gesture.current = { index, basis: weights };
    update(rebalanceWeights(gesture.current.basis, index, selected));
  }
  const normalized = normalizedWeights(weights);
  const shares = displayWeightShares(weights);
  const legacyShares = normalized && weights.reduce((sum, weight) => sum + weight, 0) !== 100;
  const left = scoreEvidence(a, weights), right = scoreEvidence(b, weights);
  const same = isDefault(weights);
  const changed = WEIGHT_DIMENSIONS.filter((_, i) => normalized && Math.abs(normalized[i] - DEFAULT_WEIGHTS[i] / 100) > 1e-12);
  const overlap = left.range && right.range && left.range.lower <= right.range.upper && right.range.lower <= left.range.upper;
  const showRange = (range: NonNullable<typeof left.range>) => `${range.lower.toFixed(2)}–${range.upper.toFixed(2)}`;
  return <section className="profile-section custom-weights" aria-labelledby="custom-weights-heading">
    <p className="eyebrow">EXPERIMENTAL · HEAD-TO-HEAD ONLY</p><h2 id="custom-weights-heading">Explore your own weights</h2>
    <p>Choose what matters to you. Set a category’s share of the 100% total. The other sliders move together so your shares always add up to 100% after an adjustment. Zero explicitly omits a category for both players.</p>
    <noscript><p>Enable JavaScript to adjust weights. The frozen default remains available below.</p></noscript>
    {invalid && <p role="alert">Invalid or unsupported shared weights. Showing the GOAT Lab default; no custom result was restored.</p>}
    {legacyShares && <p>Older shared link: sliders show rounded shares; the result below still uses the exact shared proportions until you adjust a slider.</p>}
    <fieldset><legend>Seven category weights</legend><div className="custom-weight-controls">{WEIGHT_DIMENSIONS.map((dimension, i) => <div className="custom-weight-control" key={dimension}>
      <label htmlFor={`weight-${dimension}`}>{dimension.charAt(0) + dimension.slice(1).toLowerCase()}</label>
      <input id={`weight-${dimension}`} type="range" min="0" max="100" step="1" value={shares[i]} aria-valuetext={`${shares[i]} percent`} aria-describedby={`weight-help-${dimension}`} onChange={(event) => adjust(i, Number(event.target.value))} />
      <output id={`weight-help-${dimension}`} htmlFor={`weight-${dimension}`}>{shares[i]}% <small>default {DEFAULT_WEIGHTS[i]}%</small></output>
    </div>)}</div></fieldset>
    <div className="comparison-toolbar"><button className="button button--outline" type="button" onClick={() => { gesture.current = null; update(DEFAULT_WEIGHTS); }}>Reset to GOAT Lab default</button><CopyComparisonLink /><a className="text-link" href={comparisonPath(b.identity.player_id, a.identity.player_id, weights)}>⇄ Swap with these weights</a></div>
    <div className="custom-result-grid">
      <article className="comparison-rank-card"><h3>Frozen GOAT Lab default</h3><p>Peak 17% · Longevity 14% · Offense 16% · Defense 14% · Playoffs 18% · Accolades 10% · Winning 11%</p><p>{defaultProbability === undefined ? "Default probability unavailable for this matchup." : `${a.identity.player_name} above ${b.identity.player_name}: ${percent(defaultProbability)} in frozen simulations.`}</p>{[a, b].map((profile) => profile.leaderboard && <p key={profile.identity.player_id}>{profile.identity.player_name}: diagnostic summary {profile.leaderboard.overall.center?.toFixed(2) ?? "unavailable"}; 90% Overall range {profile.leaderboard.overall.lower_90.toFixed(2)}–{profile.leaderboard.overall.upper_90.toFixed(2)}. A summary estimate is not an official exact point or a win probability.</p>)}<p>Default estimates, ranges, and comparison details below remain conditional on the frozen measurement architecture.</p></article>
      <article className="comparison-rank-card" aria-live="polite" aria-atomic="true"><h3>Custom conditional score evidence</h3>
        {!normalized ? <p role="alert">Positive total required. All seven weights are zero; custom results are disabled.</p> : <>
          {same && <p>Default-equivalent weights. The frozen default comparison beside this view is unchanged; this endpoint envelope is a different summary, not a reproduction of its Overall interval.</p>}
          {[{ player: a, result: left }, { player: b, result: right }].map(({ player, result }) => {
            return <p key={player.identity.player_id}><strong>{player.identity.player_name}: </strong>{result.range ? `${showRange(result.range)} / 100 · ${result.range.intervalOnly ? "includes interval-only evidence" : "published score evidence"}` : `Unavailable: ${result.missing.join(", ")}. Missing evidence is not zero; no weight is redistributed.`}</p>;
          })}
          {left.range && right.range && <p>{overlap ? "Too close to call from these score envelopes: they overlap." : "The published score envelopes are separated under these weights. This does not establish a confident winner."}</p>}
          <p>Custom win probability unavailable. Default probabilities are never reused for changed weights.</p>
        </>}
        <p>Envelope = sum of weighted published lower endpoints to sum of weighted upper endpoints; point-only categories are held fixed. The source ranges are marginal 90% ranges. Their weighted envelope has no joint coverage guarantee, and omits uncertainty not modeled in the source. It is not a calibrated Overall band or a probability.</p>
      </article>
    </div>
    <details open><summary>What changed, and what evidence supports it?</summary><p>{same ? "The normalized weights match the frozen default." : changed.length ? `Changed nominal shares: ${changed.map((name) => name.charAt(0) + name.slice(1).toLowerCase()).join(", ")}. Raising one share reduces the remaining shares.` : "Set at least one positive weight to compare."} Nominal weights express preferences. Effective influence also depends on correlations and player evidence; it is unavailable for custom distributions in this contract.</p>
      <ul className="custom-evidence-list">{WEIGHT_DIMENSIONS.map((dimension, i) => {
        const ra = dimensionRange(a.dimensions[dimension], i), rb = dimensionRange(b.dimensions[dimension], i);
        return <li key={dimension}><strong>{dimension.charAt(0) + dimension.slice(1).toLowerCase()}</strong> · {normalized ? `${(normalized[i] * 100).toFixed(1)}%` : "disabled"} (default {DEFAULT_WEIGHTS[i]}%){weights[i] === 0 ? " · explicitly omitted" : ""}<br />{a.identity.player_name}: {dimensionDisplay(a.dimensions[dimension])} · {a.dimensions[dimension].status} ({a.dimensions[dimension].confidence ?? "tiered uncertainty"}); {b.identity.player_name}: {dimensionDisplay(b.dimensions[dimension])} · {b.dimensions[dimension].status} ({b.dimensions[dimension].confidence ?? "tiered uncertainty"}). {ra && rb ? ra.lower > rb.upper ? "Published evidence favors the first player on this category’s scale." : rb.lower > ra.upper ? "Published evidence favors the second player on this category’s scale." : "Published ranges overlap or points tie; no category ordering established." : "Comparable category evidence unavailable."}</li>;
      })}</ul>
      <p>No precise per-category contribution is assigned to interval-only evidence. Stronger weighting does not validate how a category is measured. Winning measures team outcomes conditioned on participation, rather than individual postseason performance; the frozen participation rule has known audit limitations. Historical coverage differs, and a wider range is not lower quality.</p>
    </details>
    <small>Custom evidence contract goatlab-custom-score-envelope-v1 · release {a.release_id} · active careers through 2025–26, no projection. Copy share link preserves players and the exact integer weights.</small>
  </section>;
}

function parseHistoryWeights(values: string[]) { return parseWeights(values.length > 1 ? values : values[0]); }
