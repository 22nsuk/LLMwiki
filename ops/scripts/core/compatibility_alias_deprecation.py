#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext
else:
    from .output_runtime import display_path
    from .runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/compatibility-alias-deprecation.json"
PRODUCER = "ops.scripts.compatibility_alias_deprecation"
SCHEMA_PATH = "ops/schemas/compatibility-alias-deprecation.schema.json"
PREFER_RE = re.compile(r"compatibility alias; prefer (?P<replacement>[A-Za-z0-9_.@/-]+)")
PYTHON_CALLER_SCAN_ROOTS = ("ops", "tests", "tools")
PYTHON_CALLER_EXCLUDED_PREFIXES = (
    "ops/operator/",
    "ops/reports/",
    "ops/manifest.json",
    "ops/raw-registry.json",
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _make_target_blocks(vault: Path) -> dict[str, tuple[str, str]]:
    blocks: dict[str, tuple[str, str]] = {}
    for path in [vault / "Makefile", *sorted((vault / "mk").glob("*.mk"))]:
        if not path.is_file():
            continue
        current: str | None = None
        lines: list[str] = []
        for line in _read_text(path).splitlines():
            if line and not line.startswith(("\t", " ", "#")) and ":" in line and "=" not in line.split(":", 1)[0]:
                if current is not None:
                    blocks[current] = (path.relative_to(vault).as_posix(), "\n".join(lines))
                current = line.split(":", 1)[0].split()[0]
                lines = [line]
            elif current is not None:
                lines.append(line)
        if current is not None:
            blocks[current] = (path.relative_to(vault).as_posix(), "\n".join(lines))
    return blocks


def _make_aliases(vault: Path) -> list[dict[str, Any]]:
    aliases: list[dict[str, Any]] = []
    for target, (source_path, block) in sorted(_make_target_blocks(vault).items()):
        if "compatibility alias" not in block:
            continue
        replacement = ""
        match = PREFER_RE.search(block)
        if match:
            replacement = match.group("replacement").rstrip(".")
        aliases.append(
            {
                "alias_type": "make_target",
                "name": target,
                "path": source_path,
                "preferred_replacement": replacement,
                "removal_ready": False,
                "retained_reason": "compatibility_window",
            }
        )
    return aliases


def _script_module_compatibility_aliases(vault: Path) -> list[dict[str, Any]]:
    registry_path = vault / "ops" / "script-module-surfaces.json"
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    aliases: list[dict[str, Any]] = []
    for item in payload.get("stable_import_surfaces", []):
        if not isinstance(item, dict) or item.get("role") != "compatibility_facade":
            continue
        aliases.append(
            {
                "alias_type": "stable_import_surface",
                "name": Path(str(item.get("path", ""))).stem,
                "path": str(item.get("path", "")),
                "preferred_replacement": "",
                "removal_ready": False,
                "retained_reason": "declared_stable_compatibility_facade",
            }
        )
    return aliases


def _flat_reexport_targets(vault: Path) -> dict[str, tuple[str, str]]:
    init_path = vault / "ops" / "scripts" / "__init__.py"
    if "_ReexportFinder" not in _read_text(init_path):
        return {}
    script_root = vault / "ops" / "scripts"
    targets: dict[str, tuple[str, str]] = {}
    for path in sorted(script_root.glob("*/*.py")):
        if path.name.startswith("_"):
            continue
        relative_path = path.relative_to(vault).as_posix()
        canonical_module = relative_path.removesuffix(".py").replace("/", ".")
        targets[f"ops.scripts.{path.stem}"] = (relative_path, canonical_module)
    return targets


def _flat_reexport_aliases(
    vault: Path,
    *,
    actual_caller_counts: Counter[str] | None = None,
) -> list[dict[str, Any]]:
    aliases: list[dict[str, Any]] = []
    for alias_name, (relative_path, canonical_module) in sorted(
        _flat_reexport_targets(vault).items()
    ):
        aliases.append(
            {
                "alias_type": "flat_import_reexport",
                "name": alias_name,
                "path": relative_path,
                "preferred_replacement": canonical_module,
                "removal_ready": False,
                "retained_reason": "public_cli_import_compatibility",
                "actual_caller_count": (
                    actual_caller_counts.get(alias_name, 0)
                    if actual_caller_counts is not None
                    else 0
                ),
            }
        )
    return aliases


def _python_caller_files(vault: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in PYTHON_CALLER_SCAN_ROOTS:
        root = vault / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            rel_path = path.relative_to(vault).as_posix()
            if any(rel_path.startswith(prefix) for prefix in PYTHON_CALLER_EXCLUDED_PREFIXES):
                continue
            if any(part in {"__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts):
                continue
            files.append(path)
    return files


def _flat_import_actual_callers(vault: Path) -> list[dict[str, Any]]:
    targets = _flat_reexport_targets(vault)
    if not targets:
        return []
    flat_stems = {module.rsplit(".", maxsplit=1)[-1]: module for module in targets}
    callers: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()

    def add_caller(
        *,
        path: Path,
        line: int,
        alias_name: str,
        usage_kind: str,
    ) -> None:
        relative_path, canonical_module = targets[alias_name]
        rel_path = path.relative_to(vault).as_posix()
        key = (rel_path, line, alias_name, usage_kind)
        if key in seen:
            return
        seen.add(key)
        callers.append(
            {
                "alias": alias_name,
                "preferred_replacement": canonical_module,
                "path": rel_path,
                "line": line,
                "usage_kind": usage_kind,
            }
        )

    for path in _python_caller_files(vault):
        rel_path = path.relative_to(vault).as_posix()
        source = _read_text(path)
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in targets:
                        add_caller(
                            path=path,
                            line=node.lineno,
                            alias_name=alias.name,
                            usage_kind="import",
                        )
                continue
            if not isinstance(node, ast.ImportFrom) or node.level != 0:
                continue
            module = node.module or ""
            if module in targets:
                add_caller(
                    path=path,
                    line=node.lineno,
                    alias_name=module,
                    usage_kind="from_import",
                )
                continue
            if module != "ops.scripts":
                continue
            for alias in node.names:
                alias_name = flat_stems.get(alias.name)
                if alias_name:
                    add_caller(
                        path=path,
                        line=node.lineno,
                        alias_name=alias_name,
                        usage_kind="from_package_import",
                    )
    return sorted(callers, key=lambda item: (item["path"], item["line"], item["alias"]))


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    flat_import_actual_callers = _flat_import_actual_callers(resolved_vault)
    actual_caller_counts = Counter(
        str(item["alias"]) for item in flat_import_actual_callers
    )
    aliases = [
        *_make_aliases(resolved_vault),
        *_script_module_compatibility_aliases(resolved_vault),
        *_flat_reexport_aliases(
            resolved_vault,
            actual_caller_counts=actual_caller_counts,
        ),
    ]
    ready = [item for item in aliases if item["removal_ready"]]
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "compatibility_alias_deprecation",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": "attention" if ready else "pass",
        "summary": {
            "alias_count": len(aliases),
            "make_alias_count": sum(1 for item in aliases if item["alias_type"] == "make_target"),
            "stable_import_surface_count": sum(
                1 for item in aliases if item["alias_type"] == "stable_import_surface"
            ),
            "flat_import_reexport_count": sum(
                1 for item in aliases if item["alias_type"] == "flat_import_reexport"
            ),
            "flat_import_actual_caller_count": len(flat_import_actual_callers),
            "flat_import_actual_alias_count": len(actual_caller_counts),
            "removal_ready_count": len(ready),
        },
        "aliases": aliases,
        "flat_import_actual_callers": flat_import_actual_callers,
        "removal_ready_aliases": ready,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory compatibility aliases and deprecation readiness.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
