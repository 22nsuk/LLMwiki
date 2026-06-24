from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import write_json_object
from ops.scripts.core.filesystem_runtime import atomic_write_text
from ops.scripts.core.output_runtime import resolve_repo_output_path
from ops.scripts.core.path_runtime import normalize_repo_path_text

from .goal_runtime_resume import mapping_field, resume_metadata_from_report


def _resolve_artifact_path(vault: Path, artifacts: Mapping[str, Any], key: str) -> Path:
    raw_path = str(artifacts[key])
    normalized = normalize_repo_path_text(raw_path)
    if (
        Path(raw_path).is_absolute()
        or normalized is None
        or normalized in {".", ".."}
        or (len(normalized) > 2 and normalized[1] == ":" and normalized[2] == "/")
        or normalized.startswith("../")
    ):
        raise ValueError(f"goal run artifact path must be repo-relative: {key}")
    return resolve_repo_output_path(
        vault,
        normalized,
        default_relative_path=normalized,
    )


def build_status_markdown(report: Mapping[str, Any]) -> str:
    goal = mapping_field(report, "goal")
    run = mapping_field(report, "run")
    completion_summary = mapping_field(report, "completion_summary")
    observability = mapping_field(report, "observability")
    health = mapping_field(report, "health")
    runtime_certificate = mapping_field(report, "runtime_certificate")
    periodic_evidence = mapping_field(report, "periodic_evidence")
    session_synopsis = mapping_field(report, "session_synopsis")
    auto_improve_session = mapping_field(report, "auto_improve_session")
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
            f"- completion_class: {completion_summary.get('completion_class', '')}",
            f"- completion_status: {completion_summary.get('completion_status', '')}",
            f"- promotion_lane: {completion_summary.get('promotion_lane_label', '')}",
            f"- completion_headline: {completion_summary.get('headline', '')}",
            f"- stop_reason: {completion_summary.get('stop_reason', '')}",
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
            f"- auto_improve_session: {auto_improve_session.get('report_path', '')}",
            f"- auto_improve_session_status: {auto_improve_session.get('status', '')}",
            f"- auto_improve_session_completion_class: {auto_improve_session.get('completion_class', '')}",
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
    writer: str,
) -> list[Path]:
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("goal run status report missing artifacts")
    status_markdown = _resolve_artifact_path(vault, artifacts, "status_markdown_path")
    resume_metadata = _resolve_artifact_path(vault, artifacts, "resume_metadata_path")
    audit_log = _resolve_artifact_path(vault, artifacts, "audit_log_path")
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
