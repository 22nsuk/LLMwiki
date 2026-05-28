from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.experiment_telemetry_runtime import (
    append_ledger_event as telemetry_append_ledger_event,
)
from ops.scripts.experiment_telemetry_runtime import (
    load_run_ledger as telemetry_load_run_ledger,
)
from ops.scripts.experiment_telemetry_runtime import (
    run_rel as telemetry_run_rel,
)
from ops.scripts.experiment_telemetry_runtime import (
    write_command_logs as telemetry_write_command_logs,
)
from ops.scripts.experiment_telemetry_runtime import (
    write_run_ledger as telemetry_write_run_ledger,
)
from ops.scripts.experiment_telemetry_runtime import (
    write_run_telemetry,
)
from ops.scripts.experiment_telemetry_runtime import (
    write_timeout_failure_artifact as telemetry_write_timeout_failure_artifact,
)
from ops.scripts.runtime_context import RuntimeContext

from .mechanism_run_common_runtime import ExperimentResolution


def run_rel(run_id: str, filename: str) -> str:
    return telemetry_run_rel(run_id, filename)


def load_run_ledger(vault: Path, run_id: str) -> dict[str, Any]:
    return telemetry_load_run_ledger(vault, run_id)


def write_run_ledger(vault: Path, run_id: str, ledger: dict[str, Any]) -> None:
    telemetry_write_run_ledger(vault, run_id, ledger)


def append_ledger_event(
    vault: Path,
    run_id: str,
    *,
    event_type: str,
    summary: str,
    artifacts: list[str],
    decision: str,
    context: RuntimeContext,
    status: str | None = None,
    decision_event: dict[str, Any] | None = None,
) -> None:
    telemetry_append_ledger_event(
        vault,
        run_id,
        event_type=event_type,
        summary=summary,
        artifacts=artifacts,
        decision=decision,
        context=context,
        status=status,
        decision_event=decision_event,
    )


def write_command_logs(vault: Path, run_id: str, prefix: str, result: dict[str, Any]) -> list[str]:
    return telemetry_write_command_logs(vault, run_id, prefix, result)


def write_timeout_failure_artifact(
    vault: Path,
    run_id: str,
    *,
    phase: str,
    command: dict[str, Any],
    result: dict[str, Any],
    artifacts: dict[str, Any],
    context: RuntimeContext,
    role: str = "",
    diagnostics: dict[str, Any] | None = None,
) -> str:
    return telemetry_write_timeout_failure_artifact(
        vault,
        run_id,
        phase=phase,
        command=command,
        result=result,
        artifacts=artifacts,
        context=context,
        role=role,
        diagnostics=diagnostics,
    )


def _timeout_failure_artifacts(vault: Path, run_id: str) -> list[str]:
    run_dir = Path(vault) / run_rel(run_id, "")
    if not run_dir.exists():
        return []
    return [
        run_rel(run_id, path.name)
        for path in sorted(run_dir.glob("*-timeout-failure.json"))
        if path.is_file()
    ]


def write_experiment_telemetry(
    vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    result: dict[str, Any],
) -> str:
    payload = {
        "session_id": "",
        "run_id": run_id,
        "generated_at": resolution.context.isoformat_z(),
        "proposal_id": "",
        "proposal_snapshot": (
            run_rel(run_id, "proposal-snapshot.json")
            if resolution.proposal is not None
            else ""
        ),
        "scope_freeze": resolution.scope_freeze_path,
        "routing_reports": resolution.routing_report_paths,
        "executor_reports": resolution.executor_report_paths,
        "primary_targets": resolution.primary_targets,
        "supporting_targets": resolution.supporting_targets,
        "test_files": resolution.test_files,
        "phase_durations": {},
        "failure_taxonomy": "",
        "command_timeouts": {
            "mutation_command": {
                "timed_out": bool(result.get("mutation_command", {}).get("timed_out", False)),
                "timeout_seconds": result.get("mutation_command", {}).get("timeout_seconds", 0),
                "termination_reason": result.get("mutation_command", {}).get("termination_reason", ""),
            },
            "repo_health": {
                "timed_out": bool(result.get("repo_health", {}).get("timed_out", False)),
                "timeout_seconds": result.get("repo_health", {}).get("timeout_seconds", 0),
                "termination_reason": result.get("repo_health", {}).get("termination_reason", ""),
            },
        },
        "decision": result.get("decision", ""),
        "finalized": result.get("finalized", False),
        "finalize_result": result.get("finalize_result", {}),
    }
    if isinstance(result.get("workspace_preparation"), dict):
        payload["workspace_preparation"] = result["workspace_preparation"]
    if isinstance(result.get("post_mutation_generated_artifact_convergence"), dict):
        payload["post_mutation_generated_artifact_convergence"] = result[
            "post_mutation_generated_artifact_convergence"
        ]
    if isinstance(result.get("decision_record"), dict):
        payload["decision_record"] = result["decision_record"]
    if isinstance(result.get("failure_taxonomy"), str) and result["failure_taxonomy"].strip():
        payload["failure_taxonomy"] = result["failure_taxonomy"]
    timeout_failure_artifacts = _timeout_failure_artifacts(vault, run_id)
    if timeout_failure_artifacts:
        payload["timeout_failure_artifacts"] = timeout_failure_artifacts
    if isinstance(result.get("behavior_delta"), str) and result["behavior_delta"].strip():
        payload["behavior_delta"] = result["behavior_delta"]
    if (
        isinstance(result.get("structural_complexity_budget"), str)
        and result["structural_complexity_budget"].strip()
    ):
        payload["structural_complexity_budget"] = result["structural_complexity_budget"]
    if isinstance(result.get("apply_mode"), str) and result["apply_mode"].strip():
        payload["apply_mode"] = result["apply_mode"]
    if isinstance(result.get("apply_status"), str) and result["apply_status"].strip():
        payload["apply_status"] = result["apply_status"]
    if isinstance(result.get("live_applied"), bool):
        payload["live_applied"] = result["live_applied"]
    if isinstance(result.get("shadow_apply_report"), str) and result["shadow_apply_report"].strip():
        payload["shadow_apply_report"] = result["shadow_apply_report"]
    if (
        isinstance(result.get("rollback_rehearsal_report"), str)
        and result["rollback_rehearsal_report"].strip()
    ):
        payload["rollback_rehearsal_report"] = result["rollback_rehearsal_report"]
    return write_run_telemetry(vault, run_id, payload)
