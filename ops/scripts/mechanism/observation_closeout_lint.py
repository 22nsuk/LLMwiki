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
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
else:
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/observation-closeout-lint.json"
DEFAULT_REGISTRY = "ops/observation-closeout-registry.json"
PRODUCER = "ops.scripts.observation_closeout_lint"
SCHEMA_PATH = "ops/schemas/observation-closeout-registry.schema.json"
OPEN_STATUSES = {"open", "planned"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _registry_keys(registry: dict[str, Any]) -> set[tuple[str, str]]:
    entries = registry.get("retained_observations", [])
    if not isinstance(entries, list):
        return set()
    return {
        (str(item.get("path", "")).strip(), str(item.get("observation_id", "")).strip())
        for item in entries
        if isinstance(item, dict)
    }


def _observation_files(vault: Path) -> list[Path]:
    roots = [
        vault / "ops" / "reports" / "task-improvement-observations",
        vault / "runs",
    ]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(root.rglob("improvement-observations.json"))
    return sorted(files)


def _open_observations(vault: Path) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for path in _observation_files(vault):
        payload = _read_json(path)
        rel_path = path.relative_to(vault).as_posix()
        for item in payload.get("observations", []):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).strip()
            if status not in OPEN_STATUSES:
                continue
            observations.append(
                {
                    "path": rel_path,
                    "observation_id": str(item.get("observation_id", "")).strip(),
                    "status": status,
                    "surface": str(item.get("surface", "")).strip(),
                    "suggested_followup": str(item.get("suggested_followup", "")).strip(),
                }
            )
    return observations


def build_report(
    vault: Path,
    *,
    registry_path: str = DEFAULT_REGISTRY,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    registry = _read_json(resolved_vault / registry_path)
    allowed = _registry_keys(registry)
    open_observations = _open_observations(resolved_vault)
    unregistered = [
        item
        for item in open_observations
        if (item["path"], item["observation_id"]) not in allowed
    ]
    observed_keys = {(item["path"], item["observation_id"]) for item in open_observations}
    stale_registry_entries = [
        {"path": path, "observation_id": observation_id}
        for path, observation_id in sorted(allowed - observed_keys)
    ]
    status = "pass" if not unregistered and not stale_registry_entries else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "observation_closeout_lint",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": status,
        "registry_path": registry_path,
        "summary": {
            "open_observation_count": len(open_observations),
            "registered_retained_count": len(allowed),
            "unregistered_open_count": len(unregistered),
            "stale_registry_entry_count": len(stale_registry_entries),
        },
        "open_observations": open_observations,
        "unregistered_open_observations": unregistered,
        "stale_registry_entries": stale_registry_entries,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint open improvement observations against closeout registry.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, registry_path=args.registry)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
