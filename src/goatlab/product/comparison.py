"""HTTP-neutral assembly of frozen pairwise publication semantics."""

from __future__ import annotations

from goatlab.product.models import (
    LeaderboardEntry,
    PairwiseDimension,
    PairwiseResponse,
    PlayerProfile,
)
from goatlab.rankings.publication_policy import pairwise_order


def assemble_pairwise(
    player_a: PlayerProfile,
    player_b: PlayerProfile,
    probability_a: float,
    probability_b: float,
    tie_probability: float,
) -> PairwiseResponse:
    a: LeaderboardEntry | None = player_a.leaderboard
    b: LeaderboardEntry | None = player_b.leaderboard
    if a is None or b is None:
        raise LookupError("pairwise comparison requires two distribution-rankable players")
    if a.release_id != b.release_id:
        raise ValueError("cannot compare players from different releases")
    dimensions: dict[str, PairwiseDimension] = {}
    for key, a_dimension in player_a.dimensions.items():
        b_dimension = player_b.dimensions[key]
        difference = (
            a_dimension.diagnostic_center - b_dimension.diagnostic_center
            if a_dimension.diagnostic_center is not None
            and b_dimension.diagnostic_center is not None
            else None
        )
        dimensions[key] = PairwiseDimension(
            dimension=key,
            player_a=a_dimension,
            player_b=b_dimension,
            diagnostic_center_difference=difference,
        )
    return PairwiseResponse(
        release_id=a.release_id,
        player_a_id=a.player_id,
        player_b_id=b.player_id,
        probability_a_above_b=probability_a,
        probability_b_above_a=probability_b,
        tie_probability=tie_probability,
        ordering_label=pairwise_order(probability_a),
        player_a_overall=a.overall,
        player_b_overall=b.overall,
        player_a_rank=a.rank,
        player_b_rank=b.rank,
        overall_90_ranges_overlap=(
            a.overall.lower_90 <= b.overall.upper_90 and b.overall.lower_90 <= a.overall.upper_90
        ),
        dimensions=dimensions,
        uncertainty_context="CONDITIONAL_ON_FROZEN_MEASUREMENT_ARCHITECTURE",
        ranking_policy_version="goatlab-v1-ranking-policy-v2-probabilistic",
    )
