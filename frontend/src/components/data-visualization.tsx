import type { CSSProperties } from "react";
import { number, rank } from "@/lib/display";
import type { DimensionProfile, RankSummary } from "@/lib/types";

type RankBandLevel = 50 | 80 | 90 | 95;

const rankBandLevels: RankBandLevel[] = [95, 90, 80, 50];

function rankBand(rankSummary: RankSummary, level: RankBandLevel): [number, number] {
  return [rankSummary[`lower_${level}`], rankSummary[`upper_${level}`]];
}

function extent(rankSummaries: RankSummary[]): [number, number] {
  let start = Number.POSITIVE_INFINITY;
  let end = Number.NEGATIVE_INFINITY;
  for (const summary of rankSummaries) {
    start = Math.min(start, summary.lower_95, summary.median_rank);
    end = Math.max(end, summary.upper_95, summary.median_rank);
  }
  if (start === end) return [Math.max(1, Math.floor(start) - 1), Math.ceil(end) + 1];
  return [start, end];
}

function position(value: number, start: number, end: number): number {
  return Math.max(0, Math.min(100, ((value - start) / (end - start)) * 100));
}

function rangeStyle(lower: number, upper: number, start: number, end: number): CSSProperties {
  const left = position(lower, start, end);
  return { left: `${left}%`, width: `${Math.max(0, position(upper, start, end) - left)}%` };
}

function markerStyle(value: number, start: number, end: number): CSSProperties {
  return { left: `${position(value, start, end)}%` };
}

function scorePosition(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function scoreRangeStyle(lower: number, upper: number): CSSProperties {
  const left = scorePosition(lower);
  return { left: `${left}%`, width: `${Math.max(0, scorePosition(upper) - left)}%` };
}

function RankBandRows({ summary, start, end, side }: { summary: RankSummary; start: number; end: number; side?: "A" | "B" }) {
  return <div className="rank-interval-rows" data-side={side}>
    {rankBandLevels.map((level) => {
      const [lower, upper] = rankBand(summary, level);
      return <div className="rank-interval-row" key={level}>
        <span className="rank-interval-row__level">{level}%</span>
        <span className="rank-interval-row__endpoint">#{rank(lower)}</span>
        <span className="interval-track" aria-hidden="true">
          <span className={`interval-segment interval-segment--${level}`} data-interval-reveal style={rangeStyle(lower, upper, start, end)} />
          <span className="interval-marker" style={markerStyle(summary.median_rank, start, end)} />
        </span>
        <span className="rank-interval-row__endpoint rank-interval-row__endpoint--end">#{rank(upper)}</span>
      </div>;
    })}
  </div>;
}

export function RankDistributionGraphic({ summary }: { summary: RankSummary }) {
  const [start, end] = extent([summary]);
  const label = `Typical rank ${rank(summary.median_rank)}. 50 percent band ${rank(summary.lower_50)} to ${rank(summary.upper_50)}; 80 percent band ${rank(summary.lower_80)} to ${rank(summary.upper_80)}; 90 percent band ${rank(summary.lower_90)} to ${rank(summary.upper_90)}; 95 percent band ${rank(summary.lower_95)} to ${rank(summary.upper_95)}.`;
  return <figure className="rank-interval-graphic" aria-label={label} data-scale-start={start} data-scale-end={end}>
    <div className="rank-interval-graphic__head"><span>Local interval view</span><strong>Median #{rank(summary.median_rank)}</strong></div>
    <div className="rank-axis" aria-hidden="true"><span>#{rank(start)} · better</span><span>#{rank(end)}</span></div>
    <RankBandRows summary={summary} start={start} end={end} />
    <figcaption>Nested rank intervals on this player’s displayed 95% extent—not a probability density plot.</figcaption>
  </figure>;
}

export function ComparisonRankBands({ playerA, playerB, summaryA, summaryB }: { playerA: string; playerB: string; summaryA: RankSummary; summaryB: RankSummary }) {
  const [start, end] = extent([summaryA, summaryB]);
  const players: Array<[string, RankSummary, "A" | "B"]> = [[playerA, summaryA, "A"], [playerB, summaryB, "B"]];
  return <figure className="comparison-rank-bands" aria-labelledby="comparison-rank-bands-title" data-scale-start={start} data-scale-end={end}>
    <div className="comparison-rank-bands__head"><div><p className="eyebrow">SHARED RANK SCALE</p><h3 id="comparison-rank-bands-title">How much the rank intervals overlap</h3></div><span>Lower rank is better</span></div>
    <div className="rank-axis" aria-hidden="true"><span>#{rank(start)} · better</span><span>#{rank(end)}</span></div>
    {players.map(([player, summary, side]) => {
      return <section className="comparison-rank-bands__player" key={player} data-player-side={side} data-scale-start={start} data-scale-end={end} aria-label={`${player}: median rank ${rank(summary.median_rank)}`}>
        <div><strong>{player}</strong><span>Median #{rank(summary.median_rank)}</span></div>
        <RankBandRows summary={summary} start={start} end={end} side={side} />
      </section>;
    })}
    <figcaption>Both careers use the same local scale from their combined visible 95% interval extent. Bands show supplied intervals, not fitted densities.</figcaption>
  </figure>;
}

function dimensionState(value: DimensionProfile) {
  const interval = value.lower_90 !== null && value.upper_90 !== null;
  const unavailable = value.point_value === null && !interval;
  return { interval, unavailable };
}

export function DimensionScaleGraphic({ value, label }: { value: DimensionProfile; label?: string }) {
  const { interval, unavailable } = dimensionState(value);
  if (unavailable) {
    return <div className="dimension-scale dimension-scale--unavailable" data-dimension-unavailable aria-label={`${label ?? value.dimension}: insufficient evidence. No zero value is shown.`}><span>Insufficient evidence · no score rendered</span></div>;
  }
  const accessible = value.point_value !== null
    ? `${label ?? value.dimension}: point ${number(value.point_value)}${interval ? ` with 90 percent interval ${number(value.lower_90!)} to ${number(value.upper_90!)}` : ""} on a zero to 100 scale.`
    : `${label ?? value.dimension}: 90 percent interval ${number(value.lower_90!)} to ${number(value.upper_90!)} on a zero to 100 scale. No exact point claim.`;
  return <div className="dimension-scale" role="img" aria-label={accessible} data-scale-start="0" data-scale-end="100">
    <div className="dimension-scale__axis" aria-hidden="true"><span>0</span><span>100</span></div>
    <div className="dimension-scale__track" aria-hidden="true">
      {interval && <span className="dimension-scale__interval interval-segment" data-interval-reveal style={scoreRangeStyle(value.lower_90!, value.upper_90!)} />}
      {value.point_value !== null && <span className="dimension-scale__point" data-point-value={value.point_value} style={{ left: `${scorePosition(value.point_value)}%` }} />}
    </div>
  </div>;
}

function ComparisonDimensionLane({ name, value, side }: { name: string; value: DimensionProfile; side: "A" | "B" }) {
  const { interval, unavailable } = dimensionState(value);
  return <div className="comparison-dimension-lane" data-side={side}>
    <span className="comparison-dimension-lane__label">{name}</span>
    {unavailable ? <span className="comparison-dimension-lane__unavailable">Unavailable</span> : <span className="comparison-dimension-lane__track" aria-hidden="true">
      {interval && <span className="dimension-scale__interval interval-segment" data-interval-reveal style={scoreRangeStyle(value.lower_90!, value.upper_90!)} />}
      {value.point_value !== null && <span className="dimension-scale__point" data-point-value={value.point_value} style={{ left: `${scorePosition(value.point_value)}%` }} />}
    </span>}
  </div>;
}

export function ComparisonDimensionGraphic({ playerA, playerB, valueA, valueB }: { playerA: string; playerB: string; valueA: DimensionProfile; valueB: DimensionProfile }) {
  return <div className="comparison-dimension-graphic" role="img" aria-label={`${valueA.dimension} comparison on a shared zero to 100 scale. ${playerA}: ${valueA.point_value !== null ? number(valueA.point_value) : valueA.lower_90 !== null && valueA.upper_90 !== null ? `${number(valueA.lower_90)} to ${number(valueA.upper_90)}, no exact point claim` : "unavailable"}. ${playerB}: ${valueB.point_value !== null ? number(valueB.point_value) : valueB.lower_90 !== null && valueB.upper_90 !== null ? `${number(valueB.lower_90)} to ${number(valueB.upper_90)}, no exact point claim` : "unavailable"}.`} data-scale-start="0" data-scale-end="100">
    <div className="comparison-dimension-graphic__axis" aria-hidden="true"><span>0</span><span>Shared dimension scale</span><span>100</span></div>
    <ComparisonDimensionLane name={playerA} value={valueA} side="A" />
    <ComparisonDimensionLane name={playerB} value={valueB} side="B" />
  </div>;
}

const methodologySteps = [
  "7 dimensions",
  "Overall measurement distribution",
  "Aligned simulation draws",
  "Rank distribution",
  "Top-N membership / pairwise probability",
];

export function MethodologyProcessGraphic() {
  return <figure className="methodology-process" aria-labelledby="methodology-process-title">
    <h3 id="methodology-process-title">From evidence to probabilistic comparison</h3>
    <ol>{methodologySteps.map((step) => <li key={step}><span>{step}</span></li>)}</ol>
    <figcaption>Aligned draws retain modeled dependence. This is a measurement pipeline, not a claim of deterministic rank or causal independence.</figcaption>
  </figure>;
}
