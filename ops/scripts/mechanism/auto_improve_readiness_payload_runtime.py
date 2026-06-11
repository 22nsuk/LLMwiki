from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ops.scripts.learning_readiness_signoff_state import SIGNOFF_REPORT_REL_PATH

from .auto_improve_readiness_constants_runtime import (
    ARTIFACT_FRESHNESS_REPORT_REL_PATH,
    GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
    LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_REPORT_REL_PATH,
    MECHANISM_REVIEW_REPORT_REL_PATH,
    MUTATION_PROPOSAL_REPORT_REL_PATH,
    OUTCOME_METRICS_REPORT_REL_PATH,
    REFRESH_GENERATED_TARGET,
    RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH,
    RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH,
    SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH,
    SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH,
)

if TYPE_CHECKING:
    from .auto_improve_readiness_runtime import ReadinessInputs


def readiness_inputs_payload(*, remediation_backlog_path: str) -> dict[str, str]:
    return {
        "refresh_generated_target": REFRESH_GENERATED_TARGET,
        "outcome_metrics_report": OUTCOME_METRICS_REPORT_REL_PATH,
        "mechanism_review_report": MECHANISM_REVIEW_REPORT_REL_PATH,
        "mutation_proposal_report": MUTATION_PROPOSAL_REPORT_REL_PATH,
        "artifact_freshness_report": ARTIFACT_FRESHNESS_REPORT_REL_PATH,
        "selected_contract_summary_report": SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH,
        "source_package_clean_extract_report": SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH,
        "release_closeout_summary_report": RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH,
        "release_closeout_batch_manifest_report": RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH,
        "release_closeout_finality_attestation_report": RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH,
        "release_evidence_cohort_report": RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH,
        "release_closeout_post_check_finalizer_report": RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH,
        "release_authority_preflight_report": RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH,
        "goal_worktree_guard_report": GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
        "remediation_backlog_report": remediation_backlog_path,
        "learning_readiness_signoff_report": SIGNOFF_REPORT_REL_PATH,
    }


def readiness_file_inputs(*, remediation_backlog_path: str) -> dict[str, str]:
    return {
        "outcome_metrics_report": OUTCOME_METRICS_REPORT_REL_PATH,
        "mechanism_review_report": MECHANISM_REVIEW_REPORT_REL_PATH,
        "mutation_proposal_report": MUTATION_PROPOSAL_REPORT_REL_PATH,
        "artifact_freshness_report": ARTIFACT_FRESHNESS_REPORT_REL_PATH,
        "selected_contract_summary_report": SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH,
        "source_package_clean_extract_report": SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH,
        "release_closeout_summary_report": RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH,
        "release_closeout_batch_manifest_report": RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH,
        "release_closeout_finality_attestation_report": RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH,
        "release_evidence_cohort_report": RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH,
        "release_closeout_post_check_finalizer_report": RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH,
        "release_authority_preflight_report": RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH,
        "goal_worktree_guard_report": GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
        "remediation_backlog_report": remediation_backlog_path,
        "learning_confirmed_legacy_reconstruction_report": (
            LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_REPORT_REL_PATH
        ),
        "learning_readiness_signoff_report": SIGNOFF_REPORT_REL_PATH,
    }


def readiness_diagnostics_payload(inputs: ReadinessInputs) -> dict[str, Any]:
    queue_state = inputs.queue_state
    return {
        "loop_health_summary": queue_state.loop_health_summary,
        "same_eval_telemetry_summary": queue_state.same_eval_telemetry_summary,
        "artifact_freshness_summary": inputs.artifact_freshness_summary,
        "selected_contract_summary": inputs.selected_contract_summary,
        "source_package_clean_extract_summary": inputs.source_package_clean_extract_summary,
        "release_closeout_summary": inputs.release_closeout_summary,
        "release_closeout_batch_manifest_summary": inputs.release_closeout_batch_manifest_summary,
        "release_closeout_finality_summary": inputs.release_closeout_finality_summary,
        "release_evidence_cohort_summary": inputs.release_evidence_cohort_summary,
        "artifact_finalization_summary": inputs.artifact_finalization_summary,
        "release_authority_preflight_summary": inputs.release_authority_preflight_summary,
        "goal_worktree_guard_summary": inputs.goal_worktree_guard_summary,
        "remediation_backlog_summary": inputs.remediation_backlog_summary,
        "learning_signoff_summary": inputs.learning_signoff_summary,
    }
