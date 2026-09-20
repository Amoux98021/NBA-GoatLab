import assert from "node:assert/strict";
import { test } from "node:test";
import { statusLabel } from "../src/lib/display";

const live = process.env.GOATLAB_TEST_LIVE === "1";
const api = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const site = process.env.GOATLAB_TEST_FRONTEND_URL ?? "http://127.0.0.1:3000";

test("Top-100 HTML preserves frozen API player order and display positions", { skip: !live }, async () => {
  const payload = await fetch(`${api}/api/v1/top100`).then((response) => response.json());
  const html = await fetch(site).then((response) => response.text());
  const body = html.match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1];
  assert.ok(body, "desktop table must be server-rendered");
  const playerIds = [...body.matchAll(/href="\/players\/(player_[a-z0-9]+)"/g)].map((match) => match[1]);
  assert.equal(payload.entries.length, 100);
  assert.deepEqual(playerIds, payload.entries.map((entry: { player_id: string }) => entry.player_id));
  assert.deepEqual(payload.entries.map((entry: { display_position: number }) => entry.display_position), Array.from({ length: 100 }, (_, index) => index + 1));
});

test("diagnostic profiles render API names, statuses, and 90% ranges without changing values", { skip: !live }, async () => {
  const names = ["Michael Jordan", "LeBron James", "Stephen Curry", "Kobe Bryant", "Rudy Gobert", "Bill Russell", "George Mikan"];
  for (const name of names) {
    const page = await fetch(`${api}/api/v1/leaderboard?search=${encodeURIComponent(name)}&limit=50`).then((response) => response.json());
    const entry = page.entries.find((item: { player_name: string }) => item.player_name === name);
    assert.ok(entry, `${name} must be rankable`);
    const profile = await fetch(`${api}/api/v1/players/${entry.player_id}`).then((response) => response.json());
    const html = await fetch(`${site}/players/${entry.player_id}`).then((response) => response.text());
    assert.ok(html.includes(profile.identity.player_name), `${name} identity mismatch`);
    assert.ok(html.includes(statusLabel(profile.identity.ranking_status)), `${name} status mismatch`);
    assert.ok(html.includes(profile.leaderboard.overall.lower_90.toFixed(1)) && html.includes(profile.leaderboard.overall.upper_90.toFixed(1)), `${name} Overall interval mismatch`);
  }
  const unavailable = "player_00073e3eef455e09bf506949f46b4139";
  const html = await fetch(`${site}/players/${unavailable}`).then((response) => response.text());
  assert.ok(html.includes("Ranking unavailable"));
  assert.ok(!html.includes("No calibrated Overall distribution</p><strong>#"));
});
