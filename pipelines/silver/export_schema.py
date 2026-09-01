"""Export the current Pydantic canonical contracts as deterministic JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

from goatlab.schemas import (
    FinalsGame,
    Franchise,
    Game,
    MetricCoverage,
    Player,
    PlayerAward,
    PlayerGameStats,
    PlayerSeasonAdvanced,
    PlayerSeasonStats,
    PlayerTeamSeasonParticipation,
    Season,
    Team,
    TeamSeasonResult,
)

OUTPUT_PATH = Path("docs/data/canonical-schema-v3.json")
MODELS = (
    Player,
    Season,
    Franchise,
    Team,
    Game,
    PlayerGameStats,
    PlayerSeasonStats,
    PlayerSeasonAdvanced,
    PlayerAward,
    MetricCoverage,
    TeamSeasonResult,
    FinalsGame,
    PlayerTeamSeasonParticipation,
)


def main() -> None:
    payload = {
        "schema_version": 3,
        "entities": {model.__name__: model.model_json_schema() for model in MODELS},
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
