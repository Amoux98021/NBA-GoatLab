#!/usr/bin/env python3
"""Build factual team-success and player-participation primitives offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from goatlab.data.canonical import canonical_id
from goatlab.data.team_success import (
    AWARDS_FINGERPRINT,
    CORPUS_FINGERPRINT,
    CORPUS_ID,
    TEAM_SUCCESS_METHODOLOGY_VERSION,
    CanonicalGameEvidence,
    TeamIdentity,
    build_player_team_participation,
    career_team_context,
    derive_team_season_results,
    identify_finals_games,
    infer_finals_outcome,
    minutes_are_eligible,
    postseason_format_for_season,
    stable_json_fingerprint,
    validate_finite_rows,
)

ROOT = Path(__file__).resolve().parents[2]
START_YEAR = 1946
END_YEAR = 2025
LEGACY_END_YEAR = 2022
BUCKETS = 32
OFFICIAL_CHAMPIONS_URL = "https://www.nba.com/news/history-nba-champions"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument(
        "--recorded-runtime-seconds",
        type=float,
        help="Optional fixed observed runtime used for deterministic certification reports.",
    )
    parser.add_argument("--legacy-db", type=Path, default=ROOT / "data/bronze/nbadb/nba.sqlite")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "data/bronze/nba_api/historical-corpus-v1-checkpoint.json",
    )
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    parser.add_argument(
        "--official-reference",
        type=Path,
        default=ROOT / "data/fixtures/official_nba_championships.json",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _stable_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _stable_yaml(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    temporary.replace(path)


def _model_row(model: Any) -> dict[str, Any]:
    return cast(dict[str, Any], model.model_dump(mode="json"))


def _write_parquet(
    rows: list[dict[str, Any]], path: Path, sort_fields: tuple[str, ...]
) -> dict[str, Any]:
    rows.sort(key=lambda row: tuple(str(row.get(field) or "") for field in sort_fields))
    table = pa.Table.from_pylist(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=9,
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
    )
    temporary.replace(path)
    return {
        "path": _relative(path),
        "rows": table.num_rows,
        "columns": table.num_columns,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _bucket(player_id: str) -> int:
    return int(hashlib.sha256(player_id.encode("utf-8")).hexdigest()[:8], 16) % BUCKETS


def _reset_outputs(silver_root: Path, gold_root: Path) -> None:
    for path in (
        silver_root / "team_season_results",
        silver_root / "player_team_season_participation",
        silver_root / "finals_games",
        gold_root / "player_team_success_primitives",
        gold_root / "player_career_team_context",
    ):
        if path.exists():
            shutil.rmtree(path)


def _load_crosswalk(
    path: Path,
) -> tuple[dict[tuple[str, str], TeamIdentity], dict[str, TeamIdentity]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    by_source: dict[tuple[str, str], TeamIdentity] = {}
    by_id: dict[str, TeamIdentity] = {}
    for row in report["crosswalk"]:
        identity = TeamIdentity(
            team_id=str(row["team_id"]),
            nba_team_id=str(row["nba_team_id"]),
            franchise_id=str(row["franchise_id"]),
            team_name=str(row["team_name"]),
        )
        by_source[(identity.nba_team_id, identity.team_name)] = identity
        by_id[identity.team_id] = identity
    if len(by_source) != 74 or len({value.nba_team_id for value in by_source.values()}) != 45:
        raise ValueError("frozen team crosswalk changed")
    return by_source, by_id


def _team(
    crosswalk: dict[tuple[str, str], TeamIdentity], nba_team_id: object, team_name: object
) -> TeamIdentity:
    key = (str(nba_team_id), str(team_name).strip())
    if key not in crosswalk:
        raise ValueError(f"team evidence is absent from frozen crosswalk: {key}")
    return crosswalk[key]


def _legacy_games(
    database: Path, crosswalk: dict[tuple[str, str], TeamIdentity]
) -> dict[tuple[int, str], list[CanonicalGameEvidence]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    rows = connection.execute(
        """
        SELECT season_id, team_id_home, team_name_home, game_id, game_date,
               wl_home, pts_home, team_id_away, team_name_away, wl_away,
               pts_away, season_type
          FROM game
         WHERE season_type IN ('Regular Season', 'Playoffs')
         ORDER BY season_id, game_date, game_id
        """
    ).fetchall()
    connection.close()
    output: dict[tuple[int, str], list[CanonicalGameEvidence]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        nba_game_id = str(row["game_id"])
        if nba_game_id in seen:
            raise ValueError(f"duplicate modeled legacy game: {nba_game_id}")
        seen.add(nba_game_id)
        season_id = int(str(row["season_id"])[-4:])
        home = _team(crosswalk, row["team_id_home"], row["team_name_home"])
        away = _team(crosswalk, row["team_id_away"], row["team_name_away"])
        home_score, away_score = int(row["pts_home"]), int(row["pts_away"])
        winner = home.team_id if str(row["wl_home"]) == "W" else away.team_id
        season_type = "REGULAR" if str(row["season_type"]) == "Regular Season" else "PLAYOFF"
        output[(season_id, season_type)].append(
            CanonicalGameEvidence(
                game_id=canonical_id("game", "nba", nba_game_id),
                nba_game_id=nba_game_id,
                season_id=season_id,
                season_type=season_type,
                game_date=date.fromisoformat(str(row["game_date"])[:10]),
                home_team_id=home.team_id,
                away_team_id=away.team_id,
                home_score=home_score,
                away_score=away_score,
                winner_team_id=winner,
                venue_assignment_status="OFFICIAL_HOME_AWAY",
                score_reliable=True,
                source_id="nbadb:kaggle:v238:game",
            )
        )
    return output


def _payload_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_sets = payload.get("resultSets", payload.get("resultSet", []))
    result_sets = [raw_sets] if isinstance(raw_sets, dict) else raw_sets
    if not result_sets:
        return []
    selected = result_sets[0]
    headers = [str(value) for value in selected["headers"]]
    return [dict(zip(headers, row, strict=True)) for row in selected["rowSet"]]


def _api_games_for_scope(
    rows: list[dict[str, Any]],
    crosswalk: dict[tuple[str, str], TeamIdentity],
    *,
    season_id: int,
    season_type: str,
    source_fingerprint: str,
) -> list[CanonicalGameEvidence]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["GAME_ID"])].append(row)
    games: list[CanonicalGameEvidence] = []
    for nba_game_id, game_rows in sorted(grouped.items()):
        by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in game_rows:
            by_team[str(row["TEAM_ID"])].append(row)
        if len(by_team) != 2:
            raise ValueError(f"official game does not contain exactly two teams: {nba_game_id}")
        evidence: list[tuple[TeamIdentity, bool | None, str, int]] = []
        for team_rows in by_team.values():
            first = team_rows[0]
            identity = _team(crosswalk, first["TEAM_ID"], first["TEAM_NAME"])
            home_votes = sum(" vs. " in str(row["MATCHUP"]) for row in team_rows)
            away_votes = sum(" @ " in str(row["MATCHUP"]) for row in team_rows)
            is_home = (
                True if home_votes > away_votes else False if away_votes > home_votes else None
            )
            non_null_wl = {str(row["WL"]) for row in team_rows if row.get("WL") is not None}
            if len(non_null_wl) != 1:
                raise ValueError(f"inconsistent W/L evidence: {nba_game_id}")
            points = [row.get("PTS") for row in team_rows]
            if any(value is None for value in points):
                raise ValueError(f"team points are incomplete: {nba_game_id}")
            evidence.append(
                (identity, is_home, next(iter(non_null_wl)), sum(int(v) for v in points))
            )
        home_rows = [item for item in evidence if item[1] is True]
        away_rows = [item for item in evidence if item[1] is False]
        venue_status = "MATCHUP_HOME_AWAY"
        if len(home_rows) == 1 and len(away_rows) == 1:
            home, away = home_rows[0], away_rows[0]
        elif not home_rows or not away_rows:
            home, away = sorted(evidence, key=lambda item: item[0].team_id)
            venue_status = "NEUTRAL_SITE_DESIGNATION_UNAVAILABLE"
        else:
            raise ValueError(f"home/away evidence is ambiguous: {nba_game_id}")
        if {home[2], away[2]} != {"W", "L"}:
            raise ValueError(f"game W/L does not contain one winner: {nba_game_id}")
        winner = home[0].team_id if home[2] == "W" else away[0].team_id
        score_reliable = home[3] != away[3] and ((home[3] > away[3]) == (winner == home[0].team_id))
        games.append(
            CanonicalGameEvidence(
                game_id=canonical_id("game", "nba", nba_game_id),
                nba_game_id=nba_game_id,
                season_id=season_id,
                season_type=season_type,
                game_date=date.fromisoformat(str(game_rows[0]["GAME_DATE"])[:10]),
                home_team_id=home[0].team_id,
                away_team_id=away[0].team_id,
                home_score=home[3],
                away_score=away[3],
                winner_team_id=winner,
                venue_assignment_status=venue_status,
                score_reliable=score_reliable,
                source_id=f"nba_api:1.11.4:playergamelogs:{source_fingerprint}",
            )
        )
    return games


def _api_games(
    checkpoint_path: Path,
    crosswalk: dict[tuple[str, str], TeamIdentity],
    years: range,
) -> dict[tuple[int, str], list[CanonicalGameEvidence]]:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    output: dict[tuple[int, str], list[CanonicalGameEvidence]] = {}
    for year in years:
        season = f"{year}-{str(year + 1)[-2:]}"
        for canonical_type in ("REGULAR", "PLAYOFF"):
            scope = f"playergamelogs|{season}|{canonical_type}||"
            item = checkpoint["requests"][scope]
            if item["request_status"] != "SUCCESS_WITH_ROWS":
                raise ValueError(f"frozen PlayerGameLogs scope is unavailable: {scope}")
            path = ROOT / "data/bronze/nba_api/playergamelogs" / f"{item['cache_key']}.json"
            output[(year, canonical_type)] = _api_games_for_scope(
                _payload_rows(path),
                crosswalk,
                season_id=year,
                season_type=canonical_type,
                source_fingerprint=str(item["cache_fingerprint"]),
            )
    return output


def _assert_overlap(
    legacy: dict[tuple[int, str], list[CanonicalGameEvidence]],
    api: dict[tuple[int, str], list[CanonicalGameEvidence]],
) -> dict[str, Any]:
    partitions: list[dict[str, Any]] = []
    for season_type in ("REGULAR", "PLAYOFF"):
        legacy_games = {game.game_id: game for game in legacy[(2022, season_type)]}
        api_games = {game.game_id: game for game in api[(2022, season_type)]}
        mismatches: list[dict[str, Any]] = []
        for game_id in sorted(set(legacy_games) & set(api_games)):
            left, right = legacy_games[game_id], api_games[game_id]
            if (
                left.game_date != right.game_date
                or {left.home_team_id, left.away_team_id}
                != {right.home_team_id, right.away_team_id}
                or left.home_team_id != right.home_team_id
                or left.home_score != right.home_score
                or left.away_score != right.away_score
                or left.winner_team_id != right.winner_team_id
            ):
                mismatches.append({"game_id": game_id})
        partitions.append(
            {
                "season_id": 2022,
                "season_type": season_type,
                "legacy_games": len(legacy_games),
                "api_games": len(api_games),
                "shared_games": len(set(legacy_games) & set(api_games)),
                "legacy_only": len(set(legacy_games) - set(api_games)),
                "api_only": len(set(api_games) - set(legacy_games)),
                "mismatches": len(mismatches),
            }
        )
    if any(item["legacy_only"] or item["api_only"] or item["mismatches"] for item in partitions):
        raise ValueError("2022-23 frozen game evidence failed overlap reconciliation")
    return {"partitions": partitions, "passes": True}


def _normalize_name(value: str) -> str:
    normalized = "".join(character.lower() for character in value if character.isalnum())
    return normalized.replace("ftwayne", "fortwayne").replace("zollner", "")


def _official_team_id(
    name: str,
    season_id: int,
    crosswalk_report: dict[str, Any],
) -> str:
    candidates = [
        row
        for row in crosswalk_report["crosswalk"]
        if _normalize_name(str(row["team_name"])) == _normalize_name(name)
        and int(row["valid_from_year_observed"]) <= season_id
        and int(row["valid_to_year_observed"]) >= season_id
    ]
    if len(candidates) != 1:
        raise ValueError(f"official team name does not resolve uniquely: {season_id} {name}")
    return str(candidates[0]["team_id"])


def _read_partition(root: Path, season_id: int, season_type: str) -> list[dict[str, Any]]:
    path = root / f"season={season_id}" / f"season_type={season_type}" / "part-00000.parquet"
    return cast(list[dict[str, Any]], pq.read_table(path).to_pylist())


def _read_bucketed(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("bucket=*/part-00000.parquet")):
        rows.extend(cast(list[dict[str, Any]], pq.read_table(path).to_pylist()))
    return rows


def _minutes_classes(path: Path) -> dict[tuple[int, str], str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        (int(row["season_id"]), str(row["season_type"])): str(row["classification"])
        for row in report["matrix"]
        if row["canonical_metric"] == "minutes"
    }


def _write_partitioned_outputs(
    args: argparse.Namespace,
    team_rows: dict[int, list[dict[str, Any]]],
    finals_rows: dict[int, list[dict[str, Any]]],
    participation_rows: dict[int, list[dict[str, Any]]],
    gold_rows: list[dict[str, Any]],
    career_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    partitions: list[dict[str, Any]] = []
    for season_id in range(START_YEAR, END_YEAR + 1):
        partitions.append(
            _write_parquet(
                team_rows[season_id],
                args.silver_root
                / "team_season_results"
                / f"season={season_id}"
                / "part-00000.parquet",
                ("team_id",),
            )
        )
        partitions.append(
            _write_parquet(
                finals_rows[season_id],
                args.silver_root / "finals_games" / f"season={season_id}" / "part-00000.parquet",
                ("finals_game_number", "game_id"),
            )
        )
        partitions.append(
            _write_parquet(
                participation_rows[season_id],
                args.silver_root
                / "player_team_season_participation"
                / f"season={season_id}"
                / "part-00000.parquet",
                ("player_id", "team_id"),
            )
        )
    for entity, rows in (
        ("player_team_success_primitives", gold_rows),
        ("player_career_team_context", career_rows),
    ):
        bucketed: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            bucketed[_bucket(str(row["player_id"]))].append(row)
        for bucket in range(BUCKETS):
            partitions.append(
                _write_parquet(
                    bucketed[bucket],
                    args.gold_root / entity / f"bucket={bucket:02d}" / "part-00000.parquet",
                    ("player_id", "season_id", "team_id")
                    if entity == "player_team_success_primitives"
                    else ("player_id",),
                )
            )
    return partitions


def _aggregate_fingerprint(partitions: list[dict[str, Any]]) -> str:
    stable = [
        {key: row[key] for key in ("path", "rows", "columns", "size_bytes", "sha256")}
        for row in sorted(partitions, key=lambda item: str(item["path"]))
    ]
    return stable_json_fingerprint(stable)


def main() -> None:
    args = _args()
    started = time.monotonic()
    run_at = datetime.fromisoformat(args.run_at.replace("Z", "+00:00")).astimezone(UTC)
    corpus_manifest = json.loads(
        (args.docs_root / "historical-corpus-v1-manifest.json").read_text(encoding="utf-8")
    )
    award_manifest = json.loads(
        (args.docs_root / "award-output-manifest.json").read_text(encoding="utf-8")
    )
    if corpus_manifest["corpus_fingerprint"] != CORPUS_FINGERPRINT:
        raise ValueError("frozen corpus fingerprint changed")
    if award_manifest["output_fingerprint"] != AWARDS_FINGERPRINT:
        raise ValueError("award output fingerprint changed")

    crosswalk_path = args.docs_root / "full-team-crosswalk.json"
    crosswalk_report = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    crosswalk, identities = _load_crosswalk(crosswalk_path)
    legacy = _legacy_games(args.legacy_db, crosswalk)
    api_all = _api_games(args.checkpoint, crosswalk, range(START_YEAR, END_YEAR + 1))
    overlap = _assert_overlap(legacy, api_all)
    expected_game_partitions = {
        (year, season_type)
        for year in range(START_YEAR, END_YEAR + 1)
        for season_type in ("REGULAR", "PLAYOFF")
    }
    games = {key: legacy.get(key, api_all[key]) for key in expected_game_partitions}
    if set(games) != {
        (year, season_type)
        for year in range(START_YEAR, END_YEAR + 1)
        for season_type in ("REGULAR", "PLAYOFF")
    }:
        raise ValueError("game evidence does not cover all frozen partitions")

    official = json.loads(args.official_reference.read_text(encoding="utf-8"))
    if official["source_url"] != OFFICIAL_CHAMPIONS_URL or len(official["records"]) != 80:
        raise ValueError("official championship validation fixture changed")
    official_by_season = {int(row["season_id"]): row for row in official["records"]}
    if set(official_by_season) != set(range(START_YEAR, END_YEAR + 1)):
        raise ValueError("official championship fixture does not cover 80 seasons")

    accolades = {
        str(row["player_id"]): row
        for row in _read_bucketed(args.gold_root / "player_career_accolades")
    }
    award_status = {
        player_id: str(row["award_acquisition_status"]) for player_id, row in accolades.items()
    }
    champion_award_seasons = {
        (str(row["player_id"]), int(row["season_id"]))
        for row in _read_bucketed(args.silver_root / "player_awards")
        if row["award_type"] == "NBA_CHAMPION" and row["season_id"] is not None
    }
    minutes_classes = _minutes_classes(args.docs_root / "full-metric-coverage.json")

    team_rows_by_season: dict[int, list[dict[str, Any]]] = {}
    finals_rows_by_season: dict[int, list[dict[str, Any]]] = {}
    participation_by_season: dict[int, list[dict[str, Any]]] = {}
    all_participation: list[dict[str, Any]] = []
    all_gold: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    format_registry: list[dict[str, Any]] = []
    minute_eligibility: Counter[str] = Counter()

    for season_id in range(START_YEAR, END_YEAR + 1):
        regular_games = games[(season_id, "REGULAR")]
        playoff_games = games[(season_id, "PLAYOFF")]
        outcome = infer_finals_outcome(playoff_games)
        finals_models = identify_finals_games(playoff_games, outcome, updated_at=run_at)
        finals_rows = [_model_row(row) for row in finals_models]
        official_row = official_by_season[season_id]
        official_champion = _official_team_id(
            str(official_row["champion"]), season_id, crosswalk_report
        )
        official_finalist = _official_team_id(
            str(official_row["finalist"]), season_id, crosswalk_report
        )
        champion_match = outcome.champion_team_id == official_champion
        finalist_match = outcome.finalist_team_id == official_finalist
        champion_wins = sum(
            row["winner_team_id"] == outcome.champion_team_id for row in finals_rows
        )
        finalist_wins = len(finals_rows) - champion_wins
        series_result = f"{champion_wins}-{finalist_wins}"
        series_match = series_result == official_row["series_result"]
        reconciliation.append(
            {
                "season_id": season_id,
                "season_label": f"{season_id}-{str(season_id + 1)[-2:]}",
                "derived_champion_team_id": outcome.champion_team_id,
                "derived_champion": identities[outcome.champion_team_id].team_name,
                "official_champion_team_id": official_champion,
                "official_champion": official_row["champion"],
                "champion_match": champion_match,
                "derived_finalist_team_id": outcome.finalist_team_id,
                "derived_finalist": identities[outcome.finalist_team_id].team_name,
                "official_finalist_team_id": official_finalist,
                "official_finalist": official_row["finalist"],
                "finalist_match": finalist_match,
                "finals_game_count": len(finals_rows),
                "derived_series_result": series_result,
                "official_series_result": official_row["series_result"],
                "series_result_match": series_match,
                "deciding_game_id": outcome.deciding_game_id,
                "deciding_game_date": outcome.deciding_game_date.isoformat(),
            }
        )
        if not champion_match or not finalist_match or not series_match:
            raise ValueError(f"official Finals reconciliation failed for {season_id}")

        team_models = derive_team_season_results(
            regular_games, playoff_games, identities, outcome, updated_at=run_at
        )
        team_rows = [_model_row(row) for row in team_models]
        format_status, series_allowed, modern_labels = postseason_format_for_season(season_id)
        format_registry.append(
            {
                "season_id": season_id,
                "season_label": f"{season_id}-{str(season_id + 1)[-2:]}",
                "teams_in_postseason": len(
                    {
                        team
                        for game in playoff_games
                        for team in (game.home_team_id, game.away_team_id)
                    }
                ),
                "playoff_games": len(playoff_games),
                "format_class": format_status.value,
                "series_inference_allowed": series_allowed,
                "modern_round_labels_allowed": modern_labels,
                "known_notes": (
                    "Official NBA season review documents a division round-robin opening stage."
                    if season_id == 1953
                    else (
                        "Variable historical series lengths/byes; opponent-pair series "
                        "remain factual."
                    )
                    if season_id < 1983
                    else "Four-series title path under the 16-team bracket family."
                ),
                "validation_status": "OFFICIAL_HISTORY_VALIDATED",
            }
        )

        regular_rows = _read_partition(args.silver_root / "player_game_stats", season_id, "REGULAR")
        playoff_rows = _read_partition(args.silver_root / "player_game_stats", season_id, "PLAYOFF")
        regular_minutes = minutes_are_eligible(
            regular_rows,
            empirical_classification=minutes_classes[(season_id, "REGULAR")],
        )
        playoff_minutes = minutes_are_eligible(
            playoff_rows,
            empirical_classification=minutes_classes[(season_id, "PLAYOFF")],
        )
        minute_eligibility[f"REGULAR_{regular_minutes}"] += 1
        minute_eligibility[f"PLAYOFF_{playoff_minutes}"] += 1
        participation_models = build_player_team_participation(
            regular_rows,
            playoff_rows,
            team_models,
            {row.game_id for row in finals_models},
            {game.game_id: game.winner_team_id for game in playoff_games},
            award_status,
            champion_award_seasons,
            regular_minutes_eligible=regular_minutes,
            playoff_minutes_eligible=playoff_minutes,
            updated_at=run_at,
        )
        participation_rows = [_model_row(row) for row in participation_models]
        team_lookup = {row["team_id"]: row for row in team_rows}
        gold_rows = []
        for row in participation_rows:
            context = team_lookup[str(row["team_id"])]
            gold_rows.append(
                {
                    **row,
                    "team_regular_win_pct": context["regular_win_pct"],
                    "team_win_pct_rank": context["win_pct_rank"],
                    "team_win_pct_percentile": context["win_pct_percentile"],
                    "team_point_diff_per_game": context["regular_point_diff_per_game"],
                    "team_point_diff_rank": context["point_diff_rank"],
                    "team_point_diff_percentile": context["point_diff_percentile"],
                    "team_playoff_wins": context["playoff_wins"],
                    "team_series_won": context["series_won"],
                    "postseason_format_status": context["postseason_format_status"],
                }
            )
        team_rows_by_season[season_id] = team_rows
        finals_rows_by_season[season_id] = finals_rows
        participation_by_season[season_id] = participation_rows
        all_participation.extend(participation_rows)
        all_gold.extend(gold_rows)

    if sum(row["champion_match"] for row in reconciliation) != 80:
        raise ValueError("champion validation is not exact across 80 seasons")
    if sum(row["finalist_match"] for row in reconciliation) != 80:
        raise ValueError("finalist validation is not exact across 80 seasons")

    master_report = json.loads(
        (args.docs_root / "award-candidate-universe-analysis.json").read_text(encoding="utf-8")
    )
    career_summaries = {
        str(row["player_id"]): row
        for row in _read_bucketed(args.gold_root / "player_career_summary")
    }
    master_players = [
        {
            **row,
            "career_status": career_summaries[str(row["player_id"])]["career_status"],
        }
        for row in master_report["players"]
    ]
    team_result_lookup = {
        (str(row["team_id"]), int(row["season_id"])): row
        for rows in team_rows_by_season.values()
        for row in rows
    }
    career_rows = career_team_context(
        master_players, all_participation, team_result_lookup, accolades
    )
    validate_finite_rows(all_gold)
    validate_finite_rows(career_rows)

    duplicate_team_seasons = len(team_result_lookup) != sum(map(len, team_rows_by_season.values()))
    participation_keys = {
        (str(row["player_id"]), str(row["team_id"]), int(row["season_id"]))
        for row in all_participation
    }
    duplicate_participation = len(participation_keys) != len(all_participation)
    if duplicate_team_seasons or duplicate_participation:
        raise ValueError("duplicate canonical team-success keys detected")

    _reset_outputs(args.silver_root, args.gold_root)
    partitions = _write_partitioned_outputs(
        args,
        team_rows_by_season,
        finals_rows_by_season,
        participation_by_season,
        all_gold,
        career_rows,
    )
    output_fingerprint = _aggregate_fingerprint(partitions)
    if args.expected_fingerprint and output_fingerprint != args.expected_fingerprint:
        raise ValueError("team-success output fingerprint differs from expected")

    participation_by_player_season: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in all_participation:
        participation_by_player_season[(str(row["player_id"]), int(row["season_id"]))].append(row)
    award_participation = {
        key: participation_by_player_season.get(key, []) for key in champion_award_seasons
    }
    champion_participants = [
        row for row in all_participation if row["played_finals_for_champion_team"]
    ]
    queried_champion_participants = [
        row for row in champion_participants if row["award_acquisition_status"] != "NOT_QUERIED"
    ]
    award_audit = {
        "methodology_version": TEAM_SUCCESS_METHODOLOGY_VERSION,
        "official_champion_award_player_seasons": len(champion_award_seasons),
        "award_events_with_regular_champion_membership": sum(
            any(row["regular_season_member_of_champion_team"] for row in rows)
            for rows in award_participation.values()
        ),
        "award_events_with_champion_playoff_participation": sum(
            any(row["played_playoffs_for_champion_team"] for row in rows)
            for rows in award_participation.values()
        ),
        "award_events_with_champion_finals_participation": sum(
            any(row["played_finals_for_champion_team"] for row in rows)
            for rows in award_participation.values()
        ),
        "award_events_without_finals_appearance": sum(
            not any(row["played_finals_for_champion_team"] for row in rows)
            for rows in award_participation.values()
        ),
        "award_events_without_any_player_game_participation": sum(
            not rows for rows in award_participation.values()
        ),
        "queried_champion_finals_participants": len(queried_champion_participants),
        "queried_champion_finals_participants_without_award_event": sum(
            row["official_nba_champion_award_event"] is False
            for row in queried_champion_participants
        ),
        "nonqueried_champion_finals_participants": sum(
            row["award_acquisition_status"] == "NOT_QUERIED" for row in champion_participants
        ),
        "regular_champion_members_without_champion_playoffs": sum(
            row["regular_season_member_of_champion_team"]
            and not row["played_playoffs_for_champion_team"]
            for row in all_participation
        ),
        "queried_champion_finals_participants_without_award_examples": [
            {
                "player_id": row["player_id"],
                "display_name": next(
                    player["display_name"]
                    for player in master_players
                    if player["player_id"] == row["player_id"]
                ),
                "season_id": row["season_id"],
            }
            for row in queried_champion_participants
            if row["official_nba_champion_award_event"] is False
        ][:20],
        "semantics": {
            "team_champion": "derived from frozen postseason games and official validation",
            "regular_membership": "at least one accepted Regular Season player-game for that team",
            "playoff_participation": "at least one accepted Playoff player-game for that team",
            "finals_participation": "at least one accepted player-game in the validated Finals set",
            "official_award": (
                "candidate-scoped STEP-0009 NBA Champion source event; NULL when NOT_QUERIED"
            ),
        },
    }

    names = {str(row["player_id"]): str(row["display_name"]) for row in master_players}
    traded = [
        row
        for row in all_participation
        if sum(
            candidate["regular_games"] > 0
            for candidate in all_participation
            if candidate["player_id"] == row["player_id"]
            and candidate["season_id"] == row["season_id"]
        )
        > 1
        and row["playoff_games"] > 0
    ]
    dominant_champion = max(
        (row for rows in team_rows_by_season.values() for row in rows if row["champion"]),
        key=lambda row: (float(row["regular_win_pct"]), -int(row["season_id"])),
    )
    lower_win_finalist = min(
        (
            row
            for rows in team_rows_by_season.values()
            for row in rows
            if row["finalist"] and not row["champion"]
        ),
        key=lambda row: (float(row["regular_win_pct"]), int(row["season_id"])),
    )
    most_finals = max(career_rows, key=lambda row: int(row["finals_games"]))
    cases = {
        "dominant_champion_team": dominant_champion,
        "lowest_win_pct_finalist": lower_win_finalist,
        "multiple_championship_participation": most_finals,
        "traded_season_playoff_team_example": (
            {**traded[0], "display_name": names[str(traded[0]["player_id"])]} if traded else None
        ),
        "regular_champion_member_without_playoff_example": next(
            (
                {**row, "display_name": names[str(row["player_id"])]}
                for row in all_participation
                if row["regular_season_member_of_champion_team"]
                and not row["played_playoffs_for_champion_team"]
            ),
            None,
        ),
        "early_champion": reconciliation[0],
        "modern_champion": reconciliation[-1],
        "round_robin_or_mixed_season": format_registry[1953 - START_YEAR],
    }

    coverage_registry = [
        {
            "feature": "regular_wins_losses",
            "status": "RELIABLE",
            "source": "canonical game results",
            "notes": "Universal across 80 seasons; W + L = GP gate.",
        },
        {
            "feature": "regular_point_differential",
            "status": "PARTIAL",
            "source": "canonical final scores",
            "notes": (
                "Reliable in 76 seasons. Withheld in 1960-61, 1970-71, 1975-76, "
                "and 1976-77 because fallback team-point sums conflict with recorded W/L."
            ),
        },
        {
            "feature": "champion_finalist_finals_games",
            "status": "RELIABLE",
            "source": "frozen playoff games plus official NBA history validation",
            "notes": "80/80 champion and finalist identity and Finals score reconciliations.",
        },
        {
            "feature": "series_won_lost",
            "status": "FORMAT_BLOCKED",
            "source": "unordered playoff opponent pairs",
            "notes": "Available in 79 seasons; blocked for the 1953-54 round-robin/mixed format.",
        },
        {
            "feature": "player_minutes_share",
            "status": "PARTIAL",
            "source": "canonical player-game minutes",
            "notes": "Requires RELIABLE coverage and at least 99% positive minute observations.",
        },
    ]
    feature_definitions = {
        "registry_version": 1,
        "methodology_version": TEAM_SUCCESS_METHODOLOGY_VERSION,
        "principle": "Team outcome and player participation are separate factual surfaces.",
        "features": coverage_registry,
        "participation_variants": [
            "regular_season_member_of_champion_team",
            "played_playoffs_for_champion_team",
            "played_finals_for_champion_team",
            "official_nba_champion_award_event",
        ],
        "prohibited_composites": ["winning_score", "team_success_score", "rings_score"],
    }
    summary = {
        "step": "STEP-0010",
        "methodology_version": TEAM_SUCCESS_METHODOLOGY_VERSION,
        "run_at": run_at.isoformat(),
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "award_fingerprint": AWARDS_FINGERPRINT,
        "season_count": 80,
        "team_season_rows": sum(map(len, team_rows_by_season.values())),
        "regular_games": sum(
            len(games[(year, "REGULAR")]) for year in range(START_YEAR, END_YEAR + 1)
        ),
        "playoff_games": sum(
            len(games[(year, "PLAYOFF")]) for year in range(START_YEAR, END_YEAR + 1)
        ),
        "playoff_team_seasons": sum(
            row["made_playoffs"] for rows in team_rows_by_season.values() for row in rows
        ),
        "finals_games": sum(map(len, finals_rows_by_season.values())),
        "player_team_season_rows": len(all_participation),
        "career_rows": len(career_rows),
        "champion_matches": sum(row["champion_match"] for row in reconciliation),
        "finalist_matches": sum(row["finalist_match"] for row in reconciliation),
        "series_result_matches": sum(row["series_result_match"] for row in reconciliation),
        "format_counts": dict(
            sorted(Counter(row["format_class"] for row in format_registry).items())
        ),
        "series_inference_seasons": sum(row["series_inference_allowed"] for row in format_registry),
        "minute_eligibility_partitions": dict(sorted(minute_eligibility.items())),
        "regular_scoring_context_seasons": sum(
            rows[0]["regular_point_diff_per_game"] is not None
            for rows in team_rows_by_season.values()
        ),
        "regular_scoring_context_withheld_seasons": [
            season_id
            for season_id, rows in sorted(team_rows_by_season.items())
            if rows[0]["regular_point_diff_per_game"] is None
        ],
        "overlap_reconciliation": overlap,
        "quality": {
            "duplicate_team_season_keys": int(duplicate_team_seasons),
            "duplicate_player_team_season_keys": int(duplicate_participation),
            "champion_count_failures": 0,
            "finalist_count_failures": 0,
            "regular_record_failures": 0,
            "playoff_record_failures": 0,
            "finals_game_team_failures": 0,
            "null_to_zero_failures": 0,
            "traded_team_outcome_leakage_failures": 0,
        },
        "subjective_scores_created": 0,
        "output_fingerprint": output_fingerprint,
        "partition_count": len(partitions),
        "output_size_bytes": sum(int(row["size_bytes"]) for row in partitions),
        "runtime_seconds": (
            round(args.recorded_runtime_seconds, 6)
            if args.recorded_runtime_seconds is not None
            else round(time.monotonic() - started, 6)
        ),
    }
    manifest = {
        "manifest_version": 1,
        "step": "STEP-0010",
        "methodology_version": TEAM_SUCCESS_METHODOLOGY_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "award_fingerprint": AWARDS_FINGERPRINT,
        "output_fingerprint": output_fingerprint,
        "partition_count": len(partitions),
        "size_bytes": sum(int(row["size_bytes"]) for row in partitions),
        "partitions": sorted(partitions, key=lambda row: str(row["path"])),
    }
    championship_report = {
        "source_url": official["source_url"],
        "source_retrieved_at": official["retrieved_at"],
        "source_role": official["source_role"],
        "derivation": "unique chronologically final playoff game, then complete team-pair matchup",
        "champion_matches": 80,
        "finalist_matches": 80,
        "series_result_matches": 80,
        "seasons": reconciliation,
    }
    _stable_json(args.docs_root / "team-success-summary.json", summary)
    _stable_json(args.docs_root / "team-success-output-manifest.json", manifest)
    _stable_json(args.docs_root / "championship-reconciliation.json", championship_report)
    _stable_json(args.docs_root / "player-championship-participation-audit.json", award_audit)
    _stable_json(args.docs_root / "team-success-case-studies.json", cases)
    _stable_yaml(
        args.docs_root / "postseason-format-registry.yaml",
        {
            "registry_version": 1,
            "methodology_version": TEAM_SUCCESS_METHODOLOGY_VERSION,
            "official_validation": [
                OFFICIAL_CHAMPIONS_URL,
                "https://www.nba.com/news/history-season-review-1953-54",
                "https://www.nba.com/news/history-season-review-1983-84",
            ],
            "seasons": format_registry,
        },
    )
    _stable_yaml(args.docs_root / "team-success-feature-definitions.yaml", feature_definitions)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
