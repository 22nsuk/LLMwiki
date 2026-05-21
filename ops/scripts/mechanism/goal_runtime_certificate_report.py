from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.codex_goal_client import (
    DEFAULT_CONTRACT_PATH,
    FileGoalBackend,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext

from .goal_runtime_certificate import (
    RUNTIME_MODES,
    SESSION_REQUIREMENTS,
    evidence_statuses,
    runtime_duration_seconds,
    runtime_mode as contract_runtime_mode,
)


DEFAULT_OUT = "ops/reports/goal-runtime-certificate.json"
DEFAULT_STATUS_REPORT_PATH = "ops/reports/goal-run-status.json"
PRODUCER = "ops.scripts.goal_runtime_certificate_report"
RUNNER_PRODUCER = "ops.scripts.goal_runtime_runner"
SCHEMA_PATH = "ops/schemas/goal-runtime-certificate.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_certificate_report --vault ."


@dataclass(frozen=True)
class GoalRuntimeCertificateRequest:
    vault: Path
    goal_contract_path: str = DEFAULT_CONTRACT_PATH
    status_report_path: str = DEFAULT_STATUS_REPORT_PATH
    runtime_mode: str = ""
    apply_update: bool = False
    out_path: str | None = None
    policy_path: str | None = None
    context: RuntimeContext | None = None


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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


def _bool_value(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _parse_iso_z(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _elapsed_seconds(started_at: object, completed_at: object) -> int:
    started = _parse_iso_z(started_at)
    completed = _parse_iso_z(completed_at)
    if started is None or completed is None:
        return 0
    return max(0, int((completed - started).total_seconds()))


def _report_status_fields(path: Path) -> dict[str, str]:
    if not path.is_file() or path.suffix.lower() != ".json":
        return {}
    payload = load_optional_json_object(path)
    if not payload:
        return {"report_status": "unreadable"}
    fields: dict[str, str] = {}
    status = str(payload.get("status", "")).strip()
    if status:
        fields["report_status"] = status
    for key in (
        "preflight_status",
        "distribution_binding_status",
        "authority_preflight_status",
    ):
        value = str(payload.get(key, "")).strip()
        if value:
            fields[key] = value
    return fields


def _load_audit_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _run_artifacts(vault: Path, status_report: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = _mapping_value(status_report, "artifacts")
    run = _mapping_value(status_report, "run")
    goal = _mapping_value(status_report, "goal")
    observability = _mapping_value(status_report, "observability")
    generated_at = str(status_report.get("generated_at", "")).strip()
    run_id = str(run.get("run_id", "")).strip()
    contract_sha256 = str(goal.get("contract_sha256", "")).strip()
    checks: list[dict[str, Any]] = []

    def path_check(field: str) -> tuple[str, Path, bool]:
        rel_path = str(artifacts.get(field, "")).strip()
        absolute = vault / rel_path if rel_path else vault / "__missing_goal_runtime_artifact__"
        present = bool(rel_path) and absolute.is_file()
        checks.append(
            {
                "artifact": field,
                "path": rel_path,
                "status": "present" if present else "missing",
            }
        )
        return rel_path, absolute, present

    _, status_markdown_path, status_markdown_present = path_check("status_markdown_path")
    _, resume_metadata_path, resume_metadata_present = path_check("resume_metadata_path")
    _, audit_log_path, audit_log_present = path_check("audit_log_path")

    status_markdown_current = False
    if status_markdown_present:
        text = status_markdown_path.read_text(encoding="utf-8")
        status_markdown_current = f"- status: {run.get('status', '')}" in text
    checks.append(
        {
            "artifact": "status_markdown_current",
            "path": str(artifacts.get("status_markdown_path", "")).strip(),
            "status": "pass" if status_markdown_current else "fail",
        }
    )

    resume_metadata = load_optional_json_object(resume_metadata_path)
    resume_metadata_current = (
        resume_metadata_present
        and str(resume_metadata.get("run_id", "")).strip() == run_id
        and str(resume_metadata.get("contract_sha256", "")).strip() == contract_sha256
    )
    checks.append(
        {
            "artifact": "resume_metadata_current",
            "path": str(artifacts.get("resume_metadata_path", "")).strip(),
            "status": "pass" if resume_metadata_current else "fail",
        }
    )

    audit_events = _load_audit_events(audit_log_path)
    matching_events = [
        event
        for event in audit_events
        if str(event.get("event", "")).strip() == "goal_run_status_written"
        and str(event.get("generated_at", "")).strip() == generated_at
        and str(event.get("run_id", "")).strip() == run_id
        and str(event.get("run_status", "")).strip() == str(run.get("status", "")).strip()
    ]
    matching_audit_event = bool(matching_events)
    checks.append(
        {
            "artifact": "audit_log_current",
            "path": str(artifacts.get("audit_log_path", "")).strip(),
            "status": "pass" if matching_audit_event else "fail",
        }
    )
    def command_observability_matches(event: Mapping[str, Any]) -> bool:
        return (
            str(event.get("command_observation_mode", "")).strip()
            == str(observability.get("command_observation_mode", "")).strip()
            and _integer_value(event.get("command_heartbeat_count"))
            == _integer_value(observability.get("command_heartbeat_count"))
            and _integer_value(event.get("last_command_returncode"))
            == _integer_value(observability.get("last_command_returncode"))
            and _bool_value(event.get("last_command_timed_out"))
            == _bool_value(observability.get("last_command_timed_out"))
            and str(event.get("last_command_termination_reason", "")).strip()
            == str(observability.get("last_command_termination_reason", "")).strip()
        )

    matching_command_observability = any(command_observability_matches(event) for event in matching_events)
    runner_command_audit_current = any(
        command_observability_matches(event)
        and str(event.get("writer", "")).strip() == RUNNER_PRODUCER
        for event in matching_events
    )
    checks.append(
        {
            "artifact": "audit_log_command_observability_current",
            "path": str(artifacts.get("audit_log_path", "")).strip(),
            "status": "pass" if matching_command_observability else "fail",
        }
    )

    clean = (
        status_markdown_present
        and resume_metadata_present
        and audit_log_present
        and status_markdown_current
        and resume_metadata_current
        and matching_audit_event
        and matching_command_observability
    )
    return {
        "status": "clean" if clean else "incomplete",
        "checks": checks,
        "audit_event_count": len(audit_events),
        "runner_command_audit_current": runner_command_audit_current,
    }


def _run_artifact_file_inputs(run_artifacts: Mapping[str, Any]) -> dict[str, str]:
    input_names = {
        "status_markdown_path": "run_status_markdown",
        "resume_metadata_path": "run_resume_metadata",
        "audit_log_path": "run_audit_log",
    }
    file_inputs: dict[str, str] = {}
    for check in run_artifacts.get("checks", []):
        if not isinstance(check, Mapping):
            continue
        artifact = str(check.get("artifact", "")).strip()
        input_name = input_names.get(artifact)
        path = str(check.get("path", "")).strip()
        if input_name and path:
            file_inputs[input_name] = path
    return file_inputs


def _audit_event_timestamps_for_run(vault: Path, status_report: Mapping[str, Any]) -> list[dt.datetime]:
    artifacts = _mapping_value(status_report, "artifacts")
    audit_log_path = vault / str(artifacts.get("audit_log_path", "")).strip()
    run_id = str(_mapping_value(status_report, "run").get("run_id", "")).strip()
    seen: set[str] = set()
    timestamps: list[dt.datetime] = []
    for event in _load_audit_events(audit_log_path):
        if str(event.get("event", "")).strip() != "goal_run_status_written":
            continue
        if str(event.get("run_id", "")).strip() != run_id:
            continue
        generated_at = str(event.get("generated_at", "")).strip()
        if not generated_at or generated_at in seen:
            continue
        parsed = _parse_iso_z(generated_at)
        if parsed is None:
            continue
        seen.add(generated_at)
        timestamps.append(parsed)
    return sorted(timestamps)


def _audit_times_within_run(
    *,
    status_report: Mapping[str, Any],
    audit_times: list[dt.datetime],
) -> tuple[dt.datetime | None, dt.datetime | None, list[dt.datetime]]:
    run = _mapping_value(status_report, "run")
    started = _parse_iso_z(run.get("started_at"))
    completed = _parse_iso_z(run.get("completed_at"))
    windowed = [
        audit_time
        for audit_time in audit_times
        if (started is None or audit_time >= started)
        and (completed is None or audit_time <= completed)
    ]
    return started, completed, windowed


def _max_gap_seconds(times: list[dt.datetime]) -> int:
    if len(times) < 2:
        return 0
    return max(
        int((right - left).total_seconds())
        for left, right in zip(times, times[1:])
    )


def _expected_min_command_heartbeat_count(
    *,
    observed_elapsed_seconds: int,
    heartbeat_interval_seconds: int,
) -> int:
    if heartbeat_interval_seconds <= 0 or observed_elapsed_seconds < heartbeat_interval_seconds:
        return 0
    return max(1, observed_elapsed_seconds // heartbeat_interval_seconds - 1)


def _command_observability_summary(
    *,
    status_report: Mapping[str, Any],
    observed_elapsed_seconds: int,
    runner_audit_current: bool,
) -> dict[str, Any]:
    observability = _mapping_value(status_report, "observability")
    heartbeat_interval_seconds = _integer_value(observability.get("heartbeat_interval_seconds"))
    expected_min_heartbeat_count = _expected_min_command_heartbeat_count(
        observed_elapsed_seconds=observed_elapsed_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
    return {
        "mode": str(observability.get("command_observation_mode", "")).strip(),
        "heartbeat_count": _integer_value(observability.get("command_heartbeat_count")),
        "expected_min_heartbeat_count": expected_min_heartbeat_count,
        "timeout_seconds": _integer_value(observability.get("command_timeout_seconds")),
        "last_command_returncode": _integer_value(observability.get("last_command_returncode")),
        "last_command_timed_out": _bool_value(observability.get("last_command_timed_out")),
        "last_command_termination_reason": str(
            observability.get("last_command_termination_reason", "")
        ).strip(),
        "last_command_heartbeat_at": str(observability.get("last_command_heartbeat_at", "")).strip(),
        "runner_audit_current": runner_audit_current,
    }


def _command_observability_blockers(
    *,
    summary: Mapping[str, Any],
    observed_elapsed_seconds: int,
) -> list[str]:
    blockers: list[str] = []
    if summary.get("mode") != "process_heartbeat":
        blockers.append("goal run command observation mode is not process_heartbeat")
    if not _bool_value(summary.get("runner_audit_current")):
        blockers.append("goal run command audit was not written by goal runtime runner")
    if _integer_value(summary.get("heartbeat_count")) < _integer_value(
        summary.get("expected_min_heartbeat_count")
    ):
        blockers.append("goal run command heartbeat count is incomplete")
    timeout_seconds = _integer_value(summary.get("timeout_seconds"))
    if timeout_seconds <= 0:
        blockers.append("goal run command timeout is missing")
    elif observed_elapsed_seconds > 0 and timeout_seconds < observed_elapsed_seconds:
        blockers.append("goal run command timeout is shorter than observed elapsed")
    if _integer_value(summary.get("last_command_returncode")) != 0:
        blockers.append("goal run command returncode is not zero")
    if _bool_value(summary.get("last_command_timed_out")):
        blockers.append("goal run command timed out")
    if summary.get("last_command_termination_reason") != "completed":
        blockers.append("goal run command termination reason is not completed")
    return blockers


def _session_report_rel_path(status_report: Mapping[str, Any]) -> str:
    run_id = str(_mapping_value(status_report, "run").get("run_id", "")).strip()
    return f"ops/reports/auto-improve-sessions/{run_id}.json" if run_id else ""


def _successful_iteration(iteration: Mapping[str, Any]) -> bool:
    return (
        str(iteration.get("decision", "")).strip() == "PROMOTE"
        or str(iteration.get("outcome", "")).strip() == "promoted"
        or str(iteration.get("status", "")).strip() == "promoted"
    )


def _session_iterations(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    iterations = payload.get("iterations")
    if not isinstance(iterations, list):
        return []
    return [item for item in iterations if isinstance(item, Mapping)]


def _has_success_then_followup(iterations: list[Mapping[str, Any]]) -> bool:
    for iteration in iterations[:-1]:
        if _successful_iteration(iteration):
            return True
    return False


def _session_requirement_summary() -> dict[str, Any]:
    requirements = SESSION_REQUIREMENTS
    accepted_stop_reasons = _list_text(requirements.get("accepted_stop_reasons"))
    return {
        "accepted_stop_reasons": accepted_stop_reasons,
        "minimum_iteration_count": _integer_value(requirements.get("minimum_iteration_count")),
        "minimum_successful_iteration_count": _integer_value(
            requirements.get("minimum_successful_iteration_count")
        ),
        "requires_success_then_followup": bool(requirements.get("requires_success_then_followup", False)),
        "requires_meaningful_maintenance": bool(requirements.get("requires_meaningful_maintenance", False)),
    }


def _stop_reason_satisfies_maintenance_requirement(stop_reason: str) -> bool:
    return stop_reason != "queue_exhausted"


def _empty_session_evidence(*, status: str, path: str) -> dict[str, Any]:
    return {
        "status": status,
        "path": path,
        "session_status": "",
        "stop_reason": "",
        "iteration_count": 0,
        "successful_iteration_count": 0,
        "has_success_then_followup": False,
        "maintenance_status": "missing",
        "maintenance_cycle_count": 0,
        "meaningful_maintenance_cycle_count": 0,
        "expected_min_maintenance_cycle_count": 0,
        "maintenance_last_cycle_elapsed_seconds": 0,
        **_session_requirement_summary(),
    }


def _meaningful_maintenance_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    maintenance = _mapping_value(payload, "maintenance")
    cycles = maintenance.get("cycles")
    cycle_items = [item for item in cycles if isinstance(item, Mapping)] if isinstance(cycles, list) else []
    cycle_count = _integer_value(maintenance.get("cycle_count")) or len(cycle_items)
    meaningful_count = _integer_value(maintenance.get("meaningful_cycle_count"))
    if meaningful_count == 0:
        required_work = {
            "mechanism_review_report",
            "mutation_proposal_report",
            "auto_improve_readiness_report",
            "auto_improve_session_report",
        }
        meaningful_count = sum(
            1
            for cycle in cycle_items
            if str(cycle.get("status", "")).strip() == "pass"
            and set(_list_text(cycle.get("work_items"))) >= required_work
        )
    expected_count = _integer_value(maintenance.get("expected_min_cycle_count"))
    target_elapsed = _integer_value(maintenance.get("target_elapsed_seconds"))
    last_elapsed = _integer_value(maintenance.get("last_cycle_elapsed_seconds"))
    if last_elapsed == 0:
        last_elapsed = max(
            (_integer_value(cycle.get("elapsed_seconds")) for cycle in cycle_items),
            default=0,
        )
    complete = (
        str(maintenance.get("mode", "")).strip() == "proposal_budget_runtime_maintenance"
        and str(maintenance.get("status", "")).strip() == "complete"
        and cycle_count >= expected_count
        and meaningful_count >= expected_count
        and last_elapsed >= target_elapsed
    )
    if not maintenance:
        status = "missing"
    elif complete:
        status = "clean"
    else:
        status = "incomplete"
    return {
        "maintenance_status": status,
        "maintenance_cycle_count": cycle_count,
        "meaningful_maintenance_cycle_count": meaningful_count,
        "expected_min_maintenance_cycle_count": expected_count,
        "maintenance_last_cycle_elapsed_seconds": last_elapsed,
    }


def _session_evidence(
    vault: Path,
    status_report: Mapping[str, Any],
) -> dict[str, Any]:
    rel_path = _session_report_rel_path(status_report)
    if not rel_path:
        return _empty_session_evidence(status="missing", path="")
    payload = load_optional_json_object(vault / rel_path)
    if not payload:
        return _empty_session_evidence(status="missing", path=rel_path)
    iterations = _session_iterations(payload)
    successful_count = sum(1 for iteration in iterations if _successful_iteration(iteration))
    has_success_then_followup = _has_success_then_followup(iterations)
    stop_reason = str(payload.get("stop_reason", "")).strip()
    session_status = str(payload.get("status", "")).strip()
    session_requirements = _session_requirement_summary()
    maintenance_summary = _meaningful_maintenance_summary(payload)
    requires_meaningful_maintenance = bool(
        session_requirements["requires_meaningful_maintenance"]
        and _stop_reason_satisfies_maintenance_requirement(stop_reason)
    )
    clean = (
        session_status == "complete"
        and stop_reason in session_requirements["accepted_stop_reasons"]
        and len(iterations) >= session_requirements["minimum_iteration_count"]
        and successful_count >= session_requirements["minimum_successful_iteration_count"]
        and (
            not session_requirements["requires_success_then_followup"]
            or has_success_then_followup
        )
        and (
            not requires_meaningful_maintenance
            or maintenance_summary["maintenance_status"] == "clean"
        )
    )
    return {
        "status": "clean" if clean else "incomplete",
        "path": rel_path,
        "session_status": session_status,
        "stop_reason": stop_reason,
        "iteration_count": len(iterations),
        "successful_iteration_count": successful_count,
        "has_success_then_followup": has_success_then_followup,
        **maintenance_summary,
        **session_requirements,
        "requires_meaningful_maintenance": requires_meaningful_maintenance,
    }


def _session_evidence_blockers(session_evidence: Mapping[str, Any]) -> list[str]:
    if session_evidence.get("status") == "clean":
        return []
    if session_evidence.get("status") == "missing":
        return ["auto-improve session evidence missing"]
    blockers: list[str] = []
    if session_evidence.get("session_status") != "complete":
        blockers.append("auto-improve session did not complete")
    accepted_stop_reasons = _list_text(session_evidence.get("accepted_stop_reasons"))
    if session_evidence.get("stop_reason") not in accepted_stop_reasons:
        if accepted_stop_reasons == ["time_budget_exhausted"]:
            blockers.append("auto-improve session did not run until time budget")
        else:
            blockers.append("auto-improve session stop reason is not accepted for runtime certificate")
    minimum_iteration_count = _integer_value(session_evidence.get("minimum_iteration_count"))
    if _integer_value(session_evidence.get("iteration_count")) < minimum_iteration_count:
        if minimum_iteration_count == 2:
            blockers.append("auto-improve session did not repeat improvement iterations")
        else:
            blockers.append("auto-improve session has fewer than required improvement iterations")
    minimum_successful_count = _integer_value(
        session_evidence.get("minimum_successful_iteration_count")
    )
    if _integer_value(session_evidence.get("successful_iteration_count")) < minimum_successful_count:
        if minimum_successful_count == 1:
            blockers.append("auto-improve session has no successful improvement iteration")
        else:
            blockers.append(
                "auto-improve session has fewer than required successful improvement iterations"
            )
    if _bool_value(session_evidence.get("requires_success_then_followup")) and not _bool_value(
        session_evidence.get("has_success_then_followup")
    ):
        blockers.append("auto-improve session did not continue after a successful improvement")
    if _bool_value(session_evidence.get("requires_meaningful_maintenance")):
        if str(session_evidence.get("maintenance_status", "")).strip() != "clean":
            blockers.append("auto-improve session lacks meaningful runtime maintenance evidence")
        elif _integer_value(session_evidence.get("maintenance_cycle_count")) < _integer_value(
            session_evidence.get("expected_min_maintenance_cycle_count")
        ):
            blockers.append("auto-improve session maintenance evidence is below expected cadence")
    return blockers


def _observability_blockers(
    *,
    vault: Path,
    status_report: Mapping[str, Any],
    run_artifacts: Mapping[str, Any],
    observed_elapsed_seconds: int,
) -> list[str]:
    health = _mapping_value(status_report, "health")
    periodic_evidence = _mapping_value(status_report, "periodic_evidence")
    observability = _mapping_value(status_report, "observability")
    run = _mapping_value(status_report, "run")
    run_completed = str(run.get("status", "")).strip() == "completed"
    blockers: list[str] = []
    if not run_completed:
        if health.get("heartbeat_status") != "current":
            blockers.append("goal run heartbeat is not current")
        if health.get("checkpoint_status") != "current":
            blockers.append("goal run checkpoint is not current")
        if health.get("command_heartbeat_status") != "current":
            blockers.append("goal run command heartbeat is not current")
    if health.get("backoff_status") == "unknown":
        blockers.append("goal run backoff status is unknown")
    if health.get("resume_status") == "missing_resume_command":
        blockers.append("goal run resume command is missing")
    if periodic_evidence.get("status") == "missing_due_evidence":
        blockers.append("goal run periodic evidence checkpoint is missing")

    heartbeat_interval_seconds = _integer_value(observability.get("heartbeat_interval_seconds"))
    if heartbeat_interval_seconds <= 0:
        blockers.append("goal run heartbeat interval is missing")
    elif observed_elapsed_seconds >= heartbeat_interval_seconds:
        expected_events = max(2, observed_elapsed_seconds // heartbeat_interval_seconds)
        audit_times = _audit_event_timestamps_for_run(vault, status_report)
        started, completed, windowed_audit_times = _audit_times_within_run(
            status_report=status_report,
            audit_times=audit_times,
        )
        observed_events = len(windowed_audit_times)
        if observed_events < expected_events:
            blockers.append("goal run heartbeat audit cadence is incomplete")
        if started is not None and completed is not None and windowed_audit_times:
            cadence_times = [started, *windowed_audit_times, completed]
            if _max_gap_seconds(cadence_times) > heartbeat_interval_seconds * 2:
                blockers.append("goal run heartbeat audit gap too large")
    command_summary = _command_observability_summary(
        status_report=status_report,
        observed_elapsed_seconds=observed_elapsed_seconds,
        runner_audit_current=_bool_value(run_artifacts.get("runner_command_audit_current")),
    )
    blockers.extend(
        _command_observability_blockers(
            summary=command_summary,
            observed_elapsed_seconds=observed_elapsed_seconds,
        )
    )
    return blockers


def _sealed_authority_clean(vault: Path) -> bool:
    payload = load_optional_json_object(
        vault / "ops" / "reports" / "release-closeout-sealed-rehearsal-check.json"
    )
    return (
        payload.get("status") == "pass"
        and payload.get("preflight_status") == "sealed_clean_pass"
        and payload.get("distribution_binding_status") == "pass"
        and payload.get("authority_preflight_status") == "clean"
    )


def _verification_blockers(
    *,
    vault: Path,
    contract: Mapping[str, Any],
    status_report: Mapping[str, Any],
    runtime_mode: str,
    run_artifacts: Mapping[str, Any],
    session_evidence: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if runtime_mode not in RUNTIME_MODES:
        return [f"unsupported runtime mode: {runtime_mode}"]
    if not status_report:
        blockers.append("goal run status report missing")
        return blockers

    run = _mapping_value(status_report, "run")
    if str(run.get("runtime_mode", "")).strip() != runtime_mode:
        blockers.append("goal run status runtime mode mismatch")
    if str(run.get("status", "")).strip() != "completed":
        blockers.append("goal run is not completed")
    observed_elapsed_seconds = _elapsed_seconds(run.get("started_at"), run.get("completed_at"))
    max_runtime_seconds = runtime_duration_seconds(contract)
    if observed_elapsed_seconds > max_runtime_seconds:
        blockers.append("goal run exceeded runtime duration budget")
    if run_artifacts.get("status") != "clean":
        blockers.append("goal run artifacts are not clean")
    blockers.extend(_session_evidence_blockers(session_evidence))
    blockers.extend(
        _observability_blockers(
            vault=vault,
            status_report=status_report,
            run_artifacts=run_artifacts,
            observed_elapsed_seconds=observed_elapsed_seconds,
        )
    )
    for evidence in evidence_statuses(vault, contract):
        if evidence["status"] != "present":
            blockers.append(f"runtime certificate evidence missing: {evidence['path']}")
        elif evidence.get("report_status") in {"fail", "blocked"}:
            blockers.append(f"runtime certificate evidence is not clean: {evidence['path']}")
    promotion_guard = _mapping_value(contract, "promotion_guard")
    if bool(promotion_guard.get("sustained_runtime_claimed", False)) and not bool(
        promotion_guard.get("runtime_certificate_verified", False)
    ):
        blockers.append("sustained runtime was claimed before loop certificate verification")
    if not bool(promotion_guard.get("can_promote_result", False)):
        blockers.append("can_promote_result is not clean for runtime certificate")
    if not bool(promotion_guard.get("sealed_authority_clean", False)) or not _sealed_authority_clean(vault):
        blockers.append("sealed authority clean pass is not verified for runtime certificate")
    promotion_blockers = [
        blocker
        for blocker in _list_text(promotion_guard.get("promotion_blockers"))
        if blocker != "self-improvement loop certificate incomplete"
    ]
    if promotion_blockers:
        blockers.append("promotion guard still has blockers")
    return list(dict.fromkeys(blockers))


def _contract_patch_for_verified_certificate(
    contract: Mapping[str, Any],
    *,
    verified_at: str,
) -> dict[str, Any]:
    runtime = dict(_mapping_value(contract, "runtime"))
    runtime["certificate_status"] = "verified"
    runtime["verified_at"] = verified_at
    promotion_guard = dict(_mapping_value(contract, "promotion_guard"))
    promotion_guard["runtime_certificate_verified"] = True
    promotion_guard["sustained_runtime_claimed"] = (
        bool(promotion_guard.get("sustained_runtime_claimed", False))
        and bool(promotion_guard.get("can_promote_result", False))
        and bool(promotion_guard.get("sealed_authority_clean", False))
    )
    return {
        "runtime": runtime,
        "promotion_guard": promotion_guard,
    }


def build_report(request: GoalRuntimeCertificateRequest) -> dict[str, Any]:
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    backend = FileGoalBackend(vault=vault, contract_path=request.goal_contract_path)
    contract = backend.get_goal()
    contract_sha256_before = _canonical_json_digest(contract)
    runtime = _mapping_value(contract, "runtime")
    target_runtime_mode = request.runtime_mode.strip() or contract_runtime_mode(contract)
    certificate_status_before = str(runtime.get("certificate_status", "unverified")).strip() or "unverified"
    already_verified = certificate_status_before == "verified"
    status_report = load_optional_json_object(vault / request.status_report_path)
    run_artifacts = _run_artifacts(vault, status_report) if status_report else {
        "status": "missing",
        "checks": [],
        "audit_event_count": 0,
        "runner_command_audit_current": False,
    }
    session_evidence = (
        _session_evidence(vault, status_report)
        if status_report
        else _empty_session_evidence(status="missing", path="")
    )
    blockers: list[str] = []
    if already_verified:
        verification_status = "already_verified"
    else:
        blockers = _verification_blockers(
            vault=vault,
            contract=contract,
            status_report=status_report,
            runtime_mode=target_runtime_mode,
            run_artifacts=run_artifacts,
            session_evidence=session_evidence,
        )
        verification_status = "eligible" if not blockers else "blocked"

    apply_allowed = verification_status == "eligible"
    patch = (
        _contract_patch_for_verified_certificate(contract, verified_at=generated_at)
        if apply_allowed
        else {}
    )
    certificate_status_after = certificate_status_before
    runtime_certificate_verified_before = bool(
        _mapping_value(contract, "promotion_guard").get("runtime_certificate_verified", False)
    )
    runtime_certificate_verified_after = runtime_certificate_verified_before
    applied = False
    contract_sha256_after = contract_sha256_before
    if request.apply_update and apply_allowed:
        updated = backend.update_goal(patch)
        applied = True
        contract_sha256_after = _canonical_json_digest(updated)
        certificate_status_after = str(
            _mapping_value(updated, "runtime").get("certificate_status", "unverified")
        )
        runtime_certificate_verified_after = bool(
            _mapping_value(updated, "promotion_guard").get("runtime_certificate_verified", False)
        )
    elif patch:
        patched_runtime = _mapping_value(patch, "runtime")
        patched_guard = _mapping_value(patch, "promotion_guard")
        certificate_status_after = str(
            patched_runtime.get("certificate_status", certificate_status_after)
        )
        runtime_certificate_verified_after = bool(
            patched_guard.get("runtime_certificate_verified", runtime_certificate_verified_after)
        )

    run = _mapping_value(status_report, "run")
    max_runtime_seconds = runtime_duration_seconds(contract)
    observed_elapsed_seconds = _elapsed_seconds(run.get("started_at"), run.get("completed_at"))
    command_observability = _command_observability_summary(
        status_report=status_report,
        observed_elapsed_seconds=observed_elapsed_seconds,
        runner_audit_current=_bool_value(run_artifacts.get("runner_command_audit_current")),
    )
    command_observability["status"] = (
        "clean"
        if not _command_observability_blockers(
            summary=command_observability,
            observed_elapsed_seconds=observed_elapsed_seconds,
        )
        else "incomplete"
    )
    evidence_paths = evidence_statuses(vault, contract)
    file_inputs = {
        "goal_contract": request.goal_contract_path,
        "goal_run_status": request.status_report_path,
        **_run_artifact_file_inputs(run_artifacts),
    }
    session_evidence_path = str(session_evidence.get("path", "")).strip()
    if session_evidence_path:
        file_inputs["auto_improve_session"] = session_evidence_path
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="goal_runtime_certificate",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_certificate_report.py",
                "ops/scripts/mechanism/goal_runtime_certificate.py",
                "ops/scripts/mechanism/goal_run_status.py",
                "ops/scripts/core/codex_goal_client.py",
                "ops/schemas/goal-runtime-certificate.schema.json",
                "ops/schemas/codex-goal-contract.schema.json",
                "ops/schemas/goal-run-status.schema.json",
            ],
            file_inputs=file_inputs,
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "vault": display_path(vault, vault),
        "goal": {
            "contract_path": request.goal_contract_path,
            "contract_id": str(contract.get("contract_id", "")).strip(),
            "contract_sha256_before": contract_sha256_before,
            "contract_sha256_after": contract_sha256_after,
        },
        "certificate": {
            "target_runtime_mode": target_runtime_mode,
            "verification_status": verification_status,
            "max_runtime_seconds": max_runtime_seconds,
            "observed_elapsed_seconds": observed_elapsed_seconds,
            "already_verified": already_verified,
            "eligible": apply_allowed or verification_status in {"already_verified", "already_complete"},
        },
        "run": {
            "status_report_path": request.status_report_path,
            "run_id": str(run.get("run_id", "")).strip(),
            "run_status": str(run.get("status", "")).strip(),
            "run_runtime_mode": str(run.get("runtime_mode", "")).strip(),
            "started_at": str(run.get("started_at", "")).strip(),
            "completed_at": str(run.get("completed_at", "")).strip(),
        },
        "run_artifacts": run_artifacts,
        "session_evidence": session_evidence,
        "command_observability": command_observability,
        "evidence_paths": evidence_paths,
        "contract_update": {
            "apply_requested": request.apply_update,
            "apply_allowed": apply_allowed,
            "applied": applied,
            "certificate_status_before": certificate_status_before,
            "certificate_status_after": certificate_status_after,
            "runtime_certificate_verified_before": runtime_certificate_verified_before,
            "runtime_certificate_verified_after": runtime_certificate_verified_after,
        },
        "blockers": blockers,
        "status": "attention" if blockers else "pass",
    }


def write_report(vault: Path, report: Mapping[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal runtime certificate schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--goal-contract", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--status-report", default=DEFAULT_STATUS_REPORT_PATH)
    parser.add_argument("--runtime-mode", default="")
    parser.add_argument("--profile", dest="runtime_mode", default=argparse.SUPPRESS)
    parser.add_argument("--apply", action="store_true", help="Persist verified runtime certificate.")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeCertificateRequest(
            vault=vault,
            goal_contract_path=args.goal_contract,
            status_report_path=args.status_report,
            runtime_mode=args.runtime_mode,
            apply_update=args.apply,
            out_path=args.out,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
