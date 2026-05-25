from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .codex_exec_executor import CodexExecError, execute_codex_exec_role
from .policy_runtime import load_policy
from .runtime_context import RuntimeContext

ROLE_ORDER = ("worker", "reviewer", "validator")
SCRIPT_OUTPUT_SURFACES_TARGET = "ops/script-output-surfaces.json"
OPS_SCRIPTS_PREFIX = "ops/scripts/"


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
    targets = inputs.get(key, [])
    if not isinstance(targets, list):
        return []
    normalized: list[str] = []
    for value in targets:
        rel_path = str(value).strip().replace("\\", "/")
        if not rel_path:
            continue
        path = Path(rel_path)
        if path.is_absolute() or ".." in path.parts:
            continue
        normalized.append(rel_path)
    return normalized


def _primary_targets_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return _scope_freeze_targets(artifact_root, scope_freeze_rel, "primary_targets")


def _supporting_targets_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return _scope_freeze_targets(artifact_root, scope_freeze_rel, "supporting_targets")


def _target_digest_snapshot(workspace_root: Path, targets: list[str]) -> dict[str, str | None]:
    snapshot: dict[str, str | None] = {}
    for rel_path in targets:
        path = workspace_root / rel_path
        snapshot[rel_path] = _file_digest(path) if path.is_file() else None
    return snapshot


def _changed_targets(
    before: dict[str, str | None],
    after: dict[str, str | None],
) -> list[str]:
    return [target for target in sorted(before) if before.get(target) != after.get(target)]


def _should_refresh_script_output_surfaces(
    *,
    changed_primary_targets: list[str],
    supporting_targets: list[str],
) -> bool:
    if SCRIPT_OUTPUT_SURFACES_TARGET not in supporting_targets:
        return False
    return any(target.startswith(OPS_SCRIPTS_PREFIX) for target in changed_primary_targets)


def _refresh_script_output_surfaces(workspace_root: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ops.scripts.script_output_surfaces",
            "--vault",
            ".",
            "--out",
            SCRIPT_OUTPUT_SURFACES_TARGET,
        ],
        cwd=workspace_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ExecutorRuntimeExecutionError(
            "failed to refresh ops/script-output-surfaces.json after worker changed "
            f"ops/scripts target: {detail}"
        )


def run_executor_pipeline(
    artifact_root: Path,
    *,
    workspace_root: Path,
    run_id: str,
    policy_path: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    roles: list[str],
    routing_reports: list[str],
) -> dict:
    policy, _ = load_policy(artifact_root, policy_path)
    context = RuntimeContext.from_policy(policy, executor_id="codex_exec")
    timeout_seconds = policy["auto_improve_policy"]["defaults"]["executor_timeout_seconds"]
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
    primary_before_worker = _target_digest_snapshot(workspace_root, primary_targets)
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
                joined_targets = ", ".join(primary_targets)
                raise ExecutorRuntimeExecutionError(
                    "worker reported pass without modifying any declared primary target; "
                    f"primary_targets=[{joined_targets}]"
                )
            if _should_refresh_script_output_surfaces(
                changed_primary_targets=changed_primary_targets,
                supporting_targets=supporting_targets,
            ):
                _refresh_script_output_surfaces(workspace_root)

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
