import type { LeaderboardPage, Methodology, PairwiseResponse, PlayerProfile, RankingRelease, Top100Entry } from "./types";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string, public readonly playerIds: string[] = []) {
    super(message);
    this.name = "ApiError";
  }
}

const expectedRelease = process.env.GOATLAB_RELEASE_ID ?? "goatlab-ranking-release-2026-v2-probabilistic";

function baseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!raw) throw new ApiError("The ranking service is not configured.", 503);
  return raw.replace(/\/+$/, "");
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function released(value: unknown): asserts value is Record<string, unknown> {
  if (!record(value) || value.release_id !== expectedRelease) {
    throw new ApiError("Ranking release response did not match the configured release.", 502);
  }
}

async function get(path: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl()}/api/v1${path}`, {
      // A release is immutable. The URL and deployment configuration pin its identity.
      next: { revalidate: 3600 },
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError("The ranking service is temporarily unavailable.", 503);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = record(body) && record(body.detail) ? body.detail : null;
    const code = detail && typeof detail.code === "string" ? detail.code : undefined;
    const ids = detail && Array.isArray(detail.player_ids) ? detail.player_ids.filter((id): id is string => typeof id === "string") : [];
    throw new ApiError(response.status === 404 ? "This record was not found." : response.status === 422 ? "This matchup lacks a defensible pairwise probability." : response.status === 400 ? "Choose two different players." : "The ranking service could not complete this request.", response.status, code, ids);
  }
  try {
    return await response.json();
  } catch {
    throw new ApiError("The ranking service returned an invalid response.", 502);
  }
}

export function validateTop100(value: unknown): Top100Entry[] {
  released(value);
  if (!Array.isArray(value.entries) || value.entries.length !== 100) {
    throw new ApiError("The Top 100 response is incomplete.", 502);
  }
  for (const [index, entry] of value.entries.entries()) {
    if (!record(entry) || entry.display_position !== index + 1 || typeof entry.player_id !== "string" || typeof entry.player_name !== "string" || entry.release_id !== expectedRelease || typeof entry.median_rank !== "number" || typeof entry.rank_lower_80 !== "number" || typeof entry.rank_upper_80 !== "number" || typeof entry.top_10_probability !== "number" || typeof entry.top_100_probability !== "number" || typeof entry.overall_lower_90 !== "number" || typeof entry.overall_upper_90 !== "number" || typeof entry.ranking_status !== "string") {
      throw new ApiError("The Top 100 response is malformed.", 502);
    }
  }
  return value.entries as Top100Entry[];
}

export async function getTop100(): Promise<Top100Entry[]> {
  return validateTop100(await get("/top100"));
}

export interface LeaderboardQuery {
  limit?: number;
  offset?: number;
  search?: string;
  active?: boolean;
  status?: "OFFICIAL" | "PROVISIONAL" | "INTERVAL_NATIVE";
}

export async function getLeaderboard(query: LeaderboardQuery = {}): Promise<LeaderboardPage> {
  const params = new URLSearchParams({ release: expectedRelease, limit: String(query.limit ?? 50), offset: String(query.offset ?? 0) });
  if (query.search) params.set("search", query.search);
  if (query.active !== undefined) params.set("active", String(query.active));
  if (query.status) params.set("status", query.status);
  const value = await get(`/leaderboard?${params}`);
  released(value);
  if (!Array.isArray(value.entries) || typeof value.total !== "number" || value.entries.some((entry: unknown) => !record(entry) || typeof entry.player_id !== "string" || typeof entry.player_name !== "string" || typeof entry.display_position !== "number" || !record(entry.rank) || typeof entry.rank.median_rank !== "number" || typeof entry.rank.lower_80 !== "number" || typeof entry.rank.upper_80 !== "number" || !record(entry.top_n) || typeof entry.top_n.top_100 !== "number" || !record(entry.overall) || typeof entry.overall.lower_90 !== "number" || typeof entry.overall.upper_90 !== "number" || typeof entry.ranking_status !== "string")) {
    throw new ApiError("The leaderboard response is malformed.", 502);
  }
  return value as unknown as LeaderboardPage;
}

export async function getPlayer(playerId: string): Promise<PlayerProfile> {
  const value = await get(`/players/${encodeURIComponent(playerId)}`);
  released(value);
  if (!record(value.identity) || value.identity.player_id !== playerId || !record(value.dimensions) || typeof value.identity.ranking_eligible !== "boolean" || (value.identity.ranking_eligible && !record(value.leaderboard)) || ["PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"].some((dimension) => !record((value.dimensions as Record<string, unknown>)[dimension]))) {
    throw new ApiError("The player profile response is malformed.", 502);
  }
  return value as unknown as PlayerProfile;
}

export async function getMethodology(): Promise<Methodology> {
  const value = await get("/methodology");
  released(value);
  if (!record(value.disclosures) || !record(value.dimension_methodology_versions)) {
    throw new ApiError("The methodology response is malformed.", 502);
  }
  return value as unknown as Methodology;
}

export async function getRelease(): Promise<RankingRelease> {
  const value = await get(`/releases/${encodeURIComponent(expectedRelease)}`);
  released(value);
  if (typeof value.release_fingerprint !== "string" || typeof value.rankable_count !== "number") {
    throw new ApiError("The release response is malformed.", 502);
  }
  return value as unknown as RankingRelease;
}

const orderLabels = new Set(["STRONG_A_OVER_B", "LEAN_A_OVER_B", "INDETERMINATE", "LEAN_B_OVER_A", "STRONG_B_OVER_A"]);
const dimensionNames = ["PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"];

export async function comparePlayers(playerA: string, playerB: string): Promise<PairwiseResponse> {
  const value = await get(`/compare/${encodeURIComponent(playerA)}/${encodeURIComponent(playerB)}`);
  released(value);
  const a = value.probability_a_above_b;
  const b = value.probability_b_above_a;
  if (
    value.player_a_id !== playerA || value.player_b_id !== playerB ||
    typeof a !== "number" || typeof b !== "number" || !Number.isFinite(a) || !Number.isFinite(b) ||
    a < 0 || a > 1 || b < 0 || b > 1 || Math.abs(a + b - 1) > 1e-9 ||
    typeof value.tie_probability !== "number" || value.tie_probability < 0 || value.tie_probability > 1 ||
    !orderLabels.has(String(value.ordering_label)) ||
    value.ranking_policy_version !== "goatlab-v1-ranking-policy-v2-probabilistic" ||
    value.uncertainty_context !== "CONDITIONAL_ON_FROZEN_MEASUREMENT_ARCHITECTURE" ||
    !record(value.player_a_overall) || !record(value.player_b_overall) ||
    !record(value.player_a_rank) || !record(value.player_b_rank) || !record(value.dimensions) ||
    dimensionNames.some((name) => !record((value.dimensions as Record<string, unknown>)[name]))
  ) {
    throw new ApiError("The comparison response is malformed.", 502);
  }
  return value as unknown as PairwiseResponse;
}
