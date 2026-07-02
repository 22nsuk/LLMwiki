"""Anti-slop admission checks for lifecycle policy and operator inventory surfaces."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    MAKE_TARGET_INVENTORY_OPERATOR_SCHEMA_PATH,
    SCRIPT_LIFECYCLE_POLICY_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema

OPERATOR_INVENTORY_PATH = "ops/make-target-inventory-operator.json"
SCRIPT_LIFECYCLE_POLICY_PATH = "ops/script-lifecycle-policy.json"
CLI_SURFACE_INVENTORY_SURFACE = "ops/scripts#cli-surface-inventory"
CALENDAR_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_calendar_date(value: object) -> dt.date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return dt.date.fromisoformat(text)


def _non_empty(value: object) -> str:
    return str(value or "").strip()


def _path_from_canonical_module(canonical_module: str) -> str:
    module = _non_empty(canonical_module)
    if not module.startswith("ops.scripts."):
        return ""
    return f"{module.replace('.', '/')}.py"


def _violation(surface: str, field: str, message: str) -> dict[str, str]:
    return {"surface": surface, "field": field, "message": message}


def _expired_remove_after(
    *,
    surface: str,
    remove_after: object,
    today: dt.date,
) -> dict[str, str] | None:
    deadline = _parse_calendar_date(remove_after)
    if deadline is None or deadline >= today:
        return None
    return _violation(
        surface,
        "remove_after",
        f"remove_after {deadline.isoformat()} is before {today.isoformat()}",
    )


def validate_operator_inventory_admission(
    payload: dict[str, Any],
    *,
    makefile_targets: set[str],
    today: dt.date,
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    entries = payload.get("operator_entrypoints", [])
    if not isinstance(entries, list):
        return [_violation(OPERATOR_INVENTORY_PATH, "operator_entrypoints", "must be an array")]

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            violations.append(
                _violation(
                    OPERATOR_INVENTORY_PATH,
                    f"operator_entrypoints[{index}]",
                    "entry must be an object",
                )
            )
            continue
        target = _non_empty(entry.get("target"))
        surface = f"{OPERATOR_INVENTORY_PATH}#{target or index}"
        if not target:
            violations.append(_violation(surface, "target", "target is required"))
            continue
        if not _non_empty(entry.get("purpose")):
            violations.append(_violation(surface, "purpose", "purpose is required"))
        if not _non_empty(entry.get("replacement")):
            violations.append(_violation(surface, "replacement", "replacement is required"))
        if target not in makefile_targets:
            violations.append(
                _violation(
                    surface,
                    "target",
                    f"target `{target}` is not declared in the Make inventory",
                )
            )
        expired = _expired_remove_after(
            surface=surface,
            remove_after=entry.get("remove_after"),
            today=today,
        )
        if expired is not None:
            violations.append(expired)
    return violations


def validate_script_lifecycle_admission(
    payload: dict[str, Any],
    *,
    today: dt.date,
    vault: Path | None = None,
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    modules = payload.get("modules", [])
    if not isinstance(modules, list):
        return [_violation(SCRIPT_LIFECYCLE_POLICY_PATH, "modules", "must be an array")]

    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            violations.append(
                _violation(
                    SCRIPT_LIFECYCLE_POLICY_PATH,
                    f"modules[{index}]",
                    "module must be an object",
                )
            )
            continue
        canonical = _non_empty(module.get("canonical_module")) or f"modules[{index}]"
        surface = f"{SCRIPT_LIFECYCLE_POLICY_PATH}#{canonical}"
        derived_path = _path_from_canonical_module(canonical)
        stored_path = _non_empty(module.get("path"))
        if stored_path and stored_path != derived_path:
            violations.append(
                _violation(
                    surface,
                    "path",
                    f"path `{stored_path}` does not match canonical module path `{derived_path}`",
                )
            )
        if vault is not None and derived_path and not (vault / derived_path).is_file():
            violations.append(
                _violation(
                    surface,
                    "canonical_module",
                    f"canonical module path `{derived_path}` does not exist",
                )
            )
        if not _non_empty(module.get("rationale")):
            violations.append(_violation(surface, "rationale", "rationale is required"))
        if not _non_empty(module.get("replacement")) and module.get("lifecycle") != "public_cli":
            violations.append(_violation(surface, "replacement", "replacement is required"))
        if bool(module.get("removal_ready")) and _parse_calendar_date(module.get("remove_after")) is None:
            violations.append(
                _violation(
                    surface,
                    "remove_after",
                    "remove_after is required when removal_ready is true",
                )
            )
        expired = _expired_remove_after(
            surface=surface,
            remove_after=module.get("remove_after"),
            today=today,
        )
        if expired is not None:
            violations.append(expired)
    return violations


def _cli_surface_inventory_report(
    vault: Path,
    *,
    context: RuntimeContext,
) -> dict[str, Any]:
    from ops.scripts.core.cli_surface_inventory import build_report

    return build_report(vault, context=context)


def _cli_surface_inventory_violations(report: dict[str, Any]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for module in report.get("unclassified_modules", []):
        module_name = _non_empty(module)
        if not module_name:
            continue
        violations.append(
            _violation(
                f"{SCRIPT_LIFECYCLE_POLICY_PATH}#{module_name}",
                "canonical_module",
                "runnable script surface is missing lifecycle policy classification",
            )
        )
    for module in report.get("unresolved_modules", []):
        module_name = _non_empty(module)
        if not module_name:
            continue
        violations.append(
            _violation(
                f"{CLI_SURFACE_INVENTORY_SURFACE}#{module_name}",
                "module_path",
                "runnable script surface could not resolve to an ops/scripts file",
            )
        )
    return violations


def evaluate_anti_slop_admission(
    vault: Path,
    *,
    makefile_targets: set[str],
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    today = runtime_context.today()
    violations: list[dict[str, str]] = []
    cli_surface_inventory = _cli_surface_inventory_report(
        vault.resolve(),
        context=runtime_context,
    )
    violations.extend(_cli_surface_inventory_violations(cli_surface_inventory))

    lifecycle_path = vault / SCRIPT_LIFECYCLE_POLICY_PATH
    lifecycle_payload = _read_json_object(lifecycle_path)
    lifecycle_schema_errors: list[str] = []
    if lifecycle_path.is_file():
        lifecycle_schema_errors = validate_with_schema(
            lifecycle_payload,
            load_schema(vault / SCRIPT_LIFECYCLE_POLICY_SCHEMA_PATH),
        )
        violations.extend(
            _violation(SCRIPT_LIFECYCLE_POLICY_PATH, "$schema", error)
            for error in lifecycle_schema_errors
        )
        violations.extend(
            validate_script_lifecycle_admission(
                lifecycle_payload,
                today=today,
                vault=vault.resolve(),
            )
        )

    operator_path = vault / OPERATOR_INVENTORY_PATH
    operator_payload = _read_json_object(operator_path)
    operator_schema_errors: list[str] = []
    if operator_path.is_file():
        operator_schema_errors = validate_with_schema(
            operator_payload,
            load_schema(vault / MAKE_TARGET_INVENTORY_OPERATOR_SCHEMA_PATH),
        )
        violations.extend(
            _violation(OPERATOR_INVENTORY_PATH, "$schema", error)
            for error in operator_schema_errors
        )
        violations.extend(
            validate_operator_inventory_admission(
                operator_payload,
                makefile_targets=makefile_targets,
                today=today,
            )
        )

    return {
        "status": "fail" if violations else "pass",
        "checked_at": runtime_context.isoformat_z(),
        "today": today.isoformat(),
        "violations": violations,
        "operator_inventory": {
            "path": OPERATOR_INVENTORY_PATH,
            "present": operator_path.is_file(),
            "schema_error_count": len(operator_schema_errors),
        },
        "script_lifecycle": {
            "path": SCRIPT_LIFECYCLE_POLICY_PATH,
            "present": lifecycle_path.is_file(),
            "schema_error_count": len(lifecycle_schema_errors),
        },
        "cli_surface_inventory": {
            "status": cli_surface_inventory.get("status", "fail"),
            "module_count": int(cli_surface_inventory.get("summary", {}).get("module_count", 0)),
            "unclassified_module_count": int(
                cli_surface_inventory.get("summary", {}).get("unclassified_module_count", 0)
            ),
            "unresolved_module_count": int(
                cli_surface_inventory.get("summary", {}).get("unresolved_module_count", 0)
            ),
        },
    }
