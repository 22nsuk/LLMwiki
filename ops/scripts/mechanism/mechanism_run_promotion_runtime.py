from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from ops.scripts.observability_artifacts_runtime import (
    write_promotion_decision_trends,
    write_run_artifact_fingerprint,
)
from ops.scripts.policy_runtime import report_path
from ops.scripts.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_event_from_record,
    decision_record_from_report,
)
from ops.scripts.runtime_context import RuntimeContext

from .finalize_run_runtime import finalize_run
from .improvement_observations_runtime import IMPROVEMENT_OBSERVATIONS_FILENAME
from .mechanism_run_common_runtime import (
    CompletedRunSteps,
    ExperimentResolution,
    FinalizeStepResult,
    PromotionStepResult,
    ScaffoldedRun,
    load_json,
    sanitize_payload,
)
from .mechanism_run_ledger_runtime import (
    append_ledger_event,
    run_rel,
    write_experiment_telemetry,
)
from .planning_gate_validate import validate_run_dir
from .promotion_gate import write_report as write_promotion_report
from .promotion_gate_common_runtime import build_log, build_signoff
from .promotion_gate_mechanism_runtime import (
    MechanismGateInputs,
    MechanismPromotionReportRequest,
    collect_mechanism_gate_inputs,
    mechanism_class_report as build_mechanism_class_report,
)


@dataclass(frozen=True)
class _MechanismRunPromotionReportRequest:
    run_id: str
    policy: dict
    resolved_policy_path: Path
    primary_targets: list[str]
    supporting_targets: list[str]
    log_summary: str
    require_signoff: bool
    signoff_status: str | None
    signoff_by: str | None
    signoff_ts: str | None
    changed_files_manifest_path: str
    behavior_delta_path: str | None = None
    auto_improve_run: bool = False
    proposal: dict | None = None


def _build_signoff_and_log(
    policy: dict,
    *,
    require_signoff: bool,
    signoff_status: str | None,
    signoff_by: str | None,
    signoff_ts: str | None,
    log_summary: str,
) -> tuple[dict, dict]:
    args = SimpleNamespace(
        require_signoff=require_signoff,
        signoff_status=signoff_status,
        signoff_by=signoff_by,
        signoff_ts=signoff_ts,
        log_recorded=False,
        log_entry_ref=None,
        log_summary=log_summary,
    )
    signoff = build_signoff(policy, "system_mechanism", args)
    log = build_log(policy, args)
    return signoff, log


def _promotion_report_request(
    request: _MechanismRunPromotionReportRequest | None,
    legacy_fields: dict[str, Any],
) -> _MechanismRunPromotionReportRequest:
    if request is not None:
        if legacy_fields:
            raise TypeError("_build_promotion_report accepts either a request object or legacy keyword fields")
        return request
    return _MechanismRunPromotionReportRequest(**legacy_fields)


def _promotion_gate_inputs(
    vault: Path,
    request: _MechanismRunPromotionReportRequest,
) -> MechanismGateInputs:
    run_id = request.run_id
    return collect_mechanism_gate_inputs(
        vault,
        run_rel(run_id, "baseline-eval.json"),
        run_rel(run_id, "candidate-eval.json"),
        run_rel(run_id, "baseline-lint.json"),
        run_rel(run_id, "candidate-lint.json"),
        run_rel(run_id, "baseline-mechanism-assessment.json"),
        run_rel(run_id, "candidate-mechanism-assessment.json"),
        request.changed_files_manifest_path,
        run_rel(run_id, "run-ledger.json"),
        behavior_delta_path=request.behavior_delta_path,
    )


def _mechanism_class_report_request(
    vault: Path,
    request: _MechanismRunPromotionReportRequest,
    signoff: dict,
    log: dict,
) -> MechanismPromotionReportRequest:
    return MechanismPromotionReportRequest(
        vault=vault,
        run_id=request.run_id,
        policy=request.policy,
        resolved_policy_path=request.resolved_policy_path,
        artifact_class="system_mechanism",
        primary_targets=request.primary_targets,
        supporting_targets=request.supporting_targets,
        signoff=signoff,
        log=log,
        inputs=_promotion_gate_inputs(vault, request),
        auto_improve_run=request.auto_improve_run,
    )


def _proposal_annotated_report(report: dict[str, Any], proposal: dict | None) -> dict[str, Any]:
    if isinstance(proposal, dict):
        report["proposal_id"] = str(proposal.get("proposal_id", "")).strip()
        report["source_candidate_id"] = str(proposal.get("source_candidate_id", "")).strip()
    return report


def _build_promotion_report(
    vault: Path,
    request: _MechanismRunPromotionReportRequest | None = None,
    **legacy_fields: Any,
) -> Path:
    promotion_request = _promotion_report_request(request, legacy_fields)
    signoff, log = _build_signoff_and_log(
        promotion_request.policy,
        require_signoff=promotion_request.require_signoff,
        signoff_status=promotion_request.signoff_status,
        signoff_by=promotion_request.signoff_by,
        signoff_ts=promotion_request.signoff_ts,
        log_summary=promotion_request.log_summary,
    )
    report = build_mechanism_class_report(
        request=_mechanism_class_report_request(vault, promotion_request, signoff, log)
    )
    report = _proposal_annotated_report(report, promotion_request.proposal)
    sanitized_report = cast(dict, sanitize_payload(report, roots=[vault]))
    return write_promotion_report(vault, sanitized_report, run_rel(promotion_request.run_id, "promotion-report.json"))


def _evaluate_promotion_step(
    vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    changed_files_manifest: str,
    behavior_delta: str | None,
    require_signoff: bool,
    signoff_status: str | None,
    signoff_by: str | None,
    signoff_ts: str | None,
) -> PromotionStepResult:
    promotion_kwargs: dict[str, Any] = {
        "run_id": run_id,
        "policy": resolution.policy,
        "resolved_policy_path": resolution.resolved_policy_path,
        "primary_targets": resolution.primary_targets,
        "supporting_targets": resolution.supporting_targets,
        "log_summary": resolution.log_summary,
        "require_signoff": require_signoff,
        "signoff_status": signoff_status,
        "signoff_by": signoff_by,
        "signoff_ts": signoff_ts,
        "changed_files_manifest_path": changed_files_manifest,
        "behavior_delta_path": behavior_delta,
    }
    if resolution.scope_freeze_path or resolution.routing_report_paths or resolution.executor_report_paths:
        promotion_kwargs["auto_improve_run"] = True
    if resolution.proposal:
        promotion_kwargs["proposal"] = resolution.proposal
    promotion_path = _build_promotion_report(vault, **promotion_kwargs)
    return PromotionStepResult(
        report_path=promotion_path,
        report=load_json(promotion_path),
    )


def _record_promotion_step(
    vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    baseline_artifacts: dict,
    candidate_artifacts: dict,
    changed_files_manifest: str,
    behavior_delta: str | None,
    decision: str,
    decision_record: dict,
) -> None:
    append_ledger_event(
        vault,
        run_id,
        event_type="promotion_evaluated",
        summary=f"Promotion gate returned {decision} for this mechanism run.",
        artifacts=[
            *resolution.primary_targets,
            *resolution.supporting_targets,
            *baseline_artifacts.values(),
            *candidate_artifacts.values(),
            changed_files_manifest,
            *([behavior_delta] if behavior_delta else []),
            run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME),
            run_rel(run_id, "promotion-report.json"),
        ],
        decision=decision,
        context=resolution.context,
        status="ready",
        decision_event=decision_event_from_record(
            decision_record,
            ledger_event_type="promotion_evaluated",
            effective_at=resolution.context.isoformat_z(),
        ),
    )


def _finalize_step(
    vault: Path,
    *,
    run_id: str,
    promotion_report: dict,
    finalize: bool,
    context: RuntimeContext | None = None,
) -> FinalizeStepResult:
    finalized = False
    finalize_result: dict = {}
    try:
        decision_record = decision_record_from_report(promotion_report, require_record=True)
    except PromotionDecisionRegistryError:
        return FinalizeStepResult(finalized=False, finalize_result={})
    if finalize and bool(decision_record.get("finalizable")):
        signoff = promotion_report.get("signoff", {})
        if (not signoff.get("required")) or signoff.get("status") == "approved":
            if context is None:
                finalize_result = finalize_run(vault, run_id)
            else:
                finalize_result = finalize_run(vault, run_id, context=context)
            finalized = True
    return FinalizeStepResult(finalized=finalized, finalize_result=finalize_result)


def _build_completed_run_result(
    vault: Path,
    *,
    run_id: str,
    scaffold: ScaffoldedRun,
    resolution: ExperimentResolution,
    baseline_artifacts: dict,
    candidate_artifacts: dict,
    steps: CompletedRunSteps,
) -> dict:
    planning_gate = validate_run_dir(vault, scaffold.run_dir, context=resolution.context)
    decision_record = decision_record_from_report(steps.promotion.report, require_record=True)
    decision = decision_record["decision"]
    result = {
        "run_id": run_id,
        "run_dir": report_path(vault, scaffold.run_dir),
        "baseline_artifacts": baseline_artifacts,
        "candidate_artifacts": candidate_artifacts,
        "improvement_observations": run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME),
        "scope_freeze": resolution.scope_freeze_path,
        "routing_reports": resolution.routing_report_paths,
        "executor_reports": resolution.executor_report_paths,
        "changed_files_manifest": steps.repo_health.changed_files_manifest,
        "structural_complexity_budget": steps.repo_health.structural_complexity_budget,
        "behavior_delta": steps.repo_health.behavior_delta,
        "workspace_preparation": steps.workspace_preparation,
        "post_mutation_generated_artifact_convergence": (
            steps.generated_artifact_convergence
        ),
        "apply_mode": steps.workspace_apply.apply_mode,
        "apply_status": steps.workspace_apply.apply_status,
        "live_applied": steps.workspace_apply.live_applied,
        "shadow_apply_report": steps.workspace_apply.shadow_apply_report,
        "rollback_rehearsal_report": steps.workspace_apply.rollback_rehearsal_report,
        "mutation_command": {
            "returncode": steps.mutation_step.result["returncode"],
            "timed_out": bool(steps.mutation_step.result.get("timed_out", False)),
            "timeout_seconds": steps.mutation_step.result.get("timeout_seconds", 0),
            "termination_reason": steps.mutation_step.result.get("termination_reason", ""),
            "stdout": run_rel(run_id, "mutation-command.stdout.txt"),
            "stderr": run_rel(run_id, "mutation-command.stderr.txt"),
        },
        "repo_health": {
            "passed": steps.repo_health.passed,
            "returncode": steps.repo_health.result["returncode"],
            "timed_out": bool(steps.repo_health.result.get("timed_out", False)),
            "timeout_seconds": steps.repo_health.result.get("timeout_seconds", 0),
            "termination_reason": steps.repo_health.result.get("termination_reason", ""),
            "structural_complexity_budget_status": (
                steps.repo_health.structural_complexity_budget_status
            ),
            "stdout": run_rel(run_id, "repo-health.stdout.txt"),
            "stderr": run_rel(run_id, "repo-health.stderr.txt"),
        },
        "promotion_report": run_rel(run_id, "promotion-report.json"),
        "decision": decision,
        "decision_record": decision_record,
        "finalized": steps.finalize_step.finalized,
        "finalize_result": steps.finalize_step.finalize_result,
        "proposal_snapshot": scaffold.proposal_snapshot,
        "planning_gate": {
            "phase": planning_gate["phase"],
            "status": planning_gate["status"],
        },
    }
    write_experiment_telemetry(vault, run_id=run_id, resolution=resolution, result=result)
    result["run_artifact_fingerprint"] = write_run_artifact_fingerprint(
        vault,
        run_id,
        context=resolution.context,
    )
    result["promotion_decision_trends"] = write_promotion_decision_trends(
        vault,
        resolution.policy,
        resolution.resolved_policy_path,
        context=resolution.context,
    )
    return result
