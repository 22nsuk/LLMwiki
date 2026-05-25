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
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/mechanism-navigation-index.json"
PRODUCER = "ops.scripts.mechanism_navigation_index"
SCHEMA_PATH = "ops/schemas/mechanism-navigation-index.schema.json"
MECHANISM_ROOT = "ops/scripts/mechanism"
DEFAULT_OUT_RE = re.compile(r"DEFAULT_OUT\s*=\s*[\"'](?P<path>[^\"']+)[\"']")
SCHEMA_REF_RE = re.compile(r"ops/schemas/[A-Za-z0-9_.-]+\.schema\.json")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _makefile_text(vault: Path) -> str:
    parts: list[str] = []
    for path in [vault / "Makefile", *sorted((vault / "mk").glob("*.mk"))]:
        if path.is_file():
            parts.append(_read_text(path))
    return "\n".join(parts)


def _target_blocks(vault: Path) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for path in [vault / "Makefile", *sorted((vault / "mk").glob("*.mk"))]:
        if not path.is_file():
            continue
        for line in _read_text(path).splitlines():
            if line and not line.startswith(("\t", " ", "#")) and ":" in line and "=" not in line.split(":", 1)[0]:
                current = line.split(":", 1)[0].split()[0]
                blocks.setdefault(current, [line])
            elif current is not None:
                blocks[current].append(line)
    return {target: "\n".join(lines) for target, lines in blocks.items()}


def _referencing_targets(vault: Path, module: str, path: str) -> list[str]:
    stem = Path(path).stem
    needles = {
        module,
        f"ops.scripts.{stem}",
        path,
        path.removesuffix(".py").replace("/", "."),
    }
    matches: list[str] = []
    for target, block in _target_blocks(vault).items():
        if any(needle in block for needle in needles):
            matches.append(target)
    return sorted(matches)


def _script_entry(vault: Path, path: Path) -> dict[str, Any]:
    rel_path = path.relative_to(vault).as_posix()
    text = _read_text(path)
    module = rel_path.removesuffix(".py").replace("/", ".")
    output_paths = sorted(set(DEFAULT_OUT_RE.findall(text)))
    schema_refs = sorted(set(SCHEMA_REF_RE.findall(text)))
    return {
        "module": module,
        "path": rel_path,
        "has_main": "def main(" in text,
        "direct_script_fallback": "direct script fallback" in text,
        "make_targets": _referencing_targets(vault, module, rel_path),
        "default_output_paths": output_paths,
        "schema_refs": schema_refs,
    }


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    mechanism_dir = resolved_vault / MECHANISM_ROOT
    scripts = [
        _script_entry(resolved_vault, path)
        for path in sorted(mechanism_dir.glob("*.py"))
        if path.name != "__init__.py"
    ]
    cli_entries = [entry for entry in scripts if entry["has_main"]]
    unlinked_cli_entries = [
        entry["path"] for entry in cli_entries if not entry["make_targets"]
    ]
    schema_linked_entries = [entry for entry in scripts if entry["schema_refs"]]
    status = "pass" if scripts and (not cli_entries or len(unlinked_cli_entries) < len(cli_entries)) else "attention"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "mechanism_navigation_index",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": status,
        "summary": {
            "script_count": len(scripts),
            "cli_entrypoint_count": len(cli_entries),
            "schema_linked_entry_count": len(schema_linked_entries),
            "unlinked_cli_entry_count": len(unlinked_cli_entries),
        },
        "scripts": scripts,
        "unlinked_cli_entries": unlinked_cli_entries,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory mechanism runtime navigation surfaces.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
