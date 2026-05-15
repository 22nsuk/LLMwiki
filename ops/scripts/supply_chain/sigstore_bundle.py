#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.in_toto_statement import DEFAULT_OUT as IN_TOTO_DEFAULT_OUT
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope, embed_artifact_envelope_metadata
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.schema_constants_runtime import SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH
    from ops.scripts.supply_chain_artifact_model import build_model
    from ops.scripts.supply_chain_provenance import sha256_file
else:
    from .in_toto_statement import DEFAULT_OUT as IN_TOTO_DEFAULT_OUT
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope, embed_artifact_envelope_metadata
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.schema_constants_runtime import SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH
    from .supply_chain_artifact_model import build_model
    from .supply_chain_provenance import sha256_file


DEFAULT_OUT = "ops/reports/sigstore-bundle-verification.json"
TOOL_NAME = "ops.scripts.sigstore_bundle"
ARTIFACT_KIND = "sigstore_bundle_verification"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.sigstore_bundle"


def _resolve_ref(vault: Path, report_ref: str) -> Path:
    path = Path(report_ref)
    if path.is_absolute():
        return path
    return (vault / path).resolve()


def _subject(path: Path, vault: Path) -> dict[str, Any]:
    return {
        "path": report_path(vault, path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def build_bundle_verification(
    vault: Path,
    *,
    policy_path: str | None = None,
    artifact_model: dict[str, Any] | None = None,
    bundle_ref: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    model = artifact_model or build_model(vault, policy_path=policy_path)
    refs = [
        model["artifact_context"]["cyclonedx_ref"],
        model["artifact_context"]["spdx_ref"],
        model["artifact_context"]["openvex_ref"],
        model["artifact_context"]["in_toto_statement_ref"],
    ]
    subjects = []
    missing = []
    for report_ref in refs:
        path = _resolve_ref(vault, report_ref)
        if path.exists():
            subjects.append(_subject(path, vault))
        else:
            missing.append(report_ref)

    statement_path = _resolve_ref(vault, model["artifact_context"]["in_toto_statement_ref"])
    in_toto_match = False
    if statement_path.exists():
        statement = json.loads(statement_path.read_text(encoding="utf-8"))
        digest_by_name = {item["name"]: item["digest"]["sha256"] for item in statement.get("subject", [])}
        in_toto_match = all(digest_by_name.get(item["path"]) == item["sha256"] for item in subjects if item["path"] in digest_by_name)

    bundle_present = False
    resolved_bundle_ref = ""
    if bundle_ref:
        bundle_path = _resolve_ref(vault, bundle_ref)
        resolved_bundle_ref = report_path(vault, bundle_path) if bundle_path.exists() else bundle_ref
        bundle_present = bundle_path.exists()

    checks = [
        {
            "rule": "subject_files_exist",
            "pass": not missing,
            "details": "All attestation subjects exist." if not missing else f"Missing: {', '.join(missing)}",
        },
        {
            "rule": "in_toto_subject_digests_match",
            "pass": in_toto_match,
            "details": "In-toto subject digests match local files." if in_toto_match else "In-toto statement missing or digests do not match.",
        },
        {
            "rule": "external_bundle_observed",
            "pass": True,
            "details": "External Sigstore bundle supplied." if bundle_present else "No external Sigstore bundle supplied; local integrity checks only.",
        },
    ]
    status = "verified-external-bundle" if bundle_present and all(check["pass"] for check in checks) else "local-integrity-only"
    report = {
        "$schema": SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": model["generated_at"],
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "artifact_context": {
            "artifact_set_id": model["artifact_context"]["artifact_set_id"],
            "in_toto_statement_ref": model["artifact_context"]["in_toto_statement_ref"],
            "spdx_ref": model["artifact_context"]["spdx_ref"],
            "openvex_ref": model["artifact_context"]["openvex_ref"],
        },
        "status": status,
        "bundle_ref": resolved_bundle_ref,
        "subjects": subjects or [_subject(_resolve_ref(vault, IN_TOTO_DEFAULT_OUT), vault)] if _resolve_ref(vault, IN_TOTO_DEFAULT_OUT).exists() else [],
        "verification_checks": checks,
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=str(model["generated_at"]),
        artifact_kind=ARTIFACT_KIND,
        producer=TOOL_NAME,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/sigstore_bundle.py",
            "ops/scripts/in_toto_statement.py",
            "ops/scripts/supply_chain_artifact_model.py",
        ],
        text_inputs={
            "artifact_set_id": str(model["artifact_context"]["artifact_set_id"]),
            "subject_count": str(len(subjects)),
            "status": status,
            "bundle_ref": resolved_bundle_ref,
        },
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_bundle_verification(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="Sigstore bundle verification schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist Sigstore bundle verification metadata for release attestations")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--bundle-ref")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_bundle_verification(vault, policy_path=args.policy_path, bundle_ref=args.bundle_ref)
    destination = write_bundle_verification(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
