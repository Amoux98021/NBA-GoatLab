"""Thin, read-only FastAPI adapter for a frozen probabilistic ranking release."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from goatlab.product.api_models import (
    HealthResponse,
    LeaderboardPage,
    MethodologyResponse,
    ReleasesResponse,
    Top100Entry,
    Top100Response,
)
from goatlab.product.models import PairwiseResponse, PlayerProfile, RankingRelease
from goatlab.product.postgres_repository import PostgresRankingRepository
from goatlab.product.repository import RankingRepository
from goatlab.product.service import RankingServingRepository
from goatlab.product.settings import ProductSettings

LOGGER = logging.getLogger(__name__)
StatusFilter = Literal["OFFICIAL", "PROVISIONAL", "INTERVAL_NATIVE"]


def get_repository(request: Request) -> RankingServingRepository:
    return cast(RankingServingRepository, request.app.state.ranking_repository)


RepositoryDependency = Annotated[RankingServingRepository, Depends(get_repository)]


def create_app(
    settings: ProductSettings | None = None,
    *,
    repository: RankingServingRepository | None = None,
) -> FastAPI:
    config = settings or ProductSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        LOGGER.info(
            "GOATLab API starting backend=%s release_id=%s", config.backend_mode, config.release_id
        )
        try:
            serving = repository or (
                PostgresRankingRepository(config)
                if config.backend_mode == "postgres"
                else RankingRepository(config.release_dir)
            )
            release = serving.get_release()
            if (
                release.release_id != config.release_id
                or release.release_fingerprint != config.expected_release_fingerprint
            ):
                raise ValueError("configured ranking release fingerprint differs")
            top100 = serving.get_top100()
            if len(top100) != 100 or [row["display_position"] for row in top100] != list(
                range(1, 101)
            ):
                raise ValueError("configured Top-100 view is incomplete")
            app.state.ranking_repository = serving
            LOGGER.info("GOATLab release loaded release_id=%s", release.release_id)
            yield
        except Exception:
            LOGGER.exception("GOATLab API startup failed release_id=%s", config.release_id)
            raise
        finally:
            LOGGER.info("GOATLab API stopped release_id=%s", config.release_id)

    app = FastAPI(
        title="GOATLab Probabilistic Ranking API",
        version="1.0.0",
        description=(
            "Read-only, conditional probabilistic NBA ranking summaries. "
            "Display ranks are not exact truth."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    def check_release(requested: str | None) -> None:
        if requested is not None and requested != config.release_id:
            raise HTTPException(status_code=404, detail={"code": "UNKNOWN_RELEASE"})

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(repository: RepositoryDependency, response: Response) -> HealthResponse:
        state = repository.health()
        healthy = state["database_accessible"] is not False and state["configured_release_present"]
        if not healthy:
            response.status_code = 503
        return HealthResponse(
            status="OK" if healthy else "DEGRADED",
            release_id=config.release_id,
            database_accessible=state["database_accessible"],
            configured_release_present=state["configured_release_present"],
            draw_artifact_state=state["draw_artifact_state"],
            publication_rights_gate="PUBLICATION_RIGHTS_REVIEW_REQUIRED",
        )

    @app.get("/api/v1/releases", response_model=ReleasesResponse)
    def releases(repository: RepositoryDependency) -> ReleasesResponse:
        return ReleasesResponse(releases=repository.get_releases())

    @app.get("/api/v1/releases/{release_id}", response_model=RankingRelease)
    def release_detail(
        release_id: str,
        repository: RepositoryDependency,
    ) -> RankingRelease:
        for release in repository.get_releases():
            if release.release_id == release_id:
                return release
        raise HTTPException(status_code=404, detail={"code": "UNKNOWN_RELEASE"})

    @app.get("/api/v1/leaderboard", response_model=LeaderboardPage)
    def leaderboard(
        repository: RepositoryDependency,
        limit: int = Query(default=100, ge=0, le=1882),
        offset: int = Query(default=0, ge=0),
        search: str | None = None,
        active: bool | None = None,
        status: StatusFilter | None = None,
        release: str | None = None,
    ) -> LeaderboardPage:
        check_release(release)
        return LeaderboardPage(
            release_id=config.release_id,
            total=repository.count_leaderboard(search=search, active=active, status=status),
            limit=limit,
            offset=offset,
            entries=repository.get_leaderboard(
                limit=limit, offset=offset, search=search, active=active, status=status
            ),
        )

    @app.get("/api/v1/top100", response_model=Top100Response)
    def top100(repository: RepositoryDependency) -> Top100Response:
        return Top100Response(
            release_id=config.release_id,
            entries=[Top100Entry.model_validate(row) for row in repository.get_top100()],
        )

    @app.get("/api/v1/players/{player_id}", response_model=PlayerProfile)
    def player(
        player_id: str,
        repository: RepositoryDependency,
    ) -> PlayerProfile:
        profile = repository.get_player(player_id)
        if profile is None:
            raise HTTPException(status_code=404, detail={"code": "UNKNOWN_PLAYER"})
        return profile

    @app.get("/api/v1/compare/{player_a}/{player_b}", response_model=PairwiseResponse)
    def compare(
        player_a: str,
        player_b: str,
        repository: RepositoryDependency,
    ) -> PairwiseResponse:
        if player_a == player_b:
            raise HTTPException(status_code=400, detail={"code": "SAME_PLAYER"})
        first = repository.get_player(player_a)
        second = repository.get_player(player_b)
        missing = [
            player_id
            for player_id, profile in ((player_a, first), (player_b, second))
            if profile is None
        ]
        if missing:
            raise HTTPException(
                status_code=404, detail={"code": "UNKNOWN_PLAYER", "player_ids": missing}
            )
        unavailable = [
            player_id
            for player_id, profile in ((player_a, first), (player_b, second))
            if profile is not None and profile.leaderboard is None
        ]
        if unavailable:
            raise HTTPException(
                status_code=422,
                detail={"code": "COMPARISON_UNAVAILABLE", "player_ids": unavailable},
            )
        return repository.compare_players(player_a, player_b)

    @app.get("/api/v1/methodology", response_model=MethodologyResponse)
    def methodology(repository: RepositoryDependency) -> MethodologyResponse:
        source = repository.get_methodology()
        return MethodologyResponse(
            release_id=config.release_id,
            cutoff_season=source["cutoff_season"],
            ranking_policy_version=source["ranking_policy"]["policy_version"],
            overall_substrate_version=source["overall_substrate_version"],
            exact_overall_point_promoted=False,
            dimension_methodology_versions=source["dimension_methodology_versions"],
            disclosures=source["disclosures"],
            active_career_policy=source["active_career_policy"],
            publication_rights_gate="PUBLICATION_RIGHTS_REVIEW_REQUIRED",
        )

    return app


app = create_app()
