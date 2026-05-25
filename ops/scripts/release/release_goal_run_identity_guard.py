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
from ops.scripts.release.release_run_manifest import _resolve, git_commit
from ops.scripts.release.release_sealed_run_manifest import (
    _json_identity,
    _unique_failures,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "build/release/release-auto-promotion-goal-run-identity.json"
DEFAULT_GOAL_RUN_STATUS = "ops/reports/goal-run-status.json"
DEFAULT_GOAL_RUNTIME_CERTIFICATE = "ops/reports/goal-runtime-certificate.json"
DEFAULT_DEV_GOAL_RUN_ID = "auto-improve-trial"
SCHEMA_PATH = "ops/schemas/release-goal-run-identity.schema.json"
PRODUCER = "ops.scripts.release_goal_run_identity_guard"
SOURCE_COMMAND = "python -m ops.scripts.release_goal_run_identity_guard --vault ."
EXPLICIT_GOAL_RUN_ID_ORIGINS = {
    "command line",
    "environment",
    "environment override",
    "override",
}
INFERRED_SELECTION_MODE = "inferred_from_verified_evidence"
EXPLICIT_SELECTION_MODE = "explicit"
UNRESOLVED_SELECTION_MODE = "unresolved"


def _dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "allowed"}
    return False


def _load_report(vault: Path, path_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path_value))
    if diagnostics.get("status") != "ok":
        payload = {}
    return payload, diagnostics


def _blocker(
    *,
    blocker_id: str,
    source: str,
    field_path: str,
    observed: Any,
    expected: str,
    summary: str,
    recommended_next_step: str,
) -> dict[str, Any]:
    return {
        "id": blocker_id,
        "source": source,
        "field_path": field_path,
        "observed": str(observed),
        "expected": expected,
        "summary": summary,
        "recommended_next_step": recommended_next_step,
    }


def _require(
    blockers: list[dict[str, Any]],
    *,
    passed: bool,
    blocker_id: str,
    source: str,
    field_path: str,
    observed: Any,
    expected: str,
    summary: str,
    recommended_next_step: str,
) -> None:
    if passed:
        return
    blockers.append(
        _blocker(
            blocker_id=blocker_id,
            source=source,
            field_path=field_path,
            observed=observed,
            expected=expected,
            summary=summary,
            recommended_next_step=recommended_next_step,
        )
    )


def _identity_current(identity: dict[str, Any], fingerprint: str) -> bool:
    return str(identity.get("source_tree_fingerprint", "")).strip() == fingerprint


def _verified_inferred_run_id(
    *,
    status_identity: dict[str, Any],
    certificate_identity: dict[str, Any],
    status_run_id: str,
    certificate_run_id: str,
    status_report_status: str,
    status_run_status: str,
    status_promotion_status: str,
    status_can_promote_result: bool,
    certificate_report_status: str,
    certificate_verification_status: str,
    certificate_eligible: bool,
    fingerprint: str,
) -> str:
    status_verified = (
        status_identity["load_status"] == "ok"
        and status_identity["artifact_kind"] == "goal_run_status"
        and _identity_current(status_identity, fingerprint)
        and status_report_status == "pass"
        and status_run_status == "completed"
        and status_promotion_status == "allowed"
        and status_can_promote_result
    )
    certificate_verified = (
        certificate_identity["load_status"] == "ok"
        and certificate_identity["artifact_kind"] == "goal_runtime_certificate"
        and _identity_current(certificate_identity, fingerprint)
        and certificate_report_status == "pass"
        and certificate_verification_status in {"eligible", "already_verified"}
        and certificate_eligible
    )
    if status_verified and certificate_verified and status_run_id and status_run_id == certificate_run_id:
        return status_run_id
    return ""


def build_report(
    vault: Path,
    *,
    goal_run_id: str = "",
    goal_run_id_origin: str = "undefined",
    default_goal_run_id: str = DEFAULT_DEV_GOAL_RUN_ID,
    goal_run_status: str = DEFAULT_GOAL_RUN_STATUS,
    goal_runtime_certificate: str = DEFAULT_GOAL_RUNTIME_CERTIFICATE,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    requested_run_id = goal_run_id.strip()
    origin = goal_run_id_origin.strip()
    inputs = {
        "goal_run_status": _json_identity(vault, goal_run_status),
        "goal_runtime_certificate": _json_identity(vault, goal_runtime_certificate),
    }
    status_payload, _ = _load_report(vault, goal_run_status)
    certificate_payload, _ = _load_report(vault, goal_runtime_certificate)
    status_run = _dict(status_payload.get("run"))
    status_health = _dict(status_payload.get("health"))
    certificate = _dict(certificate_payload.get("certificate"))
    certificate_run = _dict(certificate_payload.get("run"))
    status_run_id = str(status_run.get("run_id", "")).strip()
    certificate_run_id = str(certificate_run.get("run_id", "")).strip()
    status_report_status = str(status_payload.get("status", "")).strip()
    status_run_status = str(status_run.get("status", "")).strip()
    status_promotion_status = str(status_health.get("promotion_status", "")).strip()
    status_can_promote_result = _bool_value(status_health.get("can_promote_result", False))
    certificate_report_status = str(certificate_payload.get("status", "")).strip()
    certificate_verification_status = str(certificate.get("verification_status", "")).strip()
    certificate_eligible = _bool_value(certificate.get("eligible", False))
    inferred_run_id = _verified_inferred_run_id(
        status_identity=inputs["goal_run_status"],
        certificate_identity=inputs["goal_runtime_certificate"],
        status_run_id=status_run_id,
        certificate_run_id=certificate_run_id,
        status_report_status=status_report_status,
        status_run_status=status_run_status,
        status_promotion_status=status_promotion_status,
        status_can_promote_result=status_can_promote_result,
        certificate_report_status=certificate_report_status,
        certificate_verification_status=certificate_verification_status,
        certificate_eligible=certificate_eligible,
        fingerprint=fingerprint,
    )
    explicit_run_id = requested_run_id if origin in EXPLICIT_GOAL_RUN_ID_ORIGINS else ""
    effective_run_id = explicit_run_id or inferred_run_id
    if explicit_run_id:
        selection_mode = EXPLICIT_SELECTION_MODE
    elif inferred_run_id:
        selection_mode = INFERRED_SELECTION_MODE
    else:
        selection_mode = UNRESOLVED_SELECTION_MODE
    observed = {
        "requested_run_id": requested_run_id,
        "effective_run_id": effective_run_id,
        "inferred_run_id": inferred_run_id,
        "selection_mode": selection_mode,
        "goal_run_id_origin": origin,
        "goal_run_status_run_id": status_run_id,
        "goal_run_status_run_status": status_run_status,
        "goal_run_status_report_status": status_report_status,
        "goal_run_status_promotion_status": status_promotion_status,
        "goal_run_status_can_promote_result": status_can_promote_result,
        "goal_runtime_certificate_run_id": certificate_run_id,
        "goal_runtime_certificate_run_status": str(
            certificate_run.get("run_status", "")
        ).strip(),
        "goal_runtime_certificate_report_status": certificate_report_status,
        "goal_runtime_certificate_verification_status": certificate_verification_status,
        "goal_runtime_certificate_eligible": certificate_eligible,
        "goal_runtime_certificate_already_verified": _bool_value(
            certificate.get("already_verified", False)
        ),
    }
    checks = {
        "goal_run_id_explicit": bool(explicit_run_id),
        "goal_run_id_inferred": bool(inferred_run_id) and not explicit_run_id,
        "goal_run_id_resolved": bool(effective_run_id),
        "goal_run_id_not_file_default": not (
            origin == "file"
            and requested_run_id == default_goal_run_id
            and effective_run_id == default_goal_run_id
        ),
        "inferred_goal_run_id_verified": bool(inferred_run_id),
        "explicit_goal_run_id_matches_inferred": not (
            explicit_run_id and inferred_run_id and explicit_run_id != inferred_run_id
        ),
        "goal_run_status_load_ok": inputs["goal_run_status"]["load_status"] == "ok",
        "goal_run_status_artifact_kind_ok": (
            inputs["goal_run_status"]["artifact_kind"] == "goal_run_status"
        ),
        "goal_run_status_current": _identity_current(inputs["goal_run_status"], fingerprint),
        "goal_run_status_run_id_match": observed["goal_run_status_run_id"] == effective_run_id,
        "goal_run_status_promotable": (
            observed["goal_run_status_report_status"] == "pass"
            and observed["goal_run_status_run_status"] == "completed"
            and observed["goal_run_status_promotion_status"] == "allowed"
            and bool(observed["goal_run_status_can_promote_result"])
        ),
        "goal_runtime_certificate_load_ok": (
            inputs["goal_runtime_certificate"]["load_status"] == "ok"
        ),
        "goal_runtime_certificate_artifact_kind_ok": (
            inputs["goal_runtime_certificate"]["artifact_kind"] == "goal_runtime_certificate"
        ),
        "goal_runtime_certificate_current": _identity_current(
            inputs["goal_runtime_certificate"], fingerprint
        ),
        "goal_runtime_certificate_run_id_match": (
            observed["goal_runtime_certificate_run_id"] == effective_run_id
        ),
        "goal_runtime_certificate_verified": (
            observed["goal_runtime_certificate_report_status"] == "pass"
            and observed["goal_runtime_certificate_verification_status"]
            in {"eligible", "already_verified"}
            and bool(observed["goal_runtime_certificate_eligible"])
        ),
    }
    blockers: list[dict[str, Any]] = []
    _require(
        blockers,
        passed=checks["goal_run_id_resolved"],
        blocker_id="goal_run_id_unresolved",
        source="make|goal_run_status|goal_runtime_certificate",
        field_path="GOAL_RUN_ID|$.run.run_id",
        observed=(
            f"requested={requested_run_id}; origin={origin};"
            f"status_run_id={status_run_id}; certificate_run_id={certificate_run_id}"
        ),
        expected="explicit GOAL_RUN_ID or matching verified promoted run evidence",
        summary="Release auto-promotion could not resolve the goal run id.",
        recommended_next_step="Rerun with GOAL_RUN_ID=<promoted-run-id> or publish matching verified run evidence.",
    )
    _require(
        blockers,
        passed=checks["goal_run_id_not_file_default"],
        blocker_id="goal_run_id_file_default",
        source="make",
        field_path="GOAL_RUN_ID",
        observed=(
            f"requested={requested_run_id}; effective={effective_run_id}; origin={origin}"
        ),
        expected=f"effective run id inferred away from Makefile default {default_goal_run_id}",
        summary="Release auto-promotion must not select the developer default goal run id.",
        recommended_next_step="Publish promoted evidence for a non-default run or pass GOAL_RUN_ID explicitly.",
    )
    _require(
        blockers,
        passed=checks["explicit_goal_run_id_matches_inferred"],
        blocker_id="explicit_goal_run_id_mismatch",
        source="make|goal_run_status|goal_runtime_certificate",
        field_path="GOAL_RUN_ID|$.run.run_id",
        observed=f"explicit={explicit_run_id}; inferred={inferred_run_id}",
        expected="explicit GOAL_RUN_ID matches verified promoted run evidence",
        summary="The explicit GOAL_RUN_ID does not match the verified promoted run evidence.",
        recommended_next_step="Use the verified promoted run id or republish the intended run evidence.",
    )
    _require(
        blockers,
        passed=checks["goal_run_status_load_ok"],
        blocker_id="goal_run_status_not_loadable",
        source="goal_run_status",
        field_path="$.load_status",
        observed=inputs["goal_run_status"]["load_status"],
        expected="ok",
        summary="Global goal-run status evidence is missing or invalid.",
        recommended_next_step="Publish the promoted run status before auto-promotion.",
    )
    _require(
        blockers,
        passed=checks["goal_run_status_artifact_kind_ok"],
        blocker_id="goal_run_status_artifact_kind_invalid",
        source="goal_run_status",
        field_path="$.artifact_kind",
        observed=inputs["goal_run_status"]["artifact_kind"],
        expected="goal_run_status",
        summary="Global goal-run status evidence has an unexpected artifact kind.",
        recommended_next_step="Regenerate goal-run status evidence for the promoted run.",
    )
    _require(
        blockers,
        passed=checks["goal_run_status_current"],
        blocker_id="goal_run_status_stale",
        source="goal_run_status",
        field_path="$.source_tree_fingerprint",
        observed=inputs["goal_run_status"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Global goal-run status evidence does not describe the current source tree.",
        recommended_next_step="Refresh goal-run status evidence for the current source tree.",
    )
    _require(
        blockers,
        passed=checks["goal_run_status_run_id_match"],
        blocker_id="goal_run_status_run_id_mismatch",
        source="goal_run_status",
        field_path="$.run.run_id",
        observed=observed["goal_run_status_run_id"],
        expected=effective_run_id,
        summary="GOAL_RUN_ID does not match the global goal-run status evidence.",
        recommended_next_step="Use the promoted run id or republish the intended run status.",
    )
    _require(
        blockers,
        passed=checks["goal_run_status_promotable"],
        blocker_id="goal_run_status_not_promotable",
        source="goal_run_status",
        field_path="$.status|$.run.status|$.health.promotion_status|$.health.can_promote_result",
        observed=(
            f"report_status={observed['goal_run_status_report_status']};"
            f"run_status={observed['goal_run_status_run_status']};"
            f"promotion_status={observed['goal_run_status_promotion_status']};"
            f"can_promote_result={observed['goal_run_status_can_promote_result']}"
        ),
        expected="report_status=pass; run_status=completed; promotion_status=allowed; can_promote_result=true",
        summary="The selected goal-run status is not promotable release evidence.",
        recommended_next_step="Complete and publish a promoted goal run before auto-promotion.",
    )
    _require(
        blockers,
        passed=checks["goal_runtime_certificate_load_ok"],
        blocker_id="goal_runtime_certificate_not_loadable",
        source="goal_runtime_certificate",
        field_path="$.load_status",
        observed=inputs["goal_runtime_certificate"]["load_status"],
        expected="ok",
        summary="Goal runtime certificate evidence is missing or invalid.",
        recommended_next_step="Run make goal-runtime-certificate for the promoted run.",
    )
    _require(
        blockers,
        passed=checks["goal_runtime_certificate_artifact_kind_ok"],
        blocker_id="goal_runtime_certificate_artifact_kind_invalid",
        source="goal_runtime_certificate",
        field_path="$.artifact_kind",
        observed=inputs["goal_runtime_certificate"]["artifact_kind"],
        expected="goal_runtime_certificate",
        summary="Goal runtime certificate evidence has an unexpected artifact kind.",
        recommended_next_step="Regenerate goal-runtime certificate evidence.",
    )
    _require(
        blockers,
        passed=checks["goal_runtime_certificate_current"],
        blocker_id="goal_runtime_certificate_stale",
        source="goal_runtime_certificate",
        field_path="$.source_tree_fingerprint",
        observed=inputs["goal_runtime_certificate"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Goal runtime certificate evidence does not describe the current source tree.",
        recommended_next_step="Refresh the goal-runtime certificate for the current source tree.",
    )
    _require(
        blockers,
        passed=checks["goal_runtime_certificate_run_id_match"],
        blocker_id="goal_runtime_certificate_run_id_mismatch",
        source="goal_runtime_certificate",
        field_path="$.run.run_id",
        observed=observed["goal_runtime_certificate_run_id"],
        expected=effective_run_id,
        summary="GOAL_RUN_ID does not match the goal runtime certificate evidence.",
        recommended_next_step="Use the promoted run id or regenerate the certificate for that run.",
    )
    _require(
        blockers,
        passed=checks["goal_runtime_certificate_verified"],
        blocker_id="goal_runtime_certificate_not_verified",
        source="goal_runtime_certificate",
        field_path="$.status|$.certificate.verification_status|$.certificate.eligible",
        observed=(
            f"report_status={observed['goal_runtime_certificate_report_status']};"
            f"verification_status={observed['goal_runtime_certificate_verification_status']};"
            f"eligible={observed['goal_runtime_certificate_eligible']}"
        ),
        expected="report_status=pass; verification_status in eligible,already_verified; eligible=true",
        summary="The selected goal run does not have verified certificate evidence.",
        recommended_next_step="Run make goal-runtime-certificate after the promoted run is complete.",
    )

    status = "pass" if not blockers else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_goal_run_identity",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": {key: str(value["sha256"]) for key, value in inputs.items()},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_diagnostic",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "requested_run_id": requested_run_id,
        "effective_run_id": effective_run_id,
        "inferred_run_id": inferred_run_id,
        "selection_mode": selection_mode,
        "goal_run_id_origin": origin,
        "default_goal_run_id": default_goal_run_id,
        "inputs": inputs,
        "observed": observed,
        "checks": checks,
        "blockers": blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release goal-run identity schema validation failed",
        )
    )


def read_effective_run_id_from_report(vault: Path, report_path: str) -> tuple[str, str]:
    payload, diagnostics = _load_report(vault, report_path)
    if diagnostics.get("status") != "ok":
        return "", f"could not load release goal-run identity report: {diagnostics.get('status')}"
    if payload.get("artifact_kind") != "release_goal_run_identity":
        return "", "release goal-run identity report has an unexpected artifact kind"
    if payload.get("status") != "pass":
        failures = ",".join(str(item) for item in payload.get("failures", []))
        return "", f"release goal-run identity report is not passing: {failures}"
    effective_run_id = str(payload.get("effective_run_id", "")).strip()
    if not effective_run_id:
        return "", "release goal-run identity report does not contain effective_run_id"
    return effective_run_id, ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release auto-promotion goal-run identity.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--goal-run-id", default="")
    parser.add_argument("--goal-run-id-origin", default="undefined")
    parser.add_argument("--default-goal-run-id", default=DEFAULT_DEV_GOAL_RUN_ID)
    parser.add_argument("--goal-run-status", default=DEFAULT_GOAL_RUN_STATUS)
    parser.add_argument("--goal-runtime-certificate", default=DEFAULT_GOAL_RUNTIME_CERTIFICATE)
    parser.add_argument("--print-effective-run-id-from-report")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.print_effective_run_id_from_report:
        effective_run_id, error = read_effective_run_id_from_report(
            vault, args.print_effective_run_id_from_report
        )
        if error:
            print(error, file=sys.stderr)
            return 1
        print(effective_run_id)
        return 0
    report = build_report(
        vault,
        goal_run_id=args.goal_run_id,
        goal_run_id_origin=args.goal_run_id_origin,
        default_goal_run_id=args.default_goal_run_id,
        goal_run_status=args.goal_run_status,
        goal_runtime_certificate=args.goal_runtime_certificate,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.check:
        print(f"release_goal_run_identity_status={report['status']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
