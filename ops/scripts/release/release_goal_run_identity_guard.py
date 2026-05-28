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
from ops.scripts.release.auto_promotion_manifest_sections import (
    RequirementSpec,
    append_requirement_blockers,
    input_fingerprints,
)
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
BINDING_BOUND = "bound"
BINDING_UNRESOLVED = "unresolved"
BINDING_INVALID = "invalid"
VERIFICATION_VERIFIED = "verified"
VERIFICATION_PENDING = "pending"
VERIFICATION_BLOCKED = "blocked"


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
    observed: dict[str, Any],
    fingerprint: str,
) -> str:
    status_verified = (
        status_identity["load_status"] == "ok"
        and status_identity["artifact_kind"] == "goal_run_status"
        and _identity_current(status_identity, fingerprint)
        and _goal_run_status_selectable(observed)
    )
    certificate_verified = (
        certificate_identity["load_status"] == "ok"
        and certificate_identity["artifact_kind"] == "goal_runtime_certificate"
        and _identity_current(certificate_identity, fingerprint)
        and observed["goal_runtime_certificate_report_status"] == "pass"
        and observed["goal_runtime_certificate_verification_status"]
        in {"eligible", "already_verified"}
        and bool(observed["goal_runtime_certificate_eligible"])
    )
    status_run_id = str(observed["goal_run_status_run_id"])
    certificate_run_id = str(observed["goal_runtime_certificate_run_id"])
    if status_verified and certificate_verified and status_run_id and status_run_id == certificate_run_id:
        return status_run_id
    return ""


def _goal_run_status_selectable(observed: dict[str, Any]) -> bool:
    return (
        observed["goal_run_status_report_status"] in {"pass", "attention"}
        and observed["goal_run_status_run_status"] == "completed"
    )


def _observed_evidence(
    status_payload: dict[str, Any],
    certificate_payload: dict[str, Any],
) -> dict[str, Any]:
    status_run = _dict(status_payload.get("run"))
    status_health = _dict(status_payload.get("health"))
    certificate = _dict(certificate_payload.get("certificate"))
    certificate_run = _dict(certificate_payload.get("run"))
    return {
        "goal_run_status_run_id": str(status_run.get("run_id", "")).strip(),
        "goal_run_status_run_status": str(status_run.get("status", "")).strip(),
        "goal_run_status_report_status": str(status_payload.get("status", "")).strip(),
        "goal_run_status_promotion_status": str(
            status_health.get("promotion_status", "")
        ).strip(),
        "goal_run_status_can_promote_result": _bool_value(
            status_health.get("can_promote_result", False)
        ),
        "goal_runtime_certificate_run_id": str(certificate_run.get("run_id", "")).strip(),
        "goal_runtime_certificate_run_status": str(
            certificate_run.get("run_status", "")
        ).strip(),
        "goal_runtime_certificate_report_status": str(
            certificate_payload.get("status", "")
        ).strip(),
        "goal_runtime_certificate_verification_status": str(
            certificate.get("verification_status", "")
        ).strip(),
        "goal_runtime_certificate_eligible": _bool_value(certificate.get("eligible", False)),
        "goal_runtime_certificate_already_verified": _bool_value(
            certificate.get("already_verified", False)
        ),
    }


def _goal_run_selection(
    inputs: dict[str, dict[str, Any]],
    observed: dict[str, Any],
    *,
    requested_run_id: str,
    origin: str,
    fingerprint: str,
) -> dict[str, str]:
    inferred_run_id = _verified_inferred_run_id(
        status_identity=inputs["goal_run_status"],
        certificate_identity=inputs["goal_runtime_certificate"],
        observed=observed,
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
    return {
        "requested_run_id": requested_run_id,
        "effective_run_id": effective_run_id,
        "inferred_run_id": inferred_run_id,
        "selection_mode": selection_mode,
        "goal_run_id_origin": origin,
    }


def _goal_observed(
    selection: dict[str, str],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {**selection, **evidence}


def _goal_checks(
    inputs: dict[str, dict[str, Any]],
    observed: dict[str, Any],
    *,
    default_goal_run_id: str,
    fingerprint: str,
) -> dict[str, bool]:
    requested_run_id = str(observed["requested_run_id"])
    effective_run_id = str(observed["effective_run_id"])
    inferred_run_id = str(observed["inferred_run_id"])
    origin = str(observed["goal_run_id_origin"])
    explicit_run_id = requested_run_id if origin in EXPLICIT_GOAL_RUN_ID_ORIGINS else ""
    current_status_run_id = (
        observed["goal_run_status_run_id"]
        if inputs["goal_run_status"]["load_status"] == "ok"
        and inputs["goal_run_status"]["artifact_kind"] == "goal_run_status"
        and _identity_current(inputs["goal_run_status"], fingerprint)
        else ""
    )
    current_certificate_run_id = (
        observed["goal_runtime_certificate_run_id"]
        if inputs["goal_runtime_certificate"]["load_status"] == "ok"
        and inputs["goal_runtime_certificate"]["artifact_kind"] == "goal_runtime_certificate"
        and _identity_current(inputs["goal_runtime_certificate"], fingerprint)
        else ""
    )
    return {
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
        "explicit_goal_run_id_matches_current_status": not (
            explicit_run_id and current_status_run_id and explicit_run_id != current_status_run_id
        ),
        "explicit_goal_run_id_matches_current_certificate": not (
            explicit_run_id
            and current_certificate_run_id
            and explicit_run_id != current_certificate_run_id
        ),
        "goal_run_status_load_ok": inputs["goal_run_status"]["load_status"] == "ok",
        "goal_run_status_artifact_kind_ok": (
            inputs["goal_run_status"]["artifact_kind"] == "goal_run_status"
        ),
        "goal_run_status_current": _identity_current(inputs["goal_run_status"], fingerprint),
        "goal_run_status_run_id_match": observed["goal_run_status_run_id"] == effective_run_id,
        "goal_run_status_promotable": _goal_run_status_selectable(observed),
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


def _goal_binding_requirements(
    checks: dict[str, bool],
    observed: dict[str, Any],
    *,
    default_goal_run_id: str,
) -> list[RequirementSpec]:
    requested_run_id = str(observed["requested_run_id"])
    origin = str(observed["goal_run_id_origin"])
    effective_run_id = str(observed["effective_run_id"])
    inferred_run_id = str(observed["inferred_run_id"])
    explicit_run_id = requested_run_id if origin in EXPLICIT_GOAL_RUN_ID_ORIGINS else ""
    return [
        RequirementSpec(
            checks["goal_run_id_not_file_default"],
            "goal_run_id_file_default",
            "make",
            "GOAL_RUN_ID",
            f"requested={requested_run_id}; effective={effective_run_id}; origin={origin}",
            f"effective run id inferred away from Makefile default {default_goal_run_id}",
            "Release auto-promotion must not select the developer default goal run id.",
            "Publish promoted evidence for a non-default run or pass GOAL_RUN_ID explicitly.",
        ),
        RequirementSpec(
            checks["explicit_goal_run_id_matches_inferred"],
            "explicit_goal_run_id_mismatch",
            "make|goal_run_status|goal_runtime_certificate",
            "GOAL_RUN_ID|$.run.run_id",
            f"explicit={explicit_run_id}; inferred={inferred_run_id}",
            "explicit GOAL_RUN_ID matches verified promoted run evidence",
            "The explicit GOAL_RUN_ID does not match the verified promoted run evidence.",
            "Use the verified promoted run id or republish the intended run evidence.",
        ),
        RequirementSpec(
            checks["explicit_goal_run_id_matches_current_status"],
            "explicit_goal_run_id_current_status_mismatch",
            "make|goal_run_status",
            "GOAL_RUN_ID|$.run.run_id",
            f"explicit={explicit_run_id}; status_run_id={observed['goal_run_status_run_id']}",
            "explicit GOAL_RUN_ID matches current goal-run status evidence when present",
            "The explicit GOAL_RUN_ID contradicts current goal-run status evidence.",
            "Use the current goal-run status run id or refresh status evidence for the intended run.",
        ),
        RequirementSpec(
            checks["explicit_goal_run_id_matches_current_certificate"],
            "explicit_goal_run_id_current_certificate_mismatch",
            "make|goal_runtime_certificate",
            "GOAL_RUN_ID|$.run.run_id",
            (
                f"explicit={explicit_run_id};"
                f"certificate_run_id={observed['goal_runtime_certificate_run_id']}"
            ),
            "explicit GOAL_RUN_ID matches current certificate evidence when present",
            "The explicit GOAL_RUN_ID contradicts current goal-runtime certificate evidence.",
            "Use the current certificate run id or regenerate the certificate for the intended run.",
        ),
    ]


def _goal_run_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    observed: dict[str, Any],
    *,
    fingerprint: str,
) -> list[RequirementSpec]:
    requested_run_id = str(observed["requested_run_id"])
    origin = str(observed["goal_run_id_origin"])
    effective_run_id = str(observed["effective_run_id"])
    status_run_id = str(observed["goal_run_status_run_id"])
    certificate_run_id = str(observed["goal_runtime_certificate_run_id"])
    return [
        RequirementSpec(
            checks["goal_run_id_resolved"],
            "goal_run_id_unresolved",
            "make|goal_run_status|goal_runtime_certificate",
            "GOAL_RUN_ID|$.run.run_id",
            (
                f"requested={requested_run_id}; origin={origin};"
                f"status_run_id={status_run_id}; certificate_run_id={certificate_run_id}"
            ),
            "explicit GOAL_RUN_ID or matching verified promoted run evidence",
            "Release auto-promotion could not resolve the goal run id.",
            "Rerun with GOAL_RUN_ID=<goal-run-id> or publish matching verified run evidence.",
        ),
        *_goal_run_status_requirements(checks, inputs, observed, effective_run_id, fingerprint),
        *_goal_runtime_certificate_requirements(
            checks,
            inputs,
            observed,
            effective_run_id,
            fingerprint,
        ),
    ]


def _goal_run_status_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    observed: dict[str, Any],
    effective_run_id: str,
    fingerprint: str,
) -> list[RequirementSpec]:
    status_input = inputs["goal_run_status"]
    return [
        RequirementSpec(
            checks["goal_run_status_load_ok"],
            "goal_run_status_not_loadable",
            "goal_run_status",
            "$.load_status",
            status_input["load_status"],
            "ok",
            "Global goal-run status evidence is missing or invalid.",
            "Publish the promoted run status before auto-promotion.",
        ),
        RequirementSpec(
            checks["goal_run_status_artifact_kind_ok"],
            "goal_run_status_artifact_kind_invalid",
            "goal_run_status",
            "$.artifact_kind",
            status_input["artifact_kind"],
            "goal_run_status",
            "Global goal-run status evidence has an unexpected artifact kind.",
            "Regenerate goal-run status evidence for the promoted run.",
        ),
        RequirementSpec(
            checks["goal_run_status_current"],
            "goal_run_status_stale",
            "goal_run_status",
            "$.source_tree_fingerprint",
            status_input["source_tree_fingerprint"],
            fingerprint,
            "Global goal-run status evidence does not describe the current source tree.",
            "Refresh goal-run status evidence for the current source tree.",
        ),
        RequirementSpec(
            checks["goal_run_status_run_id_match"],
            "goal_run_status_run_id_mismatch",
            "goal_run_status",
            "$.run.run_id",
            observed["goal_run_status_run_id"],
            effective_run_id,
            "GOAL_RUN_ID does not match the global goal-run status evidence.",
            "Use the promoted run id or republish the intended run status.",
        ),
        RequirementSpec(
            checks["goal_run_status_promotable"],
            "goal_run_status_not_promotable",
            "goal_run_status",
            "$.status|$.run.status|$.health.promotion_status|$.health.can_promote_result",
            (
                f"report_status={observed['goal_run_status_report_status']};"
                f"run_status={observed['goal_run_status_run_status']};"
                f"promotion_status={observed['goal_run_status_promotion_status']};"
                f"can_promote_result={observed['goal_run_status_can_promote_result']}"
            ),
            "report_status in pass,attention; run_status=completed",
            "The selected goal-run status is not completed release auto-promotion evidence.",
            "Complete and publish the goal run before auto-promotion.",
        ),
    ]


def _goal_runtime_certificate_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    observed: dict[str, Any],
    effective_run_id: str,
    fingerprint: str,
) -> list[RequirementSpec]:
    certificate_input = inputs["goal_runtime_certificate"]
    return [
        RequirementSpec(
            checks["goal_runtime_certificate_load_ok"],
            "goal_runtime_certificate_not_loadable",
            "goal_runtime_certificate",
            "$.load_status",
            certificate_input["load_status"],
            "ok",
            "Goal runtime certificate evidence is missing or invalid.",
            "Run make goal-runtime-certificate for the promoted run.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_artifact_kind_ok"],
            "goal_runtime_certificate_artifact_kind_invalid",
            "goal_runtime_certificate",
            "$.artifact_kind",
            certificate_input["artifact_kind"],
            "goal_runtime_certificate",
            "Goal runtime certificate evidence has an unexpected artifact kind.",
            "Regenerate goal-runtime certificate evidence.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_current"],
            "goal_runtime_certificate_stale",
            "goal_runtime_certificate",
            "$.source_tree_fingerprint",
            certificate_input["source_tree_fingerprint"],
            fingerprint,
            "Goal runtime certificate evidence does not describe the current source tree.",
            "Refresh the goal-runtime certificate for the current source tree.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_run_id_match"],
            "goal_runtime_certificate_run_id_mismatch",
            "goal_runtime_certificate",
            "$.run.run_id",
            observed["goal_runtime_certificate_run_id"],
            effective_run_id,
            "GOAL_RUN_ID does not match the goal runtime certificate evidence.",
            "Use the promoted run id or regenerate the certificate for that run.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_verified"],
            "goal_runtime_certificate_not_verified",
            "goal_runtime_certificate",
            "$.status|$.certificate.verification_status|$.certificate.eligible",
            (
                f"report_status={observed['goal_runtime_certificate_report_status']};"
                f"verification_status={observed['goal_runtime_certificate_verification_status']};"
                f"eligible={observed['goal_runtime_certificate_eligible']}"
            ),
            "report_status=pass; verification_status in eligible,already_verified; eligible=true",
            "The selected goal run does not have verified certificate evidence.",
            "Run make goal-runtime-certificate after the promoted run is complete.",
        ),
    ]


def _binding_status(observed: dict[str, Any], blockers: list[dict[str, Any]]) -> str:
    if blockers:
        return BINDING_INVALID
    if str(observed["effective_run_id"]).strip():
        return BINDING_BOUND
    return BINDING_UNRESOLVED


def _verification_status(
    verification_blockers: list[dict[str, Any]],
    observed: dict[str, Any],
) -> str:
    if not verification_blockers:
        return VERIFICATION_VERIFIED
    if not str(observed["effective_run_id"]).strip():
        return VERIFICATION_PENDING
    return VERIFICATION_BLOCKED


def _goal_report_payload(
    metadata: dict[str, Any],
    observed: dict[str, Any],
    checks: dict[str, bool],
    blockers: list[dict[str, Any]],
    verification_blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    status = "pass" if not blockers else "fail"
    verification_failures = _unique_failures(
        [str(blocker["id"]) for blocker in verification_blockers]
    )
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_goal_run_identity",
        "generated_at": metadata["generated_at"],
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": metadata["commit"],
        "source_tree_fingerprint": metadata["fingerprint"],
        "input_fingerprints": input_fingerprints(metadata["inputs"]),
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_diagnostic",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": metadata["generated_at"]},
        "status": status,
        "binding_status": _binding_status(observed, blockers),
        "verification_status": _verification_status(verification_blockers, observed),
        "requested_run_id": observed["requested_run_id"],
        "effective_run_id": observed["effective_run_id"],
        "inferred_run_id": observed["inferred_run_id"],
        "selection_mode": observed["selection_mode"],
        "goal_run_id_origin": observed["goal_run_id_origin"],
        "default_goal_run_id": metadata["default_goal_run_id"],
        "inputs": metadata["inputs"],
        "observed": observed,
        "checks": checks,
        "blockers": blockers,
        "verification_blockers": verification_blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
        "verification_failures": verification_failures,
    }


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
    evidence = _observed_evidence(status_payload, certificate_payload)
    selection = _goal_run_selection(
        inputs,
        evidence,
        requested_run_id=requested_run_id,
        origin=origin,
        fingerprint=fingerprint,
    )
    observed = _goal_observed(selection, evidence)
    checks = _goal_checks(
        inputs,
        observed,
        default_goal_run_id=default_goal_run_id,
        fingerprint=fingerprint,
    )
    binding_requirements = _goal_binding_requirements(
        checks,
        observed,
        default_goal_run_id=default_goal_run_id,
    )
    verification_requirements = _goal_run_requirements(
        checks,
        inputs,
        observed,
        fingerprint=fingerprint,
    )
    blockers: list[dict[str, Any]] = []
    append_requirement_blockers(blockers, binding_requirements)
    verification_blockers: list[dict[str, Any]] = []
    append_requirement_blockers(verification_blockers, verification_requirements)
    metadata = {
        "generated_at": generated_at,
        "commit": commit,
        "fingerprint": fingerprint,
        "default_goal_run_id": default_goal_run_id,
        "inputs": inputs,
    }
    return _goal_report_payload(metadata, observed, checks, blockers, verification_blockers)


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release auto-promotion goal-run identity.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--goal-run-id", default="")
    parser.add_argument("--goal-run-id-origin", default="undefined")
    parser.add_argument("--default-goal-run-id", default=DEFAULT_DEV_GOAL_RUN_ID)
    parser.add_argument("--goal-run-status", default=DEFAULT_GOAL_RUN_STATUS)
    parser.add_argument("--goal-runtime-certificate", default=DEFAULT_GOAL_RUNTIME_CERTIFICATE)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
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
        print(f"release_goal_run_verification_status={report['verification_status']}")
    if report["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
