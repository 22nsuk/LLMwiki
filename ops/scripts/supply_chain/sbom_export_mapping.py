#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import (  # noqa: PLC0415
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.export_public_repo import iter_public_files
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import SBOM_EXPORT_MAPPING_SCHEMA_PATH
    from ops.scripts.supply_chain_provenance import build_report as build_supply_chain_provenance_report
    from ops.scripts.wiki_manifest import build_manifest, release_manifest_excludes_path
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope, embed_artifact_envelope_metadata
    from ops.scripts.export_public_repo import iter_public_files
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import SBOM_EXPORT_MAPPING_SCHEMA_PATH
    from .supply_chain_provenance import build_report as build_supply_chain_provenance_report
    from ops.scripts.wiki_manifest import build_manifest, release_manifest_excludes_path


SBOM_EXPORT_MAPPING_SCHEMA = SBOM_EXPORT_MAPPING_SCHEMA_PATH
DEFAULT_OUT = "ops/reports/sbom-export-mapping.json"
DEPENDENCY_INPUT_PATHS = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "uv.lock",
)


def _path_category(rel_path: str) -> str:
    if rel_path.startswith(".codex/agents/"):
        return "agent-config"
    if rel_path.startswith(".github/"):
        return "ci-workflow"
    if rel_path in DEPENDENCY_INPUT_PATHS:
        return "dependency-input"
    if rel_path.startswith("ops/"):
        return "ops"
    if rel_path.startswith("tests/"):
        return "tests"
    if rel_path.startswith("tools/"):
        return "tools"
    return "root-metadata"


def _dependency_input_mapping(
    provenance_report: dict,
    release_files: set[str],
    public_files: set[str],
) -> list[dict]:
    mapping = []
    for item in provenance_report["inputs"]:
        mapping.append(
            {
                "path": item["path"],
                "exists": item["exists"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
                "parser_status": item["parser_status"],
                "in_release_manifest": item["path"] in release_files,
                "in_public_export": item["path"] in public_files,
            }
        )
    return mapping


def _export_mapping(release_files: set[str], public_files: set[str]) -> list[dict]:
    mapping = []
    for rel_path in sorted(release_files | public_files):
        in_public_export = rel_path in public_files
        release_manifest_exclusion = bool(in_public_export and rel_path not in release_files and release_manifest_excludes_path(rel_path))
        mapping.append(
            {
                "path": rel_path,
                "category": _path_category(rel_path),
                "in_release_manifest": rel_path in release_files,
                "in_public_export": in_public_export,
                "release_manifest_exclusion": release_manifest_exclusion,
                "visibility": "public" if in_public_export else "private",
            }
        )
    return mapping


def _surface_summary(release_files: set[str], public_files: set[str]) -> dict:
    private_release_files = release_files - public_files
    public_only_files = public_files - release_files
    release_excluded_public_files = {
        rel_path for rel_path in public_only_files if release_manifest_excludes_path(rel_path)
    }
    blocking_public_only_files = public_only_files - release_excluded_public_files
    return {
        "release_manifest_file_count": len(release_files),
        "public_export_file_count": len(public_files),
        "private_release_file_count": len(private_release_files),
        "public_only_file_count": len(public_only_files),
        "release_excluded_public_file_count": len(release_excluded_public_files),
        "blocking_public_only_file_count": len(blocking_public_only_files),
        "public_subset_of_release": not blocking_public_only_files,
    }


def _gaps(
    provenance_report: dict,
    surface_summary: dict,
    dependency_input_mapping: list[dict],
) -> list[dict]:
    gaps: list[dict] = []
    if provenance_report["status"] == "fail":
        gaps.append(
            {
                "severity": "fail",
                "code": "provenance-report-failed",
                "details": "Supply-chain provenance already failed and must be fixed before SBOM/export graduation.",
            }
        )
    elif provenance_report["status"] == "warn":
        gaps.append(
            {
                "severity": "warn",
                "code": "provenance-report-warn",
                "details": "Supply-chain provenance contains missing-but-nonfatal inputs and should be cleaned before strict SBOM/export rollout.",
            }
        )

    if int(surface_summary["blocking_public_only_file_count"]) > 0:
        gaps.append(
            {
                "severity": "fail",
                "code": "public-surface-outside-release-manifest",
                "details": "Public export contains non-exempt files missing from the release manifest, so release/public provenance parity is broken.",
            }
        )

    if not provenance_report["locked_packages"]:
        gaps.append(
            {
                "severity": "warn",
                "code": "locked-package-inventory-empty",
                "path": "uv.lock",
                "details": "Locked package inventory is empty, so exact SBOM component coverage is incomplete.",
            }
        )

    if not provenance_report["ci_install_proof"]["workflow_exists"]:
        gaps.append(
            {
                "severity": "warn",
                "code": "ci-install-proof-missing",
                "path": ".github/workflows/ci.yml",
                "details": "CI install proof is missing, so installation evidence is not mapped into the export surface.",
            }
        )

    for item in dependency_input_mapping:
        if not item["in_release_manifest"]:
            gaps.append(
                {
                    "severity": "fail",
                    "code": "dependency-input-missing-from-release-manifest",
                    "path": item["path"],
                    "details": "Dependency evidence exists outside the release manifest surface.",
                }
            )
        if not item["in_public_export"]:
            gaps.append(
                {
                    "severity": "warn",
                    "code": "dependency-input-missing-from-public-export",
                    "path": item["path"],
                    "details": "Dependency evidence is not mirrored into the public export surface.",
                }
            )
    return gaps


def _sbom_readiness(
    provenance_report: dict,
    dependency_input_mapping: list[dict],
    surface_summary: dict,
    gaps: list[dict],
) -> dict:
    release_dependency_inputs_complete = all(item["in_release_manifest"] for item in dependency_input_mapping)
    public_dependency_inputs_complete = all(item["in_public_export"] for item in dependency_input_mapping)
    return {
        "declared_dependencies_present": bool(provenance_report["declared_dependencies"]),
        "locked_packages_present": bool(provenance_report["locked_packages"]),
        "ci_install_proof_present": bool(provenance_report["ci_install_proof"]["workflow_exists"]),
        "source_package_evidence_present": provenance_report["source_package_evidence"]["exists"],
        "source_package_reproducible": (
            provenance_report["source_package_evidence"]["status"] == "pass"
            and provenance_report["source_package_evidence"]["source_package_reproducibility_status"] == "pass"
        ),
        "release_dependency_inputs_complete": release_dependency_inputs_complete,
        "public_dependency_inputs_complete": public_dependency_inputs_complete,
        "full_mapping_ready": (
            provenance_report["status"] == "pass"
            and surface_summary["public_subset_of_release"]
            and release_dependency_inputs_complete
            and public_dependency_inputs_complete
            and not gaps
        ),
    }


def _locked_dependency_edge_count(provenance_report: dict) -> int:
    count = 0
    for package in provenance_report.get("locked_packages", []):
        dependencies = package.get("dependencies", [])
        if isinstance(dependencies, list):
            count += len(dependencies)
    return count


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    provenance_report: dict | None = None,
) -> dict:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    active_provenance_report = provenance_report or build_supply_chain_provenance_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
    )
    release_files = {
        str(item["path"])
        for item in build_manifest(vault, vault / "ops" / "manifest.json").get("files", [])
        if isinstance(item, dict)
    }
    public_files = set(iter_public_files(vault))
    dependency_input_mapping = _dependency_input_mapping(active_provenance_report, release_files, public_files)
    surface_summary = _surface_summary(release_files, public_files)
    gaps = _gaps(active_provenance_report, surface_summary, dependency_input_mapping)
    sbom_readiness = _sbom_readiness(active_provenance_report, dependency_input_mapping, surface_summary, gaps)

    has_fail = any(item["severity"] == "fail" for item in gaps)
    has_warn = any(item["severity"] == "warn" for item in gaps)
    status = "fail" if has_fail else ("warn" if has_warn else "pass")

    report = {
        "$schema": SBOM_EXPORT_MAPPING_SCHEMA,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "provenance_summary": {
            "status": active_provenance_report["status"],
            "input_count": len(active_provenance_report["inputs"]),
            "declared_dependency_count": len(active_provenance_report["declared_dependencies"]),
            "dev_dependency_count": len(active_provenance_report["dev_dependencies"]),
            "requirements_entry_count": len(active_provenance_report["requirements"]),
            "dev_requirements_entry_count": len(active_provenance_report["dev_requirements"]),
            "locked_package_count": len(active_provenance_report["locked_packages"]),
            "locked_dependency_edge_count": _locked_dependency_edge_count(active_provenance_report),
            "ci_workflow_exists": active_provenance_report["ci_install_proof"]["workflow_exists"],
            "ci_install_command_count": len(active_provenance_report["ci_install_proof"]["install_commands"]),
            "source_package_evidence_status": active_provenance_report["source_package_evidence"]["status"],
            "source_package_reproducibility_status": active_provenance_report["source_package_evidence"][
                "source_package_reproducibility_status"
            ],
            "source_zip_sha256": active_provenance_report["source_package_evidence"]["source_zip_sha256"],
        },
        "surface_summary": surface_summary,
        "sbom_readiness": sbom_readiness,
        "dependency_input_mapping": dependency_input_mapping,
        "export_mapping": _export_mapping(release_files, public_files),
        "gaps": gaps,
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=runtime_context.isoformat_z(),
        artifact_kind="sbom_export_mapping_report",
        producer="ops.scripts.sbom_export_mapping",
        source_command="python -m ops.scripts.sbom_export_mapping --vault . --out ops/reports/sbom-export-mapping.json",
        resolved_policy_path=resolved_policy_path,
        schema_path=SBOM_EXPORT_MAPPING_SCHEMA,
        source_paths=[
            "ops/scripts/sbom_export_mapping.py",
            "ops/scripts/export_public_repo.py",
            "ops/scripts/supply_chain_provenance.py",
            "ops/scripts/wiki_manifest.py",
            "ops/scripts/artifact_freshness_runtime.py",
        ],
        file_inputs={
            "ops_manifest": "ops/manifest.json",
        },
        path_group_inputs={
            "release_manifest_files": sorted(release_files),
            "public_export_files": sorted(public_files),
        },
        text_inputs={
            "status": status,
            "provenance_generated_at": str(active_provenance_report.get("generated_at", "")),
        },
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_report(vault: Path, report: dict, out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SBOM_EXPORT_MAPPING_SCHEMA,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="SBOM export mapping schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] in {"pass", "warn"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
