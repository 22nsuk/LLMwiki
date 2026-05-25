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
    from ops.scripts.source_revision_runtime import (
        resolve_source_revision,  # noqa: PLC0415
    )
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,  # noqa: PLC0415
    )
else:
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_revision_runtime import resolve_source_revision
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "tmp/release-authority-inventory.json"
PRODUCER = "ops.scripts.release_authority_inventory"
SCHEMA_PATH = "ops/schemas/release-authority-inventory.schema.json"
AUTHORITY_SURFACES = [
    {
        "id": "run_manifest",
        "question": "runnable",
        "authority_role": "authority_manifest",
        "owning_stage": "run-ready",
        "path": "build/release/release-run-manifest.json",
        "make_target": "release-run-ready",
        "check_target": "release-run-ready-check",
        "schema_path": "ops/schemas/release-run-manifest.schema.json",
        "producer": "ops.scripts.release_run_manifest",
        "verdict_fields": ["status"],
        "does_not_claim": ["sealed_package", "unattended_promotion"],
    },
    {
        "id": "sealed_run_manifest",
        "question": "sealed_package",
        "authority_role": "authority_manifest",
        "owning_stage": "sealed-run-ready",
        "path": "build/release/release-sealed-run-manifest.json",
        "make_target": "release-sealed-run-ready",
        "check_target": "release-sealed-run-ready-check",
        "schema_path": "ops/schemas/release-sealed-run-manifest.schema.json",
        "producer": "ops.scripts.release_sealed_run_manifest",
        "verdict_fields": ["status"],
        "does_not_claim": ["unattended_promotion"],
    },
    {
        "id": "auto_promotion_ready",
        "question": "unattended_promotion",
        "authority_role": "authority_manifest",
        "owning_stage": "auto-promotion-ready",
        "path": "build/release/release-auto-promotion-ready-manifest.json",
        "make_target": "release-auto-promotion-ready",
        "check_target": "release-auto-promotion-ready-check",
        "schema_path": "ops/schemas/release-auto-promotion-ready-manifest.schema.json",
        "producer": "ops.scripts.release_auto_promotion_ready",
        "verdict_fields": ["status", "promotion_ready"],
        "does_not_claim": [],
    },
    {
        "id": "closeout_finality_attestation",
        "question": "runnable",
        "authority_role": "diagnostic_bridge",
        "owning_stage": "finality",
        "path": "ops/reports/release-closeout-finality-attestation.json",
        "make_target": "release-closeout-finality-attestation",
        "check_target": "release-closeout-finality-verify",
        "schema_path": "ops/schemas/release-closeout-finality-attestation.schema.json",
        "producer": "ops.scripts.release_closeout_finality_attestation",
        "verdict_fields": ["status"],
        "does_not_claim": ["sealed_package", "unattended_promotion"],
    },
]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_revision(payload: dict[str, Any]) -> str:
    for key in ("source_revision", "commit", "git_revision"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    source = payload.get("source")
    if isinstance(source, dict):
        value = source.get("source_revision") or source.get("revision")
        if isinstance(value, str):
            return value
    return ""


def _surface_entry(vault: Path, spec: dict[str, Any], current_revision: str) -> dict[str, Any]:
    payload = _read_json(vault / str(spec["path"]))
    artifact_revision = _artifact_revision(payload)
    return {
        **spec,
        "exists": bool(payload),
        "artifact_status": str(payload.get("status", "")) if payload else "missing",
        "artifact_revision": artifact_revision,
        "stale_for_current_revision": bool(artifact_revision and artifact_revision != current_revision),
    }


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    revision = resolve_source_revision(resolved_vault)
    fingerprint = release_source_tree_fingerprint(resolved_vault)
    surfaces = [_surface_entry(resolved_vault, spec, revision.revision) for spec in AUTHORITY_SURFACES]
    stale = [item["id"] for item in surfaces if item["stale_for_current_revision"]]
    manifest_count = sum(1 for item in surfaces if item["authority_role"] == "authority_manifest")
    bridge_count = sum(1 for item in surfaces if item["authority_role"] == "diagnostic_bridge")
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_authority_inventory",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": "attention" if stale else "pass",
        "authority_claim": "none_inventory_only",
        "source_revision": revision.revision,
        "source_revision_status": revision.status,
        "source_tree_fingerprint": fingerprint,
        "summary": {
            "authority_manifest_count": manifest_count,
            "diagnostic_bridge_count": bridge_count,
            "stale_artifact_count": len(stale),
            "missing_artifact_count": sum(1 for item in surfaces if not item["exists"]),
        },
        "surfaces": surfaces,
        "stale_artifacts": stale,
        "deletion_cautions": [
            "Generated release evidence is retained evidence; refresh through Make targets instead of hand editing or deleting JSON.",
            "Compatibility aliases are not release authority and should be inventoried separately from authority manifests.",
        ],
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory release authority surfaces without issuing a verdict.")
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
