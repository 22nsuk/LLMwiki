from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from ops.scripts.core.path_classification_runtime import (
    LOCAL_SOURCE_CONTRACT_FILES,
    PUBLIC_SOURCE_FILES,
    PUBLIC_SOURCE_PREFIXES,
    classify_path,
)
from ops.scripts.eval.structural_complexity_budget_runtime import (
    DEFAULT_TARGET_PROFILES,
    build_report as build_structural_complexity_budget_report,
    touched_target_profiles,
)
from ops.scripts.mechanism.mechanism_run_scaffold_resolution_runtime import (
    command_argv,
    default_check_command,
)
from ops.scripts.mechanism.structural_complexity_scope_runtime import (
    structural_complexity_source_targets,
)

from .artifact_io_runtime import write_vault_schema_validated_json
from .codex_exec_executor import CodexExecError, execute_codex_exec_role
from .executor_noop_runtime import executor_noop_mutation_failure_message
from .experiment_telemetry_runtime import append_ledger_event
from .policy_runtime import load_policy, workspace_preparation_mode_from_policy
from .run_artifact_envelope_runtime import maybe_embed_run_artifact_envelope
from .runtime_context import RuntimeContext
from .schema_constants_runtime import STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH
from .script_output_surfaces import build_registry, write_registry

ROLE_ORDER = ("worker", "reviewer", "validator")
SCRIPT_OUTPUT_SURFACES_TARGET = "ops/script-output-surfaces.json"
SCRIPT_OUTPUT_SURFACES_MODULE = "ops/scripts/core/script_output_surfaces.py"
OPS_SCRIPTS_PREFIX = "ops/scripts/"
WORKER_REPO_HEALTH_PREFLIGHT_STDOUT = "worker-repo-health-preflight.stdout.txt"
WORKER_REPO_HEALTH_PREFLIGHT_STDERR = "worker-repo-health-preflight.stderr.txt"
WORKER_STRUCTURAL_COMPLEXITY_PREFLIGHT = "worker-structural-complexity-preflight.json"
WORKER_SOURCE_SNAPSHOT_CATEGORIES = {"public_source", "local_source_contract"}
WORKER_SOURCE_SNAPSHOT_IGNORE_DIRS = {
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
WORKER_SOURCE_SNAPSHOT_IGNORE_SUFFIXES = {".pyc", ".pyo"}


def _normalized_scope_rel_paths(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        rel_path = str(value).strip().replace("\\", "/")
        if not rel_path:
            continue
        path = Path(rel_path)
        if path.is_absolute() or ".." in path.parts:
            continue
        normalized.append(rel_path)
    return normalized


class ExecutorRuntimeError(Exception):
    exit_code = 8


class ExecutorRuntimeUsageError(ExecutorRuntimeError):
    exit_code = 2


class ExecutorRuntimeExecutionError(ExecutorRuntimeError):
    exit_code = 5


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--workspace-root", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--policy-path", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--scope-freeze", required=True)
    ap.add_argument("--proposal-snapshot", required=True)
    ap.add_argument("--repair-context", default="")
    ap.add_argument("--role", action="append", default=[])
    ap.add_argument("--routing-report", action="append", default=[])
    return ap.parse_args(argv)


def _role_order_key(role: str) -> tuple[int, str]:
    try:
        return (ROLE_ORDER.index(role), role)
    except ValueError:
        return (len(ROLE_ORDER), role)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scope_freeze_targets(
    artifact_root: Path,
    scope_freeze_rel: str,
    key: str,
) -> list[str]:
    payload = json.loads((artifact_root / scope_freeze_rel).read_text(encoding="utf-8"))
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        return []
    return _normalized_scope_rel_paths(inputs.get(key, []))


def _scope_freeze_resolution_paths(
    artifact_root: Path,
    scope_freeze_rel: str,
    key: str,
) -> list[str]:
    payload = json.loads((artifact_root / scope_freeze_rel).read_text(encoding="utf-8"))
    resolution = payload.get("resolution", {})
    if not isinstance(resolution, dict):
        return []
    return _normalized_scope_rel_paths(resolution.get(key, []))


def _primary_targets_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return _scope_freeze_targets(artifact_root, scope_freeze_rel, "primary_targets")


def _supporting_targets_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return _scope_freeze_targets(artifact_root, scope_freeze_rel, "supporting_targets")


def _test_files_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return _scope_freeze_resolution_paths(artifact_root, scope_freeze_rel, "test_files")


def _target_digest_snapshot(workspace_root: Path, targets: list[str]) -> dict[str, str | None]:
    snapshot: dict[str, str | None] = {}
    for rel_path in targets:
        path = workspace_root / rel_path
        snapshot[rel_path] = _file_digest(path) if path.is_file() else None
    return snapshot


def _is_worker_source_snapshot_path(rel_path: str) -> bool:
    return classify_path(rel_path) in WORKER_SOURCE_SNAPSHOT_CATEGORIES


def _is_worker_source_snapshot_file(path: Path, rel_path: str) -> bool:
    return (
        path.is_file()
        and path.suffix not in WORKER_SOURCE_SNAPSHOT_IGNORE_SUFFIXES
        and _is_worker_source_snapshot_path(rel_path)
    )


def _worker_source_digest_snapshot(workspace_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for rel_path in sorted([*PUBLIC_SOURCE_FILES, *LOCAL_SOURCE_CONTRACT_FILES]):
        path = workspace_root / rel_path
        if _is_worker_source_snapshot_file(path, rel_path):
            snapshot[rel_path] = _file_digest(path)

    for prefix in sorted(PUBLIC_SOURCE_PREFIXES):
        root_rel = prefix.rstrip("/")
        root = workspace_root / root_rel
        if not root.is_dir():
            continue
        for current_root, dir_names, file_names in os.walk(root):
            current = Path(current_root)
            rel_current = current.relative_to(workspace_root).as_posix()
            dir_names[:] = [
                name
                for name in dir_names
                if name not in WORKER_SOURCE_SNAPSHOT_IGNORE_DIRS
                and _is_worker_source_snapshot_path(f"{rel_current}/{name}")
            ]
            for file_name in sorted(file_names):
                path = current / file_name
                rel_path = path.relative_to(workspace_root).as_posix()
                if _is_worker_source_snapshot_file(path, rel_path):
                    snapshot[rel_path] = _file_digest(path)
    return snapshot


def _changed_targets(
    before: Mapping[str, str | None],
    after: Mapping[str, str | None],
) -> list[str]:
    return [
        target
        for target in sorted(set(before) | set(after))
        if before.get(target) != after.get(target)
    ]


def _should_refresh_script_output_surfaces(
    *,
    changed_primary_targets: list[str],
    supporting_targets: list[str],
) -> bool:
    return (
        SCRIPT_OUTPUT_SURFACES_TARGET in supporting_targets
        and any(target.startswith(OPS_SCRIPTS_PREFIX) for target in changed_primary_targets)
    )


def _refresh_script_output_surfaces(workspace_root: Path) -> None:
    if not (workspace_root / SCRIPT_OUTPUT_SURFACES_MODULE).is_file():
        return
    try:
        write_registry(
            workspace_root,
            build_registry(workspace_root),
            SCRIPT_OUTPUT_SURFACES_TARGET,
        )
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
        raise ExecutorRuntimeExecutionError(
            "failed to refresh ops/script-output-surfaces.json after worker changed "
            f"ops/scripts target: {type(exc).__name__}: {exc}"
        ) from exc


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _write_worker_repo_health_preflight_logs(
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
    (artifact_root / stdout_rel).write_text(_stream_text(stdout), encoding="utf-8")
    (artifact_root / stderr_rel).write_text(_stream_text(stderr), encoding="utf-8")
    return stdout_rel, stderr_rel


def _worker_repo_health_preflight_detail(
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> str:
    combined = "\n".join(
        text
        for text in (_stream_text(stderr).strip(), _stream_text(stdout).strip())
        if text
    )
    if not combined:
        return "no output"
    return combined[-1000:]


def _write_worker_structural_complexity_preflight_report(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    policy_path: str,
    changed_targets: list[str],
    context: RuntimeContext,
) -> tuple[str, dict]:
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


def _worker_structural_complexity_detail(report: dict) -> str:
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


def _run_worker_structural_complexity_preflight(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    policy_path: str,
    changed_targets: list[str],
    context: RuntimeContext,
) -> None:
    report_rel, report = _write_worker_structural_complexity_preflight_report(
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
            f"detail={_worker_structural_complexity_detail(report)}"
        )


def _run_worker_repo_health_preflight(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    test_files: list[str],
    workspace_mode: str,
    timeout_seconds: int,
    context: RuntimeContext,
) -> None:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = command_argv(
        default_check_command(test_files, workspace_mode=workspace_mode),
        cwd=workspace_root,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=workspace_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_rel, stderr_rel = _write_worker_repo_health_preflight_logs(
            artifact_root,
            run_id=run_id,
            stdout=exc.stdout,
            stderr=exc.stderr,
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
            f"execution; command={' '.join(command)}; stdout={stdout_rel}; stderr={stderr_rel}"
        ) from exc
    except OSError as exc:
        stdout_rel, stderr_rel = _write_worker_repo_health_preflight_logs(
            artifact_root,
            run_id=run_id,
            stdout="",
            stderr=str(exc),
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
            f"execution; command={' '.join(command)}; stdout={stdout_rel}; stderr={stderr_rel}"
        ) from exc
    stdout_rel, stderr_rel = _write_worker_repo_health_preflight_logs(
        artifact_root,
        run_id=run_id,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if completed.returncode != 0:
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
        detail = _worker_repo_health_preflight_detail(completed.stdout, completed.stderr)
        raise ExecutorRuntimeExecutionError(
            "worker repo-health preflight failed before reviewer/validator/auditor "
            f"execution; command={' '.join(command)}; stdout={stdout_rel}; "
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


def run_executor_pipeline(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    policy_path: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    repair_context_rel: str = "",
    roles: list[str],
    routing_reports: list[str],
) -> dict:
    policy, _ = load_policy(artifact_root, policy_path)
    context = RuntimeContext.from_policy(policy, executor_id="codex_exec")
    timeout_seconds = policy["auto_improve_policy"]["defaults"]["executor_timeout_seconds"]
    repo_health_timeout_seconds = policy["auto_improve_policy"]["defaults"][
        "wrapper_command_timeout_seconds"
    ]
    workspace_mode = workspace_preparation_mode_from_policy(policy)
    report_by_role = {}
    routing_map = {
        Path(path).name.replace("subagent-routing.", "").replace(".json", ""): path
        for path in routing_reports
    }
    ordered_roles = sorted(set(roles), key=_role_order_key)
    if not ordered_roles:
        raise ExecutorRuntimeUsageError("at least one --role is required")

    primary_targets = _primary_targets_from_scope_freeze(artifact_root, scope_freeze_rel)
    supporting_targets = _supporting_targets_from_scope_freeze(artifact_root, scope_freeze_rel)
    test_files = _test_files_from_scope_freeze(artifact_root, scope_freeze_rel)
    primary_before_worker = _target_digest_snapshot(workspace_root, primary_targets)
    has_post_worker_roles = any(role != "worker" for role in ordered_roles)
    tracks_worker_source_changes = (
        has_post_worker_roles or SCRIPT_OUTPUT_SURFACES_TARGET in supporting_targets
    )
    source_before_worker = (
        _worker_source_digest_snapshot(workspace_root)
        if tracks_worker_source_changes
        else {}
    )
    for role in ordered_roles:
        routing_report_rel = routing_map.get(role)
        if routing_report_rel is None:
            raise ExecutorRuntimeUsageError(f"missing routing report for role: {role}")
        report = execute_codex_exec_role(
            artifact_root=artifact_root,
            workspace_root=workspace_root,
            run_id=run_id,
            role=role,
            routing_report_rel=routing_report_rel,
            scope_freeze_rel=scope_freeze_rel,
            proposal_snapshot_rel=proposal_snapshot_rel,
            repair_context_rel=repair_context_rel,
            context=context,
            timeout_seconds=timeout_seconds,
        )
        report_by_role[role] = report
        if report["status"] != "pass":
            raise ExecutorRuntimeExecutionError(f"{role} reported a blocking status")
        if role == "worker" and primary_targets:
            primary_after_worker = _target_digest_snapshot(workspace_root, primary_targets)
            changed_primary_targets = _changed_targets(primary_before_worker, primary_after_worker)
            if not changed_primary_targets:
                raise ExecutorRuntimeExecutionError(
                    executor_noop_mutation_failure_message("worker", primary_targets)
                )
            changed_worker_source_targets = (
                _changed_targets(
                    source_before_worker,
                    _worker_source_digest_snapshot(workspace_root),
                )
                if tracks_worker_source_changes
                else []
            )
            if _should_refresh_script_output_surfaces(
                changed_primary_targets=changed_primary_targets,
                supporting_targets=supporting_targets,
            ):
                if SCRIPT_OUTPUT_SURFACES_MODULE in changed_worker_source_targets:
                    raise ExecutorRuntimeExecutionError(
                        "worker changed ops/scripts/core/script_output_surfaces.py; "
                        "refusing to refresh ops/script-output-surfaces.json with the "
                        "parent's already-imported generator"
                    )
                _refresh_script_output_surfaces(workspace_root)
            if has_post_worker_roles:
                _run_worker_structural_complexity_preflight(
                    artifact_root,
                    workspace_root=workspace_root,
                    run_id=run_id,
                    policy_path=policy_path,
                    changed_targets=changed_worker_source_targets,
                    context=context,
                )
                _run_worker_repo_health_preflight(
                    artifact_root,
                    workspace_root=workspace_root,
                    run_id=run_id,
                    test_files=test_files,
                    workspace_mode=workspace_mode,
                    timeout_seconds=repo_health_timeout_seconds,
                    context=context,
                )

    return {
        "run_id": run_id,
        "roles": ordered_roles,
        "reports": {
            role: f"runs/{run_id}/{role}-executor-report.json"
            for role in ordered_roles
        },
    }


def main(argv: list[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        result = run_executor_pipeline(
            Path(args.vault).resolve(),
            workspace_root=Path(args.workspace_root).resolve(),
            run_id=args.run_id,
            policy_path=args.policy_path,
            scope_freeze_rel=args.scope_freeze,
            proposal_snapshot_rel=args.proposal_snapshot,
            repair_context_rel=args.repair_context,
            roles=args.role,
            routing_reports=args.routing_report,
        )
    except ExecutorRuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    except CodexExecError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(5) from exc
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))
