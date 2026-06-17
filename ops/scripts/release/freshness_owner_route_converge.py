#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)

DEFAULT_REPORT = "ops/reports/artifact-freshness-report.json"
DEFAULT_PLAN_OUT = "tmp/freshness-owner-route-converge-plan.json"
GENERIC_SOURCE_IDENTITY_TARGET = "freshness-source-identity-converge"
GOAL_RUN_PLACEHOLDER_PREFIX = "GOAL_RUN_ID=<completed-run-id> make "
MAKE_TARGET_RE = re.compile(r"^[A-Za-z0-9_.%/-]+$")
GOAL_RUNTIME_ROUTE_ID = "ops_reports_goal_runtime"

DEFERRED_FINALITY_TARGETS = {
    "release-finality-resettle",
    "release-finality-resettle-current-or-refresh",
    "release-terminal-finality",
}
TERMINAL_SUFFIX_TARGETS = (
    "artifact-freshness-refresh-check",
    "generated-artifact-index",
    "artifact-freshness-refresh-check",
    "release-finality-resettle-current-or-refresh",
)
ALLOWED_ROUTE_TARGETS: dict[str, frozenset[str]] = {
    "external_reports_reference_manifest": frozenset(
        {
            "external-report-reference-manifest-settle",
            "external-report-lifecycle-refresh",
        }
    ),
    "ops_reports_test_execution_summary_full_current_or_refresh": frozenset(
        {"test-execution-summary-full-current-or-refresh"}
    ),
    "ops_reports_public_check_summary_current_or_refresh": frozenset(
        {"public-check-summary-current-or-refresh"}
    ),
    "ops_reports_test_execution_summary_current_or_refresh": frozenset(
        {"test-execution-summary-current-or-refresh"}
    ),
    "ops_reports_public_check_summary": frozenset(
        {"public-check-summary-current-or-refresh"}
    ),
    "ops_reports_learning_readiness_signoff": frozenset(
        {
            "learning-readiness-signoff-refresh",
            "learning-readiness-signoff-revalidation",
        }
    ),
    "ops_reports_learning_evidence": frozenset(
        {
            "learning-claim-activation-report",
            "learning-readiness-signoff-revalidation",
        }
    ),
    GOAL_RUNTIME_ROUTE_ID: frozenset(
        {
            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-status-finalize",
            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-publish-local-evidence",
            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate",
        }
    ),
    "ops_reports_supply_chain": frozenset({"supply-chain-artifacts-cached"}),
    "ops_reports_release_smoke_fast_refresh_check": frozenset(
        {"release-smoke-fast-refresh-check"}
    ),
    "ops_reports_release_smoke_full_reuse": frozenset({"release-smoke-full-reuse"}),
    "ops_reports_release_source_package": frozenset({"release-source-package-check"}),
    "ops_reports_maintainability": frozenset(
        {
            "function-budget-refactor-proposals",
            "lint-uplift-plan",
            "type-uplift-plan",
            "complexity-budget",
        }
    ),
    "ops_reports_mechanism_review": frozenset({"mechanism-review"}),
    "ops_reports_mutation_proposal": frozenset({"mutation-proposal"}),
    "ops_reports_outcome_metrics": frozenset({"outcome-metrics"}),
    "ops_reports_outcome_provenance_gate_policy": frozenset(
        {"outcome-provenance-gate-policy"}
    ),
    "ops_reports_promotion_decision_trends": frozenset({"promotion-decision-trends"}),
    "ops_reports_registry_preflight": frozenset({"registry-preflight"}),
    "ops_reports_github_governance": frozenset({"github-governance-live-drift"}),
    "ops_reports_bootstrap_preflight": frozenset({"bootstrap-preflight"}),
}


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_report_or_none(path: Path) -> dict[str, Any] | None:
    try:
        payload = _load_json(path)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _currentness_status(report: dict[str, Any]) -> str:
    currentness = report.get("currentness")
    if not isinstance(currentness, dict):
        return ""
    return str(currentness.get("status", "")).strip()


def _report_is_current(report: dict[str, Any]) -> bool:
    return _currentness_status(report) == "current"


def _report_matches_current_source_tree(vault: Path, report: dict[str, Any]) -> bool:
    source_tree_fingerprint = str(report.get("source_tree_fingerprint", "")).strip()
    return bool(
        source_tree_fingerprint
        and source_tree_fingerprint == release_source_tree_fingerprint(vault)
    )


def _is_make_target(value: str) -> bool:
    return bool(MAKE_TARGET_RE.fullmatch(value))


def _target_plan_item(
    raw_target: str,
    *,
    route: dict[str, Any],
    env: Mapping[str, str],
) -> dict[str, Any]:
    target = raw_target.strip()
    route_id = str(route.get("route_id", "")).strip()
    if not target:
        return {
            "raw_target": raw_target,
            "route_id": route_id,
            "status": "skipped",
            "reason": "empty_target",
        }
    if target == GENERIC_SOURCE_IDENTITY_TARGET:
        return {
            "raw_target": target,
            "route_id": route_id,
            "status": "skipped",
            "reason": "generic_source_identity_recursion",
        }
    if target in DEFERRED_FINALITY_TARGETS:
        return {
            "raw_target": target,
            "route_id": route_id,
            "status": "skipped",
            "reason": "deferred_to_terminal_suffix",
        }
    if target.startswith(GOAL_RUN_PLACEHOLDER_PREFIX):
        goal_run_id = str(env.get("GOAL_RUN_ID", "")).strip()
        resolved_target = target.removeprefix(GOAL_RUN_PLACEHOLDER_PREFIX).strip()
        if (
            route_id != GOAL_RUNTIME_ROUTE_ID
            or target not in ALLOWED_ROUTE_TARGETS[GOAL_RUNTIME_ROUTE_ID]
        ):
            return {
                "raw_target": target,
                "route_id": route_id,
                "status": "blocked",
                "reason": "owner_route_target_not_allowed",
            }
        if not goal_run_id:
            return {
                "raw_target": target,
                "route_id": route_id,
                "status": "blocked",
                "reason": "goal_run_id_required",
                "required_environment": "GOAL_RUN_ID",
            }
        if not _is_make_target(resolved_target):
            return {
                "raw_target": target,
                "route_id": route_id,
                "status": "blocked",
                "reason": "unsupported_goal_runtime_target",
            }
        return {
            "raw_target": target,
            "route_id": route_id,
            "status": "selected",
            "target": resolved_target,
            "reason": "goal_run_id_bound",
        }
    allowed_targets = ALLOWED_ROUTE_TARGETS.get(route_id)
    if allowed_targets is None:
        return {
            "raw_target": target,
            "route_id": route_id,
            "status": "blocked",
            "reason": "unsupported_owner_route",
        }
    if target not in allowed_targets:
        return {
            "raw_target": target,
            "route_id": route_id,
            "status": "blocked",
            "reason": "owner_route_target_not_allowed",
        }
    if not _is_make_target(target):
        return {
            "raw_target": target,
            "route_id": route_id,
            "status": "blocked",
            "reason": "unsupported_make_target_shape",
        }
    return {
        "raw_target": target,
        "route_id": route_id,
        "status": "selected",
        "target": target,
        "reason": "owner_route_target",
    }


def _route_items(stale_routing: dict[str, Any], env: Mapping[str, str]) -> list[dict[str, Any]]:
    owner_routes = stale_routing.get("source_identity_owner_routes")
    if not isinstance(owner_routes, list):
        return []
    items: list[dict[str, Any]] = []
    for route in owner_routes:
        if not isinstance(route, dict):
            continue
        raw_targets = route.get("recommended_targets")
        if not isinstance(raw_targets, list):
            continue
        for raw_target in raw_targets:
            if isinstance(raw_target, str):
                items.append(_target_plan_item(raw_target, route=route, env=env))
    return items


def build_plan(report: dict[str, Any], *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    active_env = env if env is not None else os.environ
    stale_routing = report.get("stale_routing")
    if not isinstance(stale_routing, dict):
        stale_routing = {}
    classification = str(stale_routing.get("classification", "")).strip()
    route_items = _route_items(stale_routing, active_env)
    selected_targets = _dedupe_preserve_order(
        [
            str(item["target"])
            for item in route_items
            if item.get("status") == "selected" and str(item.get("target", "")).strip()
        ]
    )
    blocked_targets = [item for item in route_items if item.get("status") == "blocked"]
    skipped_targets = [item for item in route_items if item.get("status") == "skipped"]
    if classification == "clean":
        status = "clean"
    elif classification != "source_identity_only":
        status = "not_source_identity_only"
    elif blocked_targets:
        status = "blocked"
    elif selected_targets:
        status = "owner_targets_available"
    else:
        status = "generic_suffix_only"
    return {
        "artifact_kind": "freshness_owner_route_converge_plan",
        "status": status,
        "classification": classification or "unknown",
        "source_report_status": str(report.get("status", "")).strip() or "unknown",
        "source_report_currentness_status": _currentness_status(report) or "unknown",
        "selected_targets": selected_targets,
        "selected_target_count": len(selected_targets),
        "blocked_targets": blocked_targets,
        "blocked_target_count": len(blocked_targets),
        "skipped_targets": skipped_targets,
        "skipped_target_count": len(skipped_targets),
        "terminal_suffix_targets": list(TERMINAL_SUFFIX_TARGETS),
        "summary": _plan_summary(
            status=status,
            selected_count=len(selected_targets),
            blocked_count=len(blocked_targets),
            skipped_count=len(skipped_targets),
        ),
    }


def _plan_summary(
    *,
    status: str,
    selected_count: int,
    blocked_count: int,
    skipped_count: int,
) -> str:
    return (
        f"status={status}; selected_targets={selected_count}; "
        f"blocked_targets={blocked_count}; skipped_targets={skipped_count}"
    )


def _write_plan(vault: Path, plan: dict[str, Any], out: str | Path) -> Path:
    path = Path(out)
    if not path.is_absolute():
        path = vault / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _make_command(
    target: str,
    *,
    make_bin: str,
    python: str,
    vault: Path,
    goal_run_id: str,
) -> list[str]:
    command = [
        make_bin,
        target,
        f"PYTHON={python}",
        f"VAULT={vault.as_posix()}",
        "ALLOW_FINALITY_INVALIDATION=1",
    ]
    if goal_run_id:
        command.append(f"GOAL_RUN_ID={goal_run_id}")
    return command


def _display_command(vault: Path, command: Sequence[str]) -> list[str]:
    vault_root = vault.resolve()
    result: list[str] = []
    for item in command:
        if "=" in item:
            key, value = item.split("=", 1)
            value_path = Path(value)
            if (
                value_path.is_absolute()
                and value_path.resolve().is_relative_to(vault_root)
            ):
                result.append(f"{key}={display_path(vault, value_path)}")
                continue
        item_path = Path(item)
        if item_path.is_absolute() and item_path.resolve().is_relative_to(vault_root):
            result.append(display_path(vault, item_path))
        else:
            result.append(item)
    return result


def _run_make_target(
    target: str,
    *,
    make_bin: str,
    python: str,
    vault: Path,
    goal_run_id: str,
) -> dict[str, Any]:
    command = _make_command(
        target,
        make_bin=make_bin,
        python=python,
        vault=vault,
        goal_run_id=goal_run_id,
    )
    print(f"freshness-owner-route-converge: run target={target}", flush=True)
    completed = subprocess.run(command, cwd=vault, check=False)
    return {
        "target": target,
        "command": _display_command(vault, command),
        "returncode": completed.returncode,
        "status": "pass" if completed.returncode == 0 else "fail",
    }


def _append_command_result(plan: dict[str, Any], phase: str, result: dict[str, Any]) -> None:
    results = plan.setdefault("command_results", [])
    if isinstance(results, list):
        results.append({"phase": phase, **result})


def _refresh_report_if_needed(
    *,
    vault: Path,
    report_path: str,
    plan_out: str,
    make_bin: str,
    python: str,
    goal_run_id: str,
    dry_run: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int | None]:
    report = _load_report_or_none(vault / report_path)
    if dry_run:
        return report, None, None
    if (
        report is not None
        and _report_is_current(report)
        and _report_matches_current_source_tree(vault, report)
    ):
        return (
            report,
            {
                "target": "artifact-freshness-refresh-check",
                "status": "skipped",
                "reason": "existing_report_current",
            },
            None,
        )
    result = _run_make_target(
        "artifact-freshness-refresh-check",
        make_bin=make_bin,
        python=python,
        vault=vault,
        goal_run_id=goal_run_id,
    )
    if result["status"] != "pass":
        plan: dict[str, Any] = {
            "artifact_kind": "freshness_owner_route_converge_plan",
            "status": "initial_refresh_failed",
            "command_results": [{"phase": "initial_refresh", **result}],
        }
        _write_plan(vault, plan, plan_out)
        return report, result, int(result["returncode"]) or 1
    return _load_json(vault / report_path), result, None


def run_converge(
    *,
    vault: Path,
    report_path: str,
    plan_out: str,
    make_bin: str,
    python: str,
    env: Mapping[str, str],
    dry_run: bool,
) -> int:
    goal_run_id = str(env.get("GOAL_RUN_ID", "")).strip()
    report, initial_refresh_result, exit_code = _refresh_report_if_needed(
        vault=vault,
        report_path=report_path,
        plan_out=plan_out,
        make_bin=make_bin,
        python=python,
        goal_run_id=goal_run_id,
        dry_run=dry_run,
    )
    if exit_code is not None:
        return exit_code
    if report is None:
        report = _load_json(vault / report_path)

    plan = build_plan(report, env=env)
    if initial_refresh_result is not None:
        plan["initial_refresh"] = initial_refresh_result
    _write_plan(vault, plan, plan_out)
    if dry_run:
        print(display_path(vault, vault / plan_out))
        return 0
    if not _report_is_current(report) or not _report_matches_current_source_tree(
        vault, report
    ):
        plan["status"] = "source_report_not_current"
        plan["summary"] = (
            "status=source_report_not_current; "
            f"source_report_currentness_status={plan['source_report_currentness_status']}"
        )
        _write_plan(vault, plan, plan_out)
        print(
            "freshness-owner-route-converge: artifact freshness report is not current "
            "after initial refresh",
            file=sys.stderr,
        )
        return 2
    if plan["status"] == "clean":
        print("freshness-owner-route-converge: artifact freshness is already clean")
        return 0
    if plan["status"] == "not_source_identity_only":
        print(
            "freshness-owner-route-converge: artifact freshness is not source-identity-only; "
            "use the report's recommended lane",
            file=sys.stderr,
        )
        return 2
    if plan["status"] == "blocked":
        print(
            "freshness-owner-route-converge: owner route requires operator input; "
            f"see {display_path(vault, vault / plan_out)}",
            file=sys.stderr,
        )
        return 2

    for target in plan["selected_targets"]:
        result = _run_make_target(
            str(target),
            make_bin=make_bin,
            python=python,
            vault=vault,
            goal_run_id=goal_run_id,
        )
        _append_command_result(plan, "owner_route", result)
        _write_plan(vault, plan, plan_out)
        if result["status"] != "pass":
            plan["status"] = "owner_route_failed"
            _write_plan(vault, plan, plan_out)
            return int(result["returncode"]) or 1

    for target in TERMINAL_SUFFIX_TARGETS:
        result = _run_make_target(
            target,
            make_bin=make_bin,
            python=python,
            vault=vault,
            goal_run_id=goal_run_id,
        )
        _append_command_result(plan, "terminal_suffix", result)
        _write_plan(vault, plan, plan_out)
        if result["status"] != "pass":
            plan["status"] = "terminal_suffix_failed"
            _write_plan(vault, plan, plan_out)
            return int(result["returncode"]) or 1

    plan["status"] = "pass"
    plan["summary"] = _plan_summary(
        status="pass",
        selected_count=int(plan["selected_target_count"]),
        blocked_count=int(plan["blocked_target_count"]),
        skipped_count=int(plan["skipped_target_count"]),
    )
    _write_plan(vault, plan, plan_out)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Converge source-identity artifact freshness through owner routes before terminal finality."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--plan-out", default=DEFAULT_PLAN_OUT)
    parser.add_argument("--make", default="make")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    return run_converge(
        vault=vault,
        report_path=str(args.report),
        plan_out=str(args.plan_out),
        make_bin=str(args.make),
        python=str(args.python),
        env=os.environ,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
