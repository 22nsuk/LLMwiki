#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from ops.scripts.core.generated_artifact_semantic_digest import semantic_digest_maps
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.release.finality_current_diagnostics import (
    FRESHNESS_INDEX_COHORT_TARGETS as FRESHNESS_INDEX_COHORT_PATHS,
    SEALED_PREFLIGHT_PATH,
    dedupe_preserve_order as _dedupe_preserve_order,
    fixed_point_writer_targets_by_path as _fixed_point_writer_targets_by_path,
)
from ops.scripts.release.release_status_v2 import release_status_v2_view

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


def _normalized_digest_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(path): str(digest) for path, digest in value.items()}


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


def _recorded_digest_mismatches(
    *,
    recorded: dict[str, str],
    current: dict[str, str],
) -> list[dict[str, str]]:
    paths = sorted(set(recorded) | set(current))
    return [
        {
            "path": path,
            "recorded_digest": recorded.get(path, SHA256_MISSING),
            "current_digest": current.get(path, SHA256_MISSING),
        }
        for path in paths
        if recorded.get(path, SHA256_MISSING) != current.get(path, SHA256_MISSING)
    ]


def _batch_manifest_artifact_digest_mismatches(vault: Path) -> list[dict[str, str]]:
    payload, load_status = _load_optional(vault, BATCH_MANIFEST_PATH)
    if load_status != "ok":
        return []
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    mismatches: list[dict[str, str]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if not rel_path:
            continue
        expected = str(item.get("digest", SHA256_MISSING)).strip() or SHA256_MISSING
        actual = _sha256_file(vault / rel_path)
        if expected == actual:
            continue
        mismatches.append(
            {
                "path": rel_path,
                "role": str(item.get("role", "")).strip(),
                "batch_manifest_digest": expected,
                "current_digest": actual,
            }
        )
    return mismatches


def _sealed_preflight_summary(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_optional(vault, SEALED_PREFLIGHT_PATH)
    preflight = payload.get("preflight") if isinstance(payload, dict) else {}
    preflight = preflight if isinstance(preflight, dict) else {}
    currentness = payload.get("currentness") if isinstance(payload, dict) else {}
    currentness = currentness if isinstance(currentness, dict) else {}
    status = str(payload.get("status", "missing")).strip() if payload else "missing"
    preflight_status = str(preflight.get("preflight_status", "")).strip()
    currentness_status = str(currentness.get("status", "")).strip()
    return {
        "path": SEALED_PREFLIGHT_PATH,
        "digest": _sha256_file(vault / SEALED_PREFLIGHT_PATH),
        "load_status": load_status,
        "status": status,
        "preflight_status": preflight_status,
        "currentness_status": currentness_status,
        "current": (
            load_status == "ok"
            and status == "pass"
            and preflight_status in {"", "sealed_clean_pass"}
            and currentness_status in {"", "current"}
        ),
    }


def _finality_failure_classification(
    vault: Path,
    *,
    failures: list[str],
    raw_digest_mismatches: list[dict[str, str]],
    fixed_point_digest_mismatches: list[dict[str, str]],
) -> dict[str, Any]:
    if not failures:
        return {
            "status": "pass",
            "classes": [],
            "primary_class": "current",
            "recommended_lane": "none",
            "recommended_targets": [],
            "recommended_fixed_point_initial_targets": [],
            "batch_manifest_artifact_digest_mismatches": [],
            "freshness_index_cohort_digest_mismatches": [],
            "sealed_preflight_artifact_digest_mismatches": [],
            "sealed_preflight": _sealed_preflight_summary(vault),
            "fixed_point_tracked_writer_mismatches": [],
            "summary": "finality current-check is current",
        }
    batch_mismatches = _batch_manifest_artifact_digest_mismatches(vault)
    freshness_index_cohort = [
        item
        for item in batch_mismatches
        if item["path"] in FRESHNESS_INDEX_COHORT_PATHS
    ]
    sealed_preflight_artifact_mismatches = [
        item for item in batch_mismatches if item["path"] == SEALED_PREFLIGHT_PATH
    ]
    sealed_preflight = _sealed_preflight_summary(vault)
    fixed_point_writer_by_path = _fixed_point_writer_targets_by_path(vault)
    fixed_point_writer_mismatches = [
        {
            **item,
            "writer_target": fixed_point_writer_by_path.get(item["path"], ""),
        }
        for item in fixed_point_digest_mismatches
    ]

    classes: list[str] = []
    recommended_targets: list[str] = []
    recommended_initial_targets: list[str] = []
    if freshness_index_cohort:
        classes.append("batch_manifest_freshness_index_cohort_digest_mismatch")
        recommended_initial_targets.extend(
            FRESHNESS_INDEX_COHORT_PATHS[item["path"]]
            for item in freshness_index_cohort
        )
    if sealed_preflight_artifact_mismatches or (
        sealed_preflight["load_status"] == "ok" and not sealed_preflight["current"]
    ):
        classes.append("sealed_preflight_artifact_mismatch")
        recommended_targets.append("release-authority-sealed-preflight")
    if fixed_point_writer_mismatches:
        classes.append("fixed_point_tracked_writer_mismatch")
        recommended_initial_targets.extend(
            item["writer_target"]
            for item in fixed_point_writer_mismatches
            if item["writer_target"]
        )
    if raw_digest_mismatches and not fixed_point_writer_mismatches:
        classes.append("finality_attestation_digest_mismatch")
    if failures and not classes:
        classes.append("unclassified_finality_current_check_failure")

    if recommended_initial_targets:
        recommended_targets.append("release-closeout-fixed-point")
    if classes == ["finality_attestation_digest_mismatch"]:
        recommended_targets.append("release-closeout-finality-attestation")
    if classes:
        recommended_targets.append("release-closeout-finality-verify")

    recommended_targets = _dedupe_preserve_order(recommended_targets)
    recommended_initial_targets = _dedupe_preserve_order(recommended_initial_targets)
    recommended_lane = (
        "release-authority-sealed-preflight + release-closeout-fixed-point"
        if "sealed_preflight_artifact_mismatch" in classes
        and "fixed_point_tracked_writer_mismatch" in classes
        else "release-authority-sealed-preflight"
        if classes == ["sealed_preflight_artifact_mismatch"]
        else "release-closeout-fixed-point"
        if recommended_initial_targets or fixed_point_writer_mismatches
        else "release-closeout-finality-attestation"
        if classes == ["finality_attestation_digest_mismatch"]
        else "release-finality-resettle-current-or-refresh"
    )
    return {
        "status": "pass" if not failures else "fail",
        "classes": classes,
        "primary_class": classes[0] if classes else "current",
        "recommended_lane": recommended_lane,
        "recommended_targets": recommended_targets,
        "recommended_fixed_point_initial_targets": recommended_initial_targets,
        "batch_manifest_artifact_digest_mismatches": batch_mismatches,
        "freshness_index_cohort_digest_mismatches": freshness_index_cohort,
        "sealed_preflight_artifact_digest_mismatches": sealed_preflight_artifact_mismatches,
        "sealed_preflight": sealed_preflight,
        "fixed_point_tracked_writer_mismatches": fixed_point_writer_mismatches,
        "summary": (
            "finality current-check is current"
            if not failures
            else (
                f"primary_class={classes[0] if classes else 'unclassified'}; "
                f"recommended_lane={recommended_lane}; "
                f"recommended_targets={','.join(recommended_targets)}"
            )
        ),
    }


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
    tracked_semantic_digest_map, tracked_semantic_digest_modes = semantic_digest_maps(
        vault, tracked_paths
    )
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
            source_paths=[
                "ops/scripts/release/release_closeout_finality_attestation.py",
                "ops/scripts/core/generated_artifact_semantic_digest.py",
            ],
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
        "tracked_semantic_digest_map": tracked_semantic_digest_map,
        "tracked_semantic_digest_modes": tracked_semantic_digest_modes,
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


def _verify_attestation_diagnostics(
    vault: Path,
    attestation_path: str = DEFAULT_OUT,
) -> dict[str, Any]:
    resolved = resolve_schema_backed_report_output_path(
        vault,
        attestation_path,
        default_relative_path=DEFAULT_OUT,
    )
    payload, diagnostics = load_optional_json_object_with_diagnostics(resolved)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        load_failures = [f"attestation_load_status:{load_status}"]
        return {
            "status": "fail",
            "failures": load_failures,
            "failure_classification": _finality_failure_classification(
                vault,
                failures=load_failures,
                raw_digest_mismatches=[],
                fixed_point_digest_mismatches=[],
            ),
            "semantic_fallback_used": False,
            "raw_digest_mismatches": [],
            "raw_digest_mismatches_covered_by_semantic_digest": [],
            "fixed_point_digest_mismatches": [],
        }

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
    recorded_map = _normalized_digest_map(payload.get("tracked_digest_map"))
    current_semantic_digest_map, _current_semantic_modes = semantic_digest_maps(
        vault, tracked_paths
    )
    recorded_semantic_map = _normalized_digest_map(payload.get("tracked_semantic_digest_map"))
    semantic_map_matches = bool(recorded_semantic_map) and (
        current_semantic_digest_map == recorded_semantic_map
    )
    raw_digest_mismatches = _recorded_digest_mismatches(
        recorded=recorded_map,
        current=current_tracked_digest_map,
    )
    raw_mismatch_covered_by_semantic_digest = bool(raw_digest_mismatches) and semantic_map_matches
    uncovered_raw_digest_mismatches = (
        [] if raw_mismatch_covered_by_semantic_digest else raw_digest_mismatches
    )
    if raw_digest_mismatches and not semantic_map_matches:
        failures.append("tracked_digest_map_current_mismatch")
    raw_fixed_map = fixed_payload.get("final_digest_map")
    fixed_map: dict[str, Any] = raw_fixed_map if isinstance(raw_fixed_map, dict) else {}
    fixed_point_digest_mismatches = _digest_mismatches(fixed_map, current_tracked_digest_map)
    uncovered_fixed_point_digest_mismatches = (
        [] if semantic_map_matches else fixed_point_digest_mismatches
    )
    if fixed_point_digest_mismatches and not semantic_map_matches:
        failures.append("fixed_point_digest_map_current_mismatch")
    if _batch_manifest_artifact_digest_mismatches(vault):
        failures.append("batch_manifest_artifact_digest_current_mismatch")
    sealed_preflight = _sealed_preflight_summary(vault)
    if sealed_preflight["load_status"] == "ok" and not sealed_preflight["current"]:
        failures.append("sealed_preflight_not_current")
    if str(payload.get("finality_status", "")).strip() != "pass":
        failures.append("attestation_finality_status_not_pass")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "failure_classification": _finality_failure_classification(
            vault,
            failures=failures,
            raw_digest_mismatches=uncovered_raw_digest_mismatches,
            fixed_point_digest_mismatches=uncovered_fixed_point_digest_mismatches,
        ),
        "semantic_fallback_used": raw_mismatch_covered_by_semantic_digest,
        "raw_digest_mismatches": raw_digest_mismatches,
        "raw_digest_mismatches_covered_by_semantic_digest": raw_digest_mismatches
        if raw_mismatch_covered_by_semantic_digest
        else [],
        "fixed_point_digest_mismatches": fixed_point_digest_mismatches,
    }


def verify_attestation(vault: Path, attestation_path: str = DEFAULT_OUT) -> tuple[bool, list[str]]:
    report = _verify_attestation_diagnostics(vault, attestation_path)
    failures = [str(item) for item in report.get("failures", [])]
    return report["status"] == "pass", failures


def verify_attestation_report(vault: Path, attestation_path: str = DEFAULT_OUT) -> dict[str, Any]:
    return _verify_attestation_diagnostics(vault, attestation_path)


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
