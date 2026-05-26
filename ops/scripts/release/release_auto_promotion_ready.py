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
from ops.scripts.release.auto_promotion_learning_runtime import (
    ALLOWED_LEARNING_REVALIDATION_STATUSES,
    unaccepted_learning_claim_blockers,
)
from ops.scripts.release.auto_promotion_manifest_sections import (
    RequirementSpec,
    append_requirement_blockers,
    input_fingerprints,
)
from ops.scripts.release.release_run_manifest import (
    DEFAULT_OUT as DEFAULT_RUN_MANIFEST,
)
from ops.scripts.release.release_run_manifest import (
    _resolve,
    git_commit,
)
from ops.scripts.release.release_sealed_run_manifest import (
    DEFAULT_OUT as DEFAULT_SEALED_RUN_MANIFEST,
)
from ops.scripts.release.release_sealed_run_manifest import (
    _json_identity,
    _unique_failures,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "build/release/release-auto-promotion-ready-manifest.json"
SCHEMA_PATH = "ops/schemas/release-auto-promotion-ready-manifest.schema.json"
PRODUCER = "ops.scripts.release_auto_promotion_ready"
SOURCE_COMMAND = "python -m ops.scripts.release_auto_promotion_ready --vault ."
DEFAULT_OPERATOR_SUMMARY = "build/release/operator-release-summary.json"
DEFAULT_AUTO_IMPROVE_READINESS = "ops/reports/auto-improve-readiness.json"
DEFAULT_AUTO_PROMOTION_PREFLIGHT = "build/release/release-auto-promotion-preflight.json"
DEFAULT_AUTO_PROMOTION_PRESEAL = "build/release/release-auto-promotion-preseal.json"
STRICT_ZERO_ACCEPTED_RISK_FIELDS = (
    "accepted_risk_count",
    "release_accepted_risk_count",
    "accepted_learning_risk_count",
    "clean_lane_blocking_accepted_risk_family_count",
)
STRICT_ZERO_GATE_ATTENTION_FIELDS = (
    "gate_attention_count",
)
STRICT_ZERO_LEARNING_CLAIM_FIELDS = (
    "learning_claim_blocking_family_count",
)


def _dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _list(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else []


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _load_report(vault: Path, path_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _resolve(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok":
        payload = {}
    return payload, diagnostics


def _operator_count_group(operator_summary: dict[str, Any], fields: tuple[str, ...]) -> dict[str, int]:
    accepted_risk = _dict(operator_summary.get("accepted_risk"))
    return {field: _int_value(accepted_risk.get(field, 0)) for field in fields}


def _release_gate_diagnostic_blockers(blockers: list[Any]) -> list[dict[str, Any]]:
    return [
        blocker
        for blocker in (_dict(item) for item in blockers)
        if str(blocker.get("scope", "")).strip() == "release_gate"
    ]


def _stage3_blocking_promotion_blockers(blockers: list[Any]) -> list[dict[str, Any]]:
    return [
        blocker
        for blocker in (_dict(item) for item in blockers)
        if str(blocker.get("scope", "")).strip() != "release_gate"
    ]


def _operator_diagnostics(operator_summary: dict[str, Any]) -> dict[str, Any]:
    test_evidence = _dict(operator_summary.get("test_evidence"))
    learning_readiness = _dict(operator_summary.get("learning_readiness"))
    return {
        "status": str(operator_summary.get("status", "")).strip(),
        "source_zip_policy_status": str(operator_summary.get("source_zip_policy_status", "")).strip(),
        "tmp_json_policy_status": str(operator_summary.get("tmp_json_policy_status", "")).strip(),
        "artifact_digest_policy_status": str(operator_summary.get("artifact_digest_policy_status", "")).strip(),
        "batch_verify_status": str(_dict(operator_summary.get("batch_verify")).get("status", "")).strip(),
        "full_suite_status": str(test_evidence.get("full_suite_status", "")).strip(),
        "learning_revalidation_status": str(learning_readiness.get("revalidation_status", "")).strip(),
        "accepted_risk": _operator_count_group(operator_summary, STRICT_ZERO_ACCEPTED_RISK_FIELDS),
        "gate_attention": _operator_count_group(operator_summary, STRICT_ZERO_GATE_ATTENTION_FIELDS),
        "learning_claim": _operator_count_group(operator_summary, STRICT_ZERO_LEARNING_CLAIM_FIELDS),
    }


def _auto_improve_diagnostics(
    auto_improve_readiness: dict[str, Any],
    *,
    current_fingerprint: str,
) -> dict[str, Any]:
    learning_claim_blockers = _list(auto_improve_readiness.get("learning_claim_blockers"))
    promotion_blockers = _list(auto_improve_readiness.get("promotion_blockers"))
    clean_release_blockers = _list(auto_improve_readiness.get("clean_release_blockers"))
    stage3_promotion_blockers = _stage3_blocking_promotion_blockers(promotion_blockers)
    release_gate_diagnostic_blockers = _release_gate_diagnostic_blockers(promotion_blockers)
    learning_claim_blockers_without_signoff = unaccepted_learning_claim_blockers(
        learning_claim_blockers,
        auto_improve_readiness.get("diagnostics"),
    )
    report_fingerprint = str(auto_improve_readiness.get("source_tree_fingerprint", "")).strip()
    can_execute_trial = bool(auto_improve_readiness.get("can_execute_trial", False))
    return {
        "source_tree_fingerprint": report_fingerprint,
        "currentness_status": "current" if report_fingerprint == current_fingerprint else "stale",
        "can_execute_trial": can_execute_trial,
        "can_promote_result": bool(auto_improve_readiness.get("can_promote_result", False)),
        "stage3_can_promote_result": can_execute_trial and not stage3_promotion_blockers,
        "learning_claim_blocker_count": len(learning_claim_blockers),
        "unaccepted_learning_claim_blocker_count": len(
            learning_claim_blockers_without_signoff
        ),
        "promotion_blocker_count": len(promotion_blockers),
        "stage3_blocking_promotion_blocker_count": len(stage3_promotion_blockers),
        "release_gate_diagnostic_promotion_blocker_count": len(release_gate_diagnostic_blockers),
        "clean_release_blocker_count": len(clean_release_blockers),
    }


def _preflight_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    goal_run_identity = _dict(payload.get("goal_run_identity"))
    return {
        "phase": str(payload.get("phase", "")).strip(),
        "status": str(payload.get("status", "")).strip(),
        "blocker_count": len(_list(payload.get("blockers"))),
        "goal_run_identity": {
            "status": str(goal_run_identity.get("status", "")).strip(),
            "requested_run_id": str(goal_run_identity.get("requested_run_id", "")).strip(),
            "effective_run_id": str(goal_run_identity.get("effective_run_id", "")).strip(),
            "inferred_run_id": str(goal_run_identity.get("inferred_run_id", "")).strip(),
            "selection_mode": str(goal_run_identity.get("selection_mode", "")).strip(),
            "goal_run_id_origin": str(goal_run_identity.get("goal_run_id_origin", "")).strip(),
            "failure_count": _int_value(goal_run_identity.get("failure_count", 0)),
        },
    }


def _phase_evidence_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    diagnostics: dict[str, Any],
    *,
    input_key: str,
    source: str,
    phase: str,
    fingerprint: str,
) -> list[RequirementSpec]:
    identity = inputs[input_key]
    goal_identity = _dict(diagnostics.get("goal_run_identity"))
    goal_run_id = str(goal_identity.get("effective_run_id", "")).strip()
    return [
        RequirementSpec(
            checks[f"{input_key}_load_ok"],
            f"{input_key}_not_loadable",
            source,
            "$.load_status",
            identity["load_status"],
            "ok",
            f"Auto-promotion {phase} evidence is missing or invalid.",
            f"Run make release-auto-promotion-{phase} before release-run-ready.",
        ),
        RequirementSpec(
            checks[f"{input_key}_artifact_kind_ok"],
            f"{input_key}_artifact_kind_invalid",
            source,
            "$.artifact_kind",
            identity["artifact_kind"],
            "release_auto_promotion_preflight",
            f"Auto-promotion {phase} evidence has an unexpected artifact kind.",
            f"Regenerate auto-promotion {phase} evidence.",
        ),
        RequirementSpec(
            checks[f"{input_key}_current"],
            f"{input_key}_stale",
            source,
            "$.source_tree_fingerprint",
            identity["source_tree_fingerprint"],
            fingerprint,
            f"Auto-promotion {phase} evidence does not describe the current source tree.",
            f"Run make release-auto-promotion-{phase} before release-run-ready.",
        ),
        RequirementSpec(
            checks[f"{input_key}_phase_ok"],
            f"{input_key}_phase_invalid",
            source,
            "$.phase",
            diagnostics["phase"],
            phase,
            f"Auto-promotion {phase} evidence was written for the wrong phase.",
            f"Regenerate it with make release-auto-promotion-{phase}.",
        ),
        RequirementSpec(
            checks[f"{input_key}_pass"],
            f"{input_key}_not_pass",
            source,
            "$.status",
            diagnostics["status"],
            "pass",
            f"Auto-promotion {phase} has blockers that should be cleared.",
            f"Resolve {phase} blockers before spending release-ready cycles.",
        ),
        RequirementSpec(
            checks[f"{input_key}_goal_run_identity_present"],
            f"{input_key}_goal_run_identity_missing",
            source,
            "$.goal_run_identity.effective_run_id",
            goal_run_id,
            "non-empty run id",
            f"Auto-promotion {phase} does not bind a selected goal run id.",
            f"Regenerate it with make release-auto-promotion-{phase} and explicit GOAL_RUN_ID.",
        ),
        RequirementSpec(
            checks[f"{input_key}_goal_run_identity_pass"],
            f"{input_key}_goal_run_identity_not_pass",
            source,
            "$.goal_run_identity.status|$.goal_run_identity.failure_count",
            (
                f"status={goal_identity.get('status', '')};"
                f"failures={goal_identity.get('failure_count', '')}"
            ),
            "status=pass; failures=0",
            f"Auto-promotion {phase} goal-run identity evidence is not passing.",
            "Regenerate it after make release-auto-promotion-goal-run-id-guard passes.",
        ),
    ]


def _manifest_evidence_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    payloads: dict[str, dict[str, Any]],
    *,
    fingerprint: str,
) -> list[RequirementSpec]:
    specs: list[RequirementSpec] = []
    manifest_specs = (
        ("run_manifest", "release_run_manifest", "release_run_manifest", "Run make release-run-ready."),
        (
            "sealed_run_manifest",
            "release_sealed_run_manifest",
            "release_sealed_run_manifest",
            "Run make release-sealed-run-ready.",
        ),
        (
            "operator_summary",
            "operator_release_summary",
            "operator_release_summary",
            "Regenerate the operator release summary.",
        ),
    )
    for input_key, source, artifact_kind, next_step in manifest_specs:
        identity = inputs[input_key]
        specs.extend(
            [
                RequirementSpec(
                    checks[f"{input_key}_load_ok"],
                    f"{input_key}_not_loadable",
                    source,
                    "$.load_status",
                    identity["load_status"],
                    "ok",
                    f"{source.replace('_', ' ').capitalize()} is missing or not valid JSON.",
                    next_step,
                ),
                RequirementSpec(
                    checks[f"{input_key}_artifact_kind_ok"],
                    f"{input_key}_artifact_kind_invalid",
                    source,
                    "$.artifact_kind",
                    identity["artifact_kind"],
                    artifact_kind,
                    f"{source.replace('_', ' ').capitalize()} has an unexpected artifact kind.",
                    next_step,
                ),
                RequirementSpec(
                    checks[f"{input_key}_current"],
                    f"{input_key}_stale",
                    source,
                    "$.source_tree_fingerprint",
                    identity["source_tree_fingerprint"],
                    fingerprint,
                    f"{source.replace('_', ' ').capitalize()} does not describe the current source tree.",
                    next_step,
                ),
                RequirementSpec(
                    checks[f"{input_key}_pass"],
                    f"{input_key}_not_pass"
                    if input_key != "operator_summary"
                    else "operator_attention_open",
                    source,
                    "$.status",
                    payloads[input_key].get("status", ""),
                    "pass",
                    f"{source.replace('_', ' ').capitalize()} is not passing.",
                    next_step,
                ),
            ]
        )
    return specs


def _operator_policy_requirements(
    checks: dict[str, bool],
    operator: dict[str, Any],
    learning_revalidation_status: str,
) -> list[RequirementSpec]:
    operator_requirements = [
        RequirementSpec(
            checks["source_zip_policy_match"],
            "source_zip_policy_not_match",
            "operator_release_summary",
            "$.source_zip_policy_status",
            operator["source_zip_policy_status"],
            "match",
            "Source ZIP policy is not a digest match.",
            "Refresh release evidence, then regenerate the operator release summary.",
        ),
        RequirementSpec(
            checks["tmp_json_clean"],
            "tmp_json_not_clean",
            "operator_release_summary",
            "$.tmp_json_policy_status",
            operator["tmp_json_policy_status"],
            "clean",
            "Temporary JSON policy is not clean.",
            "Refresh release evidence, then regenerate the operator release summary.",
        ),
        RequirementSpec(
            checks["artifact_digest_policy_match"],
            "artifact_digest_policy_not_match",
            "operator_release_summary",
            "$.artifact_digest_policy_status",
            operator["artifact_digest_policy_status"],
            "match",
            "Artifact digest policy is not a match.",
            "Refresh release evidence, then regenerate the operator release summary.",
        ),
        RequirementSpec(
            checks["batch_verify_pass"],
            "batch_verify_not_pass",
            "operator_release_summary",
            "$.batch_verify_status",
            operator["batch_verify_status"],
            "pass",
            "Operator batch verification is not passing.",
            "Refresh release evidence, then regenerate the operator release summary.",
        ),
        RequirementSpec(
            checks["full_suite_pass"],
            "full_suite_not_pass",
            "operator_release_summary",
            "$.full_suite_status",
            operator["full_suite_status"],
            "pass",
            "Full test-suite evidence is not passing.",
            "Refresh release evidence, then regenerate the operator release summary.",
        ),
        RequirementSpec(
            checks["learning_revalidation_current"],
            "learning_revalidation_not_current",
            "operator_release_summary",
            "$.learning_readiness.revalidation_status",
            learning_revalidation_status,
            "one of current, fresh, metrics_close_candidate, not_due, not_required, pass",
            "Learning revalidation is not current enough for unattended promotion.",
            "Run learning-readiness-signoff-revalidation and refresh operator summary.",
        ),
    ]
    return operator_requirements


def _operator_zero_count_requirements(operator: dict[str, Any]) -> list[RequirementSpec]:
    requirements: list[RequirementSpec] = []
    for group, next_step in (
        ("accepted_risk", "Resolve or explicitly keep this release out of auto-promotion."),
        ("gate_attention", "Resolve gate attention before unattended promotion."),
        ("learning_claim", "Resolve or renew learning claim evidence before unattended promotion."),
    ):
        for field, count in operator[group].items():
            requirements.append(
                RequirementSpec(
                    count == 0,
                    f"{field}_not_zero",
                    "operator_release_summary",
                    f"$.accepted_risk.{field}",
                    count,
                    "0",
                    f"{field} must be zero for unattended promotion.",
                    next_step,
                )
            )
    return requirements


def _auto_improve_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    auto_improve: dict[str, Any],
    *,
    fingerprint: str,
) -> list[RequirementSpec]:
    auto_input = inputs["auto_improve_readiness"]
    return [
        RequirementSpec(
            checks["auto_improve_readiness_load_ok"],
            "auto_improve_readiness_not_loadable",
            "auto_improve_readiness_report",
            "$.load_status",
            auto_input["load_status"],
            "ok",
            "Auto-improve readiness diagnostics are missing or not valid JSON.",
            "Run make auto-improve-readiness-report-body.",
        ),
        RequirementSpec(
            checks["auto_improve_readiness_artifact_kind_ok"],
            "auto_improve_readiness_artifact_kind_invalid",
            "auto_improve_readiness_report",
            "$.artifact_kind",
            auto_input["artifact_kind"],
            "auto_improve_readiness_report",
            "Auto-improve readiness diagnostics have an unexpected artifact kind.",
            "Run make auto-improve-readiness-report-body.",
        ),
        RequirementSpec(
            checks["auto_improve_current"],
            "auto_improve_readiness_stale",
            "auto_improve_readiness_report",
            "$.source_tree_fingerprint",
            auto_improve["source_tree_fingerprint"],
            fingerprint,
            "Auto-improve readiness does not describe the current source tree.",
            "Run make auto-improve-readiness-report-body.",
        ),
        RequirementSpec(
            checks["auto_improve_can_execute_trial"],
            "auto_improve_trial_not_executable",
            "auto_improve_readiness_report",
            "$.can_execute_trial",
            auto_improve["can_execute_trial"],
            "true",
            "Auto-improve lane cannot execute a trial.",
            "Refresh auto-improve readiness and resolve execution blockers.",
        ),
        RequirementSpec(
            checks["auto_improve_can_promote_result"],
            "auto_improve_result_not_promotable",
            "auto_improve_readiness_report",
            "$.promotion_blockers[?scope!='release_gate']|$.can_execute_trial",
            (
                f"can_execute_trial={auto_improve['can_execute_trial']};"
                f"stage3_blocking_promotion={auto_improve['stage3_blocking_promotion_blocker_count']};"
                f"raw_can_promote_result={auto_improve['can_promote_result']}"
            ),
            "true",
            "Auto-improve readiness has independent promotion blockers for Stage 3.",
            "Resolve non-release-gate auto-improve promotion blockers before unattended promotion.",
        ),
        RequirementSpec(
            checks["auto_improve_blockers_clear"],
            "auto_improve_blockers_open",
            "auto_improve_readiness_report",
            "$.learning_claim_blockers|$.promotion_blockers[?scope!='release_gate']|$.clean_release_blockers",
            (
                f"learning_claim={auto_improve['learning_claim_blocker_count']};"
                f"stage3_promotion={auto_improve['stage3_blocking_promotion_blocker_count']};"
                f"unaccepted_learning_claim={auto_improve['unaccepted_learning_claim_blocker_count']};"
                f"release_gate_diagnostic={auto_improve['release_gate_diagnostic_promotion_blocker_count']};"
                f"clean_release={auto_improve['clean_release_blocker_count']}"
            ),
            "all blocking blocker counts are 0",
            "Auto-improve readiness still has Stage 3 blocking diagnostics.",
            (
                "Resolve learning, non-release-gate promotion, or clean-release blockers listed in "
                "ops/reports/auto-improve-readiness.json."
            ),
        ),
    ]


def _ready_checks(
    inputs: dict[str, dict[str, Any]],
    *,
    run_payload: dict[str, Any],
    sealed_payload: dict[str, Any],
    operator: dict[str, Any],
    auto_improve: dict[str, Any],
    preflight: dict[str, Any],
    preseal: dict[str, Any],
    fingerprint: str,
) -> dict[str, bool]:
    preflight_goal_identity = _dict(preflight.get("goal_run_identity"))
    preseal_goal_identity = _dict(preseal.get("goal_run_identity"))
    preflight_goal_run_id = str(preflight_goal_identity.get("effective_run_id", "")).strip()
    preseal_goal_run_id = str(preseal_goal_identity.get("effective_run_id", "")).strip()
    return {
        "auto_promotion_preflight_load_ok": inputs["auto_promotion_preflight"]["load_status"] == "ok",
        "auto_promotion_preflight_artifact_kind_ok": (
            inputs["auto_promotion_preflight"]["artifact_kind"] == "release_auto_promotion_preflight"
        ),
        "auto_promotion_preflight_current": (
            inputs["auto_promotion_preflight"]["source_tree_fingerprint"] == fingerprint
        ),
        "auto_promotion_preflight_phase_ok": preflight["phase"] == "preflight",
        "auto_promotion_preflight_pass": preflight["status"] == "pass",
        "auto_promotion_preflight_goal_run_identity_present": bool(preflight_goal_run_id),
        "auto_promotion_preflight_goal_run_identity_pass": (
            preflight_goal_identity.get("status") == "pass"
            and _int_value(preflight_goal_identity.get("failure_count", 0)) == 0
        ),
        "auto_promotion_preseal_load_ok": inputs["auto_promotion_preseal"]["load_status"] == "ok",
        "auto_promotion_preseal_artifact_kind_ok": (
            inputs["auto_promotion_preseal"]["artifact_kind"] == "release_auto_promotion_preflight"
        ),
        "auto_promotion_preseal_current": (
            inputs["auto_promotion_preseal"]["source_tree_fingerprint"] == fingerprint
        ),
        "auto_promotion_preseal_phase_ok": preseal["phase"] == "preseal",
        "auto_promotion_preseal_pass": preseal["status"] == "pass",
        "auto_promotion_preseal_goal_run_identity_present": bool(preseal_goal_run_id),
        "auto_promotion_preseal_goal_run_identity_pass": (
            preseal_goal_identity.get("status") == "pass"
            and _int_value(preseal_goal_identity.get("failure_count", 0)) == 0
        ),
        "auto_promotion_goal_run_identity_match": (
            bool(preflight_goal_run_id)
            and bool(preseal_goal_run_id)
            and preflight_goal_run_id == preseal_goal_run_id
        ),
        "run_manifest_load_ok": inputs["run_manifest"]["load_status"] == "ok",
        "run_manifest_artifact_kind_ok": inputs["run_manifest"]["artifact_kind"] == "release_run_manifest",
        "run_manifest_current": inputs["run_manifest"]["source_tree_fingerprint"] == fingerprint,
        "run_manifest_pass": str(run_payload.get("status", "")).strip() == "pass",
        "sealed_run_manifest_load_ok": inputs["sealed_run_manifest"]["load_status"] == "ok",
        "sealed_run_manifest_artifact_kind_ok": (
            inputs["sealed_run_manifest"]["artifact_kind"] == "release_sealed_run_manifest"
        ),
        "sealed_run_manifest_current": inputs["sealed_run_manifest"]["source_tree_fingerprint"] == fingerprint,
        "sealed_run_manifest_pass": str(sealed_payload.get("status", "")).strip() == "pass",
        "operator_summary_load_ok": inputs["operator_summary"]["load_status"] == "ok",
        "operator_summary_artifact_kind_ok": inputs["operator_summary"]["artifact_kind"] == "operator_release_summary",
        "operator_summary_current": str(inputs["operator_summary"]["source_tree_fingerprint"]).strip()
        == fingerprint,
        "operator_summary_pass": operator["status"] == "pass",
        "source_zip_policy_match": operator["source_zip_policy_status"] == "match",
        "tmp_json_clean": operator["tmp_json_policy_status"] == "clean",
        "artifact_digest_policy_match": operator["artifact_digest_policy_status"] == "match",
        "batch_verify_pass": operator["batch_verify_status"] == "pass",
        "full_suite_pass": operator["full_suite_status"] == "pass",
        "learning_revalidation_current": str(operator["learning_revalidation_status"])
        in ALLOWED_LEARNING_REVALIDATION_STATUSES,
        "accepted_risk_clean": all(count == 0 for count in operator["accepted_risk"].values()),
        "gate_attention_clean": all(count == 0 for count in operator["gate_attention"].values()),
        "learning_claim_clean": all(count == 0 for count in operator["learning_claim"].values()),
        "auto_improve_readiness_load_ok": inputs["auto_improve_readiness"]["load_status"] == "ok",
        "auto_improve_readiness_artifact_kind_ok": (
            inputs["auto_improve_readiness"]["artifact_kind"] == "auto_improve_readiness_report"
        ),
        "auto_improve_current": auto_improve["currentness_status"] == "current",
        "auto_improve_can_execute_trial": bool(auto_improve["can_execute_trial"]),
        "auto_improve_can_promote_result": bool(auto_improve["stage3_can_promote_result"]),
        "auto_improve_blockers_clear": (
            int(auto_improve["unaccepted_learning_claim_blocker_count"]) == 0
            and int(auto_improve["stage3_blocking_promotion_blocker_count"]) == 0
            and int(auto_improve["clean_release_blocker_count"]) == 0
        ),
    }


def _ready_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    *,
    run_payload: dict[str, Any],
    sealed_payload: dict[str, Any],
    operator: dict[str, Any],
    auto_improve: dict[str, Any],
    preflight: dict[str, Any],
    preseal: dict[str, Any],
    fingerprint: str,
) -> list[RequirementSpec]:
    preflight_goal_run_id = str(_dict(preflight.get("goal_run_identity")).get("effective_run_id", "")).strip()
    preseal_goal_run_id = str(_dict(preseal.get("goal_run_identity")).get("effective_run_id", "")).strip()
    return [
        *_phase_evidence_requirements(
            checks,
            inputs,
            preflight,
            input_key="auto_promotion_preflight",
            source="auto_promotion_preflight",
            phase="preflight",
            fingerprint=fingerprint,
        ),
        *_phase_evidence_requirements(
            checks,
            inputs,
            preseal,
            input_key="auto_promotion_preseal",
            source="auto_promotion_preseal",
            phase="preseal",
            fingerprint=fingerprint,
        ),
        RequirementSpec(
            checks["auto_promotion_goal_run_identity_match"],
            "auto_promotion_goal_run_identity_mismatch",
            "auto_promotion_preflight|auto_promotion_preseal",
            "$.goal_run_identity.effective_run_id",
            f"preflight={preflight_goal_run_id}; preseal={preseal_goal_run_id}",
            "matching non-empty run ids",
            "Auto-promotion preflight and preseal were generated for different goal runs.",
            "Regenerate preflight and preseal with the same explicit GOAL_RUN_ID.",
        ),
        *_manifest_evidence_requirements(
            checks,
            inputs,
            {
                "run_manifest": run_payload,
                "sealed_run_manifest": sealed_payload,
                "operator_summary": operator,
            },
            fingerprint=fingerprint,
        ),
        *_operator_policy_requirements(checks, operator, str(operator["learning_revalidation_status"])),
        *_operator_zero_count_requirements(operator),
        *_auto_improve_requirements(
            checks,
            inputs,
            auto_improve,
            fingerprint=fingerprint,
        ),
    ]


def _ready_manifest_payload(
    *,
    generated_at: str,
    commit: str,
    fingerprint: str,
    status: str,
    inputs: dict[str, dict[str, Any]],
    diagnostics: dict[str, Any],
    checks: dict[str, bool],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_auto_promotion_ready_manifest",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": input_fingerprints(inputs),
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "auto_promotion_status": "allowed" if status == "pass" else "blocked",
        "unattended_promotion_allowed": status == "pass",
        "inputs": inputs,
        "diagnostics": diagnostics,
        "checks": checks,
        "blockers": blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


def build_manifest(
    vault: Path,
    *,
    run_manifest: str = DEFAULT_RUN_MANIFEST,
    sealed_run_manifest: str = DEFAULT_SEALED_RUN_MANIFEST,
    operator_summary: str = DEFAULT_OPERATOR_SUMMARY,
    auto_improve_readiness: str = DEFAULT_AUTO_IMPROVE_READINESS,
    auto_promotion_preflight: str = DEFAULT_AUTO_PROMOTION_PREFLIGHT,
    auto_promotion_preseal: str = DEFAULT_AUTO_PROMOTION_PRESEAL,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    inputs = {
        "run_manifest": _json_identity(vault, run_manifest),
        "sealed_run_manifest": _json_identity(vault, sealed_run_manifest),
        "operator_summary": _json_identity(vault, operator_summary),
        "auto_improve_readiness": _json_identity(vault, auto_improve_readiness),
        "auto_promotion_preflight": _json_identity(vault, auto_promotion_preflight),
        "auto_promotion_preseal": _json_identity(vault, auto_promotion_preseal),
    }
    run_payload, _run_diagnostics = _load_report(vault, run_manifest)
    sealed_payload, _sealed_diagnostics = _load_report(vault, sealed_run_manifest)
    operator_payload, _operator_diagnostics_load = _load_report(vault, operator_summary)
    auto_payload, _auto_diagnostics_load = _load_report(vault, auto_improve_readiness)
    preflight_payload, _preflight_diagnostics_load = _load_report(vault, auto_promotion_preflight)
    preseal_payload, _preseal_diagnostics_load = _load_report(vault, auto_promotion_preseal)

    operator = _operator_diagnostics(operator_payload)
    auto_improve = _auto_improve_diagnostics(auto_payload, current_fingerprint=fingerprint)
    preflight = _preflight_diagnostics(preflight_payload)
    preseal = _preflight_diagnostics(preseal_payload)
    checks = _ready_checks(
        inputs,
        run_payload=run_payload,
        sealed_payload=sealed_payload,
        operator=operator,
        auto_improve=auto_improve,
        preflight=preflight,
        preseal=preseal,
        fingerprint=fingerprint,
    )
    requirements = _ready_requirements(
        checks,
        inputs,
        run_payload=run_payload,
        sealed_payload=sealed_payload,
        operator=operator,
        auto_improve=auto_improve,
        preflight=preflight,
        preseal=preseal,
        fingerprint=fingerprint,
    )
    blockers: list[dict[str, Any]] = []
    append_requirement_blockers(blockers, requirements)

    status = "pass" if not blockers else "fail"
    diagnostics = {
        "preflight": preflight,
        "preseal": preseal,
        "operator": operator,
        "auto_improve": auto_improve,
    }
    return _ready_manifest_payload(
        generated_at=generated_at,
        commit=commit,
        fingerprint=fingerprint,
        status=status,
        inputs=inputs,
        diagnostics=diagnostics,
        checks=checks,
        blockers=blockers,
    )


def write_manifest(vault: Path, manifest: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release-auto-promotion-ready manifest schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify unattended release auto-promotion readiness.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-manifest", default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--sealed-run-manifest", default=DEFAULT_SEALED_RUN_MANIFEST)
    parser.add_argument("--operator-summary", default=DEFAULT_OPERATOR_SUMMARY)
    parser.add_argument("--auto-improve-readiness", default=DEFAULT_AUTO_IMPROVE_READINESS)
    parser.add_argument("--auto-promotion-preflight", default=DEFAULT_AUTO_PROMOTION_PREFLIGHT)
    parser.add_argument("--auto-promotion-preseal", default=DEFAULT_AUTO_PROMOTION_PRESEAL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    manifest = build_manifest(
        vault,
        run_manifest=args.run_manifest,
        sealed_run_manifest=args.sealed_run_manifest,
        operator_summary=args.operator_summary,
        auto_improve_readiness=args.auto_improve_readiness,
        auto_promotion_preflight=args.auto_promotion_preflight,
        auto_promotion_preseal=args.auto_promotion_preseal,
    )
    path = write_manifest(vault, manifest, args.out)
    print(display_path(vault, path))
    if args.check:
        print(f"release_auto_promotion_ready_status={manifest['status']}")
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
