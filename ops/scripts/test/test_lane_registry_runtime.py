from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ops.scripts.schema_runtime import load_schema, validate_or_raise

REGISTRY_PATH = Path("ops/test-lane-registry.json")
SCHEMA_PATH = Path("ops/schemas/test-lane-registry.schema.json")


def _non_empty_str(value: object) -> str:
    return str(value).strip()


def _dict_items(items: object) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _require_unique(values: list[str], *, label: str, context: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate {label} in {context}: {duplicates}")


def persistent_lanes(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return _dict_items(registry.get("persistent_lanes", []))


def derived_packs(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return _dict_items(registry.get("derived_packs", []))


def compatibility_layers(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return _dict_items(registry.get("compatibility_layers", []))


def documentation_boundary(registry: dict[str, Any]) -> dict[str, Any]:
    raw = registry.get("documentation_boundary", {})
    return raw if isinstance(raw, dict) else {}


def lane_by_marker(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lanes = persistent_lanes(registry)
    return {_non_empty_str(lane["marker"]): lane for lane in lanes}


def lane_by_ci_tier(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lanes = persistent_lanes(registry)
    return {_non_empty_str(lane["ci_tier"]): lane for lane in lanes}


def lane_by_make_target(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lanes = persistent_lanes(registry)
    return {_non_empty_str(lane["make_target"]): lane for lane in lanes}


def pack_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packs = derived_packs(registry)
    return {_non_empty_str(pack["pack_id"]): pack for pack in packs}


def marker_semantics(registry: dict[str, Any]) -> dict[str, str]:
    return {
        _non_empty_str(lane["marker"]): _non_empty_str(lane["semantics"])
        for lane in persistent_lanes(registry)
    }


def selection_by_make_target(registry: dict[str, Any]) -> dict[str, str]:
    return {
        _non_empty_str(lane["make_target"]): _non_empty_str(lane["selection"]["pytest_mark_expr"])
        for lane in persistent_lanes(registry)
    }


def lane_ci_steps(registry: dict[str, Any], lane_id: str) -> tuple[str, ...]:
    for lane in persistent_lanes(registry):
        if _non_empty_str(lane.get("lane_id")) == lane_id:
            return tuple(_non_empty_str(item) for item in lane.get("ci_steps", []) if _non_empty_str(item))
    raise KeyError(lane_id)


def lane_ci_entrypoint(registry: dict[str, Any], lane_id: str) -> str:
    for lane in persistent_lanes(registry):
        if _non_empty_str(lane.get("lane_id")) == lane_id:
            return _non_empty_str(lane.get("ci_entrypoint"))
    raise KeyError(lane_id)


def authoritative_markers(registry: dict[str, Any]) -> set[str]:
    return set(lane_by_marker(registry))


def authoritative_ci_tiers(registry: dict[str, Any]) -> set[str]:
    return set(lane_by_ci_tier(registry))


def authoritative_make_targets(registry: dict[str, Any]) -> set[str]:
    return set(lane_by_make_target(registry))


def compatibility_names(registry: dict[str, Any], kind: str) -> tuple[str, ...]:
    return tuple(
        _non_empty_str(layer["name"])
        for layer in compatibility_layers(registry)
        if _non_empty_str(layer.get("kind")) == kind
    )


def compatibility_map(registry: dict[str, Any], kind: str) -> dict[str, str]:
    return {
        _non_empty_str(layer["name"]): _non_empty_str(layer["maps_to"])
        for layer in compatibility_layers(registry)
        if _non_empty_str(layer.get("kind")) == kind
    }


def allowed_marker_combinations(registry: dict[str, Any]) -> dict[str, set[str]]:
    return {
        _non_empty_str(lane["marker"]): {
            _non_empty_str(item)
            for item in lane.get("allowed_markers", [])
            if _non_empty_str(item)
        }
        for lane in persistent_lanes(registry)
    }


def forbidden_marker_combinations(registry: dict[str, Any]) -> dict[str, set[str]]:
    return {
        _non_empty_str(lane["marker"]): {
            _non_empty_str(item)
            for item in lane.get("forbidden_markers", [])
            if _non_empty_str(item)
        }
        for lane in persistent_lanes(registry)
    }


def pack_selection(pack: dict[str, Any]) -> dict[str, Any]:
    raw = pack.get("selection", {})
    return raw if isinstance(raw, dict) else {}


def pack_selectors(registry: dict[str, Any], pack_id: str) -> tuple[str, ...]:
    pack = pack_by_id(registry)[pack_id]
    return tuple(_non_empty_str(item) for item in pack_selection(pack).get("selectors", []) if _non_empty_str(item))


def selector_test_file(selector: str) -> str:
    return _non_empty_str(selector).split("::", 1)[0]


def _pytest_mark_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _pytest_mark_name(node.func)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    ):
        return node.attr
    return ""


def _pytestmark_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        marks: set[str] = set()
        for item in node.elts:
            marks.update(_pytestmark_names(item))
        return marks
    mark = _pytest_mark_name(node)
    return {mark} if mark else set()


def _pytestmark_value(statement: ast.stmt) -> ast.AST | None:
    if isinstance(statement, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "pytestmark"
        for target in statement.targets
    ):
        return statement.value
    if (
        isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == "pytestmark"
    ):
        return statement.value
    return None


def module_level_pytest_marks(test_file: Path) -> set[str]:
    if not test_file.is_file():
        return set()
    try:
        module = ast.parse(test_file.read_text(encoding="utf-8"), filename=test_file.as_posix())
    except SyntaxError:
        return set()
    marks: set[str] = set()
    for statement in module.body:
        value = _pytestmark_value(statement)
        if value is not None:
            marks.update(_pytestmark_names(value))
    return marks


def excluded_markers_from_expr(mark_expr: str) -> set[str]:
    expr = _non_empty_str(mark_expr)
    excluded: set[str] = set()
    for mark in ("slow", "integration_heavy", "report_contract", "public"):
        if f"not {mark}" in expr:
            excluded.add(mark)
    return excluded


def pack_effective_selectors(
    registry: dict[str, Any],
    pack_id: str,
    *,
    vault: Path | None = None,
) -> tuple[str, ...]:
    selectors = pack_selectors(registry, pack_id)
    mark_expr = pack_mark_expr(registry, pack_id)
    if not mark_expr:
        return selectors
    excluded_marks = excluded_markers_from_expr(mark_expr)
    if not excluded_marks:
        return selectors
    root = (vault or Path(".")).resolve()
    kept: list[str] = []
    for selector in selectors:
        module_marks = module_level_pytest_marks(root / selector_test_file(selector))
        if module_marks & excluded_marks:
            continue
        kept.append(selector)
    return tuple(kept)


def pack_deselects(registry: dict[str, Any], pack_id: str) -> tuple[str, ...]:
    pack = pack_by_id(registry)[pack_id]
    return tuple(_non_empty_str(item) for item in pack_selection(pack).get("deselects", []) if _non_empty_str(item))


def pack_tests_argument(registry: dict[str, Any], pack_id: str) -> str:
    pack = pack_by_id(registry)[pack_id]
    return _non_empty_str(pack_selection(pack).get("tests_argument"))


def pack_mark_expr(registry: dict[str, Any], pack_id: str) -> str:
    pack = pack_by_id(registry)[pack_id]
    return _non_empty_str(pack_selection(pack).get("pytest_mark_expr"))


def pack_deselection_policy(registry: dict[str, Any], pack_id: str) -> str:
    pack = pack_by_id(registry)[pack_id]
    return _non_empty_str(pack_selection(pack).get("deselection_policy"))


def pack_backing_targets(registry: dict[str, Any], pack_id: str) -> tuple[str, ...]:
    pack = pack_by_id(registry)[pack_id]
    return tuple(_non_empty_str(item) for item in pack.get("backing_targets", []) if _non_empty_str(item))


def pack_documented_entrypoints(registry: dict[str, Any], pack_id: str) -> tuple[str, ...]:
    pack = pack_by_id(registry)[pack_id]
    return tuple(_non_empty_str(item) for item in pack.get("documented_entrypoints", []) if _non_empty_str(item))


def pack_ci_steps(registry: dict[str, Any], pack_id: str) -> tuple[str, ...]:
    pack = pack_by_id(registry)[pack_id]
    return tuple(_non_empty_str(item) for item in pack.get("ci_steps", []) if _non_empty_str(item))


def pack_ci_entrypoint(registry: dict[str, Any], pack_id: str) -> str:
    pack = pack_by_id(registry)[pack_id]
    return _non_empty_str(pack.get("ci_entrypoint"))


def pack_summary_suite(registry: dict[str, Any], pack_id: str) -> dict[str, Any]:
    pack = pack_by_id(registry)[pack_id]
    raw = pack.get("summary_suite", {})
    return raw if isinstance(raw, dict) else {}


def documentation_authority(registry: dict[str, Any]) -> tuple[str, ...]:
    boundary = documentation_boundary(registry)
    return tuple(
        _non_empty_str(item)
        for item in boundary.get("authoritative_documents", [])
        if _non_empty_str(item)
    )


def documentation_out_of_scope(registry: dict[str, Any]) -> tuple[str, ...]:
    boundary = documentation_boundary(registry)
    return tuple(
        _non_empty_str(item)
        for item in boundary.get("out_of_scope_documents", [])
        if _non_empty_str(item)
    )


def _validate_registry_integrity(registry: dict[str, Any]) -> None:
    lanes = persistent_lanes(registry)
    packs = derived_packs(registry)
    layers = compatibility_layers(registry)

    lane_ids = [_non_empty_str(lane.get("lane_id")) for lane in lanes]
    markers = [_non_empty_str(lane.get("marker")) for lane in lanes]
    ci_tiers = [_non_empty_str(lane.get("ci_tier")) for lane in lanes]
    make_targets = [_non_empty_str(lane.get("make_target")) for lane in lanes]
    pack_ids = [_non_empty_str(pack.get("pack_id")) for pack in packs]
    layer_keys = [f"{_non_empty_str(layer.get('kind'))}:{_non_empty_str(layer.get('name'))}" for layer in layers]

    _require_unique(lane_ids, label="lane_id", context="persistent_lanes")
    _require_unique(markers, label="marker", context="persistent_lanes")
    _require_unique(ci_tiers, label="ci_tier", context="persistent_lanes")
    _require_unique(make_targets, label="make_target", context="persistent_lanes")
    _require_unique(pack_ids, label="pack_id", context="derived_packs")
    _require_unique(layer_keys, label="compatibility layer", context="compatibility_layers")

    known_ids = set(lane_ids) | set(pack_ids)
    unknown_maps = sorted(
        f"{_non_empty_str(layer.get('kind'))}:{_non_empty_str(layer.get('name'))}->{_non_empty_str(layer.get('maps_to'))}"
        for layer in layers
        if _non_empty_str(layer.get("maps_to")) not in known_ids
    )
    if unknown_maps:
        raise ValueError(f"compatibility_layers reference unknown ids: {unknown_maps}")

    documented_map = compatibility_map(registry, "documented_entrypoint")
    ci_map = compatibility_map(registry, "ci_tier")
    make_map = compatibility_map(registry, "make_target")

    for lane in lanes:
        lane_id = _non_empty_str(lane.get("lane_id"))
        lane_ci_tier = _non_empty_str(lane.get("ci_tier"))
        lane_make_target = _non_empty_str(lane.get("make_target"))
        if ci_map.get(lane_ci_tier) != lane_id:
            raise ValueError(f"missing or mismatched ci_tier compatibility for persistent lane {lane_id}: {lane_ci_tier}")
        if make_map.get(lane_make_target) != lane_id:
            raise ValueError(
                f"missing or mismatched make_target compatibility for persistent lane {lane_id}: {lane_make_target}"
            )

    for pack in packs:
        pack_id = _non_empty_str(pack.get("pack_id"))
        for target in pack.get("backing_targets", []):
            target_name = _non_empty_str(target)
            if target_name not in make_map:
                raise ValueError(
                    f"missing make_target compatibility for derived pack {pack_id}: {target_name}"
                )
        for entrypoint in pack.get("documented_entrypoints", []):
            entrypoint_name = _non_empty_str(entrypoint)
            if entrypoint_name not in documented_map:
                raise ValueError(
                    f"missing documented_entrypoint compatibility for derived pack {pack_id}: {entrypoint_name}"
                )

    for lane in lanes:
        entrypoint = _non_empty_str(lane.get("ci_entrypoint"))
        if entrypoint and make_map.get(entrypoint) != _non_empty_str(lane.get("lane_id")):
            raise ValueError(
                f"ci_entrypoint for persistent lane {_non_empty_str(lane.get('lane_id'))} must map through make_target compatibility: {entrypoint}"
            )

    for pack in packs:
        entrypoint = _non_empty_str(pack.get("ci_entrypoint"))
        if entrypoint and entrypoint not in make_map:
            raise ValueError(
                f"ci_entrypoint for derived pack {_non_empty_str(pack.get('pack_id'))} must exist in make_target compatibility: {entrypoint}"
            )


def load_registry(vault: Path | None = None) -> dict[str, Any]:
    base = (vault or Path(".")).resolve()
    payload = json.loads((base / REGISTRY_PATH).read_text(encoding="utf-8"))
    schema = load_schema(base / SCHEMA_PATH)
    validate_or_raise(payload, schema, context=(base / REGISTRY_PATH).as_posix())
    _validate_registry_integrity(payload)
    return payload
