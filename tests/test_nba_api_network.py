import os
from pathlib import Path

import pytest

from goatlab.data.nba_api_client import NBAAPIClient, RequestOutcome, ResponseCache
from goatlab.data.nba_api_probe import player_game_logs_spec


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("GOATLAB_RUN_NETWORK_TESTS") != "1",
    reason="set GOATLAB_RUN_NETWORK_TESTS=1 for the opt-in live smoke test",
)
def test_live_player_game_logs_smoke(tmp_path: Path) -> None:
    result = NBAAPIClient(ResponseCache(tmp_path), max_attempts=1).execute(
        player_game_logs_spec("2022-23", "Regular Season")
    )
    assert result.outcome is RequestOutcome.SUCCESS_WITH_ROWS
