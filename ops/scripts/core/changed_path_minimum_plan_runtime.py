from __future__ import annotations

import fnmatch
import json
import re
import shlex
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import load_optional_json_object
from ops.scripts.core.derived_surfaces import (
    MANIFEST_PATH as DERIVED_SURFACES_MANIFEST_PATH,
    currentness_output_paths as derived_surface_currentness_output_paths,
    currentness_path_patterns as derived_surface_currentness_path_patterns,
    load_manifest as load_derived_surfaces_manifest,
)

DEFAULT_TEST_LANE_REGISTRY = "ops/test-lane-registry.json"
ENV_ASSIGNMENT_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
UNSUPPORTED_COMMAND_TOKENS = frozenset({"&&", "||", ";", "|", ">", ">>", "<"})

__all__ = [
    "build_changed_path_minimum_plan",
    "derive_surface_currentness",
    "load_test_lane_registry",
]


def load_test_lane_registry(vault: Path) -> dict[str, Any]:
    payload = load_optional_json_object(vault / DEFAULT_TEST_LANE_REGISTRY)
    return payload if isinstance(payload, dict) else {}


def derive_surface_currentness(vault: Path) -> dict[str, Any]:
    manifest_path = vault / DERIVED_SURFACES_MANIFEST_PATH
    if not manifest_path.exists():
        return {
            "status": "skipped",
            "path": DERIVED_SURFACES_MANIFEST_PATH,
            "message": "manifest not found",
            "paths": [],
            "output_paths": [],
        }
    try:
        manifest = load_derived_surfaces_manifest(vault)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "path": DERIVED_SURFACES_MANIFEST_PATH,
            "message": f"{exc.__class__.__name__}: {exc}",
            "paths": [],
            "output_paths": [],
        }
    return {
        "status": "pass",
        "path": DERIVED_SURFACES_MANIFEST_PATH,
        "message": "",
        "paths": derived_surface_currentness_path_patterns(manifest),
        "output_paths": derived_surface_currentness_output_paths(manifest),
    }


def build_changed_path_minimum_plan(
    changed_paths: list[str],
    registry: dict[str, Any],
    *,
    changed_files_manifest: str | None = None,
    derived_surface_currentness_paths: list[str] | None = None,
    derived_surface_currentness_status: str = "skipped",
) -> dict[str, Any]:
    config = _changed_path_minimum_rules(registry)
    derived_rules = _derived_surface_currentness_rules(
        derived_surface_currentness_paths or []
    )
    rules = [item for item in config.get("rules", []) if isinstance(item, dict)]
    command_duration_seconds = _command_duration_seconds(config)
    default_rule = config.get("unknown_path")
    if not isinstance(default_rule, dict):
        default_rule = {
            "commands": ["make static", "make test-fast"],
            "reason": "Unknown paths use the conservative advisory minimum lane.",
            "coverage_class": "conservative",
            "static_required": True,
            "duration_seconds": 300,
        }
    path_recommendations: list[dict[str, Any]] = []
    recommendation_duration_inputs: list[dict[str, Any]] = []
    unknown_paths: list[str] = []
    for path in changed_paths:
        matched_rule = _matching_changed_path_rule(path, rules)
        derived_rule = _matching_changed_path_rule(path, derived_rules)
        rule = _combined_changed_path_rule(matched_rule, derived_rule) or default_rule
        if matched_rule is None and derived_rule is None:
            unknown_paths.append(path)
        recommendation, duration_input = _changed_path_recommendation(
            path,
            rule,
            changed_files_manifest,
        )
        path_recommendations.append(recommendation)
        recommendation_duration_inputs.append(duration_input)
    selected_commands = _dedupe_preserve_order(
        [
            command
            for recommendation in path_recommendations
            for command in recommendation["commands"]
        ]
    )
    selected_command_specs = _selected_command_specs(
        selected_commands,
        recommendation_duration_inputs,
    )
    estimated_duration_seconds = _estimate_selected_command_duration_seconds(
        selected_commands,
        recommendation_duration_inputs,
        command_duration_seconds,
    )
    selected_command_duration_seconds = _selected_command_duration_seconds(
        selected_commands,
        recommendation_duration_inputs,
        command_duration_seconds,
    )
    duration_budget_seconds = int(config.get("default_duration_budget_seconds", 0) or 0)
    if not path_recommendations:
        budget_status = "not_applicable"
        coverage_class = "none"
    else:
        budget_status = (
            "unknown"
            if duration_budget_seconds <= 0
            else "within_budget"
            if estimated_duration_seconds <= duration_budget_seconds
            else "over_budget"
        )
        coverage_classes = sorted(
            {str(item["coverage_class"]) for item in path_recommendations}
        )
        coverage_class = coverage_classes[0] if len(coverage_classes) == 1 else "mixed"
    status = (
        "attention"
        if unknown_paths or derived_surface_currentness_status == "failed"
        else "pass"
    )
    return {
        "status": status,
        "advisory": True,
        "registry_path": DEFAULT_TEST_LANE_REGISTRY,
        "selected_commands": selected_commands,
        "selected_command_specs": selected_command_specs,
        "final_checkpoint_required": True,
        "final_checkpoint_commands": _changed_path_final_checkpoint_commands(config),
        "release_proof_replacement": False,
        "coverage_class": coverage_class,
        "static_required": any(item["static_required"] for item in path_recommendations),
        "budget_status": budget_status,
        "duration_budget_seconds": duration_budget_seconds,
        "estimated_duration_seconds": estimated_duration_seconds,
        "command_duration_seconds": selected_command_duration_seconds,
        "unknown_paths": unknown_paths,
        "path_recommendations": path_recommendations,
    }


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _format_command(
    command: str,
    path: str,
    *,
    changed_files_manifest: str | None = None,
) -> str:
    manifest = changed_files_manifest or "<changed-files-manifest>"
    return command.replace("{path}", path).replace("{changed_files_manifest}", manifest)


def _command_spec(
    command: str,
    path: str,
    *,
    changed_files_manifest: str | None = None,
) -> dict[str, Any]:
    tokens = shlex.split(command, posix=True)
    if not tokens or any(token in UNSUPPORTED_COMMAND_TOKENS for token in tokens):
        raise ValueError(f"unsupported changed-path command template: {command!r}")

    manifest = changed_files_manifest or "<changed-files-manifest>"
    formatted_tokens = [
        token.replace("{path}", path).replace("{changed_files_manifest}", manifest)
        for token in tokens
    ]
    environment: dict[str, str] = {}
    command_index = 0
    for token in formatted_tokens:
        match = ENV_ASSIGNMENT_RE.fullmatch(token)
        if match is None:
            break
        environment[match.group("name")] = match.group("value")
        command_index += 1
    argv = formatted_tokens[command_index:]
    if not argv:
        raise ValueError(f"changed-path command has no executable: {command!r}")
    return {
        "command": _format_command(
            command,
            path,
            changed_files_manifest=changed_files_manifest,
        ),
        "argv": argv,
        "env": environment,
    }


def _changed_path_minimum_rules(registry: dict[str, Any]) -> dict[str, Any]:
    plan = registry.get("changed_path_minimums")
    return plan if isinstance(plan, dict) else {}


def _derived_surface_currentness_rules(paths: list[str]) -> list[dict[str, Any]]:
    if not paths:
        return []
    return [
        {
            "rule_id": "derived_surface_currentness",
            "path_patterns": paths,
            "commands": ["make sync-derived-check"],
            "reason": (
                "Derived surface output changes should verify the manifest-owned "
                "source-derived aggregate is current."
            ),
            "coverage_class": "generated_artifact_currentness",
            "static_required": False,
            "duration_seconds": 120,
        }
    ]


def _command_duration_seconds(config: dict[str, Any]) -> dict[str, int]:
    raw_durations = config.get("command_duration_seconds")
    if not isinstance(raw_durations, dict):
        return {}
    durations: dict[str, int] = {}
    for command, duration in raw_durations.items():
        command_text = str(command).strip()
        if not command_text:
            continue
        try:
            durations[command_text] = max(0, int(duration))
        except (TypeError, ValueError):
            continue
    return durations


def _changed_path_final_checkpoint_commands(config: dict[str, Any]) -> list[str]:
    commands = [
        str(command).strip()
        for command in config.get("final_checkpoint_commands", [])
        if str(command).strip()
    ]
    return commands or ["make release-run-ready"]


def _estimate_selected_command_duration_seconds(
    selected_commands: list[str],
    recommendation_duration_inputs: list[dict[str, Any]],
    command_duration_seconds: dict[str, int],
) -> int:
    selected_estimates = _selected_command_duration_seconds(
        selected_commands,
        recommendation_duration_inputs,
        command_duration_seconds,
    )
    if selected_estimates:
        return sum(selected_estimates.values())

    unique_recommendation_durations: dict[tuple[str, ...], int] = {}
    for item in recommendation_duration_inputs:
        command_key = tuple(str(command) for command in item["commands"])
        if not command_key:
            continue
        unique_recommendation_durations[command_key] = max(
            unique_recommendation_durations.get(command_key, 0),
            int(item["duration_seconds"]),
        )
    return sum(unique_recommendation_durations.values())


def _selected_command_duration_seconds(
    selected_commands: list[str],
    recommendation_duration_inputs: list[dict[str, Any]],
    command_duration_seconds: dict[str, int],
) -> dict[str, int]:
    if not command_duration_seconds:
        return {}
    selected_estimates: dict[str, int] = dict.fromkeys(selected_commands, 0)
    missing_estimates: set[str] = set(selected_commands)
    for item in recommendation_duration_inputs:
        commands = item["commands"]
        templates = item["command_templates"]
        for command, template in zip(commands, templates, strict=False):
            template_text = str(template)
            command_text = str(command)
            duration = command_duration_seconds.get(template_text)
            if duration is None:
                duration = command_duration_seconds.get(command_text)
            if duration is None:
                continue
            missing_estimates.discard(command_text)
            selected_estimates[command_text] = max(
                selected_estimates.get(command_text, 0),
                duration,
            )
    if missing_estimates or not any(selected_estimates.values()):
        return {}
    return selected_estimates


def _matching_changed_path_rule(
    path: str,
    rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return next(
        (
            rule
            for rule in rules
            if any(
                fnmatch.fnmatch(path, str(pattern))
                for pattern in rule.get("path_patterns", [])
            )
        ),
        None,
    )


def _changed_path_recommendation(
    path: str,
    rule: dict[str, Any],
    changed_files_manifest: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    command_templates = [
        str(command) for command in rule.get("commands", []) if str(command).strip()
    ]
    commands = [
        _format_command(
            command,
            path,
            changed_files_manifest=changed_files_manifest,
        )
        for command in command_templates
    ]
    command_specs = [
        _command_spec(
            command,
            path,
            changed_files_manifest=changed_files_manifest,
        )
        for command in command_templates
    ]
    duration_seconds = int(rule.get("duration_seconds", 0) or 0)
    return (
        {
            "path": path,
            "matched_rule_id": str(rule.get("rule_id", "unknown_path")),
            "commands": commands,
            "reason": str(rule.get("reason", "")).strip(),
            "coverage_class": str(rule.get("coverage_class", "conservative")).strip(),
            "static_required": bool(rule.get("static_required", True)),
            "duration_seconds": duration_seconds,
        },
        {
            "commands": commands,
            "command_specs": command_specs,
            "command_templates": command_templates,
            "duration_seconds": duration_seconds,
        },
    )


def _selected_command_specs(
    selected_commands: list[str],
    recommendation_duration_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    specs_by_command = {
        str(spec["command"]): spec
        for item in recommendation_duration_inputs
        for spec in item["command_specs"]
    }
    return [specs_by_command[command] for command in selected_commands]


def _combined_changed_path_rule(
    matched_rule: dict[str, Any] | None,
    derived_rule: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if matched_rule is None:
        return derived_rule
    if derived_rule is None:
        return matched_rule
    matched_rule_id = str(matched_rule.get("rule_id", "")).strip()
    derived_rule_id = str(derived_rule.get("rule_id", "")).strip()
    commands = _dedupe_preserve_order(
        [
            *[
                str(command)
                for command in matched_rule.get("commands", [])
                if str(command).strip()
            ],
            *[
                str(command)
                for command in derived_rule.get("commands", [])
                if str(command).strip()
            ],
        ]
    )
    return {
        "rule_id": "+".join(
            rule_id for rule_id in (matched_rule_id, derived_rule_id) if rule_id
        ),
        "commands": commands,
        "reason": " ".join(
            reason
            for reason in (
                str(matched_rule.get("reason", "")).strip(),
                str(derived_rule.get("reason", "")).strip(),
            )
            if reason
        ),
        "coverage_class": str(
            matched_rule.get("coverage_class", "conservative")
        ).strip(),
        "static_required": bool(
            matched_rule.get("static_required", True)
            or derived_rule.get("static_required", True)
        ),
        "duration_seconds": int(matched_rule.get("duration_seconds", 0) or 0)
        + int(derived_rule.get("duration_seconds", 0) or 0),
    }
