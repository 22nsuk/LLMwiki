#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
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
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import SUPPLY_CHAIN_PROVENANCE_SCHEMA_PATH
    from ops.scripts.supply_chain.ci_install_proof_runtime import (
        CANONICAL_UV_LOCK_CHECK_COMMAND,
        CI_WORKFLOW_PATH,
        LOCKED_REQUIREMENTS_EXPORT_PATH,
        UV_LOCK_CHECK_COMMAND,
        ci_install_evidence_content,
        collect_ci_install_contract,
    )
    from ops.scripts.wiki_manifest import build_manifest
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
    from ops.scripts.schema_constants_runtime import SUPPLY_CHAIN_PROVENANCE_SCHEMA_PATH
    from ops.scripts.wiki_manifest import build_manifest

    from .ci_install_proof_runtime import (
        CANONICAL_UV_LOCK_CHECK_COMMAND,
        CI_WORKFLOW_PATH,
        LOCKED_REQUIREMENTS_EXPORT_PATH,
        UV_LOCK_CHECK_COMMAND,
        ci_install_evidence_content,
        collect_ci_install_contract,
    )


SUPPLY_CHAIN_PROVENANCE_SCHEMA = SUPPLY_CHAIN_PROVENANCE_SCHEMA_PATH
DEFAULT_OUT = "ops/reports/supply-chain-provenance.json"
SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_PATH = "ops/reports/source-package-clean-extract.json"
CANONICAL_DEPENDENCY_INPUTS = (
    "pyproject.toml",
    "uv.lock",
)
COMPATIBILITY_DEPENDENCY_INPUTS = (
    "requirements.txt",
    "requirements-dev.txt",
)
DEPENDENCY_INPUTS = (
    *CANONICAL_DEPENDENCY_INPUTS,
    *COMPATIBILITY_DEPENDENCY_INPUTS,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser_status(status: str, parser: str, message: str = "") -> dict:
    return {
        "parser": parser,
        "status": status,
        "message": message,
    }


def dependency_name(requirement: str) -> str:
    text = requirement.strip()
    name = []
    for char in text:
        if char.isalnum() or char in {"_", "-", "."}:
            name.append(char)
            continue
        break
    return "".join(name)


def input_record(vault: Path, rel_path: str, parser: str) -> dict:
    path = vault / rel_path
    authority_role = "canonical" if rel_path in CANONICAL_DEPENDENCY_INPUTS else "compatibility"
    if not path.exists():
        return {
            "path": rel_path,
            "authority_role": authority_role,
            "exists": False,
            "size_bytes": 0,
            "sha256": "",
            "parser_status": _parser_status("missing", parser, "input file is missing"),
        }
    return {
        "path": rel_path,
        "authority_role": authority_role,
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "parser_status": _parser_status("pass", parser),
    }


def parse_pyproject(vault: Path) -> tuple[list[dict], list[dict], dict]:
    path = vault / "pyproject.toml"
    if not path.exists():
        return [], [], _parser_status("missing", "tomllib", "pyproject.toml is missing")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [], [], _parser_status("error", "tomllib", str(exc))

    project = payload.get("project", {})
    dependencies = []
    for index, requirement in enumerate(project.get("dependencies", []), start=1):
        requirement_text = str(requirement).strip()
        dependencies.append(
            {
                "source": "pyproject.toml:project.dependencies",
                "group": "runtime",
                "index": index,
                "name": dependency_name(requirement_text),
                "requirement": requirement_text,
            }
        )

    dev_dependencies = []
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in sorted(optional):
            entries = optional.get(group, [])
            if not isinstance(entries, list):
                continue
            for index, requirement in enumerate(entries, start=1):
                requirement_text = str(requirement).strip()
                dev_dependencies.append(
                    {
                        "source": f"pyproject.toml:project.optional-dependencies.{group}",
                        "group": str(group),
                        "index": index,
                        "name": dependency_name(requirement_text),
                        "requirement": requirement_text,
                    }
                )
    return dependencies, dev_dependencies, _parser_status("pass", "tomllib")


def parse_requirements(vault: Path, rel_path: str) -> tuple[list[dict], dict]:
    path = vault / rel_path
    if not path.exists():
        return [], _parser_status("missing", "requirements-line-parser", f"{rel_path} is missing")
    requirements = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw_line.strip()
        if not text or text.startswith("#"):
            continue
        kind = "include" if text.startswith(("-r ", "--requirement ")) else "requirement"
        requirements.append(
            {
                "source": rel_path,
                "line": line_number,
                "kind": kind,
                "name": "" if kind == "include" else dependency_name(text),
                "requirement": text,
            }
        )
    return requirements, _parser_status("pass", "requirements-line-parser")


def _sdist_record(value: Any) -> dict:
    if not isinstance(value, dict):
        return {"url": "", "hash": "", "upload_time": ""}
    return {
        "url": str(value.get("url", "")),
        "hash": str(value.get("hash", "")),
        "upload_time": str(value.get("upload-time", "")),
    }


def _locked_dependency_records(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    dependencies = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        dependencies.append(
            {
                "index": index,
                "name": name,
                "version": str(item.get("version", "")),
                "marker": str(item.get("marker", "")),
                "extra": str(item.get("extra", "")),
            }
        )
    return dependencies


def parse_uv_lock(vault: Path) -> tuple[list[dict], dict]:
    path = vault / "uv.lock"
    if not path.exists():
        return [], _parser_status("missing", "tomllib", "uv.lock is missing")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [], _parser_status("error", "tomllib", str(exc))

    packages = []
    for item in payload.get("package", []):
        if not isinstance(item, dict):
            continue
        source = item.get("source", {})
        if not isinstance(source, dict):
            source = {}
        wheels = item.get("wheels", [])
        if not isinstance(wheels, list):
            wheels = []
        wheel_hashes = []
        for wheel in wheels:
            if isinstance(wheel, dict) and str(wheel.get("hash", "")).strip():
                wheel_hashes.append(str(wheel["hash"]))
        packages.append(
            {
                "name": str(item.get("name", "")),
                "version": str(item.get("version", "")),
                "registry": str(source.get("registry", "")),
                "editable": str(source.get("editable", "")),
                "sdist": _sdist_record(item.get("sdist")),
                "wheel_count": len(wheels),
                "wheel_hashes_sample": wheel_hashes[:5],
                "dependencies": _locked_dependency_records(item.get("dependencies")),
            }
        )
    packages.sort(key=lambda item: (item["name"], item["version"]))
    return packages, _parser_status("pass", "tomllib")


def release_manifest_summary(vault: Path) -> dict:
    manifest = build_manifest(vault, vault / "ops" / "manifest.json")
    files = {str(item["path"]) for item in manifest.get("files", []) if isinstance(item, dict)}
    canonical_dependency_files = [
        rel_path for rel_path in CANONICAL_DEPENDENCY_INPUTS if rel_path in files
    ]
    compatibility_dependency_files = [
        rel_path for rel_path in COMPATIBILITY_DEPENDENCY_INPUTS if rel_path in files
    ]
    return {
        "source": "ops.scripts.wiki_manifest.build_manifest",
        "file_count": len(files),
        "dependency_file_count": len(canonical_dependency_files),
        "dependency_files": canonical_dependency_files,
        "canonical_dependency_files": canonical_dependency_files,
        "compatibility_dependency_files": compatibility_dependency_files,
    }


def ci_install_proof(vault: Path) -> dict:
    path = vault / CI_WORKFLOW_PATH
    proof = {
        "workflow_path": CI_WORKFLOW_PATH,
        "workflow_exists": False,
        "workflow_sha256": "",
        "install_commands": [],
        "locked_requirements_path": LOCKED_REQUIREMENTS_EXPORT_PATH,
        "lock_check_commands": [],
        "checks_uv_lock_freshness": False,
        "exports_frozen_uv_lock": False,
        "installs_locked_requirements": False,
        "installs_requirements_dev": False,
        "editable_install": False,
        "includes_build_package": False,
        "install_resolution_mode": "unknown",
    }
    if not path.exists():
        return proof

    _workflow_exists, content = ci_install_evidence_content(vault)
    contract = collect_ci_install_contract(content)
    proof.update(
        {
            "workflow_exists": True,
            "workflow_sha256": sha256_file(path),
            **contract,
        }
    )
    return proof


def lock_evidence(inputs: list[dict], uv_lock_status: dict, ci_proof: dict) -> dict:
    uv_lock_input = next((item for item in inputs if item["path"] == "uv.lock"), None)
    uv_lock_exists = bool(uv_lock_input and uv_lock_input.get("exists"))
    checks_uv_lock_freshness = bool(ci_proof.get("checks_uv_lock_freshness"))
    if not uv_lock_exists:
        lock_check_status = "missing_lockfile"
    elif checks_uv_lock_freshness:
        lock_check_status = "enforced"
    else:
        lock_check_status = "missing_ci_check"
    toolchain_alignment_status = (
        "canonical_policy_enforced"
        if lock_check_status == "enforced"
        else "canonical_policy_not_enforced"
    )
    recommended_normalization_step = (
        "none" if lock_check_status == "enforced" else "make uv-lock-check"
    )
    return {
        "path": "uv.lock",
        "exists": uv_lock_exists,
        "sha256": "" if uv_lock_input is None else str(uv_lock_input.get("sha256", "")),
        "parser_status": uv_lock_status,
        "lock_check_status": lock_check_status,
        "lock_check_command": UV_LOCK_CHECK_COMMAND if checks_uv_lock_freshness else "",
        "canonical_lock_check_command": (
            CANONICAL_UV_LOCK_CHECK_COMMAND if checks_uv_lock_freshness else ""
        ),
        "baseline_environment_lock_check_status": "not_evaluated",
        "canonical_lock_policy_status": lock_check_status,
        "toolchain_alignment_status": toolchain_alignment_status,
        "recommended_normalization_step": recommended_normalization_step,
        "note": "uv.lock is canonical lock evidence; replay requires the canonical-index uv-lock-check gate plus frozen locked-requirements install proof.",
    }


def source_package_evidence(vault: Path) -> dict:
    path = vault / SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_PATH
    base = {
        "path": SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_PATH,
        "exists": path.exists(),
        "load_status": "missing",
        "status": "missing",
        "source_zip_path": "",
        "source_zip_sha256": "",
        "source_package_reproducibility_status": "",
        "test_source_package_status": "",
        "zip_smoke_status": "",
        "zip_smoke_archive_budget_pass": False,
        "zip_smoke_manifest_comparison_pass": False,
        "note": "source package clean-extract evidence is optional for this audit report, but links SBOM/provenance to a replayed source ZIP when present.",
    }
    if not path.exists():
        return base

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            **base,
            "load_status": "error",
            "status": "error",
            "note": f"could not parse source package evidence: {exc}",
        }

    source_zip = payload.get("source_zip", {})
    if not isinstance(source_zip, dict):
        source_zip = {}
    zip_smoke = payload.get("zip_smoke_report", {})
    if not isinstance(zip_smoke, dict):
        zip_smoke = {}
    return {
        **base,
        "load_status": "ok",
        "status": str(payload.get("status", "")),
        "source_zip_path": str(source_zip.get("path", "")),
        "source_zip_sha256": str(source_zip.get("sha256", "")),
        "source_package_reproducibility_status": str(
            payload.get("source_package_reproducibility_status", "")
        ),
        "test_source_package_status": str(payload.get("test_source_package_status", "")),
        "zip_smoke_status": str(zip_smoke.get("status", "")),
        "zip_smoke_archive_budget_pass": bool(zip_smoke.get("archive_budget_pass")),
        "zip_smoke_manifest_comparison_pass": bool(zip_smoke.get("manifest_comparison_pass")),
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)

    parser_by_input = {
        "pyproject.toml": "tomllib",
        "requirements.txt": "requirements-line-parser",
        "requirements-dev.txt": "requirements-line-parser",
        "uv.lock": "tomllib",
    }
    inputs = [
        input_record(vault, rel_path, parser_by_input[rel_path])
        for rel_path in DEPENDENCY_INPUTS
    ]

    declared_dependencies, pyproject_dev_dependencies, pyproject_status = parse_pyproject(vault)
    requirements, requirements_status = parse_requirements(vault, "requirements.txt")
    dev_requirements, dev_requirements_status = parse_requirements(vault, "requirements-dev.txt")
    locked_packages, uv_lock_status = parse_uv_lock(vault)
    parser_statuses = {
        "pyproject.toml": pyproject_status,
        "requirements.txt": requirements_status,
        "requirements-dev.txt": dev_requirements_status,
        "uv.lock": uv_lock_status,
    }
    for item in inputs:
        item["parser_status"] = parser_statuses[item["path"]]

    canonical_inputs = [item for item in inputs if item["authority_role"] == "canonical"]
    compatibility_inputs = [item for item in inputs if item["authority_role"] == "compatibility"]
    canonical_has_non_pass = any(
        item["parser_status"]["status"] != "pass" for item in canonical_inputs
    )
    compatibility_has_error = any(
        item["exists"] and item["parser_status"]["status"] == "error"
        for item in compatibility_inputs
    )
    status = "fail" if canonical_has_non_pass else ("warn" if compatibility_has_error else "pass")
    ci_proof = ci_install_proof(vault)
    uv_lock_evidence = lock_evidence(inputs, uv_lock_status, ci_proof)
    if status == "pass" and uv_lock_evidence["lock_check_status"] != "enforced":
        status = "fail"
    source_package = source_package_evidence(vault)
    if status == "pass" and source_package["status"] in {"fail", "error"}:
        status = "warn"

    report = {
        "$schema": SUPPLY_CHAIN_PROVENANCE_SCHEMA,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "inputs": inputs,
        "declared_dependencies": declared_dependencies,
        "dev_dependencies": pyproject_dev_dependencies,
        "requirements": requirements,
        "dev_requirements": dev_requirements,
        "locked_packages": locked_packages,
        "ci_install_proof": ci_proof,
        "lock_evidence": uv_lock_evidence,
        "source_package_evidence": source_package,
        "release_manifest": release_manifest_summary(vault),
        "provenance_notes": [
            "CI install proof is recorded from .github/workflows/ci.yml and must show make uv-lock-check before frozen uv.lock export for release replay.",
            "uv.lock is canonical dependency evidence only when paired with the canonical-index uv-lock-check gate and a frozen locked-requirements install.",
            "source-package-clean-extract links SBOM/provenance evidence to a replayed source ZIP digest when that release check has run.",
            "This repo-native provenance report is audit evidence only; it does not sign artifacts or gate release/promotion.",
        ],
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=runtime_context.isoformat_z(),
        artifact_kind="supply_chain_provenance_report",
        producer="ops.scripts.supply_chain_provenance",
        source_command="python -m ops.scripts.supply_chain_provenance --vault . --out ops/reports/supply-chain-provenance.json",
        resolved_policy_path=resolved_policy_path,
        schema_path=SUPPLY_CHAIN_PROVENANCE_SCHEMA,
        source_paths=[
            "ops/scripts/supply_chain/supply_chain_provenance.py",
            "ops/scripts/supply_chain/ci_install_proof_runtime.py",
            "ops/scripts/wiki_manifest.py",
            "ops/scripts/artifact_freshness_runtime.py",
        ],
        file_inputs={
            **{rel_path: rel_path for rel_path in CANONICAL_DEPENDENCY_INPUTS},
            **{
                rel_path: rel_path
                for rel_path in COMPATIBILITY_DEPENDENCY_INPUTS
                if (vault / rel_path).exists()
            },
        },
        text_inputs={
            "status": status,
            "ci_workflow_path": CI_WORKFLOW_PATH,
            "source_package_status": str(source_package["status"]),
            "source_package_sha256": str(source_package["source_zip_sha256"]),
        },
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_report(vault: Path, report: dict, out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SUPPLY_CHAIN_PROVENANCE_SCHEMA,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="supply-chain provenance schema validation failed",
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
