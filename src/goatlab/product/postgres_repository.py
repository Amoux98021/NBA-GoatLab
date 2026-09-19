"""PostgreSQL-backed read-only adapter for an immutable ranking release."""

from __future__ import annotations

from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

from goatlab.product.comparison import assemble_pairwise
from goatlab.product.draw_store import PairedDrawStore
from goatlab.product.models import LeaderboardEntry, PairwiseResponse, PlayerProfile, RankingRelease
from goatlab.product.repository import normalized_search_name
from goatlab.product.settings import ProductSettings


class PostgresRankingRepository:
    """Indexed summaries/profiles in PostgreSQL; aligned draws remain in file storage."""

    def __init__(self, settings: ProductSettings) -> None:
        if settings.backend_mode != "postgres" or settings.database_url is None:
            raise ValueError("PostgreSQL repository requires database settings")
        self.settings = settings
        self.database_url = settings.database_url
        self.draw_store = PairedDrawStore(
            settings.release_dir,
            expected_release_id=settings.release_id,
            expected_release_fingerprint=settings.expected_release_fingerprint,
            cache_pairs=settings.draw_cache_enabled,
        )
        release = self.get_release()
        if release.release_fingerprint != settings.expected_release_fingerprint:
            raise ValueError("configured DB release fingerprint differs from draw artifact")
        self.release = release

    def get_release(self) -> RankingRelease:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT manifest_json, release_fingerprint FROM ranking_versions "
                "WHERE release_id = %s",
                (self.settings.release_id,),
            ).fetchone()
        if row is None:
            raise LookupError("configured ranking release is not present in PostgreSQL")
        release = RankingRelease.model_validate(row["manifest_json"])
        if release.release_fingerprint != row["release_fingerprint"]:
            raise ValueError("stored release manifest and fingerprint differ")
        return release

    def get_releases(self) -> list[RankingRelease]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT manifest_json FROM ranking_versions ORDER BY generated_at_utc, release_id"
            ).fetchall()
        return [RankingRelease.model_validate(row["manifest_json"]) for row in rows]

    def get_methodology(self) -> dict[str, Any]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT methodology_json FROM ranking_versions WHERE release_id = %s",
                (self.settings.release_id,),
            ).fetchone()
        if row is None:
            raise LookupError("configured ranking release is not present")
        return cast(dict[str, Any], row["methodology_json"])

    @staticmethod
    def _filters(
        search: str | None, active: bool | None, status: str | None
    ) -> tuple[str, list[Any]]:
        clauses = ["r.release_id = %s"]
        values: list[Any] = []
        query = normalized_search_name(search or "")
        if query:
            clauses.append("p.search_name LIKE %s")
            values.append(f"%{query}%")
        if active is not None:
            clauses.append("p.career_state = %s")
            values.append("ACTIVE" if active else "RETIRED")
        if status is not None:
            clauses.append("r.ranking_status = %s")
            values.append(status)
        return " AND ".join(clauses), values

    def get_leaderboard(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
        active: bool | None = None,
        status: str | None = None,
    ) -> list[LeaderboardEntry]:
        if limit < 0 or offset < 0 or limit > self.release.rankable_count:
            raise ValueError("invalid pagination")
        where, extra = self._filters(search, active, status)
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT q.profile_json->'leaderboard' AS entry "
                "FROM player_rankings r "
                "JOIN players p ON (p.release_id, p.player_id) = (r.release_id, r.player_id) "
                "JOIN player_profiles q ON (q.release_id, q.player_id) = "
                "(r.release_id, r.player_id) "
                f"WHERE {where} ORDER BY r.display_position LIMIT %s OFFSET %s",
                (self.settings.release_id, *extra, limit, offset),
            ).fetchall()
        return [LeaderboardEntry.model_validate(row["entry"]) for row in rows]

    def count_leaderboard(
        self,
        *,
        search: str | None = None,
        active: bool | None = None,
        status: str | None = None,
    ) -> int:
        where, extra = self._filters(search, active, status)
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT count(*) AS n FROM player_rankings r "
                "JOIN players p ON (p.release_id, p.player_id) = (r.release_id, r.player_id) "
                f"WHERE {where}",
                (self.settings.release_id, *extra),
            ).fetchone()
        assert row is not None
        return int(row["n"])

    def get_top100(self) -> list[dict[str, Any]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM top100_entries WHERE release_id = %s "
                "ORDER BY display_position",
                (self.settings.release_id,),
            ).fetchall()
        if len(rows) != 100:
            raise ValueError("PostgreSQL Top-100 view is incomplete")
        return [cast(dict[str, Any], row["payload_json"]) for row in rows]

    def get_player(self, player_id: str) -> PlayerProfile | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT profile_json FROM player_profiles WHERE release_id = %s AND player_id = %s",
                (self.settings.release_id, player_id),
            ).fetchone()
        return PlayerProfile.model_validate(row["profile_json"]) if row is not None else None

    def compare_players(self, player_a: str, player_b: str) -> PairwiseResponse:
        if player_a == player_b:
            raise ValueError("cannot compare a player with himself")
        profile_a = self.get_player(player_a)
        profile_b = self.get_player(player_b)
        if profile_a is None or profile_b is None:
            raise LookupError("unknown canonical player ID")
        if profile_a.leaderboard is None or profile_b.leaderboard is None:
            raise LookupError("pairwise comparison requires two distribution-rankable players")
        probability_a, probability_b, ties = self.draw_store.pair_probability(player_a, player_b)
        return assemble_pairwise(profile_a, profile_b, probability_a, probability_b, ties)

    def health(self) -> dict[str, Any]:
        try:
            with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
                row = connection.execute(
                    "SELECT release_fingerprint FROM ranking_versions WHERE release_id = %s",
                    (self.settings.release_id,),
                ).fetchone()
            present = (
                row is not None and row["release_fingerprint"] == self.release.release_fingerprint
            )
            return {
                "database_accessible": True,
                "configured_release_present": present,
                "draw_artifact_state": self.draw_store.state,
            }
        except psycopg.Error:
            return {
                "database_accessible": False,
                "configured_release_present": False,
                "draw_artifact_state": self.draw_store.state,
            }
