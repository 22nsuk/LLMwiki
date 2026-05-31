#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
else:
    from .output_runtime import display_path
    from .runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/cli-surface-inventory.json"
PRODUCER = "ops.scripts.cli_surface_inventory"
SCRIPT_MODULE_RE = re.compile(
    r"-m\s+(ops\.scripts\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\b"
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _pyproject_script_modules(vault: Path) -> list[str]:
    path = vault / "pyproject.toml"
    if not path.is_file():
        return []
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    scripts = project.get("scripts", {}) if isinstance(project, dict) else {}
    if not isinstance(scripts, dict):
        return []
    return sorted(
        str(target).split(":", maxsplit=1)[0]
        for target in scripts.values()
        if str(target).strip()
    )


def _makefile_script_modules(vault: Path) -> list[str]:
    modules: set[str] = set()
    for path in [vault / "Makefile", *sorted((vault / "mk").glob("*.mk"))]:
        if path.is_file():
            modules.update(SCRIPT_MODULE_RE.findall(path.read_text()))
    return sorted(modules)


def _direct_fallback_modules(vault: Path) -> list[str]:
    registry = _read_json(vault / "ops" / "script-output-surfaces.json")
    modules: list[str] = []
    for item in registry.get("surfaces", []):
        if not isinstance(item, dict) or not item.get("direct_fallback_eligible"):
            continue
        rel_path = str(item.get("path", "")).strip()
        path = vault / rel_path
        if not path.is_file():
            continue
        if "direct script fallback" not in path.read_text(encoding="utf-8"):
            continue
        modules.append(Path(rel_path).with_suffix("").as_posix().replace("/", "."))
    return sorted(dict.fromkeys(modules))


def _canonical_module_from_path(path: str) -> str:
    return Path(path).with_suffix("").as_posix().replace("/", ".")


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    groups = {
        "pyproject_scripts": _pyproject_script_modules(resolved_vault),
        "makefile_module_invocations": _makefile_script_modules(resolved_vault),
        "direct_fallback_modules": _direct_fallback_modules(resolved_vault),
    }
    module_names = sorted({module for modules in groups.values() for module in modules})
    entries_by_key: dict[str, dict[str, Any]] = {}
    for module in module_names:
        path = _resolve_module_path(resolved_vault, module)
        key = path or module
        entry = entries_by_key.setdefault(
            key,
            {
                "module": _canonical_module_from_path(path) if path else module,
                "path": path,
                "aliases": [],
                "sources": [],
            },
        )
        entry["aliases"].append(module)
        entry["sources"].extend(name for name, modules in groups.items() if module in modules)
    entries = [
        {
            **entry,
            "aliases": sorted(set(entry["aliases"])),
            "sources": sorted(set(entry["sources"])),
        }
        for entry in entries_by_key.values()
    ]
    entries.sort(key=lambda item: str(item["module"]))
    unresolved = [entry["module"] for entry in entries if not entry["path"]]
    return {
        "$schema": "ops/schemas/cli-surface-inventory.schema.json",
        "artifact_kind": "cli_surface_inventory",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": "fail" if unresolved else "pass",
        "summary": {
            "module_count": len(entries),
            "pyproject_script_count": len(groups["pyproject_scripts"]),
            "makefile_module_invocation_count": len(groups["makefile_module_invocations"]),
            "direct_fallback_module_count": len(groups["direct_fallback_modules"]),
            "unresolved_module_count": len(unresolved),
        },
        "modules": entries,
        "unresolved_modules": unresolved,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory public CLI module surfaces.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    destination = write_report(vault, build_report(vault), args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
