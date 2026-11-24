import type { DimensionProfile, PlayerProfile } from "./types";

export const WEIGHT_DIMENSIONS = ["PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"] as const;
export type Weights = readonly number[];
export const DEFAULT_WEIGHTS: Weights = [17, 14, 16, 14, 18, 10, 11];
export const CUSTOM_VERSION = "v1";
const RELEASE = "goatlab-ranking-release-2026-v2-probabilistic";
const VERSIONS = ["goatlab-v1-peak-v2", "goatlab-v1-longevity-v2-tiered", "goatlab-v1-dimension-scores-v1", "goatlab-v1-defense-v2-tiered", "goatlab-v1-dimension-scores-v1", "goatlab-v1-dimension-scores-v1", "goatlab-v1-dimension-scores-v1"];
const STATUSES = [
  new Set(["OFFICIAL_PEAK_POINT", "PROVISIONAL_PEAK_POINT", "PEAK_INTERVAL_ONLY"]),
  new Set(["OFFICIAL_LONGEVITY_POINT", "PROVISIONAL_LONGEVITY_POINT", "LONGEVITY_INTERVAL_ONLY"]),
  new Set(["AVAILABLE", "PARTIAL_EVIDENCE"]),
  new Set(["OFFICIAL_DEFENSE_POINT", "PROVISIONAL_DEFENSE_POINT", "DEFENSE_INTERVAL_ONLY"]),
  new Set(["AVAILABLE", "PARTIAL_EVIDENCE"]),
  new Set(["AVAILABLE", "PARTIAL_EVIDENCE"]),
  new Set(["AVAILABLE", "PARTIAL_EVIDENCE"]),
];
export function validWeights(weights: Weights): boolean {
  return weights.length === 7 && weights.every((n) => Number.isInteger(n) && n >= 0 && n <= 100);
}
export function encodeWeights(weights: Weights): string {
  if (!validWeights(weights)) throw new Error("Weights must be seven integers from 0 to 100.");
  return `${CUSTOM_VERSION}:${weights.join(",")}`;
}
export function parseWeights(raw: string | string[] | undefined): { weights: Weights; invalid: boolean } {
  if (raw === undefined) return { weights: DEFAULT_WEIGHTS, invalid: false };
  if (typeof raw !== "string" || !/^v1:(?:0|[1-9]\d?|100)(?:,(?:0|[1-9]\d?|100)){6}$/.test(raw)) return { weights: DEFAULT_WEIGHTS, invalid: true };
  return { weights: raw.slice(3).split(",").map(Number), invalid: false };
}
export function normalizedWeights(weights: Weights): number[] | null {
  const total = weights.reduce((sum, n) => sum + n, 0);
  return validWeights(weights) && total > 0 ? weights.map((n) => n / total) : null;
}
export function isDefault(weights: Weights): boolean {
  const normalized = normalizedWeights(weights);
  return normalized !== null && normalized.every((n, i) => Math.abs(n - DEFAULT_WEIGHTS[i] / 100) < 1e-12);
}
// Largest remainder allocation keeps the integer budget exact; ties use category order.
function allocateShares(total: number, bases: Weights): number[] {
  const sum = bases.reduce((a, b) => a + b, 0);
  if (sum === 0) return bases.map(() => 0);
  const allocations = bases.map((weight) => Math.floor(total * weight / sum));
  const order = bases.map((weight, index) => ({ index, remainder: (total * weight) % sum }))
    .sort((a, b) => b.remainder - a.remainder || a.index - b.index);
  const remaining = total - allocations.reduce((a, b) => a + b, 0);
  for (const { index } of order.slice(0, remaining)) allocations[index]++;
  return allocations;
}

export function displayWeightShares(weights: Weights): Weights {
  return allocateShares(100, weights);
}

export function rebalanceWeights(weights: Weights, index: number, selected: number): Weights {
  const others = weights.map((weight, i) => i === index ? 0 : weight);
  // On leaving a 100% category (or an old all-zero link), use default proportions for the rest.
  const basis = others.some((weight) => weight > 0) ? others : DEFAULT_WEIGHTS.map((weight, i) => i === index ? 0 : weight);
  const result = allocateShares(100 - selected, basis);
  result[index] = selected;
  return result;
}

export function comparisonPath(a: string, b: string, weights: Weights): string {
  return `/compare/${encodeURIComponent(a)}/${encodeURIComponent(b)}?weights=${encodeURIComponent(encodeWeights(weights))}`;
}
export type EvidenceRange = { lower: number; upper: number; intervalOnly: boolean };
export function dimensionRange(value: DimensionProfile, index: number): EvidenceRange | null {
  if (value.dimension !== WEIGHT_DIMENSIONS[index] || value.methodology_version !== VERSIONS[index] || !STATUSES[index]?.has(value.status)) return null;
  const valid = (n: number | null): n is number => n !== null && Number.isFinite(n) && n >= 0 && n <= 100;
  const intervalOnly = value.status.endsWith("INTERVAL_ONLY");
  if (valid(value.lower_90) && valid(value.upper_90) && value.lower_90 <= value.upper_90) return { lower: value.lower_90, upper: value.upper_90, intervalOnly };
  if (!intervalOnly && value.lower_90 === null && value.upper_90 === null && valid(value.point_value)) return { lower: value.point_value, upper: value.point_value, intervalOnly: false };
  return null;
}
// Endpoint arithmetic over published marginal evidence. This is neither a joint interval
// nor a calibrated probability; diagnostic centers are deliberately never read.
export function scoreEvidence(profile: PlayerProfile, weights: Weights): { range: EvidenceRange | null; missing: string[] } {
  const normalized = normalizedWeights(weights);
  if (!normalized || profile.release_id !== RELEASE) return { range: null, missing: [!normalized ? "Positive total required" : "Unsupported release"] };
  let lower = 0, upper = 0, intervalOnly = false;
  const missing: string[] = [];
  WEIGHT_DIMENSIONS.forEach((dimension, i) => {
    if (normalized[i] === 0) return; // An explicit zero is the only permitted omission.
    const range = dimensionRange(profile.dimensions[dimension], i);
    if (!range) { missing.push(dimension); return; }
    lower += normalized[i] * range.lower;
    upper += normalized[i] * range.upper;
    intervalOnly ||= range.intervalOnly;
  });
  return { range: missing.length ? null : { lower, upper, intervalOnly }, missing };
}
