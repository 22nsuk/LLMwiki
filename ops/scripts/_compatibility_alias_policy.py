from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FlatReexportTarget:
    alias_name: str
    canonical_module: str
    path: Path
    relative_path: str
    retained_reason: str
    removal_ready: bool


LIFECYCLE_RETAINED_REASONS = {
    "public_cli": "public_cli_import_contract",
    "make_only": "make_only_legacy_module_compatibility",
    "report_generator": "report_generator_legacy_module_compatibility",
    "helper": "helper_legacy_module_compatibility",
    "test_only": "test_only_legacy_module_compatibility",
    "legacy_delete": "legacy_delete_pending_removal",
}


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _script_vault_root(script_root: Path) -> Path:
    return script_root.resolve().parents[1]


def _available_flat_targets(script_root: Path) -> dict[str, FlatReexportTarget]:
    vault = _script_vault_root(script_root)
    targets: dict[str, FlatReexportTarget] = {}
    for path in sorted(script_root.glob("*/*.py")):
        if path.name.startswith("_"):
            continue
        relative_path = path.relative_to(vault).as_posix()
        canonical_module = relative_path.removesuffix(".py").replace("/", ".")
        alias_name = f"ops.scripts.{path.stem}"
        targets[canonical_module] = FlatReexportTarget(
            alias_name=alias_name,
            canonical_module=canonical_module,
            path=path,
            relative_path=relative_path,
            retained_reason="unclassified_flat_reexport",
            removal_ready=False,
        )
    return targets


def _lifecycle_retained_reason(module: dict[str, Any]) -> str:
    if bool(module.get("removal_ready")):
        return "lifecycle_policy_removal_ready"
    install_state = str(module.get("install_state", ""))
    if install_state == "transitional_installed":
        return "transitional_installed_import_contract"
    lifecycle = str(module.get("lifecycle", ""))
    return LIFECYCLE_RETAINED_REASONS.get(lifecycle, "lifecycle_policy_compatibility")


def discover_flat_reexport_targets(script_root: Path) -> dict[str, FlatReexportTarget]:
    """Return policy-backed flat import aliases that remain part of the contract."""
    resolved_script_root = script_root.resolve()
    vault = _script_vault_root(resolved_script_root)
    available_by_module = _available_flat_targets(resolved_script_root)
    retained_by_stem: dict[str, FlatReexportTarget] = {}

    lifecycle_policy = _read_json_object(vault / "ops" / "script-lifecycle-policy.json")
    for module in lifecycle_policy.get("modules", []):
        if not isinstance(module, dict):
            continue
        canonical_module = str(module.get("canonical_module", ""))
        target = available_by_module.get(canonical_module)
        if target is None:
            continue
        retained_by_stem[Path(target.relative_path).stem] = FlatReexportTarget(
            alias_name=target.alias_name,
            canonical_module=target.canonical_module,
            path=target.path,
            relative_path=target.relative_path,
            retained_reason=_lifecycle_retained_reason(module),
            removal_ready=bool(module.get("removal_ready")),
        )

    module_surfaces = _read_json_object(vault / "ops" / "script-module-surfaces.json")
    for surface in module_surfaces.get("stable_import_surfaces", []):
        if not isinstance(surface, dict) or surface.get("role") != "compatibility_facade":
            continue
        relative_path = str(surface.get("path", ""))
        canonical_module = relative_path.removesuffix(".py").replace("/", ".")
        target = available_by_module.get(canonical_module)
        if target is None:
            continue
        retained_by_stem.setdefault(
            Path(target.relative_path).stem,
            FlatReexportTarget(
                alias_name=target.alias_name,
                canonical_module=target.canonical_module,
                path=target.path,
                relative_path=target.relative_path,
                retained_reason="declared_stable_compatibility_facade",
                removal_ready=False,
            ),
        )

    return {stem: retained_by_stem[stem] for stem in sorted(retained_by_stem)}
