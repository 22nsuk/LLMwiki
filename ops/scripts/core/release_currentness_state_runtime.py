from __future__ import annotations

from typing import Any


def currentness_field(payload: dict[str, Any], field: str) -> str:
    currentness = payload.get("currentness")
    if not isinstance(currentness, dict):
        return ""
    return str(currentness.get(field, "")).strip()


def live_rerun_state(
    component: dict[str, Any], *, current_fingerprint: str
) -> dict[str, str]:
    component_fingerprint = str(component.get("source_tree_fingerprint", "")).strip()
    currentness_status = str(component.get("currentness_status", "")).strip()
    if not component_fingerprint:
        return {
            "status": "not_run",
            "reason": "component has no source_tree_fingerprint",
        }
    if component_fingerprint != current_fingerprint:
        return {
            "status": "not_run",
            "reason": "component fingerprint differs from current source tree",
        }
    if currentness_status != "current":
        return {
            "status": "not_run",
            "reason": f"component currentness_status={currentness_status or 'unknown'}",
        }
    if bool(component.get("ready")):
        return {
            "status": "pass",
            "reason": "checked-in component matches current source tree",
        }
    return {
        "status": "fail",
        "reason": "checked-in component matches current source tree but is not ready",
    }


def components_match_current_source_tree(
    components: list[dict[str, Any]],
    *,
    current_source_tree_fingerprint: str,
) -> bool:
    if not components:
        return False
    for component in components:
        if component.get("load_status") != "ok":
            return False
        if str(component.get("source_tree_fingerprint", "")).strip() != current_source_tree_fingerprint:
            return False
        if str(component.get("currentness_status", "")).strip() != "current":
            return False
    return True
