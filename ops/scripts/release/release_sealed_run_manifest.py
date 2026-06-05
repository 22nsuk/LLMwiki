#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.core.release_authority_state_runtime import (
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.release.release_run_manifest import (
    DEFAULT_DISTRIBUTION_ZIP,
    DEFAULT_OUT as DEFAULT_RUN_MANIFEST,
    _file_identity,
    _resolve,
    _status_label,
    git_commit,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "build/release/release-sealed-run-manifest.json"
SCHEMA_PATH = "ops/schemas/release-sealed-run-manifest.schema.json"
PRODUCER = "ops.scripts.release_sealed_run_manifest"
SOURCE_COMMAND = "python -m ops.scripts.release_sealed_run_manifest --vault ."
DEFAULT_BATCH_MANIFEST = "build/release/release-closeout-batch-manifest.json"
DEFAULT_EXTERNAL_MANIFEST = "build/release/external-report-reference-manifest.json"
DEFAULT_SELF_CHECK = "build/release/release-evidence-closeout-self-check.json"
DEFAULT_POST_SEAL_ATTESTATION = "build/release/release-sealed-post-seal-attestation.json"
DEFAULT_SEALED_REHEARSAL_CHECK = "build/release/release-closeout-sealed-rehearsal-check.json"
EXPECTED_SIDECAR_KINDS = {
    "batch_manifest": "release_closeout_batch_manifest",
    "external_manifest": "external_report_reference_manifest",
    "self_check": "release_evidence_closeout_self_check",
    "post_seal_attestation": "release_sealed_post_seal_attestation",
    "sealed_rehearsal_check": "release_closeout_sealed_rehearsal_check",
}


def _json_identity(vault: Path, path_value: str | Path) -> dict[str, Any]:
    identity = _file_identity(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path_value))
    if diagnostics.get("status") != "ok":
        payload = {}
    identity.update(
        {
            "load_status": str(diagnostics.get("status", "")),
            "artifact_kind": str(payload.get("artifact_kind", "")),
            "producer": str(payload.get("producer", "")),
            "generated_at": str(payload.get("generated_at", "")),
            "status": _status_label(payload.get("status")),
            "source_revision": str(payload.get("source_revision", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
        }
    )
    return identity


def _unique_failures(failures: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for failure in failures:
        if failure and failure not in seen:
            seen.add(failure)
            result.append(failure)
    return result


def _sealed_authority_axes(vault: Path, batch_manifest: str) -> dict[str, Any]:
    path = _resolve(vault, batch_manifest)
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok" or not isinstance(payload, dict):
        return {"sealed_release_status": "unknown"}
    status_view = release_status_v2_view_with_readiness_fallback(payload)
    return {
        "sealed_release_status": str(status_view.get("sealed_release_status", "unknown")).strip(),
    }


def _run_manifest_expected_zip_sha(run_manifest: dict[str, Any]) -> str:
    distribution_zip = run_manifest.get("distribution_zip")
    if isinstance(distribution_zip, dict):
        return str(distribution_zip.get("sha256", "")).strip()
    fingerprints = run_manifest.get("input_fingerprints")
    if isinstance(fingerprints, dict):
        return str(fingerprints.get("distribution_zip", "")).strip()
    return ""


def _run_manifest_fingerprint(run_manifest: dict[str, Any]) -> str:
    for key in ("final_source_tree_fingerprint", "source_tree_fingerprint"):
        value = str(run_manifest.get(key, "")).strip()
        if value:
            return value
    return ""


def build_manifest(
    vault: Path,
    *,
    run_manifest: str = DEFAULT_RUN_MANIFEST,
    source_zip: str = DEFAULT_DISTRIBUTION_ZIP,
    batch_manifest: str = DEFAULT_BATCH_MANIFEST,
    external_manifest: str = DEFAULT_EXTERNAL_MANIFEST,
    self_check: str = DEFAULT_SELF_CHECK,
    post_seal_attestation: str = DEFAULT_POST_SEAL_ATTESTATION,
    sealed_rehearsal_check: str = DEFAULT_SEALED_REHEARSAL_CHECK,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    run_identity = _json_identity(vault, run_manifest)
    run_payload, run_diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, run_manifest))
    if run_diagnostics.get("status") != "ok":
        run_payload = {}
    source_zip_identity = _file_identity(vault, source_zip)
    sidecars = {
        "batch_manifest": _json_identity(vault, batch_manifest),
        "external_manifest": _json_identity(vault, external_manifest),
        "self_check": _json_identity(vault, self_check),
        "post_seal_attestation": _json_identity(vault, post_seal_attestation),
        "sealed_rehearsal_check": _json_identity(vault, sealed_rehearsal_check),
    }
    sealed_axes = _sealed_authority_axes(vault, batch_manifest)
    run_fingerprint = _run_manifest_fingerprint(run_payload)
    run_zip_sha = _run_manifest_expected_zip_sha(run_payload)
    checks = {
        "run_manifest_present": bool(run_identity["exists"]),
        "run_manifest_load_ok": run_identity["load_status"] == "ok",
        "run_manifest_artifact_kind_ok": run_identity["artifact_kind"] == "release_run_manifest",
        "run_manifest_pass": run_identity["status"] == "pass",
        "source_tree_fingerprint_matches_run_manifest": bool(run_fingerprint)
        and run_fingerprint == fingerprint,
        "run_manifest_source_revision_current": run_identity["source_revision"]
        in {commit, "source_package_without_git"},
        "source_zip_present": bool(source_zip_identity["exists"]),
        "source_zip_matches_run_manifest": bool(run_zip_sha)
        and run_zip_sha == str(source_zip_identity["sha256"]),
        "sidecars_present": all(bool(item["exists"]) for item in sidecars.values()),
        "sidecars_load_ok": all(item["load_status"] == "ok" for item in sidecars.values()),
        "sidecars_artifact_kind_ok": all(
            sidecars[key]["artifact_kind"] == expected
            for key, expected in EXPECTED_SIDECAR_KINDS.items()
        ),
        "sidecars_source_tree_fingerprints_current": all(
            sidecar["source_tree_fingerprint"] == fingerprint
            for sidecar in sidecars.values()
        ),
        "sidecars_source_revisions_current": all(
            sidecar["source_revision"] in {commit, "source_package_without_git"}
            for sidecar in sidecars.values()
        ),
        "post_seal_attestation_pass": sidecars["post_seal_attestation"]["status"] == "pass",
        "sealed_rehearsal_check_pass": sidecars["sealed_rehearsal_check"]["status"] == "pass",
    }
    failures = [name for name, passed in checks.items() if not passed]
    status = "pass" if not failures else "fail"
    input_fingerprints = {
        "run_manifest": str(run_identity["sha256"]),
        "source_zip": str(source_zip_identity["sha256"]),
        **{key: str(value["sha256"]) for key, value in sidecars.items()},
    }
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_sealed_run_manifest",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": input_fingerprints,
        "schema_version": 2,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "sealed_release_status": sealed_axes["sealed_release_status"],
        "sealed_package_authority": "sealed" if status == "pass" else "blocked",
        "run_manifest": run_identity,
        "source_zip": source_zip_identity,
        "sidecars": sidecars,
        "checks": checks,
        "failures": _unique_failures(failures),
    }


def write_manifest(vault: Path, manifest: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release-sealed-run manifest schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify the sealed release-run manifest.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-manifest", default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--source-zip", default=DEFAULT_DISTRIBUTION_ZIP)
    parser.add_argument("--batch-manifest", default=DEFAULT_BATCH_MANIFEST)
    parser.add_argument("--external-manifest", default=DEFAULT_EXTERNAL_MANIFEST)
    parser.add_argument("--self-check", default=DEFAULT_SELF_CHECK)
    parser.add_argument("--post-seal-attestation", default=DEFAULT_POST_SEAL_ATTESTATION)
    parser.add_argument("--sealed-rehearsal-check", default=DEFAULT_SEALED_REHEARSAL_CHECK)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    manifest = build_manifest(
        vault,
        run_manifest=args.run_manifest,
        source_zip=args.source_zip,
        batch_manifest=args.batch_manifest,
        external_manifest=args.external_manifest,
        self_check=args.self_check,
        post_seal_attestation=args.post_seal_attestation,
        sealed_rehearsal_check=args.sealed_rehearsal_check,
    )
    path = write_manifest(vault, manifest, args.out)
    print(display_path(vault, path))
    if args.check:
        print(f"release_sealed_run_status={manifest['status']}")
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
