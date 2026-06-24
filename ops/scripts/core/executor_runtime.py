from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .codex_exec_executor import CodexExecError, execute_codex_exec_role
from .executor_noop_runtime import executor_noop_mutation_failure_message
from .executor_runtime_errors_runtime import (
    ExecutorRuntimeError,
    ExecutorRuntimeExecutionError,
    ExecutorRuntimeUsageError,
)
from .executor_runtime_scope_freeze_runtime import (
    SCRIPT_OUTPUT_SURFACES_MODULE,
    SCRIPT_OUTPUT_SURFACES_TARGET,
    changed_targets as _changed_targets,
    primary_targets_from_scope_freeze as _primary_targets_from_scope_freeze,
    should_refresh_script_output_surfaces as _should_refresh_script_output_surfaces,
    supporting_targets_from_scope_freeze as _supporting_targets_from_scope_freeze,
    target_digest_snapshot as _target_digest_snapshot,
    test_files_from_scope_freeze as _test_files_from_scope_freeze,
    worker_source_digest_snapshot as _worker_source_digest_snapshot,
)
from .executor_runtime_worker_preflight_runtime import (
    run_worker_repo_health_preflight as _run_worker_repo_health_preflight,
    run_worker_structural_complexity_preflight as _run_worker_structural_complexity_preflight,
)
from .policy_runtime import load_policy, workspace_preparation_mode_from_policy
from .runtime_context import RuntimeContext
from .script_output_surfaces import build_registry, write_registry

ROLE_ORDER = ("worker", "reviewer", "validator")


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
) -> dict[str, Any]:
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
