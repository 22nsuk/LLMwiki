from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .codex_exec_executor import CodexExecError, execute_codex_exec_role
from .policy_runtime import load_policy
from .runtime_context import RuntimeContext


ROLE_ORDER = ("worker", "reviewer", "validator")


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
        raise SystemExit(exc.exit_code)
    except CodexExecError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(5)
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8)

    print(json.dumps(result, ensure_ascii=False, indent=2))
