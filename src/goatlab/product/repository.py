"""Artifact-backed, read-only service for a fingerprinted ranking release."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, cast

from goatlab.product.comparison import assemble_pairwise
from goatlab.product.draw_store import PairedDrawStore
from goatlab.product.models import (
    LeaderboardEntry,
    PairwiseResponse,
    PlayerProfile,
    RankingRelease,
)


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
        self.draw_store = PairedDrawStore(
            release_dir,
            expected_release_id=self.release.release_id,
            expected_release_fingerprint=self.release.release_fingerprint,
        )

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

    def get_releases(self) -> list[RankingRelease]:
        return [self.release]

    def get_top100(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            json.loads((self.release_dir / "leaderboard-v2-probabilistic.json").read_text()),
        )

    def count_leaderboard(
        self,
        *,
        search: str | None = None,
        active: bool | None = None,
        status: str | None = None,
    ) -> int:
        return len(
            self.get_leaderboard(
                limit=self.release.rankable_count, search=search, active=active, status=status
            )
        )

    def health(self) -> dict[str, Any]:
        return {
            "database_accessible": None,
            "configured_release_present": True,
            "draw_artifact_state": self.draw_store.state,
        }

    def get_methodology(self) -> dict[str, Any]:
        return cast(
            dict[str, Any], json.loads((self.release_dir / "methodology-metadata.json").read_text())
        )

    def compare_players(self, player_a: str, player_b: str) -> PairwiseResponse:
        if player_a == player_b:
            raise ValueError("cannot compare a player with himself")
        a, b = self._by_id.get(player_a), self._by_id.get(player_b)
        if a is None or b is None:
            raise LookupError("pairwise comparison requires two distribution-rankable players")
        self._load_profiles()
        assert self._profiles is not None
        probability_a, probability_b, ties = self.draw_store.pair_probability(player_a, player_b)
        return assemble_pairwise(
            self._profiles[player_a], self._profiles[player_b], probability_a, probability_b, ties
        )
