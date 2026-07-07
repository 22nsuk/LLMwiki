#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
MAKE_RECIPE_RE = re.compile(r"\$\(MAKE\)\s+(?P<args>[^\n;&|]+)")


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


@dataclass(frozen=True)
class _TargetRule:
    targets: set[str]
    deps: list[str]
    inline_recipe: str
    has_inline_recipe: bool
    is_double_colon: bool


@dataclass
class _RecipeDefinition:
    line: int
    rule: _TargetRule
    body_lines: list[tuple[int, str]]


@dataclass(frozen=True)
class _ProtectedExpectedRecipeLine:
    role: str
    target: str
    raw_line: str


@dataclass(frozen=True)
class _ProtectedRecipeObservation:
    expected_lines: list[_ProtectedExpectedRecipeLine]
    invocations: list[dict[str, Any]]
    violations: list[dict[str, Any]]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


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


def _target_rule(raw_line: str) -> _TargetRule | None:
    target_match = TARGET_RE.match(raw_line.rstrip())
    if target_match is None:
        return None
    targets = {item.strip() for item in target_match.group(1).split() if item.strip()}
    raw_deps = target_match.group("deps")
    is_double_colon = raw_deps.startswith(":")
    if is_double_colon:
        raw_deps = raw_deps[1:].lstrip()
    deps_text, separator, inline_recipe = raw_deps.partition(";")
    deps = [
        token.strip()
        for token in deps_text.split()
        if token.strip() and not token.strip().startswith("$")
    ]
    return _TargetRule(
        targets=targets,
        deps=deps,
        inline_recipe=inline_recipe.strip(),
        has_inline_recipe=bool(separator),
        is_double_colon=is_double_colon,
    )


def _target_dependencies(makefile_text: str) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    for raw_line in makefile_text.splitlines():
        if raw_line.startswith("\t"):
            continue
        target_rule = _target_rule(raw_line)
        if target_rule is None:
            continue
        for target in target_rule.targets:
            dependencies.setdefault(target, [])
            for dep in target_rule.deps:
                if dep not in dependencies[target]:
                    dependencies[target].append(dep)
    return dependencies


def _target_rule_kinds(makefile_text: str) -> dict[str, set[str]]:
    rule_kinds: dict[str, set[str]] = {}
    for raw_line in makefile_text.splitlines():
        if raw_line.startswith("\t"):
            continue
        target_rule = _target_rule(raw_line)
        if target_rule is None:
            continue
        rule_kind = "::" if target_rule.is_double_colon else ":"
        for target in target_rule.targets:
            rule_kinds.setdefault(target, set()).add(rule_kind)
    return rule_kinds


def _recipe_line_events(
    raw_line: str,
    line_no: int,
    workflow_order_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    recipe_events: list[tuple[int, dict[str, Any]]] = []
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
    return [event for _event_index, event in sorted(recipe_events, key=lambda item: item[0])]


def _protected_recipe_entries(workflow_order_spec: dict[str, Any]) -> list[dict[str, Any]]:
    return _spec_entries(workflow_order_spec, "protected_recipes")


def _protected_recipe_targets(workflow_order_spec: dict[str, Any]) -> set[str]:
    return {
        str(entry.get("target", "")).strip()
        for entry in _protected_recipe_entries(workflow_order_spec)
        if str(entry.get("target", "")).strip()
    }


def _protected_expected_lines(entry: dict[str, Any]) -> list[_ProtectedExpectedRecipeLine]:
    expected_lines: list[_ProtectedExpectedRecipeLine] = []
    for line_entry in entry.get("expected_lines", []):
        if not isinstance(line_entry, dict):
            continue
        role = str(line_entry.get("role", "")).strip()
        target = str(line_entry.get("target", role)).strip() or role
        raw_line = str(line_entry.get("raw_line", "")).strip()
        if role and target and raw_line:
            expected_lines.append(
                _ProtectedExpectedRecipeLine(
                    role=role,
                    target=target,
                    raw_line=raw_line,
                )
            )
    return expected_lines


def _recipe_definitions(makefile_text: str, target: str) -> list[_RecipeDefinition]:
    lines = makefile_text.splitlines()
    definitions: list[_RecipeDefinition] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        if raw_line.startswith("\t"):
            index += 1
            continue
        target_rule = _target_rule(raw_line)
        if target_rule is None or target not in target_rule.targets:
            index += 1
            continue

        rule_line = index + 1
        body_lines: list[tuple[int, str]] = []
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if not next_line.startswith("\t") and _target_rule(next_line) is not None:
                break
            body_lines.append((index + 1, next_line))
            index += 1

        while body_lines and not body_lines[-1][1].strip():
            body_lines.pop()
        definitions.append(
            _RecipeDefinition(
                line=rule_line,
                rule=target_rule,
                body_lines=body_lines,
            )
        )
    return definitions


def _protected_recipe_invocation(
    line_no: int,
    expected_line: _ProtectedExpectedRecipeLine,
    workflow_order_spec: dict[str, Any],
    protected_target: str,
    violations: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed_events = _recipe_line_events(
        f"\t{expected_line.raw_line}",
        line_no,
        workflow_order_spec,
    )
    if not parsed_events:
        return {
            "line": line_no,
            "target": expected_line.target,
            "role": expected_line.role,
            "raw_args": expected_line.raw_line,
        }
    if len(parsed_events) != 1:
        violations.append(
            {
                "target": protected_target,
                "line": line_no,
                "expected_role": expected_line.role,
                "expected_line": expected_line.raw_line,
                "observed_count": len(parsed_events),
                "reason": "protected_recipe_make_invocation_count_mismatch",
            }
        )

    parsed_event = parsed_events[0]
    if parsed_event["target"] != expected_line.target:
        violations.append(
            {
                "target": protected_target,
                "line": line_no,
                "expected_target": expected_line.target,
                "observed_target": parsed_event["target"],
                "expected_role": expected_line.role,
                "reason": "protected_recipe_target_mismatch",
            }
        )
    if parsed_event["role"] != expected_line.role:
        violations.append(
            {
                "target": protected_target,
                "line": line_no,
                "expected_role": expected_line.role,
                "observed_role": parsed_event["role"],
                "observed_target": parsed_event["target"],
                "reason": "protected_recipe_role_mismatch",
            }
        )
    return {
        "line": line_no,
        "target": parsed_event["target"],
        "role": parsed_event["role"],
        "raw_args": parsed_event["raw_args"],
    }


def _observe_protected_recipe(
    makefile_text: str,
    entry: dict[str, Any],
    workflow_order_spec: dict[str, Any],
) -> _ProtectedRecipeObservation:
    target = str(entry["target"])
    expected_lines = _protected_expected_lines(entry)
    definitions = _recipe_definitions(makefile_text, target)
    violations: list[dict[str, Any]] = []

    if len(definitions) != 1:
        violations.append(
            {
                "target": target,
                "expected_count": 1,
                "observed_count": len(definitions),
                "reason": "protected_recipe_definition_count_mismatch",
            }
        )

    definition = definitions[0] if definitions else None
    if definition is None:
        return _ProtectedRecipeObservation(
            expected_lines=expected_lines,
            invocations=[],
            violations=violations,
        )

    for recipe_definition in definitions:
        if recipe_definition.rule.targets != {target}:
            violations.append(
                {
                    "target": target,
                    "line": recipe_definition.line,
                    "reason": "protected_recipe_multi_target_rule",
                }
            )
        if recipe_definition.rule.is_double_colon:
            violations.append(
                {
                    "target": target,
                    "line": recipe_definition.line,
                    "reason": "protected_recipe_double_colon_rule",
                }
            )
        if recipe_definition.rule.deps:
            violations.append(
                {
                    "target": target,
                    "line": recipe_definition.line,
                    "reason": "protected_recipe_prerequisites_forbidden",
                }
            )
        if recipe_definition.rule.has_inline_recipe:
            violations.append(
                {
                    "target": target,
                    "line": recipe_definition.line,
                    "reason": "protected_recipe_inline_recipe_forbidden",
                }
            )

    body_lines = definition.body_lines
    if len(body_lines) != len(expected_lines):
        violations.append(
            {
                "target": target,
                "expected_count": len(expected_lines),
                "observed_count": len(body_lines),
                "reason": "protected_recipe_line_count_mismatch",
            }
        )

    invocations: list[dict[str, Any]] = []
    for index, expected_line in enumerate(expected_lines):
        if index >= len(body_lines):
            violations.append(
                {
                    "target": target,
                    "expected_role": expected_line.role,
                    "expected_line": expected_line.raw_line,
                    "reason": "protected_recipe_line_missing",
                }
            )
            continue

        line_no, raw_line = body_lines[index]
        expected_physical_line = f"\t{expected_line.raw_line}"
        if raw_line != expected_physical_line:
            violations.append(
                {
                    "target": target,
                    "line": line_no,
                    "expected_role": expected_line.role,
                    "expected_line": expected_line.raw_line,
                    "observed_line": raw_line.strip(),
                    "reason": "protected_recipe_line_mismatch",
                }
            )
            continue
        invocations.append(
            _protected_recipe_invocation(
                line_no,
                expected_line,
                workflow_order_spec,
                target,
                violations,
            )
        )

    for line_no, raw_line in body_lines[len(expected_lines) :]:
        violations.append(
            {
                "target": target,
                "line": line_no,
                "observed_line": raw_line.strip(),
                "reason": "protected_recipe_unexpected_line",
            }
        )

    return _ProtectedRecipeObservation(
        expected_lines=expected_lines,
        invocations=[
            {**invocation, "order": order}
            for order, invocation in enumerate(invocations, start=1)
        ],
        violations=violations,
    )


def _protected_recipe_observations(
    makefile_text: str,
    workflow_order_spec: dict[str, Any],
) -> dict[str, _ProtectedRecipeObservation]:
    return {
        str(entry["target"]): _observe_protected_recipe(
            makefile_text,
            entry,
            workflow_order_spec,
        )
        for entry in _protected_recipe_entries(workflow_order_spec)
    }


def _direct_recipe_invocations(
    makefile_text: str,
    target: str,
    workflow_order_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    active = False
    invocations: list[dict[str, Any]] = []
    current_definition_active = False
    current_definition_has_recipe = False
    current_definition_is_double_colon = False
    current_definition_events: list[dict[str, Any]] = []
    single_colon_recipe_events: list[dict[str, Any]] | None = None
    double_colon_recipe_events: list[dict[str, Any]] = []

    def close_current_definition() -> None:
        nonlocal current_definition_active
        nonlocal current_definition_has_recipe
        nonlocal current_definition_is_double_colon
        nonlocal current_definition_events
        nonlocal single_colon_recipe_events
        if current_definition_active and current_definition_has_recipe:
            if current_definition_is_double_colon:
                double_colon_recipe_events.extend(current_definition_events)
            else:
                single_colon_recipe_events = list(current_definition_events)
        current_definition_active = False
        current_definition_has_recipe = False
        current_definition_is_double_colon = False
        current_definition_events = []

    for line_no, raw_line in enumerate(makefile_text.splitlines(), start=1):
        if raw_line.startswith("\t"):
            if not active:
                continue
            current_definition_has_recipe = True
            current_definition_events.extend(
                _recipe_line_events(
                    raw_line,
                    line_no,
                    workflow_order_spec,
                )
            )
            continue

        target_rule = _target_rule(raw_line)
        if target_rule is None:
            close_current_definition()
            active = False
            continue
        close_current_definition()
        active = target in target_rule.targets
        current_definition_active = active
        current_definition_is_double_colon = target_rule.is_double_colon
        if active and target_rule.has_inline_recipe:
            current_definition_has_recipe = True
            if target_rule.inline_recipe:
                current_definition_events.extend(
                    _recipe_line_events(
                        f"\t{target_rule.inline_recipe}",
                        line_no,
                        workflow_order_spec,
                    )
                )
    close_current_definition()
    selected_events = (
        double_colon_recipe_events
        if double_colon_recipe_events
        else single_colon_recipe_events or []
    )
    for event in selected_events:
        invocations.append({**event, "order": len(invocations) + 1})
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


def _expanded_recipe_invocations(
    makefile_text: str,
    target: str,
    workflow_order_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    active_stack: set[str] = set()

    def visit(active_target: str, path: list[str]) -> None:
        if active_target in active_stack:
            return
        active_stack.add(active_target)
        for invocation in _recipe_invocations(
            makefile_text,
            active_target,
            workflow_order_spec,
        ):
            invocation_target = str(invocation["target"])
            invocation_path = [*path, invocation_target]
            expanded.append(
                {
                    **invocation,
                    "order": len(expanded) + 1,
                    "invocation_path": " -> ".join(invocation_path),
                    "root_target": target,
                }
            )
            visit(invocation_target, invocation_path)
        active_stack.remove(active_target)

    visit(target, [target])
    return expanded


def _invocation_role(
    target: str,
    raw_args: str,
    workflow_order_spec: dict[str, Any],
) -> str:
    for override in _spec_entries(workflow_order_spec, "role_overrides"):
        if _role_override_matches(target, raw_args, override):
            return str(override.get("role", "")).strip() or target
    return target


def _make_arg_assignments(raw_args: str) -> dict[str, str]:
    try:
        tokens = shlex.split(raw_args, posix=True)
    except ValueError:
        tokens = raw_args.split()
    assignments: dict[str, str] = {}
    for token in tokens:
        name, separator, value = token.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        assignments[name] = value
    return assignments


def _role_override_matches(
    target: str,
    raw_args: str,
    override: dict[str, Any],
) -> bool:
    if str(override.get("target", "")).strip() != target:
        return False

    required_assignments = _string_dict(override.get("required_assignments"))
    if required_assignments:
        assignments = _make_arg_assignments(raw_args)
        return all(
            assignments.get(name) == value
            for name, value in required_assignments.items()
        )

    return False


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
            _check_planner_hooks(
                inputs.planner_report,
                invocations[RELEASE_CONVERGE_TARGET],
            ),
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
