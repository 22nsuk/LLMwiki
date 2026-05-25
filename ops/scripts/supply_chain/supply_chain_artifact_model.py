#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.cyclonedx_sbom import (
        _build_components,
        _build_dependencies,
        _build_metadata,
        _extract_project_identity,
        _locked_dependency_edge_count,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.sbom_export_mapping import (
        build_report as build_sbom_export_mapping_report,
    )
    from ops.scripts.schema_constants_runtime import (
        SUPPLY_CHAIN_ARTIFACT_MODEL_SCHEMA_PATH,
    )
    from ops.scripts.security_advisories import (
        build_report as build_security_advisories_report,
    )
    from ops.scripts.supply_chain_provenance import (
        build_report as build_supply_chain_provenance_report,
    )
else:
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        SUPPLY_CHAIN_ARTIFACT_MODEL_SCHEMA_PATH,
    )

    from .cyclonedx_sbom import (
        _build_components,
        _build_dependencies,
        _build_metadata,
        _extract_project_identity,
        _locked_dependency_edge_count,
    )
    from .sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from .security_advisories import build_report as build_security_advisories_report
    from .supply_chain_provenance import (
        build_report as build_supply_chain_provenance_report,
    )


DEFAULT_OUT = "ops/reports/supply-chain-artifact-model.json"
DEFAULT_SECURITY_ADVISORIES_REF = "ops/reports/security-advisories.json"
TOOL_NAME = "ops.scripts.supply_chain_artifact_model"
ARTIFACT_KIND = "supply_chain_artifact_model"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.supply_chain_artifact_model"


def _artifact_set_id(root_ref: str, generated_at: str) -> str:
    return hashlib.sha256(f"{root_ref}|{generated_at}".encode()).hexdigest()[:16]


def _artifact_context(artifact_set_id: str) -> dict[str, str]:
    return {
        "artifact_set_id": artifact_set_id,
        "security_advisories_ref": "ops/reports/security-advisories.json",
        "model_ref": DEFAULT_OUT,
        "cyclonedx_ref": "ops/reports/cyclonedx-bom.json",
        "spdx_ref": "ops/reports/spdx-sbom.json",
        "openvex_ref": "ops/reports/openvex-draft.json",
        "in_toto_statement_ref": "ops/reports/in-toto-statement.json",
        "sigstore_bundle_ref": "ops/reports/sigstore-bundle-verification.json",
    }


def build_model(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    provenance_report: dict[str, Any] | None = None,
    mapping_report: dict[str, Any] | None = None,
    security_advisories_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    active_provenance_report = provenance_report or build_supply_chain_provenance_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
    )
    active_mapping_report = mapping_report or build_sbom_export_mapping_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
        provenance_report=active_provenance_report,
    )
    active_security_advisories_report = security_advisories_report or build_security_advisories_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
    )
    metadata = _build_metadata(vault, runtime_context.isoformat_z(), active_provenance_report, active_mapping_report)
    components, direct_runtime_refs, name_to_ref = _build_components(vault, active_provenance_report)
    root_ref = metadata["component"]["bom-ref"]
    project_name, project_version, _ = _extract_project_identity(vault)
    artifact_set_id = _artifact_set_id(root_ref, runtime_context.isoformat_z())

    report = {
        "$schema": SUPPLY_CHAIN_ARTIFACT_MODEL_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "tooling": {
            "generator": TOOL_NAME,
        },
        "subject": {
            "type": metadata["component"]["type"],
            "name": project_name,
            "version": project_version,
            "bom_ref": root_ref,
            "purl": metadata["component"]["purl"],
        },
        "provenance_summary": {
            "status": active_provenance_report["status"],
            "locked_package_count": len(active_provenance_report["locked_packages"]),
            "locked_dependency_edge_count": _locked_dependency_edge_count(active_provenance_report),
        },
        "mapping_summary": {
            "status": active_mapping_report["status"],
            "full_mapping_ready": active_mapping_report["sbom_readiness"]["full_mapping_ready"],
            "release_dependency_inputs_complete": active_mapping_report["sbom_readiness"]["release_dependency_inputs_complete"],
            "public_dependency_inputs_complete": active_mapping_report["sbom_readiness"]["public_dependency_inputs_complete"],
        },
        "artifact_context": _artifact_context(artifact_set_id),
        "components": components,
        "dependencies": _build_dependencies(
            vault,
            root_ref,
            direct_runtime_refs,
            components,
            name_to_ref,
            active_provenance_report,
        ),
        "advisories": [
            {
                "id": item["id"],
                "package": item["package"],
                "analysis_state": item["analysis"]["state"],
                "aliases": item["aliases"],
            }
            for item in active_security_advisories_report["advisories"]
        ],
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=runtime_context.isoformat_z(),
        artifact_kind=ARTIFACT_KIND,
        producer=TOOL_NAME,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=SUPPLY_CHAIN_ARTIFACT_MODEL_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/supply_chain_artifact_model.py",
            "ops/scripts/cyclonedx_sbom.py",
            "ops/scripts/security_advisories.py",
            "ops/scripts/supply_chain_provenance.py",
            "ops/scripts/sbom_export_mapping.py",
        ],
        text_inputs={
            "artifact_set_id": artifact_set_id,
            "provenance_status": str(active_provenance_report["status"]),
            "mapping_status": str(active_mapping_report["status"]),
            "advisory_count": str(len(active_security_advisories_report["advisories"])),
        },
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_model(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SUPPLY_CHAIN_ARTIFACT_MODEL_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="Supply-chain artifact model schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the canonical supply-chain artifact model")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_model(vault, policy_path=args.policy_path)
    destination = write_model(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
