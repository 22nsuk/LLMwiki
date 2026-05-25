#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
else:
    from .output_runtime import display_path
    from .runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/compatibility-alias-deprecation.json"
PRODUCER = "ops.scripts.compatibility_alias_deprecation"
SCHEMA_PATH = "ops/schemas/compatibility-alias-deprecation.schema.json"
PREFER_RE = re.compile(r"compatibility alias; prefer (?P<replacement>[A-Za-z0-9_.@/-]+)")


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


def _flat_reexport_alias(vault: Path) -> list[dict[str, Any]]:
    init_path = vault / "ops" / "scripts" / "__init__.py"
    if "_ReexportFinder" not in _read_text(init_path):
        return []
    return [
        {
            "alias_type": "flat_import_reexport",
            "name": "ops.scripts.<name>",
            "path": "ops/scripts/__init__.py",
            "preferred_replacement": "ops.scripts.<domain>.<name>",
            "removal_ready": False,
            "retained_reason": "public_cli_import_compatibility",
        }
    ]


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    aliases = [
        *_make_aliases(resolved_vault),
        *_script_module_compatibility_aliases(resolved_vault),
        *_flat_reexport_alias(resolved_vault),
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
            "removal_ready_count": len(ready),
        },
        "aliases": aliases,
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
