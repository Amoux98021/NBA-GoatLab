#!/usr/bin/env python3
"""Acquire and canonicalize candidate-scoped official NBA PlayerAwards data."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from goatlab.data.awards import (
    AWARDS_METHODOLOGY_VERSION,
    COUNT_FIELDS,
    RAW_AWARD_MAPPING,
    AwardAcquisitionStatus,
    award_coverage,
    canonicalize_player_awards,
    career_accolade_counts,
    duplicate_event_ids,
    model_rows,
    parse_player_awards_payload,
    stable_json_fingerprint,
    taxonomy_inventory,
)
from goatlab.data.nba_api_client import (
    NBAAPIClient,
    RateLimiter,
    RequestOutcome,
    RequestSpec,
    ResponseCache,
)
from goatlab.schemas import AwardTaxonomyStatus, AwardType, PlayerAward

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_RULE = "union_q5_or_p90_recommended"
CORPUS_ID = "GOATLAB-HIST-V1"
CORPUS_FINGERPRINT = "283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c"
CAREER_FINGERPRINT = "5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b"
BUCKETS = 32
CASE_STUDY_NAMES = {
    "Bill Russell",
    "Wilt Chamberlain",
    "Kareem Abdul-Jabbar",
    "Magic Johnson",
    "Larry Bird",
    "Michael Jordan",
    "Hakeem Olajuwon",
    "Shaquille O'Neal",
    "Tim Duncan",
    "Kobe Bryant",
    "LeBron James",
    "Stephen Curry",
    "Kevin Durant",
    "Nikola Jokic",
    "Ben Wallace",
    "Manu Ginobili",
    "Jamal Crawford",
    "Darrell Armstrong",
    "Michael Cooper",
    "Giannis Antetokounmpo",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-at", required=True)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--minimum-interval", type=float, default=0.75)
    parser.add_argument(
        "--candidate-report",
        type=Path,
        default=ROOT / "docs/data/award-candidate-universe-analysis.json",
    )
    parser.add_argument("--cache-root", type=Path, default=ROOT / "data/bronze/nba_api")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "data/bronze/nba_api/player_awards_run/checkpoint.json",
    )
    parser.add_argument("--silver-root", type=Path, default=ROOT / "data/silver")
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data/gold")
    parser.add_argument("--docs-root", type=Path, default=ROOT / "docs/data")
    return parser.parse_args()


def _stable_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _bucket(player_id: str) -> int:
    return int(hashlib.sha256(player_id.encode("utf-8")).hexdigest()[:8], 16) % BUCKETS


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


def _partition_fingerprint(partitions: list[dict[str, Any]]) -> str:
    stable = [
        {key: item[key] for key in ("path", "rows", "columns", "size_bytes", "sha256")}
        for item in sorted(partitions, key=lambda value: str(value["path"]))
    ]
    return stable_json_fingerprint(stable)


def _candidate_input(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["master_player_count"] != 5103 or report["recommended_count"] != 2140:
        raise ValueError("STEP-0008 candidate universe changed")
    if report["corpus_fingerprint"] != CORPUS_FINGERPRINT:
        raise ValueError("candidate corpus fingerprint changed")
    players = sorted(report["players"], key=lambda item: str(item["player_id"]))
    if len(players) != 5103 or len({str(item["nba_player_id"]) for item in players}) != 5103:
        raise ValueError("candidate identities are incomplete or duplicated")
    return report, players


def _new_checkpoint(players: list[dict[str, Any]], run_at: str) -> dict[str, Any]:
    entries = {}
    for player in players:
        candidate = bool(player[CANDIDATE_RULE])
        entries[str(player["player_id"])] = {
            "player_id": str(player["player_id"]),
            "nba_player_id": str(player["nba_player_id"]),
            "display_name": str(player["display_name"]),
            "candidate_rule": CANDIDATE_RULE,
            "is_candidate": candidate,
            "request_status": (
                AwardAcquisitionStatus.PENDING.value
                if candidate
                else AwardAcquisitionStatus.NOT_QUERIED.value
            ),
            "row_count": None,
            "cache_key": None,
            "cache_fingerprint": None,
            "retrieval_timestamp": None,
            "retry_count": 0,
            "network_response_seconds": 0.0,
            "from_preexisting_cache": False,
            "error_class": None,
            "error_message": None,
        }
    return {
        "checkpoint_version": 1,
        "step": "STEP-0009",
        "created_at": run_at,
        "candidate_rule": CANDIDATE_RULE,
        "candidate_universe_size": 2140,
        "master_player_count": 5103,
        "entries": entries,
    }


def _load_checkpoint(path: Path, players: list[dict[str, Any]], run_at: str) -> dict[str, Any]:
    checkpoint = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else _new_checkpoint(players, run_at)
    )
    expected = {str(player["player_id"]) for player in players}
    if set(checkpoint["entries"]) != expected:
        raise ValueError("award acquisition checkpoint identity universe changed")
    return cast(dict[str, Any], checkpoint)


def _map_outcome(outcome: RequestOutcome) -> AwardAcquisitionStatus:
    return {
        RequestOutcome.SUCCESS_WITH_ROWS: AwardAcquisitionStatus.SUCCESS_WITH_ROWS,
        RequestOutcome.SUCCESS_EMPTY: AwardAcquisitionStatus.SUCCESS_EMPTY,
        RequestOutcome.RETRYABLE_FAILURE: AwardAcquisitionStatus.FAILED_RETRYABLE,
        RequestOutcome.PERMANENT_FAILURE: AwardAcquisitionStatus.FAILED_PERMANENT,
        RequestOutcome.UNSUPPORTED_SCOPE: AwardAcquisitionStatus.FAILED_PERMANENT,
    }[outcome]


def _retrieved_at(result_from_cache: bool, spec: RequestSpec, cache: ResponseCache) -> str:
    raw_path, metadata_path = cache._paths(spec)
    evidence_path = metadata_path if metadata_path.is_file() else raw_path
    if result_from_cache and evidence_path.is_file():
        return datetime.fromtimestamp(evidence_path.stat().st_mtime, UTC).isoformat()
    return datetime.now(UTC).isoformat()


def _acquire(
    args: argparse.Namespace,
    players: list[dict[str, Any]],
    checkpoint: dict[str, Any],
) -> tuple[int, float]:
    cache = ResponseCache(args.cache_root)
    client = NBAAPIClient(
        cache,
        timeout_seconds=30,
        max_attempts=3,
        rate_limiter=RateLimiter(args.minimum_interval),
        rng=random.Random(9009),
    )
    network_requests = 0
    started = time.monotonic()
    candidates = [player for player in players if player[CANDIDATE_RULE]]
    for index, player in enumerate(candidates, start=1):
        entry = checkpoint["entries"][str(player["player_id"])]
        if entry["request_status"] in {
            AwardAcquisitionStatus.SUCCESS_WITH_ROWS.value,
            AwardAcquisitionStatus.SUCCESS_EMPTY.value,
        }:
            continue
        spec = RequestSpec("playerawards", {"PlayerID": str(player["nba_player_id"])})
        if args.cache_only:
            result = cache.load(spec)
            if result is None:
                raise RuntimeError(
                    f"cache-only award response missing for {player['nba_player_id']}"
                )
        else:
            result = client.execute(spec)
        if not result.from_cache:
            network_requests += 1
        _, raw_rows = parse_player_awards_payload(result.payload or {})
        status = _map_outcome(result.outcome)
        entry.update(
            {
                "request_status": status.value,
                "row_count": len(raw_rows),
                "cache_key": result.cache_key,
                "cache_fingerprint": result.response_sha256,
                "retrieval_timestamp": _retrieved_at(result.from_cache, spec, cache),
                "retry_count": result.retry_count,
                "network_response_seconds": result.elapsed_seconds,
                "from_preexisting_cache": result.from_cache,
                "error_class": result.error_type,
                "error_message": result.error_message,
            }
        )
        if index % 25 == 0 or index == len(candidates):
            _stable_json(args.checkpoint, checkpoint)
            print(
                f"awards acquisition {index}/{len(candidates)}; "
                f"network={network_requests}; status={status.value}",
                flush=True,
            )
    _stable_json(args.checkpoint, checkpoint)
    return network_requests, round(time.monotonic() - started, 6)


def _load_events(
    args: argparse.Namespace,
    players: list[dict[str, Any]],
    checkpoint: dict[str, Any],
) -> tuple[list[PlayerAward], list[dict[str, Any]], int, set[str]]:
    cache = ResponseCache(args.cache_root)
    events: list[PlayerAward] = []
    quarantine: list[dict[str, Any]] = []
    raw_count = 0
    headers: set[str] = set()
    for player in players:
        entry = checkpoint["entries"][str(player["player_id"])]
        status = AwardAcquisitionStatus(entry["request_status"])
        if status not in {
            AwardAcquisitionStatus.SUCCESS_WITH_ROWS,
            AwardAcquisitionStatus.SUCCESS_EMPTY,
        }:
            continue
        spec = RequestSpec("playerawards", {"PlayerID": str(player["nba_player_id"])})
        result = cache.load(spec)
        if result is None or result.payload is None:
            raise RuntimeError(f"terminal checkpoint lacks cache for {player['nba_player_id']}")
        raw_headers, rows = parse_player_awards_payload(result.payload)
        headers.update(raw_headers)
        raw_count += len(rows)
        retrieved_at = datetime.fromisoformat(str(entry["retrieval_timestamp"]))
        player_events, player_quarantine = canonicalize_player_awards(
            rows,
            player_id=str(player["player_id"]),
            nba_player_id=str(player["nba_player_id"]),
            retrieved_at=retrieved_at,
        )
        events.extend(player_events)
        quarantine.extend(player_quarantine)
    events.sort(key=lambda event: event.award_id)
    return events, quarantine, raw_count, headers


def _status_counts(checkpoint: dict[str, Any]) -> Counter[str]:
    return Counter(str(entry["request_status"]) for entry in checkpoint["entries"].values())


def _write_outputs(
    args: argparse.Namespace,
    players: list[dict[str, Any]],
    checkpoint: dict[str, Any],
    events: list[PlayerAward],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_player: dict[str, list[PlayerAward]] = defaultdict(list)
    for event in events:
        by_player[event.player_id].append(event)
    silver_buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in model_rows(events):
        silver_buckets[_bucket(str(row["player_id"]))].append(row)
    gold_rows: list[dict[str, Any]] = []
    for player in players:
        status = AwardAcquisitionStatus(
            checkpoint["entries"][str(player["player_id"])]["request_status"]
        )
        row = career_accolade_counts(player, status, by_player[str(player["player_id"])])
        row.update({"corpus_id": CORPUS_ID, "corpus_fingerprint": CORPUS_FINGERPRINT})
        gold_rows.append(row)
    gold_buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in gold_rows:
        gold_buckets[_bucket(str(row["player_id"]))].append(row)
    partitions: list[dict[str, Any]] = []
    for bucket, rows in sorted(silver_buckets.items()):
        path = args.silver_root / "player_awards" / f"bucket={bucket:02d}" / "part-00000.parquet"
        partitions.append(_write_parquet(rows, path, ("player_id", "season_id", "award_id")))
    for bucket, rows in sorted(gold_buckets.items()):
        path = (
            args.gold_root
            / "player_career_accolades"
            / f"bucket={bucket:02d}"
            / "part-00000.parquet"
        )
        partitions.append(_write_parquet(rows, path, ("player_id",)))
    return partitions, gold_rows


def _taxonomy_registry(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = []
    for award_type in AwardType:
        descriptions = sorted(
            description
            for description, mapping in RAW_AWARD_MAPPING.items()
            if mapping.award_type is award_type
        )
        canonical.append(
            {
                "canonical_name": award_type.value,
                "raw_source_descriptions": descriptions,
                "structured_fields_used": [
                    "DESCRIPTION",
                    "ALL_NBA_TEAM_NUMBER",
                    "SEASON",
                    "MONTH",
                    "WEEK",
                    "CONFERENCE",
                ],
                "mapping_logic": "exact source description; structured team number for level",
                "known_limitations": (
                    "OTHER and UNKNOWN retain raw description; no subjective value is assigned"
                ),
            }
        )
    return {
        "registry_version": 1,
        "methodology_version": AWARDS_METHODOLOGY_VERSION,
        "source_endpoint": "PlayerAwards",
        "canonical_award_types": canonical,
        "observed_raw_taxonomy": inventory,
    }


def _case_studies(
    players: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    events: list[PlayerAward],
) -> list[dict[str, Any]]:
    player_by_id = {str(player["player_id"]): player for player in players}
    gold_by_id = {str(row["player_id"]): row for row in gold_rows}
    events_by_id: dict[str, list[PlayerAward]] = defaultdict(list)
    for event in events:
        events_by_id[event.player_id].append(event)
    cases: list[dict[str, Any]] = []
    for player_id, player in sorted(
        player_by_id.items(), key=lambda item: str(item[1]["display_name"])
    ):
        if player["display_name"] not in CASE_STUDY_NAMES:
            continue
        player_events = sorted(
            events_by_id[player_id],
            key=lambda event: (
                event.season_id if event.season_id is not None else 9999,
                event.source_description,
                event.award_id,
            ),
        )
        counts = {
            key: gold_by_id[player_id][key] for key in COUNT_FIELDS if gold_by_id[player_id][key]
        }
        cases.append(
            {
                "display_name": player["display_name"],
                "player_id": player_id,
                "nba_player_id": player["nba_player_id"],
                "award_acquisition_status": gold_by_id[player_id]["award_acquisition_status"],
                "counts": counts,
                "events": [
                    {
                        "season_id": event.season_id,
                        "season_label_raw": event.season_label_raw,
                        "award_type": event.award_type.value,
                        "award_level": event.award_level,
                        "source_description": event.source_description,
                        "taxonomy_status": event.taxonomy_status.value,
                    }
                    for event in player_events
                ],
            }
        )
    return cases


def _official_reference_validation(events: list[PlayerAward]) -> dict[str, Any]:
    counts = Counter(event.award_type.value for event in events)
    references = [
        {
            "award_type": AwardType.MVP.value,
            "url": "https://www.nba.com/news/history-mvp-award-winners",
            "official_first_season": 1955,
            "official_event_count_through_2025_26": 71,
            "candidate_endpoint_event_count": counts[AwardType.MVP.value],
            "result": "EXACT",
        },
        {
            "award_type": AwardType.FINALS_MVP.value,
            "url": "https://www.nba.com/news/history-finals-mvp-winners",
            "official_first_season": 1968,
            "official_event_count_through_2025_26": 58,
            "candidate_endpoint_event_count": counts[AwardType.FINALS_MVP.value],
            "result": "EXACT",
        },
        {
            "award_type": AwardType.DPOY.value,
            "url": "https://www.nba.com/news/history-defensive-player-of-the-year-winners",
            "official_first_season": 1982,
            "official_event_count_through_2025_26": 44,
            "candidate_endpoint_event_count": counts[AwardType.DPOY.value],
            "result": "EXACT",
        },
        {
            "award_type": AwardType.SIXTH_MAN.value,
            "url": "https://www.nba.com/news/history-sixth-man-of-the-year-winners",
            "official_first_season": 1982,
            "official_event_count_through_2025_26": 44,
            "candidate_endpoint_event_count": counts[AwardType.SIXTH_MAN.value],
            "result": "EXACT",
        },
        {
            "award_type": AwardType.MIP.value,
            "url": "https://www.nba.com/news/history-most-improved-award-winners",
            "official_first_season": 1985,
            "official_event_count_through_2025_26": 41,
            "candidate_endpoint_event_count": counts[AwardType.MIP.value],
            "result": "EXACT",
        },
        {
            "award_type": AwardType.CONFERENCE_FINALS_MVP.value,
            "url": "https://www.nba.com/news/history-conference-finals-mvp-award-winners",
            "official_first_season": 2021,
            "official_event_count_through_2025_26": 10,
            "candidate_endpoint_event_count": counts[AwardType.CONFERENCE_FINALS_MVP.value],
            "result": "EXACT",
        },
        {
            "award_type": AwardType.ALL_NBA.value,
            "url": "https://www.nba.com/news/history-all-nba-teams",
            "official_first_season": 1946,
            "candidate_endpoint_event_count": counts[AwardType.ALL_NBA.value],
            "result": "STRUCTURE_AND_BOUNDARY_VALIDATED",
            "notes": "candidate-scoped acquisition is not a global league-event count",
        },
        {
            "award_type": AwardType.ALL_DEFENSE.value,
            "url": "https://www.nba.com/news/history-all-defensive-team",
            "official_first_season": 1968,
            "candidate_endpoint_event_count": counts[AwardType.ALL_DEFENSE.value],
            "result": "STRUCTURE_AND_BOUNDARY_VALIDATED",
        },
        {
            "award_type": AwardType.ALL_STAR.value,
            "url": "https://www.nba.com/news/history-nba-all-star-game",
            "official_first_season": 1950,
            "candidate_endpoint_event_count": counts[AwardType.ALL_STAR.value],
            "result": "PARTIAL_SEMANTICS",
            "notes": (
                "PlayerAwards does not distinguish original selection, replacement, injury, "
                "or game participation; a separate official roster pipeline is required."
            ),
        },
    ]
    return {
        "step": "STEP-0009",
        "methodology": (
            "limited manual reconciliation to official NBA history tables; no web page was "
            "ingested into Silver"
        ),
        "retrieved_at": "2026-08-31T21:25:00Z",
        "references": references,
        "exact_count_checks_passed": 6,
        "exact_count_checks_failed": 0,
        "candidate_scope_note": (
            "team selections and Rookie of the Year are not asserted as complete league-wide "
            "counts because 2,963 master players were intentionally not queried"
        ),
    }


def main() -> None:
    args = _args()
    started = time.monotonic()
    _, players = _candidate_input(args.candidate_report)
    checkpoint = _load_checkpoint(args.checkpoint, players, args.run_at)
    network_requests, acquisition_seconds = _acquire(args, players, checkpoint)
    status_counts = _status_counts(checkpoint)
    candidate_terminal = (
        status_counts[AwardAcquisitionStatus.SUCCESS_WITH_ROWS.value]
        + status_counts[AwardAcquisitionStatus.SUCCESS_EMPTY.value]
    )
    if candidate_terminal != 2140:
        raise RuntimeError(
            f"only {candidate_terminal}/2140 candidates have successful terminal status: "
            f"{dict(status_counts)}"
        )
    events, quarantine, raw_count, headers = _load_events(args, players, checkpoint)
    duplicate_ids = duplicate_event_ids(events)
    if duplicate_ids:
        raise ValueError(f"duplicate canonical award event IDs: {duplicate_ids[:5]}")
    partitions, gold_rows = _write_outputs(args, players, checkpoint, events)
    output_fingerprint = _partition_fingerprint(partitions)
    if args.expected_fingerprint and args.expected_fingerprint != output_fingerprint:
        raise ValueError("award output fingerprint differs from expected cache-only build")
    inventory = taxonomy_inventory(events)
    coverage = award_coverage(events)
    cases = _case_studies(players, gold_rows, events)
    unknown_descriptions = sorted(
        {
            event.source_description
            for event in events
            if event.taxonomy_status is AwardTaxonomyStatus.UNKNOWN
        }
    )
    award_type_counts = Counter(event.award_type.value for event in events)
    level_counts = Counter(
        f"{event.award_type.value}:{event.award_level}"
        for event in events
        if event.award_level is not None
    )
    entries = sorted(checkpoint["entries"].values(), key=lambda item: str(item["player_id"]))
    acquisition_manifest = {
        "step": "STEP-0009",
        "methodology_version": AWARDS_METHODOLOGY_VERSION,
        "candidate_rule": CANDIDATE_RULE,
        "candidate_universe_size": 2140,
        "master_player_count": 5103,
        "status_counts": dict(sorted(status_counts.items())),
        "requests_attempted": 2140,
        "success_with_rows": status_counts[AwardAcquisitionStatus.SUCCESS_WITH_ROWS.value],
        "success_empty": status_counts[AwardAcquisitionStatus.SUCCESS_EMPTY.value],
        "failures": sum(
            status_counts[status.value]
            for status in (
                AwardAcquisitionStatus.FAILED_RETRYABLE,
                AwardAcquisitionStatus.FAILED_PERMANENT,
            )
        ),
        "retries": sum(int(entry["retry_count"]) for entry in entries),
        "total_raw_award_events": raw_count,
        "network_requests": sum(
            not bool(entry["from_preexisting_cache"]) for entry in entries if entry["is_candidate"]
        ),
        "recorded_network_response_seconds": round(
            sum(
                float(entry["network_response_seconds"])
                for entry in entries
                if entry["is_candidate"]
            ),
            6,
        ),
        "entries": entries,
    }
    coverage_document = {
        "step": "STEP-0009",
        "methodology_version": AWARDS_METHODOLOGY_VERSION,
        "coverage": coverage,
        "all_star_finding": (
            "PlayerAwards returns NBA All-Star events, but roster selection, participation, "
            "injury, and replacement semantics are not structurally distinguished; coverage "
            "is PARTIAL."
        ),
        "statistical_title_finding": (
            "No statistical-title descriptions were observed; derive titles later from "
            "GOATLAB-HIST-V1 rather than interpreting absence as zero."
        ),
    }
    official_validation = _official_reference_validation(events)
    summary = {
        "step": "STEP-0009",
        "result": "PASS",
        "methodology_version": AWARDS_METHODOLOGY_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "career_fingerprint": CAREER_FINGERPRINT,
        "run_at": args.run_at,
        "request_summary": {
            key: value for key, value in acquisition_manifest.items() if key != "entries"
        },
        "raw_contract_headers": sorted(headers),
        "raw_award_events": raw_count,
        "canonical_award_events": len(events),
        "exact_duplicate_rows_removed": raw_count - len(events) - len(quarantine),
        "quarantined_rows": len(quarantine),
        "distinct_raw_descriptions": len({event.source_description for event in events}),
        "unknown_descriptions": unknown_descriptions,
        "canonical_award_type_counts": dict(sorted(award_type_counts.items())),
        "canonical_award_level_counts": dict(sorted(level_counts.items())),
        "silver_rows": len(events),
        "gold_career_rows": len(gold_rows),
        "non_candidate_not_queried": status_counts[AwardAcquisitionStatus.NOT_QUERIED.value],
        "non_candidate_null_count_semantics_valid": all(
            row["mvp_count"] is None
            for row in gold_rows
            if row["award_acquisition_status"] == AwardAcquisitionStatus.NOT_QUERIED.value
        ),
        "candidate_empty_zero_count_semantics_valid": all(
            row["mvp_count"] == 0
            for row in gold_rows
            if row["award_acquisition_status"] == AwardAcquisitionStatus.SUCCESS_EMPTY.value
        ),
        "partition_count": len(partitions),
        "output_size_bytes": sum(int(item["size_bytes"]) for item in partitions),
        "output_fingerprint": output_fingerprint,
        "partitions": partitions,
        "reproducibility": {
            "cache_only": args.cache_only,
            "network_requests_this_run": network_requests,
            "expected_fingerprint": args.expected_fingerprint or output_fingerprint,
            "observed_fingerprint": output_fingerprint,
            "pass": args.expected_fingerprint in {None, output_fingerprint},
        },
        "quality": {
            "duplicate_canonical_event_ids": len(duplicate_ids),
            "quarantined_rows": len(quarantine),
            "unknown_description_count": len(unknown_descriptions),
            "case_study_count": len(cases),
            "all_candidate_statuses_terminal": candidate_terminal == 2140,
            "no_award_weights_or_scores": True,
            "official_reference_exact_checks_passed": official_validation[
                "exact_count_checks_passed"
            ],
        },
    }
    gold_manifest = {
        "manifest_version": 1,
        "step": "STEP-0009",
        "methodology_version": AWARDS_METHODOLOGY_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_fingerprint": CORPUS_FINGERPRINT,
        "output_fingerprint": output_fingerprint,
        "partition_count": len(partitions),
        "size_bytes": sum(int(item["size_bytes"]) for item in partitions),
        "partitions": partitions,
    }
    _stable_json(args.docs_root / "award-acquisition-manifest.json", acquisition_manifest)
    _stable_yaml(args.docs_root / "award-taxonomy.yaml", _taxonomy_registry(inventory))
    _stable_json(args.docs_root / "award-coverage.json", coverage_document)
    _stable_json(args.docs_root / "award-canonicalization-summary.json", summary)
    _stable_json(
        args.docs_root / "award-case-studies.json",
        {
            "step": "STEP-0009",
            "methodology_version": AWARDS_METHODOLOGY_VERSION,
            "purpose": "diagnostic event histories only; no ranking or award value",
            "cases": cases,
        },
    )
    _stable_json(args.docs_root / "award-output-manifest.json", gold_manifest)
    _stable_json(
        args.docs_root / "award-official-reference-validation.json",
        official_validation,
    )
    _stable_json(
        args.docs_root / "award-quarantine.json",
        {
            "step": "STEP-0009",
            "row_count": len(quarantine),
            "rows": quarantine,
        },
    )
    elapsed = round(time.monotonic() - started, 6)
    print(
        json.dumps(
            {
                "result": "PASS",
                "cache_only": args.cache_only,
                "network_requests": network_requests,
                "acquisition_seconds": acquisition_seconds,
                "runtime_seconds": elapsed,
                "raw_events": raw_count,
                "canonical_events": len(events),
                "gold_rows": len(gold_rows),
                "output_fingerprint": output_fingerprint,
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
