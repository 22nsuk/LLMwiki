#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_binding_runtime import RAW_BINDING_MODE
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.schema_constants_runtime import (
        SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH,
    )
    from ops.scripts.supply_chain.in_toto_statement import (
        DEFAULT_OUT as IN_TOTO_DEFAULT_OUT,
    )
    from ops.scripts.supply_chain.supply_chain_artifact_model import build_model
    from ops.scripts.supply_chain.supply_chain_provenance import sha256_file
else:
    from ops.scripts.core.artifact_binding_runtime import RAW_BINDING_MODE
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.schema_constants_runtime import (
        SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH,
    )

    from .in_toto_statement import DEFAULT_OUT as IN_TOTO_DEFAULT_OUT
    from .supply_chain_artifact_model import build_model
    from .supply_chain_provenance import sha256_file


DEFAULT_OUT = "ops/reports/sigstore-bundle-verification.json"
TOOL_NAME = "ops.scripts.sigstore_bundle"
ARTIFACT_KIND = "sigstore_bundle_verification"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.sigstore_bundle"
BUNDLE_BINDING_MODE = RAW_BINDING_MODE


@dataclass(frozen=True)
class _BundleEvidence:
    ref: str
    present: bool
    parseable: bool
    has_sigstore_shape: bool
    raw_digest: str
    size_bytes: int


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


def _bundle_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _has_sigstore_bundle_shape(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    verification_material = (
        payload.get("verificationMaterial")
        or payload.get("verification_material")
        or payload.get("verification_materials")
    )
    signed_content = (
        payload.get("messageSignature")
        or payload.get("message_signature")
        or payload.get("dsseEnvelope")
        or payload.get("dsse_envelope")
    )
    return isinstance(verification_material, dict) and isinstance(signed_content, dict)


def _artifact_subject_refs(model: dict[str, Any]) -> list[str]:
    context = model["artifact_context"]
    return [
        context["cyclonedx_ref"],
        context["spdx_ref"],
        context["openvex_ref"],
        context["in_toto_statement_ref"],
    ]


def _collect_subjects(vault: Path, refs: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    subjects: list[dict[str, Any]] = []
    missing: list[str] = []
    for report_ref in refs:
        path = _resolve_ref(vault, report_ref)
        if path.exists():
            subjects.append(_subject(path, vault))
        else:
            missing.append(report_ref)
    return subjects, missing


def _in_toto_subject_digests_match(
    vault: Path,
    statement_ref: str,
    subjects: list[dict[str, Any]],
) -> bool:
    statement_path = _resolve_ref(vault, statement_ref)
    if not statement_path.exists():
        return False
    statement = json.loads(statement_path.read_text(encoding="utf-8"))
    digest_by_name = {
        item["name"]: item["digest"]["sha256"] for item in statement.get("subject", [])
    }
    statement_report_path = report_path(vault, statement_path)
    expected_subjects = [
        item for item in subjects if item["path"] != statement_report_path
    ]
    if not expected_subjects:
        return False
    return all(
        digest_by_name.get(item["path"]) == item["sha256"]
        for item in expected_subjects
    )


def _bundle_evidence(
    vault: Path,
    bundle_ref: str | None,
) -> _BundleEvidence:
    if not bundle_ref:
        return _BundleEvidence("", False, False, False, "", 0)
    bundle_path = _resolve_ref(vault, bundle_ref)
    resolved_bundle_ref = report_path(vault, bundle_path) if bundle_path.exists() else bundle_ref
    bundle_present = bundle_path.exists()
    bundle_payload = _bundle_payload(bundle_path) if bundle_present else None
    bundle_parseable = bundle_payload is not None
    return _BundleEvidence(
        resolved_bundle_ref,
        bundle_present,
        bundle_parseable,
        _has_sigstore_bundle_shape(bundle_payload),
        sha256_file(bundle_path) if bundle_present else "",
        bundle_path.stat().st_size if bundle_present else 0,
    )


def _verification_checks(
    *,
    missing: list[str],
    in_toto_match: bool,
    bundle_present: bool,
    bundle_parseable: bool,
    bundle_has_sigstore_shape: bool,
) -> list[dict[str, Any]]:
    return [
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
            "pass": bundle_present,
            "details": "External Sigstore bundle supplied." if bundle_present else "No external Sigstore bundle supplied; local integrity checks only.",
        },
        {
            "rule": "external_bundle_json_parseable",
            "pass": bundle_parseable,
            "details": (
                "External Sigstore bundle is parseable JSON."
                if bundle_parseable
                else "External Sigstore bundle is missing or is not parseable JSON."
            ),
        },
        {
            "rule": "external_bundle_has_sigstore_shape",
            "pass": bundle_has_sigstore_shape,
            "details": (
                "External Sigstore bundle carries verification material and signed content."
                if bundle_has_sigstore_shape
                else "External Sigstore bundle lacks verification material or signed content."
            ),
        },
    ]


def _verification_status(
    checks: list[dict[str, Any]],
    *,
    bundle_present: bool,
) -> str:
    if not bundle_present:
        return "local-integrity-only"
    if all(check["pass"] for check in checks):
        return "verified-external-bundle"
    return "external-bundle-verification-failed"


def _bundle_binding_status(bundle_ref: str | None, bundle: _BundleEvidence) -> str:
    if bundle.present:
        return "bound"
    return "missing" if bundle_ref else "not_applicable"


def _report_subjects(vault: Path, subjects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if subjects:
        return subjects
    in_toto_path = _resolve_ref(vault, IN_TOTO_DEFAULT_OUT)
    return [_subject(in_toto_path, vault)] if in_toto_path.exists() else []


def _artifact_context(model: dict[str, Any]) -> dict[str, Any]:
    context = model["artifact_context"]
    return {
        "artifact_set_id": context["artifact_set_id"],
        "in_toto_statement_ref": context["in_toto_statement_ref"],
        "spdx_ref": context["spdx_ref"],
        "openvex_ref": context["openvex_ref"],
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
    subjects, missing = _collect_subjects(vault, _artifact_subject_refs(model))
    bundle = _bundle_evidence(vault, bundle_ref)
    checks = _verification_checks(
        missing=missing,
        in_toto_match=_in_toto_subject_digests_match(
            vault,
            model["artifact_context"]["in_toto_statement_ref"],
            subjects,
        ),
        bundle_present=bundle.present,
        bundle_parseable=bundle.parseable,
        bundle_has_sigstore_shape=bundle.has_sigstore_shape,
    )
    status = _verification_status(checks, bundle_present=bundle.present)
    report = {
        "$schema": SIGSTORE_BUNDLE_VERIFICATION_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": model["generated_at"],
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "artifact_context": _artifact_context(model),
        "status": status,
        "bundle_ref": bundle.ref,
        "bundle_binding": {
            "binding_mode": BUNDLE_BINDING_MODE,
            "status": _bundle_binding_status(bundle_ref, bundle),
            "raw_digest": bundle.raw_digest,
            "size_bytes": bundle.size_bytes,
        },
        "subjects": _report_subjects(vault, subjects),
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
            "ops/scripts/supply_chain/sigstore_bundle.py",
            "ops/scripts/supply_chain/in_toto_statement.py",
            "ops/scripts/supply_chain/supply_chain_artifact_model.py",
        ],
        text_inputs={
            "artifact_set_id": str(model["artifact_context"]["artifact_set_id"]),
            "subject_count": str(len(subjects)),
            "status": status,
            "bundle_ref": bundle.ref,
            "bundle_binding_mode": BUNDLE_BINDING_MODE,
            "bundle_raw_digest": bundle.raw_digest,
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
