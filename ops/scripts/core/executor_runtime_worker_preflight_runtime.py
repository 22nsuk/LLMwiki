from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import write_vault_schema_validated_json
from ops.scripts.core.executor_runtime_errors_runtime import (
    ExecutorRuntimeExecutionError,
)
from ops.scripts.core.experiment_telemetry_runtime import append_ledger_event
from ops.scripts.core.run_artifact_envelope_runtime import (
    maybe_embed_run_artifact_envelope,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
)
from ops.scripts.core.trusted_candidate_runner import (
    TrustedCandidateRunRequest,
    resolve_trusted_repo_health_argv,
    run_trusted_candidate_command,
)
from ops.scripts.eval.structural_complexity_budget_runtime import (
    DEFAULT_TARGET_PROFILES,
    build_report as build_structural_complexity_budget_report,
    touched_target_profiles,
)
from ops.scripts.mechanism.structural_complexity_scope_runtime import (
    structural_complexity_source_targets,
)

WORKER_REPO_HEALTH_PREFLIGHT_STDOUT = "worker-repo-health-preflight.stdout.txt"
WORKER_REPO_HEALTH_PREFLIGHT_STDERR = "worker-repo-health-preflight.stderr.txt"
WORKER_STRUCTURAL_COMPLEXITY_PREFLIGHT = "worker-structural-complexity-preflight.json"


def stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def write_worker_repo_health_preflight_logs(
    artifact_root: Path,
    *,
    run_id: str,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> tuple[str, str]:
    run_dir = artifact_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_rel = f"runs/{run_id}/{WORKER_REPO_HEALTH_PREFLIGHT_STDOUT}"
    stderr_rel = f"runs/{run_id}/{WORKER_REPO_HEALTH_PREFLIGHT_STDERR}"
    (artifact_root / stdout_rel).write_text(stream_text(stdout), encoding="utf-8")
    (artifact_root / stderr_rel).write_text(stream_text(stderr), encoding="utf-8")
    return stdout_rel, stderr_rel


def worker_repo_health_preflight_detail(
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> str:
    combined = "\n".join(
        text
        for text in (stream_text(stderr).strip(), stream_text(stdout).strip())
        if text
    )
    if not combined:
        return "no output"
    return combined[-1000:]


def write_worker_structural_complexity_preflight_report(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    policy_path: str,
    changed_targets: list[str],
    context: RuntimeContext,
) -> tuple[str, dict[str, Any]]:
    source_targets = structural_complexity_source_targets(changed_targets)
    report = build_structural_complexity_budget_report(
        workspace_root,
        policy_path=policy_path,
        context=context,
        target_profiles=touched_target_profiles(DEFAULT_TARGET_PROFILES, source_targets),
    )
    rel_path = f"runs/{run_id}/{WORKER_STRUCTURAL_COMPLEXITY_PREFLIGHT}"
    payload = maybe_embed_run_artifact_envelope(
        artifact_root,
        rel_path,
        report,
        schema_path=STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
    )
    write_vault_schema_validated_json(
        artifact_root,
        rel_path,
        payload,
        STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
        context=f"schema validation failed for {rel_path}",
    )
    return rel_path, payload


def worker_structural_complexity_detail(report: dict[str, Any]) -> str:
    targets = [
        target
        for target in report.get("targets", [])
        if isinstance(target, dict) and str(target.get("status", "")) != "pass"
    ]
    if not targets:
        return "no structural attention details"
    details: list[str] = []
    for target in targets[:3]:
        details.append(
            "{path}: status={status}; over_budget={over_budget}; "
            "function_budget_candidate_count={candidate_count}".format(
                path=target.get("path", ""),
                status=target.get("status", ""),
                over_budget=",".join(str(item) for item in target.get("over_budget_metrics", [])),
                candidate_count=target.get("function_budget_candidate_count", 0),
            )
        )
    return " | ".join(details)


def trusted_python_for_candidate_runs(vault_root: Path) -> Path:
    repo_python = vault_root / ".venv" / "bin" / "python"
    if repo_python.is_file():
        return repo_python.resolve()
    return Path(sys.executable).resolve()


def run_worker_structural_complexity_preflight(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    policy_path: str,
    changed_targets: list[str],
    context: RuntimeContext,
) -> None:
    report_rel, report = write_worker_structural_complexity_preflight_report(
        artifact_root,
        workspace_root=workspace_root,
        run_id=run_id,
        policy_path=policy_path,
        changed_targets=changed_targets,
        context=context,
    )
    status = str(report.get("status", "")).strip()
    if status != "pass":
        append_ledger_event(
            artifact_root,
            run_id,
            event_type="validation_blocked",
            summary="Checked worker structural complexity before non-worker executor roles.",
            artifacts=[report_rel],
            decision=f"worker_structural_complexity_preflight_{status or 'unknown'}",
            context=context,
            status="blocked",
        )
        raise ExecutorRuntimeExecutionError(
            "worker structural complexity preflight blocked before "
            "reviewer/validator/auditor execution; "
            f"report={report_rel}; status={status or 'unknown'}; "
            f"detail={worker_structural_complexity_detail(report)}"
        )


def run_worker_repo_health_preflight(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    test_files: list[str],
    workspace_mode: str,
    timeout_seconds: int,
    context: RuntimeContext,
) -> None:
    trusted_python = trusted_python_for_candidate_runs(artifact_root)
    command = resolve_trusted_repo_health_argv(
        test_files=test_files,
        workspace_mode=workspace_mode,
        workspace_root=workspace_root,
        trusted_vault_root=artifact_root,
        trusted_python=trusted_python,
    )
    outcome = run_trusted_candidate_command(
        TrustedCandidateRunRequest(
            purpose="worker_repo_health_preflight",
            argv=command,
            workspace_root=workspace_root,
            trusted_vault_root=artifact_root,
            trusted_python=trusted_python,
            timeout_seconds=timeout_seconds,
            cwd=workspace_root,
            audit_rel_path=f"runs/{run_id}/worker-repo-health-preflight.audit.json",
        )
    )
    completed_stdout = outcome.stdout
    completed_stderr = outcome.stderr
    if outcome.timed_out:
        stdout_rel, stderr_rel = write_worker_repo_health_preflight_logs(
            artifact_root,
            run_id=run_id,
            stdout=completed_stdout,
            stderr=completed_stderr,
        )
        append_ledger_event(
            artifact_root,
            run_id,
            event_type="worker_repo_health_preflight_checked",
            summary="Checked worker repo-health preflight before non-worker executor roles.",
            artifacts=[stdout_rel, stderr_rel],
            decision="worker_repo_health_preflight_timeout",
            context=context,
            status="blocked",
        )
        raise ExecutorRuntimeExecutionError(
            "worker repo-health preflight timed out before reviewer/validator/auditor "
            f"execution; command={' '.join(outcome.argv)}; stdout={stdout_rel}; stderr={stderr_rel}"
        )
    if outcome.returncode == 126:
        stdout_rel, stderr_rel = write_worker_repo_health_preflight_logs(
            artifact_root,
            run_id=run_id,
            stdout=completed_stdout,
            stderr=completed_stderr,
        )
        append_ledger_event(
            artifact_root,
            run_id,
            event_type="worker_repo_health_preflight_checked",
            summary="Checked worker repo-health preflight before non-worker executor roles.",
            artifacts=[stdout_rel, stderr_rel],
            decision="worker_repo_health_preflight_failed_to_start",
            context=context,
            status="blocked",
        )
        raise ExecutorRuntimeExecutionError(
            "worker repo-health preflight could not start before reviewer/validator/auditor "
            f"execution; command={' '.join(outcome.argv)}; stdout={stdout_rel}; stderr={stderr_rel}"
        )
    stdout_rel, stderr_rel = write_worker_repo_health_preflight_logs(
        artifact_root,
        run_id=run_id,
        stdout=completed_stdout,
        stderr=completed_stderr,
    )
    if outcome.returncode != 0:
        append_ledger_event(
            artifact_root,
            run_id,
            event_type="worker_repo_health_preflight_checked",
            summary="Checked worker repo-health preflight before non-worker executor roles.",
            artifacts=[stdout_rel, stderr_rel],
            decision="worker_repo_health_preflight_fail",
            context=context,
            status="blocked",
        )
        detail = worker_repo_health_preflight_detail(completed_stdout, completed_stderr)
        raise ExecutorRuntimeExecutionError(
            "worker repo-health preflight failed before reviewer/validator/auditor "
            f"execution; command={' '.join(outcome.argv)}; stdout={stdout_rel}; "
            f"stderr={stderr_rel}; detail={detail}"
        )
    append_ledger_event(
        artifact_root,
        run_id,
        event_type="worker_repo_health_preflight_checked",
        summary="Checked worker repo-health preflight before non-worker executor roles.",
        artifacts=[stdout_rel, stderr_rel],
        decision="worker_repo_health_preflight_pass",
        context=context,
    )
