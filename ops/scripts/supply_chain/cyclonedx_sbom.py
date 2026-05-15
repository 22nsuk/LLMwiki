#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from ops.scripts.schema_constants_runtime import CYCLONEDX_16_SCHEMA_PATH, CYCLONEDX_16_SCHEMA_URI
    from ops.scripts.supply_chain_provenance import build_report as build_supply_chain_provenance_report
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
    from .sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from ops.scripts.schema_constants_runtime import CYCLONEDX_16_SCHEMA_PATH, CYCLONEDX_16_SCHEMA_URI
    from .supply_chain_provenance import build_report as build_supply_chain_provenance_report


CYCLONEDX_SCHEMA_PATH = CYCLONEDX_16_SCHEMA_PATH
DEFAULT_OUT = "ops/reports/cyclonedx-bom.json"
CANONICAL_VENDOR = "PyPI"
TOOL_NAME = "ops.scripts.cyclonedx_sbom"
SOURCE_COMMAND = "python -m ops.scripts.cyclonedx_sbom"
ARTIFACT_KIND = "cyclonedx_sbom"
ARTIFACT_ENVELOPE_PROPERTY = "urn:openai:artifact-envelope"
NAME_NORMALIZE_RE = re.compile(r"[-_.]+")


def canonicalize_package_name(name: str) -> str:
    return NAME_NORMALIZE_RE.sub("-", name.strip().lower())


def normalize_requirement_name(name: str) -> str:
    canonical = canonicalize_package_name(name)
    return canonical if canonical else name.strip().lower()


def safe_string(value: Any) -> str:
    return "" if value is None else str(value)


def encode_purl_name(name: str) -> str:
    return quote(name, safe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def make_pypi_purl(name: str, version: str = "") -> str:
    encoded_name = encode_purl_name(canonicalize_package_name(name))
    if version.strip():
        return f"pkg:pypi/{encoded_name}@{quote(version.strip(), safe='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')}"
    return f"pkg:pypi/{encoded_name}"


def make_generic_purl(name: str, version: str = "") -> str:
    encoded_name = encode_purl_name(name.strip() or "unnamed")
    if version.strip():
        return f"pkg:generic/{encoded_name}@{quote(version.strip(), safe='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')}"
    return f"pkg:generic/{encoded_name}"


def make_component_ref(name: str, version: str, component_type: str) -> str:
    if component_type == "application":
        return make_generic_purl(name, version)
    return make_pypi_purl(name, version)


def _property(name: str, value: Any) -> dict[str, str]:
    return {"name": name, "value": safe_string(value)}


def _extract_project_identity(vault: Path) -> tuple[str, str, str]:
    import tomllib

    pyproject_path = vault / "pyproject.toml"
    if not pyproject_path.exists():
        return vault.name, "", ""
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    if not isinstance(project, dict):
        return vault.name, "", ""
    license_value = project.get("license", "")
    if isinstance(license_value, dict):
        license_text = safe_string(license_value.get("text") or license_value.get("file") or "")
    else:
        license_text = safe_string(license_value)
    return (
        safe_string(project.get("name") or vault.name),
        safe_string(project.get("version")),
        license_text,
    )


def _build_metadata_component(vault: Path) -> dict[str, Any]:
    project_name, project_version, project_license = _extract_project_identity(vault)
    component = {
        "type": "application",
        "bom-ref": make_component_ref(project_name, project_version, "application"),
        "name": project_name,
        "version": project_version,
        "purl": make_generic_purl(project_name, project_version),
        "properties": [
            _property("urn:openai:sbom:project-root", "true"),
            _property("urn:openai:sbom:source-path", "."),
        ],
    }
    if project_license:
        component["licenses"] = [{"license": {"name": project_license}}]
    return component


def _tool_components() -> list[dict[str, Any]]:
    return [
        {
            "type": "application",
            "name": TOOL_NAME,
            "version": "0.1.0-draft",
            "bom-ref": make_generic_purl(TOOL_NAME, "0.1.0-draft"),
        }
    ]


def _envelope_file_inputs(vault: Path, provenance_report: dict) -> dict[str, str]:
    file_inputs: dict[str, str] = {}
    candidate_inputs = {
        "pyproject": "pyproject.toml",
        "requirements": "requirements.txt",
        "requirements_dev": "requirements-dev.txt",
        "lock": "uv.lock",
    }
    workflow_path = provenance_report.get("ci_install_proof", {}).get("workflow_path")
    if isinstance(workflow_path, str) and workflow_path.strip():
        candidate_inputs["ci_workflow"] = workflow_path.strip()
    for name, rel_path in candidate_inputs.items():
        if (vault / rel_path).exists():
            file_inputs[name] = rel_path
    return file_inputs


def _embedded_artifact_envelope_property(artifact_envelope: dict[str, Any]) -> dict[str, str]:
    return _property(
        ARTIFACT_ENVELOPE_PROPERTY,
        json.dumps(artifact_envelope, ensure_ascii=False, sort_keys=True),
    )


def _metadata_properties(
    provenance_report: dict,
    mapping_report: dict,
    artifact_envelope: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    source_package = provenance_report.get("source_package_evidence", {})
    if not isinstance(source_package, dict):
        source_package = {}
    properties = [
        _property("urn:openai:sbom:canonical-format", "cyclonedx-json"),
        _property("urn:openai:sbom:canonical-spec-version", "1.6"),
        _property("urn:openai:sbom:spdx-emitter-decision", "shared-artifact-model-spdx-enabled"),
        _property("urn:openai:sbom:model-ref", "ops/reports/supply-chain-artifact-model.json"),
        _property("urn:openai:sbom:spdx-ref", "ops/reports/spdx-sbom.json"),
        _property("urn:openai:sbom:openvex-ref", "ops/reports/openvex-draft.json"),
        _property("urn:openai:sbom:provenance-status", provenance_report["status"]),
        _property("urn:openai:sbom:mapping-status", mapping_report["status"]),
        _property("urn:openai:sbom:locked-dependency-edge-count", _locked_dependency_edge_count(provenance_report)),
        _property("urn:openai:sbom:source-package-status", source_package.get("status", "missing")),
        _property(
            "urn:openai:sbom:source-package-reproducibility-status",
            source_package.get("source_package_reproducibility_status", ""),
        ),
        _property("urn:openai:sbom:source-zip-sha256", source_package.get("source_zip_sha256", "")),
        _property("urn:openai:sbom:inputs:pyproject", "pyproject.toml"),
        _property("urn:openai:sbom:inputs:requirements", "requirements.txt"),
        _property("urn:openai:sbom:inputs:requirements-dev", "requirements-dev.txt"),
        _property("urn:openai:sbom:inputs:lock", "uv.lock"),
    ]
    if provenance_report["ci_install_proof"]["workflow_exists"]:
        properties.append(
            _property(
                "urn:openai:sbom:ci-workflow-path",
                provenance_report["ci_install_proof"]["workflow_path"],
            )
        )
    if artifact_envelope is not None:
        properties.append(_embedded_artifact_envelope_property(artifact_envelope))
    return properties


def _build_metadata(
    vault: Path,
    generated_at: str,
    provenance_report: dict,
    mapping_report: dict,
    artifact_envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": generated_at,
        "component": _build_metadata_component(vault),
        "tools": {"components": _tool_components()},
        "properties": _metadata_properties(provenance_report, mapping_report, artifact_envelope),
    }


def _requirement_names(items: list[dict]) -> set[str]:
    names: set[str] = set()
    for item in items:
        if item.get("kind") == "include":
            continue
        normalized = normalize_requirement_name(item.get("name", ""))
        if normalized:
            names.add(normalized)
    return names


def _runtime_requirement_names(provenance_report: dict) -> set[str]:
    names = _requirement_names(provenance_report.get("declared_dependencies", []))
    return names or _requirement_names(provenance_report.get("requirements", []))


def _dev_requirement_names(provenance_report: dict) -> set[str]:
    return _requirement_names(provenance_report.get("dev_dependencies", [])) | _requirement_names(
        provenance_report.get("dev_requirements", [])
    )


def _package_key(package: dict) -> str:
    return normalize_requirement_name(package.get("name", ""))


def _locked_package_by_name(provenance_report: dict) -> dict[str, dict]:
    packages: dict[str, dict] = {}
    for package in provenance_report.get("locked_packages", []):
        key = _package_key(package)
        if key:
            packages[key] = package
    return packages


def _locked_dependency_names(package: dict) -> list[str]:
    names = []
    for item in package.get("dependencies", []):
        normalized = normalize_requirement_name(item.get("name", ""))
        if normalized:
            names.append(normalized)
    return sorted(set(names))


def _find_editable_root_package(vault: Path, provenance_report: dict) -> dict | None:
    project_name, _, _ = _extract_project_identity(vault)
    project_key = normalize_requirement_name(project_name)
    for package in provenance_report.get("locked_packages", []):
        editable = safe_string(package.get("editable")).strip()
        if editable == "." or (project_key and _package_key(package) == project_key):
            return package
    return None


def _root_direct_dependency_names(vault: Path, provenance_report: dict) -> list[str]:
    root_package = _find_editable_root_package(vault, provenance_report)
    if root_package is not None:
        names = _locked_dependency_names(root_package)
        if names:
            return names
    return sorted(_runtime_requirement_names(provenance_report))


def _reachable_required_names(vault: Path, provenance_report: dict) -> set[str]:
    packages = _locked_package_by_name(provenance_report)
    pending = list(_root_direct_dependency_names(vault, provenance_report))
    seen: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        package = packages.get(name)
        if package is None:
            continue
        pending.extend(child for child in _locked_dependency_names(package) if child not in seen)
    return seen


def _component_scope(package_name: str, required_names: set[str], dev_names: set[str]) -> str:
    normalized = normalize_requirement_name(package_name)
    if normalized in required_names:
        return "required"
    if normalized in dev_names or required_names:
        return "excluded"
    return "required"


def _registry_from_locked_package(package: dict) -> str:
    registry = safe_string(package.get("registry")).strip()
    return registry if registry else CANONICAL_VENDOR


def _locked_component_properties(package: dict, source_kind: str) -> list[dict[str, str]]:
    properties = [
        _property("urn:openai:sbom:component-source", source_kind),
        _property("urn:openai:sbom:registry", package.get("registry", "")),
        _property("urn:openai:sbom:editable", package.get("editable", "")),
        _property("urn:openai:sbom:wheel-count", package.get("wheel_count", 0)),
        _property("urn:openai:sbom:dependency-count", len(package.get("dependencies", []))),
    ]
    sdist = package.get("sdist", {})
    if isinstance(sdist, dict):
        if safe_string(sdist.get("url")).strip():
            properties.append(_property("urn:openai:sbom:sdist-url", sdist["url"]))
        if safe_string(sdist.get("hash")).strip():
            properties.append(_property("urn:openai:sbom:sdist-hash", sdist["hash"]))
        if safe_string(sdist.get("upload_time")).strip():
            properties.append(_property("urn:openai:sbom:sdist-upload-time", sdist["upload_time"]))
    wheel_hashes = package.get("wheel_hashes_sample", [])
    if isinstance(wheel_hashes, list):
        for index, value in enumerate(wheel_hashes[:5], start=1):
            properties.append(_property(f"urn:openai:sbom:wheel-hash:{index}", value))
    return properties


def _component_from_locked_package(
    package: dict,
    required_names: set[str],
    dev_names: set[str],
) -> dict[str, Any] | None:
    name = safe_string(package.get("name")).strip()
    version = safe_string(package.get("version")).strip()
    if not name:
        return None
    ref = make_component_ref(name, version, "library")
    return {
        "type": "library",
        "bom-ref": ref,
        "name": name,
        "version": version,
        "scope": _component_scope(name, required_names, dev_names),
        "purl": make_pypi_purl(name, version),
        "publisher": _registry_from_locked_package(package),
        "properties": _locked_component_properties(package, "uv.lock"),
    }


def _component_from_requirement(
    item: dict,
    *,
    source_kind: str,
    scope: str,
) -> dict[str, Any] | None:
    if item.get("kind") == "include":
        return None
    name = safe_string(item.get("name")).strip()
    requirement = safe_string(item.get("requirement")).strip()
    if not name:
        return None
    ref = make_component_ref(name, "", "library")
    return {
        "type": "library",
        "bom-ref": ref,
        "name": name,
        "scope": scope,
        "purl": make_pypi_purl(name, ""),
        "publisher": CANONICAL_VENDOR,
        "properties": [
            _property("urn:openai:sbom:component-source", source_kind),
            _property("urn:openai:sbom:requirement", requirement),
        ],
    }


def _merge_component(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    if not safe_string(merged.get("version")).strip() and safe_string(candidate.get("version")).strip():
        merged["version"] = candidate["version"]
        merged["bom-ref"] = candidate["bom-ref"]
        merged["purl"] = candidate["purl"]
    if merged.get("scope") == "excluded" and candidate.get("scope") == "required":
        merged["scope"] = "required"
    merged_properties = []
    seen_properties: set[tuple[str, str]] = set()
    for item in list(existing.get("properties", [])) + list(candidate.get("properties", [])):
        key = (safe_string(item.get("name")), safe_string(item.get("value")))
        if key in seen_properties:
            continue
        seen_properties.add(key)
        merged_properties.append({"name": key[0], "value": key[1]})
    if merged_properties:
        merged["properties"] = merged_properties
    if not safe_string(merged.get("publisher")).strip() and safe_string(candidate.get("publisher")).strip():
        merged["publisher"] = candidate["publisher"]
    return merged


def _build_components(vault: Path, provenance_report: dict) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    required_names = _reachable_required_names(vault, provenance_report)
    dev_names = _dev_requirement_names(provenance_report)
    root_package = _find_editable_root_package(vault, provenance_report)
    root_key = _package_key(root_package) if root_package else ""
    by_name: dict[str, dict[str, Any]] = {}

    for package in provenance_report.get("locked_packages", []):
        normalized = _package_key(package)
        if not normalized or normalized == root_key:
            continue
        component = _component_from_locked_package(package, required_names, dev_names)
        if component is None:
            continue
        by_name[normalized] = _merge_component(by_name[normalized], component) if normalized in by_name else component

    if not by_name:
        for item in provenance_report.get("declared_dependencies", []):
            component = _component_from_requirement(item, source_kind=item.get("source", "pyproject.toml"), scope="required")
            if component is None:
                continue
            normalized = normalize_requirement_name(component["name"])
            by_name[normalized] = _merge_component(by_name[normalized], component) if normalized in by_name else component

    for item in provenance_report.get("dev_dependencies", []):
        component = _component_from_requirement(item, source_kind=item.get("source", "pyproject.toml"), scope="excluded")
        if component is None:
            continue
        normalized = normalize_requirement_name(component["name"])
        by_name[normalized] = _merge_component(by_name[normalized], component) if normalized in by_name else component

    if not by_name:
        for item in provenance_report.get("requirements", []):
            component = _component_from_requirement(item, source_kind=item.get("source", "requirements.txt"), scope="required")
            if component is None:
                continue
            normalized = normalize_requirement_name(component["name"])
            by_name[normalized] = _merge_component(by_name[normalized], component) if normalized in by_name else component

    for item in provenance_report.get("dev_requirements", []):
        component = _component_from_requirement(item, source_kind=item.get("source", "requirements-dev.txt"), scope="excluded")
        if component is None:
            continue
        normalized = normalize_requirement_name(component["name"])
        by_name[normalized] = _merge_component(by_name[normalized], component) if normalized in by_name else component

    components = sorted(by_name.values(), key=lambda item: (safe_string(item.get("scope")), safe_string(item.get("name")).lower()))
    name_to_ref = {normalize_requirement_name(item["name"]): item["bom-ref"] for item in components}
    direct_runtime_refs = [name_to_ref[name] for name in _root_direct_dependency_names(vault, provenance_report) if name in name_to_ref]
    return components, sorted(set(direct_runtime_refs)), name_to_ref


def _locked_dependency_edge_count(provenance_report: dict) -> int:
    count = 0
    for package in provenance_report.get("locked_packages", []):
        dependencies = package.get("dependencies", [])
        if isinstance(dependencies, list):
            count += len(dependencies)
    return count


def _build_dependencies(
    vault: Path,
    root_ref: str,
    direct_runtime_refs: list[str],
    components: list[dict[str, Any]],
    name_to_ref: dict[str, str],
    provenance_report: dict,
) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = [{"ref": root_ref, "dependsOn": sorted(set(direct_runtime_refs))}]
    root_package = _find_editable_root_package(vault, provenance_report)
    root_key = _package_key(root_package) if root_package else ""
    component_refs = {item["bom-ref"] for item in components}
    for package in provenance_report.get("locked_packages", []):
        package_key = _package_key(package)
        if not package_key or package_key == root_key:
            continue
        ref = name_to_ref.get(package_key)
        if ref is None or ref not in component_refs:
            continue
        depends_on = [
            name_to_ref[name]
            for name in _locked_dependency_names(package)
            if name in name_to_ref and name_to_ref[name] in component_refs
        ]
        dependencies.append({"ref": ref, "dependsOn": sorted(set(depends_on))})
    if len(dependencies) == 1:
        dependencies.extend({"ref": item["bom-ref"], "dependsOn": []} for item in components)
    return dependencies


def build_bom(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    provenance_report: dict[str, Any] | None = None,
    mapping_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    active_provenance_report = provenance_report or build_supply_chain_provenance_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
    )
    active_mapping_report = mapping_report or build_sbom_export_mapping_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
    )
    artifact_envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=ARTIFACT_KIND,
        producer=TOOL_NAME,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=CYCLONEDX_SCHEMA_PATH,
        source_paths=["ops/scripts/cyclonedx_sbom.py"],
        file_inputs=_envelope_file_inputs(vault, active_provenance_report),
    )
    artifact_envelope["$schema"] = CYCLONEDX_16_SCHEMA_URI
    metadata = _build_metadata(
        vault,
        generated_at,
        active_provenance_report,
        active_mapping_report,
        artifact_envelope,
    )
    components, direct_runtime_refs, name_to_ref = _build_components(vault, active_provenance_report)
    root_ref = metadata["component"]["bom-ref"]

    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": metadata,
        "components": components,
        "dependencies": _build_dependencies(
            vault,
            root_ref,
            direct_runtime_refs,
            components,
            name_to_ref,
            active_provenance_report,
        ),
    }


def write_bom(vault: Path, bom: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=bom,
            schema_path=CYCLONEDX_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="CycloneDX 1.6 schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a CycloneDX 1.6 JSON SBOM")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    bom = build_bom(vault, policy_path=args.policy_path)
    destination = write_bom(vault, bom, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
