from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .goal_runtime_backoff import backoff_status, freshness_status, parse_iso_z
from .goal_runtime_resume import resume_status

PERIODIC_EVIDENCE_CHECKPOINTS: list[dict[str, Any]] = [
    {
        "checkpoint_id": "checkpoint_6h",
        "due_after_seconds": 21600,
        "commands": [
            "make auto-improve-readiness-report-body",
            "make session-synopsis",
            "make static",
        ],
        "evidence_paths": [
            "ops/reports/auto-improve-readiness.json",
            "ops/reports/session-synopsis.json",
        ],
    },
    {
        "checkpoint_id": "checkpoint_12h",
        "due_after_seconds": 43200,
        "commands": [
            "make test-execution-summary-report-contract",
            "make release-source-package-check",
        ],
        "evidence_paths": [
            "ops/reports/test-execution-summary.json",
            "ops/reports/source-package-clean-extract.json",
        ],
    },
    {
        "checkpoint_id": "checkpoint_24h",
        "due_after_seconds": 86400,
        "commands": [
            "make public-check",
            "make release-authority-sealed-preflight",
        ],
        "evidence_paths": [
            "ops/reports/public-check-summary.json",
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
        ],
    },
]

PERIODIC_CHECKPOINT_COMMAND_EVENT = "goal_periodic_checkpoint_commands_completed"


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def periodic_checkpoint_status(*, due: bool, observed: bool) -> str:
    if not due:
        return "pending"
    if observed:
        return "observed"
    return "missing"


def periodic_evidence_status(checkpoints: Sequence[Mapping[str, Any]]) -> str:
    due = [item for item in checkpoints if item["due"]]
    if not due:
        return "not_due"
    if all(item["status"] == "observed" for item in due):
        return "current"
    return "missing_due_evidence"


def _json_generated_at(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, Mapping):
        return ""
    return str(payload.get("generated_at", "")).strip()


def _evidence_freshness_status(*, due: bool, due_at: dt.datetime | None, generated_at: str) -> str:
    if not due:
        return "not_due"
    generated = parse_iso_z(generated_at)
    if due_at is not None and generated is not None and generated >= due_at:
        return "fresh"
    return "stale"


def _evidence_path_status(
    vault: Path,
    path: str,
    *,
    due: bool,
    due_at: dt.datetime | None,
) -> dict[str, Any]:
    evidence_path = vault / path
    if not evidence_path.is_file():
        return {
            "path": path,
            "status": "missing",
            "generated_at": "",
            "freshness_status": "missing",
        }
    generated_at = _json_generated_at(evidence_path)
    return {
        "path": path,
        "status": "present",
        "generated_at": generated_at,
        "freshness_status": _evidence_freshness_status(
            due=due,
            due_at=due_at,
            generated_at=generated_at,
        ),
    }


def _load_checkpoint_command_events(vault: Path, path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    event_path = vault / path
    if not event_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for raw_line in event_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def append_checkpoint_command_event(vault: Path, path: str, event: Mapping[str, Any]) -> None:
    event_path = vault / path
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(event), ensure_ascii=False, sort_keys=True) + "\n")


def _checkpoint_command_run_summary(
    *,
    checkpoint_id: str,
    due: bool,
    due_at: dt.datetime | None,
    commands: Sequence[str],
    checkpoint_command_log_path: str,
    command_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    base = {
        "status": "not_due" if not due else "not_run",
        "last_event_at": "",
        "command_count": len(commands),
        "failed_command_count": 0,
        "log_path": checkpoint_command_log_path,
    }
    if not due or due_at is None:
        return base

    matching_events: list[tuple[dt.datetime, Mapping[str, Any]]] = []
    for event in command_events:
        if str(event.get("event", "")).strip() != PERIODIC_CHECKPOINT_COMMAND_EVENT:
            continue
        if str(event.get("checkpoint_id", "")).strip() != checkpoint_id:
            continue
        generated = parse_iso_z(str(event.get("generated_at", "")).strip())
        if generated is None or generated < due_at:
            continue
        matching_events.append((generated, event))
    if not matching_events:
        return base

    generated, latest = sorted(matching_events, key=lambda item: item[0])[-1]
    failed_count = int(latest.get("failed_command_count", 0) or 0)
    status = "pass" if str(latest.get("status", "")).strip() == "pass" else "fail"
    return {
        **base,
        "status": status,
        "last_event_at": iso_z(generated),
        "command_count": int(latest.get("command_count", len(commands)) or len(commands)),
        "failed_command_count": failed_count,
    }


def checkpoint_command_retry_due(
    *,
    generated_at: str,
    command_run: Mapping[str, Any],
    retry_after_seconds: int,
) -> bool:
    if command_run.get("status") in {"not_due", "pass"}:
        return False
    last_event_at = parse_iso_z(str(command_run.get("last_event_at", "")).strip())
    now = parse_iso_z(generated_at)
    if last_event_at is None or now is None:
        return True
    return (now - last_event_at).total_seconds() >= retry_after_seconds


def build_periodic_evidence(
    vault: Path,
    *,
    generated_at: str,
    started_at: str,
    last_checkpoint_at: str,
    checkpoint_command_log_path: str = "",
    checkpoints_config: Sequence[Mapping[str, Any]] = PERIODIC_EVIDENCE_CHECKPOINTS,
) -> dict[str, Any]:
    started = parse_iso_z(started_at)
    now = parse_iso_z(generated_at)
    last_checkpoint = parse_iso_z(last_checkpoint_at)
    command_events = _load_checkpoint_command_events(vault, checkpoint_command_log_path)
    checkpoints: list[dict[str, Any]] = []
    for checkpoint in checkpoints_config:
        due_after_seconds = int(checkpoint["due_after_seconds"])
        commands = [str(command) for command in checkpoint["commands"]]
        due_at = started + dt.timedelta(seconds=due_after_seconds) if started else None
        due = bool(due_at is not None and now is not None and now >= due_at)
        evidence_paths = [
            _evidence_path_status(
                vault,
                str(path),
                due=due,
                due_at=due_at,
            )
            for path in checkpoint["evidence_paths"]
        ]
        command_run = _checkpoint_command_run_summary(
            checkpoint_id=str(checkpoint["checkpoint_id"]),
            due=due,
            due_at=due_at,
            commands=commands,
            checkpoint_command_log_path=checkpoint_command_log_path,
            command_events=command_events,
        )
        evidence_complete = all(
            item["status"] == "present"
            and (not due or item["freshness_status"] == "fresh")
            for item in evidence_paths
        )
        checkpoint_observed = bool(
            due
            and last_checkpoint is not None
            and due_at is not None
            and last_checkpoint >= due_at
            and evidence_complete
            and command_run["status"] == "pass"
        )
        checkpoints.append(
            {
                "checkpoint_id": checkpoint["checkpoint_id"],
                "due_after_seconds": due_after_seconds,
                "due_at": iso_z(due_at) if due_at else "",
                "due": due,
                "status": periodic_checkpoint_status(
                    due=due,
                    observed=checkpoint_observed,
                ),
                "commands": list(checkpoint["commands"]),
                "command_run": command_run,
                "evidence_paths": evidence_paths,
            }
        )
    missing_due_ids = [
        str(item["checkpoint_id"])
        for item in checkpoints
        if item["due"] and item["status"] != "observed"
    ]
    next_checkpoint_id = ""
    for item in checkpoints:
        if not item["due"]:
            next_checkpoint_id = str(item["checkpoint_id"])
            break
    return {
        "status": periodic_evidence_status(checkpoints),
        "schedule": "6h_12h_24h",
        "observed_checkpoint_count": sum(1 for item in checkpoints if item["status"] == "observed"),
        "due_checkpoint_count": sum(1 for item in checkpoints if item["due"]),
        "missing_due_checkpoint_ids": missing_due_ids,
        "next_checkpoint_id": next_checkpoint_id,
        "checkpoints": checkpoints,
    }


def promotion_status(promotion_guard: Mapping[str, Any]) -> str:
    if bool(promotion_guard.get("can_promote_result", False)):
        return "allowed"
    return "blocked"


def build_goal_health(
    *,
    generated_at: str,
    promotion_guard: Mapping[str, Any],
    heartbeat_interval_seconds: int,
    checkpoint_interval_seconds: int,
    last_heartbeat_at: str,
    last_checkpoint_at: str,
    last_command_heartbeat_at: str,
    last_backoff_until: str,
    resume_from_checkpoint: bool,
    resume_command: str,
) -> dict[str, Any]:
    return {
        "heartbeat_status": freshness_status(
            now_iso=generated_at,
            observed_iso=last_heartbeat_at,
            interval_seconds=heartbeat_interval_seconds,
        ),
        "checkpoint_status": freshness_status(
            now_iso=generated_at,
            observed_iso=last_checkpoint_at,
            interval_seconds=checkpoint_interval_seconds,
        ),
        "command_heartbeat_status": freshness_status(
            now_iso=generated_at,
            observed_iso=last_command_heartbeat_at,
            interval_seconds=heartbeat_interval_seconds,
            allow_not_recorded=True,
        ),
        "backoff_status": backoff_status(generated_at, last_backoff_until),
        "resume_status": resume_status(
            resume_from_checkpoint=resume_from_checkpoint,
            resume_command=resume_command,
        ),
        "promotion_status": promotion_status(promotion_guard),
        "can_promote_result": bool(promotion_guard.get("can_promote_result", False)),
    }


def health_blockers(
    health: Mapping[str, Any],
    *,
    run_status: str,
    periodic_evidence: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    run_is_active = run_status in {"running", "blocked", "paused"}
    if run_is_active and health.get("heartbeat_status") in {"stale", "unknown"}:
        blockers.append(f"heartbeat {health['heartbeat_status']}")
    if run_is_active and health.get("checkpoint_status") in {"stale", "unknown"}:
        blockers.append(f"checkpoint {health['checkpoint_status']}")
    if run_status == "running" and health.get("command_heartbeat_status") in {
        "stale",
        "unknown",
        "not_recorded",
    }:
        blockers.append(f"command heartbeat {health['command_heartbeat_status']}")
    if health.get("resume_status") == "missing_resume_command":
        blockers.append("resume command missing")
    missing_due = periodic_evidence.get("missing_due_checkpoint_ids")
    if isinstance(missing_due, list) and missing_due:
        blockers.append("periodic evidence checkpoint missing")
    return blockers
