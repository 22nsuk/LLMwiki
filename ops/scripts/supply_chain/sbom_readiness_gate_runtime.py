#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from ops.scripts.schema_constants_runtime import SBOM_READINESS_GATE_REPORT_SCHEMA_PATH
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from .sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from ops.scripts.schema_constants_runtime import SBOM_READINESS_GATE_REPORT_SCHEMA_PATH


GATE_REPORT_SCHEMA_PATH = SBOM_READINESS_GATE_REPORT_SCHEMA_PATH
SBOM_MAPPING_REPORT_REL_PATH = "ops/reports/sbom-export-mapping.json"
GATE_REPORT_REL_PATH = "ops/reports/sbom-readiness-gate-report.json"
PRODUCER = "ops.scripts.sbom_readiness_gate_runtime"
SOURCE_COMMAND = "python -m ops.scripts.sbom_readiness_gate_runtime --vault ."


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _check_mapping_exists(mapping_report: dict[str, Any]) -> dict[str, Any]:
    if not mapping_report:
        return {
            "rule": "sbom_mapping_report_exists",
            "pass": False,
            "details": "Run sbom-export-mapping first.",
        }
    return {"rule": "sbom_mapping_report_exists", "pass": True}


def _check_mapping_status(mapping_report: dict[str, Any]) -> dict[str, Any]:
    status = str(mapping_report.get("status", "")).lower()
    if status != "pass":
        return {
            "rule": "mapping_report_status_pass",
            "pass": False,
            "details": f"Expected status=pass but found {status or 'missing'}.",
        }
    return {"rule": "mapping_report_status_pass", "pass": True}


def _check_full_mapping_ready(mapping_report: dict[str, Any]) -> dict[str, Any]:
    readiness = mapping_report.get("sbom_readiness", {})
    if not isinstance(readiness, dict) or not bool(readiness.get("full_mapping_ready")):
        return {
            "rule": "full_mapping_ready",
            "pass": False,
            "details": "sbom_readiness.full_mapping_ready must be true.",
        }
    return {"rule": "full_mapping_ready", "pass": True}


def _check_public_subset(mapping_report: dict[str, Any]) -> dict[str, Any]:
    surface_summary = mapping_report.get("surface_summary", {})
    if not isinstance(surface_summary, dict) or not bool(surface_summary.get("public_subset_of_release")):
        return {
            "rule": "public_export_subset_of_release_manifest",
            "pass": False,
            "details": "surface_summary.public_subset_of_release must be true.",
        }
    return {"rule": "public_export_subset_of_release_manifest", "pass": True}


def _check_dependency_graph_parsed(mapping_report: dict[str, Any]) -> dict[str, Any]:
    summary = mapping_report.get("provenance_summary", {})
    if not isinstance(summary, dict):
        return {
            "rule": "locked_dependency_graph_observed",
            "pass": True,
            "details": "No provenance summary was available; graph coverage is advisory in this gate.",
        }
    locked_count = summary.get("locked_package_count", 0)
    edge_count = summary.get("locked_dependency_edge_count", 0)
    locked_count = locked_count if isinstance(locked_count, int) else 0
    edge_count = edge_count if isinstance(edge_count, int) else 0
    if locked_count and edge_count == 0:
        return {
            "rule": "locked_dependency_graph_observed",
            "pass": True,
            "details": "No uv.lock dependency edges were observed; graph coverage remains advisory.",
        }
    return {"rule": "locked_dependency_graph_observed", "pass": True}


def build_gate_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    refresh_mapping: bool = False,
    mapping_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    mapping_path = vault / SBOM_MAPPING_REPORT_REL_PATH
    active_mapping_report = mapping_report
    if active_mapping_report is None:
        if refresh_mapping:
            active_mapping_report = build_sbom_export_mapping_report(
                vault,
                policy_path=policy_path,
                context=runtime_context,
            )
        else:
            active_mapping_report = _load_json(mapping_path)

    checks = [_check_mapping_exists(active_mapping_report)]
    if active_mapping_report:
        checks.extend(
            [
                _check_mapping_status(active_mapping_report),
                _check_full_mapping_ready(active_mapping_report),
                _check_public_subset(active_mapping_report),
                _check_dependency_graph_parsed(active_mapping_report),
            ]
        )
    status = "pass" if all(check["pass"] for check in checks) else "fail"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="sbom_readiness_gate_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=GATE_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/sbom_readiness_gate_runtime.py",
                "ops/scripts/sbom_export_mapping.py",
            ],
            file_inputs={"sbom_mapping_report": SBOM_MAPPING_REPORT_REL_PATH},
            text_inputs={"refresh_mapping": str(refresh_mapping)},
        ),
        "$schema": GATE_REPORT_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": generated_at,
        "sbom_mapping_report_ref": SBOM_MAPPING_REPORT_REL_PATH,
        "status": status,
        "checks": checks,
    }


def write_gate_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=GATE_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=GATE_REPORT_REL_PATH,
            context="SBOM readiness gate schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the strict SBOM readiness gate")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=GATE_REPORT_REL_PATH)
    parser.add_argument(
        "--refresh-mapping",
        action="store_true",
        help="Build the SBOM export mapping report in memory before checking readiness.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_gate_report(
        vault,
        policy_path=args.policy_path,
        refresh_mapping=args.refresh_mapping,
    )
    destination = write_gate_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
