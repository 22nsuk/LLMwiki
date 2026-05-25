#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,  # noqa: PLC0415
    )
    from ops.scripts.artifact_io_runtime import (  # noqa: PLC0415
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.external_report_lifecycle_runtime import (  # noqa: PLC0415
        ACTION_CATALOG,
        REFERENCE_MANIFEST,
        active_report_paths,
        archived_report_count,
        reference_manifest_alignment,
        report_coverage_item,
        status_from_evidence,
    )
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.policy_runtime import load_policy, report_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext

    from .external_report_lifecycle_runtime import (
        ACTION_CATALOG,
        REFERENCE_MANIFEST,
        active_report_paths,
        archived_report_count,
        reference_manifest_alignment,
        report_coverage_item,
        status_from_evidence,
    )


DEFAULT_OUT = "ops/reports/external-report-action-matrix.json"
PRODUCER = "ops.scripts.external_report_action_matrix"
SCHEMA_PATH = "ops/schemas/external-report-action-matrix.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.external_report_action_matrix --vault ."


def _action_items(vault: Path, coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_by_action: dict[str, list[str]] = {str(action["action_id"]): [] for action in ACTION_CATALOG}
    for item in coverage:
        for action_id in item["matched_action_ids"]:
            source_by_action.setdefault(str(action_id), []).append(str(item["path"]))
    action_items: list[dict[str, Any]] = []
    for action in ACTION_CATALOG:
        status, evidence = status_from_evidence(vault, action)
        action_items.append(
            {
                "action_id": action["action_id"],
                "priority": action["priority"],
                "theme": action["theme"],
                "current_status": status,
                "source_report_paths": sorted(set(source_by_action[str(action["action_id"])])),
                "recommended_target": action["recommended_target"],
                "evidence": evidence,
            }
        )
    return action_items


def _report_coverage(vault: Path, paths: list[Path]) -> list[dict[str, Any]]:
    return [report_coverage_item(vault, path) for path in paths]


def _summary(
    *,
    coverage: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    archived_report_count: int,
    manifest_alignment: dict[str, Any],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for action in actions:
        status = str(action["current_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "active_report_count": len(coverage),
        "archived_report_count": archived_report_count,
        "action_item_count": len(actions),
        "implemented_count": status_counts.get("implemented", 0),
        "partially_automated_count": status_counts.get("partially_automated", 0),
        "requires_release_run_verification_count": status_counts.get("requires_release_run_verification", 0),
        "planned_count": status_counts.get("planned", 0),
        "unmatched_active_report_count": sum(
            1 for item in coverage if int(item["matched_action_count"]) == 0
        ),
        "reference_manifest_alignment_status": manifest_alignment["status"],
        "reference_manifest_missing_active_report_count": len(
            manifest_alignment["missing_active_report_paths"]
        ),
        "reference_manifest_stale_reference_count": len(manifest_alignment["stale_reference_paths"]),
    }


def _stabilize_self_evidence(actions: list[dict[str, Any]], *, status: str) -> None:
    for action in actions:
        for evidence in action.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            if evidence.get("path") == DEFAULT_OUT:
                evidence["status"] = status
                evidence["producer"] = PRODUCER


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    report_paths = active_report_paths(resolved_vault)
    coverage = _report_coverage(resolved_vault, report_paths)
    actions = _action_items(resolved_vault, coverage)
    manifest_alignment = reference_manifest_alignment(resolved_vault)
    summary = _summary(
        coverage=coverage,
        actions=actions,
        archived_report_count=archived_report_count(resolved_vault),
        manifest_alignment=manifest_alignment,
    )
    status = (
        "attention"
        if (
            summary["planned_count"]
            or summary["partially_automated_count"]
            or summary["requires_release_run_verification_count"]
            or summary["unmatched_active_report_count"]
            or summary["reference_manifest_alignment_status"] != "current"
        )
        else "pass"
    )
    _stabilize_self_evidence(actions, status=status)
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="external_report_action_matrix",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/external_report_action_matrix.py",
                "ops/scripts/external_report_lifecycle_runtime.py",
                "ops/scripts/external_report_reference_manifest.py",
            ],
            path_group_inputs={
                "active_external_reports": [report_path(resolved_vault, path) for path in report_paths],
            },
            text_inputs={
                "action_catalog": json.dumps(ACTION_CATALOG, ensure_ascii=False, sort_keys=True),
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "status": status,
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "summary": summary,
        "reference_manifest_alignment": manifest_alignment,
        "active_report_coverage": coverage,
        "action_items": actions,
        "archive_policy": {
            "active_root": "external-reports",
            "archive_root": "external-reports/archive",
            "reference_manifest": REFERENCE_MANIFEST,
            "archive_excluded_from_action_matching": True,
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
            context="external report action matrix schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a lifecycle/action matrix for non-archived external reports.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, context=None, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
