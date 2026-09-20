export type RankingStatus = "OFFICIAL" | "PROVISIONAL" | "INTERVAL_NATIVE" | "UNAVAILABLE";
export type Membership =
  | "ROBUST_TOP100"
  | "LIKELY_TOP100"
  | "TOP100_BUBBLE"
  | "LIKELY_OUTSIDE_TOP100"
  | "ROBUST_OUTSIDE_TOP100";

export interface OverallSummary {
  center: number | null;
  center_semantics: "DIAGNOSTIC_SUMMARY" | null;
  lower_80: number;
  upper_80: number;
  lower_90: number;
  upper_90: number;
  lower_95: number;
  upper_95: number;
}

export interface RankSummary {
  median_rank: number;
  mean_rank: number;
  lower_50: number;
  upper_50: number;
  lower_80: number;
  upper_80: number;
  lower_90: number;
  upper_90: number;
  lower_95: number;
  upper_95: number;
}

export interface TopN {
  top_1: number;
  top_5: number;
  top_10: number;
  top_25: number;
  top_50: number;
  top_100: number;
}

export interface LeaderboardEntry {
  release_id: string;
  display_position: number;
  player_id: string;
  player_name: string;
  active: boolean | null;
  overall: OverallSummary;
  rank: RankSummary;
  top_n: TopN;
  ranking_status: Exclude<RankingStatus, "UNAVAILABLE">;
  overall_source_status: string;
  top100_membership: Membership;
  disclosure_codes: string[];
  ranking_policy_version: string;
  cutoff_season: string;
}

export interface Top100Entry {
  active: boolean | null;
  cutoff_season: string;
  display_position: number;
  median_rank: number;
  overall_center: number | null;
  overall_center_semantics: "DIAGNOSTIC_SUMMARY" | null;
  overall_lower_90: number;
  overall_upper_90: number;
  player_id: string;
  player_name: string;
  rank_lower_80: number;
  rank_upper_80: number;
  rank_lower_90: number;
  rank_upper_90: number;
  ranking_status: Exclude<RankingStatus, "UNAVAILABLE">;
  top100_membership: Membership;
  top_10_probability: number;
  top_25_probability: number;
  top_50_probability: number;
  top_100_probability: number;
  release_id: string;
}

export interface LeaderboardPage {
  release_id: string;
  total: number;
  limit: number;
  offset: number;
  entries: LeaderboardEntry[];
}

export interface DimensionProfile {
  dimension: "PEAK" | "LONGEVITY" | "OFFENSE" | "DEFENSE" | "PLAYOFFS" | "ACCOLADES" | "WINNING";
  status: string;
  point_value: number | null;
  diagnostic_center: number | null;
  lower_90: number | null;
  upper_90: number | null;
  methodology_version: string;
  confidence: string | null;
  reason_codes: string[];
  evidence_metadata: Record<string, string | number | null>;
}

export interface PlayerProfile {
  release_id: string;
  identity: {
    player_id: string;
    player_name: string;
    career_state: "ACTIVE" | "RETIRED" | "UNKNOWN";
    career_start_season: number | null;
    career_end_season: number | null;
    latest_season_used: number | null;
    cutoff_season: string;
    ranking_status: RankingStatus;
    ranking_eligible: boolean;
  };
  leaderboard: LeaderboardEntry | null;
  dimensions: Record<DimensionProfile["dimension"], DimensionProfile>;
  reason_codes: string[];
  methodology_versions: Record<string, string>;
  active_career_policy: "TO_DATE_NO_PROJECTION";
  uncertainty_is_quality_penalty: false;
}

export interface Methodology {
  release_id: string;
  cutoff_season: string;
  ranking_policy_version: string;
  overall_substrate_version: string;
  exact_overall_point_promoted: false;
  dimension_methodology_versions: Record<string, string>;
  disclosures: Record<string, string>;
  active_career_policy: "TO_DATE_NO_PROJECTION";
  publication_rights_gate: "PUBLICATION_RIGHTS_REVIEW_REQUIRED";
}

export interface RankingRelease {
  release_id: string;
  release_fingerprint: string;
  cutoff_season: string;
  player_count: number;
  rankable_count: number;
  unavailable_count: number;
  ranking_policy_version: string;
}
