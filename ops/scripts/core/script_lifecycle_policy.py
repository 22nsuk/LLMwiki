from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from .makefile_runtime import makefile_script_module_targets
from .output_runtime import display_path
from .schema_runtime import load_schema, validate_with_schema
from .script_output_surfaces import (
    DIRECT_SCRIPT_FALLBACK_MARKER,
    build_registry as build_script_output_surfaces,
)

DEFAULT_OUT = "ops/script-lifecycle-policy.json"
DEFAULT_OVERRIDES = "ops/script-lifecycle-overrides.json"
SCHEMA_PATH = "ops/schemas/script-lifecycle-policy.schema.json"
OVERRIDES_SCHEMA_PATH = "ops/schemas/script-lifecycle-overrides.schema.json"
DESCRIPTION = (
    "Generated lifecycle policy for ops/scripts surfaces. Module entries are "
    "derived from the live ops/scripts tree, pyproject.toml console scripts, "
    "Make recipe module references, and direct fallback inventory; human-owned "
    "lifecycle guidance lives in ops/script-lifecycle-overrides.json."
)
LIFECYCLE_VALUES = (
    "public_cli",
    "make_only",
    "report_generator",
    "helper",
    "test_only",
    "legacy_delete",
)
INSTALL_STATE_VALUES = ("public_cli", "transitional_installed", "not_installed")
OVERRIDE_FIELDS = {"lifecycle", "replacement"}


class ScriptLifecyclePolicyError(ValueError):
    pass


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScriptLifecyclePolicyError(f"{path.as_posix()} must contain a JSON object")
    return payload


def _read_overrides(vault: Path, override_path: str | None = None) -> dict[str, Any]:
    path = Path(override_path or DEFAULT_OVERRIDES)
    if not path.is_absolute():
        path = vault / path
    if not path.is_file():
        return {"overrides": []}
    overrides = _read_json_object(path)
    schema_path = vault / OVERRIDES_SCHEMA_PATH
    if schema_path.is_file():
        schema_errors = validate_with_schema(overrides, load_schema(schema_path))
        if schema_errors:
            raise ScriptLifecyclePolicyError(
                "script lifecycle overrides schema validation failed:\n"
                + "\n".join(schema_errors[:10])
            )
    return overrides


def _script_files(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in (vault / "ops" / "scripts").rglob("*.py")
        if path.name != "__init__.py"
    )


def _canonical_module_from_path(path: str) -> str:
    return Path(path).with_suffix("").as_posix().replace("/", ".")


def _module_path_candidates(vault: Path, module_name: str) -> list[str]:
    parts = module_name.split(".")
    if parts[:2] != ["ops", "scripts"] or len(parts) < 3:
        return []
    relative = Path(*parts).with_suffix(".py").as_posix()
    candidates = [relative]
    if len(parts) == 3:
        candidates.extend(
            path.relative_to(vault).as_posix()
            for path in sorted((vault / "ops" / "scripts").glob(f"*/{parts[-1]}.py"))
        )
    return candidates


def _resolve_module_path(vault: Path, module_name: str) -> str:
    for candidate in _module_path_candidates(vault, module_name):
        if (vault / candidate).is_file():
            return candidate
    return ""


def _canonical_module(vault: Path, module_name: str) -> str:
    path = _resolve_module_path(vault, module_name)
    return _canonical_module_from_path(path) if path else module_name


def _project_scripts(vault: Path) -> dict[str, str]:
    path = vault / "pyproject.toml"
    if not path.is_file():
        return {}
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    scripts = project.get("scripts", {}) if isinstance(project, dict) else {}
    if not isinstance(scripts, dict):
        return {}
    return {str(command): str(target) for command, target in sorted(scripts.items())}


def _project_scripts_by_module(vault: Path) -> dict[str, list[str]]:
    modules: dict[str, set[str]] = {}
    for command, target in _project_scripts(vault).items():
        module = str(target).split(":", maxsplit=1)[0].strip()
        if module:
            modules.setdefault(_canonical_module(vault, module), set()).add(command)
    return {
        module: sorted(commands)
        for module, commands in sorted(modules.items())
    }


def _makefile_script_module_targets(vault: Path) -> dict[str, list[str]]:
    modules: dict[str, set[str]] = {}
    for module, targets in makefile_script_module_targets(vault).items():
        modules.setdefault(_canonical_module(vault, module), set()).update(targets)
    return {
        module: sorted(target for target in targets if target)
        for module, targets in sorted(modules.items())
    }


def _override_by_module(overrides: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    raw_items = overrides.get("overrides", [])
    if not isinstance(raw_items, list):
        raise ScriptLifecyclePolicyError("script lifecycle overrides must be an array")
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ScriptLifecyclePolicyError(
                f"script lifecycle override overrides[{index}] must be an object"
            )
        module = str(item.get("canonical_module", "")).strip()
        if not module:
            raise ScriptLifecyclePolicyError(
                f"script lifecycle override overrides[{index}] is missing canonical_module"
            )
        if module in records:
            raise ScriptLifecyclePolicyError(
                f"duplicate script lifecycle override module: {module}"
            )
        records[module] = {
            field: item[field]
            for field in OVERRIDE_FIELDS
            if field in item
        }
    return records


def _ensure_entry(entries: dict[str, dict[str, Any]], module: str) -> dict[str, Any]:
    return entries.setdefault(
        module,
        {
            "canonical_module": module,
            "console_scripts": [],
            "make_targets": [],
            "sources": [],
            "output_classifications": [],
            "direct_fallback": False,
        },
    )


def _live_script_entries(vault: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for path in _script_files(vault):
        rel_path = path.relative_to(vault).as_posix()
        module = _canonical_module_from_path(rel_path)
        entry = _ensure_entry(entries, module)
        entry["sources"].append("ops_scripts_scan")
    return entries


def _surface_entries(vault: Path, entries: dict[str, dict[str, Any]]) -> None:
    registry = build_script_output_surfaces(vault)
    for item in registry.get("surfaces", []):
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if not rel_path:
            continue
        module = _canonical_module_from_path(rel_path)
        entry = _ensure_entry(entries, module)
        entry["sources"].append("script_output_surfaces")
        entry["output_classifications"].append(str(item.get("classification", "")))
        if bool(item.get("direct_fallback_eligible")):
            path = vault / rel_path
            if (
                path.is_file()
                and DIRECT_SCRIPT_FALLBACK_MARKER in path.read_text(encoding="utf-8")
            ):
                entry["direct_fallback"] = True
                entry["sources"].append("direct_fallback_modules")


def _source_derived_entries(vault: Path) -> dict[str, dict[str, Any]]:
    entries = _live_script_entries(vault)
    _surface_entries(vault, entries)
    for module, commands in _project_scripts_by_module(vault).items():
        entry = _ensure_entry(entries, module)
        entry["console_scripts"].extend(commands)
        entry["sources"].append("pyproject_scripts")
    for module, targets in _makefile_script_module_targets(vault).items():
        entry = _ensure_entry(entries, module)
        entry["make_targets"].extend(targets)
        entry["sources"].append("makefile_module_invocations")
    for entry in entries.values():
        entry["console_scripts"] = sorted(set(entry["console_scripts"]))
        entry["make_targets"] = sorted(set(entry["make_targets"]))
        entry["sources"] = sorted(set(entry["sources"]))
        entry["output_classifications"] = sorted(set(entry["output_classifications"]))
    return dict(sorted(entries.items()))


def _default_lifecycle(entry: Mapping[str, Any]) -> str:
    if entry.get("console_scripts"):
        return "public_cli"
    output_classifications = {
        str(item) for item in entry.get("output_classifications", []) if str(item)
    }
    if output_classifications - {"no_output"}:
        return "report_generator"
    if entry.get("make_targets") or entry.get("direct_fallback"):
        return "make_only"
    return "helper"


def _default_replacement(module: str, entry: Mapping[str, Any]) -> str:
    make_targets = [str(item) for item in entry.get("make_targets", []) if str(item)]
    if make_targets:
        return f"make {make_targets[0]}"
    if entry.get("console_scripts"):
        return ""
    return f"python -m {module}"


def _default_override_values(module: str, entry: Mapping[str, Any]) -> dict[str, str]:
    return {
        "lifecycle": _default_lifecycle(entry),
        "replacement": _default_replacement(module, entry),
    }


def _redundant_override_fields(
    entries: Mapping[str, Mapping[str, Any]],
    override_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    redundant: dict[str, list[str]] = {}
    for module, override in sorted(override_records.items()):
        default_values = _default_override_values(module, entries[module])
        fields = [
            field
            for field in sorted(OVERRIDE_FIELDS)
            if field in override and str(override[field]) == default_values[field]
        ]
        if not override:
            fields = ["<empty>"]
        if fields:
            redundant[module] = fields
    return redundant


def _default_rationale(entry: Mapping[str, Any], lifecycle: str) -> str:
    sources = ", ".join(str(item) for item in entry.get("sources", [])) or "source scan"
    if lifecycle == "public_cli":
        return "Generated from pyproject.toml console-script exposure."
    return f"Generated from {sources}; lifecycle and replacement may be overridden."


def _policy_inputs(
    resolved_vault: Path,
    override_payload: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    override_records = _override_by_module(override_payload)
    entries = _source_derived_entries(resolved_vault)
    missing_paths = [
        module
        for module in sorted(entries)
        if _resolve_module_path(resolved_vault, module) == ""
    ]
    if missing_paths:
        raise ScriptLifecyclePolicyError(
            "script lifecycle scanner found modules without ops/scripts files: "
            + ", ".join(missing_paths)
        )
    extra_overrides = sorted(set(override_records) - set(entries))
    if extra_overrides:
        raise ScriptLifecyclePolicyError(
            "script lifecycle overrides reference missing scripts: "
            + ", ".join(extra_overrides)
        )
    return entries, override_records


def redundant_override_fields(
    vault: Path,
    *,
    overrides: Mapping[str, Any] | None = None,
    overrides_path: str | None = None,
) -> dict[str, list[str]]:
    resolved_vault = vault.resolve()
    override_payload = (
        overrides
        if overrides is not None
        else _read_overrides(resolved_vault, overrides_path)
    )
    entries, override_records = _policy_inputs(resolved_vault, override_payload)
    return _redundant_override_fields(entries, override_records)


def _build_policy_from_inputs(
    entries: Mapping[str, Mapping[str, Any]],
    override_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    for module, entry in entries.items():
        override = override_records.get(module, {})
        lifecycle = str(override.get("lifecycle") or _default_lifecycle(entry))
        replacement = str(
            override.get("replacement")
            if "replacement" in override
            else _default_replacement(module, entry)
        )
        record: dict[str, Any] = {
            "canonical_module": module,
            "console_scripts": entry["console_scripts"],
            "install_state": "public_cli" if entry["console_scripts"] else "not_installed",
            "lifecycle": lifecycle,
            "rationale": _default_rationale(entry, lifecycle),
            "removal_ready": False,
            "replacement": replacement,
        }
        modules.append(record)

    return {
        "$schema": SCHEMA_PATH,
        "version": 1,
        "description": DESCRIPTION,
        "lifecycle_values": list(LIFECYCLE_VALUES),
        "install_state_values": list(INSTALL_STATE_VALUES),
        "modules": modules,
    }


def build_policy(
    vault: Path,
    *,
    overrides: Mapping[str, Any] | None = None,
    overrides_path: str | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    override_payload = (
        overrides
        if overrides is not None
        else _read_overrides(resolved_vault, overrides_path)
    )
    entries, override_records = _policy_inputs(resolved_vault, override_payload)
    return _build_policy_from_inputs(entries, override_records)


def load_script_lifecycle_policy(
    vault: Path,
    *,
    stored_path: str | None = DEFAULT_OUT,
    overrides_path: str | None = DEFAULT_OVERRIDES,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy_path = _resolve_path(resolved_vault, stored_path, DEFAULT_OUT)
    if policy_path.is_file():
        payload = _read_json_object(policy_path)
        schema_path = resolved_vault / SCHEMA_PATH
        if schema_path.is_file():
            schema_errors = validate_with_schema(payload, load_schema(schema_path))
            if schema_errors:
                raise ScriptLifecyclePolicyError(
                    "script lifecycle policy schema validation failed:\n"
                    + "\n".join(schema_errors[:10])
                )
        return payload
    return build_policy(resolved_vault, overrides_path=overrides_path)


def lifecycle_modules_by_canonical_module(
    policy: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    modules = policy.get("modules", [])
    if not isinstance(modules, list):
        return {}
    records: dict[str, dict[str, Any]] = {}
    for item in modules:
        if not isinstance(item, dict):
            continue
        module = str(item.get("canonical_module", "")).strip()
        if module:
            records[module] = dict(item)
    return records


def write_policy(vault: Path, policy: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=policy,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="script lifecycle policy schema validation failed",
            trailing_newline=True,
        )
    )


def _resolve_path(vault: Path, path: str | None, default: str) -> Path:
    resolved = Path(path or default)
    if not resolved.is_absolute():
        resolved = vault / resolved
    return resolved


def _policy_check_diagnostics(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, Any]:
    actual_modules = {
        str(item.get("canonical_module", "")): item
        for item in actual.get("modules", [])
        if isinstance(item, dict) and str(item.get("canonical_module", "")).strip()
    }
    expected_modules = {
        str(item.get("canonical_module", "")): item
        for item in expected.get("modules", [])
        if isinstance(item, dict) and str(item.get("canonical_module", "")).strip()
    }
    actual_names = set(actual_modules)
    expected_names = set(expected_modules)
    return {
        "added_modules": sorted(expected_names - actual_names),
        "removed_modules": sorted(actual_names - expected_names),
        "changed_modules": sorted(
            module
            for module in actual_names & expected_names
            if actual_modules[module] != expected_modules[module]
        ),
    }


def check_policy(
    vault: Path, *, stored_path: str | None = None, overrides_path: str | None = None
) -> int:
    policy_path = _resolve_path(vault, stored_path, DEFAULT_OUT)
    try:
        actual = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            "script-lifecycle-policy check failed: "
            f"could not read {display_path(vault, policy_path)} ({type(exc).__name__}: {exc}). "
            "Run `make script-lifecycle-policy`.",
            file=sys.stderr,
        )
        return 1
    if not isinstance(actual, dict):
        print(
            "script-lifecycle-policy check failed: stored policy must be a JSON object. "
            "Run `make script-lifecycle-policy`.",
            file=sys.stderr,
        )
        return 1
    schema_errors = validate_with_schema(actual, load_schema(vault / SCHEMA_PATH))
    if schema_errors:
        print(
            "script-lifecycle-policy schema validation failed; this is a schema/shape "
            "error, not a source-derived mismatch. "
            "Run `make script-lifecycle-policy` after fixing the schema issue.\n"
            + "\n".join(schema_errors[:10]),
            file=sys.stderr,
        )
        return 1
    try:
        override_payload = _read_overrides(vault, overrides_path)
        entries, override_records = _policy_inputs(vault, override_payload)
        redundant_fields = _redundant_override_fields(entries, override_records)
        if redundant_fields:
            print(
                "script-lifecycle-policy check failed: "
                "script lifecycle overrides must only store non-default manual judgments.\n"
                + json.dumps(
                    {"redundant_override_fields": redundant_fields},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
        expected = _build_policy_from_inputs(entries, override_records)
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
        print(
            "script-lifecycle-policy check failed while deriving live script surfaces: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    if actual == expected:
        print(f"{display_path(vault, policy_path)} is current")
        return 0
    print(
        "script-lifecycle-policy is stale; run `make script-lifecycle-policy`.\n"
        + json.dumps(
            _policy_check_diagnostics(actual, expected),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument(
        "--out", default=DEFAULT_OUT, help="Output path for the generated policy."
    )
    parser.add_argument(
        "--stored",
        default=None,
        help="Stored policy path to verify in --check mode. Defaults to --out.",
    )
    parser.add_argument(
        "--overrides",
        default=DEFAULT_OVERRIDES,
        help="Override path that provides manually curated lifecycle values.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the stored policy differs from the live source-derived policy.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.check:
        return check_policy(
            vault,
            stored_path=args.stored or args.out,
            overrides_path=args.overrides,
        )
    policy = build_policy(vault, overrides_path=args.overrides)
    destination = write_policy(vault, policy, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
