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
from ops.scripts.output_runtime import display_path
from ops.scripts.release.release_run_manifest import (
    DEFAULT_DISTRIBUTION_ZIP,
    _file_identity,
    _resolve,
    git_commit,
)
from ops.scripts.release.release_run_manifest import (
    DEFAULT_OUT as DEFAULT_RUN_MANIFEST,
)
from ops.scripts.release.release_sealed_run_manifest import (
    DEFAULT_BATCH_MANIFEST,
    DEFAULT_EXTERNAL_MANIFEST,
    DEFAULT_SELF_CHECK,
    _json_identity,
    _unique_failures,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "build/release/release-sealed-post-seal-attestation.json"
SCHEMA_PATH = "ops/schemas/release-sealed-post-seal-attestation.schema.json"
PRODUCER = "ops.scripts.release_sealed_post_seal_attestation"
SOURCE_COMMAND = "python -m ops.scripts.release_sealed_post_seal_attestation --vault ."
EXPECTED_REPORT_KINDS = {
    "run_manifest": "release_run_manifest",
    "batch_manifest": "release_closeout_batch_manifest",
    "external_manifest": "external_report_reference_manifest",
    "self_check": "release_evidence_closeout_self_check",
}


def _dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _load_report(vault: Path, path_value: str) -> dict[str, Any]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path_value))
    return payload if diagnostics.get("status") == "ok" else {}


def _status_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("result", "")).strip()
    return str(value).strip()


def _run_manifest_expected_zip_sha(run_manifest: dict[str, Any]) -> str:
    distribution_zip = _dict(run_manifest.get("distribution_zip"))
    return str(distribution_zip.get("sha256", "")).strip()


def _run_manifest_fingerprint(run_manifest: dict[str, Any]) -> str:
    return str(
        run_manifest.get("final_source_tree_fingerprint")
        or run_manifest.get("source_tree_fingerprint")
        or ""
    ).strip()


def _zip_sha_from(payload: dict[str, Any], *path: str) -> str:
    cursor: Any = payload
    for key in path:
        cursor = _dict(cursor).get(key)
    return str(cursor or "").strip()


def build_attestation(
    vault: Path,
    *,
    source_zip: str = DEFAULT_DISTRIBUTION_ZIP,
    run_manifest: str = DEFAULT_RUN_MANIFEST,
    batch_manifest: str = DEFAULT_BATCH_MANIFEST,
    external_manifest: str = DEFAULT_EXTERNAL_MANIFEST,
    self_check: str = DEFAULT_SELF_CHECK,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    source_zip_identity = _file_identity(vault, source_zip)
    reports = {
        "run_manifest": _json_identity(vault, run_manifest),
        "batch_manifest": _json_identity(vault, batch_manifest),
        "external_manifest": _json_identity(vault, external_manifest),
        "self_check": _json_identity(vault, self_check),
    }
    run_payload = _load_report(vault, run_manifest)
    batch_payload = _load_report(vault, batch_manifest)
    external_payload = _load_report(vault, external_manifest)
    self_check_payload = _load_report(vault, self_check)
    run_zip_sha = _run_manifest_expected_zip_sha(run_payload)
    run_fingerprint = _run_manifest_fingerprint(run_payload)
    batch_zip_sha = _zip_sha_from(batch_payload, "distribution_package", "sha256")
    external_current_zip_sha = _zip_sha_from(external_payload, "current_distribution_zip", "sha256")
    external_basis_zip_sha = _zip_sha_from(external_payload, "basis_zip", "sha256")
    self_check_watch_status = str(
        _dict(self_check_payload.get("batch_artifact_digest_watch")).get("status", "")
    ).strip()
    checks = {
        "source_zip_present": bool(source_zip_identity["exists"]),
        "run_manifest_present": bool(reports["run_manifest"]["exists"]),
        "run_manifest_load_ok": reports["run_manifest"]["load_status"] == "ok",
        "run_manifest_artifact_kind_ok": reports["run_manifest"]["artifact_kind"]
        == EXPECTED_REPORT_KINDS["run_manifest"],
        "run_manifest_pass": _status_label(run_payload.get("status")) == "pass",
        "source_tree_fingerprint_matches_run_manifest": bool(run_fingerprint)
        and run_fingerprint == fingerprint,
        "source_zip_matches_run_manifest": bool(run_zip_sha)
        and run_zip_sha == str(source_zip_identity["sha256"]),
        "batch_manifest_present": bool(reports["batch_manifest"]["exists"]),
        "batch_manifest_load_ok": reports["batch_manifest"]["load_status"] == "ok",
        "batch_manifest_artifact_kind_ok": reports["batch_manifest"]["artifact_kind"]
        == EXPECTED_REPORT_KINDS["batch_manifest"],
        "batch_manifest_fingerprint_current": reports["batch_manifest"]["source_tree_fingerprint"]
        == fingerprint,
        "external_manifest_present": bool(reports["external_manifest"]["exists"]),
        "external_manifest_load_ok": reports["external_manifest"]["load_status"] == "ok",
        "external_manifest_artifact_kind_ok": reports["external_manifest"]["artifact_kind"]
        == EXPECTED_REPORT_KINDS["external_manifest"],
        "external_manifest_fingerprint_current": reports["external_manifest"]["source_tree_fingerprint"]
        == fingerprint,
        "self_check_present": bool(reports["self_check"]["exists"]),
        "self_check_load_ok": reports["self_check"]["load_status"] == "ok",
        "self_check_artifact_kind_ok": reports["self_check"]["artifact_kind"]
        == EXPECTED_REPORT_KINDS["self_check"],
        "self_check_fingerprint_current": reports["self_check"]["source_tree_fingerprint"]
        == fingerprint,
        "batch_distribution_matches_source_zip": bool(batch_zip_sha)
        and batch_zip_sha == str(source_zip_identity["sha256"]),
        "external_current_distribution_matches_source_zip": bool(external_current_zip_sha)
        and external_current_zip_sha == str(source_zip_identity["sha256"]),
        "external_basis_distribution_matches_source_zip": bool(external_basis_zip_sha)
        and external_basis_zip_sha == str(source_zip_identity["sha256"]),
        "self_check_batch_digest_watch_match": self_check_watch_status == "match",
    }
    failures = [name for name, passed in checks.items() if not passed]
    status = "pass" if not failures else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_sealed_post_seal_attestation",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": {
            "source_zip": str(source_zip_identity["sha256"]),
            **{key: str(value["sha256"]) for key, value in reports.items()},
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "source_zip": source_zip_identity,
        "reports": reports,
        "checks": checks,
        "failures": _unique_failures(failures),
    }


def write_attestation(vault: Path, attestation: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=attestation,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release sealed post-seal attestation schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a sealed post-seal attestation without operator diagnostics.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--source-zip", default=DEFAULT_DISTRIBUTION_ZIP)
    parser.add_argument("--run-manifest", default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--batch-manifest", default=DEFAULT_BATCH_MANIFEST)
    parser.add_argument("--external-manifest", default=DEFAULT_EXTERNAL_MANIFEST)
    parser.add_argument("--self-check", default=DEFAULT_SELF_CHECK)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    attestation = build_attestation(
        vault,
        source_zip=args.source_zip,
        run_manifest=args.run_manifest,
        batch_manifest=args.batch_manifest,
        external_manifest=args.external_manifest,
        self_check=args.self_check,
    )
    path = write_attestation(vault, attestation, args.out)
    print(display_path(vault, path))
    return 0 if attestation["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
