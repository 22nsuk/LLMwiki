from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from email.policy import default as default_email_policy
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    read_json_object,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.release.release_status_v2 import release_status_v2_view

PRODUCER = "ops.scripts.release_live_artifact_attestation"
SCHEMA_PATH = "ops/schemas/release-live-artifact-attestation.schema.json"
DEFAULT_OUT = "build/release/release-live-attestation.json"
DEFAULT_SOURCE_ZIP = "build/release/live-source.zip"
DEFAULT_EVIDENCE_BUNDLE = "build/release/release-evidence-bundle.zip"
DEFAULT_CLOSEOUT_SUMMARY = "ops/reports/release-closeout-summary.json"
DEFAULT_BATCH_MANIFEST = "ops/reports/release-closeout-batch-manifest.json"
DEFAULT_SELF_CHECK = "ops/reports/release-evidence-closeout-self-check.json"
DEFAULT_DIST_DIR = "dist"
AUDIT_PACK_MANIFEST = "release-audit-pack-manifest.json"
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"
_DIST_NAME_SEPARATOR_RE = re.compile(r"[-_.]+")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(vault: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (vault / path).resolve()


def _file_identity(vault: Path, value: str | Path, *, role: str) -> dict[str, Any]:
    path = _resolve(vault, value)
    exists = path.is_file()
    return {
        "role": role,
        "path": report_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
    }


def _canonical_json_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_distribution_name(value: str) -> str:
    return _DIST_NAME_SEPARATOR_RE.sub("-", value).lower()


def _source_command(
    *,
    source_zip_path: str,
    evidence_bundle_path: str,
    dist_dir: str,
    closeout_summary_path: str,
    batch_manifest_path: str,
    self_check_path: str,
    expected_package_version: str,
    expected_source_revision: str,
) -> str:
    return shlex.join(
        [
            "python",
            "-m",
            "ops.scripts.release.release_live_artifact_attestation",
            "build",
            "--vault",
            ".",
            "--source-zip-path",
            source_zip_path,
            "--evidence-bundle-path",
            evidence_bundle_path,
            "--dist-dir",
            dist_dir,
            "--closeout-summary-path",
            closeout_summary_path,
            "--batch-manifest-path",
            batch_manifest_path,
            "--self-check-path",
            self_check_path,
            "--expected-package-version",
            expected_package_version,
            "--expected-source-revision",
            expected_source_revision,
        ]
    )


def _source_zip_release_metadata(path: Path) -> dict[str, str]:
    empty = {
        "status": "missing",
        "archive_root_name": "",
        "package_name": "",
        "package_version": "",
        "source_revision": "",
        "source_tree_fingerprint": "",
        "failure": "source_zip_missing",
    }
    if not path.is_file():
        return empty
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = sorted(
                name
                for name in archive.namelist()
                if name == ARCHIVE_SELF_DESCRIPTION_PATH
                or name.endswith(f"/{ARCHIVE_SELF_DESCRIPTION_PATH}")
            )
            if len(candidates) != 1:
                return {
                    **empty,
                    "status": "invalid",
                    "failure": "source_zip_self_description_count_invalid",
                }
            self_description = json.loads(
                archive.read(candidates[0]).decode("utf-8")
            )
            if not isinstance(self_description, dict):
                return {
                    **empty,
                    "status": "invalid",
                    "failure": "source_zip_self_description_invalid",
                }
            archive_root_name = str(
                self_description.get("archive_root_name", "")
            ).strip()
            pyproject_member = (
                f"{archive_root_name}/pyproject.toml"
                if archive_root_name
                else "pyproject.toml"
            )
            if pyproject_member not in archive.namelist():
                return {
                    **empty,
                    "status": "invalid",
                    "archive_root_name": archive_root_name,
                    "failure": "source_zip_pyproject_missing",
                }
            pyproject = tomllib.loads(
                archive.read(pyproject_member).decode("utf-8")
            )
    except (
        json.JSONDecodeError,
        OSError,
        tomllib.TOMLDecodeError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
    ):
        return {**empty, "status": "unreadable", "failure": "source_zip_unreadable"}

    project = pyproject.get("project")
    if not isinstance(project, dict):
        project = {}
    package_name = str(project.get("name", "")).strip()
    package_version = str(project.get("version", "")).strip()
    source_revision = str(self_description.get("git_commit", "")).strip()
    source_tree_fingerprint = str(
        self_description.get("source_tree_fingerprint", "")
    ).strip()
    if not all(
        (
            archive_root_name,
            package_name,
            package_version,
            source_revision,
            source_tree_fingerprint,
        )
    ):
        return {
            **empty,
            "status": "invalid",
            "archive_root_name": archive_root_name,
            "package_name": package_name,
            "package_version": package_version,
            "source_revision": source_revision,
            "source_tree_fingerprint": source_tree_fingerprint,
            "failure": "source_zip_release_metadata_incomplete",
        }
    return {
        "status": "loaded",
        "archive_root_name": archive_root_name,
        "package_name": package_name,
        "package_version": package_version,
        "source_revision": source_revision,
        "source_tree_fingerprint": source_tree_fingerprint,
        "failure": "",
    }


def _core_metadata_fields(payload: bytes) -> tuple[str, str]:
    metadata = BytesParser(policy=default_email_policy).parsebytes(payload)
    return str(metadata.get("Name", "")).strip(), str(
        metadata.get("Version", "")
    ).strip()


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        candidates = sorted(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        if len(candidates) != 1:
            raise ValueError("wheel metadata count must be exactly one")
        return _core_metadata_fields(archive.read(candidates[0]))


def _sdist_metadata(path: Path) -> tuple[str, str]:
    with tarfile.open(path, mode="r:gz") as archive:
        candidates = sorted(
            (
                member
                for member in archive.getmembers()
                if member.isfile()
                and re.fullmatch(r"[^/\\]+/PKG-INFO", member.name) is not None
                and not member.name.startswith(("./", "../"))
            ),
            key=lambda member: member.name,
        )
        if len(candidates) != 1:
            raise ValueError("sdist metadata count must be exactly one")
        extracted = archive.extractfile(candidates[0])
        if extracted is None:
            raise ValueError("sdist metadata is unreadable")
        return _core_metadata_fields(extracted.read())


def _distribution_manifest(
    vault: Path,
    *,
    dist_dir: str | Path,
    source_zip_path: str | Path,
) -> dict[str, Any]:
    resolved_dist_dir = _resolve(vault, dist_dir)
    source_zip = _resolve(vault, source_zip_path)
    source_metadata = _source_zip_release_metadata(source_zip)
    failures: list[str] = []
    if source_metadata["status"] != "loaded":
        failures.append(source_metadata["failure"])

    candidates: list[tuple[Path, str]] = []
    unexpected_files: list[str] = []
    if not resolved_dist_dir.is_dir():
        failures.append("distribution_directory_missing")
    else:
        for path in sorted(resolved_dist_dir.iterdir(), key=lambda item: item.name):
            if not path.is_file() or path.is_symlink():
                unexpected_files.append(path.name)
                continue
            if path.name.endswith(".whl"):
                candidates.append((path, "wheel"))
            elif path.name.endswith(".tar.gz"):
                candidates.append((path, "sdist"))
            else:
                unexpected_files.append(path.name)
        if unexpected_files:
            failures.append("unexpected_distribution_files")

    distribution_types = [distribution_type for _, distribution_type in candidates]
    if distribution_types.count("wheel") != 1:
        failures.append("wheel_count_invalid")
    if distribution_types.count("sdist") != 1:
        failures.append("sdist_count_invalid")

    files: list[dict[str, Any]] = []
    for path, distribution_type in candidates:
        package_name = ""
        package_version = ""
        try:
            if distribution_type == "wheel":
                package_name, package_version = _wheel_metadata(path)
            else:
                package_name, package_version = _sdist_metadata(path)
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile):
            failures.append(f"{distribution_type}_metadata_invalid")
        if (
            source_metadata["package_name"]
            and _canonical_distribution_name(package_name)
            != _canonical_distribution_name(source_metadata["package_name"])
        ):
            failures.append(f"{distribution_type}_package_name_mismatch")
        if (
            source_metadata["package_version"]
            and package_version != source_metadata["package_version"]
        ):
            failures.append(f"{distribution_type}_package_version_mismatch")
        files.append(
            {
                "filename": path.name,
                "distribution_type": distribution_type,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "package_name": package_name,
                "package_version": package_version,
            }
        )
    files.sort(
        key=lambda item: (str(item["distribution_type"]), str(item["filename"]))
    )

    deduped_failures = list(dict.fromkeys(failures))
    return {
        "status": "pass" if not deduped_failures else "fail",
        "failures": deduped_failures,
        "package_name": source_metadata["package_name"],
        "package_version": source_metadata["package_version"],
        "source_zip_sha256": _sha256_file(source_zip) if source_zip.is_file() else "",
        "source_revision": source_metadata["source_revision"],
        "source_tree_fingerprint": source_metadata["source_tree_fingerprint"],
        "file_count": len(files),
        "unexpected_files": unexpected_files,
        "files": files,
    }


def _report_identity(vault: Path, value: str | Path, *, role: str) -> dict[str, Any]:
    identity = _file_identity(vault, value, role=role)
    payload = read_json_object(_resolve(vault, value)) if identity["exists"] else {}
    identity.update(
        {
            "artifact_kind": str(payload.get("artifact_kind", "")),
            "producer": str(payload.get("producer", "")),
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
        }
    )
    return identity


def _audit_pack_manifest(vault: Path, evidence_bundle_path: str | Path) -> dict[str, Any]:
    empty_source_zip = {
        "source_zip_status": "",
        "source_zip_path": "",
        "source_zip_sha256": "",
    }
    bundle = _resolve(vault, evidence_bundle_path)
    if not bundle.is_file():
        return {
            "status": "missing",
            "source_of_truth": "",
            "batch_id": "",
            "evidence_set_digest": "",
            "packed_entry_count": 0,
            **empty_source_zip,
        }
    try:
        with zipfile.ZipFile(bundle) as archive:
            payload = json.loads(archive.read(AUDIT_PACK_MANIFEST).decode("utf-8"))
    except (KeyError, OSError, json.JSONDecodeError, zipfile.BadZipFile, UnicodeDecodeError):
        return {
            "status": "unreadable",
            "source_of_truth": "",
            "batch_id": "",
            "evidence_set_digest": "",
            "packed_entry_count": 0,
            **empty_source_zip,
        }
    source_zip = payload.get("source_zip")
    if not isinstance(source_zip, dict):
        source_zip = {}
    return {
        "status": "loaded",
        "source_of_truth": str(payload.get("source_of_truth", "")),
        "batch_id": str(payload.get("batch_id", "")),
        "evidence_set_digest": str(payload.get("evidence_set_digest", "")),
        "packed_entry_count": int(payload.get("packed_entry_count", 0) or 0),
        "source_zip_status": str(source_zip.get("status", "")),
        "source_zip_path": str(source_zip.get("path", "")),
        "source_zip_sha256": str(source_zip.get("sha256", "")),
    }


def _status_is_pass(value: Any) -> bool:
    if isinstance(value, dict):
        return str(value.get("result", "")).strip() == "pass"
    return str(value).strip() == "pass"


def _status_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("result", "")).strip()
    return str(value).strip()


def _batch_integrity_pass(batch_manifest: dict[str, Any]) -> bool:
    batch_integrity_status = str(batch_manifest.get("batch_integrity_status", "")).strip()
    return batch_integrity_status == "pass"


def _batch_authority_clean_pass(batch_manifest: dict[str, Any]) -> bool:
    authority_status = str(release_status_v2_view(batch_manifest)["release_authority_status"])
    return authority_status == "clean_pass"


def _batch_distribution_sha256(batch_manifest: dict[str, Any]) -> str:
    distribution = batch_manifest.get("distribution_package", {})
    if not isinstance(distribution, dict):
        return ""
    return str(distribution.get("sha256", "")).strip()


def _external_source_zip_sha256(batch_manifest: dict[str, Any]) -> str:
    external_bound = batch_manifest.get("external_source_zip_bound", {})
    if not isinstance(external_bound, dict):
        return ""
    return str(external_bound.get("sha256", "")).strip()


def _verification(
    *,
    source_zip: dict[str, Any],
    evidence_bundle: dict[str, Any],
    distribution_manifest: dict[str, Any],
    closeout: dict[str, Any],
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    audit_pack_manifest: dict[str, Any],
    expected_package_version: str,
    expected_source_revision: str,
) -> dict[str, Any]:
    source_zip_sha256 = str(source_zip.get("sha256", "")).strip()
    source_tree_fingerprint = str(
        distribution_manifest.get("source_tree_fingerprint", "")
    ).strip()
    closeout_source_tree_fingerprint = str(
        closeout.get("source_tree_fingerprint", "")
    ).strip()
    batch_source_tree_fingerprint = str(
        batch_manifest.get("source_tree_fingerprint", "")
    ).strip()
    self_check_source_tree_fingerprint = str(
        self_check.get("source_tree_fingerprint", "")
    ).strip()
    batch_distribution_sha256 = _batch_distribution_sha256(batch_manifest)
    external_source_sha256 = _external_source_zip_sha256(batch_manifest)
    audit_pack_source_sha256 = str(audit_pack_manifest.get("source_zip_sha256", "")).strip()
    status_view = release_status_v2_view(batch_manifest)
    checks = {
        "source_zip_present": bool(source_zip["exists"]),
        "evidence_bundle_present": bool(evidence_bundle["exists"]),
        "closeout_machine_release_allowed": bool(closeout.get("machine_release_allowed", False)),
        "closeout_clean_release_ready": bool(closeout.get("clean_release_ready", False)),
        "batch_manifest_integrity_pass": _batch_integrity_pass(batch_manifest),
        "batch_manifest_release_authority_clean_pass": _batch_authority_clean_pass(batch_manifest),
        "batch_manifest_semantic_clean_pass": (
            str(status_view["semantic_release_status"]) == "clean_pass"
        ),
        "batch_manifest_sealed_clean_pass": (
            str(status_view["sealed_release_status"]) == "sealed_clean_pass"
        ),
        "source_zip_matches_batch_distribution": (
            bool(source_zip_sha256)
            and source_zip_sha256 == batch_distribution_sha256
        ),
        "source_zip_matches_external_source_bound": (
            bool(source_zip_sha256)
            and source_zip_sha256 == external_source_sha256
        ),
        "source_zip_matches_audit_pack_manifest": (
            bool(source_zip_sha256)
            and source_zip_sha256 == audit_pack_source_sha256
        ),
        "self_check_pass": _status_is_pass(self_check.get("status")),
        "audit_pack_manifest_loaded": audit_pack_manifest.get("status") == "loaded",
        "evidence_set_digest_bound": (
            str(batch_manifest.get("audit_materialization", {}).get("evidence_set_digest", ""))
            == str(audit_pack_manifest.get("evidence_set_digest", ""))
            and bool(str(audit_pack_manifest.get("evidence_set_digest", "")))
        ),
        "distribution_manifest_pass": distribution_manifest.get("status") == "pass",
        "distribution_manifest_source_zip_bound": (
            bool(source_zip_sha256)
            and distribution_manifest.get("source_zip_sha256") == source_zip_sha256
        ),
        "distribution_manifest_package_version_bound": bool(
            str(distribution_manifest.get("package_version", "")).strip()
        ),
        "distribution_manifest_source_revision_bound": bool(
            str(distribution_manifest.get("source_revision", "")).strip()
        ),
        "distribution_manifest_source_tree_fingerprint_bound": bool(
            source_tree_fingerprint
        ),
        "source_zip_matches_closeout_source_tree_fingerprint": (
            bool(source_tree_fingerprint)
            and source_tree_fingerprint == closeout_source_tree_fingerprint
        ),
        "source_zip_matches_batch_source_tree_fingerprint": (
            bool(source_tree_fingerprint)
            and source_tree_fingerprint == batch_source_tree_fingerprint
        ),
        "source_zip_matches_self_check_source_tree_fingerprint": (
            bool(source_tree_fingerprint)
            and source_tree_fingerprint == self_check_source_tree_fingerprint
        ),
        "expected_package_version_matches": (
            not expected_package_version
            or distribution_manifest.get("package_version") == expected_package_version
        ),
        "expected_source_revision_matches": (
            not expected_source_revision
            or distribution_manifest.get("source_revision") == expected_source_revision
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def build_attestation(
    vault: Path,
    *,
    source_zip_path: str = DEFAULT_SOURCE_ZIP,
    evidence_bundle_path: str = DEFAULT_EVIDENCE_BUNDLE,
    dist_dir: str = DEFAULT_DIST_DIR,
    closeout_summary_path: str = DEFAULT_CLOSEOUT_SUMMARY,
    batch_manifest_path: str = DEFAULT_BATCH_MANIFEST,
    self_check_path: str = DEFAULT_SELF_CHECK,
    expected_package_version: str = "",
    expected_source_revision: str = "",
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    source_zip = _file_identity(vault, source_zip_path, role="source_zip")
    evidence_bundle = _file_identity(vault, evidence_bundle_path, role="evidence_bundle")
    distribution_manifest = _distribution_manifest(
        vault,
        dist_dir=dist_dir,
        source_zip_path=source_zip_path,
    )
    closeout = read_json_object(_resolve(vault, closeout_summary_path))
    batch_manifest = read_json_object(_resolve(vault, batch_manifest_path))
    self_check = read_json_object(_resolve(vault, self_check_path))
    audit_manifest = _audit_pack_manifest(vault, evidence_bundle_path)
    effective_expected_package_version = (
        expected_package_version
        or str(distribution_manifest.get("package_version", "")).strip()
    )
    effective_expected_source_revision = (
        expected_source_revision
        or str(distribution_manifest.get("source_revision", "")).strip()
    )
    verification = _verification(
        source_zip=source_zip,
        evidence_bundle=evidence_bundle,
        distribution_manifest=distribution_manifest,
        closeout=closeout,
        batch_manifest=batch_manifest,
        self_check=self_check,
        audit_pack_manifest=audit_manifest,
        expected_package_version=effective_expected_package_version,
        expected_source_revision=effective_expected_source_revision,
    )
    reports = {
        "release_closeout_summary": _report_identity(vault, closeout_summary_path, role="release_authority"),
        "release_closeout_batch_manifest": _report_identity(vault, batch_manifest_path, role="batch_authority"),
        "release_evidence_closeout_self_check": _report_identity(vault, self_check_path, role="self_check"),
    }
    file_inputs = {
        "source_zip": source_zip_path,
        "evidence_bundle": evidence_bundle_path,
        "release_closeout_summary": closeout_summary_path,
        "release_closeout_batch_manifest": batch_manifest_path,
        "release_evidence_closeout_self_check": self_check_path,
    }
    for distribution in distribution_manifest["files"]:
        distribution_type = str(distribution["distribution_type"])
        filename = str(distribution["filename"])
        file_inputs[f"distribution_{distribution_type}"] = str(
            Path(dist_dir) / filename
        )
    status_view = release_status_v2_view(batch_manifest)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_live_artifact_attestation",
            producer=PRODUCER,
            source_command=_source_command(
                source_zip_path=source_zip_path,
                evidence_bundle_path=evidence_bundle_path,
                dist_dir=dist_dir,
                closeout_summary_path=closeout_summary_path,
                batch_manifest_path=batch_manifest_path,
                self_check_path=self_check_path,
                expected_package_version=effective_expected_package_version,
                expected_source_revision=effective_expected_source_revision,
            ),
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/release/release_live_artifact_attestation.py"],
            file_inputs=file_inputs,
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": verification["status"],
        "source_zip": source_zip,
        "evidence_bundle": evidence_bundle,
        "distribution_manifest": distribution_manifest,
        "reports": reports,
        "audit_pack_manifest": audit_manifest,
        "bindings": {
            "source_zip_sha256": source_zip["sha256"],
            "evidence_bundle_sha256": evidence_bundle["sha256"],
            "batch_distribution_zip_sha256": _batch_distribution_sha256(batch_manifest),
            "external_source_zip_bound_sha256": _external_source_zip_sha256(batch_manifest),
            "audit_pack_source_zip_sha256": str(audit_manifest.get("source_zip_sha256", "")),
            "release_closeout_summary_sha256": reports["release_closeout_summary"]["sha256"],
            "release_closeout_batch_manifest_sha256": reports["release_closeout_batch_manifest"]["sha256"],
            "release_evidence_closeout_self_check_sha256": reports[
                "release_evidence_closeout_self_check"
            ]["sha256"],
            "source_tree_fingerprint": str(
                distribution_manifest.get("source_tree_fingerprint", "")
            ),
            "evidence_set_digest": str(
                batch_manifest.get("audit_materialization", {}).get("evidence_set_digest", "")
            ),
            "audit_pack_evidence_set_digest": str(audit_manifest.get("evidence_set_digest", "")),
            "distribution_manifest_sha256": _canonical_json_sha256(
                distribution_manifest
            ),
            "distribution_package_name": str(
                distribution_manifest.get("package_name", "")
            ),
            "distribution_package_version": str(
                distribution_manifest.get("package_version", "")
            ),
            "distribution_source_revision": str(
                distribution_manifest.get("source_revision", "")
            ),
        },
        "release_authority": {
            "machine_release_allowed": bool(closeout.get("machine_release_allowed", False)),
            "clean_release_ready": bool(closeout.get("clean_release_ready", False)),
            "release_readiness_state": str(closeout.get("release_readiness_state", "")),
            "batch_manifest_status": str(status_view["compatibility_status_value"]),
            "semantic_release_status": str(status_view["semantic_release_status"]),
            "sealed_release_status": str(status_view["sealed_release_status"]),
            "distribution_package_status": str(
                batch_manifest.get("distribution_package", {}).get("status", "")
            ),
            "self_check_status": _status_label(self_check.get("status")),
        },
        "verification": verification,
    }


def verify_attestation(
    vault: Path,
    *,
    attestation_path: str,
    source_zip_path: str,
    evidence_bundle_path: str,
    closeout_summary_path: str,
    batch_manifest_path: str,
    self_check_path: str,
    dist_dir: str = DEFAULT_DIST_DIR,
    expected_package_version: str = "",
    expected_source_revision: str = "",
) -> dict[str, Any]:
    attestation = read_json_object(_resolve(vault, attestation_path))
    schema = load_schema_with_vault_override(vault, SCHEMA_PATH)
    validate_or_raise(attestation, schema, context="release live artifact attestation validation failed")
    current = build_attestation(
        vault,
        source_zip_path=source_zip_path,
        evidence_bundle_path=evidence_bundle_path,
        dist_dir=dist_dir,
        closeout_summary_path=closeout_summary_path,
        batch_manifest_path=batch_manifest_path,
        self_check_path=self_check_path,
        expected_package_version=expected_package_version,
        expected_source_revision=expected_source_revision,
        context=RuntimeContext.from_policy(load_policy(vault)[0]),
    )
    expected_bindings = attestation.get("bindings", {})
    current_bindings = current.get("bindings", {})
    binding_mismatches = [
        key
        for key in sorted(set(expected_bindings) | set(current_bindings))
        if expected_bindings.get(key) != current_bindings.get(key)
    ]
    stored_manifest = attestation.get("distribution_manifest", {})
    attestation_self_binding_mismatches: list[str] = []
    if expected_bindings.get("distribution_manifest_sha256") != (
        _canonical_json_sha256(stored_manifest)
    ):
        attestation_self_binding_mismatches.append("distribution_manifest_sha256")
    for binding_key, manifest_key in (
        ("distribution_package_name", "package_name"),
        ("distribution_package_version", "package_version"),
        ("distribution_source_revision", "source_revision"),
        ("source_tree_fingerprint", "source_tree_fingerprint"),
    ):
        if expected_bindings.get(binding_key) != stored_manifest.get(manifest_key):
            attestation_self_binding_mismatches.append(binding_key)
    stored_verification = attestation.get("verification", {})
    stored_status_pass = attestation.get("status") == "pass" and (
        isinstance(stored_verification, dict)
        and stored_verification.get("status") == "pass"
    )
    status = (
        "pass"
        if current["status"] == "pass"
        and stored_status_pass
        and not binding_mismatches
        and not attestation_self_binding_mismatches
        else "fail"
    )
    return {
        "status": status,
        "attestation_path": attestation_path,
        "binding_mismatches": binding_mismatches,
        "attestation_status_pass": stored_status_pass,
        "attestation_self_binding_mismatches": attestation_self_binding_mismatches,
        "verification": current["verification"],
    }


def distribution_binding_reason_ids(
    vault: Path,
    *,
    attestation_path: str = DEFAULT_OUT,
    dist_dir: str = DEFAULT_DIST_DIR,
) -> list[str]:
    resolved_attestation = _resolve(vault, attestation_path)
    if not resolved_attestation.is_file():
        return ["release_live_distribution_attestation_missing"]
    try:
        attestation = read_json_object(resolved_attestation)
    except (json.JSONDecodeError, OSError, ValueError):
        return ["release_live_distribution_attestation_invalid"]

    reasons: list[str] = []
    manifest = attestation.get("distribution_manifest")
    bindings = attestation.get("bindings")
    source_zip = attestation.get("source_zip")
    if not isinstance(manifest, dict) or not isinstance(bindings, dict):
        return ["release_live_distribution_manifest_missing"]
    if not isinstance(source_zip, dict):
        source_zip = {}

    if attestation.get("status") != "pass":
        reasons.append("release_live_distribution_attestation_not_pass")
    if manifest.get("status") != "pass":
        reasons.append("release_live_distribution_manifest_not_pass")
    if manifest.get("failures") or manifest.get("unexpected_files"):
        reasons.append("release_live_distribution_manifest_integrity_invalid")
    manifest_sha256 = _canonical_json_sha256(manifest)
    if bindings.get("distribution_manifest_sha256") != manifest_sha256:
        reasons.append("release_live_distribution_manifest_digest_mismatch")

    package_name = str(manifest.get("package_name", "")).strip()
    package_version = str(manifest.get("package_version", "")).strip()
    source_revision = str(manifest.get("source_revision", "")).strip()
    source_tree_fingerprint = str(
        manifest.get("source_tree_fingerprint", "")
    ).strip()
    source_zip_sha256 = str(manifest.get("source_zip_sha256", "")).strip()
    if not package_name or not package_version:
        reasons.append("release_live_distribution_package_identity_missing")
    if not source_revision:
        reasons.append("release_live_distribution_source_revision_missing")
    if not source_tree_fingerprint:
        reasons.append("release_live_distribution_source_tree_fingerprint_missing")
    if source_zip_sha256 != str(source_zip.get("sha256", "")).strip():
        reasons.append("release_live_distribution_source_zip_digest_mismatch")
    if bindings.get("distribution_package_name") != package_name:
        reasons.append("release_live_distribution_package_name_binding_mismatch")
    if bindings.get("distribution_package_version") != package_version:
        reasons.append("release_live_distribution_package_version_binding_mismatch")
    if bindings.get("distribution_source_revision") != source_revision:
        reasons.append("release_live_distribution_source_revision_binding_mismatch")
    if bindings.get("source_tree_fingerprint") != source_tree_fingerprint:
        reasons.append("release_live_distribution_source_tree_fingerprint_binding_mismatch")
    files = manifest.get("files")
    if not isinstance(files, list):
        return list(
            dict.fromkeys([*reasons, "release_live_distribution_files_invalid"])
        )
    expected_types = sorted(
        str(item.get("distribution_type", ""))
        for item in files
        if isinstance(item, dict)
    )
    if expected_types != ["sdist", "wheel"] or manifest.get("file_count") != 2:
        reasons.append("release_live_distribution_file_set_invalid")

    resolved_dist_dir = _resolve(vault, dist_dir)
    expected_filenames: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            reasons.append("release_live_distribution_file_record_invalid")
            continue
        filename = str(item.get("filename", ""))
        if not filename or Path(filename).name != filename:
            reasons.append("release_live_distribution_filename_invalid")
            continue
        expected_filenames.add(filename)
        path = resolved_dist_dir / filename
        if not path.is_file():
            reasons.append("release_live_distribution_file_missing")
            continue
        if item.get("sha256") != _sha256_file(path):
            reasons.append("release_live_distribution_file_sha256_mismatch")
        if item.get("size_bytes") != path.stat().st_size:
            reasons.append("release_live_distribution_file_size_mismatch")
        if item.get("package_name") != package_name:
            reasons.append("release_live_distribution_file_package_name_mismatch")
        if item.get("package_version") != package_version:
            reasons.append("release_live_distribution_file_package_version_mismatch")

    actual_filenames = (
        {path.name for path in resolved_dist_dir.iterdir()}
        if resolved_dist_dir.is_dir()
        else set()
    )
    if actual_filenames != expected_filenames:
        reasons.append("release_live_distribution_file_set_mismatch")
    return list(dict.fromkeys(reasons))


def write_attestation(vault: Path, payload: dict[str, Any], out_path: str) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=payload,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release live artifact attestation schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify release live artifact attestation")
    subparsers = parser.add_subparsers(dest="command_name", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--vault", default=".")
    build.add_argument("--out", default=DEFAULT_OUT)
    build.add_argument("--source-zip-path", default=DEFAULT_SOURCE_ZIP)
    build.add_argument("--evidence-bundle-path", default=DEFAULT_EVIDENCE_BUNDLE)
    build.add_argument("--dist-dir", default=DEFAULT_DIST_DIR)
    build.add_argument("--closeout-summary-path", default=DEFAULT_CLOSEOUT_SUMMARY)
    build.add_argument("--batch-manifest-path", default=DEFAULT_BATCH_MANIFEST)
    build.add_argument("--self-check-path", default=DEFAULT_SELF_CHECK)
    build.add_argument("--expected-package-version", default="")
    build.add_argument("--expected-source-revision", default="")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--vault", default=".")
    verify.add_argument("--attestation", required=True)
    verify.add_argument("--source-zip-path", required=True)
    verify.add_argument("--evidence-bundle-path", required=True)
    verify.add_argument("--dist-dir", required=True)
    verify.add_argument("--closeout-summary-path", required=True)
    verify.add_argument("--batch-manifest-path", required=True)
    verify.add_argument("--self-check-path", required=True)
    verify.add_argument("--expected-package-version", default="")
    verify.add_argument("--expected-source-revision", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.command_name == "build":
        payload = build_attestation(
            vault,
            source_zip_path=args.source_zip_path,
            evidence_bundle_path=args.evidence_bundle_path,
            dist_dir=args.dist_dir,
            closeout_summary_path=args.closeout_summary_path,
            batch_manifest_path=args.batch_manifest_path,
            self_check_path=args.self_check_path,
            expected_package_version=args.expected_package_version,
            expected_source_revision=args.expected_source_revision,
        )
        destination = write_attestation(vault, payload, args.out)
        print(display_path(vault, destination))
        return 0 if payload["status"] == "pass" else 1

    result = verify_attestation(
        vault,
        attestation_path=args.attestation,
        source_zip_path=args.source_zip_path,
        evidence_bundle_path=args.evidence_bundle_path,
        dist_dir=args.dist_dir,
        closeout_summary_path=args.closeout_summary_path,
        batch_manifest_path=args.batch_manifest_path,
        self_check_path=args.self_check_path,
        expected_package_version=args.expected_package_version,
        expected_source_revision=args.expected_source_revision,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
