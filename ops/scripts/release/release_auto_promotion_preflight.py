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

DEFAULT_OUT = "build/release/release-auto-promotion-preflight.json"
DEFAULT_AUTO_IMPROVE_READINESS = "ops/reports/auto-improve-readiness.json"
DEFAULT_REMEDIATION_BACKLOG = "ops/reports/remediation-backlog.json"
DEFAULT_LEARNING_REVALIDATION = "ops/reports/learning-readiness-signoff-revalidation.json"
DEFAULT_CLOSEOUT_SUMMARY = "ops/reports/release-closeout-summary.json"
DEFAULT_EVIDENCE_COHORT = "ops/reports/release-evidence-cohort.json"
DEFAULT_GOAL_RUN_IDENTITY = "build/release/release-auto-promotion-goal-run-identity.json"
SCHEMA_PATH = "ops/schemas/release-auto-promotion-preflight.schema.json"
PRODUCER = "ops.scripts.release_auto_promotion_preflight"
SOURCE_COMMAND = "python -m ops.scripts.release_auto_promotion_preflight --vault ."
ALLOWED_LEARNING_REVALIDATION_STATUSES = {
    "current",
    "fresh",
    "metrics_close_candidate",
    "not_due",
    "not_required",
    "pass",
}
PHASES = {"preflight", "preseal"}


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


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "allowed"}
    return False


def _load_report(vault: Path, path_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _resolve(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok":
        payload = {}
    return payload, diagnostics


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


def _auto_improve_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    learning_claim_blockers = _list(payload.get("learning_claim_blockers"))
    promotion_blockers = _list(payload.get("promotion_blockers"))
    stage3_promotion_blockers = _stage3_blocking_promotion_blockers(promotion_blockers)
    release_gate_diagnostic_blockers = _release_gate_diagnostic_blockers(promotion_blockers)
    clean_release_blockers = _list(payload.get("clean_release_blockers"))
    signoff_summary = _dict(_dict(payload.get("diagnostics")).get("learning_signoff_summary"))
    signoff_supported_blocker_id = str(signoff_summary.get("linked_blocker_id", "")).strip()
    signoff_active = _bool_value(signoff_summary.get("active", False))
    unaccepted_learning_claim_blockers = [
        blocker
        for blocker in (_dict(item) for item in learning_claim_blockers)
        if not (
            signoff_active
            and signoff_supported_blocker_id
            and str(blocker.get("id", "")).strip() == signoff_supported_blocker_id
        )
    ]
    can_execute_trial = bool(payload.get("can_execute_trial", False))
    return {
        "can_execute_trial": can_execute_trial,
        "raw_can_promote_result": bool(payload.get("can_promote_result", False)),
        "stage3_can_promote_result": can_execute_trial and not stage3_promotion_blockers,
        "learning_claim_blocker_count": len(learning_claim_blockers),
        "unaccepted_learning_claim_blocker_count": len(unaccepted_learning_claim_blockers),
        "stage3_blocking_promotion_blocker_count": len(stage3_promotion_blockers),
        "release_gate_diagnostic_promotion_blocker_count": len(release_gate_diagnostic_blockers),
        "clean_release_blocker_count": len(clean_release_blockers),
    }


def _remediation_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(payload.get("summary"))
    return {
        "status": str(payload.get("status", "")).strip(),
        "open_total_count": _int_value(summary.get("open_total_count", 0)),
        "open_promotion_count": _int_value(summary.get("open_promotion_count", 0)),
        "open_repeat_count": _int_value(summary.get("open_repeat_count", 0)),
    }


def _learning_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    revalidation = _dict(payload.get("revalidation"))
    return {
        "status": str(payload.get("status", "")).strip(),
        "revalidation_status": str(revalidation.get("status", "")).strip(),
        "clean_closeout_required": bool(revalidation.get("clean_closeout_required", False)),
    }


def _closeout_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(payload.get("summary"))
    release_authority_status = str(payload.get("release_authority_status", "")).strip()
    if not release_authority_status:
        status_v2 = _dict(payload.get("status_v2"))
        axes = _dict(status_v2.get("status_axes"))
        release_authority_status = str(axes.get("release_authority_status", "")).strip()
    machine_release_allowed = _bool_value(payload.get("machine_release_allowed", False))
    clean_release_ready = _bool_value(payload.get("clean_release_ready", False))
    return {
        "status": str(payload.get("status", "")).strip(),
        "release_authority_status": release_authority_status,
        "machine_release_allowed": machine_release_allowed,
        "clean_release_ready": clean_release_ready,
        "accepted_risk_instance_count": _int_value(summary.get("accepted_risk_instance_count", 0)),
        "release_blocking_risk_family_count": _int_value(
            summary.get("release_blocking_risk_family_count", 0)
        ),
        "gate_attention_count": _int_value(summary.get("gate_attention_count", 0)),
        "source_tree_coherence_status": str(
            summary.get("source_tree_coherence_status", "")
        ).strip(),
    }


def _cohort_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    cohort = _dict(payload.get("cohort"))
    summary = _dict(payload.get("summary"))
    return {
        "status": str(payload.get("status", "")).strip(),
        "strict_same_fingerprint": bool(cohort.get("strict_same_fingerprint", False)),
        "component_fingerprint_count": _int_value(cohort.get("component_fingerprint_count", 0)),
        "clean_lane_contract_status": str(summary.get("clean_lane_contract_status", "")).strip(),
    }


def _goal_run_identity_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    observed = _dict(payload.get("observed"))
    return {
        "status": str(payload.get("status", "")).strip(),
        "requested_run_id": str(payload.get("requested_run_id", "")).strip(),
        "effective_run_id": str(payload.get("effective_run_id", "")).strip(),
        "inferred_run_id": str(payload.get("inferred_run_id", "")).strip(),
        "selection_mode": str(payload.get("selection_mode", "")).strip(),
        "goal_run_id_origin": str(payload.get("goal_run_id_origin", "")).strip(),
        "goal_run_status_run_id": str(observed.get("goal_run_status_run_id", "")).strip(),
        "goal_runtime_certificate_run_id": str(
            observed.get("goal_runtime_certificate_run_id", "")
        ).strip(),
        "failure_count": len(_list(payload.get("failures"))),
    }


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


def build_manifest(
    vault: Path,
    *,
    phase: str = "preflight",
    auto_improve_readiness: str = DEFAULT_AUTO_IMPROVE_READINESS,
    remediation_backlog: str = DEFAULT_REMEDIATION_BACKLOG,
    learning_revalidation: str = DEFAULT_LEARNING_REVALIDATION,
    closeout_summary: str = DEFAULT_CLOSEOUT_SUMMARY,
    evidence_cohort: str = DEFAULT_EVIDENCE_COHORT,
    goal_run_identity: str = DEFAULT_GOAL_RUN_IDENTITY,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"unsupported auto-promotion preflight phase: {phase}")
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    inputs = {
        "auto_improve_readiness": _json_identity(vault, auto_improve_readiness),
        "remediation_backlog": _json_identity(vault, remediation_backlog),
        "learning_revalidation": _json_identity(vault, learning_revalidation),
        "closeout_summary": _json_identity(vault, closeout_summary),
        "evidence_cohort": _json_identity(vault, evidence_cohort),
        "goal_run_identity": _json_identity(vault, goal_run_identity),
    }
    auto_payload, _ = _load_report(vault, auto_improve_readiness)
    remediation_payload, _ = _load_report(vault, remediation_backlog)
    learning_payload, _ = _load_report(vault, learning_revalidation)
    closeout_payload, _ = _load_report(vault, closeout_summary)
    cohort_payload, _ = _load_report(vault, evidence_cohort)
    goal_identity_payload, _ = _load_report(vault, goal_run_identity)

    auto = _auto_improve_diagnostics(auto_payload)
    remediation = _remediation_diagnostics(remediation_payload)
    learning = _learning_diagnostics(learning_payload)
    closeout = _closeout_diagnostics(closeout_payload)
    cohort = _cohort_diagnostics(cohort_payload)
    identity = _goal_run_identity_diagnostics(goal_identity_payload)
    checks = {
        "goal_run_identity_load_ok": inputs["goal_run_identity"]["load_status"] == "ok",
        "goal_run_identity_artifact_kind_ok": (
            inputs["goal_run_identity"]["artifact_kind"] == "release_goal_run_identity"
        ),
        "goal_run_identity_current": _identity_current(inputs["goal_run_identity"], fingerprint),
        "goal_run_identity_pass": identity["status"] == "pass",
        "goal_run_identity_effective_run_id_present": bool(identity["effective_run_id"]),
        "auto_improve_readiness_load_ok": inputs["auto_improve_readiness"]["load_status"] == "ok",
        "auto_improve_readiness_artifact_kind_ok": (
            inputs["auto_improve_readiness"]["artifact_kind"] == "auto_improve_readiness_report"
        ),
        "auto_improve_readiness_current": _identity_current(
            inputs["auto_improve_readiness"], fingerprint
        ),
        "auto_improve_can_execute_trial": auto["can_execute_trial"],
        "auto_improve_stage3_promotion_blockers_clear": (
            int(auto["stage3_blocking_promotion_blocker_count"]) == 0
        ),
        "auto_improve_learning_claim_blockers_clear": (
            int(auto["unaccepted_learning_claim_blocker_count"]) == 0
        ),
        "auto_improve_clean_release_blockers_clear": (
            int(auto["clean_release_blocker_count"]) == 0
        ),
        "remediation_backlog_load_ok": inputs["remediation_backlog"]["load_status"] == "ok",
        "remediation_backlog_artifact_kind_ok": (
            inputs["remediation_backlog"]["artifact_kind"] == "remediation_backlog"
        ),
        "remediation_backlog_current": _identity_current(inputs["remediation_backlog"], fingerprint),
        "remediation_backlog_promotion_clear": int(remediation["open_promotion_count"]) == 0,
        "learning_revalidation_load_ok": inputs["learning_revalidation"]["load_status"] == "ok",
        "learning_revalidation_artifact_kind_ok": (
            inputs["learning_revalidation"]["artifact_kind"]
            == "learning_readiness_signoff_revalidation"
        ),
        "learning_revalidation_current_source": _identity_current(
            inputs["learning_revalidation"], fingerprint
        ),
        "learning_revalidation_current": (
            str(learning["revalidation_status"]) in ALLOWED_LEARNING_REVALIDATION_STATUSES
        ),
        "closeout_summary_load_ok": True,
        "closeout_summary_artifact_kind_ok": True,
        "closeout_summary_current": True,
        "closeout_summary_clean": True,
        "closeout_accepted_risk_clean": True,
        "closeout_gate_attention_clean": True,
        "closeout_source_tree_coherence_clean": True,
        "evidence_cohort_load_ok": True,
        "evidence_cohort_artifact_kind_ok": True,
        "evidence_cohort_current": True,
        "evidence_cohort_strict": True,
    }
    if phase == "preseal":
        checks.update(
            {
                "closeout_summary_load_ok": inputs["closeout_summary"]["load_status"] == "ok",
                "closeout_summary_artifact_kind_ok": (
                    inputs["closeout_summary"]["artifact_kind"] == "release_closeout_summary"
                ),
                "closeout_summary_current": _identity_current(inputs["closeout_summary"], fingerprint),
                "closeout_summary_clean": (
                    closeout["status"] == "pass"
                    and closeout["release_authority_status"] == "clean_pass"
                    and bool(closeout["machine_release_allowed"])
                    and bool(closeout["clean_release_ready"])
                ),
                "closeout_accepted_risk_clean": (
                    int(closeout["release_blocking_risk_family_count"]) == 0
                ),
                "closeout_gate_attention_clean": (
                    int(closeout["gate_attention_count"]) == 0
                ),
                "closeout_source_tree_coherence_clean": (
                    closeout["source_tree_coherence_status"] == "pass"
                ),
                "evidence_cohort_load_ok": inputs["evidence_cohort"]["load_status"] == "ok",
                "evidence_cohort_artifact_kind_ok": (
                    inputs["evidence_cohort"]["artifact_kind"] == "release_evidence_cohort"
                ),
                "evidence_cohort_current": _identity_current(inputs["evidence_cohort"], fingerprint),
                "evidence_cohort_strict": (
                    bool(cohort["strict_same_fingerprint"])
                    and cohort["clean_lane_contract_status"] == "pass"
                ),
            }
        )

    blockers: list[dict[str, Any]] = []
    _require(
        blockers,
        passed=checks["goal_run_identity_load_ok"],
        blocker_id="goal_run_identity_not_loadable",
        source="goal_run_identity",
        field_path="$.load_status",
        observed=inputs["goal_run_identity"]["load_status"],
        expected="ok",
        summary="Release auto-promotion goal-run identity evidence is missing or invalid.",
        recommended_next_step="Run make release-auto-promotion-goal-run-id-guard with explicit GOAL_RUN_ID.",
    )
    _require(
        blockers,
        passed=checks["goal_run_identity_artifact_kind_ok"],
        blocker_id="goal_run_identity_artifact_kind_invalid",
        source="goal_run_identity",
        field_path="$.artifact_kind",
        observed=inputs["goal_run_identity"]["artifact_kind"],
        expected="release_goal_run_identity",
        summary="Goal-run identity evidence has an unexpected artifact kind.",
        recommended_next_step="Regenerate release auto-promotion goal-run identity evidence.",
    )
    _require(
        blockers,
        passed=checks["goal_run_identity_current"],
        blocker_id="goal_run_identity_stale",
        source="goal_run_identity",
        field_path="$.source_tree_fingerprint",
        observed=inputs["goal_run_identity"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Goal-run identity evidence does not describe the current source tree.",
        recommended_next_step="Rerun make release-auto-promotion-goal-run-id-guard.",
    )
    _require(
        blockers,
        passed=checks["goal_run_identity_pass"],
        blocker_id="goal_run_identity_not_pass",
        source="goal_run_identity",
        field_path="$.status|$.failures",
        observed=f"status={identity['status']}; failures={identity['failure_count']}",
        expected="status=pass; failures=0",
        summary="The selected GOAL_RUN_ID is not verified release auto-promotion evidence.",
        recommended_next_step="Use an explicit GOAL_RUN_ID that matches the promoted run status and certificate.",
    )
    _require(
        blockers,
        passed=checks["goal_run_identity_effective_run_id_present"],
        blocker_id="goal_run_identity_missing_effective_run_id",
        source="goal_run_identity",
        field_path="$.effective_run_id",
        observed=identity["effective_run_id"],
        expected="non-empty run id",
        summary="Goal-run identity evidence does not name the selected run.",
        recommended_next_step="Rerun with GOAL_RUN_ID=<promoted-run-id>.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_readiness_load_ok"],
        blocker_id="auto_improve_readiness_not_loadable",
        source="auto_improve_readiness",
        field_path="$.load_status",
        observed=inputs["auto_improve_readiness"]["load_status"],
        expected="ok",
        summary="Auto-improve readiness diagnostics are missing or invalid.",
        recommended_next_step="Run make auto-improve-readiness-report-body.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_readiness_artifact_kind_ok"],
        blocker_id="auto_improve_readiness_artifact_kind_invalid",
        source="auto_improve_readiness",
        field_path="$.artifact_kind",
        observed=inputs["auto_improve_readiness"]["artifact_kind"],
        expected="auto_improve_readiness_report",
        summary="Auto-improve readiness diagnostics have an unexpected artifact kind.",
        recommended_next_step="Regenerate auto-improve readiness diagnostics.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_readiness_current"],
        blocker_id="auto_improve_readiness_stale",
        source="auto_improve_readiness",
        field_path="$.source_tree_fingerprint",
        observed=inputs["auto_improve_readiness"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Auto-improve readiness does not describe the current source tree.",
        recommended_next_step="Run make release-auto-promotion-preflight.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_can_execute_trial"],
        blocker_id="auto_improve_trial_not_executable",
        source="auto_improve_readiness",
        field_path="$.can_execute_trial",
        observed=auto["can_execute_trial"],
        expected="true",
        summary="The auto-improve lane cannot execute a trial.",
        recommended_next_step="Refresh auto-improve readiness and resolve execution blockers.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_stage3_promotion_blockers_clear"],
        blocker_id="auto_improve_independent_promotion_blockers_open",
        source="auto_improve_readiness",
        field_path="$.promotion_blockers[?scope!='release_gate']",
        observed=auto["stage3_blocking_promotion_blocker_count"],
        expected="0",
        summary="Auto-improve readiness has independent promotion blockers.",
        recommended_next_step="Resolve non-release-gate auto-improve promotion blockers before sealing.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_learning_claim_blockers_clear"],
        blocker_id="auto_improve_learning_claim_blockers_open",
        source="auto_improve_readiness",
        field_path="$.learning_claim_blockers",
        observed=auto["learning_claim_blocker_count"],
        expected="0",
        summary="Learning-claim blockers are still open for unattended promotion.",
        recommended_next_step="Resolve or renew learning readiness before running expensive release stages.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_clean_release_blockers_clear"],
        blocker_id="auto_improve_clean_release_blockers_open",
        source="auto_improve_readiness",
        field_path="$.clean_release_blockers",
        observed=auto["clean_release_blocker_count"],
        expected="0",
        summary="Clean-release blockers are still open.",
        recommended_next_step="Resolve clean-release blockers before sealing.",
    )
    _require(
        blockers,
        passed=checks["remediation_backlog_load_ok"],
        blocker_id="remediation_backlog_not_loadable",
        source="remediation_backlog",
        field_path="$.load_status",
        observed=inputs["remediation_backlog"]["load_status"],
        expected="ok",
        summary="Remediation backlog evidence is missing or invalid.",
        recommended_next_step="Run make remediation-backlog.",
    )
    _require(
        blockers,
        passed=checks["remediation_backlog_artifact_kind_ok"],
        blocker_id="remediation_backlog_artifact_kind_invalid",
        source="remediation_backlog",
        field_path="$.artifact_kind",
        observed=inputs["remediation_backlog"]["artifact_kind"],
        expected="remediation_backlog",
        summary="Remediation backlog evidence has an unexpected artifact kind.",
        recommended_next_step="Regenerate remediation backlog evidence.",
    )
    _require(
        blockers,
        passed=checks["remediation_backlog_current"],
        blocker_id="remediation_backlog_stale",
        source="remediation_backlog",
        field_path="$.source_tree_fingerprint",
        observed=inputs["remediation_backlog"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Remediation backlog does not describe the current source tree.",
        recommended_next_step="Run make remediation-backlog.",
    )
    _require(
        blockers,
        passed=checks["remediation_backlog_promotion_clear"],
        blocker_id="remediation_backlog_promotion_open",
        source="remediation_backlog",
        field_path="$.summary.open_promotion_count",
        observed=remediation["open_promotion_count"],
        expected="0",
        summary="Promotion-blocking remediation backlog items are open.",
        recommended_next_step="Close or defer promotion-blocking remediation items before run-ready.",
    )
    _require(
        blockers,
        passed=checks["learning_revalidation_load_ok"],
        blocker_id="learning_revalidation_not_loadable",
        source="learning_revalidation",
        field_path="$.load_status",
        observed=inputs["learning_revalidation"]["load_status"],
        expected="ok",
        summary="Learning revalidation evidence is missing or invalid.",
        recommended_next_step="Run make learning-readiness-signoff-revalidation.",
    )
    _require(
        blockers,
        passed=checks["learning_revalidation_artifact_kind_ok"],
        blocker_id="learning_revalidation_artifact_kind_invalid",
        source="learning_revalidation",
        field_path="$.artifact_kind",
        observed=inputs["learning_revalidation"]["artifact_kind"],
        expected="learning_readiness_signoff_revalidation",
        summary="Learning revalidation evidence has an unexpected artifact kind.",
        recommended_next_step="Regenerate learning revalidation evidence.",
    )
    _require(
        blockers,
        passed=checks["learning_revalidation_current_source"],
        blocker_id="learning_revalidation_stale",
        source="learning_revalidation",
        field_path="$.source_tree_fingerprint",
        observed=inputs["learning_revalidation"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Learning revalidation does not describe the current source tree.",
        recommended_next_step="Run make learning-readiness-signoff-revalidation.",
    )
    _require(
        blockers,
        passed=checks["learning_revalidation_current"],
        blocker_id="learning_revalidation_due",
        source="learning_revalidation",
        field_path="$.revalidation.status",
        observed=learning["revalidation_status"],
        expected="one of current, fresh, metrics_close_candidate, not_due, not_required, pass",
        summary="Learning revalidation is not current enough for unattended promotion.",
        recommended_next_step="Renew or resolve learning readiness before spending run/seal cycles.",
    )

    if phase == "preseal":
        _require(
            blockers,
            passed=checks["closeout_summary_load_ok"],
            blocker_id="closeout_summary_not_loadable",
            source="closeout_summary",
            field_path="$.load_status",
            observed=inputs["closeout_summary"]["load_status"],
            expected="ok",
            summary="Release closeout summary is missing or invalid.",
            recommended_next_step="Run make release-closeout-summary-report.",
        )
        _require(
            blockers,
            passed=checks["closeout_summary_artifact_kind_ok"],
            blocker_id="closeout_summary_artifact_kind_invalid",
            source="closeout_summary",
            field_path="$.artifact_kind",
            observed=inputs["closeout_summary"]["artifact_kind"],
            expected="release_closeout_summary",
            summary="Release closeout summary has an unexpected artifact kind.",
            recommended_next_step="Regenerate release closeout summary evidence.",
        )
        _require(
            blockers,
            passed=checks["closeout_summary_current"],
            blocker_id="closeout_summary_stale",
            source="closeout_summary",
            field_path="$.source_tree_fingerprint",
            observed=inputs["closeout_summary"]["source_tree_fingerprint"],
            expected=fingerprint,
            summary="Release closeout summary does not describe the current source tree.",
            recommended_next_step="Run make release-auto-promotion-preseal.",
        )
        _require(
            blockers,
            passed=checks["closeout_summary_clean"],
            blocker_id="closeout_summary_not_clean",
            source="closeout_summary",
            field_path="$.release_authority_status|$.machine_release_allowed|$.clean_release_ready",
            observed=(
                f"release_authority_status={closeout['release_authority_status']};"
                f"machine_release_allowed={closeout['machine_release_allowed']};"
                f"clean_release_ready={closeout['clean_release_ready']}"
            ),
            expected="release_authority_status=clean_pass; machine_release_allowed=true; clean_release_ready=true",
            summary="Release closeout is not clean enough for unattended promotion.",
            recommended_next_step="Resolve closeout blockers before sealing promotion evidence.",
        )
        _require(
            blockers,
            passed=checks["closeout_accepted_risk_clean"],
            blocker_id="closeout_accepted_risk_not_clean",
            source="closeout_summary",
            field_path="$.summary.accepted_risk_instance_count|$.summary.release_blocking_risk_family_count",
            observed=(
                f"accepted={closeout['accepted_risk_instance_count']};"
                f"release_blocking={closeout['release_blocking_risk_family_count']}"
            ),
            expected="release_blocking=0; advisory accepted risks may remain diagnostic",
            summary="Closeout has accepted-risk families that still block the clean release lane.",
            recommended_next_step="Resolve clean-lane blocking release risks before sealing.",
        )
        _require(
            blockers,
            passed=checks["closeout_gate_attention_clean"],
            blocker_id="closeout_gate_attention_not_clean",
            source="closeout_summary",
            field_path="$.summary.gate_attention_count",
            observed=closeout["gate_attention_count"],
            expected="0",
            summary="Closeout gate-attention count is not clean.",
            recommended_next_step="Resolve gate attention before sealing promotion evidence.",
        )
        _require(
            blockers,
            passed=checks["closeout_source_tree_coherence_clean"],
            blocker_id="closeout_source_tree_coherence_not_clean",
            source="closeout_summary",
            field_path="$.summary.source_tree_coherence_status",
            observed=closeout["source_tree_coherence_status"],
            expected="pass",
            summary="Closeout source-tree coherence is not clean.",
            recommended_next_step="Refresh lower release evidence into one source-tree cohort before sealing.",
        )
        _require(
            blockers,
            passed=checks["evidence_cohort_load_ok"],
            blocker_id="evidence_cohort_not_loadable",
            source="evidence_cohort",
            field_path="$.load_status",
            observed=inputs["evidence_cohort"]["load_status"],
            expected="ok",
            summary="Release evidence cohort is missing or invalid.",
            recommended_next_step="Run make release-evidence-cohort.",
        )
        _require(
            blockers,
            passed=checks["evidence_cohort_artifact_kind_ok"],
            blocker_id="evidence_cohort_artifact_kind_invalid",
            source="evidence_cohort",
            field_path="$.artifact_kind",
            observed=inputs["evidence_cohort"]["artifact_kind"],
            expected="release_evidence_cohort",
            summary="Release evidence cohort has an unexpected artifact kind.",
            recommended_next_step="Regenerate release evidence cohort evidence.",
        )
        _require(
            blockers,
            passed=checks["evidence_cohort_current"],
            blocker_id="evidence_cohort_stale",
            source="evidence_cohort",
            field_path="$.source_tree_fingerprint",
            observed=inputs["evidence_cohort"]["source_tree_fingerprint"],
            expected=fingerprint,
            summary="Release evidence cohort does not describe the current source tree.",
            recommended_next_step="Run make release-evidence-cohort.",
        )
        _require(
            blockers,
            passed=checks["evidence_cohort_strict"],
            blocker_id="evidence_cohort_not_strict",
            source="evidence_cohort",
            field_path="$.cohort.strict_same_fingerprint|$.summary.clean_lane_contract_status",
            observed=(
                f"strict_same_fingerprint={cohort['strict_same_fingerprint']};"
                f"clean_lane_contract_status={cohort['clean_lane_contract_status']}"
            ),
            expected="strict_same_fingerprint=true; clean_lane_contract_status=pass",
            summary="Release evidence cohort is not strict enough for unattended promotion.",
            recommended_next_step="Refresh release evidence into one strict source-tree cohort before sealing.",
        )

    status = "pass" if not blockers else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_auto_promotion_preflight",
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
        "phase": phase,
        "status": status,
        "goal_run_identity": identity,
        "inputs": inputs,
        "diagnostics": {
            "goal_run_identity": identity,
            "auto_improve": auto,
            "remediation_backlog": remediation,
            "learning_revalidation": learning,
            "closeout_summary": closeout,
            "evidence_cohort": cohort,
        },
        "checks": checks,
        "blockers": blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


def write_manifest(vault: Path, manifest: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release auto-promotion preflight schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check cheap unattended-promotion preflight diagnostics.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--phase", choices=sorted(PHASES), default="preflight")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--auto-improve-readiness", default=DEFAULT_AUTO_IMPROVE_READINESS)
    parser.add_argument("--remediation-backlog", default=DEFAULT_REMEDIATION_BACKLOG)
    parser.add_argument("--learning-revalidation", default=DEFAULT_LEARNING_REVALIDATION)
    parser.add_argument("--closeout-summary", default=DEFAULT_CLOSEOUT_SUMMARY)
    parser.add_argument("--evidence-cohort", default=DEFAULT_EVIDENCE_COHORT)
    parser.add_argument("--goal-run-identity", default=DEFAULT_GOAL_RUN_IDENTITY)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    manifest = build_manifest(
        vault,
        phase=args.phase,
        auto_improve_readiness=args.auto_improve_readiness,
        remediation_backlog=args.remediation_backlog,
        learning_revalidation=args.learning_revalidation,
        closeout_summary=args.closeout_summary,
        evidence_cohort=args.evidence_cohort,
        goal_run_identity=args.goal_run_identity,
    )
    path = write_manifest(vault, manifest, args.out)
    print(display_path(vault, path))
    if args.check:
        print(f"release_auto_promotion_preflight_status={manifest['status']}")
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
