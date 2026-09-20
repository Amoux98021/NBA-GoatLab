import assert from "node:assert/strict";
import { test } from "node:test";
import { percent } from "../src/lib/display";

const live = process.env.GOATLAB_TEST_LIVE === "1";
const api = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const site = process.env.GOATLAB_TEST_FRONTEND_URL ?? "http://127.0.0.1:3000";
const ids = {
  jordan: "player_a274ec9223a25dabaa1972e8610b4b84",
  lebron: "player_ae8bd817fd095b748cbeca969369a966",
  curry: "player_2e91fa79b96359ae8b93f6c9dd8f7a4e",
  kobe: "player_dd5f0bde53db5cef8a1d3b738e9d67b9",
  russell: "player_c0f05230945752728b22330b9dc82c5b",
  wilt: "player_860bacb725f05f02b5871e085270f726",
  kareem: "player_ee62fde09b405fa18c2516d1f5cd4e81",
  duncan: "player_b99799c86e9f5cc1a5008c2c8c721213",
  gobert: "player_7d611c69e597575d839b46dffcaf83b8",
  unavailable: "player_00073e3eef455e09bf506949f46b4139",
};

test("comparison SSR agrees with frozen API across distinct matchups and reverse direction", { skip: !live }, async () => {
  const cases = [
    [ids.jordan, ids.lebron], [ids.curry, ids.kobe], [ids.russell, ids.wilt],
    [ids.kareem, ids.duncan], [ids.curry, ids.gobert],
  ];
  for (const [a, b] of cases) {
    const response = await fetch(`${api}/api/v1/compare/${a}/${b}`);
    assert.equal(response.status, 200);
    const result = await response.json();
    const page = await fetch(`${site}/compare/${a}/${b}`);
    assert.equal(page.status, 200);
    const html = await page.text();
    assert.ok(html.includes(percent(result.probability_a_above_b)));
    assert.ok(html.includes(percent(result.probability_b_above_a)));
    assert.ok(html.includes(result.release_id));
    assert.ok(html.includes(result.ranking_policy_version));
    assert.ok(html.includes("Seven-dimension player comparison"));
    assert.ok(html.includes(`/compare/${b}/${a}`), "reverse link must preserve canonical IDs");
    assert.ok(html.includes("not a direct sum of the displayed point differences"));
    const reverse = await fetch(`${api}/api/v1/compare/${b}/${a}`).then((value) => value.json());
    assert.ok(Math.abs(result.probability_a_above_b - reverse.probability_b_above_a) < 1e-12);
    assert.ok(Math.abs(result.probability_b_above_a - reverse.probability_a_above_b) < 1e-12);
  }
});

test("unavailable, same-player, and unknown-player UI never fabricate a probability", { skip: !live }, async () => {
  const unavailable = await fetch(`${site}/compare/${ids.jordan}/${ids.unavailable}`);
  assert.equal(unavailable.status, 200);
  const unavailableHtml = await unavailable.text();
  assert.ok(unavailableHtml.includes("NO DEFENSIBLE PAIRWISE PROBABILITY"));
  assert.ok(unavailableHtml.includes("no interval midpoint"));
  assert.ok(!unavailableHtml.includes("probability-split"));
  const same = await fetch(`${site}/compare/${ids.jordan}/${ids.jordan}`);
  assert.equal(same.status, 200);
  assert.ok((await same.text()).includes("Choose two different players"));
  const unknown = await fetch(`${site}/compare/${ids.jordan}/not-a-player`);
  // App Router streams the loading shell with HTTP 200 before rendering notFound.
  // The user-visible state must still fail closed with no fabricated matchup.
  const unknownHtml = await unknown.text();
  assert.ok(unknownHtml.includes("That matchup is not in this release"));
  assert.ok(!unknownHtml.includes("probability-split"));
});

test("profile entry and canonical search route support comparison selection", { skip: !live }, async () => {
  const profile = await fetch(`${site}/players/${ids.jordan}`).then((response) => response.text());
  assert.ok(profile.includes(`/compare?playerA=${ids.jordan}`));
  const search = await fetch(`${site}/api/compare/search?q=Jordan`).then((response) => response.json());
  assert.ok(search.entries.some((entry: { player_id: string }) => entry.player_id === ids.jordan));
  assert.ok(search.entries.every((entry: { player_id: string; player_name: string }) => entry.player_id.startsWith("player_") && entry.player_name.length > 0));
});
