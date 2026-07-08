from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.filesystem_runtime import atomic_write_text
from ops.scripts.core.makefile_runtime import load_makefile_text
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.core.workflow_dependency_planner import TARGET_RE, _first_make_target

SPEC_PATH = "ops/policies/release-workflow-order-guard.json"
SPEC_SCHEMA_PATH = "ops/schemas/release-workflow-order-guard-spec.schema.json"


MAKE_RECIPE_RE = re.compile(r"\$\(MAKE\)\s+(?P<args>[^\n;&|]+)")
_DIRECT_PYTHON_PROTECTED_TOKENS: dict[str, tuple[str, ...]] = {
    "release-post-commit-finalizer-snapshot": (
        "$(PYTHON)",
        "-m",
        "ops.scripts.release.release_post_commit_finalizer",
        "--vault",
        "$(VAULT)",
        "--mode",
        "snapshot",
        "--out",
        "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)",
    ),
    "release-post-commit-finalizer-verify": (
        "$(PYTHON)",
        "-m",
        "ops.scripts.release.release_post_commit_finalizer",
        "--vault",
        "$(VAULT)",
        "--mode",
        "verify",
        "--previous",
        "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)",
        "--out",
        "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)",
        "--fail-on-attention",
    ),
    "release-auto-promotion-preflight-authority-write": (
        "$(PYTHON)",
        "-m",
        "ops.scripts.release_auto_promotion_preflight",
        "--vault",
        "$(VAULT)",
        "--phase",
        "preflight",
        "--out",
        "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)",
        "--auto-improve-readiness",
        "$(AUTO_IMPROVE_READINESS_OUT)",
        "--remediation-backlog",
        "$(REMEDIATION_BACKLOG_OUT)",
        "--learning-revalidation",
        "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)",
        "--closeout-summary",
        "$(RELEASE_CLOSEOUT_SUMMARY_OUT)",
        "--evidence-cohort",
        "$(RELEASE_EVIDENCE_COHORT_OUT)",
        "--goal-run-identity",
        "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)",
    ),
    "release-auto-promotion-preseal-authority-write": (
        "$(PYTHON)",
        "-m",
        "ops.scripts.release_auto_promotion_preflight",
        "--vault",
        "$(VAULT)",
        "--phase",
        "preseal",
        "--out",
        "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)",
        "--auto-improve-readiness",
        "$(AUTO_IMPROVE_READINESS_OUT)",
        "--remediation-backlog",
        "$(REMEDIATION_BACKLOG_OUT)",
        "--learning-revalidation",
        "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)",
        "--closeout-summary",
        "$(RELEASE_CLOSEOUT_SUMMARY_OUT)",
        "--evidence-cohort",
        "$(RELEASE_EVIDENCE_COHORT_OUT)",
        "--goal-run-identity",
        "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)",
    ),
}


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


def _split_recipe_args(raw_args: str) -> list[str]:
    try:
        return shlex.split(raw_args, posix=True)
    except ValueError:
        return raw_args.split()


def _protected_recipe_unparseable_line_diagnostic(
    *,
    protected_target: str,
    line_no: int,
    expected_line: _ProtectedExpectedRecipeLine,
    observed_line: str,
) -> dict[str, Any]:
    return {
        "target": protected_target,
        "line": line_no,
        "expected_role": expected_line.role,
        "expected_target": expected_line.target,
        "expected_line": expected_line.raw_line,
        "observed_line": observed_line,
        "reason": "protected_recipe_unparseable_line",
    }


def _direct_python_protected_recipe_event(
    line_no: int,
    expected_line: _ProtectedExpectedRecipeLine,
    raw_args: str,
) -> dict[str, Any] | None:
    expected_tokens = _DIRECT_PYTHON_PROTECTED_TOKENS.get(expected_line.role)
    if expected_tokens is None or expected_line.target != expected_line.role:
        return None
    if tuple(_split_recipe_args(raw_args)) != expected_tokens:
        return None
    return {
        "line": line_no,
        "target": expected_line.target,
        "role": expected_line.role,
        "raw_args": raw_args,
    }


def _required_make_assignments_for_role(
    workflow_order_spec: dict[str, Any],
    expected_line: _ProtectedExpectedRecipeLine,
) -> dict[str, str]:
    for override in _spec_entries(workflow_order_spec, "role_overrides"):
        if (
            str(override.get("role", "")).strip() == expected_line.role
            and str(override.get("target", "")).strip() == expected_line.target
        ):
            return _string_dict(override.get("required_assignments"))
    return {}


def _make_protected_recipe_args_diagnostic(
    *,
    protected_target: str,
    line_no: int,
    expected_line: _ProtectedExpectedRecipeLine,
    parsed_event: dict[str, Any],
    workflow_order_spec: dict[str, Any],
) -> dict[str, Any] | None:
    tokens = _split_recipe_args(str(parsed_event["raw_args"]))
    if not tokens or tokens[0] != expected_line.target:
        return {
            "target": protected_target,
            "line": line_no,
            "expected_role": expected_line.role,
            "expected_target": expected_line.target,
            "observed_raw_args": parsed_event["raw_args"],
            "reason": "protected_recipe_make_args_mismatch",
        }

    assignments: dict[str, str] = {}
    unexpected_tokens: list[str] = []
    for token in tokens[1:]:
        name, separator, value = token.partition("=")
        if separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            assignments[name] = value
        else:
            unexpected_tokens.append(token)

    expected_assignments = _required_make_assignments_for_role(
        workflow_order_spec,
        expected_line,
    )
    if not unexpected_tokens and assignments == expected_assignments:
        return None
    return {
        "target": protected_target,
        "line": line_no,
        "expected_role": expected_line.role,
        "expected_target": expected_line.target,
        "expected_assignments": expected_assignments,
        "observed_assignments": assignments,
        "unexpected_tokens": unexpected_tokens,
        "reason": "protected_recipe_make_args_mismatch",
    }


def _protected_recipe_line_event(
    *,
    protected_target: str,
    line_no: int,
    expected_line: _ProtectedExpectedRecipeLine,
    observed_line: str,
    workflow_order_spec: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    direct_event = _direct_python_protected_recipe_event(
        line_no,
        expected_line,
        observed_line,
    )
    if direct_event is not None:
        return direct_event, None

    make_prefix = "$(MAKE) "
    if not observed_line.startswith(make_prefix):
        return None, _protected_recipe_unparseable_line_diagnostic(
            protected_target=protected_target,
            line_no=line_no,
            expected_line=expected_line,
            observed_line=observed_line,
        )

    raw_args = observed_line[len(make_prefix) :].strip()
    tokens = _split_recipe_args(raw_args)
    if not tokens:
        return None, _protected_recipe_unparseable_line_diagnostic(
            protected_target=protected_target,
            line_no=line_no,
            expected_line=expected_line,
            observed_line=observed_line,
        )

    parsed_event = {
        "line": line_no,
        "target": tokens[0],
        "role": _invocation_role(tokens[0], raw_args, workflow_order_spec),
        "raw_args": raw_args,
    }
    if parsed_event["target"] != expected_line.target:
        return None, {
            "target": protected_target,
            "line": line_no,
            "expected_target": expected_line.target,
            "observed_target": parsed_event["target"],
            "expected_role": expected_line.role,
            "reason": "protected_recipe_target_mismatch",
        }
    if parsed_event["role"] != expected_line.role:
        return None, {
            "target": protected_target,
            "line": line_no,
            "expected_role": expected_line.role,
            "observed_role": parsed_event["role"],
            "observed_target": parsed_event["target"],
            "reason": "protected_recipe_role_mismatch",
        }
    make_args_diagnostic = _make_protected_recipe_args_diagnostic(
        protected_target=protected_target,
        line_no=line_no,
        expected_line=expected_line,
        parsed_event=parsed_event,
        workflow_order_spec=workflow_order_spec,
    )
    if make_args_diagnostic is not None:
        return None, make_args_diagnostic
    return parsed_event, None


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
    parsed_event, diagnostic = _protected_recipe_line_event(
        protected_target=protected_target,
        line_no=line_no,
        expected_line=expected_line,
        observed_line=expected_line.raw_line,
        workflow_order_spec=workflow_order_spec,
    )
    if diagnostic is not None:
        violations.append(diagnostic)
    if parsed_event is None:
        return {
            "line": line_no,
            "target": expected_line.target,
            "role": expected_line.role,
            "raw_args": expected_line.raw_line,
        }
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


def _protected_recipe_resnapshot_lines(
    makefile_text: str,
    entry: dict[str, Any],
    workflow_order_spec: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    target = str(entry.get("target", "")).strip()
    expected_lines = _protected_expected_lines(entry)
    definitions = _recipe_definitions(makefile_text, target)
    diagnostics: list[dict[str, Any]] = []

    if len(definitions) != 1:
        diagnostics.append(
            {
                "target": target,
                "expected_count": 1,
                "observed_count": len(definitions),
                "reason": "protected_recipe_definition_count_mismatch",
            }
        )
        return [], diagnostics

    definition = definitions[0]
    if definition.rule.targets != {target}:
        diagnostics.append(
            {
                "target": target,
                "line": definition.line,
                "reason": "protected_recipe_multi_target_rule",
            }
        )
    if definition.rule.is_double_colon:
        diagnostics.append(
            {
                "target": target,
                "line": definition.line,
                "reason": "protected_recipe_double_colon_rule",
            }
        )
    if definition.rule.deps:
        diagnostics.append(
            {
                "target": target,
                "line": definition.line,
                "reason": "protected_recipe_prerequisites_forbidden",
            }
        )
    if definition.rule.has_inline_recipe:
        diagnostics.append(
            {
                "target": target,
                "line": definition.line,
                "reason": "protected_recipe_inline_recipe_forbidden",
            }
        )

    body_lines = definition.body_lines
    if len(body_lines) != len(expected_lines):
        diagnostics.append(
            {
                "target": target,
                "expected_count": len(expected_lines),
                "observed_count": len(body_lines),
                "reason": "protected_recipe_line_count_mismatch",
            }
        )

    observed_lines: list[str] = []
    for index, (line_no, raw_line) in enumerate(body_lines):
        if not raw_line.startswith("\t") or not raw_line.strip():
            diagnostics.append(
                {
                    "target": target,
                    "line": line_no,
                    "observed_line": raw_line.strip(),
                    "reason": "protected_recipe_non_recipe_body_line",
                }
            )
            continue
        observed_line = raw_line[1:].strip()
        observed_lines.append(observed_line)
        if index >= len(expected_lines):
            continue
        expected_line = expected_lines[index]
        _parsed_event, diagnostic = _protected_recipe_line_event(
            protected_target=target,
            line_no=line_no,
            expected_line=expected_line,
            observed_line=observed_line,
            workflow_order_spec=workflow_order_spec,
        )
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return observed_lines, diagnostics


def _stable_json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _workflow_order_spec_raw_line_candidate(
    vault: Path,
    *,
    spec_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[dict[str, Any]], list[dict[str, Any]]]:
    workflow_order_spec, resolved_spec_path = _load_workflow_order_spec(vault, spec_path)
    makefile_text, _makefile_sources = load_makefile_text(vault)
    candidate = json.loads(json.dumps(workflow_order_spec))
    diagnostics: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []

    for recipe_index, entry in enumerate(_protected_recipe_entries(candidate)):
        observed_lines, entry_diagnostics = _protected_recipe_resnapshot_lines(
            makefile_text,
            entry,
            candidate,
        )
        diagnostics.extend(entry_diagnostics)
        if entry_diagnostics:
            continue
        expected_line_entries = [
            line_entry
            for line_entry in entry.get("expected_lines", [])
            if isinstance(line_entry, dict)
        ]
        for line_index, (line_entry, observed_line) in enumerate(
            zip(expected_line_entries, observed_lines, strict=True)
        ):
            current_raw_line = str(line_entry.get("raw_line", "")).strip()
            if current_raw_line == observed_line:
                continue
            line_entry["raw_line"] = observed_line
            updates.append(
                {
                    "target": entry.get("target"),
                    "recipe_index": recipe_index,
                    "line_index": line_index,
                    "role": line_entry.get("role"),
                    "old_raw_line": current_raw_line,
                    "new_raw_line": observed_line,
                    "reason": "protected_recipe_raw_line_drift",
                }
            )
    return workflow_order_spec, candidate, resolved_spec_path, diagnostics, updates


def check_workflow_order_spec_raw_lines(
    vault: Path,
    *,
    spec_path: str | None = None,
) -> list[dict[str, Any]]:
    original, candidate, _resolved_spec_path, diagnostics, updates = (
        _workflow_order_spec_raw_line_candidate(vault, spec_path=spec_path)
    )
    if diagnostics:
        return diagnostics
    if original != candidate:
        return updates
    return []


def write_workflow_order_spec_raw_lines(
    vault: Path,
    *,
    spec_path: str | None = None,
) -> Path:
    _original, candidate, resolved_spec_path, diagnostics, _updates = (
        _workflow_order_spec_raw_line_candidate(vault, spec_path=spec_path)
    )
    if diagnostics:
        raise ValueError(
            "release workflow order guard spec raw lines could not be resnapshotted: "
            + json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
        )
    atomic_write_text(resolved_spec_path, _stable_json_text(candidate))
    return resolved_spec_path


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
    assignments: dict[str, str] = {}
    for token in _split_recipe_args(raw_args):
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
