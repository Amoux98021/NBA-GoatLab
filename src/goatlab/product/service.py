"""Small read-only service interface shared by artifact and PostgreSQL adapters."""

from __future__ import annotations

from typing import Any, Protocol

from goatlab.product.models import LeaderboardEntry, PairwiseResponse, PlayerProfile, RankingRelease


class RankingServingRepository(Protocol):
    def get_release(self) -> RankingRelease: ...

    def get_releases(self) -> list[RankingRelease]: ...

    def get_methodology(self) -> dict[str, Any]: ...

    def get_leaderboard(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        active: bool | None = None,
        status: str | None = None,
    ) -> list[LeaderboardEntry]: ...

    def count_leaderboard(
        self,
        *,
        search: str | None = None,
        active: bool | None = None,
        status: str | None = None,
    ) -> int: ...

    def get_top100(self) -> list[dict[str, Any]]: ...

    def get_player(self, player_id: str) -> PlayerProfile | None: ...

    def compare_players(self, player_a: str, player_b: str) -> PairwiseResponse: ...

    def health(self) -> dict[str, Any]: ...
