"""HTTP-neutral response models for STEP-0016 ranking products."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from goatlab.rankings.publication_policy import PairwiseOrder, RankingStatus, Top100Membership


class ProductModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerIdentity(ProductModel):
    player_id: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    search_name: str = Field(min_length=1)
    career_state: Literal["ACTIVE", "RETIRED", "UNKNOWN"]
    career_start_season: int | None = None
    career_end_season: int | None = None
    latest_season_used: int | None = None
    cutoff_season: Literal["2025-26"] = "2025-26"
    ranking_status: RankingStatus
    ranking_eligible: bool

    @model_validator(mode="after")
    def check_career(self) -> PlayerIdentity:
        if self.career_state == "ACTIVE" and self.career_end_season is not None:
            raise ValueError("active career cannot have an observed career end")
        if self.ranking_eligible == (self.ranking_status == RankingStatus.UNAVAILABLE):
            raise ValueError("ranking eligibility and evidence status disagree")
        return self


class OverallDistributionSummary(ProductModel):
    center: float | None = Field(default=None, ge=0, le=100)
    center_semantics: Literal["DIAGNOSTIC_SUMMARY"] | None = None
    lower_80: float = Field(ge=0, le=100)
    upper_80: float = Field(ge=0, le=100)
    lower_90: float = Field(ge=0, le=100)
    upper_90: float = Field(ge=0, le=100)
    lower_95: float = Field(ge=0, le=100)
    upper_95: float = Field(ge=0, le=100)
    distribution_ref: str = Field(min_length=1)
    distribution_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_intervals(self) -> OverallDistributionSummary:
        if (self.center is None) != (self.center_semantics is None):
            raise ValueError("center requires diagnostic label")
        if not (
            self.lower_95
            <= self.lower_90
            <= self.lower_80
            <= self.upper_80
            <= self.upper_90
            <= self.upper_95
        ):
            raise ValueError("Overall intervals are not nested")
        if self.center is not None and not self.lower_95 <= self.center <= self.upper_95:
            raise ValueError("center lies outside Overall range")
        return self


class RankDistributionSummary(ProductModel):
    median_rank: float = Field(ge=1)
    mean_rank: float = Field(ge=1)
    lower_50: float = Field(ge=1)
    upper_50: float = Field(ge=1)
    lower_80: float = Field(ge=1)
    upper_80: float = Field(ge=1)
    lower_90: float = Field(ge=1)
    upper_90: float = Field(ge=1)
    lower_95: float = Field(ge=1)
    upper_95: float = Field(ge=1)

    @model_validator(mode="after")
    def check_intervals(self) -> RankDistributionSummary:
        if not (
            self.lower_95
            <= self.lower_90
            <= self.lower_80
            <= self.lower_50
            <= self.median_rank
            <= self.upper_50
            <= self.upper_80
            <= self.upper_90
            <= self.upper_95
        ):
            raise ValueError("rank bands are not nested")
        return self


class TopNProbabilities(ProductModel):
    top_1: float = Field(ge=0, le=1)
    top_5: float = Field(ge=0, le=1)
    top_10: float = Field(ge=0, le=1)
    top_25: float = Field(ge=0, le=1)
    top_50: float = Field(ge=0, le=1)
    top_100: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def check_monotonicity(self) -> TopNProbabilities:
        if (
            not self.top_1
            <= self.top_5
            <= self.top_10
            <= self.top_25
            <= self.top_50
            <= self.top_100
        ):
            raise ValueError("Top-N probabilities must be nondecreasing")
        return self


class DimensionProfile(ProductModel):
    dimension: Literal[
        "PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"
    ]
    status: str = Field(min_length=1)
    point_value: float | None = Field(default=None, ge=0, le=100)
    diagnostic_center: float | None = Field(default=None, ge=0, le=100)
    lower_90: float | None = Field(default=None, ge=0, le=100)
    upper_90: float | None = Field(default=None, ge=0, le=100)
    methodology_version: str = Field(min_length=1)
    confidence: str | None = None
    reason_codes: tuple[str, ...] = ()
    evidence_metadata: dict[str, str | float | int | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_display(self) -> DimensionProfile:
        if (self.lower_90 is None) != (self.upper_90 is None):
            raise ValueError("dimension interval requires both bounds")
        if (
            self.lower_90 is not None
            and self.upper_90 is not None
            and self.lower_90 > self.upper_90
        ):
            raise ValueError("dimension interval is reversed")
        if "INTERVAL_ONLY" in self.status and self.point_value is not None:
            raise ValueError("interval-native dimension has no official point")
        if "INTERVAL_ONLY" in self.status and self.lower_90 is None:
            raise ValueError("interval-native dimension needs a range")
        if ("UNAVAILABLE" in self.status or self.status == "NOT_QUERIED") and (
            self.point_value is not None or self.diagnostic_center is not None
        ):
            raise ValueError("missing dimension is not zero or a diagnostic center")
        return self


class LeaderboardEntry(ProductModel):
    release_id: str = Field(min_length=1)
    display_position: int = Field(ge=1)
    display_position_semantics: Literal["NAVIGATIONAL_MEDIAN_RANK_SORT"]
    player_id: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    active: bool | None
    overall: OverallDistributionSummary
    rank: RankDistributionSummary
    top_n: TopNProbabilities
    ranking_status: RankingStatus
    overall_source_status: str = Field(min_length=1)
    top100_membership: Top100Membership
    disclosure_codes: tuple[str, ...]
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]
    overall_substrate_version: Literal["goatlab-v1-overall-v2-tiered"]
    cutoff_season: Literal["2025-26"]

    @model_validator(mode="after")
    def check_eligibility(self) -> LeaderboardEntry:
        if self.ranking_status == RankingStatus.UNAVAILABLE:
            raise ValueError("unavailable player cannot enter leaderboard")
        return self


class PlayerProfile(ProductModel):
    release_id: str = Field(min_length=1)
    identity: PlayerIdentity
    leaderboard: LeaderboardEntry | None
    dimensions: dict[str, DimensionProfile]
    reason_codes: tuple[str, ...]
    methodology_versions: dict[str, str]
    active_career_policy: Literal["TO_DATE_NO_PROJECTION"]
    uncertainty_is_quality_penalty: Literal[False] = False

    @model_validator(mode="after")
    def check_profile(self) -> PlayerProfile:
        expected = {"PEAK", "LONGEVITY", "OFFENSE", "DEFENSE", "PLAYOFFS", "ACCOLADES", "WINNING"}
        if set(self.dimensions) != expected:
            raise ValueError("profile requires seven dimension objects")
        if self.identity.ranking_eligible != (self.leaderboard is not None):
            raise ValueError("profile and leaderboard eligibility disagree")
        if self.leaderboard is not None and self.leaderboard.player_id != self.identity.player_id:
            raise ValueError("profile identity mismatch")
        return self


class RankingRelease(ProductModel):
    release_id: str = Field(min_length=1)
    generated_at_utc: str = Field(min_length=1)
    cutoff_season: Literal["2025-26"]
    player_count: int = Field(ge=1)
    rankable_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]
    overall_substrate_version: Literal["goatlab-v1-overall-v2-tiered"]
    exact_overall_point_promoted: Literal[False]
    artifact_sha256: dict[str, str]
    upstream_sha256: dict[str, str]
    release_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_counts(self) -> RankingRelease:
        if self.player_count != self.rankable_count + self.unavailable_count:
            raise ValueError("release population does not reconcile")
        return self


class PairwiseDimension(ProductModel):
    dimension: str
    player_a: DimensionProfile
    player_b: DimensionProfile
    diagnostic_center_difference: float | None = None
    difference_is_exact: Literal[False] = False


class PairwiseResponse(ProductModel):
    release_id: str
    player_a_id: str
    player_b_id: str
    probability_a_above_b: float = Field(ge=0, le=1)
    probability_b_above_a: float = Field(ge=0, le=1)
    tie_probability: float = Field(ge=0, le=1)
    ordering_label: PairwiseOrder
    player_a_overall: OverallDistributionSummary
    player_b_overall: OverallDistributionSummary
    player_a_rank: RankDistributionSummary
    player_b_rank: RankDistributionSummary
    overall_90_ranges_overlap: bool
    dimensions: dict[str, PairwiseDimension]
    uncertainty_context: Literal["CONDITIONAL_ON_FROZEN_MEASUREMENT_ARCHITECTURE"]
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]

    @model_validator(mode="after")
    def check_pairwise(self) -> PairwiseResponse:
        if self.player_a_id == self.player_b_id:
            raise ValueError("cannot compare a player with himself")
        if abs(self.probability_a_above_b + self.probability_b_above_a - 1) > 1e-12:
            raise ValueError("pairwise probabilities are not complementary")
        if not 0 <= self.tie_probability <= 1:
            raise ValueError("invalid tie probability")
        return self
