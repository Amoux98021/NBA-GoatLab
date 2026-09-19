"""Fingerprint-verified, once-loaded paired Overall/rank draws outside PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from goatlab.product.models import RankingRelease

LOGGER = logging.getLogger(__name__)


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


class PairedDrawStore:
    def __init__(
        self,
        release_dir: Path,
        *,
        expected_release_id: str,
        expected_release_fingerprint: str,
        cache_pairs: bool = True,
    ) -> None:
        self.release_dir = release_dir
        manifest_dict = json.loads((release_dir / "ranking-release-manifest.json").read_text())
        fingerprint = manifest_dict.pop("release_fingerprint")
        if (
            hashlib.sha256(_canonical_json(manifest_dict)).hexdigest() != fingerprint
            or fingerprint != expected_release_fingerprint
        ):
            raise ValueError("paired-draw release fingerprint differs")
        self.release = RankingRelease.model_validate(
            {**manifest_dict, "release_fingerprint": fingerprint}
        )
        if self.release.release_id != expected_release_id:
            raise ValueError("paired-draw release ID differs")
        self.path = release_dir / "paired-overall-rank-draws.npz"
        self.expected_draw_hash = self.release.artifact_sha256[self.path.name]
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.expected_draw_hash:
            raise ValueError("paired-draw artifact fingerprint differs")
        self._lock = Lock()
        self._overall: np.ndarray | None = None
        self._ranks: np.ndarray | None = None
        self._index: dict[str, int] | None = None
        self._cache_pairs = cache_pairs
        self._pair_cache: OrderedDict[tuple[str, str], tuple[float, float]] = OrderedDict()
        self._pair_lock = Lock()
        LOGGER.info("paired-draw artifact verified release_id=%s", self.release.release_id)

    @property
    def state(self) -> str:
        return "LOADED" if self._overall is not None else "VERIFIED_NOT_LOADED"

    def _load(self) -> None:
        if self._overall is not None:
            return
        with self._lock:
            if self._overall is not None:
                return
            if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.expected_draw_hash:
                raise ValueError("paired-draw artifact changed after startup verification")
            with np.load(self.path, allow_pickle=False) as content:
                ids = [str(value) for value in content["player_ids"].tolist()]
                overall = content["overall_draws"].copy()
                ranks = content["rank_draws"].copy()
            if (
                len(ids) != self.release.rankable_count
                or len(set(ids)) != len(ids)
                or overall.shape != ranks.shape
                or overall.shape != (self.release.rankable_count, 2500)
                or not np.isfinite(overall).all()
            ):
                raise ValueError("paired-draw population or arrays differ")
            self._index = {player_id: index for index, player_id in enumerate(ids)}
            self._overall = overall
            self._ranks = ranks
            LOGGER.info("paired-draw artifact loaded release_id=%s", self.release.release_id)

    def _uncached_pair(self, smaller: str, larger: str) -> tuple[float, float]:
        self._load()
        assert self._overall is not None and self._index is not None
        try:
            a = self._overall[self._index[smaller]]
            b = self._overall[self._index[larger]]
        except KeyError as error:
            raise LookupError("player has no paired Overall distribution") from error
        ties = float(np.mean(a == b))
        first = float(np.mean(a > b) + 0.5 * ties)
        return first, ties

    def _cached_pair(self, smaller: str, larger: str) -> tuple[float, float]:
        key = (smaller, larger)
        with self._pair_lock:
            if key in self._pair_cache:
                self._pair_cache.move_to_end(key)
                return self._pair_cache[key]
        value = self._uncached_pair(smaller, larger)
        with self._pair_lock:
            self._pair_cache[key] = value
            self._pair_cache.move_to_end(key)
            if len(self._pair_cache) > 4096:
                self._pair_cache.popitem(last=False)
        return value

    def pair_probability(self, player_a: str, player_b: str) -> tuple[float, float, float]:
        if player_a == player_b:
            raise ValueError("cannot compare a player with himself")
        smaller, larger = sorted((player_a, player_b))
        probability, ties = (
            self._cached_pair(smaller, larger)
            if self._cache_pairs
            else self._uncached_pair(smaller, larger)
        )
        probability_a = probability if player_a == smaller else 1.0 - probability
        return probability_a, 1.0 - probability_a, ties

    def health(self) -> dict[str, Any]:
        return {
            "release_id": self.release.release_id,
            "artifact_state": self.state,
            "fingerprint_verified": True,
            "rankable_players": self.release.rankable_count,
        }
