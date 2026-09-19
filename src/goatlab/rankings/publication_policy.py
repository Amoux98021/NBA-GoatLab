"""STEP-0015P probabilistic publication contract; no basketball scoring logic."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

POLICY_VERSION = "goatlab-v1-ranking-policy-v2-probabilistic"
PRODUCT_CONTRACT_VERSION = "goatlab-v1-probabilistic-product-contract-v1"
OVERALL_SUBSTRATE_VERSION = "goatlab-v1-overall-v2-tiered"
FROZEN_CUTOFF = "2025-26"
PROBABILITY_LEVELS = (10, 25, 50, 100)
RANK_BAND_LEVELS = (50, 80, 90, 95)
STRONG_ORDER_MINIMUM = 0.90
LEAN_ORDER_MINIMUM = 0.65
INDETERMINATE_LOWER = 0.35
ROBUST_TOP100_MINIMUM = 0.90
LIKELY_TOP100_MINIMUM = 0.65
TOP100_BUBBLE_MINIMUM = 0.35
LIKELY_OUTSIDE_MINIMUM = 0.10


class RankingStatus(StrEnum):
    OFFICIAL = "OFFICIAL"
    PROVISIONAL = "PROVISIONAL"
    INTERVAL_NATIVE = "INTERVAL_NATIVE"
    UNAVAILABLE = "UNAVAILABLE"


class Top100Membership(StrEnum):
    ROBUST_TOP100 = "ROBUST_TOP100"
    LIKELY_TOP100 = "LIKELY_TOP100"
    TOP100_BUBBLE = "TOP100_BUBBLE"
    LIKELY_OUTSIDE_TOP100 = "LIKELY_OUTSIDE_TOP100"
    ROBUST_OUTSIDE_TOP100 = "ROBUST_OUTSIDE_TOP100"


class PairwiseOrder(StrEnum):
    STRONG_A_OVER_B = "STRONG_A_OVER_B"
    LEAN_A_OVER_B = "LEAN_A_OVER_B"
    INDETERMINATE = "INDETERMINATE"
    LEAN_B_OVER_A = "LEAN_B_OVER_A"
    STRONG_B_OVER_A = "STRONG_B_OVER_A"


def ranking_status(overall_status: str, *, distribution_available: bool) -> RankingStatus:
    """Translate evidence status without turning uncertainty into a score adjustment."""

    if overall_status == "OVERALL_UNAVAILABLE":
        if distribution_available:
            raise ValueError("unavailable Overall cannot have a publishable distribution")
        return RankingStatus.UNAVAILABLE
    if not distribution_available:
        raise ValueError("rankable status requires a calibrated Overall distribution")
    statuses = {
        "OFFICIAL_OVERALL_POINT": RankingStatus.OFFICIAL,
        "PROVISIONAL_OVERALL_POINT": RankingStatus.PROVISIONAL,
        "OVERALL_INTERVAL_ONLY": RankingStatus.INTERVAL_NATIVE,
    }
    if overall_status not in statuses:
        raise ValueError(f"unknown Overall status: {overall_status}")
    return statuses[overall_status]


def top100_membership(probability: float) -> Top100Membership:
    """Classify probability only; this cannot change quality or list position."""

    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between zero and one")
    if probability >= ROBUST_TOP100_MINIMUM:
        return Top100Membership.ROBUST_TOP100
    if probability >= LIKELY_TOP100_MINIMUM:
        return Top100Membership.LIKELY_TOP100
    if probability >= TOP100_BUBBLE_MINIMUM:
        return Top100Membership.TOP100_BUBBLE
    if probability >= LIKELY_OUTSIDE_MINIMUM:
        return Top100Membership.LIKELY_OUTSIDE_TOP100
    return Top100Membership.ROBUST_OUTSIDE_TOP100


def pairwise_order(probability_a_above_b: float) -> PairwiseOrder:
    """Return symmetric evidence language, including uncertain adjacent players."""

    if not 0.0 <= probability_a_above_b <= 1.0:
        raise ValueError("probability must be between zero and one")
    if probability_a_above_b >= STRONG_ORDER_MINIMUM:
        return PairwiseOrder.STRONG_A_OVER_B
    if probability_a_above_b >= LEAN_ORDER_MINIMUM:
        return PairwiseOrder.LEAN_A_OVER_B
    if probability_a_above_b >= INDETERMINATE_LOWER:
        return PairwiseOrder.INDETERMINATE
    if 1.0 - probability_a_above_b >= STRONG_ORDER_MINIMUM:
        return PairwiseOrder.STRONG_B_OVER_A
    return PairwiseOrder.LEAN_B_OVER_A


class ProductModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DimensionDisplay(ProductModel):
    """A dimension's point or diagnostic center with explicit evidence semantics."""

    value: float | None = Field(default=None, ge=0, le=100)
    lower_90: float | None = Field(default=None, ge=0, le=100)
    upper_90: float | None = Field(default=None, ge=0, le=100)
    source_status: str = Field(min_length=1)
    value_is_official_point: bool

    @model_validator(mode="after")
    def check_evidence_semantics(self) -> DimensionDisplay:
        if (self.lower_90 is None) != (self.upper_90 is None):
            raise ValueError("dimension interval requires both bounds")
        if self.lower_90 is not None and self.upper_90 is not None:
            if self.lower_90 > self.upper_90:
                raise ValueError("dimension interval is reversed")
            if self.value is not None and not self.lower_90 <= self.value <= self.upper_90:
                raise ValueError("dimension value must be within its interval")
        if (
            "INTERVAL_ONLY" in self.source_status or "UNAVAILABLE" in self.source_status
        ) and self.value_is_official_point:
            raise ValueError("interval/unavailable dimension has no official point")
        if self.value_is_official_point and self.value is None:
            raise ValueError("official dimension point requires a value")
        if "INTERVAL_ONLY" in self.source_status and self.lower_90 is None:
            raise ValueError("interval-only dimension requires an uncertainty range")
        if "UNAVAILABLE" in self.source_status and self.value is not None:
            raise ValueError("unavailable dimension has no diagnostic value")
        if "UNAVAILABLE" in self.source_status and self.lower_90 is not None:
            raise ValueError("unavailable dimension has no usable interval")
        return self


class PlayerLeaderboardRecord(ProductModel):
    """STEP-0016 handoff schema; no official leaderboard is generated by STEP-0015P."""

    player_id: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    distribution_ref: str = Field(min_length=1)
    distribution_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    overall_center: float | None = Field(default=None, ge=0, le=100)
    overall_center_label: Literal["DIAGNOSTIC_SUMMARY"] | None = None
    overall_lower_80: float = Field(ge=0, le=100)
    overall_upper_80: float = Field(ge=0, le=100)
    overall_lower_90: float = Field(ge=0, le=100)
    overall_upper_90: float = Field(ge=0, le=100)
    median_rank: float = Field(ge=1)
    rank_lower_50: float = Field(ge=1)
    rank_upper_50: float = Field(ge=1)
    rank_lower_80: float = Field(ge=1)
    rank_upper_80: float = Field(ge=1)
    rank_lower_90: float = Field(ge=1)
    rank_upper_90: float = Field(ge=1)
    rank_lower_95: float = Field(ge=1)
    rank_upper_95: float = Field(ge=1)
    top_10_probability: float = Field(ge=0, le=1)
    top_25_probability: float = Field(ge=0, le=1)
    top_50_probability: float = Field(ge=0, le=1)
    top_100_probability: float = Field(ge=0, le=1)
    ranking_status: RankingStatus
    overall_source_status: str = Field(min_length=1)
    display_position: int | None = Field(default=None, ge=1)
    display_position_semantics: Literal["NAVIGATIONAL_MEDIAN_RANK_SORT"] | None = None
    peak: DimensionDisplay
    longevity: DimensionDisplay
    offense: DimensionDisplay
    defense: DimensionDisplay
    playoffs: DimensionDisplay
    accolades: DimensionDisplay
    winning: DimensionDisplay
    career_state: Literal["ACTIVE", "RETIRED", "UNKNOWN"]
    active_career_policy: Literal["TO_DATE_NO_PROJECTION"]
    cutoff_season: Literal["2025-26"]
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]
    overall_substrate_version: Literal["goatlab-v1-overall-v2-tiered"]
    dimension_methodology_versions: dict[str, str]
    conditional_on_frozen_measurement_architecture: Literal[True]
    shared_cross_player_calibration_uncertainty_modeled: Literal[False]
    uncertainty_quality_penalty_applied: Literal[False]
    overall_point_claimed_exact: Literal[False]

    @model_validator(mode="after")
    def check_publication_contract(self) -> PlayerLeaderboardRecord:
        if self.ranking_status == RankingStatus.UNAVAILABLE:
            raise ValueError("unavailable player cannot enter a leaderboard")
        if self.ranking_status != ranking_status(
            self.overall_source_status, distribution_available=True
        ):
            raise ValueError("ranking status disagrees with Overall evidence status")
        if (self.display_position is None) != (self.display_position_semantics is None):
            raise ValueError("display position must be labeled navigational")
        if (self.overall_center is None) != (self.overall_center_label is None):
            raise ValueError("diagnostic Overall center must be explicitly labeled")
        if not (
            self.overall_lower_90
            <= self.overall_lower_80
            <= self.overall_upper_80
            <= self.overall_upper_90
        ):
            raise ValueError("Overall interval bounds must be nested")
        if self.overall_center is not None and not (
            self.overall_lower_90 <= self.overall_center <= self.overall_upper_90
        ):
            raise ValueError("Overall center must lie in its 90% range")
        if not (
            self.rank_lower_95
            <= self.rank_lower_90
            <= self.rank_lower_80
            <= self.rank_lower_50
            <= self.median_rank
            <= self.rank_upper_50
            <= self.rank_upper_80
            <= self.rank_upper_90
            <= self.rank_upper_95
        ):
            raise ValueError("rank bands must be nested around median rank")
        if not (
            self.top_10_probability
            <= self.top_25_probability
            <= self.top_50_probability
            <= self.top_100_probability
        ):
            raise ValueError("Top-N probabilities must be nondecreasing")
        expected = {"peak", "longevity", "offense", "defense", "playoffs", "accolades", "winning"}
        if set(self.dimension_methodology_versions) != expected:
            raise ValueError("all seven dimension methodology versions are required")
        if any(not version for version in self.dimension_methodology_versions.values()):
            raise ValueError("dimension methodology versions cannot be empty")
        return self


class UnrankedPlayerRecord(ProductModel):
    """Insufficient-evidence listing, intentionally distinct from a leaderboard entry."""

    player_id: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    ranking_status: Literal[RankingStatus.UNAVAILABLE]
    overall_source_status: Literal["OVERALL_UNAVAILABLE"]
    reason_codes: tuple[str, ...] = Field(min_length=1)
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]


class PairwiseComparison(ProductModel):
    player_a_id: str = Field(min_length=1)
    player_b_id: str = Field(min_length=1)
    player_a_ranking_status: RankingStatus
    player_b_ranking_status: RankingStatus
    probability_a_above_b: float = Field(ge=0, le=1)
    ordering_label: PairwiseOrder
    dimension_comparison: dict[str, tuple[DimensionDisplay, DimensionDisplay]]
    uncertainty_context: str = Field(min_length=1)
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]
    overall_substrate_version: Literal["goatlab-v1-overall-v2-tiered"]
    conditional_on_frozen_measurement_architecture: Literal[True]

    @model_validator(mode="after")
    def check_comparison(self) -> PairwiseComparison:
        if self.player_a_id == self.player_b_id:
            raise ValueError("pairwise comparison requires distinct players")
        if RankingStatus.UNAVAILABLE in (
            self.player_a_ranking_status,
            self.player_b_ranking_status,
        ):
            raise ValueError("unavailable player cannot enter a pairwise comparison")
        if self.ordering_label != pairwise_order(self.probability_a_above_b):
            raise ValueError("ordering label does not match probability")
        if set(self.dimension_comparison) != {
            "peak",
            "longevity",
            "offense",
            "defense",
            "playoffs",
            "accolades",
            "winning",
        }:
            raise ValueError("pairwise comparison requires all seven dimensions")
        return self
