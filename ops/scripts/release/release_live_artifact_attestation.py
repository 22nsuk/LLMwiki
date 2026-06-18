from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
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
AUDIT_PACK_MANIFEST = "release-audit-pack-manifest.json"


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
    closeout: dict[str, Any],
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    audit_pack_manifest: dict[str, Any],
) -> dict[str, Any]:
    source_zip_sha256 = str(source_zip.get("sha256", "")).strip()
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
    closeout_summary_path: str = DEFAULT_CLOSEOUT_SUMMARY,
    batch_manifest_path: str = DEFAULT_BATCH_MANIFEST,
    self_check_path: str = DEFAULT_SELF_CHECK,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    source_zip = _file_identity(vault, source_zip_path, role="source_zip")
    evidence_bundle = _file_identity(vault, evidence_bundle_path, role="evidence_bundle")
    closeout = read_json_object(_resolve(vault, closeout_summary_path))
    batch_manifest = read_json_object(_resolve(vault, batch_manifest_path))
    self_check = read_json_object(_resolve(vault, self_check_path))
    audit_manifest = _audit_pack_manifest(vault, evidence_bundle_path)
    verification = _verification(
        source_zip=source_zip,
        evidence_bundle=evidence_bundle,
        closeout=closeout,
        batch_manifest=batch_manifest,
        self_check=self_check,
        audit_pack_manifest=audit_manifest,
    )
    reports = {
        "release_closeout_summary": _report_identity(vault, closeout_summary_path, role="release_authority"),
        "release_closeout_batch_manifest": _report_identity(vault, batch_manifest_path, role="batch_authority"),
        "release_evidence_closeout_self_check": _report_identity(vault, self_check_path, role="self_check"),
    }
    status_view = release_status_v2_view(batch_manifest)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_live_artifact_attestation",
            producer=PRODUCER,
            source_command=(
                "python -m ops.scripts.release.release_live_artifact_attestation build "
                "--vault . --source-zip-path "
                f"{source_zip_path} --evidence-bundle-path {evidence_bundle_path}"
            ),
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/release/release_live_artifact_attestation.py"],
            file_inputs={
                "source_zip": source_zip_path,
                "evidence_bundle": evidence_bundle_path,
                "release_closeout_summary": closeout_summary_path,
                "release_closeout_batch_manifest": batch_manifest_path,
                "release_evidence_closeout_self_check": self_check_path,
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": verification["status"],
        "source_zip": source_zip,
        "evidence_bundle": evidence_bundle,
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
            "source_tree_fingerprint": reports["release_closeout_batch_manifest"]["source_tree_fingerprint"],
            "evidence_set_digest": str(
                batch_manifest.get("audit_materialization", {}).get("evidence_set_digest", "")
            ),
            "audit_pack_evidence_set_digest": str(audit_manifest.get("evidence_set_digest", "")),
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
) -> dict[str, Any]:
    attestation = read_json_object(_resolve(vault, attestation_path))
    schema = load_schema_with_vault_override(vault, SCHEMA_PATH)
    validate_or_raise(attestation, schema, context="release live artifact attestation validation failed")
    current = build_attestation(
        vault,
        source_zip_path=source_zip_path,
        evidence_bundle_path=evidence_bundle_path,
        closeout_summary_path=closeout_summary_path,
        batch_manifest_path=batch_manifest_path,
        self_check_path=self_check_path,
        context=RuntimeContext.from_policy(load_policy(vault)[0]),
    )
    expected_bindings = attestation.get("bindings", {})
    current_bindings = current.get("bindings", {})
    binding_mismatches = [
        key
        for key in sorted(set(expected_bindings) | set(current_bindings))
        if expected_bindings.get(key) != current_bindings.get(key)
    ]
    status = "pass" if current["status"] == "pass" and not binding_mismatches else "fail"
    return {
        "status": status,
        "attestation_path": attestation_path,
        "binding_mismatches": binding_mismatches,
        "verification": current["verification"],
    }


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
    build.add_argument("--closeout-summary-path", default=DEFAULT_CLOSEOUT_SUMMARY)
    build.add_argument("--batch-manifest-path", default=DEFAULT_BATCH_MANIFEST)
    build.add_argument("--self-check-path", default=DEFAULT_SELF_CHECK)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--vault", default=".")
    verify.add_argument("--attestation", required=True)
    verify.add_argument("--source-zip-path", required=True)
    verify.add_argument("--evidence-bundle-path", required=True)
    verify.add_argument("--closeout-summary-path", required=True)
    verify.add_argument("--batch-manifest-path", required=True)
    verify.add_argument("--self-check-path", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.command_name == "build":
        payload = build_attestation(
            vault,
            source_zip_path=args.source_zip_path,
            evidence_bundle_path=args.evidence_bundle_path,
            closeout_summary_path=args.closeout_summary_path,
            batch_manifest_path=args.batch_manifest_path,
            self_check_path=args.self_check_path,
        )
        destination = write_attestation(vault, payload, args.out)
        print(display_path(vault, destination))
        return 0 if payload["status"] == "pass" else 1

    result = verify_attestation(
        vault,
        attestation_path=args.attestation,
        source_zip_path=args.source_zip_path,
        evidence_bundle_path=args.evidence_bundle_path,
        closeout_summary_path=args.closeout_summary_path,
        batch_manifest_path=args.batch_manifest_path,
        self_check_path=args.self_check_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
