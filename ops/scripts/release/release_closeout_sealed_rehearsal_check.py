#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    load_optional_json_object_with_diagnostics,
    resolve_repo_artifact_path,
)
from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from .release_authority_vocabulary import legacy_sealed_rehearsal_reason_id
from .release_status_v2 import release_status_v2_view
from ops.scripts.runtime_context import RuntimeContext


BATCH_MANIFEST_PATH = "ops/reports/release-closeout-batch-manifest.json"
EXTERNAL_REPORT_REFERENCE_MANIFEST_PATH = (
    "external-reports/report-reference-manifest.json"
)
DEFAULT_OUT = "tmp/release-closeout-sealed-rehearsal-check.json"
SCHEMA_PATH = "ops/schemas/release-closeout-sealed-rehearsal-check.schema.json"
PRODUCER = "ops.scripts.release_closeout_sealed_rehearsal_check"
SOURCE_COMMAND = "python -m ops.scripts.release_closeout_sealed_rehearsal_check --vault ."
AUTHORITY_FAILURE_IDS = {
    "batch_release_authority_not_clean_pass",
    "batch_sealed_release_not_clean_pass",
}


@dataclass(frozen=True)
class DistributionZipFacts:
    path: Path
    display_path: str
    exists: bool
    sha256: str
    entry_count: int


@dataclass(frozen=True)
class LoadedJsonReport:
    payload: dict[str, Any]
    load_status: str
    display_path: str


@dataclass(frozen=True)
class SealedRehearsalInputs:
    generated_at: str
    distribution_zip: DistributionZipFacts
    batch: dict[str, Any]
    batch_load_status: str
    batch_display_path: str
    external: dict[str, Any]
    external_load_status: str
    external_display_path: str
    distribution_package: dict[str, Any]
    external_source_zip_bound: dict[str, Any]
    distribution_provenance: dict[str, Any]
    current_distribution_zip: dict[str, Any]
    basis_zip: dict[str, Any]
    status_view: dict[str, Any]


@dataclass(frozen=True)
class SealedRehearsalDecision:
    status: str
    failures: list[str]
    preflight: dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_entry_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return len(archive.infolist())


def _resolve(vault: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = vault / path
    return path.resolve()


def _load(vault: Path, path_value: str) -> tuple[dict[str, Any], str, str]:
    path = _resolve(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    return payload, status, display_path(vault, path)


def _load_json_report(vault: Path, path_value: str) -> LoadedJsonReport:
    payload, load_status, report_path = _load(vault, path_value)
    return LoadedJsonReport(
        payload=payload,
        load_status=load_status,
        display_path=report_path,
    )


def _object_child(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _distribution_zip_facts(vault: Path, distribution_zip: str) -> DistributionZipFacts:
    distribution_zip_path = _resolve(vault, distribution_zip)
    exists = distribution_zip_path.is_file()
    return DistributionZipFacts(
        path=distribution_zip_path,
        display_path=display_path(vault, distribution_zip_path),
        exists=exists,
        sha256=_sha256_file(distribution_zip_path) if exists else "",
        entry_count=_zip_entry_count(distribution_zip_path) if exists else 0,
    )


def _sealed_rehearsal_inputs(
    vault: Path,
    *,
    generated_at: str,
    distribution_zip: str,
    batch_manifest: str,
    external_manifest: str,
) -> SealedRehearsalInputs:
    distribution_zip_facts = _distribution_zip_facts(vault, distribution_zip)
    batch_report = _load_json_report(vault, batch_manifest)
    external_report = _load_json_report(vault, external_manifest)
    batch = batch_report.payload
    external = external_report.payload
    return SealedRehearsalInputs(
        generated_at=generated_at,
        distribution_zip=distribution_zip_facts,
        batch=batch,
        batch_load_status=batch_report.load_status,
        batch_display_path=batch_report.display_path,
        external=external,
        external_load_status=external_report.load_status,
        external_display_path=external_report.display_path,
        distribution_package=_object_child(batch, "distribution_package"),
        external_source_zip_bound=_object_child(batch, "external_source_zip_bound"),
        distribution_provenance=_object_child(external, "distribution_provenance"),
        current_distribution_zip=_object_child(external, "current_distribution_zip"),
        basis_zip=_object_child(external, "basis_zip"),
        status_view=release_status_v2_view(batch),
    )


def _check_equal(
    failures: list[str], observed: object, expected: object, code: str
) -> None:
    if observed != expected:
        failures.append(code)


def _failure_details(failures: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "failure_id": failure,
            "vocabulary_reason_id": legacy_sealed_rehearsal_reason_id(failure),
            "status_axis": "release_authority"
            if "authority" in failure
            else "sealed_distribution"
            if "sealed" in failure or "distribution" in failure
            else "evidence_binding",
        }
        for failure in failures
    ]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _binding_failure_ids(failures: list[str]) -> list[str]:
    return [failure for failure in failures if failure not in AUTHORITY_FAILURE_IDS]


def _vocabulary_reason_ids(
    failures: list[str],
    batch: dict[str, Any],
) -> list[str]:
    status_view = release_status_v2_view(batch)
    blocker_reasons = _string_list(status_view.get("blocker_reason_ids"))
    if blocker_reasons:
        return blocker_reasons
    return _unique(
        [
            legacy_sealed_rehearsal_reason_id(failure)
            for failure in failures
            if legacy_sealed_rehearsal_reason_id(failure) != failure
        ]
    )


def _preflight_status(
    *,
    status: str,
    failures: list[str],
    batch: dict[str, Any],
) -> dict[str, Any]:
    binding_failures = _binding_failure_ids(failures)
    release_authority_status = str(
        release_status_v2_view(batch).get("release_authority_status", "")
    ).strip()
    authority_blocked = release_authority_status not in {"", "clean_pass"}
    distribution_binding_status = "fail" if binding_failures else "pass"
    if status == "pass":
        preflight_status = "sealed_clean_pass"
        authority_preflight_status = "clean"
        preflight_mode = "clean_required"
    elif distribution_binding_status == "pass" and authority_blocked:
        preflight_status = "binding_pass_authority_blocked"
        authority_preflight_status = "blocked"
        preflight_mode = "expected_blocked"
    elif distribution_binding_status == "fail":
        preflight_status = "binding_failed"
        authority_preflight_status = "blocked" if authority_blocked else "unknown"
        preflight_mode = "binding_failed"
    else:
        preflight_status = "unexpected_failure"
        authority_preflight_status = "unknown"
        preflight_mode = "unexpected_failure"
    return {
        "preflight_status": preflight_status,
        "preflight_mode": preflight_mode,
        "distribution_binding_status": distribution_binding_status,
        "authority_preflight_status": authority_preflight_status,
        "expected_blocked_preflight": preflight_status == "binding_pass_authority_blocked",
        "clean_required_preflight": preflight_status == "sealed_clean_pass",
        "blocking_reason_ids": _vocabulary_reason_ids(failures, batch),
        "unexpected_failure_ids": binding_failures
        if preflight_status != "binding_pass_authority_blocked"
        else [],
        "operator_summary": (
            "distribution binding pass; release authority blocked"
            if preflight_status == "binding_pass_authority_blocked"
            else "sealed release evidence clean"
            if preflight_status == "sealed_clean_pass"
            else f"sealed preflight {preflight_status}"
        ),
    }


def _load_failures(inputs: SealedRehearsalInputs) -> list[str]:
    failures: list[str] = []
    if not inputs.distribution_zip.exists:
        failures.append("distribution_zip_missing")
    if inputs.batch_load_status != "ok":
        failures.append("batch_manifest_unavailable")
    if inputs.external_load_status != "ok":
        failures.append("external_report_reference_manifest_unavailable")
    return failures


def _batch_status_failures(inputs: SealedRehearsalInputs) -> list[str]:
    failures: list[str] = []
    _check_equal(
        failures,
        inputs.status_view.get("release_authority_status"),
        "clean_pass",
        "batch_release_authority_not_clean_pass",
    )
    _check_equal(
        failures,
        inputs.status_view.get("sealed_release_status"),
        "sealed_clean_pass",
        "batch_sealed_release_not_clean_pass",
    )
    _check_equal(
        failures,
        inputs.external_source_zip_bound.get("status"),
        "bound",
        "batch_external_source_zip_not_bound",
    )
    _check_equal(
        failures,
        inputs.distribution_package.get("status"),
        "materialized",
        "batch_distribution_not_materialized",
    )
    return failures


def _distribution_hash_failures(inputs: SealedRehearsalInputs) -> list[str]:
    if not inputs.distribution_zip.sha256:
        return []
    failures: list[str] = []
    distribution_sha256 = inputs.distribution_zip.sha256
    _check_equal(
        failures,
        inputs.distribution_package.get("sha256"),
        distribution_sha256,
        "batch_distribution_sha256_mismatch",
    )
    _check_equal(
        failures,
        inputs.external_source_zip_bound.get("sha256"),
        distribution_sha256,
        "batch_external_source_zip_sha256_mismatch",
    )
    _check_equal(
        failures,
        inputs.current_distribution_zip.get("sha256"),
        distribution_sha256,
        "external_current_distribution_sha256_mismatch",
    )
    _check_equal(
        failures,
        inputs.basis_zip.get("sha256"),
        distribution_sha256,
        "external_basis_zip_sha256_mismatch",
    )
    return failures


def _distribution_entry_count_failures(inputs: SealedRehearsalInputs) -> list[str]:
    if not inputs.distribution_zip.entry_count:
        return []
    failures: list[str] = []
    distribution_entry_count = inputs.distribution_zip.entry_count
    _check_equal(
        failures,
        inputs.current_distribution_zip.get("entry_count"),
        distribution_entry_count,
        "external_current_distribution_entry_count_mismatch",
    )
    _check_equal(
        failures,
        inputs.basis_zip.get("entry_count"),
        distribution_entry_count,
        "external_basis_zip_entry_count_mismatch",
    )
    return failures


def _external_provenance_failures(inputs: SealedRehearsalInputs) -> list[str]:
    failures: list[str] = []
    _check_equal(
        failures,
        inputs.distribution_provenance.get("mode"),
        "strict_review_release",
        "external_manifest_not_strict_review_release",
    )
    _check_equal(
        failures,
        inputs.distribution_provenance.get("status"),
        "basis_current_match",
        "external_manifest_not_bound_to_current_distribution",
    )
    _check_equal(
        failures,
        inputs.distribution_provenance.get("basis_zip_matches_current_distribution"),
        True,
        "external_basis_current_distribution_not_matching",
    )
    return failures


def _sealed_rehearsal_failures(inputs: SealedRehearsalInputs) -> list[str]:
    failures: list[str] = []
    failures.extend(_load_failures(inputs))
    failures.extend(_batch_status_failures(inputs))
    failures.extend(_distribution_hash_failures(inputs))
    failures.extend(_distribution_entry_count_failures(inputs))
    failures.extend(_external_provenance_failures(inputs))
    return failures


def _sealed_rehearsal_decision(
    inputs: SealedRehearsalInputs,
) -> SealedRehearsalDecision:
    failures = _sealed_rehearsal_failures(inputs)
    status = "pass" if not failures else "fail"
    preflight = _preflight_status(
        status=status,
        failures=failures,
        batch=inputs.batch,
    )
    return SealedRehearsalDecision(
        status=status,
        failures=failures,
        preflight=preflight,
    )


def _distribution_zip_summary(inputs: SealedRehearsalInputs) -> dict[str, Any]:
    return {
        "path": inputs.distribution_zip.display_path,
        "exists": inputs.distribution_zip.exists,
        "sha256": inputs.distribution_zip.sha256,
        "entry_count": inputs.distribution_zip.entry_count,
    }


def _batch_manifest_summary(inputs: SealedRehearsalInputs) -> dict[str, Any]:
    return {
        "path": inputs.batch_display_path,
        "load_status": inputs.batch_load_status,
        "release_authority_status": str(
            inputs.status_view.get("release_authority_status", "")
        ).strip(),
        "sealed_release_status": str(
            inputs.status_view.get("sealed_release_status", "")
        ).strip(),
        "external_source_zip_bound_status": str(
            inputs.external_source_zip_bound.get("status", "")
        ).strip(),
        "distribution_package_status": str(
            inputs.distribution_package.get("status", "")
        ).strip(),
    }


def _external_manifest_summary(inputs: SealedRehearsalInputs) -> dict[str, Any]:
    return {
        "path": inputs.external_display_path,
        "load_status": inputs.external_load_status,
        "mode": str(inputs.distribution_provenance.get("mode", "")).strip(),
        "status": str(inputs.distribution_provenance.get("status", "")).strip(),
        "basis_zip_matches_current_distribution": inputs.distribution_provenance.get(
            "basis_zip_matches_current_distribution"
        ),
    }


def _sealed_rehearsal_summary(decision: SealedRehearsalDecision) -> str:
    if decision.status == "pass":
        return (
            "sealed closeout rehearsal passed: batch sealed clean pass and external "
            "strict manifest bind the distribution ZIP"
        )
    if decision.preflight["expected_blocked_preflight"]:
        return str(decision.preflight["operator_summary"])
    return f"sealed closeout rehearsal failed with {len(decision.failures)} failure(s)"


def _render_report(
    inputs: SealedRehearsalInputs,
    decision: SealedRehearsalDecision,
) -> dict[str, Any]:
    preflight = decision.preflight
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_closeout_sealed_rehearsal_check",
        "generated_at": inputs.generated_at,
        "status": decision.status,
        **preflight,
        "distribution_zip": _distribution_zip_summary(inputs),
        "batch_manifest": _batch_manifest_summary(inputs),
        "external_report_reference_manifest": _external_manifest_summary(inputs),
        "failures": decision.failures,
        "failure_details": _failure_details(decision.failures),
        "summary": _sealed_rehearsal_summary(decision),
    }


def build_report(
    vault: Path,
    *,
    distribution_zip: str,
    batch_manifest: str = BATCH_MANIFEST_PATH,
    external_manifest: str = EXTERNAL_REPORT_REFERENCE_MANIFEST_PATH,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    _policy, resolved_policy_path = load_policy(vault)
    inputs = _sealed_rehearsal_inputs(
        vault,
        generated_at=runtime_context.isoformat_z(),
        distribution_zip=distribution_zip,
        batch_manifest=batch_manifest,
        external_manifest=external_manifest,
    )
    decision = _sealed_rehearsal_decision(inputs)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=inputs.generated_at,
            artifact_kind="release_closeout_sealed_rehearsal_check",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/release_closeout_sealed_rehearsal_check.py",
                "ops/scripts/release/release_status_v2.py",
                "ops/scripts/release/release_authority_vocabulary.py",
                "ops/schemas/release-closeout-sealed-rehearsal-check.schema.json",
            ],
            file_inputs={
                "batch_manifest": batch_manifest,
                "external_manifest": external_manifest,
            },
            text_inputs={"distribution_zip": distribution_zip},
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        **_render_report(inputs, decision),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    destination = resolve_repo_artifact_path(
        vault, out_path, default_relative_path=DEFAULT_OUT
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assert sealed closeout rehearsal evidence."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--distribution-zip", required=True)
    parser.add_argument("--batch-manifest", default=BATCH_MANIFEST_PATH)
    parser.add_argument(
        "--external-manifest", default=EXTERNAL_REPORT_REFERENCE_MANIFEST_PATH
    )
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--no-fail", action="store_true")
    parser.add_argument(
        "--allow-blocked-preflight",
        action="store_true",
        help=(
            "Exit successfully when distribution binding passes but release authority "
            "is the only blocker."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        distribution_zip=args.distribution_zip,
        batch_manifest=args.batch_manifest,
        external_manifest=args.external_manifest,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.no_fail:
        return 0
    if args.allow_blocked_preflight and report.get("expected_blocked_preflight"):
        return 0
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
