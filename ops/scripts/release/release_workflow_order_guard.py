#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
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
        SEMANTIC_NOOP_ENVELOPE_FIELDS,
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
        MAKE_RECIPE_RE,
        TARGET_RE,
        _first_make_target,
        build_report as build_workflow_dependency_report,
    )
    from ops.scripts.release.release_closeout_fixed_point import (
        POLICY_PATH as FIXED_POINT_POLICY_PATH,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SEMANTIC_NOOP_ENVELOPE_FIELDS,
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
        MAKE_RECIPE_RE,
        TARGET_RE,
        _first_make_target,
        build_report as build_workflow_dependency_report,
    )

    from .release_closeout_fixed_point import POLICY_PATH as FIXED_POINT_POLICY_PATH


DEFAULT_OUT = "ops/reports/release-workflow-order-guard.json"
PRODUCER = "ops.scripts.release_workflow_order_guard"
SCHEMA_PATH = "ops/schemas/release-workflow-order-guard.schema.json"
SPEC_PATH = "ops/policies/release-workflow-order-guard.json"
SPEC_SCHEMA_PATH = "ops/schemas/release-workflow-order-guard-spec.schema.json"
SOURCE_COMMAND = (
    "python -m ops.scripts.release_workflow_order_guard "
    "--vault . --out ops/reports/release-workflow-order-guard.json"
)
RELEASE_CONVERGE_TARGET = "release-evidence-converge"
CHECK_FINALIZED_TARGET = "check-finalized"
RAW_RECIPE_COMMAND_ROLE = "raw-recipe-command"


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
    invocations_by_target: dict[str, list[dict[str, Any]]]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _spec_entries(spec: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = spec.get(key)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _load_workflow_order_spec(
    vault: Path,
    spec_path: str | None = None,
) -> tuple[dict[str, Any], Path]:
    relative_path = Path(spec_path or SPEC_PATH)
    resolved_path = relative_path if relative_path.is_absolute() else vault / relative_path
    spec = _load_json(resolved_path)
    schema = load_schema_with_vault_override(vault, SPEC_SCHEMA_PATH)
    validate_or_raise(
        spec,
        schema,
        context=f"invalid release workflow order spec in {resolved_path.as_posix()}",
    )
    return spec, resolved_path


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


def _recipe_argv(raw_line: str) -> list[str]:
    try:
        return shlex.split(raw_line.strip())
    except ValueError:
        return []


def _command_role_match_index(raw_line: str, command_role: dict[str, Any]) -> int:
    raw_line_contains = str(command_role.get("raw_line_contains", "")).strip()
    match_index = raw_line.find(raw_line_contains) if raw_line_contains else -1
    if match_index < 0:
        return -1
    argv_equals = _string_list(command_role.get("argv_equals"))
    if argv_equals and _recipe_argv(raw_line) != argv_equals:
        return -1
    return match_index


def _first_role_targets(workflow_order_spec: dict[str, Any]) -> set[str]:
    return {
        str(entry.get("target", "")).strip()
        for entry in _spec_entries(workflow_order_spec, "first_role_checks")
        if str(entry.get("target", "")).strip()
    }


def _raw_recipe_command_event(line_no: int, raw_line: str) -> dict[str, Any]:
    return {
        "line": line_no,
        "target": RAW_RECIPE_COMMAND_ROLE,
        "role": RAW_RECIPE_COMMAND_ROLE,
        "raw_args": raw_line.strip(),
    }


def _is_ignorable_recipe_line(raw_line: str) -> bool:
    stripped = raw_line.strip()
    return not stripped or stripped.startswith("#")


def _direct_recipe_invocations(
    makefile_text: str,
    target: str,
    workflow_order_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    active = False
    invocations: list[dict[str, Any]] = []
    command_roles = [
        item
        for item in _spec_entries(workflow_order_spec, "recipe_command_roles")
        if str(item.get("target", "")).strip() == target
    ]
    raw_sensitive = target in _first_role_targets(workflow_order_spec)
    for line_no, raw_line in enumerate(makefile_text.splitlines(), start=1):
        if raw_line.startswith("\t"):
            if not active:
                continue
            recipe_events: list[tuple[int, dict[str, Any]]] = []
            for command_role in command_roles:
                match_index = _command_role_match_index(raw_line, command_role)
                if match_index < 0:
                    continue
                role = str(command_role.get("role", "")).strip()
                recipe_events.append(
                    (
                        match_index,
                        {
                            "line": line_no,
                            "target": role,
                            "role": role,
                            "raw_args": raw_line.strip(),
                        },
                    )
                )
            for make_match in MAKE_RECIPE_RE.finditer(raw_line):
                raw_args = make_match.group("args").strip()
                make_target = _first_make_target(raw_args.split())
                if make_target is None:
                    continue
                recipe_events.append(
                    (
                        make_match.start(),
                        {
                            "line": line_no,
                            "target": make_target,
                            "role": _invocation_role(make_target, raw_args, workflow_order_spec),
                            "raw_args": raw_args,
                        },
                    )
                )
            if raw_sensitive and not recipe_events and not _is_ignorable_recipe_line(raw_line):
                recipe_events.append((0, _raw_recipe_command_event(line_no, raw_line)))
            for _event_index, event in sorted(recipe_events, key=lambda item: item[0]):
                invocations.append({**event, "order": len(invocations) + 1})
            continue

        target_match = TARGET_RE.match(raw_line.rstrip())
        if target_match is None:
            active = False
            continue
        active = target in {item.strip() for item in target_match.group(1).split() if item.strip()}
    return invocations


def _recipe_invocations(
    makefile_text: str,
    target: str,
    workflow_order_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    dependencies = _target_dependencies(makefile_text)
    visited: set[str] = set()
    invocations: list[dict[str, Any]] = []

    def visit(active_target: str) -> None:
        if active_target in visited:
            return
        visited.add(active_target)
        for dependency in dependencies.get(active_target, []):
            visit(dependency)
        for invocation in _direct_recipe_invocations(
            makefile_text,
            active_target,
            workflow_order_spec,
        ):
            invocations.append({**invocation, "order": len(invocations) + 1})

    visit(target)
    return invocations


def _invocation_role(
    target: str,
    raw_args: str,
    workflow_order_spec: dict[str, Any],
) -> str:
    for override in _spec_entries(workflow_order_spec, "role_overrides"):
        if str(override.get("target", "")).strip() != target:
            continue
        required_fragment = str(override.get("raw_args_contains", "")).strip()
        if required_fragment and required_fragment in raw_args:
            return str(override.get("role", "")).strip() or target
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


def _check_spec_subsequence(
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return _check_subsequence(
        str(entry["id"]),
        invocations_by_target.get(str(entry["target"]), []),
        _string_list(entry.get("roles")),
        details=str(entry.get("details", "")),
    )


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
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> None:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    observed_targets = [str(item["target"]) for item in invocations]
    for target in _string_list(entry.get("forbidden_targets")):
        if target not in observed_targets:
            continue
        check["status"] = "fail"
        check["violations"].append(
            {
                "target": target,
                "reason": str(entry["violation_reason"]),
            }
        )


def _check_forbidden_target_guard(
    entry: dict[str, Any],
    invocations_by_target: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    invocations = invocations_by_target.get(str(entry["target"]), [])
    check = _check(
        str(entry["id"]),
        expected_order=[f"no {target}" for target in _string_list(entry.get("forbidden_targets"))],
        observed_order=[str(item["target"]) for item in invocations],
        details=str(entry.get("details", "")),
    )
    _append_forbidden_target_guard(check, entry, invocations_by_target)
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
    forbidden_targets = set(_string_list(entry.get("forbidden_targets")))
    violations = [
        {
            "target": target,
            "count": counts[target],
            "reason": str(entry["violation_reason"]),
        }
        for target in repeated_targets
        if target not in allowed_repeated_targets
    ]
    violations.extend(
        {
            "target": target,
            "count": counts[target],
            "reason": str(entry.get("forbidden_violation_reason", entry["violation_reason"])),
        }
        for target in sorted(forbidden_targets)
        if counts.get(target, 0)
    )
    observed_targets = sorted(set(repeated_targets) | (forbidden_targets & set(counts)))
    expected_order = (
        sorted(allowed_repeated_targets)
        if allowed_repeated_targets
        else [str(entry.get("expected_order_label", "each Make target at most once"))]
    )
    return _check(
        str(entry["id"]),
        expected_order=expected_order,
        observed_order=[f"{target} x{counts[target]}" for target in observed_targets],
        violations=violations,
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
    elif "release-terminal-finality" in planner_steps:
        expected = ["release-terminal-finality"]
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
    invocations_by_target = {
        target: _recipe_invocations(makefile_text, target, workflow_order_spec)
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
        invocations_by_target=invocations_by_target,
    )


def _release_workflow_order_checks(inputs: _WorkflowOrderInputs) -> list[dict[str, Any]]:
    invocations = inputs.invocations_by_target
    checks: list[dict[str, Any]] = []
    checks_by_id: dict[str, dict[str, Any]] = {}
    for entry in _spec_entries(inputs.workflow_order_spec, "expected_subsequences"):
        check = _check_spec_subsequence(entry, invocations)
        checks.append(check)
        checks_by_id[str(entry["id"])] = check

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
            _append_forbidden_target_guard(checks_by_id[check_id], entry, invocations)
        else:
            checks.append(_check_forbidden_target_guard(entry, invocations))

    for entry in _spec_entries(inputs.workflow_order_spec, "repetition_budgets"):
        checks.append(_check_repetition_budget(entry, invocations))

    checks.extend(
        [
            _check_fixed_point_policy_order(inputs.writers),
            _check_planner_hooks(
                inputs.planner_report,
                invocations[RELEASE_CONVERGE_TARGET],
            ),
            _check_planner_fixed_point_writer_order(
                inputs.planner_report,
                inputs.writers,
            ),
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
    return {
        key: value
        for key, value in report.items()
        if key not in SEMANTIC_NOOP_ENVELOPE_FIELDS
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
        "--check-out",
        default=None,
        help="Optional candidate report path to write while checking the canonical report.",
    )
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
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
