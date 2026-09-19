"""Artifact-backed, read-only service for a fingerprinted ranking release."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, cast

import numpy as np

from goatlab.product.models import (
    LeaderboardEntry,
    PairwiseDimension,
    PairwiseResponse,
    PlayerProfile,
    RankingRelease,
)
from goatlab.rankings.publication_policy import pairwise_order


def normalized_search_name(value: str) -> str:
    """Deterministic search token; never an identity key or a fuzzy merge."""

    normalized = unicodedata.normalize("NFKD", value).casefold()
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in ascii_text).split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RankingRepository:
    """Serves immutable summaries; loads paired draws lazily for pairwise requests."""

    def __init__(self, release_dir: Path) -> None:
        self.release_dir = release_dir
        manifest = json.loads((release_dir / "ranking-release-manifest.json").read_text())
        self.release = RankingRelease.model_validate(manifest)
        for relative_path, fingerprint in self.release.artifact_sha256.items():
            if _sha256(release_dir / relative_path) != fingerprint:
                raise ValueError(f"immutable release artifact differs: {relative_path}")
        entries = json.loads((release_dir / "leaderboard.json").read_text())
        self._leaderboard = [LeaderboardEntry.model_validate(item) for item in entries]
        self._by_id = {entry.player_id: entry for entry in self._leaderboard}
        if len(self._by_id) != self.release.rankable_count:
            raise ValueError("leaderboard count or player identity is invalid")
        self._profiles: dict[str, PlayerProfile] | None = None
        self._draws: np.ndarray | None = None
        self._draw_index: dict[str, int] | None = None

    def get_leaderboard(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        active: bool | None = None,
        status: str | None = None,
    ) -> list[LeaderboardEntry]:
        if limit < 0 or offset < 0 or limit > 1882:
            raise ValueError("invalid pagination")
        query = normalized_search_name(search or "")
        rows = self._leaderboard
        if query:
            rows = [row for row in rows if query in normalized_search_name(row.player_name)]
        if active is not None:
            rows = [row for row in rows if row.active is active]
        if status is not None:
            rows = [row for row in rows if row.ranking_status.value == status]
        return rows[offset : offset + limit]

    def _load_profiles(self) -> None:
        if self._profiles is None:
            path = self.release_dir / "player-profiles.jsonl"
            rows = [
                PlayerProfile.model_validate_json(line) for line in path.read_text().splitlines()
            ]
            self._profiles = {row.identity.player_id: row for row in rows}
            if len(self._profiles) != self.release.player_count:
                raise ValueError("profile count or identity is invalid")

    def get_player(self, player_id: str) -> PlayerProfile | None:
        self._load_profiles()
        assert self._profiles is not None
        return self._profiles.get(player_id)

    def get_release(self) -> RankingRelease:
        return self.release

    def get_methodology(self) -> dict[str, Any]:
        return cast(
            dict[str, Any], json.loads((self.release_dir / "methodology-metadata.json").read_text())
        )

    def _load_draws(self) -> None:
        if self._draws is None:
            with np.load(
                self.release_dir / "paired-overall-rank-draws.npz", allow_pickle=False
            ) as data:
                ids = data["player_ids"].tolist()
                self._draws = data["overall_draws"].copy()
            self._draw_index = {player_id: index for index, player_id in enumerate(ids)}
            if len(self._draw_index) != self.release.rankable_count:
                raise ValueError("serving distribution IDs do not match release")

    def compare_players(self, player_a: str, player_b: str) -> PairwiseResponse:
        if player_a == player_b:
            raise ValueError("cannot compare a player with himself")
        a, b = self._by_id.get(player_a), self._by_id.get(player_b)
        if a is None or b is None:
            raise LookupError("pairwise comparison requires two distribution-rankable players")
        self._load_draws()
        self._load_profiles()
        assert self._draws is not None and self._draw_index is not None
        assert self._profiles is not None
        a_draw = self._draws[self._draw_index[player_a]]
        b_draw = self._draws[self._draw_index[player_b]]
        ties = float(np.mean(a_draw == b_draw))
        # A tied draw is an indeterminate ordering; split it symmetrically for
        # a complementary pairwise request without changing either quality draw.
        probability_a = float(np.mean(a_draw > b_draw) + 0.5 * ties)
        probability_b = 1.0 - probability_a
        dimensions: dict[str, PairwiseDimension] = {}
        for key, a_dim in self._profiles[player_a].dimensions.items():
            b_dim = self._profiles[player_b].dimensions[key]
            difference = (
                a_dim.diagnostic_center - b_dim.diagnostic_center
                if a_dim.diagnostic_center is not None and b_dim.diagnostic_center is not None
                else None
            )
            dimensions[key] = PairwiseDimension(
                dimension=key,
                player_a=a_dim,
                player_b=b_dim,
                diagnostic_center_difference=difference,
            )
        return PairwiseResponse(
            release_id=self.release.release_id,
            player_a_id=player_a,
            player_b_id=player_b,
            probability_a_above_b=probability_a,
            probability_b_above_a=probability_b,
            tie_probability=ties,
            ordering_label=pairwise_order(probability_a),
            player_a_overall=a.overall,
            player_b_overall=b.overall,
            player_a_rank=a.rank,
            player_b_rank=b.rank,
            overall_90_ranges_overlap=(
                a.overall.lower_90 <= b.overall.upper_90
                and b.overall.lower_90 <= a.overall.upper_90
            ),
            dimensions=dimensions,
            uncertainty_context="CONDITIONAL_ON_FROZEN_MEASUREMENT_ARCHITECTURE",
            ranking_policy_version="goatlab-v1-ranking-policy-v2-probabilistic",
        )
