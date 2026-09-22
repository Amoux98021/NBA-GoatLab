import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiError, getLeaderboard, getMethodology, getPlayer, validateTop100 } from "../src/lib/api";
import { dimensionDisplay, membershipLabel, percent, statusLabel } from "../src/lib/display";
import { LeaderboardTable } from "../src/components/leaderboard";
import { DimensionCard, Probability, UncertaintyInfo } from "../src/components/primitives";
import { ComparisonRankBands, RankDistributionGraphic } from "../src/components/data-visualization";
import type { DimensionProfile, RankSummary, Top100Entry } from "../src/lib/types";

const release = "goatlab-ranking-release-2026-v2-probabilistic";
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

function row(position: number): Top100Entry {
  return {
    active: false, cutoff_season: "2025-26", display_position: position,
    median_rank: position, overall_center: 90, overall_center_semantics: "DIAGNOSTIC_SUMMARY",
    overall_lower_90: 85, overall_upper_90: 94,
    player_id: `player_${position}`, player_name: `Player ${position}`,
    rank_lower_80: Math.max(1, position - 2), rank_upper_80: position + 2,
    rank_lower_90: Math.max(1, position - 4), rank_upper_90: position + 4,
    ranking_status: "INTERVAL_NATIVE", top100_membership: "TOP100_BUBBLE",
    top_10_probability: .1, top_25_probability: .3, top_50_probability: .5, top_100_probability: .75,
    release_id: release,
  };
}

function rankSummary(median: number, spread = 10): RankSummary {
  return {
    median_rank: median, mean_rank: median + .5,
    lower_50: median - 2, upper_50: median + 2,
    lower_80: median - 5, upper_80: median + 5,
    lower_90: median - 8, upper_90: median + 8,
    lower_95: median - spread, upper_95: median + spread,
  };
}

test("Top 100 accepts only 100 frozen-order records and does not reorder", () => {
  const entries = Array.from({ length: 100 }, (_, index) => row(index + 1));
  assert.deepEqual(validateTop100({ release_id: release, entries }), entries);
  assert.throws(() => validateTop100({ release_id: release, entries: entries.slice().reverse() }), ApiError);
  assert.throws(() => validateTop100({ release_id: release, entries: entries.slice(0, 99) }), ApiError);
  assert.throws(() => validateTop100({ release_id: "wrong", entries }), ApiError);
});

test("Top-100 table renders backend order, range, and interval status", () => {
  const html = renderToStaticMarkup(<LeaderboardTable entries={[row(1), row(2)]} compact />);
  assert.ok(html.indexOf("Player 1") < html.indexOf("Player 2"));
  assert.match(html, /85\.0–94\.0/);
  assert.match(html, /Interval-native/);
  assert.match(html, /80% rank band/);
  assert.match(html, /\/players\/player_1/);
});

test("interval-native dimension never displays a standalone diagnostic center or missing zero", () => {
  const dimension: DimensionProfile = {
    dimension: "LONGEVITY", status: "LONGEVITY_INTERVAL_ONLY", point_value: null,
    diagnostic_center: 90.5, lower_90: 86, upper_90: 95, methodology_version: "tiered",
    confidence: null, reason_codes: [], evidence_metadata: {},
  };
  assert.equal(dimensionDisplay(dimension), "86.0–95.0");
  assert.equal(dimensionDisplay({ ...dimension, status: "LONGEVITY_UNAVAILABLE", diagnostic_center: null, lower_90: null, upper_90: null }), "Insufficient evidence");
  const interval = renderToStaticMarkup(<DimensionCard value={dimension} description="Duration near the top." />);
  assert.doesNotMatch(interval, /90\.5/);
  assert.doesNotMatch(interval, /data-point-value/);
  assert.match(interval, /86\.0–95\.0/);
  assert.match(interval, /no exact point claim/i);
  const missing = renderToStaticMarkup(<DimensionCard value={{ ...dimension, status: "INSUFFICIENT_SAMPLE", point_value: null, diagnostic_center: null, lower_90: null, upper_90: null }} description="Postseason evidence." />);
  assert.doesNotMatch(missing, /\/ 100/);
  assert.doesNotMatch(missing, /dimension-scale__track/);
  assert.doesNotMatch(missing, /data-point-value/);
  assert.match(missing, /no score rendered/);
  assert.equal(percent(.9972), "99.72%");
});

test("rank interval graphic preserves every supplied endpoint on a documented local scale", () => {
  const summary = rankSummary(25, 13);
  const html = renderToStaticMarkup(<RankDistributionGraphic summary={summary} />);
  assert.match(html, /data-scale-start="12"/);
  assert.match(html, /data-scale-end="38"/);
  for (const endpoint of [23, 27, 20, 30, 17, 33, 12, 38]) assert.match(html, new RegExp(`#${endpoint}`));
  assert.match(html, /Median #25/);
  assert.match(html, /not a probability density plot/);
});

test("comparison rank bands use one combined scale for both players", () => {
  const html = renderToStaticMarkup(<ComparisonRankBands playerA="Player A" playerB="Player B" summaryA={rankSummary(20, 10)} summaryB={rankSummary(45, 15)} />);
  assert.equal((html.match(/data-scale-start="10"/g) ?? []).length, 3);
  assert.equal((html.match(/data-scale-end="60"/g) ?? []).length, 3);
  assert.match(html, /Both careers use the same local scale/);
});

test("search and filters are sent to the API, not applied to ranking outputs", async () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  let requested = "";
  globalThis.fetch = async (input) => {
    requested = String(input);
    return Response.json({ release_id: release, total: 0, limit: 50, offset: 0, entries: [] });
  };
  const result = await getLeaderboard({ search: "  Curry  ", active: true, status: "INTERVAL_NATIVE" });
  assert.equal(result.total, 0);
  assert.match(requested, /search=\+\+Curry\+\+/);
  assert.match(requested, /active=true/);
  assert.match(requested, /status=INTERVAL_NATIVE/);
  assert.match(requested, /release=goatlab-ranking-release-2026-v2-probabilistic/);
});

test("malformed profile is rejected instead of inventing dimension evidence", async () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  globalThis.fetch = async () => Response.json({ release_id: release, identity: { player_id: "p", ranking_eligible: false }, dimensions: {} });
  await assert.rejects(() => getPlayer("p"), ApiError);
});

test("status and Top-100 labels retain frozen neutral semantics", () => {
  assert.equal(statusLabel("OFFICIAL"), "Official");
  assert.equal(statusLabel("PROVISIONAL"), "Provisional");
  assert.equal(statusLabel("INTERVAL_NATIVE"), "Interval-native");
  assert.equal(statusLabel("UNAVAILABLE"), "Unavailable");
  assert.equal(membershipLabel("TOP100_BUBBLE"), "Top-100 bubble");
  assert.equal(membershipLabel("ROBUST_OUTSIDE_TOP100"), "Robustly outside");
});

test("methodology disclosure is API-owned and uncertainty copy is visible", async () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  globalThis.fetch = async () => Response.json({
    release_id: release, disclosures: { display_rank: "Display positions summarize uncertainty." },
    dimension_methodology_versions: {},
  });
  const methodology = await getMethodology();
  assert.equal(methodology.disclosures.display_rank, "Display positions summarize uncertainty.");
  const html = renderToStaticMarkup(<UncertaintyInfo />);
  assert.match(html, /Wider uncertainty does not mean lower player quality/);
  assert.match(html, /nearby players may not be definitively ordered/);
});

test("probability motion preserves the exact provided value in server markup", () => {
  const html = renderToStaticMarkup(<Probability label="Top 25" value={0.372} bar />);
  assert.match(html, /37\.2%/);
  assert.match(html, /width:37\.2%/);
  assert.match(html, /data-probability-bar="true"/);
  assert.match(html, /probability__fill/);
});

test("motion is local, reduced-motion aware, and introduces no request path", () => {
  const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");
  const enhancer = readFileSync(new URL("../src/components/motion.tsx", import.meta.url), "utf8");
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/);
  assert.match(enhancer, /IntersectionObserver/);
  assert.doesNotMatch(enhancer, /fetch\s*\(/);
  const visualizations = readFileSync(new URL("../src/components/data-visualization.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(visualizations, /fetch\s*\(/);
});
