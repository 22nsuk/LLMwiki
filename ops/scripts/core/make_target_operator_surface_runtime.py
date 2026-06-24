from __future__ import annotations

from typing import Any

INTERNAL_TARGET_PREFIX = "_internal-"


def is_internal_make_target(name: str) -> bool:
    return name.startswith(INTERNAL_TARGET_PREFIX)


def internal_make_targets(target_names: set[str] | list[str]) -> list[str]:
    return sorted(name for name in target_names if is_internal_make_target(name))


def validate_operator_inventory_surface(
    operator_inventory: dict[str, Any],
    *,
    makefile_targets: set[str],
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    entries = operator_inventory.get("operator_entrypoints", [])
    if not isinstance(entries, list):
        return violations
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("target", "")).strip()
        if is_internal_make_target(target):
            violations.append(
                {
                    "path": "ops/make-target-inventory-operator.json",
                    "field": f"operator_entrypoints[{index}].target",
                    "message": (
                        f"operator inventory must not list internal target {target!r}; "
                        "use the public wrapper target instead"
                    ),
                }
            )
        if target and target not in makefile_targets:
            violations.append(
                {
                    "path": "ops/make-target-inventory-operator.json",
                    "field": f"operator_entrypoints[{index}].target",
                    "message": f"operator target {target!r} is missing from Makefile inventory",
                }
            )
    return violations
