#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.runtime_context import RuntimeContext
else:
    from .output_runtime import display_path
    from .runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/tools-migration-plan.json"
PRODUCER = "ops.scripts.tools_migration_plan"
SCHEMA_PATH = "ops/schemas/tools-migration-plan.schema.json"
SCAN_PREFIXES = ("Makefile", "mk", "ops/scripts", "tests", "docs", ".github", "pyproject.toml", "README.md")
GENERATED_PREFIXES = ("ops/reports/", "runs/", "external-reports/", "tmp/", "build/")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _scan_files(vault: Path) -> list[Path]:
    files: list[Path] = []
    for prefix in SCAN_PREFIXES:
        path = vault / prefix
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    return sorted(
        {
            path
            for path in files
            if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
        }
    )


def _references_for_tool(vault: Path, tool_path: str) -> list[str]:
    references: list[str] = []
    for path in _scan_files(vault):
        rel_path = path.relative_to(vault).as_posix()
        if rel_path == tool_path or rel_path.startswith(GENERATED_PREFIXES):
            continue
        if tool_path in _read_text(path):
            references.append(rel_path)
    return sorted(set(references))


def _retention_reason(tool_path: str, references: list[str]) -> str:
    if any(path.startswith("mk/") or path == "Makefile" for path in references):
        return "live_make_target"
    if any(path.startswith("tests/") for path in references):
        return "test_contract"
    if any(path.startswith("ops/scripts/") for path in references):
        return "runtime_registry_or_source_contract"
    if Path(tool_path).name == "regenerate_report_schema_samples.py":
        return "schema_sample_regeneration_entrypoint"
    return "tracked_source_review_required"


def _canonical_replacement(tool_path: str) -> str:
    stem = Path(tool_path).stem
    known = {
        "regenerate_report_schema_samples": "tools/regenerate_report_schema_samples.py",
        "ruff_strict_preview": "tools/ruff_strict_preview.py",
        "strict_preview_audit": "tools/strict_preview_audit.py",
    }
    return known.get(stem, "")


def _tool_entry(vault: Path, path: Path) -> dict[str, Any]:
    rel_path = path.relative_to(vault).as_posix()
    references = _references_for_tool(vault, rel_path)
    retained_reason = _retention_reason(rel_path, references)
    deletion_candidate = not references and retained_reason == "tracked_source_review_required"
    return {
        "path": rel_path,
        "reference_count": len(references),
        "references": references,
        "canonical_replacement": _canonical_replacement(rel_path),
        "retained_reason": retained_reason,
        "deletion_candidate": deletion_candidate,
    }


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    tools_dir = resolved_vault / "tools"
    tools = [
        _tool_entry(resolved_vault, path)
        for path in sorted(tools_dir.glob("*.py"))
    ]
    deletion_candidates = [entry["path"] for entry in tools if entry["deletion_candidate"]]
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "tools_migration_plan",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": "attention" if deletion_candidates else "pass",
        "summary": {
            "tool_count": len(tools),
            "retained_tool_count": len(tools) - len(deletion_candidates),
            "deletion_candidate_count": len(deletion_candidates),
        },
        "tools": tools,
        "deletion_candidates": deletion_candidates,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory tools/ migration and deletion readiness.")
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
