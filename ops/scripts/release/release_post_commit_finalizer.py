#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.release.release_run_manifest import _resolve, git_commit
from ops.scripts.release.release_source_ready_commit import (
    SOURCE_CONTRACT_CATEGORIES,
    classify_path,
    git_status_entries,
)

DEFAULT_OUT = "build/release/release-post-commit-finalization.json"
DEFAULT_SNAPSHOT_OUT = "tmp/release-post-commit-finalization.snapshot.json"
SCHEMA_PATH = "ops/schemas/release-post-commit-finalization.schema.json"
PRODUCER = "ops.scripts.release.release_post_commit_finalizer"
SOURCE_COMMAND = "python -m ops.scripts.release.release_post_commit_finalizer --vault ."
MODES = {"snapshot", "verify", "refresh"}

SOURCE_BLOCKING_CATEGORIES = {
    *SOURCE_CONTRACT_CATEGORIES,
    "unexpected",
}

AUTHORITY_INPUTS = [
    {
        "stage": "release-auto-promotion-preflight",
        "path": "build/release/release-auto-promotion-preflight.json",
        "artifact_kind": "release_auto_promotion_preflight",
        "owning_target": "release-auto-promotion-preflight",
    },
    {
        "stage": "release-run-ready",
        "path": "build/release/release-run-manifest.json",
        "artifact_kind": "release_run_manifest",
        "owning_target": "release-run-ready",
    },
    {
        "stage": "release-auto-promotion-preseal",
        "path": "build/release/release-auto-promotion-preseal.json",
        "artifact_kind": "release_auto_promotion_preflight",
        "owning_target": "release-auto-promotion-preseal",
    },
    {
        "stage": "release-sealed-run-ready",
        "path": "build/release/release-sealed-run-manifest.json",
        "artifact_kind": "release_sealed_run_manifest",
        "owning_target": "release-sealed-run-ready",
    },
    {
        "stage": "release-auto-promotion-ready",
        "path": "build/release/release-auto-promotion-ready-manifest.json",
        "artifact_kind": "release_auto_promotion_ready_manifest",
        "owning_target": "release-auto-promotion-ready",
    },
]


def _load_json(path: Path) -> dict[str, Any]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok" or not isinstance(payload, dict):
        return {}
    return payload


def _previous_snapshot(vault: Path, previous_path: str | None) -> dict[str, Any]:
    if not previous_path:
        return {}
    return _load_json(_resolve(vault, previous_path))


def _dirty_entries(vault: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    try:
        status_entries = git_status_entries(vault)
    except RuntimeError:
        return [
            {
                "path": "",
                "xy": "!!",
                "category": "unexpected",
            }
        ]
    for entry in status_entries:
        category = classify_path(entry.path)
        entries.append(
            {
                "path": entry.path,
                "xy": entry.xy,
                "category": category,
            }
        )
    return sorted(entries, key=lambda item: (item["path"], item["xy"]))


def _source_dirty_paths(entries: list[dict[str, str]]) -> list[str]:
    return sorted(
        {
            entry["path"]
            for entry in entries
            if entry["path"] and entry["category"] in SOURCE_BLOCKING_CATEGORIES
        }
    )


def _generated_dirty_paths(entries: list[dict[str, str]]) -> list[str]:
    return sorted(
        {
            entry["path"]
            for entry in entries
            if entry["path"] and entry["category"] == "generated_canonical"
        }
    )


def _artifact_status(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if isinstance(status, dict):
        return str(status.get("result", "")).strip()
    return str(status or "").strip()


def _authority_input(
    vault: Path,
    spec: dict[str, str],
    *,
    current_revision: str,
    current_fingerprint: str,
) -> dict[str, Any]:
    path = _resolve(vault, spec["path"])
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok" or not isinstance(payload, dict):
        payload = {}
    source_revision = str(payload.get("source_revision", "")).strip()
    source_tree_fingerprint = str(payload.get("source_tree_fingerprint", "")).strip()
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    status = _artifact_status(payload)
    issues: list[str] = []
    if diagnostics.get("status") != "ok":
        issues.append("not_loadable")
    if artifact_kind != spec["artifact_kind"]:
        issues.append("artifact_kind_mismatch")
    if source_revision != current_revision:
        issues.append("source_revision_stale" if source_revision else "source_revision_missing")
    if source_tree_fingerprint != current_fingerprint:
        issues.append(
            "source_tree_fingerprint_stale"
            if source_tree_fingerprint
            else "source_tree_fingerprint_missing"
        )
    return {
        "stage": spec["stage"],
        "path": spec["path"],
        "artifact_kind": artifact_kind,
        "expected_artifact_kind": spec["artifact_kind"],
        "status": status,
        "source_revision": source_revision,
        "source_tree_fingerprint": source_tree_fingerprint,
        "owning_target": spec["owning_target"],
        "current": not issues,
        "issues": issues,
    }


def _authority_inputs(
    vault: Path,
    *,
    current_revision: str,
    current_fingerprint: str,
) -> list[dict[str, Any]]:
    return [
        _authority_input(
            vault,
            spec,
            current_revision=current_revision,
            current_fingerprint=current_fingerprint,
        )
        for spec in AUTHORITY_INPUTS
    ]


def _first_stale_authority(authority_inputs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in authority_inputs:
        if not bool(item["current"]):
            return item
    return None


def _authority_readback(
    authority_inputs: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    stale_authority = _first_stale_authority(authority_inputs)
    evaluated = mode != "snapshot"
    stale_count = sum(1 for item in authority_inputs if not item["current"])
    minimal_next_target = (
        str(stale_authority["owning_target"])
        if evaluated and stale_authority is not None
        else "release-auto-promotion-ready"
    )
    return {
        "status": "attention" if evaluated and stale_authority is not None else "pass",
        "evaluated": evaluated,
        "blocker_class": "authority_stale" if evaluated and stale_authority is not None else "none",
        "owning_target": minimal_next_target,
        "minimal_next_target": minimal_next_target,
        "authority_stale_count": stale_count,
        "authority_inputs": authority_inputs,
    }


def build_report(
    vault: Path,
    *,
    mode: str = "verify",
    previous_path: str | None = None,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unsupported release post-commit finalizer mode: {mode}")
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    current_revision = git_commit(resolved_vault)
    current_fingerprint = release_source_tree_fingerprint(resolved_vault)
    previous = _previous_snapshot(resolved_vault, previous_path)
    previous_fingerprint = str(previous.get("source_tree_fingerprint_after", "")).strip()
    previous_revision = str(previous.get("source_revision", "")).strip()

    dirty_entries = _dirty_entries(resolved_vault)
    dirty_source_paths = _source_dirty_paths(dirty_entries)
    dirty_generated_paths = _generated_dirty_paths(dirty_entries)
    authority = _authority_inputs(
        resolved_vault,
        current_revision=current_revision,
        current_fingerprint=current_fingerprint,
    )
    authority_readback = _authority_readback(authority, mode=mode)

    fingerprint_changed_since_snapshot = bool(
        previous_fingerprint and previous_fingerprint != current_fingerprint
    )
    revision_changed_since_snapshot = bool(previous_revision and previous_revision != current_revision)
    if dirty_source_paths or fingerprint_changed_since_snapshot or revision_changed_since_snapshot:
        status = "fail"
        blocker_class = "source_tree_changed"
        owning_target = "release-source-ready-prepare"
        minimal_next_target = "release-source-ready-prepare"
    elif dirty_generated_paths:
        status = "attention"
        blocker_class = "generated_canonical_dirty"
        owning_target = "release-source-ready-prepare"
        minimal_next_target = "release-source-ready-prepare"
    else:
        status = "pass"
        blocker_class = "none"
        owning_target = "release-post-commit-finalize"
        minimal_next_target = "release-check-all-surfaces"

    changed_paths = sorted(
        {
            *dirty_source_paths,
            *dirty_generated_paths,
            *(
                ["<source-tree-fingerprint>"]
                if fingerprint_changed_since_snapshot
                else []
            ),
            *(["<source-revision>"] if revision_changed_since_snapshot else []),
        }
    )
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=generated_at,
            artifact_kind="release_post_commit_finalization",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/release_post_commit_finalizer.py",
                "mk/release.mk",
            ],
            file_inputs={"previous_snapshot": previous_path} if previous_path else {},
            text_inputs={
                "mode": mode,
                "authority_inputs": json.dumps(AUTHORITY_INPUTS, sort_keys=True),
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "mode": mode,
        "stage": "post-commit-finalization",
        "status": status,
        "blocker_class": blocker_class,
        "owning_target": owning_target,
        "minimal_next_target": minimal_next_target,
        "source_revision": current_revision,
        "source_tree_fingerprint_before": previous_fingerprint or current_fingerprint,
        "source_tree_fingerprint_after": current_fingerprint,
        "previous_source_revision": previous_revision,
        "changed_paths": changed_paths,
        "dirty_entries": dirty_entries,
        "dirty_source_paths": dirty_source_paths,
        "dirty_generated_paths": dirty_generated_paths,
        "authority_readback": authority_readback,
        "authority_inputs": authority,
        "summary": {
            "dirty_source_path_count": len(dirty_source_paths),
            "dirty_generated_path_count": len(dirty_generated_paths),
            "authority_stale_count": authority_readback["authority_stale_count"],
            "authority_readback_status": authority_readback["status"],
            "fingerprint_changed_since_snapshot": fingerprint_changed_since_snapshot,
            "revision_changed_since_snapshot": revision_changed_since_snapshot,
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release post-commit finalization schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build post-commit release evidence finalization diagnostics.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=sorted(MODES), default="verify")
    parser.add_argument("--previous")
    parser.add_argument(
        "--fail-on-attention",
        action="store_true",
        help="Return nonzero when finalization reports attention, for strict Make target use.",
    )
    parser.add_argument(
        "--fail-on-authority-attention",
        action="store_true",
        help="Return nonzero when nested release authority readback reports attention.",
    )
    parser.add_argument("--policy-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        mode=args.mode,
        previous_path=args.previous,
        policy_path=args.policy_path,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    print(f"release_post_commit_finalization_status={report['status']}")
    print(f"release_authority_readback_status={report['authority_readback']['status']}")
    if report["status"] == "fail" or (
        args.fail_on_attention and report["status"] == "attention"
    ) or (
        args.fail_on_authority_attention
        and report["authority_readback"]["status"] == "attention"
    ):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
