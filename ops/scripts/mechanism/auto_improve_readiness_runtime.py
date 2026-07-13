from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_envelope_runtime import artifact_input_fingerprints
from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.core.gate_effect_vocabulary import GATE_EFFECT_OPERATOR_REVIEW_REQUIRED
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH,
)
from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.learning.learning_readiness_signoff_state import (
    learning_readiness_signoff_summary,
)
from ops.scripts.learning.learning_readiness_vocabulary import (
    EXECUTION_NO_RUNNABLE_PROPOSAL_BLOCKER_ID,
)

from .auto_improve_readiness_constants_runtime import (
    READINESS_REPORT_PRODUCER,
    READINESS_REPORT_REL_PATH,
    READINESS_REPORT_SOURCE_COMMAND,
    READINESS_SOURCE_PATHS,
    RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATHS,
    REMEDIATION_BACKLOG_REPORT_REL_PATH,
)
from .auto_improve_readiness_learning_runtime import (
    LearningReadinessAssessment,
    _learning_readiness_assessment,
    learning_claim_blocker_payloads,
)
from .auto_improve_readiness_loader_runtime import load_readiness_report_payloads
from .auto_improve_readiness_payload_runtime import (
    readiness_diagnostics_payload,
    readiness_file_inputs,
    readiness_inputs_payload,
)
from .auto_improve_readiness_queue_runtime import (
    ReadinessQueueState,
    readiness_execution_fields,
    readiness_queue_payloads,
    readiness_queue_state,
)
from .auto_improve_readiness_release_authority_runtime import (
    _artifact_contract_promotion_blockers,
    _release_authority_preflight_promotion_blockers,
    _release_gate_promotion_blockers,
    _release_gate_summaries,
    promotion_readiness_payload,
    promotion_status,
)
from .auto_improve_readiness_remediation_runtime import (
    remediation_backlog_promotion_blockers,
    remediation_backlog_summary,
)
from .auto_improve_readiness_worktree_guard_runtime import (
    _goal_worktree_guard_promotion_blockers,
    _goal_worktree_guard_summary,
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
    active_goal_worktree_guard: dict[str, Any]
    active_remediation_backlog: dict[str, Any]
    active_learning_signoff: dict[str, Any]
    remediation_backlog_path: str
    artifact_freshness_summary: dict[str, Any]
    selected_contract_summary: dict[str, Any]
    source_package_clean_extract_summary: dict[str, Any]
    release_closeout_summary: dict[str, Any]
    release_closeout_batch_manifest_summary: dict[str, Any]
    release_closeout_finality_summary: dict[str, Any]
    release_evidence_cohort_summary: dict[str, Any]
    artifact_finalization_summary: dict[str, Any]
    release_authority_preflight_summary: dict[str, Any]
    goal_worktree_guard_summary: dict[str, Any]
    remediation_backlog_summary: dict[str, Any]
    learning_signoff_summary: dict[str, Any]
    queue_state: ReadinessQueueState
    reports_present: bool


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
    return bool(
        isinstance(learning, dict)
        and learning.get("gate_effect")
        in {GATE_EFFECT_OPERATOR_REVIEW_REQUIRED, "review_required"}
    )


def load_readiness_inputs(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    outcome_metrics_report: dict[str, Any] | None = None,
    mechanism_review_report: dict[str, Any] | None = None,
    mutation_proposal_report: dict[str, Any] | None = None,
    remediation_backlog_path: str = REMEDIATION_BACKLOG_REPORT_REL_PATH,
) -> ReadinessInputs:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    loaded_reports = load_readiness_report_payloads(
        vault,
        outcome_metrics_report=outcome_metrics_report,
        mechanism_review_report=mechanism_review_report,
        mutation_proposal_report=mutation_proposal_report,
        remediation_backlog_path=remediation_backlog_path,
    )
    reports = loaded_reports.reports
    release_summaries = _release_gate_summaries(reports)
    queue_state = readiness_queue_state(vault, reports)

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
        active_goal_worktree_guard=reports["goal_worktree_guard"],
        active_remediation_backlog=reports["remediation_backlog"],
        active_learning_signoff=reports["learning_signoff"],
        remediation_backlog_path=remediation_backlog_path,
        artifact_freshness_summary=release_summaries["artifact_freshness"],
        selected_contract_summary=release_summaries["selected_contract"],
        source_package_clean_extract_summary=release_summaries["source_package"],
        release_closeout_summary=release_summaries["release_closeout"],
        release_closeout_batch_manifest_summary=release_summaries[
            "release_batch_manifest"
        ],
        release_closeout_finality_summary=release_summaries["release_finality"],
        release_evidence_cohort_summary=release_summaries["release_evidence_cohort"],
        artifact_finalization_summary=release_summaries["artifact_finalization"],
        release_authority_preflight_summary=release_summaries[
            "release_authority_preflight"
        ],
        goal_worktree_guard_summary=_goal_worktree_guard_summary(
            reports["goal_worktree_guard"]
        ),
        remediation_backlog_summary=remediation_backlog_summary(
            reports["remediation_backlog"],
            remediation_backlog_path=remediation_backlog_path,
        ),
        learning_signoff_summary=learning_readiness_signoff_summary(
            reports["learning_signoff"],
            generated_at=runtime_context.isoformat_z(),
        ),
        queue_state=queue_state,
        reports_present=loaded_reports.reports_present,
    )


def assess_execution_readiness(inputs: ReadinessInputs) -> ExecutionReadinessAssessment:
    fields = readiness_execution_fields(inputs.queue_state)
    return ExecutionReadinessAssessment(
        status=fields.status,
        gate_effect=fields.gate_effect,
        can_run=fields.can_run,
        reasons=fields.reasons,
        runnable_proposal_count=fields.runnable_proposal_count,
        blocked_proposal_count=fields.blocked_proposal_count,
        recommended_next_step=fields.recommended_next_step,
    )


def assess_learning_readiness(inputs: ReadinessInputs) -> LearningReadinessAssessment:
    queue_state = inputs.queue_state
    return _learning_readiness_assessment(
        queue_ready=queue_state.queue_ready,
        reports_present=inputs.reports_present,
        outcome_summary=queue_state.outcome_summary,
        active_outcome_metrics=inputs.active_outcome_metrics,
        active_mechanism_review=inputs.active_mechanism_review,
        loop_health_summary=queue_state.loop_health_summary,
        same_eval_telemetry_summary=queue_state.same_eval_telemetry_summary,
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


def _execution_blockers(
    execution: ExecutionReadinessAssessment,
) -> list[dict[str, Any]]:
    if execution.can_run:
        return []
    return [
        {
            "id": EXECUTION_NO_RUNNABLE_PROPOSAL_BLOCKER_ID,
            "scope": "execution_readiness",
            "status": "open",
            "severity": "blocker",
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
    learning: LearningReadinessAssessment,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    learning_claim_blockers, learning_promotion_blockers = (
        learning_claim_blocker_payloads(
            learning,
            signoff_active=bool(inputs.learning_signoff_summary.get("active")),
        )
    )
    promotion_blockers = [
        *learning_promotion_blockers,
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
        *_goal_worktree_guard_promotion_blockers(
            inputs.goal_worktree_guard_summary,
        ),
        *remediation_backlog_promotion_blockers(
            inputs.remediation_backlog_summary,
        ),
    ]
    return learning_claim_blockers, promotion_blockers


def _execution_status(execution: ExecutionReadinessAssessment) -> str:
    return "pass" if execution.can_run else "blocked"


def _readiness_path_group_inputs() -> dict[str, list[str]]:
    return {
        "release_authority_preflight_report_candidates": list(
            RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATHS
        )
    }


def readiness_report_currentness_diagnostics(
    vault: Path,
    *,
    policy_path: str | None = None,
    remediation_backlog_path: str = REMEDIATION_BACKLOG_REPORT_REL_PATH,
) -> dict[str, Any]:
    canonical_path = vault / READINESS_REPORT_REL_PATH
    _, resolved_policy_path = load_policy(vault, policy_path)
    current_source_revision = resolve_source_revision(vault).revision
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    current_input_fingerprints = artifact_input_fingerprints(
        vault,
        resolved_policy_path=resolved_policy_path,
        schema_path=READINESS_REPORT_SCHEMA_PATH,
        source_paths=READINESS_SOURCE_PATHS,
        file_inputs=readiness_file_inputs(
            remediation_backlog_path=remediation_backlog_path
        ),
        path_group_inputs=_readiness_path_group_inputs(),
    )

    try:
        payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "fail",
            "current": False,
            "path": report_path(vault, canonical_path),
            "reasons": ["canonical_artifact_unavailable"],
            "load_error": type(exc).__name__,
            "checks": {
                "artifact_kind": False,
                "producer": False,
                "artifact_status": False,
                "currentness_status": False,
                "source_revision": False,
                "source_tree_fingerprint": False,
                "input_fingerprints": False,
            },
            "expected": {
                "source_revision": current_source_revision,
                "source_tree_fingerprint": current_source_tree_fingerprint,
                "input_fingerprints": current_input_fingerprints,
            },
            "observed": {},
        }

    if not isinstance(payload, dict):
        payload = {}
    currentness = payload.get("currentness")
    checks = {
        "artifact_kind": payload.get("artifact_kind")
        == "auto_improve_readiness_report",
        "producer": payload.get("producer") == READINESS_REPORT_PRODUCER,
        "artifact_status": payload.get("artifact_status") == "current",
        "currentness_status": isinstance(currentness, dict)
        and currentness.get("status") == "current",
        "source_revision": payload.get("source_revision") == current_source_revision,
        "source_tree_fingerprint": payload.get("source_tree_fingerprint")
        == current_source_tree_fingerprint,
        "input_fingerprints": payload.get("input_fingerprints")
        == current_input_fingerprints,
    }
    reasons = [f"{name}_mismatch" for name, passed in checks.items() if not passed]
    current = not reasons
    return {
        "status": "pass" if current else "fail",
        "current": current,
        "path": report_path(vault, canonical_path),
        "reasons": reasons,
        "checks": checks,
        "expected": {
            "source_revision": current_source_revision,
            "source_tree_fingerprint": current_source_tree_fingerprint,
            "input_fingerprints": current_input_fingerprints,
        },
        "observed": {
            "artifact_kind": payload.get("artifact_kind"),
            "producer": payload.get("producer"),
            "artifact_status": payload.get("artifact_status"),
            "currentness_status": (
                currentness.get("status") if isinstance(currentness, dict) else None
            ),
            "source_revision": payload.get("source_revision"),
            "source_tree_fingerprint": payload.get("source_tree_fingerprint"),
            "input_fingerprints": payload.get("input_fingerprints"),
        },
    }


def render_readiness_report(
    vault: Path,
    inputs: ReadinessInputs,
    *,
    execution: ExecutionReadinessAssessment,
    learning: LearningReadinessAssessment,
) -> dict[str, Any]:
    generated_at = inputs.runtime_context.isoformat_z()
    queue_payloads = readiness_queue_payloads(
        queue_state=inputs.queue_state,
        reports_present=inputs.reports_present,
        mechanism_review_report=inputs.active_mechanism_review,
    )
    execution_blockers = _execution_blockers(execution)
    learning_claim_blockers, promotion_blockers = _readiness_promotion_blockers(
        inputs,
        learning,
    )
    can_execute_trial = execution.can_run
    can_promote_result = not promotion_blockers
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
            file_inputs=readiness_file_inputs(
                remediation_backlog_path=inputs.remediation_backlog_path
            ),
            path_group_inputs=_readiness_path_group_inputs(),
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, inputs.resolved_policy_path),
            "version": inputs.policy["version"],
        },
        "execution_status": _execution_status(execution),
        "promotion_status": promotion_status(promotion_blockers),
        "can_execute_trial": can_execute_trial,
        "can_promote_result": can_promote_result,
        "execution_readiness": execution.to_wire(),
        "promotion_readiness": promotion_readiness_payload(promotion_blockers),
        "learning_readiness": learning.to_wire(),
        "execution_blockers": execution_blockers,
        "learning_claim_blockers": learning_claim_blockers,
        "promotion_blockers": promotion_blockers,
        "clean_release_blockers": [],
        "inputs": readiness_inputs_payload(
            remediation_backlog_path=inputs.remediation_backlog_path
        ),
        "diagnostics": readiness_diagnostics_payload(inputs),
        "queue": queue_payloads.queue.to_wire(),
        "fallback": queue_payloads.fallback,
        "checks": queue_payloads.checks,
        "remediations": queue_payloads.remediations,
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
    remediation_backlog_path: str = REMEDIATION_BACKLOG_REPORT_REL_PATH,
) -> dict[str, Any]:
    inputs = load_readiness_inputs(
        vault,
        policy_path=policy_path,
        context=context,
        outcome_metrics_report=outcome_metrics_report,
        mechanism_review_report=mechanism_review_report,
        mutation_proposal_report=mutation_proposal_report,
        remediation_backlog_path=remediation_backlog_path,
    )
    execution = assess_execution_readiness(inputs)
    learning = assess_learning_readiness(inputs)
    return render_readiness_report(
        vault,
        inputs,
        execution=execution,
        learning=learning,
    )


def write_readiness_report(
    vault: Path, report: dict[str, Any], out_path: str | None = None
) -> Path:
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
