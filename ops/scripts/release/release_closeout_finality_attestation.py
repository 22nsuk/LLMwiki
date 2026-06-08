#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.release.release_status_v2 import release_status_v2_view
from ops.scripts.runtime_context import RuntimeContext

DEFAULT_OUT = "ops/reports/release-closeout-finality-attestation.json"
PRODUCER = "ops.scripts.release_closeout_finality_attestation"
SCHEMA_PATH = "ops/schemas/release-closeout-finality-attestation.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.release_closeout_finality_attestation --vault ."
FIXED_POINT_REPORT_PATH = "ops/reports/release-closeout-fixed-point.json"
BATCH_MANIFEST_PATH = "ops/reports/release-closeout-batch-manifest.json"
SELF_CHECK_PATH = "ops/reports/release-evidence-closeout-self-check.json"
EXTERNAL_REPORT_MANIFEST_PATH = "external-reports/report-reference-manifest.json"
SHA256_MISSING = "missing"


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return SHA256_MISSING
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_optional(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    raw_payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _tracked_paths_from_fixed_point(fixed_point: dict[str, Any]) -> list[str]:
    tracked = fixed_point.get("tracked_artifacts")
    if isinstance(tracked, list):
        paths = [
            str(item.get("path", "")).strip()
            for item in tracked
            if isinstance(item, dict) and str(item.get("path", "")).strip()
        ]
        if paths:
            return sorted(dict.fromkeys(paths))
    final_map = fixed_point.get("final_digest_map")
    if isinstance(final_map, dict):
        return sorted(str(path) for path in final_map)
    return []


def _digest_map(vault: Path, paths: list[str]) -> dict[str, str]:
    return {path: _sha256_file(vault / path) for path in paths}


def _digest_mismatches(
    expected: dict[str, Any],
    actual: dict[str, str],
) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for path in sorted(set(expected) | set(actual)):
        expected_digest = str(expected.get(path, SHA256_MISSING))
        actual_digest = str(actual.get(path, SHA256_MISSING))
        if expected_digest == actual_digest:
            continue
        mismatches.append(
            {
                "path": path,
                "fixed_point_digest": expected_digest,
                "current_digest": actual_digest,
            }
        )
    return mismatches


def _fixed_point_summary(vault: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload, load_status = _load_optional(vault, FIXED_POINT_REPORT_PATH)
    digest = _sha256_file(vault / FIXED_POINT_REPORT_PATH)
    summary = {
        "path": FIXED_POINT_REPORT_PATH,
        "digest": digest,
        "load_status": load_status,
        "status": str(payload.get("status", "missing")).strip() if payload else "missing",
        "converged": bool(payload.get("converged", False)) if payload else False,
        "converged_iteration": int(payload.get("converged_iteration", 0) or 0) if payload else 0,
        "final_digest_map": payload.get("final_digest_map", {}) if isinstance(payload.get("final_digest_map"), dict) else {},
    }
    return payload, summary, digest


def _batch_manifest_summary(vault: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload, load_status = _load_optional(vault, BATCH_MANIFEST_PATH)
    digest = _sha256_file(vault / BATCH_MANIFEST_PATH)
    raw_finality = payload.get("finality")
    finality: dict[str, Any] = raw_finality if isinstance(raw_finality, dict) else {}
    status_view = release_status_v2_view(payload) if payload else {}
    summary = {
        "path": BATCH_MANIFEST_PATH,
        "digest": digest,
        "load_status": load_status,
        "status": str(status_view.get("compatibility_status_value", "missing")).strip()
        if payload
        else "missing",
        "release_authority_status": str(status_view.get("release_authority_status", "unknown")).strip(),
        "semantic_release_status": str(status_view.get("semantic_release_status", "unknown")).strip(),
        "sealed_release_status": str(status_view.get("sealed_release_status", "unknown")).strip(),
        "finality_required": bool(finality.get("finality_required", False)),
        "finality_attestation_path": str(finality.get("finality_attestation_path", "")).strip(),
    }
    return payload, summary, digest


def _self_check_summary(vault: Path, *, batch_digest: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload, load_status = _load_optional(vault, SELF_CHECK_PATH)
    digest = _sha256_file(vault / SELF_CHECK_PATH)
    raw_status = payload.get("status")
    status_payload: dict[str, Any] = raw_status if isinstance(raw_status, dict) else {}
    raw_closeout_inputs = payload.get("closeout_inputs")
    closeout_inputs: dict[str, Any] = raw_closeout_inputs if isinstance(raw_closeout_inputs, dict) else {}
    batch_fingerprint = str(closeout_inputs.get("batch_manifest_fingerprint", "")).strip()
    summary = {
        "path": SELF_CHECK_PATH,
        "digest": digest,
        "load_status": load_status,
        "result": str(status_payload.get("result", "missing")).strip() if payload else "missing",
        "batch_manifest_fingerprint": batch_fingerprint,
        "batch_manifest_fingerprint_matches_current": bool(batch_fingerprint and batch_fingerprint == batch_digest),
    }
    return payload, summary, digest


def _external_report_manifest_summary(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_optional(vault, EXTERNAL_REPORT_MANIFEST_PATH)
    raw_provenance = payload.get("distribution_provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    return {
        "path": EXTERNAL_REPORT_MANIFEST_PATH,
        "digest": _sha256_file(vault / EXTERNAL_REPORT_MANIFEST_PATH),
        "load_status": load_status,
        "mode": str(provenance.get("mode", "")).strip(),
        "distribution_provenance_status": str(provenance.get("status", "")).strip(),
    }


def _finality_failures(
    *,
    fixed_point_report: dict[str, Any],
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    matches_fixed_point_digest_map: bool,
    digest_mismatches: list[dict[str, str]],
) -> list[str]:
    failures: list[str] = []
    if fixed_point_report["load_status"] != "ok":
        failures.append("fixed_point_report_unavailable")
    if fixed_point_report["status"] != "pass" or not fixed_point_report["converged"]:
        failures.append("fixed_point_not_converged")
    if batch_manifest["load_status"] != "ok":
        failures.append("batch_manifest_unavailable")
    if not batch_manifest["finality_required"]:
        failures.append("batch_manifest_finality_not_required")
    if batch_manifest["finality_attestation_path"] != DEFAULT_OUT:
        failures.append("batch_manifest_finality_pointer_mismatch")
    if self_check["load_status"] != "ok":
        failures.append("self_check_unavailable")
    if self_check["result"] != "pass":
        failures.append("self_check_not_pass")
    if not self_check["batch_manifest_fingerprint_matches_current"]:
        failures.append("self_check_batch_digest_mismatch")
    if not matches_fixed_point_digest_map:
        failures.append("tracked_digest_map_mismatch")
        failures.extend(f"digest_mismatch:{item['path']}" for item in digest_mismatches)
    return failures


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    fixed_payload, fixed_point_report, _fixed_digest = _fixed_point_summary(vault)
    _batch_payload, batch_manifest, batch_digest = _batch_manifest_summary(vault)
    _self_payload, self_check, _self_digest = _self_check_summary(vault, batch_digest=batch_digest)
    external_report_manifest = _external_report_manifest_summary(vault)

    tracked_paths = _tracked_paths_from_fixed_point(fixed_payload)
    tracked_digest_map = _digest_map(vault, tracked_paths)
    fixed_point_digest_map = fixed_point_report["final_digest_map"]
    digest_mismatches = _digest_mismatches(fixed_point_digest_map, tracked_digest_map)
    matches_fixed_point_digest_map = not digest_mismatches and bool(tracked_paths)
    finality_failures = _finality_failures(
        fixed_point_report=fixed_point_report,
        batch_manifest=batch_manifest,
        self_check=self_check,
        matches_fixed_point_digest_map=matches_fixed_point_digest_map,
        digest_mismatches=digest_mismatches,
    )
    finality_status = "pass" if not finality_failures else "fail"

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_closeout_finality_attestation",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/release_closeout_finality_attestation.py"],
            file_inputs={
                "fixed_point_report": FIXED_POINT_REPORT_PATH,
                "batch_manifest": BATCH_MANIFEST_PATH,
                "self_check": SELF_CHECK_PATH,
                "external_report_manifest": EXTERNAL_REPORT_MANIFEST_PATH,
            },
            path_group_inputs={"tracked_artifacts": tracked_paths},
            text_inputs={
                "finality_status": finality_status,
                "matches_fixed_point_digest_map": str(matches_fixed_point_digest_map),
            },
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "fixed_point_report": fixed_point_report,
        "batch_manifest": batch_manifest,
        "self_check": self_check,
        "external_report_manifest": external_report_manifest,
        "tracked_digest_map": tracked_digest_map,
        "matches_fixed_point_digest_map": matches_fixed_point_digest_map,
        "digest_mismatches": digest_mismatches,
        "finality_status": finality_status,
        "finality_failures": finality_failures,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release closeout finality attestation schema validation failed",
        )
    )


def verify_attestation(vault: Path, attestation_path: str = DEFAULT_OUT) -> tuple[bool, list[str]]:
    resolved = resolve_schema_backed_report_output_path(
        vault,
        attestation_path,
        default_relative_path=DEFAULT_OUT,
    )
    payload, diagnostics = load_optional_json_object_with_diagnostics(resolved)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return False, [f"attestation_load_status:{load_status}"]

    failures: list[str] = []
    for field in ("fixed_point_report", "batch_manifest", "self_check", "external_report_manifest"):
        item = payload.get(field)
        if not isinstance(item, dict):
            failures.append(f"{field}_missing")
            continue
        rel_path = str(item.get("path", "")).strip()
        expected = str(item.get("digest", "")).strip()
        actual = _sha256_file(vault / rel_path) if rel_path else SHA256_MISSING
        if expected != actual:
            failures.append(f"{field}_digest_mismatch")

    fixed_payload, _fixed_summary, _fixed_digest = _fixed_point_summary(vault)
    tracked_paths = _tracked_paths_from_fixed_point(fixed_payload)
    current_tracked_digest_map = _digest_map(vault, tracked_paths)
    recorded_map = payload.get("tracked_digest_map")
    if not isinstance(recorded_map, dict) or current_tracked_digest_map != {
        str(path): str(digest) for path, digest in recorded_map.items()
    }:
        failures.append("tracked_digest_map_current_mismatch")
    raw_fixed_map = fixed_payload.get("final_digest_map")
    fixed_map: dict[str, Any] = raw_fixed_map if isinstance(raw_fixed_map, dict) else {}
    if _digest_mismatches(fixed_map, current_tracked_digest_map):
        failures.append("fixed_point_digest_map_current_mismatch")
    if str(payload.get("finality_status", "")).strip() != "pass":
        failures.append("attestation_finality_status_not_pass")
    return not failures, failures


def verify_attestation_report(vault: Path, attestation_path: str = DEFAULT_OUT) -> dict[str, Any]:
    ok, failures = verify_attestation(vault, attestation_path)
    return {"status": "pass" if ok else "fail", "failures": failures}


def write_verify_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    raw_path = Path(out_path)
    destination = raw_path if raw_path.is_absolute() else vault / raw_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify release closeout finality attestation.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--attestation", default=DEFAULT_OUT)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--verify-out")
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.verify:
        report = verify_attestation_report(vault, args.attestation)
        if args.verify_out:
            write_verify_report(vault, report, args.verify_out)
        stream = sys.stdout if report["status"] == "pass" else sys.stderr
        print(json.dumps(report, sort_keys=True), file=stream)
        return 0 if report["status"] == "pass" or args.no_fail else 1
    report = build_report(vault, policy_path=args.policy_path)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0 if report["finality_status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
