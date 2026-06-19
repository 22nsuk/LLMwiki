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
    from ops.scripts.public.public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
        PUBLIC_INCLUDE_FILES,
        PUBLIC_INCLUDE_PREFIXES,
        is_public_excluded_by_local_state,
    )
else:
    from ..core.output_runtime import display_path
    from ..core.runtime_context import RuntimeContext
    from .public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
        PUBLIC_INCLUDE_FILES,
        PUBLIC_INCLUDE_PREFIXES,
        is_public_excluded_by_local_state,
    )


DEFAULT_OUT = "tmp/public-surface-snapshot.json"
PRODUCER = "ops.scripts.public_surface_snapshot"


def _prefix_file_count(vault: Path, prefix: str) -> int:
    root = vault / prefix
    if not root.exists():
        return 0
    if root.is_file():
        return 1
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and not is_public_excluded_by_local_state(path.relative_to(vault).as_posix())
    )


def _excluded_prefix_presence(vault: Path) -> list[dict[str, Any]]:
    return [
        {
            "prefix": prefix,
            "present": (vault / prefix).exists(),
        }
        for prefix in PUBLIC_EXCLUDED_PREFIXES
    ]


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    include_files = [
        {"path": path, "exists": (resolved_vault / path).is_file()}
        for path in PUBLIC_INCLUDE_FILES
    ]
    include_prefixes = [
        {
            "prefix": prefix,
            "exists": (resolved_vault / prefix).exists(),
            "file_count": _prefix_file_count(resolved_vault, prefix),
        }
        for prefix in PUBLIC_INCLUDE_PREFIXES
    ]
    excluded_files = [
        {"path": path, "present_in_local_tree": (resolved_vault / path).exists()}
        for path in PUBLIC_EXCLUDED_FILES
    ]
    missing_include_files = [item["path"] for item in include_files if not item["exists"]]
    missing_include_prefixes = [item["prefix"] for item in include_prefixes if not item["exists"]]
    return {
        "$schema": "ops/schemas/public-surface-snapshot.schema.json",
        "artifact_kind": "public_surface_snapshot",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": "pass" if not missing_include_files and not missing_include_prefixes else "attention",
        "summary": {
            "include_file_count": len(include_files),
            "include_prefix_count": len(include_prefixes),
            "missing_include_file_count": len(missing_include_files),
            "missing_include_prefix_count": len(missing_include_prefixes),
            "excluded_file_count": len(excluded_files),
            "excluded_prefix_count": len(PUBLIC_EXCLUDED_PREFIXES),
        },
        "include_files": include_files,
        "include_prefixes": include_prefixes,
        "excluded_files": excluded_files,
        "excluded_prefixes": _excluded_prefix_presence(resolved_vault),
        "missing_include_files": missing_include_files,
        "missing_include_prefixes": missing_include_prefixes,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Snapshot the public mirror include/exclude policy surface.")
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
