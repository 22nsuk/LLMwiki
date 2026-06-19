from __future__ import annotations

import hashlib
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ops.scripts.core.behavior_delta_runtime import (
    build_behavior_delta_report,
    write_behavior_delta_report,
)
from ops.scripts.core.command_runtime import run_with_timeout
from ops.scripts.core.filesystem_runtime import (
    FilesystemTransactionError,
    apply_manifest_transaction,
    plan_manifest_apply_transaction,
    rehearse_manifest_apply_rollback,
)
from ops.scripts.core.observability_artifacts_runtime import (
    write_run_artifact_fingerprint,
)
from ops.scripts.core.path_runtime import normalize_repo_path_text
from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
    SHADOW_APPLY_REPORT_SCHEMA_PATH,
)

from .improvement_observations_runtime import IMPROVEMENT_OBSERVATIONS_FILENAME
from .mechanism_run_candidate_snapshot_runtime import (
    write_candidate_changed_files_snapshot,
)
from .mechanism_run_common_runtime import (
    CommandStepResult,
    ExperimentResolution,
    RepoHealthStepResult,
    RunMechanismExperimentUsageError,
    ScaffoldedRun,
    WorkspaceApplyResult,
    WorkspacePreparation,
    load_json,
    sanitize_path_text,
    timestamp,
    write_json,
)
from .mechanism_run_ledger_runtime import (
    append_ledger_event,
    run_rel,
    write_command_logs,
    write_experiment_telemetry,
    write_timeout_failure_artifact,
)
from .mechanism_run_mutation_step_runtime import (
    MutationStepDependencies,
    execute_mutation_step,
)
from .mechanism_run_repo_health_step_runtime import (
    RepoHealthStepDependencies,
    repo_health_step,
    write_structural_complexity_budget_artifact,
)
from .mechanism_run_scaffold_resolution_runtime import _command_argv
from .planning_gate_validate import validate_run_dir

CHANGED_FILES_MANIFEST_SCHEMA = CHANGED_FILES_MANIFEST_SCHEMA_PATH
ROLLBACK_REHEARSAL_REPORT_SCHEMA = ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH
SHADOW_APPLY_REPORT_SCHEMA = SHADOW_APPLY_REPORT_SCHEMA_PATH
FULL_WORKSPACE_DIFF_MODEL = "full_workspace"
COPIED_UNIVERSE_DIFF_MODEL = "copied_universe"
WORKSPACE_IGNORE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".coverage",
    ".DS_Store",
    ".git",
    ".obsidian",
    ".venv",
    ".idea",
    ".vscode",
}
WORKSPACE_IGNORE_SUFFIXES = {".pyc", ".pyo"}
CHANGED_FILES_MANIFEST_IGNORED_PREFIX_REASONS = {
    "ops/reports/": "generated_report_surface",
    "tmp/": "transient_workspace_surface",
}
CHANGED_FILES_MANIFEST_IGNORED_PATH_REASONS = {
    "ops/script-output-surfaces.json": "generated_report_surface",
}


def _copytree_ignore(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in WORKSPACE_IGNORE_NAMES:
            ignored.add(name)
            continue
        if Path(name).suffix in WORKSPACE_IGNORE_SUFFIXES:
            ignored.add(name)
    return ignored


def _is_ignored_candidate_surface(rel_path: str, *, run_id: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    if normalized == f"runs/{run_id}" or normalized.startswith(f"runs/{run_id}/"):
        return True
    parts = [part for part in Path(normalized).parts if part not in {".", ""}]
    return any(part in WORKSPACE_IGNORE_NAMES for part in parts)


def _snapshot_repo_file_digests(root: Path, *, run_id: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root).as_posix()
        if _is_ignored_candidate_surface(rel_path, run_id=run_id):
            continue
        if path.suffix in WORKSPACE_IGNORE_SUFFIXES:
            continue
        files[rel_path] = _file_digest(path)
    return files


def _snapshot_repo_file_count(root: Path, *, run_id: str) -> int:
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root).as_posix()
        if _is_ignored_candidate_surface(rel_path, run_id=run_id):
            continue
        if path.suffix in WORKSPACE_IGNORE_SUFFIXES:
            continue
        count += 1
    return count


def _overlay_workspace_digest_changes(
    workspace_vault: Path,
    report_workspace_vault: Path,
    *,
    run_id: str,
    baseline_file_digests: dict[str, str],
) -> list[str]:
    candidate_file_digests = _snapshot_repo_file_digests(workspace_vault, run_id=run_id)
    changed_paths: list[str] = []
    for rel_path in sorted(set(baseline_file_digests) | set(candidate_file_digests)):
        baseline_digest = baseline_file_digests.get(rel_path)
        candidate_digest = candidate_file_digests.get(rel_path)
        if baseline_digest == candidate_digest:
            continue
        changed_paths.append(rel_path)
        destination = report_workspace_vault / rel_path
        if candidate_digest is None:
            if destination.exists() or destination.is_symlink():
                destination.unlink()
                _remove_empty_parent_dirs(destination, stop_at=report_workspace_vault)
            continue
        source = workspace_vault / rel_path
        if not source.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return changed_paths


def _prepare_candidate_report_workspace(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    workspace_root: str,
    baseline_file_digests: dict[str, str],
    diff_model: str,
) -> Path:
    if diff_model != COPIED_UNIVERSE_DIFF_MODEL:
        return workspace_vault
    report_workspace_vault = Path(workspace_root) / "vault"
    shutil.copytree(vault, report_workspace_vault, ignore=_copytree_ignore)
    _overlay_workspace_digest_changes(
        workspace_vault,
        report_workspace_vault,
        run_id=run_id,
        baseline_file_digests=baseline_file_digests,
    )
    return report_workspace_vault


def _changed_files_manifest_ignore_reason(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/")
    path_reason = CHANGED_FILES_MANIFEST_IGNORED_PATH_REASONS.get(normalized)
    if path_reason:
        return path_reason
    for prefix, reason in CHANGED_FILES_MANIFEST_IGNORED_PREFIX_REASONS.items():
        if normalized.startswith(prefix):
            return reason
    return ""


def _normalize_sparse_copy_entry(value: str) -> str:
    raw = str(value).strip().replace("\\", "/").rstrip("/")
    normalized = normalize_repo_path_text(raw)
    if (
        normalized is None or normalized in {".", ".."} or normalized.startswith(("../", "/"))
    ):
        raise RunMechanismExperimentUsageError(f"invalid sparse workspace copy entry: {value}")
    return normalized


def _sparse_copy_entries(
    *,
    allowed_apply_roots: list[str],
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
    declared_dependencies: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in [
        *allowed_apply_roots,
        *primary_targets,
        *supporting_targets,
        *test_files,
        *declared_dependencies,
    ]:
        normalized = _normalize_sparse_copy_entry(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _copy_sparse_file(source: Path, destination: Path) -> None:
    if source.is_symlink():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_sparse_entry(vault: Path, workspace_vault: Path, rel_path: str, *, run_id: str) -> None:
    source = vault / rel_path
    if not source.exists():
        raise RunMechanismExperimentUsageError(
            f"sparse workspace copy entry does not exist: {rel_path}"
        )
    if _is_ignored_candidate_surface(rel_path, run_id=run_id):
        return
    if source.is_file():
        if source.suffix not in WORKSPACE_IGNORE_SUFFIXES:
            _copy_sparse_file(source, workspace_vault / rel_path)
        return
    if not source.is_dir():
        return
    for child in sorted(source.rglob("*")):
        if not child.is_file():
            continue
        child_rel = child.relative_to(vault).as_posix()
        if _is_ignored_candidate_surface(child_rel, run_id=run_id):
            continue
        if child.suffix in WORKSPACE_IGNORE_SUFFIXES:
            continue
        _copy_sparse_file(child, workspace_vault / child_rel)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_changed_files_manifest(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
    baseline_file_digests: dict[str, str] | None = None,
    diff_model: str = FULL_WORKSPACE_DIFF_MODEL,
    context: RuntimeContext | None = None,
) -> str:
    if diff_model not in {FULL_WORKSPACE_DIFF_MODEL, COPIED_UNIVERSE_DIFF_MODEL}:
        raise RunMechanismExperimentUsageError(f"unsupported changed-files diff model: {diff_model}")
    baseline_files = (
        dict(baseline_file_digests)
        if baseline_file_digests is not None
        else _snapshot_repo_file_digests(vault, run_id=run_id)
    )
    candidate_files = _snapshot_repo_file_digests(workspace_vault, run_id=run_id)
    changed_files: list[dict] = []
    ignored_changes: list[dict] = []
    added = 0
    modified = 0
    deleted = 0
    ignored_added = 0
    ignored_modified = 0
    ignored_deleted = 0
    for rel_path in sorted(set(baseline_files) | set(candidate_files)):
        baseline_digest = baseline_files.get(rel_path)
        candidate_digest = candidate_files.get(rel_path)
        if baseline_digest is None:
            change_type = "added"
        elif candidate_digest is None:
            change_type = "deleted"
        elif baseline_digest != candidate_digest:
            change_type = "modified"
        else:
            continue
        ignore_reason = _changed_files_manifest_ignore_reason(rel_path)
        if ignore_reason:
            if change_type == "added":
                ignored_added += 1
            elif change_type == "deleted":
                ignored_deleted += 1
            elif change_type == "modified":
                ignored_modified += 1
            ignored_changes.append(
                {
                    "path": rel_path,
                    "change_type": change_type,
                    "reason": ignore_reason,
                }
            )
            continue
        if change_type == "added":
            added += 1
        elif change_type == "deleted":
            deleted += 1
        elif change_type == "modified":
            modified += 1
        changed_files.append({"path": rel_path, "change_type": change_type})

    payload = {
        "$schema": CHANGED_FILES_MANIFEST_SCHEMA,
        "run_id": run_id,
        "generated_at": timestamp(context),
        "declared_targets": {
            "primary_targets": primary_targets,
            "supporting_targets": supporting_targets,
            "test_files": test_files,
        },
        "summary": {
            "total_changed_files": len(changed_files),
            "added": added,
            "modified": modified,
            "deleted": deleted,
        },
        "diff_universe": {
            "model": diff_model,
            "baseline_file_count": len(baseline_files),
            "candidate_file_count": len(candidate_files),
        },
        "files": changed_files,
    }
    if ignored_changes:
        payload["ignored_changes"] = {
            "summary": {
                "total_ignored_files": len(ignored_changes),
                "added": ignored_added,
                "modified": ignored_modified,
                "deleted": ignored_deleted,
            },
            "ignored_prefixes": sorted(CHANGED_FILES_MANIFEST_IGNORED_PREFIX_REASONS),
            "files": ignored_changes,
        }
    manifest_rel = run_rel(run_id, "changed-files-manifest.json")
    write_json(vault, manifest_rel, payload, CHANGED_FILES_MANIFEST_SCHEMA)
    return manifest_rel


def _write_behavior_delta_artifact(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    changed_files_manifest: str,
) -> str:
    input_artifacts = {
        "baseline_eval_report": run_rel(run_id, "baseline-eval.json"),
        "candidate_eval_report": run_rel(run_id, "candidate-eval.json"),
        "baseline_lint_report": run_rel(run_id, "baseline-lint.json"),
        "candidate_lint_report": run_rel(run_id, "candidate-lint.json"),
        "baseline_mechanism_report": run_rel(run_id, "baseline-mechanism-assessment.json"),
        "candidate_mechanism_report": run_rel(run_id, "candidate-mechanism-assessment.json"),
        "changed_files_manifest": changed_files_manifest,
    }
    report = build_behavior_delta_report(
        baseline_root=vault,
        candidate_root=workspace_vault,
        run_id=run_id,
        generated_at=timestamp(resolution.context),
        policy_path=resolution.policy_path_text,
        policy=resolution.policy,
        primary_targets=resolution.primary_targets,
        supporting_targets=resolution.supporting_targets,
        test_files=resolution.test_files,
        input_artifacts=input_artifacts,
        changed_files_manifest=load_json(vault / changed_files_manifest),
    )
    return write_behavior_delta_report(
        vault=vault,
        report_path=run_rel(run_id, "behavior-delta.json"),
        report=report,
    )


def _write_candidate_changed_files_snapshot(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    context: RuntimeContext,
    changed_files_manifest: str,
    decision: str,
    apply_mode: str,
    apply_status: str,
    live_applied: bool,
    capture_reason: str,
) -> str:
    return write_candidate_changed_files_snapshot(
        vault,
        workspace_vault,
        run_id=run_id,
        changed_files_manifest=changed_files_manifest,
        decision=decision,
        apply_mode=apply_mode,
        apply_status=apply_status,
        live_applied=live_applied,
        capture_reason=capture_reason,
        context=context,
    )


def _schema_backed_run_report_writer(
    vault: Path,
    schema_rel_path: str,
) -> Callable[[Path, dict[str, Any]], Path]:
    def _write(path: Path, report: dict[str, Any]) -> Path:
        write_json(vault, report_path(vault, path), report, schema_rel_path)
        return path

    return _write


def _remove_empty_parent_dirs(path: Path, *, stop_at: Path) -> None:
    current = path.parent
    resolved_stop = stop_at.resolve()
    while current != resolved_stop and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _apply_workspace_changes(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    context: RuntimeContext,
    decision: str,
    manifest_rel: str,
    allowed_apply_roots: list[str],
) -> WorkspaceApplyResult:
    manifest = load_json(vault / manifest_rel)
    shadow_apply_report = run_rel(run_id, "shadow-apply-report.json")
    rollback_rehearsal_report = run_rel(run_id, "rollback-rehearsal-report.json")
    plan_manifest_apply_transaction(
        vault,
        workspace_vault,
        manifest,
        allowed_apply_roots=allowed_apply_roots,
        shadow_report_path=vault / shadow_apply_report,
        shadow_report_generated_at=context.isoformat_z(),
        shadow_report_writer=_schema_backed_run_report_writer(vault, SHADOW_APPLY_REPORT_SCHEMA),
    )
    rehearsal_report = rehearse_manifest_apply_rollback(
        vault,
        workspace_vault,
        manifest,
        allowed_apply_roots=allowed_apply_roots,
        rollback_rehearsal_report_path=vault / rollback_rehearsal_report,
        rollback_rehearsal_generated_at=context.isoformat_z(),
        shadow_report_ref=shadow_apply_report,
        rollback_rehearsal_report_writer=_schema_backed_run_report_writer(
            vault,
            ROLLBACK_REHEARSAL_REPORT_SCHEMA,
        ),
    )
    if rehearsal_report["status"] != "pass":
        raise FilesystemTransactionError(
            f"rollback rehearsal failed before live apply: {rollback_rehearsal_report}"
        )
    append_ledger_event(
        vault,
        run_id,
        event_type="workspace_rollback_rehearsed",
        summary="Rehearsed workspace apply and rollback before mutating the live repository.",
        artifacts=[manifest_rel, shadow_apply_report, rollback_rehearsal_report],
        decision=decision,
        context=context,
        status="running",
    )
    apply_manifest_transaction(
        vault,
        workspace_vault,
        manifest,
        allowed_apply_roots=allowed_apply_roots,
    )
    return WorkspaceApplyResult(
        apply_mode="live",
        apply_status="live_applied",
        live_applied=True,
        shadow_apply_report=shadow_apply_report,
        rollback_rehearsal_report=rollback_rehearsal_report,
    )


def _plan_workspace_changes(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    context: RuntimeContext,
    manifest_rel: str,
    allowed_apply_roots: list[str],
) -> str:
    manifest = load_json(vault / manifest_rel)
    shadow_apply_report = run_rel(run_id, "shadow-apply-report.json")
    plan_manifest_apply_transaction(
        vault,
        workspace_vault,
        manifest,
        allowed_apply_roots=allowed_apply_roots,
        shadow_report_path=vault / shadow_apply_report,
        shadow_report_generated_at=context.isoformat_z(),
        shadow_report_writer=_schema_backed_run_report_writer(vault, SHADOW_APPLY_REPORT_SCHEMA),
    )
    return shadow_apply_report


def _prepare_workspace_copy(
    vault: Path,
    *,
    run_id: str,
    workspace_root: str,
    mode: str = "full_copy",
    allowed_apply_roots: list[str] | None = None,
    primary_targets: list[str] | None = None,
    supporting_targets: list[str] | None = None,
    test_files: list[str] | None = None,
    declared_dependencies: list[str] | None = None,
) -> WorkspacePreparation:
    if mode == "sparse_manifest":
        return _prepare_sparse_workspace_copy(
            vault,
            run_id=run_id,
            workspace_root=workspace_root,
            allowed_apply_roots=list(allowed_apply_roots or []),
            primary_targets=list(primary_targets or []),
            supporting_targets=list(supporting_targets or []),
            test_files=list(test_files or []),
            declared_dependencies=list(declared_dependencies or []),
        )
    if mode != "full_copy":
        raise RunMechanismExperimentUsageError(f"unsupported workspace preparation mode: {mode}")
    started = time.monotonic()
    digest_started = time.monotonic()
    baseline_file_digests = _snapshot_repo_file_digests(vault, run_id=run_id)
    digest_seconds = round(time.monotonic() - digest_started, 3)
    workspace_vault = Path(workspace_root) / "vault"
    copy_started = time.monotonic()
    shutil.copytree(vault, workspace_vault, ignore=_copytree_ignore)
    copy_seconds = round(time.monotonic() - copy_started, 3)
    copied_file_count = _snapshot_repo_file_count(workspace_vault, run_id=run_id)
    return WorkspacePreparation(
        workspace_vault=workspace_vault,
        baseline_file_digests=baseline_file_digests,
        telemetry={
            "mode": mode,
            "diff_model": FULL_WORKSPACE_DIFF_MODEL,
            "baseline_file_count": len(baseline_file_digests),
            "copied_file_count": copied_file_count,
            "diff_universe_file_count": len(baseline_file_digests),
            "copy_entry_count": 1,
            "phase_durations": {
                "digest": digest_seconds,
                "copy": copy_seconds,
                "total": round(time.monotonic() - started, 3),
            },
        },
    )


def _prepare_sparse_workspace_copy(
    vault: Path,
    *,
    run_id: str,
    workspace_root: str,
    allowed_apply_roots: list[str],
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
    declared_dependencies: list[str],
) -> WorkspacePreparation:
    if not allowed_apply_roots:
        raise RunMechanismExperimentUsageError(
            "sparse_manifest workspace preparation requires allowed_apply_roots"
        )
    started = time.monotonic()
    digest_started = time.monotonic()
    baseline_file_count = _snapshot_repo_file_count(vault, run_id=run_id)
    digest_seconds = round(time.monotonic() - digest_started, 3)
    workspace_vault = Path(workspace_root) / "vault"
    workspace_vault.mkdir(parents=True, exist_ok=True)
    copy_entries = _sparse_copy_entries(
        allowed_apply_roots=allowed_apply_roots,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        test_files=test_files,
        declared_dependencies=declared_dependencies,
    )

    copy_started = time.monotonic()
    for rel_path in copy_entries:
        _copy_sparse_entry(vault, workspace_vault, rel_path, run_id=run_id)
    copy_seconds = round(time.monotonic() - copy_started, 3)
    baseline_file_digests = _snapshot_repo_file_digests(workspace_vault, run_id=run_id)
    copied_file_count = _snapshot_repo_file_count(workspace_vault, run_id=run_id)
    return WorkspacePreparation(
        workspace_vault=workspace_vault,
        baseline_file_digests=baseline_file_digests,
        telemetry={
            "mode": "sparse_manifest",
            "diff_model": COPIED_UNIVERSE_DIFF_MODEL,
            "baseline_file_count": baseline_file_count,
            "copied_file_count": copied_file_count,
            "diff_universe_file_count": len(baseline_file_digests),
            "copy_entry_count": len(copy_entries),
            "phase_durations": {
                "digest": digest_seconds,
                "copy": copy_seconds,
                "total": round(time.monotonic() - started, 3),
            },
        },
    )


def _run_command(
    command: str,
    *,
    cwd: Path,
    timeout_seconds: int,
    argv: list[str] | None = None,
) -> dict:
    resolved_argv = list(argv) if argv is not None else _command_argv(command, cwd=cwd)
    completed = run_with_timeout(
        resolved_argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    return {
        "command": command,
        "argv": resolved_argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "timed_out": completed.timed_out,
        "timeout_seconds": completed.timeout_seconds,
        "termination_reason": completed.termination_reason,
        "launch_succeeded": completed.launch_succeeded,
        "signal_sent": completed.signal_sent,
        "final_state_observed": completed.final_state_observed,
        "stdout_received": completed.stdout_received,
        "stderr_received": completed.stderr_received,
    }


def _execute_mutation_step(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
) -> CommandStepResult:
    return execute_mutation_step(
        vault,
        workspace_vault,
        run_id=run_id,
        resolution=resolution,
        dependencies=MutationStepDependencies(
            command_argv=_command_argv,
            run_command=_run_command,
            write_command_logs=write_command_logs,
            write_timeout_failure_artifact=write_timeout_failure_artifact,
            append_ledger_event=append_ledger_event,
            write_experiment_telemetry=write_experiment_telemetry,
            sanitize_path_text=sanitize_path_text,
        ),
    )


def _repo_health_step(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    baseline_file_digests: dict[str, str],
    diff_model: str = FULL_WORKSPACE_DIFF_MODEL,
) -> RepoHealthStepResult:
    return repo_health_step(
        vault,
        workspace_vault,
        run_id=run_id,
        resolution=resolution,
        baseline_file_digests=baseline_file_digests,
        diff_model=diff_model,
        dependencies=RepoHealthStepDependencies(
            command_argv=_command_argv,
            run_command=_run_command,
            write_command_logs=write_command_logs,
            write_timeout_failure_artifact=write_timeout_failure_artifact,
            append_ledger_event=append_ledger_event,
            write_changed_files_manifest=_write_changed_files_manifest,
            write_structural_complexity_budget_artifact=write_structural_complexity_budget_artifact,
            write_behavior_delta_artifact=_write_behavior_delta_artifact,
            sanitize_path_text=sanitize_path_text,
        ),
    )


def _build_repo_health_blocked_result(
    vault: Path,
    *,
    run_id: str,
    scaffold: ScaffoldedRun,
    resolution: ExperimentResolution,
    baseline_artifacts: dict,
    candidate_artifacts: dict,
    workspace_preparation: dict,
    generated_artifact_convergence: dict,
    repo_health: RepoHealthStepResult,
    candidate_changed_files_snapshot: str = "",
) -> dict:
    planning_gate = validate_run_dir(vault, scaffold.run_dir, context=resolution.context)
    failure_taxonomy = _repo_health_failure_taxonomy(repo_health)
    result = {
        "run_id": run_id,
        "run_dir": report_path(vault, scaffold.run_dir),
        "baseline_artifacts": baseline_artifacts,
        "candidate_artifacts": candidate_artifacts,
        "improvement_observations": run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME),
        "scope_freeze": resolution.scope_freeze_path,
        "routing_reports": resolution.routing_report_paths,
        "executor_reports": resolution.executor_report_paths,
        "changed_files_manifest": repo_health.changed_files_manifest,
        "structural_complexity_budget": repo_health.structural_complexity_budget,
        "behavior_delta": repo_health.behavior_delta,
        "workspace_preparation": workspace_preparation,
        "post_mutation_generated_artifact_convergence": generated_artifact_convergence,
        "failure_taxonomy": failure_taxonomy,
        "repo_health": {
            "passed": False,
            "returncode": repo_health.result["returncode"],
            "timed_out": bool(repo_health.result.get("timed_out", False)),
            "timeout_seconds": repo_health.result.get("timeout_seconds", 0),
            "termination_reason": repo_health.result.get("termination_reason", ""),
            "structural_complexity_budget_status": repo_health.structural_complexity_budget_status,
            "stdout": run_rel(run_id, "repo-health.stdout.txt"),
            "stderr": run_rel(run_id, "repo-health.stderr.txt"),
        },
        "promotion_report": "",
        "decision": "SKIPPED",
        "finalized": False,
        "planning_gate": {
            "phase": planning_gate["phase"],
            "status": planning_gate["status"],
        },
    }
    if candidate_changed_files_snapshot:
        result["candidate_changed_files_snapshot"] = candidate_changed_files_snapshot
    write_experiment_telemetry(vault, run_id=run_id, resolution=resolution, result=result)
    result["run_artifact_fingerprint"] = write_run_artifact_fingerprint(
        vault,
        run_id,
        context=resolution.context,
    )
    return result


def _repo_health_failure_taxonomy(repo_health: RepoHealthStepResult) -> str:
    if repo_health.failure_taxonomy:
        return repo_health.failure_taxonomy
    if (
        repo_health.result["returncode"] == 0
        and repo_health.structural_complexity_budget_status != "pass"
    ):
        return "structural_complexity_non_regression"
    return "repo_health_blocked"


def _apply_or_discard_workspace_changes(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str | None = None,
    context: RuntimeContext | None = None,
    decision: str,
    changed_files_manifest: str,
    allowed_apply_roots: list[str],
    apply_mode: str = "live",
) -> WorkspaceApplyResult:
    if decision != "PROMOTE":
        return WorkspaceApplyResult(
            apply_mode=apply_mode,
            apply_status="not_applicable",
            live_applied=False,
            shadow_apply_report="",
            rollback_rehearsal_report="",
        )
    if apply_mode == "canary_only":
        if run_id is None or context is None:
            raise RunMechanismExperimentUsageError(
                "canary_only apply mode requires run_id and context"
            )
        shadow_apply_report = _plan_workspace_changes(
            vault,
            workspace_vault,
            run_id=run_id,
            context=context,
            manifest_rel=changed_files_manifest,
            allowed_apply_roots=allowed_apply_roots,
        )
        append_ledger_event(
            vault,
            run_id,
            event_type="workspace_apply_canary_ready",
            summary="Prepared workspace changes as a canary-only apply plan; live repository was not mutated.",
            artifacts=[changed_files_manifest, shadow_apply_report],
            decision=decision,
            context=context,
            status="running",
        )
        return WorkspaceApplyResult(
            apply_mode=apply_mode,
            apply_status="canary_ready",
            live_applied=False,
            shadow_apply_report=shadow_apply_report,
            rollback_rehearsal_report="",
        )
    if apply_mode != "live":
        raise RunMechanismExperimentUsageError(f"unsupported apply mode: {apply_mode}")
    if run_id is None or context is None:
        raise RunMechanismExperimentUsageError(
            "live apply mode requires run_id and context for rollback rehearsal"
        )
    apply_result = _apply_workspace_changes(
        vault,
        workspace_vault,
        run_id=run_id,
        context=context,
        decision=decision,
        manifest_rel=changed_files_manifest,
        allowed_apply_roots=allowed_apply_roots,
    )
    append_ledger_event(
        vault,
        run_id,
        event_type="workspace_applied",
        summary="Applied workspace changes to the live repository after promotion.",
        artifacts=[
            changed_files_manifest,
            apply_result.shadow_apply_report,
            apply_result.rollback_rehearsal_report,
        ],
        decision=decision,
        context=context,
        status="running",
    )
    return apply_result
