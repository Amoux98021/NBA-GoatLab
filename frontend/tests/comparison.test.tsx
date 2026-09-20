import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, comparePlayers } from "../src/lib/api";
import { orderingCopy } from "../src/components/comparison-view";

const release = "goatlab-ranking-release-2026-v2-probabilistic";
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

function pair() {
  return {
    release_id: release,
    player_a_id: "player_a",
    player_b_id: "player_b",
    probability_a_above_b: 0.72,
    probability_b_above_a: 0.28,
    tie_probability: 0,
    ordering_label: "LEAN_A_OVER_B",
    ranking_policy_version: "goatlab-v1-ranking-policy-v2-probabilistic",
    uncertainty_context: "CONDITIONAL_ON_FROZEN_MEASUREMENT_ARCHITECTURE",
    player_a_overall: {}, player_b_overall: {}, player_a_rank: {}, player_b_rank: {},
    dimensions: Object.fromEntries(["PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"].map((name) => [name, {}])),
  };
}

test("pairwise client preserves backend probability and frozen ordering label", async () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  let requested = "";
  globalThis.fetch = async (input) => {
    requested = String(input);
    return Response.json(pair());
  };
  const result = await comparePlayers("player_a", "player_b");
  assert.equal(result.probability_a_above_b, 0.72);
  assert.equal(result.ordering_label, "LEAN_A_OVER_B");
  assert.equal(requested, "http://api.test/api/v1/compare/player_a/player_b");
});

test("pairwise client rejects wrong release, player IDs, malformed or noncomplementary probabilities", async () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  for (const change of [
    { release_id: "other" },
    { player_b_id: "different" },
    { probability_a_above_b: 1.1 },
    { probability_a_above_b: 0.73 },
    { ordering_label: "UNKNOWN" },
    { dimensions: { PEAK: {} } },
  ]) {
    globalThis.fetch = async () => Response.json({ ...pair(), ...change });
    await assert.rejects(() => comparePlayers("player_a", "player_b"), ApiError);
  }
});

test("structured 422 is preserved for the unavailable comparison state", async () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  globalThis.fetch = async () => Response.json({ detail: { code: "COMPARISON_UNAVAILABLE", player_ids: ["player_b"] } }, { status: 422 });
  await assert.rejects(() => comparePlayers("player_a", "player_b"), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 422);
    assert.equal(error.code, "COMPARISON_UNAVAILABLE");
    assert.deepEqual(error.playerIds, ["player_b"]);
    return true;
  });
});

test("strong, lean, and indeterminate copy follows backend label without frontend threshold inference", () => {
  assert.match(orderingCopy("STRONG_A_OVER_B", "A", "B", 0.94, 0.06).heading, /Strong ordering evidence for A/);
  assert.match(orderingCopy("LEAN_B_OVER_A", "A", "B", 0.2, 0.8).detail, /lean, not a definitive ordering/);
  assert.match(orderingCopy("INDETERMINATE", "A", "B", 0.53, 0.47).heading, /Too close/);
  assert.match(orderingCopy("STRONG_B_OVER_A", "A", "B", 0.05, 0.95).heading, /Strong ordering evidence for B/);
});
