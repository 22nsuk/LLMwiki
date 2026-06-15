#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.makefile_runtime import load_makefile_text
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.release_closeout_fixed_point import (
        POLICY_PATH as FIXED_POINT_POLICY_PATH,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.workflow_dependency_planner import (
        MAKE_RECIPE_RE,
        TARGET_RE,
        _first_make_target,
        build_report as build_workflow_dependency_report,
    )
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.makefile_runtime import load_makefile_text
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.workflow_dependency_planner import (
        MAKE_RECIPE_RE,
        TARGET_RE,
        _first_make_target,
        build_report as build_workflow_dependency_report,
    )

    from .release_closeout_fixed_point import POLICY_PATH as FIXED_POINT_POLICY_PATH


DEFAULT_OUT = "ops/reports/release-workflow-order-guard.json"
PRODUCER = "ops.scripts.release_workflow_order_guard"
SCHEMA_PATH = "ops/schemas/release-workflow-order-guard.schema.json"
SOURCE_COMMAND = (
    "python -m ops.scripts.release_workflow_order_guard "
    "--vault . --out ops/reports/release-workflow-order-guard.json"
)
RELEASE_CONVERGE_TARGET = "release-evidence-converge"
RELEASE_CONVERGE_PREFLIGHT_TARGET = "release-converge-preflight"
CHECK_FINALIZED_TARGET = "check-finalized"
RELEASE_FINALITY_RESETTLE_TARGET = "release-finality-resettle"
RELEASE_SOURCE_READY_TARGET = "release-source-ready"
RELEASE_SOURCE_READY_PREPARE_TARGET = "release-source-ready-prepare"
RELEASE_POST_COMMIT_FINALIZE_TARGET = "release-post-commit-finalize"
RELEASE_SOURCE_READY_POST_VERIFY_TARGET = "release-source-ready-post-verify"
STRICT_FINALIZER_FLAG = "RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required"
ALLOWED_REPEATED_CONVERGE_TARGETS = {
    "auto-improve-readiness-report-body",
    "generated-artifact-converge",
    "release-closeout-fixed-point",
    "release-closeout-summary-report",
    "tmp-json-clean",
}
FORBIDDEN_POST_COMMIT_FINALIZER_TARGETS = {
    "release-auto-promotion-ready-invalidate",
    "release-authority-settle",
    "release-authority-sealed-preflight",
    "release-evidence-converge",
    "release-evidence-dashboard-report",
    "release-clean-blocker-ledger",
    "generated-artifact-converge",
    "generated-artifact-script-output",
    "release-finality-resettle",
    "test-execution-summary-full-current-or-refresh",
    "test-execution-summary-full-refresh",
    "test-execution-summary-current-or-refresh",
}
TARGET_RECIPE_ORDER = (
    RELEASE_CONVERGE_TARGET,
    RELEASE_CONVERGE_PREFLIGHT_TARGET,
    CHECK_FINALIZED_TARGET,
    RELEASE_FINALITY_RESETTLE_TARGET,
    RELEASE_SOURCE_READY_TARGET,
    RELEASE_SOURCE_READY_PREPARE_TARGET,
    RELEASE_SOURCE_READY_POST_VERIFY_TARGET,
    RELEASE_POST_COMMIT_FINALIZE_TARGET,
)


@dataclass(frozen=True)
class _WorkflowOrderInputs:
    resolved_vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    generated_at: str
    makefile_sources: list[str]
    fixed_point_policy: dict[str, Any]
    writers: list[dict[str, Any]]
    planner_report: dict[str, Any]
    invocations_by_target: dict[str, list[dict[str, Any]]]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _target_dependencies(makefile_text: str) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    for raw_line in makefile_text.splitlines():
        if raw_line.startswith("\t"):
            continue
        target_match = TARGET_RE.match(raw_line.rstrip())
        if target_match is None:
            continue
        targets = [item.strip() for item in target_match.group(1).split() if item.strip()]
        deps = [
            token.strip()
            for token in target_match.group("deps").split()
            if token.strip() and not token.strip().startswith("$")
        ]
        for target in targets:
            dependencies.setdefault(target, [])
            for dep in deps:
                if dep not in dependencies[target]:
                    dependencies[target].append(dep)
    return dependencies


def _direct_recipe_invocations(makefile_text: str, target: str) -> list[dict[str, Any]]:
    active = False
    invocations: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(makefile_text.splitlines(), start=1):
        if raw_line.startswith("\t"):
            if not active:
                continue
            for match in MAKE_RECIPE_RE.finditer(raw_line):
                raw_args = match.group("args").strip()
                make_target = _first_make_target(raw_args.split())
                if make_target is None:
                    continue
                invocations.append(
                    {
                        "order": len(invocations) + 1,
                        "line": line_no,
                        "target": make_target,
                        "role": _invocation_role(make_target, raw_args),
                        "raw_args": raw_args,
                    }
                )
            continue

        target_match = TARGET_RE.match(raw_line.rstrip())
        if target_match is None:
            active = False
            continue
        active = target in {item.strip() for item in target_match.group(1).split() if item.strip()}
    return invocations


def _recipe_invocations(makefile_text: str, target: str) -> list[dict[str, Any]]:
    dependencies = _target_dependencies(makefile_text)
    visited: set[str] = set()
    invocations: list[dict[str, Any]] = []

    def visit(active_target: str) -> None:
        if active_target in visited:
            return
        visited.add(active_target)
        for dependency in dependencies.get(active_target, []):
            visit(dependency)
        for invocation in _direct_recipe_invocations(makefile_text, active_target):
            invocations.append({**invocation, "order": len(invocations) + 1})

    visit(target)
    return invocations


def _invocation_role(target: str, raw_args: str) -> str:
    if target == "release-closeout-post-check-finalizer-dry-run":
        if STRICT_FINALIZER_FLAG in raw_args:
            return "release-closeout-post-check-finalizer-strict-dry-run"
        return "release-closeout-post-check-finalizer-dry-run"
    return target


def _first_index(invocations: list[dict[str, Any]], role: str, *, after: int = 0) -> int:
    for index, invocation in enumerate(invocations, start=1):
        if index <= after:
            continue
        if role.startswith("release-closeout-post-check-finalizer-"):
            if invocation["role"] == role:
                return index
            continue
        if invocation["role"] == role or invocation["target"] == role:
            return index
    return 0


def _subsequence_positions(invocations: list[dict[str, Any]], expected_roles: list[str]) -> list[int]:
    positions: list[int] = []
    cursor = 0
    for role in expected_roles:
        index = _first_index(invocations, role, after=cursor)
        positions.append(index)
        if index:
            cursor = index
    return positions


def _check(
    check_id: str,
    *,
    expected_order: list[str],
    observed_order: list[str],
    violations: list[dict[str, Any]] | None = None,
    details: str = "",
    attention: bool = False,
) -> dict[str, Any]:
    active_violations = list(violations or [])
    status = "fail" if active_violations else "attention" if attention else "pass"
    return {
        "id": check_id,
        "status": status,
        "expected_order": expected_order,
        "observed_order": observed_order,
        "violations": active_violations,
        "details": details,
    }


def _check_subsequence(
    check_id: str,
    invocations: list[dict[str, Any]],
    expected_roles: list[str],
    *,
    details: str,
) -> dict[str, Any]:
    positions = _subsequence_positions(invocations, expected_roles)
    violations = [
        {
            "expected_role": role,
            "reason": "missing_or_out_of_order",
        }
        for role, position in zip(expected_roles, positions, strict=False)
        if position == 0
    ]
    return _check(
        check_id,
        expected_order=expected_roles,
        observed_order=[str(item["role"]) for item in invocations],
        violations=violations,
        details=details,
    )


def _fixed_point_writer_specs(policy: dict[str, Any]) -> list[dict[str, Any]]:
    writers = policy.get("writers")
    if not isinstance(writers, list):
        return []
    result: list[dict[str, Any]] = []
    for item in writers:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target", "")).strip()
        if not target:
            continue
        result.append(
            {
                "name": str(item.get("name", target)).strip() or target,
                "target": target,
                "depends_on": [
                    str(dep).strip()
                    for dep in item.get("depends_on", [])
                    if str(dep).strip()
                ],
                "expensive_prerequisites_once": [
                    str(dep).strip()
                    for dep in item.get("expensive_prerequisites_once", [])
                    if str(dep).strip()
                ],
                "produces": [
                    str(path).strip()
                    for path in item.get("produces", [])
                    if str(path).strip()
                ],
            }
        )
    return result


def _fixed_point_initial_order(writers: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for writer in writers:
        for target in writer["expensive_prerequisites_once"]:
            if target not in seen:
                seen.add(target)
                ordered.append(target)
    for writer in writers:
        target = str(writer["target"])
        if target not in seen:
            seen.add(target)
            ordered.append(target)
    return ordered


def _check_fixed_point_policy_order(writers: list[dict[str, Any]]) -> dict[str, Any]:
    order = {str(writer["target"]): index for index, writer in enumerate(writers, start=1)}
    violations = []
    for writer in writers:
        target = str(writer["target"])
        for dependency in writer["depends_on"]:
            if dependency not in order:
                violations.append(
                    {
                        "target": target,
                        "dependency": dependency,
                        "reason": "unknown_dependency",
                    }
                )
            elif order[dependency] >= order[target]:
                violations.append(
                    {
                        "target": target,
                        "dependency": dependency,
                        "reason": "dependency_not_before_target",
                    }
                )
    return _check(
        "fixed_point_policy_topological_order",
        expected_order=[str(writer["target"]) for writer in writers],
        observed_order=[str(writer["target"]) for writer in writers],
        violations=violations,
        details="Fixed-point writer policy must list dependencies before their consumers.",
    )


def _check_planner_hooks(planner_report: dict[str, Any], closeout_invocations: list[dict[str, Any]]) -> dict[str, Any]:
    workflows = {
        str(item.get("workflow_id", "")): item
        for item in planner_report.get("selected_workflows", [])
        if isinstance(item, dict)
    }
    planner_workflow = workflows.get("workflow_dependency_planner_closeout", {})
    planner_steps = [
        str(step.get("target", "")).strip()
        for step in planner_workflow.get("steps", [])
        if isinstance(step, dict) and str(step.get("target", "")).strip()
    ]
    required_steps = [
        "workflow-dependency-planner",
        "release-closeout-finality-verify",
    ]
    violations = [
        {
            "target": target,
            "reason": "missing_from_workflow_dependency_planner_closeout_steps",
        }
        for target in required_steps
        if target not in planner_steps
    ]
    return _check(
        "workflow_dependency_planner_closeout_hooks",
        expected_order=required_steps,
        observed_order=planner_steps,
        violations=violations,
        details="The planner closeout recommendation must keep finality hooks visible in the source-derived workflow graph.",
    )


def _check_planner_fixed_point_writer_order(
    planner_report: dict[str, Any], writers: list[dict[str, Any]]
) -> dict[str, Any]:
    workflows = {
        str(item.get("workflow_id", "")): item
        for item in planner_report.get("selected_workflows", [])
        if isinstance(item, dict)
    }
    planner_workflow = workflows.get("workflow_dependency_planner_closeout", {})
    planner_steps = [
        str(step.get("target", "")).strip()
        for step in planner_workflow.get("steps", [])
        if isinstance(step, dict) and str(step.get("target", "")).strip()
    ]
    if "generated-artifact-converge" in planner_steps:
        expected = ["generated-artifact-converge"]
    elif "generated-artifact-finality-suffix" in planner_steps:
        expected = ["generated-artifact-finality-suffix"]
    else:
        expected = _fixed_point_initial_order(writers)
    positions = _subsequence_positions(
        [{"role": step, "target": step} for step in planner_steps],
        expected,
    )
    violations = [
        {
            "expected_role": role,
            "reason": "missing_or_out_of_order",
        }
        for role, position in zip(expected, positions, strict=False)
        if position == 0
    ]
    return _check(
        "workflow_dependency_planner_fixed_point_policy_order",
        expected_order=expected,
        observed_order=planner_steps,
        violations=violations,
        details="The planner closeout recommendation must derive fixed-point writer order from ops/policies/release-closeout-fixed-point.json.",
    )


def _release_converge_finalizer_check(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    finality_index = _first_index(invocations, "release-closeout-finality-verify")
    fixed_point_index = _first_index(invocations, "release-closeout-fixed-point")
    tmp_after_fixed_point = _first_index(invocations, "tmp-json-clean", after=fixed_point_index)
    expected = [
        "release-closeout-post-check-finalizer-dry-run",
        "release-closeout-fixed-point",
        "tmp-json-clean",
        "release-closeout-finality-verify",
    ]
    positions = [
        _first_index(invocations, "release-closeout-post-check-finalizer-dry-run"),
        fixed_point_index,
        tmp_after_fixed_point,
        finality_index,
    ]
    violations = [
        {"expected_role": role, "reason": "missing_or_out_of_order"}
        for role, position in zip(expected, positions, strict=False)
        if position == 0
    ]
    if finality_index and finality_index != len(invocations):
        violations.append(
            {
                "expected_role": "release-closeout-finality-verify",
                "reason": "finality_verify_must_be_terminal",
            }
        )
    return _check(
        "release_evidence_converge_finalizer_sequence",
        expected_order=expected,
        observed_order=[str(item["role"]) for item in invocations],
        violations=violations,
        details="release-evidence-converge must run a dry-run finalizer, converge fixed-point writers, clean tmp JSON, and end with finality verification.",
    )


def _release_converge_repetition_budget(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for invocation in invocations:
        target = str(invocation["target"])
        counts[target] = counts.get(target, 0) + 1
    repeated_targets = sorted(target for target, count in counts.items() if count > 1)
    violations = [
        {
            "target": target,
            "count": counts[target],
            "reason": "unexpected_repeated_closeout_target",
        }
        for target in repeated_targets
        if target not in ALLOWED_REPEATED_CONVERGE_TARGETS
    ]
    return _check(
        "release_evidence_converge_repetition_budget",
        expected_order=sorted(ALLOWED_REPEATED_CONVERGE_TARGETS),
        observed_order=[f"{target} x{counts[target]}" for target in repeated_targets],
        violations=violations,
        details=(
            "Repeated release evidence converge refresh targets must stay explicit and bounded. "
            "Fixed-point owns iterative convergence; new repeated Make targets need an intentional contract update."
        ),
    )


def _release_finality_resettle_check(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [
        "workflow-dependency-planner",
        "release-authority-sealed-preflight",
        "generated-artifact-finality-suffix",
        "release-closeout-summary-report",
        "release-closeout-fixed-point",
        "tmp-json-clean",
        "release-closeout-finality-verify",
    ]
    check = _check_subsequence(
        "release_finality_resettle_sequence",
        invocations,
        expected,
        details=(
            "release-finality-resettle must keep narrow generated-report repairs cheap, "
            "refresh sealed rehearsal authority before freshness/finality scans, "
            "refresh the summary tracked by fixed-point, "
            "then make release-closeout-fixed-point the terminal writer before finality verify."
        ),
    )
    finality_index = _first_index(invocations, "release-closeout-finality-verify")
    if finality_index and finality_index != len(invocations):
        check["status"] = "fail"
        check["violations"].append(
            {
                "expected_role": "release-closeout-finality-verify",
                "reason": "finality_verify_must_be_terminal",
            }
        )
    if _first_index(invocations, "release-evidence-converge"):
        check["status"] = "fail"
        check["violations"].append(
            {
                "target": "release-evidence-converge",
                "reason": "resettle_lane_must_not_call_full_converge",
            }
        )
    return check


def _release_post_commit_finalizer_sequence_check(
    invocations: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = [
        "script-output-surfaces-check",
        "release-smoke-fast-current-check",
        "test-execution-summary-current-check",
        "test-execution-summary-full-current-check",
        "sync-public-policy-check",
        "public-check-summary-current-check",
        "artifact-freshness-check",
        "release-closeout-finality-verify",
    ]
    check = _check_subsequence(
        "release_post_commit_finalizer_sequence",
        invocations,
        expected,
        details=(
            "release-post-commit-finalize must stay a focused HEAD-bound suffix: "
            "current/check-only surfaces first, terminal finality verify, then "
            "the non-mutating post-commit readback."
        ),
    )
    if invocations and str(invocations[-1]["target"]) != "release-closeout-finality-verify":
        check["status"] = "fail"
        check["violations"].append(
            {
                "expected_role": "release-closeout-finality-verify",
                "reason": "finality_verify_must_be_last_make_invocation",
            }
        )
    return check


def _release_post_commit_finalizer_repetition_budget(
    invocations: list[dict[str, Any]],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for invocation in invocations:
        target = str(invocation["target"])
        counts[target] = counts.get(target, 0) + 1
    repeated_targets = sorted(target for target, count in counts.items() if count > 1)
    violations = [
        {
            "target": target,
            "count": counts[target],
            "reason": "unexpected_repeated_post_commit_target",
        }
        for target in repeated_targets
    ]
    violations.extend(
        {
            "target": target,
            "count": counts[target],
            "reason": "forbidden_post_commit_target",
        }
        for target in sorted(FORBIDDEN_POST_COMMIT_FINALIZER_TARGETS)
        if counts.get(target, 0)
    )
    return _check(
        "release_post_commit_finalizer_repetition_budget",
        expected_order=["each post-commit Make target at most once"],
        observed_order=[
            f"{target} x{counts[target]}"
            for target in sorted(
                set(repeated_targets) | (FORBIDDEN_POST_COMMIT_FINALIZER_TARGETS & set(counts))
            )
        ],
        violations=violations,
        details=(
            "Post-commit finalization must not reintroduce an outer writer loop, "
            "full-suite refresh, or staged release-authority cleanup. "
            "Fixed-point owns digest iteration and staged authority lanes own their own refreshes."
        ),
    )


def _release_converge_preflight_check(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [
        "generated-artifact-script-output",
        "report-schema-samples-regenerate",
        "goal-runtime-local-evidence-refresh",
        "test-execution-summary-report-contract-refresh-no-smoke",
    ]
    check = _check_subsequence(
        "release_converge_preflight_sequence",
        invocations,
        expected,
        details=(
            "release-converge-preflight must refresh the narrow script-output surface "
            "before report-contract summaries or smoke evidence can read it."
        ),
    )
    if invocations and str(invocations[0]["role"]) != "generated-artifact-script-output":
        check["status"] = "fail"
        check["violations"].append(
            {
                "expected_role": "generated-artifact-script-output",
                "reason": "script_output_surface_refresh_must_start_preflight",
            }
        )
    return check


def _release_source_ready_transaction_check(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [
        "release-source-ready-prepare",
        "release-source-ready-commit",
        "release-post-commit-finalize",
        "release-source-ready-post-verify",
    ]
    check = _check_subsequence(
        "release_source_ready_transaction_sequence",
        invocations,
        expected,
        details=(
            "release-source-ready must prepare all mutating evidence before committing, "
            "create one release-source-ready commit, converge post-commit evidence, "
            "then run a write-free post-verify lane."
        ),
    )
    terminal_index = _first_index(invocations, "release-source-ready-post-verify")
    if terminal_index != len(invocations):
        check["status"] = "fail"
        check["violations"].append(
            {
                "expected_role": "release-source-ready-post-verify",
                "reason": "release_source_ready_post_verify_must_be_terminal",
            }
        )
    return check


def _release_source_ready_prepare_check(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    return _check_subsequence(
        "release_source_ready_prepare_sequence",
        invocations,
        [
            "release-source-ready-snapshot",
            "release-converge-all-surfaces",
        ],
        details="release-source-ready-prepare must snapshot the starting HEAD before mutating convergence.",
    )


def _release_source_ready_post_verify_check(
    invocations: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = [
        "release-check-all-surfaces",
        "release-source-ready-status",
    ]
    check = _check_subsequence(
        "release_source_ready_post_verify_sequence",
        invocations,
        expected,
        details=(
            "release-source-ready-post-verify must stay write-free: check all surfaces, "
            "then print the source-ready versus sealed machine-release authority summary."
        ),
    )
    forbidden = [
        "auto-improve-readiness-worktree-guard",
        "goal-runtime-local-evidence-refresh",
        "generated-artifact-converge",
        "remediation-backlog",
        "release-closeout-fixed-point",
        "release-source-ready-amend",
        "release-source-ready-final-guard-amend",
    ]
    for target in forbidden:
        if _first_index(invocations, target):
            check["status"] = "fail"
            check["violations"].append(
                {
                    "target": target,
                    "reason": "post_verify_must_be_write_free",
                }
            )
    terminal_index = _first_index(invocations, "release-source-ready-status")
    if terminal_index != len(invocations):
        check["status"] = "fail"
        check["violations"].append(
            {
                "expected_role": "release-source-ready-status",
                "reason": "release_source_ready_status_must_be_terminal",
            }
        )
    return check


def _status_from_checks(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if any(check["status"] == "attention" for check in checks):
        return "attention"
    return "pass"


def _planner_snapshot(planner_report: dict[str, Any]) -> dict[str, Any]:
    workflow_ids = [
        str(item.get("workflow_id", "")).strip()
        for item in planner_report.get("selected_workflows", [])
        if isinstance(item, dict) and str(item.get("workflow_id", "")).strip()
    ]
    return {
        "status": str(planner_report.get("status", "")),
        "workflow_ids": workflow_ids,
        "dependency_edge_count": int(
            planner_report.get("summary", {}).get("dependency_edge_count", 0)
        ),
    }


def _target_recipe_payload(target: str, invocations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "target": target,
        "invocation_count": len(invocations),
        "invocations": invocations,
    }


def _workflow_order_inputs(
    vault: Path,
    *,
    policy_path: str | None,
    context: RuntimeContext | None,
) -> _WorkflowOrderInputs:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    makefile_text, makefile_sources = load_makefile_text(resolved_vault)
    fixed_point_policy = _load_json(resolved_vault / FIXED_POINT_POLICY_PATH)
    writers = _fixed_point_writer_specs(fixed_point_policy)
    invocations_by_target = {
        target: _recipe_invocations(makefile_text, target)
        for target in TARGET_RECIPE_ORDER
    }
    planner_report = build_workflow_dependency_report(
        resolved_vault,
        changed_paths=["Makefile"],
        policy_path=policy_path,
        context=runtime_context,
    )
    return _WorkflowOrderInputs(
        resolved_vault=resolved_vault,
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_context=runtime_context,
        generated_at=runtime_context.isoformat_z(),
        makefile_sources=makefile_sources,
        fixed_point_policy=fixed_point_policy,
        writers=writers,
        planner_report=planner_report,
        invocations_by_target=invocations_by_target,
    )


def _check_finalized_finality_terminal_check(
    invocations: list[dict[str, Any]],
) -> dict[str, Any]:
    finality_index = _first_index(invocations, "release-closeout-finality-verify")
    violations = []
    if not finality_index or finality_index != len(invocations):
        violations.append(
            {
                "expected_role": "release-closeout-finality-verify",
                "reason": "finality_verify_must_be_terminal",
            }
        )
    return _check(
        "check_finalized_finality_terminal",
        expected_order=["release-closeout-finality-verify"],
        observed_order=[str(item["role"]) for item in invocations],
        violations=violations,
        details="check-finalized must end with release-closeout-finality-verify after any canonical refreshes.",
    )


def _release_workflow_order_checks(inputs: _WorkflowOrderInputs) -> list[dict[str, Any]]:
    invocations = inputs.invocations_by_target
    check_finalized_invocations = invocations[CHECK_FINALIZED_TARGET]
    return [
        _release_converge_finalizer_check(invocations[RELEASE_CONVERGE_TARGET]),
        _release_converge_repetition_budget(invocations[RELEASE_CONVERGE_TARGET]),
        _release_converge_preflight_check(invocations[RELEASE_CONVERGE_PREFLIGHT_TARGET]),
        _release_finality_resettle_check(invocations[RELEASE_FINALITY_RESETTLE_TARGET]),
        _release_post_commit_finalizer_sequence_check(
            invocations[RELEASE_POST_COMMIT_FINALIZE_TARGET]
        ),
        _release_post_commit_finalizer_repetition_budget(
            invocations[RELEASE_POST_COMMIT_FINALIZE_TARGET]
        ),
        _check_subsequence(
            "check_finalized_post_check_sequence",
            check_finalized_invocations,
            [
                "release-closeout-post-check-finalizer-dry-run",
                "release-closeout-fixed-point",
                "tmp-json-clean",
                "release-closeout-post-check-finalizer-strict-dry-run",
                "release-closeout-finality-verify",
            ],
            details="check-finalized must make post-check canonical refresh self-contained instead of relying on operator memory.",
        ),
        _check_finalized_finality_terminal_check(check_finalized_invocations),
        _check_fixed_point_policy_order(inputs.writers),
        _release_source_ready_transaction_check(invocations[RELEASE_SOURCE_READY_TARGET]),
        _release_source_ready_prepare_check(invocations[RELEASE_SOURCE_READY_PREPARE_TARGET]),
        _release_source_ready_post_verify_check(
            invocations[RELEASE_SOURCE_READY_POST_VERIFY_TARGET]
        ),
        _check_planner_hooks(inputs.planner_report, invocations[RELEASE_CONVERGE_TARGET]),
        _check_planner_fixed_point_writer_order(inputs.planner_report, inputs.writers),
    ]


def _workflow_order_envelope(inputs: _WorkflowOrderInputs) -> dict[str, Any]:
    return build_canonical_report_envelope(
        inputs.resolved_vault,
        generated_at=inputs.generated_at,
        artifact_kind="release_workflow_order_guard",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=inputs.resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=[
            "ops/scripts/release/release_workflow_order_guard.py",
            "ops/scripts/core/workflow_dependency_planner.py",
            "ops/scripts/release/release_closeout_fixed_point.py",
            "Makefile",
            *[path for path in inputs.makefile_sources if path != "Makefile"],
            FIXED_POINT_POLICY_PATH,
        ],
        file_inputs={
            **{path: path for path in inputs.makefile_sources},
            "fixed_point_policy": FIXED_POINT_POLICY_PATH,
        },
        text_inputs={
            "fixed_point_initial_order": json.dumps(
                _fixed_point_initial_order(inputs.writers),
                ensure_ascii=False,
            ),
        },
    )


def _workflow_order_target_recipes(inputs: _WorkflowOrderInputs) -> list[dict[str, Any]]:
    return [
        _target_recipe_payload(target, inputs.invocations_by_target[target])
        for target in TARGET_RECIPE_ORDER
    ]


def _workflow_order_summary(
    inputs: _WorkflowOrderInputs,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    invocations = inputs.invocations_by_target
    return {
        "check_count": len(checks),
        "fail_count": sum(1 for check in checks if check["status"] == "fail"),
        "attention_count": sum(1 for check in checks if check["status"] == "attention"),
        "release_converge_invocation_count": len(invocations[RELEASE_CONVERGE_TARGET]),
        "check_finalized_invocation_count": len(invocations[CHECK_FINALIZED_TARGET]),
        "fixed_point_writer_count": len(inputs.writers),
    }


def _workflow_order_report_payload(
    inputs: _WorkflowOrderInputs,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **_workflow_order_envelope(inputs),
        "vault": report_path(inputs.resolved_vault, inputs.resolved_vault),
        "status": _status_from_checks(checks),
        "policy": {
            "path": report_path(inputs.resolved_vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "fixed_point_policy": {
            "path": FIXED_POINT_POLICY_PATH,
            "version": inputs.fixed_point_policy.get("version"),
            "writer_count": len(inputs.writers),
            "initial_iteration_targets": _fixed_point_initial_order(inputs.writers),
        },
        "summary": _workflow_order_summary(inputs, checks),
        "checks": checks,
        "target_recipes": _workflow_order_target_recipes(inputs),
        "planner_snapshot": _planner_snapshot(inputs.planner_report),
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    inputs = _workflow_order_inputs(vault, policy_path=policy_path, context=context)
    checks = _release_workflow_order_checks(inputs)
    return _workflow_order_report_payload(inputs, checks)


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release workflow order guard schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate release evidence converge Make ordering against planner and fixed-point policy hooks.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.no_fail:
        return 0
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
