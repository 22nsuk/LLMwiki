from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from .output_runtime import display_path
from .schema_runtime import load_schema, validate_with_schema
from .script_output_surfaces import (
    DEFAULT_OUT as SCRIPT_OUTPUT_SURFACES_OUT,
    DIRECT_SCRIPT_FALLBACK_MARKER,
    build_registry as build_script_output_surfaces,
)

DEFAULT_OUT = "ops/script-module-surfaces.json"
DEFAULT_OVERRIDES = "ops/script-module-surface-overrides.json"
SCHEMA_PATH = "ops/schemas/script-module-surfaces.schema.json"
OVERRIDES_SCHEMA_PATH = "ops/schemas/script-module-surface-overrides.schema.json"
DESCRIPTION = (
    "Generated contract for ops/scripts module surfaces. Stable import paths and "
    "exports are discovered from literal __all__ declarations, direct-script "
    "entrypoints are derived from the live material output/fallback surface scan, "
    "and roles are applied from ops/script-module-surface-overrides.json."
)


class ScriptModuleSurfaceError(ValueError):
    pass


def _script_files(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in (vault / "ops" / "scripts").rglob("*.py")
        if path.name != "__init__.py"
    )


def _module_tree(path: Path, *, vault: Path) -> ast.Module:
    rel_path = path.relative_to(vault).as_posix()
    return ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)


def literal_all_exports(path: Path, *, vault: Path | None = None) -> list[str] | None:
    resolved_vault = vault.resolve() if vault is not None else Path(".").resolve()
    for node in _module_tree(path, vault=resolved_vault).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ScriptModuleSurfaceError(
                f"{path.relative_to(resolved_vault).as_posix()} has non-literal __all__"
            )
        return list(value)
    return None


def _literal_all_by_path(vault: Path) -> dict[str, list[str]]:
    exports_by_path: dict[str, list[str]] = {}
    for path in _script_files(vault):
        exports = literal_all_exports(path, vault=vault)
        if exports is not None:
            exports_by_path[path.relative_to(vault).as_posix()] = exports
    return exports_by_path


def direct_script_entrypoint_paths(vault: Path) -> set[str]:
    registry = build_script_output_surfaces(vault)
    paths: set[str] = set()
    for item in registry.get("surfaces", []):
        if not isinstance(item, dict) or not item.get("direct_fallback_eligible"):
            continue
        rel_path = str(item.get("path", ""))
        if not rel_path:
            continue
        path = vault / rel_path
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if DIRECT_SCRIPT_FALLBACK_MARKER in source:
            paths.add(rel_path)
    return paths


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        raise ScriptModuleSurfaceError(f"{path.as_posix()} must contain a JSON object")
    return payload


def _read_overrides(vault: Path, override_path: str | None = None) -> dict[str, Any]:
    path = Path(override_path or DEFAULT_OVERRIDES)
    if not path.is_absolute():
        path = vault / path
    overrides = _read_json_object(path)
    schema_errors = validate_with_schema(overrides, load_schema(vault / OVERRIDES_SCHEMA_PATH))
    if schema_errors:
        raise ScriptModuleSurfaceError(
            "script module surface overrides schema validation failed:\n"
            + "\n".join(schema_errors[:10])
        )
    return overrides


def _role_by_path(overrides: Mapping[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for item in overrides.get("overrides", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        role = str(item.get("role", ""))
        if not path or not role:
            continue
        if path in roles:
            raise ScriptModuleSurfaceError(
                f"duplicate script module surface override path: {path}"
            )
        roles[path] = role
    return roles


def _ordered_paths(overrides: Mapping[str, Any], derived_paths: set[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in overrides.get("overrides", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        if path in derived_paths and path not in seen:
            ordered.append(path)
            seen.add(path)
    ordered.extend(sorted(derived_paths - seen))
    return ordered


def build_contract(
    vault: Path, *, overrides: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    override_payload = overrides if overrides is not None else _read_overrides(resolved_vault)
    roles = _role_by_path(override_payload)
    exports_by_path = _literal_all_by_path(resolved_vault)
    derived_paths = set(exports_by_path)
    missing_roles = sorted(derived_paths - set(roles))
    if missing_roles:
        raise ScriptModuleSurfaceError(
            "script-module-surfaces is missing manually curated roles for: "
            + ", ".join(missing_roles)
        )
    extra_roles = sorted(set(roles) - derived_paths)
    if extra_roles:
        raise ScriptModuleSurfaceError(
            "script-module-surface overrides reference modules without literal __all__: "
            + ", ".join(extra_roles)
        )
    direct_entrypoints = direct_script_entrypoint_paths(resolved_vault)
    surfaces = [
        {
            "path": path,
            "role": roles[path],
            "direct_script_entrypoint": path in direct_entrypoints,
            "exports": exports_by_path[path],
        }
        for path in _ordered_paths(override_payload, derived_paths)
    ]
    invalid_direct_roles = [
        str(item["path"])
        for item in surfaces
        if item["direct_script_entrypoint"] and item["role"] != "cli_facade"
    ]
    if invalid_direct_roles:
        raise ScriptModuleSurfaceError(
            "direct script entrypoints must use role=cli_facade: "
            + ", ".join(invalid_direct_roles)
        )
    return {
        "$schema": SCHEMA_PATH,
        "version": 1,
        "description": DESCRIPTION,
        "stable_import_surfaces": surfaces,
    }


def write_contract(
    vault: Path, contract: dict[str, Any], out_path: str | None = None
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=contract,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="script module surfaces schema validation failed",
            trailing_newline=True,
        )
    )


def _resolve_contract_path(vault: Path, out_path: str | None) -> Path:
    path = Path(out_path or DEFAULT_OUT)
    if not path.is_absolute():
        path = vault / path
    return path


def _surface_map(contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("path", "")): item
        for item in contract.get("stable_import_surfaces", [])
        if isinstance(item, dict) and str(item.get("path", "")).strip()
    }


def _contract_check_diagnostics(
    actual: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    actual_surfaces = _surface_map(actual)
    expected_surfaces = _surface_map(expected)
    actual_paths = set(actual_surfaces)
    expected_paths = set(expected_surfaces)
    contract_fields = ("$schema", "version", "description")
    return {
        "contract_fields_changed": [
            field
            for field in contract_fields
            if actual.get(field) != expected.get(field)
        ],
        "added_paths": sorted(expected_paths - actual_paths),
        "removed_paths": sorted(actual_paths - expected_paths),
        "changed_paths": sorted(
            path
            for path in actual_paths & expected_paths
            if actual_surfaces[path] != expected_surfaces[path]
        ),
    }


def _contract_is_current(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        actual.get("$schema") == expected.get("$schema")
        and actual.get("version") == expected.get("version")
        and actual.get("description") == expected.get("description")
        and actual.get("stable_import_surfaces")
        == expected.get("stable_import_surfaces")
    )


def check_contract(
    vault: Path, *, stored_path: str | None = None, overrides_path: str | None = None
) -> int:
    contract_path = _resolve_contract_path(vault, stored_path)
    try:
        actual = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            "script-module-surfaces check failed: "
            f"could not read {display_path(vault, contract_path)} ({type(exc).__name__}: {exc}). "
            "Run `make script-module-surfaces`.",
            file=sys.stderr,
        )
        return 1
    if not isinstance(actual, dict):
        print(
            "script-module-surfaces check failed: stored contract must be a JSON object. "
            "Run `make script-module-surfaces`.",
            file=sys.stderr,
        )
        return 1

    schema_errors = validate_with_schema(actual, load_schema(vault / SCHEMA_PATH))
    if schema_errors:
        print(
            "script-module-surfaces schema validation failed; this is a schema/shape "
            "error, not a derived source mismatch. "
            "Run `make script-module-surfaces` after fixing the schema issue.\n"
            + "\n".join(schema_errors[:10]),
            file=sys.stderr,
        )
        return 1

    try:
        expected = build_contract(
            vault,
            overrides=_read_overrides(vault, overrides_path),
        )
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
        print(
            "script-module-surfaces check failed while deriving live module surfaces: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    if _contract_is_current(actual, expected):
        print(f"{display_path(vault, contract_path)} is current")
        return 0

    diagnostics = _contract_check_diagnostics(actual, expected)
    print(
        "script-module-surfaces contract is stale; run `make script-module-surfaces`.\n"
        + json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True),
        file=sys.stderr,
    )
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument(
        "--out", default=DEFAULT_OUT, help="Output path for the generated contract."
    )
    parser.add_argument(
        "--stored",
        default=None,
        help="Stored contract path to verify in --check mode. Defaults to --out.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the stored contract differs from the live source-derived module surface set.",
    )
    parser.add_argument(
        "--script-output-surfaces",
        default=SCRIPT_OUTPUT_SURFACES_OUT,
        help="Accepted for CLI compatibility; live derivation rebuilds this registry from source.",
    )
    parser.add_argument(
        "--overrides",
        default=DEFAULT_OVERRIDES,
        help="Override path that provides manually curated module roles.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    del args.script_output_surfaces
    vault = Path(args.vault).resolve()
    if args.check:
        return check_contract(
            vault,
            stored_path=args.stored or args.out,
            overrides_path=args.overrides,
        )
    destination = write_contract(
        vault,
        build_contract(vault, overrides=_read_overrides(vault, args.overrides)),
        args.out,
    )
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
