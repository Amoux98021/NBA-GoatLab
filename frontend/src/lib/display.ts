import type { DimensionProfile, Membership, RankingStatus } from "./types";

export const DIMENSIONS: DimensionProfile["dimension"][] = ["PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"];

export const DIMENSION_DESCRIPTIONS: Record<DimensionProfile["dimension"], string> = {
  PEAK: "Highest sustained regular-season level.",
  LONGEVITY: "Duration near elite regular-season performance.",
  OFFENSE: "Regular-season scoring and creation value.",
  DEFENSE: "Individual defensive value from era-available evidence.",
  PLAYOFFS: "Individual postseason performance.",
  ACCOLADES: "Major honors and sustained recognition.",
  WINNING: "Team success with participation and context.",
};

export function number(value: number, digits = 1): string {
  return value.toFixed(digits);
}

export function percent(value: number): string {
  if (value === 0 || value === 1) return `${value * 100}%`;
  const scaled = value * 100;
  return `${scaled.toFixed(scaled < 1 || scaled > 99 ? 2 : 1)}%`;
}

export function rank(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function statusLabel(status: RankingStatus | string): string {
  if (status === "OFFICIAL" || status.startsWith("OFFICIAL_")) return "Official";
  if (status === "PROVISIONAL" || status.startsWith("PROVISIONAL_")) return "Provisional";
  if (status === "INTERVAL_NATIVE" || status.includes("INTERVAL_ONLY")) return "Interval-native";
  if (status === "UNAVAILABLE" || status.includes("UNAVAILABLE") || status === "NOT_QUERIED") return "Unavailable";
  if (status === "INSUFFICIENT_SAMPLE") return "Insufficient sample";
  return status === "AVAILABLE" ? "Available" : status.replaceAll("_", " ").toLowerCase();
}

export function membershipLabel(value: Membership): string {
  const labels: Record<Membership, string> = {
    ROBUST_TOP100: "Robust Top 100",
    LIKELY_TOP100: "Likely Top 100",
    TOP100_BUBBLE: "Top-100 bubble",
    LIKELY_OUTSIDE_TOP100: "Likely outside",
    ROBUST_OUTSIDE_TOP100: "Robustly outside",
  };
  return labels[value];
}

export function dimensionDisplay(dimension: DimensionProfile): string {
  if (dimension.status.includes("INTERVAL_ONLY")) {
    return dimension.lower_90 !== null && dimension.upper_90 !== null
      ? `${number(dimension.lower_90)}–${number(dimension.upper_90)}`
      : "Insufficient evidence";
  }
  if (dimension.point_value !== null) return number(dimension.point_value);
  return dimension.lower_90 !== null && dimension.upper_90 !== null
    ? `${number(dimension.lower_90)}–${number(dimension.upper_90)}`
    : "Insufficient evidence";
}

export function reasonLabel(code: string): string {
  const human = code.split(":").at(-1) ?? code;
  const specific: Record<string, string> = {
    NOT_QUERIED: "This evidence was not queried or is not available in the frozen source.",
    HISTORICALLY_NOT_RECORDED: "This statistic was not recorded in that era.",
    SOURCE_UNAVAILABLE: "The source record is unavailable.",
    NO_PRESENCE_PREDICTION: "Defensive Presence is used only where observed.",
    INSUFFICIENT_CAREER: "There are too few qualifying seasons for this dimension.",
    TO_DATE_NO_PROJECTION: "Active career measured through the cutoff only; no future projection.",
  };
  return specific[human] ?? human.replaceAll("_", " ").toLowerCase();
}
