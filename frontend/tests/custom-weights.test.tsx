import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { CustomWeightComparison } from "../src/components/custom-weight-comparison";
import { comparisonPath, DEFAULT_WEIGHTS, dimensionRange, displayWeightShares, encodeWeights, isDefault, normalizedWeights, parseWeights, rebalanceWeights, scoreEvidence, WEIGHT_DIMENSIONS } from "../src/lib/custom-weights";
import type { DimensionProfile, PlayerProfile } from "../src/lib/types";

function fixture(): PlayerProfile {
  const versions = ["goatlab-v1-peak-v2", "goatlab-v1-longevity-v2-tiered", "goatlab-v1-dimension-scores-v1", "goatlab-v1-defense-v2-tiered", "goatlab-v1-dimension-scores-v1", "goatlab-v1-dimension-scores-v1", "goatlab-v1-dimension-scores-v1"];
  return { release_id: "goatlab-ranking-release-2026-v2-probabilistic", identity: { player_id: "a", player_name: "Player A", career_state: "RETIRED", career_start_season: 1980, career_end_season: 1990, latest_season_used: 1990, cutoff_season: "2025-26", ranking_status: "INTERVAL_NATIVE", ranking_eligible: true }, leaderboard: null, reason_codes: [], methodology_versions: {}, active_career_policy: "TO_DATE_NO_PROJECTION", uncertainty_is_quality_penalty: false,
    dimensions: Object.fromEntries(WEIGHT_DIMENSIONS.map((dimension, i) => [dimension, { dimension, methodology_version: versions[i], status: i === 0 ? "PROVISIONAL_PEAK_POINT" : i === 1 ? "OFFICIAL_LONGEVITY_POINT" : i === 3 ? "OFFICIAL_DEFENSE_POINT" : "AVAILABLE", point_value: 60 + i, diagnostic_center: 999, lower_90: null, upper_90: null, confidence: "STRONG", reason_codes: [], evidence_metadata: {} }])) as unknown as Record<DimensionProfile["dimension"], DimensionProfile> };
}

test("default-equivalence compares normalized weights and never reconstructs official Overall", () => {
  assert.equal(isDefault(DEFAULT_WEIGHTS), true);
  assert.equal(isDefault(DEFAULT_WEIGHTS.map((n) => n * 2)), true);
  assert.equal(isDefault([0,0,100,0,0,0,0]), false);
  const a = fixture(), b = fixture(); b.identity.player_id = "b";
  const html = renderToStaticMarkup(<CustomWeightComparison a={a} b={b} defaultProbability={0.72} />);
  assert.match(html, /72.0% in frozen simulations/);
  assert.match(html, /Default-equivalent weights/);
  assert.match(html, /not a reproduction of its Overall interval/);
  assert.doesNotMatch(html, /999/);
});
test("every 100% category uses only its versioned point or interval evidence", () => {
  const p = fixture();
  WEIGHT_DIMENSIONS.forEach((dimension, i) => {
    const weights = WEIGHT_DIMENSIONS.map((_, j) => i === j ? 100 : 0);
    const range = scoreEvidence(p, weights).range!;
    assert.equal(range.lower, 60 + i); assert.equal(range.upper, 60 + i);
    if (![0,1,3].includes(i)) return;
    p.dimensions[dimension] = { ...p.dimensions[dimension], point_value: null, status: i === 0 ? "PEAK_INTERVAL_ONLY" : i === 1 ? "LONGEVITY_INTERVAL_ONLY" : "DEFENSE_INTERVAL_ONLY", lower_90: 20, upper_90: 80 };
    assert.deepEqual(scoreEvidence(p, weights).range, { lower: 20, upper: 80, intervalOnly: true });
  });
});
test("all-zero and invalid totals disable; unavailable evidence is omitted only at explicit zero", () => {
  const p = fixture(); p.dimensions.PEAK = { ...p.dimensions.PEAK, status: "PEAK_UNAVAILABLE", point_value: null };
  assert.equal(scoreEvidence(p, DEFAULT_WEIGHTS).range, null);
  assert.deepEqual(scoreEvidence(p, DEFAULT_WEIGHTS).missing, ["PEAK"]);
  assert.equal(scoreEvidence(p, [0,0,100,0,0,0,0]).range!.lower, 62);
  for (const weights of [[0,0,0,0,0,0,0], [-1,0,0,0,0,0,0], [NaN], [Infinity], [0.5,1,2,3,4,5,6]]) assert.equal(normalizedWeights(weights), null);
  const html = renderToStaticMarkup(<CustomWeightComparison a={p} b={fixture()} initialWeights={[0,0,0,0,0,0,0]} />);
  assert.match(html, /Default probability unavailable/);
  assert.doesNotMatch(html, /applies unchanged/);
  assert.match(html, /Positive total required/); assert.doesNotMatch(html, /\/ 100 ·/);
});
test("unknown release/version/status, malformed endpoints and interval centers fail closed", () => {
  const p = fixture(); p.release_id = "future";
  assert.equal(scoreEvidence(p, DEFAULT_WEIGHTS).range, null);
  const observedZero = fixture(); observedZero.dimensions.OFFENSE.point_value = 0;
  assert.deepEqual(scoreEvidence(observedZero, [0,0,100,0,0,0,0]).range, { lower: 0, upper: 0, intervalOnly: false });
  const v = fixture().dimensions.PEAK;
  for (const patch of [{methodology_version:"future"}, {status:"UNKNOWN"}, {lower_90:80,upper_90:20}, {lower_90:NaN,upper_90:80}, {lower_90:20,upper_90:null}, {status:"PEAK_INTERVAL_ONLY",point_value:50}]) assert.equal(dimensionRange({...v,...patch}, 0), null);
  assert.deepEqual(dimensionRange({...v, status:"PEAK_INTERVAL_ONLY",point_value:null,lower_90:50,upper_90:50},0),{lower:50,upper:50,intervalOnly:true});
});
test("share links deterministically preserve exact players, units, single-category and all-zero states", () => {
  for (const w of [DEFAULT_WEIGHTS, [0,0,100,0,0,0,0], [0,0,0,0,0,0,0], [3,5,7,11,13,17,19]]) {
    const path = comparisonPath("player/a", "player b", w);
    assert.equal(path, comparisonPath("player/a", "player b", w));
    const url = new URL(path, "http://localhost");
    assert.deepEqual(parseWeights(url.searchParams.get("weights")!).weights, w);
    assert.equal(encodeWeights(w), `v1:${w.join(",")}`);
    assert.match(url.pathname,/player%2Fa\/player%20b/);
  }
  for (const value of ["v2:17,14,16,14,18,10,11", "v1:0,0,100,0,0,0", "v1:0,0,101,0,0,0,0", "v1:0,0,1.5,0,0,0,0", "", ["v1:0,0,100,0,0,0,0","v1:0,0,0,0,100,0,0"]]) assert.equal(parseWeights(value).invalid,true);
});
test("accessible controls and conditional custom evidence remain distinct from frozen probability", () => {
  const a = fixture(), b = fixture(); b.identity.player_id = "b"; b.identity.player_name = "Player B";
  const html = renderToStaticMarkup(<CustomWeightComparison a={a} b={b} initialWeights={[0,0,100,0,0,0,0]} defaultProbability={0.72} invalidLink />);
  assert.equal((html.match(/type="range"/g) ?? []).length, 7);
  for (const dimension of WEIGHT_DIMENSIONS) assert.match(html, new RegExp(`for="weight-${dimension}"`));
  assert.match(html, /aria-live="polite"/); assert.match(html,/Reset to GOAT Lab default/);
  assert.match(html,/Invalid or unsupported shared weights/);
  assert.match(html,/Custom win probability unavailable/);
  assert.match(html,/Too close to call/);
  assert.match(html,/no joint coverage guarantee/);
});


test("edited share is held exactly; other percentages move together at a total of 100", () => {
  assert.deepEqual(rebalanceWeights(DEFAULT_WEIGHTS, 6, 40), [12, 9, 11, 9, 12, 7, 40]);
  for (const weights of [DEFAULT_WEIGHTS, [1, 2, 3, 4, 5, 6, 7], [0, 0, 0, 0, 0, 0, 100], [0, 0, 0, 0, 0, 0, 0]]) {
    for (const index of WEIGHT_DIMENSIONS.keys()) {
      for (let selected = 0; selected <= 100; selected++) {
        const shares = rebalanceWeights(weights, index, selected);
        assert.equal(shares[index], selected);
        assert.equal(shares.reduce((sum, n) => sum + n, 0), 100);
        assert.ok(shares.every((value) => Number.isInteger(value) && value >= 0 && value <= 100));
      }
    }
  }
  assert.deepEqual(rebalanceWeights([0, 0, 0, 0, 0, 0, 100], 6, 99), [0, 0, 0, 0, 1, 0, 99]);
  assert.deepEqual(rebalanceWeights([0, 0, 0, 0, 0, 0, 100], 6, 11), DEFAULT_WEIGHTS);
});

test("legacy rounded control display does not mutate exact old shares or scores", () => {
  const old = [1, 2, 3, 4, 5, 6, 7];
  assert.deepEqual(displayWeightShares(old), [4, 7, 11, 14, 18, 21, 25]);
  assert.deepEqual(parseWeights(encodeWeights(old)).weights, old);
  const html = renderToStaticMarkup(<CustomWeightComparison a={fixture()} b={fixture()} initialWeights={old} />);
  assert.match(html, /exact shared proportions/);
  assert.match(html, /aria-valuetext="4 percent"/);
});
