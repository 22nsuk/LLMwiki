from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.codex_goal_client import DEFAULT_CONTRACT_PATH, FileGoalBackend
from ops.scripts.observability_artifacts_shared_runtime import (
    auto_improve_session_report_rel,
    resolve_auto_improve_session_report_rel,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext

from .auto_improve_session_completion_runtime import completion_class_for_session
from .goal_contract_digest_runtime import semantic_goal_contract_digest
from .goal_run_status_artifacts_runtime import (
    build_status_markdown as _build_status_markdown,
    write_run_artifacts as _write_run_artifacts,
)
from .goal_runtime_certificate import (
    DEFAULT_RUNTIME_MODE,
    build_runtime_certificate,
    runtime_certificate_blockers,
)
from .goal_runtime_maintenance import (
    PERIODIC_EVIDENCE_CHECKPOINTS,
    build_goal_health,
    build_periodic_evidence,
    health_blockers,
)
from .goal_runtime_resume import mapping_field

DEFAULT_STATUS_PATH = "ops/reports/goal-run-status.json"
DEFAULT_RUN_ROOT_TEMPLATE = "runs/goal-{run_id}"
SESSION_SYNOPSIS_PATH = "ops/reports/session-synopsis.json"
PRODUCER = "ops.scripts.goal_run_status"
SCHEMA_PATH = "ops/schemas/goal-run-status.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_run_status --vault ."
TERMINAL_RUN_STATUSES = {"completed", "failed", "stopped"}
STATUS_REFRESH_RUN_STATUSES = {"running", "blocked"}
PRIOR_CLOCK_RUN_STATUSES = {"running", "paused", "blocked", *TERMINAL_RUN_STATUSES}


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
    command_heartbeat_count: int | None = None
    command_timeout_seconds: int | None = None
    last_stdout_at: str = ""
    last_stderr_at: str = ""
    last_artifact_touch_at: str = ""
    last_command_returncode: int | None = None
    last_command_timed_out: bool | None = None
    last_command_termination_reason: str = ""
    last_backoff_until: str = ""
    backoff_reason: str = ""
    resume_from_checkpoint: bool | None = None
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


@dataclass(frozen=True)
class _MergedRunState:
    status: str
    started_at: str
    completed_at: str


@dataclass(frozen=True)
class _MergedObservability:
    last_heartbeat_at: str
    last_checkpoint_at: str
    last_command_heartbeat_at: str
    command_observation_mode: str
    command_heartbeat_count: int
    command_timeout_seconds: int
    last_stdout_at: str
    last_stderr_at: str
    last_artifact_touch_at: str
    last_command_returncode: int
    last_command_timed_out: bool
    last_command_termination_reason: str
    last_backoff_until: str
    backoff_reason: str
    resume_from_checkpoint: bool
    resume_command: str


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


def _promoted_iteration_count(iterations: object) -> int:
    if not isinstance(iterations, list):
        return 0
    return sum(
        1
        for item in iterations
        if isinstance(item, Mapping)
        and (
            str(item.get("decision", "")).strip() == "PROMOTE"
            or str(item.get("outcome", "")).strip() == "promoted"
            or str(item.get("status", "")).strip() == "promoted"
        )
    )


def _auto_improve_session_report_path(run_id: str) -> str:
    return auto_improve_session_report_rel(run_id)


def _auto_improve_session_completion_class(session: Mapping[str, Any]) -> str:
    completion_class = str(session.get("completion_class", "")).strip()
    if completion_class:
        return completion_class
    if str(session.get("status", "")).strip() != "complete":
        return ""
    return completion_class_for_session(
        session,
        stop_reason=str(session.get("stop_reason", "")).strip(),
    )


def _auto_improve_session_link(vault: Path, run_id: str) -> dict[str, Any]:
    report_path = resolve_auto_improve_session_report_rel(vault, run_id) or _auto_improve_session_report_path(run_id)
    if not report_path:
        return {
            "link_status": "missing",
            "report_path": "",
            "status": "",
            "generated_at": "",
            "stop_reason": "",
            "completion_class": "",
            "iteration_count": 0,
            "promoted_iteration_count": 0,
        }
    session = load_optional_json_object(vault / report_path)
    if not session:
        return {
            "link_status": "missing",
            "report_path": report_path,
            "status": "",
            "generated_at": "",
            "stop_reason": "",
            "completion_class": "",
            "iteration_count": 0,
            "promoted_iteration_count": 0,
        }
    iterations = session.get("iterations")
    iteration_count = len(iterations) if isinstance(iterations, list) else 0
    return {
        "link_status": "linked",
        "report_path": report_path,
        "status": str(session.get("status", "")).strip(),
        "generated_at": str(session.get("generated_at", "")).strip(),
        "stop_reason": str(session.get("stop_reason", "")).strip(),
        "completion_class": _auto_improve_session_completion_class(session),
        "iteration_count": iteration_count,
        "promoted_iteration_count": _promoted_iteration_count(iterations),
    }


def _prior_status_for_run(vault: Path, request: GoalRunStatusRequest) -> Mapping[str, Any]:
    prior_report = load_optional_json_object(vault / request.status_report_path)
    prior_run = mapping_field(prior_report, "run")
    prior_status = str(prior_run.get("status", "")).strip()
    same_run = str(prior_run.get("run_id", "")).strip() == request.run_id
    if same_run and prior_status in PRIOR_CLOCK_RUN_STATUSES:
        return prior_report
    return {}


def _should_preserve_terminal_run_status(
    request: GoalRunStatusRequest,
    prior_report: Mapping[str, Any],
) -> bool:
    prior_status = _prior_text_field(prior_report, "run", "status")
    if prior_status not in TERMINAL_RUN_STATUSES:
        return False
    if request.status not in STATUS_REFRESH_RUN_STATUSES and request.status != prior_status:
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


def _request_int_or_prior(
    request_value: int | None,
    prior_report: Mapping[str, Any],
    section: str,
    field: str,
    *,
    default: int = 0,
) -> int:
    if request_value is not None:
        return request_value
    return _prior_int_field(prior_report, section, field, default=default)


def _request_bool_or_prior(
    request_value: bool | None,
    prior_report: Mapping[str, Any],
    section: str,
    field: str,
) -> bool:
    if request_value is not None:
        return request_value
    return _prior_bool_field(prior_report, section, field)


def _merged_run_state(
    request: GoalRunStatusRequest,
    prior_report: Mapping[str, Any],
    *,
    generated_at: str,
) -> _MergedRunState:
    preserve_terminal_status = _should_preserve_terminal_run_status(request, prior_report)
    status = (
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
    if not completed_at and status in TERMINAL_RUN_STATUSES:
        completed_at = generated_at
    started_at = request.started_at or _prior_text_field(prior_report, "run", "started_at") or generated_at
    return _MergedRunState(
        status=status,
        started_at=started_at,
        completed_at=completed_at,
    )


def _merged_observability(
    request: GoalRunStatusRequest,
    prior_report: Mapping[str, Any],
    *,
    generated_at: str,
) -> _MergedObservability:
    return _MergedObservability(
        last_heartbeat_at=(
            request.last_heartbeat_at
            or _prior_text_field(prior_report, "observability", "last_heartbeat_at")
            or generated_at
        ),
        last_checkpoint_at=(
            request.last_checkpoint_at
            or _prior_text_field(prior_report, "observability", "last_checkpoint_at")
            or generated_at
        ),
        last_command_heartbeat_at=(
            request.last_command_heartbeat_at
            or _prior_text_field(prior_report, "observability", "last_command_heartbeat_at")
        ),
        command_observation_mode=(
            request.command_observation_mode
            or _prior_text_field(prior_report, "observability", "command_observation_mode")
        ),
        command_heartbeat_count=_request_int_or_prior(
            request.command_heartbeat_count,
            prior_report,
            "observability",
            "command_heartbeat_count",
        ),
        command_timeout_seconds=_request_int_or_prior(
            request.command_timeout_seconds,
            prior_report,
            "observability",
            "command_timeout_seconds",
        ),
        last_stdout_at=(
            request.last_stdout_at
            or _prior_text_field(prior_report, "observability", "last_stdout_at")
        ),
        last_stderr_at=(
            request.last_stderr_at
            or _prior_text_field(prior_report, "observability", "last_stderr_at")
        ),
        last_artifact_touch_at=(
            request.last_artifact_touch_at
            or _prior_text_field(prior_report, "observability", "last_artifact_touch_at")
        ),
        last_command_returncode=_request_int_or_prior(
            request.last_command_returncode,
            prior_report,
            "observability",
            "last_command_returncode",
            default=-1,
        ),
        last_command_timed_out=_request_bool_or_prior(
            request.last_command_timed_out,
            prior_report,
            "observability",
            "last_command_timed_out",
        ),
        last_command_termination_reason=(
            request.last_command_termination_reason
            or _prior_text_field(prior_report, "observability", "last_command_termination_reason")
        ),
        last_backoff_until=(
            request.last_backoff_until
            or _prior_text_field(prior_report, "observability", "last_backoff_until")
        ),
        backoff_reason=(
            request.backoff_reason
            or _prior_text_field(prior_report, "observability", "backoff_reason")
        ),
        resume_from_checkpoint=_request_bool_or_prior(
            request.resume_from_checkpoint,
            prior_report,
            "observability",
            "resume_from_checkpoint",
        ),
        resume_command=(
            request.resume_command
            or _prior_text_field(prior_report, "observability", "resume_command")
        ),
    )


def _promotion_guard(contract: Mapping[str, Any]) -> dict[str, Any]:
    promotion_guard = contract.get("promotion_guard")
    return promotion_guard if isinstance(promotion_guard, dict) else {}


def _promotion_blockers(promotion_guard: Mapping[str, Any]) -> list[str]:
    raw_blockers = promotion_guard.get("promotion_blockers")
    return [str(item) for item in raw_blockers] if isinstance(raw_blockers, list) else []


def _goal_status_source_paths() -> list[str]:
    return [
        "ops/scripts/mechanism/goal_run_status.py",
        "ops/scripts/mechanism/goal_run_status_artifacts_runtime.py",
        "ops/scripts/mechanism/goal_runtime_backoff.py",
        "ops/scripts/mechanism/goal_runtime_maintenance.py",
        "ops/scripts/mechanism/goal_runtime_certificate.py",
        "ops/scripts/mechanism/goal_contract_digest_runtime.py",
        "ops/scripts/mechanism/goal_runtime_resume.py",
        "ops/scripts/mechanism/auto_improve_session_completion_runtime.py",
        "ops/scripts/core/codex_goal_client.py",
        "ops/schemas/goal-run-status.schema.json",
        "ops/schemas/codex-goal-contract.schema.json",
    ]


def _goal_status_file_inputs(
    request: GoalRunStatusRequest,
    auto_improve_session: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "goal_contract": request.goal_contract_path,
        "auto_improve_session": str(auto_improve_session.get("report_path", "")).strip(),
    }


def _goal_payload(
    *,
    request: GoalRunStatusRequest,
    contract: Mapping[str, Any],
    backend: FileGoalBackend,
    backend_name: str,
) -> dict[str, Any]:
    return {
        "contract_path": request.goal_contract_path,
        "contract_sha256": semantic_goal_contract_digest(contract),
        "contract_status": "loaded",
        "contract_id": str(contract.get("contract_id", "")).strip(),
        "objective": str(contract.get("objective", "")).strip(),
        "goal_status": str(contract.get("status", "")).strip(),
        "backend": {
            "name": backend_name,
            "process_persistent": backend.process_persistent,
        },
    }


def _run_payload(
    *,
    request: GoalRunStatusRequest,
    run_state: _MergedRunState,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "run_id": request.run_id,
        "status": run_state.status,
        "runtime_mode": request.runtime_mode,
        "started_at": run_state.started_at,
        "updated_at": generated_at,
        "completed_at": run_state.completed_at,
    }


def _observability_payload(
    *,
    request: GoalRunStatusRequest,
    observability: _MergedObservability,
) -> dict[str, Any]:
    return {
        "heartbeat_interval_seconds": request.heartbeat_interval_seconds,
        "checkpoint_interval_seconds": request.checkpoint_interval_seconds,
        "last_heartbeat_at": observability.last_heartbeat_at,
        "last_checkpoint_at": observability.last_checkpoint_at,
        "last_command_heartbeat_at": observability.last_command_heartbeat_at,
        "quiet_seconds": request.quiet_seconds,
        "command_observation_mode": observability.command_observation_mode,
        "command_heartbeat_count": observability.command_heartbeat_count,
        "command_timeout_seconds": observability.command_timeout_seconds,
        "last_stdout_at": observability.last_stdout_at,
        "last_stderr_at": observability.last_stderr_at,
        "last_artifact_touch_at": observability.last_artifact_touch_at,
        "last_command_returncode": observability.last_command_returncode,
        "last_command_timed_out": observability.last_command_timed_out,
        "last_command_termination_reason": observability.last_command_termination_reason,
        "last_backoff_until": observability.last_backoff_until,
        "backoff_reason": observability.backoff_reason,
        "resume_from_checkpoint": observability.resume_from_checkpoint,
        "resume_command": observability.resume_command,
    }


def _artifacts_payload(paths: GoalRunArtifactPaths) -> dict[str, str]:
    return {
        "status_report_path": paths.status_report_path,
        "status_markdown_path": paths.status_markdown_path,
        "audit_log_path": paths.audit_log_path,
        "resume_metadata_path": paths.resume_metadata_path,
        "checkpoint_command_log_path": paths.checkpoint_command_log_path,
    }


def _goal_status_blockers(
    *,
    promotion_blockers: list[str],
    runtime_certificate: Mapping[str, Any],
    health: Mapping[str, Any],
    run_state: _MergedRunState,
    periodic_evidence: Mapping[str, Any],
) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *promotion_blockers,
                *runtime_certificate_blockers(runtime_certificate),
                *health_blockers(
                    health,
                    run_status=run_state.status,
                    periodic_evidence=periodic_evidence,
                ),
            ]
        )
    )


def _goal_status_envelope(
    *,
    vault: Path,
    generated_at: str,
    resolved_policy_path: Path,
    request: GoalRunStatusRequest,
    auto_improve_session: Mapping[str, Any],
) -> dict[str, Any]:
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="goal_run_status",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=_goal_status_source_paths(),
        file_inputs=_goal_status_file_inputs(request, auto_improve_session),
        text_inputs={"session_synopsis_link": SESSION_SYNOPSIS_PATH},
        source_tree_excluded_files=(request.status_report_path,),
    )


def build_report(request: GoalRunStatusRequest) -> dict[str, Any]:
    if not isinstance(request, GoalRunStatusRequest):
        raise TypeError("build_report expects GoalRunStatusRequest")
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    prior_report = _prior_status_for_run(vault, request)
    run_state = _merged_run_state(request, prior_report, generated_at=generated_at)
    observability = _merged_observability(request, prior_report, generated_at=generated_at)
    backend = FileGoalBackend(vault=vault, contract_path=request.goal_contract_path)
    contract = backend.get_goal()
    contract_backend = mapping_field(contract, "goal_backend")
    backend_name = str(contract_backend.get("backend_type", "")).strip() or backend.name
    promotion_guard = _promotion_guard(contract)
    promotion_blockers = _promotion_blockers(promotion_guard)
    health = build_goal_health(
        generated_at=generated_at,
        promotion_guard=promotion_guard,
        heartbeat_interval_seconds=request.heartbeat_interval_seconds,
        checkpoint_interval_seconds=request.checkpoint_interval_seconds,
        last_heartbeat_at=observability.last_heartbeat_at,
        last_checkpoint_at=observability.last_checkpoint_at,
        last_command_heartbeat_at=observability.last_command_heartbeat_at,
        last_backoff_until=observability.last_backoff_until,
        resume_from_checkpoint=observability.resume_from_checkpoint,
        resume_command=observability.resume_command,
    )
    paths = goal_run_artifact_paths(
        request.run_id,
        status_report_path=request.status_report_path,
    )
    periodic_generated_at = (
        run_state.completed_at
        if run_state.status in TERMINAL_RUN_STATUSES and run_state.completed_at
        else generated_at
    )
    periodic_evidence = build_periodic_evidence(
        vault,
        generated_at=periodic_generated_at,
        started_at=run_state.started_at,
        last_checkpoint_at=observability.last_checkpoint_at,
        checkpoint_command_log_path=paths.checkpoint_command_log_path,
        checkpoints_config=PERIODIC_EVIDENCE_CHECKPOINTS,
    )
    runtime_certificate = build_runtime_certificate(
        vault,
        contract=contract,
        run_mode=request.runtime_mode,
    )
    session_synopsis = _session_synopsis_link(vault)
    auto_improve_session = _auto_improve_session_link(vault, request.run_id)
    blockers = _goal_status_blockers(
        promotion_blockers=promotion_blockers,
        runtime_certificate=runtime_certificate,
        health=health,
        run_state=run_state,
        periodic_evidence=periodic_evidence,
    )
    return {
        **_goal_status_envelope(
            vault=vault,
            generated_at=generated_at,
            resolved_policy_path=resolved_policy_path,
            request=request,
            auto_improve_session=auto_improve_session,
        ),
        "goal": _goal_payload(
            request=request,
            contract=contract,
            backend=backend,
            backend_name=backend_name,
        ),
        "run": _run_payload(
            request=request,
            run_state=run_state,
            generated_at=generated_at,
        ),
        "observability": _observability_payload(
            request=request,
            observability=observability,
        ),
        "health": health,
        "runtime_certificate": runtime_certificate,
        "periodic_evidence": periodic_evidence,
        "session_synopsis": session_synopsis,
        "auto_improve_session": auto_improve_session,
        "artifacts": _artifacts_payload(paths),
        "promotion_guard": promotion_guard,
        "blockers": blockers,
        "status": _status_from_blockers(run_state.status, blockers),
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
    return _build_status_markdown(report)


def write_run_artifacts(
    vault: Path,
    report: Mapping[str, Any],
    *,
    writer: str = PRODUCER,
) -> list[Path]:
    return _write_run_artifacts(vault, report, writer=writer)


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected one of: true, false, 1, 0, yes, no")


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
    parser.add_argument("--command-observation-mode", default="")
    parser.add_argument("--command-heartbeat-count", type=int, default=None)
    parser.add_argument("--command-timeout-seconds", type=int, default=None)
    parser.add_argument("--last-stdout-at", default="")
    parser.add_argument("--last-stderr-at", default="")
    parser.add_argument("--last-artifact-touch-at", default="")
    parser.add_argument("--last-command-returncode", type=int, default=None)
    parser.add_argument("--last-command-timed-out", type=_parse_bool, default=None)
    parser.add_argument("--last-command-termination-reason", default="")
    parser.add_argument("--quiet-seconds", type=int, default=0)
    parser.add_argument("--last-backoff-until", default="")
    parser.add_argument("--backoff-reason", default="")
    parser.add_argument("--resume-from-checkpoint", action="store_true", default=None)
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
            command_observation_mode=args.command_observation_mode,
            command_heartbeat_count=args.command_heartbeat_count,
            command_timeout_seconds=args.command_timeout_seconds,
            last_stdout_at=args.last_stdout_at,
            last_stderr_at=args.last_stderr_at,
            last_artifact_touch_at=args.last_artifact_touch_at,
            last_command_returncode=args.last_command_returncode,
            last_command_timed_out=args.last_command_timed_out,
            last_command_termination_reason=args.last_command_termination_reason,
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
