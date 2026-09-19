"""Typed, secret-safe runtime configuration for the read-only ranking API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from goatlab.product.loading import FROZEN_RELEASE_FINGERPRINT, FROZEN_RELEASE_ID


class ProductSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["local", "test", "production"] = "local"
    backend_mode: Literal["artifact", "postgres"] = "artifact"
    database_url: str | None = Field(default=None, repr=False)
    product_artifact_root: Path = Path(__file__).resolve().parents[3] / "data/product"
    release_id: str = FROZEN_RELEASE_ID
    expected_release_fingerprint: str = FROZEN_RELEASE_FINGERPRINT
    allowed_cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    draw_cache_enabled: bool = True

    @model_validator(mode="after")
    def check_configuration(self) -> ProductSettings:
        if self.backend_mode == "postgres" and not self.database_url:
            raise ValueError("DATABASE_URL is required in PostgreSQL mode")
        if self.environment == "production" and "*" in self.allowed_cors_origins:
            raise ValueError("wildcard CORS origin is forbidden in production")
        if not self.release_id:
            raise ValueError("ranking release ID is required")
        if len(self.expected_release_fingerprint) != 64:
            raise ValueError("expected release fingerprint must be SHA-256")
        return self

    @property
    def release_dir(self) -> Path:
        return self.product_artifact_root / self.release_id

    @classmethod
    def from_environment(cls) -> ProductSettings:
        origins = os.getenv("GOATLAB_ALLOWED_CORS_ORIGINS", "http://localhost:3000")
        return cls(
            environment=cast(
                Literal["local", "test", "production"],
                os.getenv("GOATLAB_ENVIRONMENT", "local"),
            ),
            backend_mode=cast(
                Literal["artifact", "postgres"],
                os.getenv("GOATLAB_BACKEND_MODE", "artifact"),
            ),
            database_url=os.getenv("DATABASE_URL"),
            product_artifact_root=Path(
                os.getenv(
                    "GOATLAB_PRODUCT_ARTIFACT_ROOT",
                    str(Path(__file__).resolve().parents[3] / "data/product"),
                )
            ),
            release_id=os.getenv("GOATLAB_RELEASE_ID", FROZEN_RELEASE_ID),
            expected_release_fingerprint=os.getenv(
                "GOATLAB_RELEASE_FINGERPRINT", FROZEN_RELEASE_FINGERPRINT
            ),
            allowed_cors_origins=tuple(
                origin.strip() for origin in origins.split(",") if origin.strip()
            ),
            draw_cache_enabled=os.getenv("GOATLAB_DRAW_CACHE_ENABLED", "true").lower()
            not in {"false", "0", "no"},
        )
