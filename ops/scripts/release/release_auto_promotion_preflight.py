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
from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.release.auto_promotion_learning_runtime import (
    ALLOWED_LEARNING_REVALIDATION_STATUSES,
    bool_value,
    unaccepted_learning_claim_blockers,
)
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
    learning_claim_blockers_without_signoff = unaccepted_learning_claim_blockers(
        learning_claim_blockers,
        payload.get("diagnostics"),
    )
    can_execute_trial = bool(payload.get("can_execute_trial", False))
    return {
        "can_execute_trial": can_execute_trial,
        "raw_can_promote_result": bool(payload.get("can_promote_result", False)),
        "stage3_can_promote_result": can_execute_trial and not stage3_promotion_blockers,
        "learning_claim_blocker_count": len(learning_claim_blockers),
        "unaccepted_learning_claim_blocker_count": len(
            learning_claim_blockers_without_signoff
        ),
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
    machine_release_allowed = bool_value(payload.get("machine_release_allowed", False))
    clean_release_ready = bool_value(payload.get("clean_release_ready", False))
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
        "binding_status": str(payload.get("binding_status", "")).strip(),
        "verification_status": str(payload.get("verification_status", "")).strip(),
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
        "verification_failure_count": len(_list(payload.get("verification_failures"))),
        "verification_failures": [
            str(item) for item in _list(payload.get("verification_failures"))
        ],
    }


def _goal_run_identity_final_promotion_blockers(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in (_dict(candidate) for candidate in _list(payload.get("verification_blockers")))
        if item
    ]


def _identity_current(identity: dict[str, Any], fingerprint: str) -> bool:
    return str(identity.get("source_tree_fingerprint", "")).strip() == fingerprint


def _identity_revision_current(identity: dict[str, Any], current_revision: str) -> bool:
    source_revision = str(identity.get("source_revision", "")).strip()
    return bool(source_revision) and source_revision in {
        current_revision,
        "source_package_without_git",
    }


def _identity_current_for_source(
    identity: dict[str, Any],
    *,
    fingerprint: str,
    current_revision: str,
) -> bool:
    return _identity_current(identity, fingerprint) and _identity_revision_current(
        identity,
        current_revision,
    )


def _goal_run_identity_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    identity: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> list[RequirementSpec]:
    goal_input = inputs["goal_run_identity"]
    return [
        RequirementSpec(
            checks["goal_run_identity_load_ok"],
            "goal_run_identity_not_loadable",
            "goal_run_identity",
            "$.load_status",
            goal_input["load_status"],
            "ok",
            "Release auto-promotion goal-run identity evidence is missing or invalid.",
            "Run make release-auto-promotion-goal-run-id-guard with explicit GOAL_RUN_ID.",
        ),
        RequirementSpec(
            checks["goal_run_identity_artifact_kind_ok"],
            "goal_run_identity_artifact_kind_invalid",
            "goal_run_identity",
            "$.artifact_kind",
            goal_input["artifact_kind"],
            "release_goal_run_identity",
            "Goal-run identity evidence has an unexpected artifact kind.",
            "Regenerate release auto-promotion goal-run identity evidence.",
        ),
        RequirementSpec(
            checks["goal_run_identity_current"],
            "goal_run_identity_stale",
            "goal_run_identity",
            "$.source_tree_fingerprint",
            (
                f"source_revision={goal_input['source_revision']};"
                f"source_tree_fingerprint={goal_input['source_tree_fingerprint']}"
            ),
            f"source_revision={current_revision}; source_tree_fingerprint={fingerprint}",
            "Goal-run identity evidence does not describe the current source tree.",
            "Rerun make release-auto-promotion-goal-run-id-guard.",
        ),
        RequirementSpec(
            checks["goal_run_identity_pass"],
            "goal_run_identity_not_pass",
            "goal_run_identity",
            "$.status|$.failures",
            f"status={identity['status']}; failures={identity['failure_count']}",
            "status=pass; failures=0",
            "The selected GOAL_RUN_ID binding is unsafe for release auto-promotion.",
            "Use an explicit GOAL_RUN_ID that does not contradict current goal-run evidence.",
        ),
    ]


def _auto_improve_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    auto: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> list[RequirementSpec]:
    auto_input = inputs["auto_improve_readiness"]
    return [
        RequirementSpec(
            checks["auto_improve_readiness_load_ok"],
            "auto_improve_readiness_not_loadable",
            "auto_improve_readiness",
            "$.load_status",
            auto_input["load_status"],
            "ok",
            "Auto-improve readiness diagnostics are missing or invalid.",
            "Run make auto-improve-readiness-report-body.",
        ),
        RequirementSpec(
            checks["auto_improve_readiness_artifact_kind_ok"],
            "auto_improve_readiness_artifact_kind_invalid",
            "auto_improve_readiness",
            "$.artifact_kind",
            auto_input["artifact_kind"],
            "auto_improve_readiness_report",
            "Auto-improve readiness diagnostics have an unexpected artifact kind.",
            "Regenerate auto-improve readiness diagnostics.",
        ),
        RequirementSpec(
            checks["auto_improve_readiness_current"],
            "auto_improve_readiness_stale",
            "auto_improve_readiness",
            "$.source_revision|$.source_tree_fingerprint",
            (
                f"source_revision={auto_input['source_revision']};"
                f"source_tree_fingerprint={auto_input['source_tree_fingerprint']}"
            ),
            f"source_revision={current_revision}; source_tree_fingerprint={fingerprint}",
            "Auto-improve readiness does not describe the current source tree.",
            "Run make release-auto-promotion-preflight.",
        ),
        RequirementSpec(
            checks["auto_improve_can_execute_trial"],
            "auto_improve_trial_not_executable",
            "auto_improve_readiness",
            "$.can_execute_trial",
            auto["can_execute_trial"],
            "true",
            "The auto-improve lane cannot execute a trial.",
            "Refresh auto-improve readiness and resolve execution blockers.",
            GATE_EFFECT_BLOCKS_EXECUTION,
        ),
        RequirementSpec(
            checks["auto_improve_stage3_promotion_blockers_clear"],
            "auto_improve_independent_promotion_blockers_open",
            "auto_improve_readiness",
            "$.promotion_blockers[?scope!='release_gate']",
            auto["stage3_blocking_promotion_blocker_count"],
            "0",
            "Auto-improve readiness has independent promotion blockers.",
            "Resolve non-release-gate auto-improve promotion blockers before sealing.",
        ),
        RequirementSpec(
            checks["auto_improve_learning_claim_blockers_clear"],
            "auto_improve_learning_claim_blockers_open",
            "auto_improve_readiness",
            "$.learning_claim_blockers",
            auto["learning_claim_blocker_count"],
            "0",
            "Learning-claim blockers are still open for unattended promotion.",
            "Resolve or renew learning readiness before running expensive release stages.",
            GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
        ),
        RequirementSpec(
            checks["auto_improve_clean_release_blockers_clear"],
            "auto_improve_clean_release_blockers_open",
            "auto_improve_readiness",
            "$.clean_release_blockers",
            auto["clean_release_blocker_count"],
            "0",
            "Clean-release blockers are still open.",
            "Resolve clean-release blockers before sealing.",
        ),
    ]


def _artifact_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    *,
    input_key: str,
    source: str,
    artifact_kind: str,
    stale_next_step: str,
    fingerprint: str,
    current_revision: str,
) -> list[RequirementSpec]:
    identity = inputs[input_key]
    return [
        RequirementSpec(
            checks[f"{input_key}_load_ok"],
            f"{input_key}_not_loadable",
            source,
            "$.load_status",
            identity["load_status"],
            "ok",
            f"{source.replace('_', ' ').capitalize()} evidence is missing or invalid.",
            stale_next_step,
        ),
        RequirementSpec(
            checks[f"{input_key}_artifact_kind_ok"],
            f"{input_key}_artifact_kind_invalid",
            source,
            "$.artifact_kind",
            identity["artifact_kind"],
            artifact_kind,
            f"{source.replace('_', ' ').capitalize()} evidence has an unexpected artifact kind.",
            f"Regenerate {source.replace('_', ' ')} evidence.",
        ),
        RequirementSpec(
            checks[f"{input_key}_current"],
            f"{input_key}_stale",
            source,
            "$.source_revision|$.source_tree_fingerprint",
            (
                f"source_revision={identity['source_revision']};"
                f"source_tree_fingerprint={identity['source_tree_fingerprint']}"
            ),
            f"source_revision={current_revision}; source_tree_fingerprint={fingerprint}",
            f"{source.replace('_', ' ').capitalize()} does not describe the current source tree.",
            stale_next_step,
        ),
    ]


def _base_phase_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    *,
    identity: dict[str, Any],
    auto: dict[str, Any],
    remediation: dict[str, Any],
    learning: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> list[RequirementSpec]:
    requirements = [
        *_goal_run_identity_requirements(
            checks,
            inputs,
            identity,
            fingerprint,
            current_revision,
        ),
        *_auto_improve_requirements(checks, inputs, auto, fingerprint, current_revision),
        *_artifact_requirements(
            checks,
            inputs,
            input_key="remediation_backlog",
            source="remediation_backlog",
            artifact_kind="remediation_backlog",
            stale_next_step="Run make remediation-backlog.",
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        RequirementSpec(
            checks["remediation_backlog_promotion_clear"],
            "remediation_backlog_promotion_open",
            "remediation_backlog",
            "$.summary.open_promotion_count",
            remediation["open_promotion_count"],
            "0",
            "Promotion-blocking remediation backlog items are open.",
            "Close or defer promotion-blocking remediation items before run-ready.",
        ),
        *_artifact_requirements(
            checks,
            inputs,
            input_key="learning_revalidation",
            source="learning_revalidation",
            artifact_kind="learning_readiness_signoff_revalidation",
            stale_next_step="Run make learning-readiness-signoff-revalidation.",
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        RequirementSpec(
            checks["learning_revalidation_current"],
            "learning_revalidation_due",
            "learning_revalidation",
            "$.revalidation.status",
            learning["revalidation_status"],
            "one of current, fresh, metrics_close_candidate, not_due, not_required, pass",
            "Learning revalidation is not current enough for unattended promotion.",
            "Renew or resolve learning readiness before spending run/seal cycles.",
        ),
    ]
    return requirements


def _preseal_phase_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    *,
    closeout: dict[str, Any],
    cohort: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> list[RequirementSpec]:
    return [
        *_artifact_requirements(
            checks,
            inputs,
            input_key="closeout_summary",
            source="closeout_summary",
            artifact_kind="release_closeout_summary",
            stale_next_step="Run make release-auto-promotion-preseal.",
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        RequirementSpec(
            checks["closeout_summary_clean"],
            "closeout_summary_not_clean",
            "closeout_summary",
            "$.release_authority_status|$.machine_release_allowed|$.clean_release_ready",
            (
                f"release_authority_status={closeout['release_authority_status']};"
                f"machine_release_allowed={closeout['machine_release_allowed']};"
                f"clean_release_ready={closeout['clean_release_ready']}"
            ),
            "release_authority_status=clean_pass; machine_release_allowed=true; clean_release_ready=true",
            "Release closeout is not clean enough for unattended promotion.",
            "Resolve closeout blockers before sealing promotion evidence.",
        ),
        RequirementSpec(
            checks["closeout_accepted_risk_clean"],
            "closeout_accepted_risk_not_clean",
            "closeout_summary",
            "$.summary.accepted_risk_instance_count|$.summary.release_blocking_risk_family_count",
            (
                f"accepted={closeout['accepted_risk_instance_count']};"
                f"release_blocking={closeout['release_blocking_risk_family_count']}"
            ),
            "release_blocking=0; advisory accepted risks may remain diagnostic",
            "Closeout has accepted-risk families that still block the clean release lane.",
            "Resolve clean-lane blocking release risks before sealing.",
            GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
        ),
        RequirementSpec(
            checks["closeout_gate_attention_clean"],
            "closeout_gate_attention_not_clean",
            "closeout_summary",
            "$.summary.gate_attention_count",
            closeout["gate_attention_count"],
            "0",
            "Closeout gate-attention count is not clean.",
            "Resolve gate attention before sealing promotion evidence.",
        ),
        RequirementSpec(
            checks["closeout_source_tree_coherence_clean"],
            "closeout_source_tree_coherence_not_clean",
            "closeout_summary",
            "$.summary.source_tree_coherence_status",
            closeout["source_tree_coherence_status"],
            "pass",
            "Closeout source-tree coherence is not clean.",
            "Refresh lower release evidence into one source-tree cohort before sealing.",
        ),
        *_artifact_requirements(
            checks,
            inputs,
            input_key="evidence_cohort",
            source="evidence_cohort",
            artifact_kind="release_evidence_cohort",
            stale_next_step="Run make release-evidence-cohort.",
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        RequirementSpec(
            checks["evidence_cohort_strict"],
            "evidence_cohort_not_strict",
            "evidence_cohort",
            "$.cohort.strict_same_fingerprint|$.summary.clean_lane_contract_status",
            (
                f"strict_same_fingerprint={cohort['strict_same_fingerprint']};"
                f"clean_lane_contract_status={cohort['clean_lane_contract_status']}"
            ),
            "strict_same_fingerprint=true; clean_lane_contract_status=pass",
            "Release evidence cohort is not strict enough for unattended promotion.",
            "Refresh release evidence into one strict source-tree cohort before sealing.",
        ),
    ]


def _preflight_checks(
    inputs: dict[str, dict[str, Any]],
    *,
    phase: str,
    identity: dict[str, Any],
    auto: dict[str, Any],
    remediation: dict[str, Any],
    learning: dict[str, Any],
    closeout: dict[str, Any],
    cohort: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> dict[str, bool]:
    checks = {
        "goal_run_identity_load_ok": inputs["goal_run_identity"]["load_status"] == "ok",
        "goal_run_identity_artifact_kind_ok": (
            inputs["goal_run_identity"]["artifact_kind"] == "release_goal_run_identity"
        ),
        "goal_run_identity_current": _identity_current_for_source(
            inputs["goal_run_identity"],
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        "goal_run_identity_pass": identity["status"] == "pass",
        "goal_run_identity_effective_run_id_present": bool(identity["effective_run_id"]),
        "auto_improve_readiness_load_ok": inputs["auto_improve_readiness"]["load_status"] == "ok",
        "auto_improve_readiness_artifact_kind_ok": (
            inputs["auto_improve_readiness"]["artifact_kind"] == "auto_improve_readiness_report"
        ),
        "auto_improve_readiness_current": _identity_current_for_source(
            inputs["auto_improve_readiness"],
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        "auto_improve_can_execute_trial": auto["can_execute_trial"],
        "auto_improve_stage3_promotion_blockers_clear": (
            int(auto["stage3_blocking_promotion_blocker_count"]) == 0
        ),
        "auto_improve_learning_claim_blockers_clear": (
            int(auto["unaccepted_learning_claim_blocker_count"]) == 0
        ),
        "auto_improve_clean_release_blockers_clear": int(auto["clean_release_blocker_count"]) == 0,
        "remediation_backlog_load_ok": inputs["remediation_backlog"]["load_status"] == "ok",
        "remediation_backlog_artifact_kind_ok": (
            inputs["remediation_backlog"]["artifact_kind"] == "remediation_backlog"
        ),
        "remediation_backlog_current": _identity_current_for_source(
            inputs["remediation_backlog"],
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        "remediation_backlog_promotion_clear": int(remediation["open_promotion_count"]) == 0,
        "learning_revalidation_load_ok": inputs["learning_revalidation"]["load_status"] == "ok",
        "learning_revalidation_artifact_kind_ok": (
            inputs["learning_revalidation"]["artifact_kind"]
            == "learning_readiness_signoff_revalidation"
        ),
        "learning_revalidation_current_source": _identity_current_for_source(
            inputs["learning_revalidation"],
            fingerprint=fingerprint,
            current_revision=current_revision,
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
            _preseal_checks(
                inputs,
                closeout=closeout,
                cohort=cohort,
                fingerprint=fingerprint,
                current_revision=current_revision,
            )
        )
    return checks


def _preseal_checks(
    inputs: dict[str, dict[str, Any]],
    *,
    closeout: dict[str, Any],
    cohort: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> dict[str, bool]:
    return {
        "closeout_summary_load_ok": inputs["closeout_summary"]["load_status"] == "ok",
        "closeout_summary_artifact_kind_ok": (
            inputs["closeout_summary"]["artifact_kind"] == "release_closeout_summary"
        ),
        "closeout_summary_current": _identity_current_for_source(
            inputs["closeout_summary"],
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        "closeout_summary_clean": (
            closeout["status"] == "pass"
            and closeout["release_authority_status"] == "clean_pass"
            and bool(closeout["machine_release_allowed"])
            and bool(closeout["clean_release_ready"])
        ),
        "closeout_accepted_risk_clean": int(closeout["release_blocking_risk_family_count"]) == 0,
        "closeout_gate_attention_clean": int(closeout["gate_attention_count"]) == 0,
        "closeout_source_tree_coherence_clean": closeout["source_tree_coherence_status"] == "pass",
        "evidence_cohort_load_ok": inputs["evidence_cohort"]["load_status"] == "ok",
        "evidence_cohort_artifact_kind_ok": (
            inputs["evidence_cohort"]["artifact_kind"] == "release_evidence_cohort"
        ),
        "evidence_cohort_current": _identity_current_for_source(
            inputs["evidence_cohort"],
            fingerprint=fingerprint,
            current_revision=current_revision,
        ),
        "evidence_cohort_strict": (
            bool(cohort["strict_same_fingerprint"])
            and cohort["clean_lane_contract_status"] == "pass"
        ),
    }


def _preflight_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    *,
    phase: str,
    identity: dict[str, Any],
    auto: dict[str, Any],
    remediation: dict[str, Any],
    learning: dict[str, Any],
    closeout: dict[str, Any],
    cohort: dict[str, Any],
    fingerprint: str,
    current_revision: str,
) -> list[RequirementSpec]:
    requirements = _base_phase_requirements(
        checks,
        inputs,
        identity=identity,
        auto=auto,
        remediation=remediation,
        learning=learning,
        fingerprint=fingerprint,
        current_revision=current_revision,
    )
    if phase == "preseal":
        requirements.extend(
            _preseal_phase_requirements(
                checks,
                inputs,
                closeout=closeout,
                cohort=cohort,
                fingerprint=fingerprint,
                current_revision=current_revision,
            )
        )
    return requirements


def _preflight_manifest_payload(
    *,
    generated_at: str,
    commit: str,
    fingerprint: str,
    phase: str,
    status: str,
    inputs: dict[str, dict[str, Any]],
    goal_run_identity: dict[str, Any],
    diagnostics: dict[str, Any],
    checks: dict[str, bool],
    blockers: list[dict[str, Any]],
    final_promotion_blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_auto_promotion_preflight",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": input_fingerprints(inputs),
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_diagnostic",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "phase": phase,
        "status": status,
        "goal_run_identity": goal_run_identity,
        "inputs": inputs,
        "diagnostics": diagnostics,
        "checks": checks,
        "blockers": blockers,
        "final_promotion_blockers": final_promotion_blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


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
    final_promotion_blockers = _goal_run_identity_final_promotion_blockers(
        goal_identity_payload
    )
    checks = _preflight_checks(
        inputs,
        phase=phase,
        identity=identity,
        auto=auto,
        remediation=remediation,
        learning=learning,
        closeout=closeout,
        cohort=cohort,
        fingerprint=fingerprint,
        current_revision=commit,
    )
    requirements = _preflight_requirements(
        checks,
        inputs,
        phase=phase,
        identity=identity,
        auto=auto,
        remediation=remediation,
        learning=learning,
        closeout=closeout,
        cohort=cohort,
        fingerprint=fingerprint,
        current_revision=commit,
    )
    blockers: list[dict[str, Any]] = []
    append_requirement_blockers(blockers, requirements)

    status = "pass" if not blockers else "fail"
    diagnostics = {
        "goal_run_identity": identity,
        "auto_improve": auto,
        "remediation_backlog": remediation,
        "learning_revalidation": learning,
        "closeout_summary": closeout,
        "evidence_cohort": cohort,
    }
    return _preflight_manifest_payload(
        generated_at=generated_at,
        commit=commit,
        fingerprint=fingerprint,
        phase=phase,
        status=status,
        inputs=inputs,
        goal_run_identity=identity,
        diagnostics=diagnostics,
        checks=checks,
        blockers=blockers,
        final_promotion_blockers=final_promotion_blockers,
    )


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
