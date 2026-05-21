from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_json_object,
    write_schema_backed_report,
)
from ops.scripts.codex_goal_client import DEFAULT_CONTRACT_PATH, FileGoalBackend
from ops.scripts.filesystem_runtime import atomic_write_text
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext

from .goal_runtime_maintenance import (
    PERIODIC_EVIDENCE_CHECKPOINTS,
    build_goal_health,
    build_periodic_evidence,
    health_blockers,
)
from .goal_runtime_certificate import (
    DEFAULT_RUNTIME_MODE,
    build_runtime_certificate,
    runtime_certificate_blockers,
)
from .goal_runtime_resume import mapping_field, resume_metadata_from_report


DEFAULT_STATUS_PATH = "ops/reports/goal-run-status.json"
DEFAULT_RUN_ROOT_TEMPLATE = "runs/goal-{run_id}"
SESSION_SYNOPSIS_PATH = "ops/reports/session-synopsis.json"
PRODUCER = "ops.scripts.goal_run_status"
SCHEMA_PATH = "ops/schemas/goal-run-status.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_run_status --vault ."
TERMINAL_RUN_STATUSES = {"completed", "failed", "stopped"}
STATUS_REFRESH_RUN_STATUSES = {"running", "blocked"}


@dataclass(frozen=True)
class GoalRunStatusRequest:
    vault: Path
    run_id: str
    goal_contract_path: str = DEFAULT_CONTRACT_PATH
    status: str = "running"
    runtime_mode: str = DEFAULT_RUNTIME_MODE
    started_at: str = ""
    completed_at: str = ""
    heartbeat_interval_seconds: int = 300
    checkpoint_interval_seconds: int = 1800
    last_heartbeat_at: str = ""
    last_checkpoint_at: str = ""
    last_command_heartbeat_at: str = ""
    quiet_seconds: int = 0
    command_observation_mode: str = ""
    command_heartbeat_count: int = 0
    command_timeout_seconds: int = 0
    last_stdout_at: str = ""
    last_stderr_at: str = ""
    last_artifact_touch_at: str = ""
    last_command_returncode: int = -1
    last_command_timed_out: bool = False
    last_command_termination_reason: str = ""
    last_backoff_until: str = ""
    backoff_reason: str = ""
    resume_from_checkpoint: bool = False
    resume_command: str = ""
    status_report_path: str = DEFAULT_STATUS_PATH
    out_path: str | None = None
    policy_path: str | None = None
    context: RuntimeContext | None = None


@dataclass(frozen=True)
class GoalRunArtifactPaths:
    status_report_path: str
    status_markdown_path: str
    audit_log_path: str
    resume_metadata_path: str
    checkpoint_command_log_path: str


def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def goal_run_artifact_paths(run_id: str, *, status_report_path: str = DEFAULT_STATUS_PATH) -> GoalRunArtifactPaths:
    run_root = DEFAULT_RUN_ROOT_TEMPLATE.format(run_id=run_id)
    status_path = PurePosixPath(status_report_path)
    expected_state_prefix = f"{run_root}/state/"
    if status_report_path.startswith(expected_state_prefix):
        state_root = status_path.parent.as_posix()
        return GoalRunArtifactPaths(
            status_report_path=status_report_path,
            status_markdown_path=f"{state_root}/status.md",
            audit_log_path=f"{state_root}/audit-log.jsonl",
            resume_metadata_path=f"{state_root}/resume-metadata.json",
            checkpoint_command_log_path=f"{state_root}/checkpoint-command-events.jsonl",
        )
    return GoalRunArtifactPaths(
        status_report_path=status_report_path,
        status_markdown_path=f"{run_root}/status.md",
        audit_log_path=f"{run_root}/audit-log.jsonl",
        resume_metadata_path=f"{run_root}/resume-metadata.json",
        checkpoint_command_log_path=f"{run_root}/checkpoint-command-events.jsonl",
    )


def _status_from_blockers(run_status: str, blockers: list[str]) -> str:
    if run_status in {"failed", "stopped"}:
        return "fail"
    if blockers or run_status in {"blocked", "paused"}:
        return "attention"
    return "pass"


def _integer_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _session_synopsis_link(vault: Path) -> dict[str, Any]:
    synopsis = load_optional_json_object(vault / SESSION_SYNOPSIS_PATH)
    if not synopsis:
        return {
            "link_status": "missing",
            "report_path": SESSION_SYNOPSIS_PATH,
            "status": "",
            "generated_at": "",
            "recent_blocker_count": 0,
            "evidence_gap_count": 0,
            "next_action": "Run make session-synopsis to refresh next-session context.",
        }
    summary = synopsis.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    return {
        "link_status": "linked",
        "report_path": SESSION_SYNOPSIS_PATH,
        "status": str(synopsis.get("status", "")).strip(),
        "generated_at": str(synopsis.get("generated_at", "")).strip(),
        "recent_blocker_count": _integer_value(summary.get("recent_blocker_count")),
        "evidence_gap_count": _integer_value(summary.get("evidence_gap_count")),
        "next_action": str(summary.get("next_action", "")).strip(),
    }


def _request_from_legacy(
    vault_or_request: Path | GoalRunStatusRequest,
    legacy_fields: dict[str, Any],
) -> GoalRunStatusRequest:
    if isinstance(vault_or_request, GoalRunStatusRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        return vault_or_request
    return GoalRunStatusRequest(vault=Path(vault_or_request), **legacy_fields)


def _prior_status_for_run(vault: Path, request: GoalRunStatusRequest) -> Mapping[str, Any]:
    prior_report = load_optional_json_object(vault / request.status_report_path)
    prior_run = mapping_field(prior_report, "run")
    prior_status = str(prior_run.get("status", "")).strip()
    same_run = str(prior_run.get("run_id", "")).strip() == request.run_id
    if same_run and prior_status in {"running", "paused", *TERMINAL_RUN_STATUSES}:
        return prior_report
    return {}


def _should_preserve_terminal_run_status(
    request: GoalRunStatusRequest,
    prior_report: Mapping[str, Any],
) -> bool:
    prior_status = _prior_text_field(prior_report, "run", "status")
    if prior_status not in TERMINAL_RUN_STATUSES:
        return False
    if request.status not in STATUS_REFRESH_RUN_STATUSES:
        return False
    return not bool(request.started_at or request.completed_at)


def _prior_text_field(prior_report: Mapping[str, Any], section: str, field: str) -> str:
    return str(mapping_field(prior_report, section).get(field, "")).strip()


def _prior_int_field(
    prior_report: Mapping[str, Any],
    section: str,
    field: str,
    *,
    default: int = 0,
) -> int:
    section_payload = mapping_field(prior_report, section)
    if field not in section_payload:
        return default
    return _integer_value(section_payload.get(field))


def _prior_bool_field(prior_report: Mapping[str, Any], section: str, field: str) -> bool:
    value = mapping_field(prior_report, section).get(field)
    return bool(value) if isinstance(value, bool) else False


def build_report(
    vault_or_request: Path | GoalRunStatusRequest,
    **legacy_fields: Any,
) -> dict[str, Any]:
    request = _request_from_legacy(vault_or_request, legacy_fields)
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    prior_report = _prior_status_for_run(vault, request)
    preserve_terminal_status = _should_preserve_terminal_run_status(request, prior_report)
    run_status = (
        _prior_text_field(prior_report, "run", "status")
        if preserve_terminal_status
        else request.status
    )
    completed_at = (
        request.completed_at
        or (
            _prior_text_field(prior_report, "run", "completed_at")
            if preserve_terminal_status
            else ""
        )
    )
    started_at = request.started_at or _prior_text_field(prior_report, "run", "started_at") or generated_at
    last_heartbeat_at = (
        request.last_heartbeat_at
        or _prior_text_field(prior_report, "observability", "last_heartbeat_at")
        or generated_at
    )
    last_checkpoint_at = (
        request.last_checkpoint_at
        or _prior_text_field(prior_report, "observability", "last_checkpoint_at")
        or generated_at
    )
    last_command_heartbeat_at = (
        request.last_command_heartbeat_at
        or _prior_text_field(prior_report, "observability", "last_command_heartbeat_at")
    )
    command_observation_mode = (
        request.command_observation_mode
        or _prior_text_field(prior_report, "observability", "command_observation_mode")
    )
    command_heartbeat_count = request.command_heartbeat_count or _prior_int_field(
        prior_report,
        "observability",
        "command_heartbeat_count",
    )
    command_timeout_seconds = request.command_timeout_seconds or _prior_int_field(
        prior_report,
        "observability",
        "command_timeout_seconds",
    )
    last_stdout_at = request.last_stdout_at or _prior_text_field(
        prior_report,
        "observability",
        "last_stdout_at",
    )
    last_stderr_at = request.last_stderr_at or _prior_text_field(
        prior_report,
        "observability",
        "last_stderr_at",
    )
    last_artifact_touch_at = request.last_artifact_touch_at or _prior_text_field(
        prior_report,
        "observability",
        "last_artifact_touch_at",
    )
    last_command_returncode = (
        request.last_command_returncode
        if request.last_command_returncode != -1
        else _prior_int_field(
            prior_report,
            "observability",
            "last_command_returncode",
            default=-1,
        )
    )
    last_command_timed_out = request.last_command_timed_out or _prior_bool_field(
        prior_report,
        "observability",
        "last_command_timed_out",
    )
    last_command_termination_reason = (
        request.last_command_termination_reason
        or _prior_text_field(prior_report, "observability", "last_command_termination_reason")
    )
    last_backoff_until = (
        request.last_backoff_until
        or _prior_text_field(prior_report, "observability", "last_backoff_until")
    )
    backoff_reason = request.backoff_reason or _prior_text_field(
        prior_report,
        "observability",
        "backoff_reason",
    )
    resume_command = request.resume_command or _prior_text_field(
        prior_report,
        "observability",
        "resume_command",
    )
    resume_from_checkpoint = request.resume_from_checkpoint or bool(
        mapping_field(prior_report, "observability").get("resume_from_checkpoint", False)
    )
    backend = FileGoalBackend(vault=vault, contract_path=request.goal_contract_path)
    contract = backend.get_goal()
    contract_backend = mapping_field(contract, "goal_backend")
    backend_name = str(contract_backend.get("backend_type", "")).strip() or backend.name
    promotion_guard = contract.get("promotion_guard")
    if not isinstance(promotion_guard, dict):
        promotion_guard = {}
    raw_blockers = promotion_guard.get("promotion_blockers")
    promotion_blockers = [str(item) for item in raw_blockers] if isinstance(raw_blockers, list) else []
    health = build_goal_health(
        generated_at=generated_at,
        promotion_guard=promotion_guard,
        heartbeat_interval_seconds=request.heartbeat_interval_seconds,
        checkpoint_interval_seconds=request.checkpoint_interval_seconds,
        last_heartbeat_at=last_heartbeat_at,
        last_checkpoint_at=last_checkpoint_at,
        last_command_heartbeat_at=last_command_heartbeat_at,
        last_backoff_until=last_backoff_until,
        resume_from_checkpoint=resume_from_checkpoint,
        resume_command=resume_command,
    )
    paths = goal_run_artifact_paths(
        request.run_id,
        status_report_path=request.status_report_path,
    )
    periodic_generated_at = (
        completed_at
        if run_status in TERMINAL_RUN_STATUSES and completed_at
        else generated_at
    )
    periodic_evidence = build_periodic_evidence(
        vault,
        generated_at=periodic_generated_at,
        started_at=started_at,
        last_checkpoint_at=last_checkpoint_at,
        checkpoint_command_log_path=paths.checkpoint_command_log_path,
        checkpoints_config=PERIODIC_EVIDENCE_CHECKPOINTS,
    )
    runtime_certificate = build_runtime_certificate(
        vault,
        contract=contract,
        run_mode=request.runtime_mode,
    )
    session_synopsis = _session_synopsis_link(vault)
    blockers = list(
        dict.fromkeys(
            [
                    *promotion_blockers,
                    *runtime_certificate_blockers(runtime_certificate),
                    *health_blockers(
                        health,
                        run_status=run_status,
                        periodic_evidence=periodic_evidence,
                    ),
            ]
        )
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="goal_run_status",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_run_status.py",
                "ops/scripts/mechanism/goal_runtime_backoff.py",
                "ops/scripts/mechanism/goal_runtime_maintenance.py",
                "ops/scripts/mechanism/goal_runtime_certificate.py",
                "ops/scripts/mechanism/goal_runtime_resume.py",
                "ops/scripts/core/codex_goal_client.py",
                "ops/schemas/goal-run-status.schema.json",
                "ops/schemas/codex-goal-contract.schema.json",
            ],
            file_inputs={"goal_contract": request.goal_contract_path},
            text_inputs={"session_synopsis_link": SESSION_SYNOPSIS_PATH},
            source_tree_excluded_files=(request.status_report_path,),
        ),
        "goal": {
            "contract_path": request.goal_contract_path,
            "contract_sha256": _canonical_json_digest(contract),
            "contract_status": "loaded",
            "contract_id": str(contract.get("contract_id", "")).strip(),
            "objective": str(contract.get("objective", "")).strip(),
            "goal_status": str(contract.get("status", "")).strip(),
            "backend": {
                "name": backend_name,
                "process_persistent": backend.process_persistent,
            },
        },
        "run": {
            "run_id": request.run_id,
            "status": run_status,
            "runtime_mode": request.runtime_mode,
            "started_at": started_at,
            "updated_at": generated_at,
            "completed_at": completed_at,
        },
        "observability": {
            "heartbeat_interval_seconds": request.heartbeat_interval_seconds,
            "checkpoint_interval_seconds": request.checkpoint_interval_seconds,
            "last_heartbeat_at": last_heartbeat_at,
            "last_checkpoint_at": last_checkpoint_at,
            "last_command_heartbeat_at": last_command_heartbeat_at,
            "quiet_seconds": request.quiet_seconds,
            "command_observation_mode": command_observation_mode,
            "command_heartbeat_count": command_heartbeat_count,
            "command_timeout_seconds": command_timeout_seconds,
            "last_stdout_at": last_stdout_at,
            "last_stderr_at": last_stderr_at,
            "last_artifact_touch_at": last_artifact_touch_at,
            "last_command_returncode": last_command_returncode,
            "last_command_timed_out": last_command_timed_out,
            "last_command_termination_reason": last_command_termination_reason,
            "last_backoff_until": last_backoff_until,
            "backoff_reason": backoff_reason,
            "resume_from_checkpoint": resume_from_checkpoint,
            "resume_command": resume_command,
        },
        "health": health,
        "runtime_certificate": runtime_certificate,
        "periodic_evidence": periodic_evidence,
        "session_synopsis": session_synopsis,
        "artifacts": {
            "status_report_path": paths.status_report_path,
            "status_markdown_path": paths.status_markdown_path,
            "audit_log_path": paths.audit_log_path,
            "resume_metadata_path": paths.resume_metadata_path,
            "checkpoint_command_log_path": paths.checkpoint_command_log_path,
        },
        "promotion_guard": promotion_guard,
        "blockers": blockers,
        "status": _status_from_blockers(run_status, blockers),
    }


def write_report(vault: Path, report: Mapping[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_STATUS_PATH,
            context="goal run status schema validation failed",
            trailing_newline=True,
        )
    )


def build_status_markdown(report: Mapping[str, Any]) -> str:
    goal = mapping_field(report, "goal")
    run = mapping_field(report, "run")
    observability = mapping_field(report, "observability")
    health = mapping_field(report, "health")
    runtime_certificate = mapping_field(report, "runtime_certificate")
    periodic_evidence = mapping_field(report, "periodic_evidence")
    session_synopsis = mapping_field(report, "session_synopsis")
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    blocker_text = "\n".join(f"- {item}" for item in blockers) if blockers else "- none"
    missing_due = periodic_evidence.get("missing_due_checkpoint_ids", [])
    missing_due_text = ", ".join(str(item) for item in missing_due) if missing_due else "none"
    checkpoint_command_log = mapping_field(report, "artifacts").get(
        "checkpoint_command_log_path",
        "",
    )
    return "\n".join(
        [
            f"# Goal Run {run.get('run_id', '')}",
            "",
            f"- status: {run.get('status', '')}",
            f"- runtime_mode: {run.get('runtime_mode', '')}",
            f"- goal: {goal.get('contract_id', '')}",
            f"- contract_sha256: {goal.get('contract_sha256', '')}",
            f"- last_heartbeat_at: {observability.get('last_heartbeat_at', '')}",
            f"- last_checkpoint_at: {observability.get('last_checkpoint_at', '')}",
            f"- last_command_heartbeat_at: {observability.get('last_command_heartbeat_at', '')}",
            f"- command_observation_mode: {observability.get('command_observation_mode', '')}",
            f"- command_heartbeat_count: {observability.get('command_heartbeat_count', 0)}",
            f"- command_timeout_seconds: {observability.get('command_timeout_seconds', 0)}",
            f"- last_command_termination_reason: {observability.get('last_command_termination_reason', '')}",
            f"- last_backoff_until: {observability.get('last_backoff_until', '')}",
            f"- resume_from_checkpoint: {observability.get('resume_from_checkpoint', False)}",
            f"- heartbeat_status: {health.get('heartbeat_status', '')}",
            f"- checkpoint_status: {health.get('checkpoint_status', '')}",
            f"- command_heartbeat_status: {health.get('command_heartbeat_status', '')}",
            f"- backoff_status: {health.get('backoff_status', '')}",
            f"- resume_status: {health.get('resume_status', '')}",
            f"- promotion_status: {health.get('promotion_status', '')}",
            f"- runtime_certificate_status: {runtime_certificate.get('status', '')}",
            f"- runtime_certificate_verified: {runtime_certificate.get('certificate_status', '')}",
            f"- full_gate_clean: {runtime_certificate.get('full_gate_clean', False)}",
            f"- periodic_evidence_status: {periodic_evidence.get('status', '')}",
            f"- missing_due_checkpoints: {missing_due_text}",
            f"- checkpoint_command_log: {checkpoint_command_log}",
            f"- session_synopsis: {session_synopsis.get('report_path', '')}",
            f"- session_synopsis_status: {session_synopsis.get('status', '')}",
            "",
            "## Promotion Blockers",
            blocker_text,
            "",
        ]
    )


def write_run_artifacts(
    vault: Path,
    report: Mapping[str, Any],
    *,
    writer: str = PRODUCER,
) -> list[Path]:
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("goal run status report missing artifacts")
    status_markdown = vault / str(artifacts["status_markdown_path"])
    resume_metadata = vault / str(artifacts["resume_metadata_path"])
    audit_log = vault / str(artifacts["audit_log_path"])
    atomic_write_text(status_markdown, build_status_markdown(report))
    write_json_object(
        resume_metadata,
        resume_metadata_from_report(report),
        trailing_newline=True,
    )
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event": "goal_run_status_written",
        "writer": writer,
        "generated_at": str(report.get("generated_at", "")),
        "run_id": mapping_field(report, "run").get("run_id", ""),
        "run_status": mapping_field(report, "run").get("status", ""),
        "status": report.get("status", ""),
        "heartbeat_status": mapping_field(report, "health").get("heartbeat_status", ""),
        "checkpoint_status": mapping_field(report, "health").get("checkpoint_status", ""),
        "command_heartbeat_status": mapping_field(report, "health").get("command_heartbeat_status", ""),
        "command_observation_mode": mapping_field(report, "observability").get(
            "command_observation_mode",
            "",
        ),
        "command_heartbeat_count": mapping_field(report, "observability").get(
            "command_heartbeat_count",
            0,
        ),
        "quiet_seconds": mapping_field(report, "observability").get("quiet_seconds", 0),
        "last_command_returncode": mapping_field(report, "observability").get(
            "last_command_returncode",
            -1,
        ),
        "last_command_timed_out": mapping_field(report, "observability").get(
            "last_command_timed_out",
            False,
        ),
        "last_command_termination_reason": mapping_field(report, "observability").get(
            "last_command_termination_reason",
            "",
        ),
    }
    with audit_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return [status_markdown, resume_metadata, audit_log]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--goal-contract", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", default="running")
    parser.add_argument("--runtime-mode", default=DEFAULT_RUNTIME_MODE)
    parser.add_argument("--profile", dest="runtime_mode", default=argparse.SUPPRESS)
    parser.add_argument("--started-at", default="")
    parser.add_argument("--completed-at", default="")
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=300)
    parser.add_argument("--checkpoint-interval-seconds", type=int, default=1800)
    parser.add_argument("--last-heartbeat-at", default="")
    parser.add_argument("--last-checkpoint-at", default="")
    parser.add_argument("--last-command-heartbeat-at", default="")
    parser.add_argument("--quiet-seconds", type=int, default=0)
    parser.add_argument("--last-backoff-until", default="")
    parser.add_argument("--backoff-reason", default="")
    parser.add_argument("--resume-from-checkpoint", action="store_true")
    parser.add_argument("--resume-command", default="")
    parser.add_argument("--status-report-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--out", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--write-run-artifacts", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRunStatusRequest(
            vault=vault,
            run_id=args.run_id,
            goal_contract_path=args.goal_contract,
            status=args.status,
            runtime_mode=args.runtime_mode,
            started_at=args.started_at,
            completed_at=args.completed_at,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
            checkpoint_interval_seconds=args.checkpoint_interval_seconds,
            last_heartbeat_at=args.last_heartbeat_at,
            last_checkpoint_at=args.last_checkpoint_at,
            last_command_heartbeat_at=args.last_command_heartbeat_at,
            quiet_seconds=args.quiet_seconds,
            last_backoff_until=args.last_backoff_until,
            backoff_reason=args.backoff_reason,
            resume_from_checkpoint=args.resume_from_checkpoint,
            resume_command=args.resume_command,
            status_report_path=args.status_report_path,
            out_path=args.out,
        )
    )
    destination = write_report(vault, report, args.out)
    if args.write_run_artifacts:
        write_run_artifacts(vault, report)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
