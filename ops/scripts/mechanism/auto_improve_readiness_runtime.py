from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    read_json_object,
    write_schema_backed_report,
)
from ops.scripts.artifact_freshness_runtime import (
    build_canonical_report_envelope,
    canonical_report_loading_issue,
)
from ops.scripts.learning_readiness_vocabulary import EXECUTION_NO_RUNNABLE_PROPOSAL_BLOCKER_ID
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH

from .auto_improve_readiness_constants_runtime import (
    AUTO_IMPROVE_LOOP_COMMAND,
    ARTIFACT_FRESHNESS_REPORT_REL_PATH,
    FALLBACK_PRIMARY_TARGETS,
    FALLBACK_SUPPORTING_TARGETS,
    FALLBACK_TEST_FILES,
    MECHANISM_REVIEW_REPORT_REL_PATH,
    MUTATION_PROPOSAL_REPORT_REL_PATH,
    OUTCOME_METRICS_REPORT_REL_PATH,
    READINESS_REPORT_PRODUCER,
    READINESS_REPORT_REL_PATH,
    READINESS_REPORT_SOURCE_COMMAND,
    READINESS_SOURCE_PATHS,
    READINESS_TARGET,
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
from .auto_improve_readiness_learning_runtime import (
    LearningReadinessAssessment,
    _build_loop_health_summary,
    _learning_readiness_assessment,
    _learning_release_blockers,
)
from .auto_improve_readiness_queue_runtime import (
    _blocked_proposal_count,
    _blocked_proposal_ids_by_reason,
    _blocked_reason_counts,
    _checks,
    _fallback_history_requirement,
    _fallback_status,
    _matching_fallback_seed_runs,
    _readiness_next_action,
    _readiness_queue,
    _readiness_remediations,
    _runnable_proposal_ids,
    _same_eval_telemetry_summary,
)
from .auto_improve_readiness_release_authority_runtime import (
    _artifact_contract_promotion_blockers,
    _dict_field,
    _release_authority_preflight_promotion_blockers,
    _release_gate_promotion_blockers,
    _release_gate_summaries,
)


READINESS_REPORT_SCHEMA_PATH = AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH


@dataclass(frozen=True)
class ReadinessInputs:
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    active_outcome_metrics: dict[str, Any]
    active_mechanism_review: dict[str, Any]
    active_mutation_proposal: dict[str, Any]
    active_artifact_freshness: dict[str, Any]
    active_selected_contract_summary: dict[str, Any]
    active_source_package_summary: dict[str, Any]
    active_release_closeout_summary: dict[str, Any]
    active_release_closeout_batch_manifest: dict[str, Any]
    active_release_closeout_finality: dict[str, Any]
    active_release_evidence_cohort: dict[str, Any]
    active_artifact_finalization: dict[str, Any]
    active_release_authority_preflight: dict[str, Any]
    artifact_freshness_summary: dict[str, Any]
    selected_contract_summary: dict[str, Any]
    source_package_clean_extract_summary: dict[str, Any]
    release_closeout_summary: dict[str, Any]
    release_closeout_batch_manifest_summary: dict[str, Any]
    release_closeout_finality_summary: dict[str, Any]
    release_evidence_cohort_summary: dict[str, Any]
    artifact_finalization_summary: dict[str, Any]
    release_authority_preflight_summary: dict[str, Any]
    loop_health_summary: dict[str, Any]
    same_eval_telemetry_summary: dict[str, Any]
    reports_present: bool
    outcome_summary: dict[str, Any]
    review_summary: dict[str, Any]
    proposal_summary: dict[str, Any]
    proposal_diagnostics: dict[str, Any]
    queue_evidence_gaps: list[str]
    proposals_emitted: int
    runnable_proposal_ids: list[str]
    blocked_proposal_count: int
    blocked_reason_counts: dict[str, int]
    blocked_proposal_ids: dict[str, list[str]]
    blocked_reasons: list[str]
    queue_ready: bool
    seed_runs: list[str]
    history_requirement: int
    additional_runs_needed: int


@dataclass(frozen=True)
class ExecutionReadinessAssessment:
    status: str
    gate_effect: str
    can_run: bool
    reasons: list[str]
    runnable_proposal_count: int
    blocked_proposal_count: int
    recommended_next_step: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "gate_effect": self.gate_effect,
            "can_run": self.can_run,
            "reasons": self.reasons,
            "runnable_proposal_count": self.runnable_proposal_count,
            "blocked_proposal_count": self.blocked_proposal_count,
            "recommended_next_step": self.recommended_next_step,
        }


def readiness_can_run(report: dict[str, Any]) -> bool:
    execution = report.get("execution_readiness")
    return bool(isinstance(execution, dict) and execution.get("can_run", False))


def readiness_exit_code(report: dict[str, Any]) -> int:
    return 0 if readiness_can_run(report) else 1


def learning_review_required(report: dict[str, Any]) -> bool:
    learning = report.get("learning_readiness")
    return bool(isinstance(learning, dict) and learning.get("gate_effect") == "review_required")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json_object(path)
    if canonical_report_loading_issue(path, payload):
        return {}
    return payload


def _load_selected_contract_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json_object(path)
    loading_issue = canonical_report_loading_issue(path, payload)
    if loading_issue and not loading_issue.startswith("currentness_status="):
        return {}
    return payload


def _load_optional_json(path: Path) -> dict[str, Any]:
    return load_optional_json_object(path)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _upstream_attention_summaries(
    *,
    review_report: dict[str, Any],
    proposal_report: dict[str, Any],
    review_summary: dict[str, Any],
    proposal_summary: dict[str, Any],
) -> list[str]:
    summaries: list[str] = []

    review_status = str(review_report.get("status", "")).strip()
    review_bootstrap = review_report.get("diagnostics", {}).get("bootstrap", {})
    if review_status == "attention":
        bootstrap_status = str(review_bootstrap.get("status", "")).strip()
        candidates_emitted = int(review_summary.get("candidates_emitted", 0) or 0)
        detail = bootstrap_status or "attention"
        summaries.append(
            f"mechanism_review.status=attention ({detail}; candidates_emitted={candidates_emitted})"
        )

    proposal_status = str(proposal_report.get("status", "")).strip()
    if proposal_status == "attention":
        proposals_emitted = int(proposal_summary.get("proposals_emitted", 0) or 0)
        queue_pressure_summary = str(proposal_summary.get("queue_pressure_summary", "")).strip()
        detail = queue_pressure_summary or "attention"
        summaries.append(
            f"mutation_proposal.status=attention ({detail}; proposals_emitted={proposals_emitted})"
        )

    return summaries


def _load_readiness_report_payloads(
    vault: Path,
    *,
    outcome_metrics_report: dict[str, Any] | None,
    mechanism_review_report: dict[str, Any] | None,
    mutation_proposal_report: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    return {
        "outcome_metrics": (
            outcome_metrics_report
            if isinstance(outcome_metrics_report, dict)
            else _load_json(vault / OUTCOME_METRICS_REPORT_REL_PATH)
        ),
        "mechanism_review": (
            mechanism_review_report
            if isinstance(mechanism_review_report, dict)
            else _load_json(vault / MECHANISM_REVIEW_REPORT_REL_PATH)
        ),
        "mutation_proposal": (
            mutation_proposal_report
            if isinstance(mutation_proposal_report, dict)
            else _load_json(vault / MUTATION_PROPOSAL_REPORT_REL_PATH)
        ),
        "artifact_freshness": _load_json(vault / ARTIFACT_FRESHNESS_REPORT_REL_PATH),
        "selected_contract": _load_selected_contract_json(
            vault / SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH
        ),
        "source_package": _load_json(vault / SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH),
        "release_closeout": _load_json(vault / RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH),
        "release_batch_manifest": _load_json(vault / RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH),
        "release_finality": _load_json(vault / RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH),
        "release_evidence_cohort": _load_json(vault / RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH),
        "artifact_finalization": _load_json(vault / RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH),
        "release_authority_preflight": _load_optional_json(
            vault / RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH
        ),
    }


def _queue_evidence_gaps(
    *,
    review_report: dict[str, Any],
    proposal_report: dict[str, Any],
    review_summary: dict[str, Any],
    proposal_summary: dict[str, Any],
    proposal_diagnostics: dict[str, Any],
    proposals_emitted: int,
    queue_ready: bool,
    blocked_reasons: list[str],
) -> list[str]:
    evidence_gaps = [
        *_upstream_attention_summaries(
            review_report=review_report,
            proposal_report=proposal_report,
            review_summary=review_summary,
            proposal_summary=proposal_summary,
        ),
        *_string_list(proposal_diagnostics.get("evidence_gaps", [])),
    ]
    if proposals_emitted <= 0 or queue_ready:
        return evidence_gaps
    blocked_detail = (
        f"proposal blockers active: {', '.join(blocked_reasons)}"
        if blocked_reasons
        else "all emitted proposals are currently blocked"
    )
    return [*evidence_gaps, blocked_detail]


def load_readiness_inputs(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    outcome_metrics_report: dict[str, Any] | None = None,
    mechanism_review_report: dict[str, Any] | None = None,
    mutation_proposal_report: dict[str, Any] | None = None,
) -> ReadinessInputs:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    reports = _load_readiness_report_payloads(
        vault,
        outcome_metrics_report=outcome_metrics_report,
        mechanism_review_report=mechanism_review_report,
        mutation_proposal_report=mutation_proposal_report,
    )
    release_summaries = _release_gate_summaries(reports)

    reports_present = all(
        bool(report)
        for report in (
            reports["outcome_metrics"],
            reports["mechanism_review"],
            reports["mutation_proposal"],
        )
    )
    outcome_summary = _dict_field(reports["outcome_metrics"], "summary")
    review_summary = _dict_field(reports["mechanism_review"], "summary")
    proposal_summary = _dict_field(reports["mutation_proposal"], "summary")
    proposal_diagnostics = _dict_field(reports["mutation_proposal"], "diagnostics")
    loop_health_summary = _build_loop_health_summary(vault)
    same_eval_telemetry_summary = _same_eval_telemetry_summary(vault, reports["mutation_proposal"])
    proposals_emitted = int(proposal_summary.get("proposals_emitted", 0) or 0)
    runnable_proposal_ids = _runnable_proposal_ids(reports["mutation_proposal"])
    blocked_proposal_count = _blocked_proposal_count(proposal_summary, proposal_diagnostics)
    blocked_reason_counts = _blocked_reason_counts(reports["mutation_proposal"])
    blocked_proposal_ids = _blocked_proposal_ids_by_reason(reports["mutation_proposal"])
    blocked_reasons = list(blocked_reason_counts)
    queue_ready = bool(runnable_proposal_ids)
    queue_evidence_gaps = _queue_evidence_gaps(
        review_report=reports["mechanism_review"],
        proposal_report=reports["mutation_proposal"],
        review_summary=review_summary,
        proposal_summary=proposal_summary,
        proposal_diagnostics=proposal_diagnostics,
        proposals_emitted=proposals_emitted,
        queue_ready=queue_ready,
        blocked_reasons=blocked_reasons,
    )
    seed_runs = _matching_fallback_seed_runs(vault)
    history_requirement, additional_runs_needed = _fallback_history_requirement(reports["mechanism_review"])
    return ReadinessInputs(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_context=runtime_context,
        active_outcome_metrics=reports["outcome_metrics"],
        active_mechanism_review=reports["mechanism_review"],
        active_mutation_proposal=reports["mutation_proposal"],
        active_artifact_freshness=reports["artifact_freshness"],
        active_selected_contract_summary=reports["selected_contract"],
        active_source_package_summary=reports["source_package"],
        active_release_closeout_summary=reports["release_closeout"],
        active_release_closeout_batch_manifest=reports["release_batch_manifest"],
        active_release_closeout_finality=reports["release_finality"],
        active_release_evidence_cohort=reports["release_evidence_cohort"],
        active_artifact_finalization=reports["artifact_finalization"],
        active_release_authority_preflight=reports["release_authority_preflight"],
        artifact_freshness_summary=release_summaries["artifact_freshness"],
        selected_contract_summary=release_summaries["selected_contract"],
        source_package_clean_extract_summary=release_summaries["source_package"],
        release_closeout_summary=release_summaries["release_closeout"],
        release_closeout_batch_manifest_summary=release_summaries["release_batch_manifest"],
        release_closeout_finality_summary=release_summaries["release_finality"],
        release_evidence_cohort_summary=release_summaries["release_evidence_cohort"],
        artifact_finalization_summary=release_summaries["artifact_finalization"],
        release_authority_preflight_summary=release_summaries[
            "release_authority_preflight"
        ],
        loop_health_summary=loop_health_summary,
        same_eval_telemetry_summary=same_eval_telemetry_summary,
        reports_present=reports_present,
        outcome_summary=outcome_summary,
        review_summary=review_summary,
        proposal_summary=proposal_summary,
        proposal_diagnostics=proposal_diagnostics,
        queue_evidence_gaps=queue_evidence_gaps,
        proposals_emitted=proposals_emitted,
        runnable_proposal_ids=runnable_proposal_ids,
        blocked_proposal_count=blocked_proposal_count,
        blocked_reason_counts=blocked_reason_counts,
        blocked_proposal_ids=blocked_proposal_ids,
        blocked_reasons=blocked_reasons,
        queue_ready=queue_ready,
        seed_runs=seed_runs,
        history_requirement=history_requirement,
        additional_runs_needed=additional_runs_needed,
    )


def assess_execution_readiness(inputs: ReadinessInputs) -> ExecutionReadinessAssessment:
    reasons = [
        "runnable proposal queue is non-empty"
        if inputs.queue_ready
        else "no runnable proposal is available"
    ]
    reasons.extend(
        gap
        for gap in inputs.queue_evidence_gaps
        if gap.startswith("mechanism_review.status=attention")
        or gap.startswith("mutation_proposal.status=attention")
    )
    if inputs.proposals_emitted > 0 and not inputs.queue_ready:
        if inputs.blocked_reasons:
            reasons.append(f"proposal blockers active: {', '.join(inputs.blocked_reasons)}")
        else:
            reasons.append("generated proposals exist, but every emitted proposal is currently blocked")
    elif inputs.proposals_emitted == 0 and not inputs.queue_ready:
        reasons.append("mutation proposal generation emitted zero runnable proposals")
    return ExecutionReadinessAssessment(
        status="pass" if inputs.queue_ready else "warn",
        gate_effect="active",
        can_run=inputs.queue_ready,
        reasons=reasons,
        runnable_proposal_count=len(inputs.runnable_proposal_ids),
        blocked_proposal_count=inputs.blocked_proposal_count,
        recommended_next_step=_readiness_next_action(
            queue_ready=inputs.queue_ready,
            proposals_emitted=inputs.proposals_emitted,
            blocked_reasons=inputs.blocked_reasons,
            seed_runs=inputs.seed_runs,
        ),
    )


def assess_learning_readiness(inputs: ReadinessInputs) -> LearningReadinessAssessment:
    return _learning_readiness_assessment(
        queue_ready=inputs.queue_ready,
        reports_present=inputs.reports_present,
        outcome_summary=inputs.outcome_summary,
        active_outcome_metrics=inputs.active_outcome_metrics,
        active_mechanism_review=inputs.active_mechanism_review,
        loop_health_summary=inputs.loop_health_summary,
        same_eval_telemetry_summary=inputs.same_eval_telemetry_summary,
        policy=inputs.policy,
    )


def _top_level_next_action(
    execution: ExecutionReadinessAssessment,
    learning: LearningReadinessAssessment,
    promotion_blockers: list[dict[str, Any]],
) -> str:
    if not execution.can_run:
        return execution.recommended_next_step
    if not learning.likely_to_learn:
        return learning.recommended_next_step
    if promotion_blockers:
        blocker_next_step = ""
        for blocker in promotion_blockers:
            candidate = str(blocker.get("recommended_next_step", "")).strip()
            if candidate:
                blocker_next_step = candidate
                break
        if blocker_next_step:
            return (
                "Trial only; do not promote. "
                f"{execution.recommended_next_step} "
                f"Promotion remains blocked until: {blocker_next_step}"
            )
        return (
            "Trial only; do not promote. "
            f"{execution.recommended_next_step} "
            "Clear promotion_blockers and rerun `make auto-improve-readiness` before promotion."
        )
    return execution.recommended_next_step


def _execution_blockers(execution: ExecutionReadinessAssessment) -> list[dict[str, Any]]:
    if execution.can_run:
        return []
    return [
        {
            "id": EXECUTION_NO_RUNNABLE_PROPOSAL_BLOCKER_ID,
            "scope": "execution_readiness",
            "status": "open",
            "severity": "blocker",
            "release_blocker": True,
            "accepted_risk": False,
            "gate_effect": execution.gate_effect,
            "source_status": execution.status,
            "reason": "; ".join(execution.reasons),
            "signal_ids": [],
            "required_evidence": [
                "execution_readiness.can_run must be true before an auto-improve trial can execute",
                "refresh generated proposal queue evidence or seed a runnable fallback mechanism",
            ],
            "recommended_next_step": execution.recommended_next_step,
        }
    ]


def _readiness_promotion_blockers(
    inputs: ReadinessInputs,
    execution: ExecutionReadinessAssessment,
    learning: LearningReadinessAssessment,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    learning_blockers = [blocker.to_wire() for blocker in _learning_release_blockers(learning)]
    promotion_blockers = [
        *_execution_blockers(execution),
        *learning_blockers,
        *_release_gate_promotion_blockers(
            inputs.selected_contract_summary,
            inputs.source_package_clean_extract_summary,
            inputs.release_closeout_summary,
            inputs.release_closeout_batch_manifest_summary,
            inputs.release_closeout_finality_summary,
            inputs.release_evidence_cohort_summary,
            inputs.artifact_finalization_summary,
        ),
        *_release_authority_preflight_promotion_blockers(
            inputs.release_authority_preflight_summary,
        ),
        *_artifact_contract_promotion_blockers(
            inputs.artifact_freshness_summary,
            inputs.active_artifact_freshness,
        ),
    ]
    return learning_blockers, promotion_blockers


def _readiness_inputs_payload() -> dict[str, str]:
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
    }


def _readiness_diagnostics_payload(inputs: ReadinessInputs) -> dict[str, Any]:
    return {
        "loop_health_summary": inputs.loop_health_summary,
        "same_eval_telemetry_summary": inputs.same_eval_telemetry_summary,
        "artifact_freshness_summary": inputs.artifact_freshness_summary,
        "selected_contract_summary": inputs.selected_contract_summary,
        "source_package_clean_extract_summary": inputs.source_package_clean_extract_summary,
        "release_closeout_summary": inputs.release_closeout_summary,
        "release_closeout_batch_manifest_summary": inputs.release_closeout_batch_manifest_summary,
        "release_closeout_finality_summary": inputs.release_closeout_finality_summary,
        "release_evidence_cohort_summary": inputs.release_evidence_cohort_summary,
        "artifact_finalization_summary": inputs.artifact_finalization_summary,
        "release_authority_preflight_summary": inputs.release_authority_preflight_summary,
    }


def _readiness_fallback_payload(inputs: ReadinessInputs, fallback_status: str) -> dict[str, Any]:
    return {
        "status": fallback_status,
        "primary_targets": FALLBACK_PRIMARY_TARGETS,
        "supporting_targets": FALLBACK_SUPPORTING_TARGETS,
        "test_files": FALLBACK_TEST_FILES,
        "seed_run_count": len(inputs.seed_runs),
        "seed_runs": inputs.seed_runs,
        "history_requirement": inputs.history_requirement,
        "additional_runs_needed": inputs.additional_runs_needed,
        "queue_recheck_target": READINESS_TARGET,
        "auto_improve_command": AUTO_IMPROVE_LOOP_COMMAND,
    }


def render_readiness_report(
    vault: Path,
    inputs: ReadinessInputs,
    *,
    execution: ExecutionReadinessAssessment,
    learning: LearningReadinessAssessment,
) -> dict[str, Any]:
    generated_at = inputs.runtime_context.isoformat_z()
    checks = _checks(
        reports_present=inputs.reports_present,
        proposals_emitted=inputs.proposals_emitted,
        runnable_proposal_count=len(inputs.runnable_proposal_ids),
        session_reports_considered=int(inputs.outcome_summary.get("session_reports_considered", 0) or 0),
        seed_runs=inputs.seed_runs,
        history_requirement=inputs.history_requirement,
    )
    remediations = _readiness_remediations(
        reports_present=inputs.reports_present,
        proposals_emitted=inputs.proposals_emitted,
        runnable_proposal_count=len(inputs.runnable_proposal_ids),
        blocked_reason_counts=inputs.blocked_reason_counts,
        blocked_proposal_ids=inputs.blocked_proposal_ids,
        seed_runs=inputs.seed_runs,
        history_requirement=inputs.history_requirement,
    )
    queue = _readiness_queue(
        queue_ready=inputs.queue_ready,
        proposals_emitted=inputs.proposals_emitted,
        runnable_proposal_ids=inputs.runnable_proposal_ids,
        blocked_proposal_count=inputs.blocked_proposal_count,
        blocked_reason_counts=inputs.blocked_reason_counts,
        proposal_summary=inputs.proposal_summary,
        review_summary=inputs.review_summary,
        outcome_summary=inputs.outcome_summary,
        mechanism_review_report=inputs.active_mechanism_review,
        evidence_gaps=inputs.queue_evidence_gaps,
    )
    fallback_status = _fallback_status(
        inputs.queue_ready,
        inputs.proposals_emitted,
        inputs.blocked_proposal_count,
        inputs.seed_runs,
    )
    learning_blockers, promotion_blockers = _readiness_promotion_blockers(inputs, execution, learning)
    can_execute_trial = execution.can_run
    can_promote_result = can_execute_trial and not promotion_blockers
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="auto_improve_readiness_report",
            producer=READINESS_REPORT_PRODUCER,
            source_command=READINESS_REPORT_SOURCE_COMMAND,
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=READINESS_REPORT_SCHEMA_PATH,
            source_paths=READINESS_SOURCE_PATHS,
            file_inputs={
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
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, inputs.resolved_policy_path),
            "version": inputs.policy["version"],
        },
        "can_execute_trial": can_execute_trial,
        "can_promote_result": can_promote_result,
        "execution_readiness": execution.to_wire(),
        "learning_readiness": learning.to_wire(),
        "learning_blockers": learning_blockers,
        "promotion_blockers": promotion_blockers,
        "release_blockers": learning_blockers,
        "inputs": _readiness_inputs_payload(),
        "diagnostics": _readiness_diagnostics_payload(inputs),
        "queue": queue.to_wire(),
        "fallback": _readiness_fallback_payload(inputs, fallback_status),
        "checks": checks,
        "remediations": remediations,
        "next_action": _top_level_next_action(execution, learning, promotion_blockers),
    }


def build_readiness_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    outcome_metrics_report: dict[str, Any] | None = None,
    mechanism_review_report: dict[str, Any] | None = None,
    mutation_proposal_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = load_readiness_inputs(
        vault,
        policy_path=policy_path,
        context=context,
        outcome_metrics_report=outcome_metrics_report,
        mechanism_review_report=mechanism_review_report,
        mutation_proposal_report=mutation_proposal_report,
    )
    execution = assess_execution_readiness(inputs)
    learning = assess_learning_readiness(inputs)
    return render_readiness_report(
        vault,
        inputs,
        execution=execution,
        learning=learning,
    )


def write_readiness_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=READINESS_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=READINESS_REPORT_REL_PATH,
            context="auto-improve readiness report schema validation failed",
        )
    )
