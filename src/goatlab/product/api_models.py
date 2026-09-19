"""Stable FastAPI response envelopes around STEP-0016 domain models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from goatlab.product.models import LeaderboardEntry, RankingRelease
from goatlab.rankings.publication_policy import RankingStatus, Top100Membership


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(APIModel):
    status: Literal["OK", "DEGRADED"]
    release_id: str
    database_accessible: bool | None
    configured_release_present: bool
    draw_artifact_state: Literal["VERIFIED_NOT_LOADED", "LOADED"]
    publication_rights_gate: Literal["PUBLICATION_RIGHTS_REVIEW_REQUIRED"]


class ReleasesResponse(APIModel):
    releases: list[RankingRelease]


class LeaderboardPage(APIModel):
    release_id: str
    total: int = Field(ge=0)
    limit: int = Field(ge=0)
    offset: int = Field(ge=0)
    entries: list[LeaderboardEntry]


class Top100Entry(APIModel):
    active: bool | None
    cutoff_season: Literal["2025-26"]
    display_position: int = Field(ge=1, le=100)
    display_position_semantics: Literal["NAVIGATIONAL_MEDIAN_RANK_SORT"]
    median_rank: float = Field(ge=1)
    overall_center: float | None = Field(default=None, ge=0, le=100)
    overall_center_semantics: Literal["DIAGNOSTIC_SUMMARY"] | None
    overall_lower_90: float = Field(ge=0, le=100)
    overall_upper_90: float = Field(ge=0, le=100)
    player_id: str
    player_name: str
    rank_lower_80: float = Field(ge=1)
    rank_lower_90: float = Field(ge=1)
    rank_upper_80: float = Field(ge=1)
    rank_upper_90: float = Field(ge=1)
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]
    ranking_status: RankingStatus
    release_id: str
    top100_membership: Top100Membership
    top_100_probability: float = Field(ge=0, le=1)
    top_10_probability: float = Field(ge=0, le=1)
    top_25_probability: float = Field(ge=0, le=1)
    top_50_probability: float = Field(ge=0, le=1)


class Top100Response(APIModel):
    release_id: str
    entries: list[Top100Entry]


class MethodologyResponse(APIModel):
    release_id: str
    cutoff_season: Literal["2025-26"]
    ranking_policy_version: Literal["goatlab-v1-ranking-policy-v2-probabilistic"]
    overall_substrate_version: Literal["goatlab-v1-overall-v2-tiered"]
    exact_overall_point_promoted: Literal[False]
    dimension_methodology_versions: dict[str, str]
    disclosures: dict[str, str]
    active_career_policy: Literal["TO_DATE_NO_PROJECTION"]
    publication_rights_gate: Literal["PUBLICATION_RIGHTS_REVIEW_REQUIRED"]
    additional_public_context: dict[str, Any] = Field(default_factory=dict)
