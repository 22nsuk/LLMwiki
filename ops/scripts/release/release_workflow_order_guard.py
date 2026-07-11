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
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        read_json_object,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.core.makefile_runtime import load_makefile_text
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_runtime import (
        load_schema_with_vault_override,
        validate_or_raise,
    )
    from ops.scripts.core.workflow_dependency_planner import (
        build_report as build_workflow_dependency_report,
    )
    from ops.scripts.release.release_closeout_fixed_point import (
        POLICY_PATH as FIXED_POINT_POLICY_PATH,
    )
    from ops.scripts.release.release_workflow_order_guard_recipes import (
        SPEC_PATH,
        _expanded_recipe_invocations,
        _load_json,
        _load_workflow_order_spec,
        _protected_expected_lines,
        _protected_recipe_entries,
        _protected_recipe_observations,
        _protected_recipe_targets,
        _ProtectedRecipeObservation,
        _recipe_invocations,
        _spec_entries,
        _target_rule_kinds,
        check_workflow_order_spec_raw_lines,
        write_workflow_order_spec_raw_lines,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        read_json_object,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.core.makefile_runtime import load_makefile_text
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_runtime import (
        load_schema_with_vault_override,
        validate_or_raise,
    )
    from ops.scripts.core.workflow_dependency_planner import (
        build_report as build_workflow_dependency_report,
    )

    from .release_closeout_fixed_point import POLICY_PATH as FIXED_POINT_POLICY_PATH
    from .release_workflow_order_guard_recipes import (
        SPEC_PATH,
        _expanded_recipe_invocations,
        _load_json,
        _load_workflow_order_spec,
        _protected_expected_lines,
        _protected_recipe_entries,
        _protected_recipe_observations,
        _protected_recipe_targets,
        _ProtectedRecipeObservation,
        _recipe_invocations,
        _spec_entries,
        _target_rule_kinds,
        check_workflow_order_spec_raw_lines,
        write_workflow_order_spec_raw_lines,
    )


DEFAULT_OUT = "ops/reports/release-workflow-order-guard.json"
PRODUCER = "ops.scripts.release_workflow_order_guard"
SCHEMA_PATH = "ops/schemas/release-workflow-order-guard.schema.json"
SOURCE_COMMAND = (
    "python -m ops.scripts.release_workflow_order_guard "
    "--vault . --out ops/reports/release-workflow-order-guard.json"
)
RELEASE_CONVERGE_TARGET = "release-evidence-converge"
CHECK_FINALIZED_TARGET = "check-finalized"


@dataclass(frozen=True)
class _WorkflowOrderInputs:
    resolved_vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    workflow_order_spec: dict[str, Any]
    runtime_context: RuntimeContext
    generated_at: str
    makefile_sources: list[str]
    fixed_point_policy: dict[str, Any]
    writers: list[dict[str, Any]]
    planner_report: dict[str, Any]
    rule_kinds_by_target: dict[str, set[str]]
    invocations_by_target: dict[str, list[dict[str, Any]]]
    expanded_invocations_by_target: dict[str, list[dict[str, Any]]]
    protected_recipe_observations: dict[str, _ProtectedRecipeObservation]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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


def _check_spec_subsequence(
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    expected_roles = _string_list(entry.get("roles"))
    check = _check_subsequence(
        str(entry["id"]),
        invocations,
        expected_roles,
        details=str(entry.get("details", "")),
    )
    observed_roles = [str(item["role"]) for item in invocations]
    if bool(entry.get("exact")) and observed_roles != expected_roles:
        check["status"] = "fail"
        check["violations"].append(
            {
                "expected_role": ",".join(expected_roles),
                "observed_role": ",".join(observed_roles),
                "reason": "sequence_must_be_exact",
            }
        )
    return check


def _append_terminal_guard(
    check: dict[str, Any],
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> None:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    role = str(entry["role"])
    terminal_index = _first_index(invocations, role)
    if terminal_index == len(invocations) and terminal_index:
        return
    check["status"] = "fail"
    check["violations"].append(
        {
            "expected_role": role,
            "reason": str(entry["reason"]),
        }
    )


def _check_terminal_guard(
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    check = _check(
        str(entry["id"]),
        expected_order=[str(entry["role"])],
        observed_order=[str(item["role"]) for item in invocations],
        details=str(entry.get("details", "")),
    )
    _append_terminal_guard(check, entry, invocations_by_target)
    return check


def _append_first_role_guard(
    check: dict[str, Any],
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> None:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    expected_role = str(entry["role"])
    if invocations and str(invocations[0]["role"]) == expected_role:
        return
    check["status"] = "fail"
    check["violations"].append(
        {
            "expected_role": expected_role,
            "reason": str(entry["reason"]),
        }
    )


def _check_first_role_guard(
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    check = _check(
        str(entry["id"]),
        expected_order=[str(entry["role"])],
        observed_order=[str(item["role"]) for item in invocations],
        details=str(entry.get("details", "")),
    )
    _append_first_role_guard(check, entry, invocations_by_target)
    return check


def _append_forbidden_target_guard(
    check: dict[str, Any],
    entry: dict[str, Any],
    expanded_invocations_by_target: dict[str, list[dict[str, Any]]],
) -> None:
    invocations = expanded_invocations_by_target.get(str(entry["target"]), [])
    for target in _string_list(entry.get("forbidden_targets")):
        matching_invocations = [
            item for item in invocations if str(item["target"]) == target
        ]
        if not matching_invocations:
            continue
        first_match = matching_invocations[0]
        check["status"] = "fail"
        check["violations"].append(
            {
                "target": target,
                "line": int(first_match["line"]),
                "invocation_path": str(first_match.get("invocation_path", target)),
                "reason": str(entry["violation_reason"]),
            }
        )


def _check_forbidden_target_guard(
    entry: dict[str, Any],
    expanded_invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    invocations = expanded_invocations_by_target.get(str(entry["target"]), [])
    check = _check(
        str(entry["id"]),
        expected_order=[f"no {target}" for target in _string_list(entry.get("forbidden_targets"))],
        observed_order=[str(item["target"]) for item in invocations],
        details=str(entry.get("details", "")),
    )
    _append_forbidden_target_guard(check, entry, expanded_invocations_by_target)
    return check


def _check_repetition_budget(
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    counts: dict[str, int] = {}
    for invocation in invocations:
        target = str(invocation["target"])
        counts[target] = counts.get(target, 0) + 1
    repeated_targets = sorted(target for target, count in counts.items() if count > 1)
    allowed_repeated_targets = set(_string_list(entry.get("allowed_repeated_targets")))
    violations = [
        {
            "target": target,
            "count": counts[target],
            "reason": str(entry["violation_reason"]),
        }
        for target in repeated_targets
        if target not in allowed_repeated_targets
    ]
    expected_order = (
        sorted(allowed_repeated_targets)
        if allowed_repeated_targets
        else [str(entry.get("expected_order_label", "each Make target at most once"))]
    )
    return _check(
        str(entry["id"]),
        expected_order=expected_order,
        observed_order=[f"{target} x{counts[target]}" for target in repeated_targets],
        violations=violations,
        details=str(entry.get("details", "")),
    )


def _check_role_override_sequence_coverage(inputs: _WorkflowOrderInputs) -> dict[str, Any]:
    coverage = inputs.workflow_order_spec.get("role_override_sequence_coverage", {})
    coverage = coverage if isinstance(coverage, dict) else {}
    allowlisted_roles = set(_string_list(coverage.get("allowlisted_roles")))
    override_roles = {
        str(entry.get("role", "")).strip()
        for entry in _spec_entries(inputs.workflow_order_spec, "role_overrides")
        if str(entry.get("role", "")).strip()
    }
    expected_roles_by_target: dict[str, set[str]] = {}
    for entry in _spec_entries(inputs.workflow_order_spec, "expected_subsequences"):
        target = str(entry.get("target", "")).strip()
        if not target:
            continue
        expected_roles_by_target.setdefault(target, set()).update(
            _string_list(entry.get("roles"))
        )

    observed_order: list[str] = []
    violations: list[dict[str, Any]] = []
    observed_pairs: set[tuple[str, str]] = set()
    for target, invocations in inputs.invocations_by_target.items():
        expected_roles = expected_roles_by_target.get(target, set())
        for invocation in invocations:
            role = str(invocation.get("role", "")).strip()
            if role not in override_roles or role in allowlisted_roles:
                continue
            observed_pair = (target, role)
            if observed_pair in observed_pairs:
                continue
            observed_pairs.add(observed_pair)
            observed_order.append(f"{target}:{role}")
            if role in expected_roles:
                continue
            violations.append(
                {
                    "target": target,
                    "expected_role": role,
                    "reason": "role_override_missing_from_expected_subsequence",
                }
            )

    expected_order = sorted(role for role in override_roles if role not in allowlisted_roles)
    return _check(
        "role_override_sequence_coverage",
        expected_order=expected_order,
        observed_order=observed_order,
        violations=violations,
        details=str(
            coverage.get(
                "details",
                "Observed role overrides must be named in their target expected subsequence.",
            )
        ),
    )


def _check_protected_recipe(
    entry: dict[str, Any],
    observations: dict[str, _ProtectedRecipeObservation],
) -> dict[str, Any]:
    target = str(entry["target"])
    observation = observations.get(target)
    expected_order = [
        expected_line.role
        for expected_line in _protected_expected_lines(entry)
    ]
    if observation is None:
        return _check(
            str(entry["id"]),
            expected_order=expected_order,
            observed_order=[],
            violations=[
                {
                    "target": target,
                    "reason": "protected_recipe_observation_missing",
                }
            ],
            details=str(entry.get("details", "")),
        )
    return _check(
        str(entry["id"]),
        expected_order=expected_order,
        observed_order=[str(item["role"]) for item in observation.invocations],
        violations=observation.violations,
        details=str(entry.get("details", "")),
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
                "expensive_prerequisites": [
                    str(dep).strip()
                    for dep in item.get("expensive_prerequisites", [])
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
        for target in writer["expensive_prerequisites"]:
            if target not in seen:
                seen.add(target)
                ordered.append(target)
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


def _check_planner_hooks(planner_report: dict[str, Any]) -> dict[str, Any]:
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
        "release-terminal-finality",
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
        details="The planner closeout recommendation must delegate once to terminal finality instead of expanding writer suffixes.",
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
    elif "release-terminal-finality" in planner_steps:
        expected = ["release-terminal-finality"]
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
        details="The planner closeout recommendation must delegate to the fixed-point terminal controller or preserve a valid graph entrypoint.",
    )


def _check_target_rule_kind_conflicts(inputs: _WorkflowOrderInputs) -> dict[str, Any]:
    targets = _string_list(inputs.workflow_order_spec.get("target_recipe_order"))
    violations = [
        {
            "target": target,
            "reason": "mixed_single_and_double_colon_rules",
        }
        for target in targets
        if {":", "::"}.issubset(inputs.rule_kinds_by_target.get(target, set()))
    ]
    return _check(
        "make_target_rule_kind_conflicts",
        expected_order=["no mixed single-colon and double-colon target rules"],
        observed_order=[violation["target"] for violation in violations],
        violations=violations,
        details="Modeled Make targets must not mix ':' and '::' rule forms because GNU make rejects that target shape.",
    )


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
    spec_path: str | None,
    context: RuntimeContext | None,
) -> _WorkflowOrderInputs:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    workflow_order_spec, _resolved_workflow_order_spec_path = _load_workflow_order_spec(
        resolved_vault,
        spec_path,
    )
    runtime_context = context or RuntimeContext.from_policy(policy)
    makefile_text, makefile_sources = load_makefile_text(resolved_vault)
    fixed_point_policy = _load_json(resolved_vault / FIXED_POINT_POLICY_PATH)
    writers = _fixed_point_writer_specs(fixed_point_policy)
    rule_kinds_by_target = _target_rule_kinds(makefile_text)
    protected_recipe_observations = _protected_recipe_observations(
        makefile_text,
        workflow_order_spec,
    )
    protected_recipe_targets = _protected_recipe_targets(workflow_order_spec)
    invocations_by_target = {
        target: (
            protected_recipe_observations[target].invocations
            if target in protected_recipe_targets
            else _recipe_invocations(makefile_text, target, workflow_order_spec)
        )
        for target in _string_list(workflow_order_spec.get("target_recipe_order"))
    }
    expanded_invocations_by_target = {
        target: _expanded_recipe_invocations(
            makefile_text,
            target,
            workflow_order_spec,
        )
        for target in _string_list(workflow_order_spec.get("target_recipe_order"))
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
        workflow_order_spec=workflow_order_spec,
        runtime_context=runtime_context,
        generated_at=runtime_context.isoformat_z(),
        makefile_sources=makefile_sources,
        fixed_point_policy=fixed_point_policy,
        writers=writers,
        planner_report=planner_report,
        rule_kinds_by_target=rule_kinds_by_target,
        invocations_by_target=invocations_by_target,
        expanded_invocations_by_target=expanded_invocations_by_target,
        protected_recipe_observations=protected_recipe_observations,
    )


def _release_workflow_order_checks(inputs: _WorkflowOrderInputs) -> list[dict[str, Any]]:
    invocations = inputs.invocations_by_target
    checks: list[dict[str, Any]] = []
    checks_by_id: dict[str, dict[str, Any]] = {}
    for entry in _protected_recipe_entries(inputs.workflow_order_spec):
        checks.append(_check_protected_recipe(entry, inputs.protected_recipe_observations))

    for entry in _spec_entries(inputs.workflow_order_spec, "expected_subsequences"):
        check = _check_spec_subsequence(entry, invocations)
        checks.append(check)
        checks_by_id[str(entry["id"])] = check

    checks.append(_check_role_override_sequence_coverage(inputs))

    for entry in _spec_entries(inputs.workflow_order_spec, "terminal_checks"):
        check_id = str(entry["id"])
        if check_id in checks_by_id:
            _append_terminal_guard(checks_by_id[check_id], entry, invocations)
        else:
            checks.append(_check_terminal_guard(entry, invocations))

    for entry in _spec_entries(inputs.workflow_order_spec, "first_role_checks"):
        check_id = str(entry["id"])
        if check_id in checks_by_id:
            _append_first_role_guard(checks_by_id[check_id], entry, invocations)
        else:
            checks.append(_check_first_role_guard(entry, invocations))

    for entry in _spec_entries(inputs.workflow_order_spec, "forbidden_target_checks"):
        check_id = str(entry["id"])
        if check_id in checks_by_id:
            _append_forbidden_target_guard(
                checks_by_id[check_id],
                entry,
                inputs.expanded_invocations_by_target,
            )
        else:
            checks.append(
                _check_forbidden_target_guard(
                    entry,
                    inputs.expanded_invocations_by_target,
                )
            )

    for entry in _spec_entries(inputs.workflow_order_spec, "repetition_budgets"):
        checks.append(_check_repetition_budget(entry, invocations))

    checks.extend(
        [
            _check_fixed_point_policy_order(inputs.writers),
            _check_planner_hooks(inputs.planner_report),
            _check_planner_fixed_point_writer_order(
                inputs.planner_report,
                inputs.writers,
            ),
            _check_target_rule_kind_conflicts(inputs),
        ]
    )
    return checks


def _workflow_order_envelope(inputs: _WorkflowOrderInputs) -> dict[str, Any]:
    source_paths = _string_list(inputs.workflow_order_spec.get("source_paths", {}).get("static"))
    if inputs.workflow_order_spec.get("source_paths", {}).get("include_makefile_sources"):
        for path in inputs.makefile_sources:
            if path not in source_paths:
                source_paths.append(path)
    file_inputs = {
        str(key): str(value)
        for key, value in inputs.workflow_order_spec.get("file_inputs", {})
        .get("static", {})
        .items()
    }
    if inputs.workflow_order_spec.get("file_inputs", {}).get("include_makefile_sources"):
        file_inputs.update({path: path for path in inputs.makefile_sources})
    return build_canonical_report_envelope(
        inputs.resolved_vault,
        generated_at=inputs.generated_at,
        artifact_kind="release_workflow_order_guard",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=inputs.resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=source_paths,
        file_inputs=file_inputs,
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
        for target in _string_list(inputs.workflow_order_spec.get("target_recipe_order"))
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
    spec_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    inputs = _workflow_order_inputs(
        vault,
        policy_path=policy_path,
        spec_path=spec_path,
        context=context,
    )
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


def _stable_report_payload(report: dict[str, Any]) -> dict[str, Any]:
    projection_envelope_fields = {
        "generated_at",
        "source_revision",
        "source_tree_fingerprint",
        "input_fingerprints",
        "currentness",
    }
    return {
        key: value
        for key, value in report.items()
        if key not in projection_envelope_fields
    }


def _stable_report_mismatch_diagnostics(
    actual: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    actual_payload = _stable_report_payload(actual)
    expected_payload = _stable_report_payload(expected)
    actual_keys = set(actual_payload)
    expected_keys = set(expected_payload)
    return {
        "added_keys": sorted(expected_keys - actual_keys),
        "removed_keys": sorted(actual_keys - expected_keys),
        "changed_keys": sorted(
            key
            for key in actual_keys & expected_keys
            if actual_payload[key] != expected_payload[key]
        ),
    }


def check_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    spec_path: str | None = None,
    stored_path: str | None = None,
    check_out: str | None = None,
    context: RuntimeContext | None = None,
    no_fail: bool = False,
) -> int:
    report = build_report(
        vault,
        policy_path=policy_path,
        spec_path=spec_path,
        context=context,
    )
    if check_out:
        destination = write_report(vault, report, check_out)
        print(display_path(vault, destination))

    status_ok = report["status"] in {"pass", "attention"}
    stored = resolve_schema_backed_report_output_path(
        vault,
        stored_path,
        default_relative_path=DEFAULT_OUT,
    )
    if not stored.exists():
        print(
            "release workflow order guard canonical report is missing; "
            f"validated live candidate for {display_path(vault, stored)}",
            file=sys.stderr,
        )
        return 0 if (status_ok or no_fail) else 1

    try:
        actual = read_json_object(stored, context=display_path(vault, stored))
        schema = load_schema_with_vault_override(vault, SCHEMA_PATH)
        validate_or_raise(
            actual,
            schema,
            context=(
                "release workflow order guard stored report schema validation failed "
                f"for {display_path(vault, stored)}"
            ),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            "release workflow order guard check failed: "
            f"could not validate {display_path(vault, stored)} "
            f"({type(exc).__name__}: {exc}). "
            "Run `make release-workflow-order-guard`.",
            file=sys.stderr,
        )
        return 1

    if _stable_report_payload(actual) != _stable_report_payload(report):
        diagnostics = _stable_report_mismatch_diagnostics(actual, report)
        print(
            "release workflow order guard report is stale; "
            "run `make release-workflow-order-guard`.\n"
            + json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 1

    print(f"{display_path(vault, stored)} is current")
    return 0 if (status_ok or no_fail) else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate release evidence converge Make ordering against planner and fixed-point policy hooks.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--spec-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--write-spec",
        action="store_true",
        help="Refresh protected recipe raw_line fields in the workflow order spec from Make recipes.",
    )
    parser.add_argument(
        "--check-spec",
        action="store_true",
        help="Fail when protected recipe raw_line fields drift from Make recipes.",
    )
    parser.add_argument(
        "--check-out",
        default=None,
        help="Optional candidate report path to write while checking the canonical report.",
    )
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    selected_modes = sum(
        bool(flag)
        for flag in (args.check, args.write_spec, args.check_spec)
    )
    if selected_modes > 1:
        print(
            "choose only one of --check, --write-spec, or --check-spec",
            file=sys.stderr,
        )
        return 2
    if args.write_spec:
        try:
            destination = write_workflow_order_spec_raw_lines(
                vault,
                spec_path=args.spec_path,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(display_path(vault, destination))
        return 0
    if args.check_spec:
        diagnostics = check_workflow_order_spec_raw_lines(
            vault,
            spec_path=args.spec_path,
        )
        if diagnostics:
            print(
                "release workflow order guard spec raw lines drifted:\n"
                + json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 1
        spec_path = Path(args.spec_path or SPEC_PATH)
        resolved_spec_path = spec_path if spec_path.is_absolute() else vault / spec_path
        print(f"{display_path(vault, resolved_spec_path)} is current")
        return 0
    if args.check:
        return check_report(
            vault,
            policy_path=args.policy_path,
            spec_path=args.spec_path,
            stored_path=args.out,
            check_out=args.check_out,
            no_fail=args.no_fail,
        )
    report = build_report(vault, policy_path=args.policy_path, spec_path=args.spec_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.no_fail:
        return 0
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
