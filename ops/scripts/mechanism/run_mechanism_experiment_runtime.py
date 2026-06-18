from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.policy_runtime import (
    workspace_preparation_declared_dependencies_from_policy,
    workspace_preparation_mode_from_policy,
)
from ops.scripts.core.promotion_decision_registry_runtime import decision_from_report
from ops.scripts.core.run_id_runtime import reject_template_placeholder_run_id
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    SAME_SESSION_REPAIR_CONTEXT_SCHEMA_PATH,
)

from .mechanism_contract_eval_runtime import (
    MechanismContractEvalRequest,
    write_mechanism_contract_eval_pair,
)
from .mechanism_run_capture_runtime import (
    _capture_baseline_step,
    _capture_candidate_step,
    _capture_reports,
)
from .mechanism_run_common_runtime import (
    CommandStepResult,
    CompletedRunSteps,
    FinalizeStepResult,
    PromotionStepResult,
    RepoHealthStepResult,
    RunMechanismExperimentArtifactError,
    RunMechanismExperimentError,
    RunMechanismExperimentMutationError,
    RunMechanismExperimentPolicyError,
    RunMechanismExperimentUsageError,
    RunMechanismExperimentWriteError,
    WorkspaceApplyResult,
    write_json,
)
from .mechanism_run_ledger_runtime import append_ledger_event, run_rel
from .mechanism_run_promotion_runtime import (
    _build_completed_run_result,
    _build_promotion_report,
    _evaluate_promotion_step,
    _finalize_step,
    _record_promotion_step,
)
from .mechanism_run_scaffold_resolution_runtime import _resolve_experiment_inputs
from .mechanism_run_scaffold_runtime import (
    _build_scaffold_only_result,
    _freeze_seed_scope,
    _scaffold_or_load_run,
)
from .mechanism_run_workspace_runtime import (
    _apply_or_discard_workspace_changes,
    _build_repo_health_blocked_result,
    _execute_mutation_step,
    _prepare_candidate_report_workspace,
    _prepare_workspace_copy,
    _repo_health_failure_taxonomy,
    _repo_health_step,
    _run_command,
    _snapshot_repo_file_digests,
    _write_candidate_changed_files_snapshot,
    _write_changed_files_manifest,
)
from .post_mutation_generated_artifact_convergence_runtime import (
    run_post_mutation_generated_artifact_convergence,
)

SAME_SESSION_REPAIR_CONTEXT_FILENAME = "same-session-repair-context.json"
SAME_SESSION_REPAIR_CONTEXT_SCHEMA = SAME_SESSION_REPAIR_CONTEXT_SCHEMA_PATH
SAME_SESSION_REPAIR_MAX_ATTEMPTS = 1
REPAIRABLE_PARENT_VALIDATION_FAILURES = frozenset(
    {
        "structural_complexity_non_regression",
    }
)

__all__ = [
    "RunMechanismExperimentArtifactError",
    "RunMechanismExperimentError",
    "RunMechanismExperimentMutationError",
    "RunMechanismExperimentPolicyError",
    "RunMechanismExperimentRequest",
    "RunMechanismExperimentUsageError",
    "RunMechanismExperimentWriteError",
    "_apply_or_discard_workspace_changes",
    "_build_promotion_report",
    "_capture_reports",
    "_finalize_step",
    "_repo_health_step",
    "_resolve_experiment_inputs",
    "_run_command",
    "_snapshot_repo_file_digests",
    "_write_changed_files_manifest",
    "run_mechanism_experiment",
]


@dataclass(frozen=True)
class RunMechanismExperimentRequest:
    run_id: str
    policy_path: str | None
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]
    log_summary: str | None
    mutation_command: str | None
    check_command: str | None
    require_signoff: bool
    signoff_status: str | None
    signoff_by: str | None
    signoff_ts: str | None
    finalize: bool
    proposal_id: str | None = None
    proposal_report_path: str | None = None
    scaffold_only: bool = False
    scope_freeze_path: str | None = None
    routing_report_paths: list[str] | None = None
    executor_report_paths: list[str] | None = None
    apply_mode: str | None = None
    context: RuntimeContext | None = None

    @classmethod
    def from_kwargs(cls, kwargs: dict[str, Any]) -> RunMechanismExperimentRequest:
        required_fields = {
            "run_id",
            "policy_path",
            "primary_targets",
            "supporting_targets",
            "test_files",
            "log_summary",
            "mutation_command",
            "check_command",
            "require_signoff",
            "signoff_status",
            "signoff_by",
            "signoff_ts",
            "finalize",
        }
        optional_defaults = {
            "proposal_id": None,
            "proposal_report_path": None,
            "scaffold_only": False,
            "scope_freeze_path": None,
            "routing_report_paths": None,
            "executor_report_paths": None,
            "apply_mode": None,
            "context": None,
        }
        allowed_fields = required_fields | set(optional_defaults)
        unknown_fields = sorted(set(kwargs) - allowed_fields)
        if unknown_fields:
            joined = ", ".join(unknown_fields)
            raise TypeError(f"run_mechanism_experiment got unexpected keyword argument(s): {joined}")
        missing_fields = sorted(field for field in required_fields if field not in kwargs)
        if missing_fields:
            joined = ", ".join(missing_fields)
            raise TypeError(f"run_mechanism_experiment missing required keyword argument(s): {joined}")
        values = {**optional_defaults, **kwargs}
        return cls(**values)


@dataclass(frozen=True)
class _WorkspaceExperimentResult:
    workspace_preparation: dict
    mutation_step: CommandStepResult
    generated_artifact_convergence: dict[str, Any]
    candidate_artifacts: dict
    repo_health: RepoHealthStepResult
    promotion: PromotionStepResult
    finalize_step: FinalizeStepResult
    workspace_apply: WorkspaceApplyResult
    candidate_changed_files_snapshot: str


@dataclass(frozen=True)
class _WorkspaceParentValidationFailure:
    attempt_index: int
    workspace_preparation: dict[str, Any]
    mutation_step: CommandStepResult
    generated_artifact_convergence: dict[str, Any]
    candidate_artifacts: dict[str, Any]
    repo_health: RepoHealthStepResult
    candidate_changed_files_snapshot: str


def _mechanism_temp_dir_parent() -> str | None:
    if os.name == "nt":
        return None
    current = Path(tempfile.gettempdir()).as_posix().lower()
    if current.startswith("/mnt/") and Path("/tmp").is_dir():
        return "/tmp"
    return None


def _mechanism_temporary_directory(prefix: str) -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix, dir=_mechanism_temp_dir_parent())


def run_mechanism_experiment(
    vault: Path,
    request: RunMechanismExperimentRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if request is not None and kwargs:
        raise TypeError("run_mechanism_experiment request cannot be combined with keyword arguments")
    resolved_request = request or RunMechanismExperimentRequest.from_kwargs(kwargs)
    return _run_mechanism_experiment_request(vault, resolved_request)


def _run_mechanism_experiment_request(
    vault: Path,
    request: RunMechanismExperimentRequest,
) -> dict[str, Any]:
    vault = vault.resolve()
    try:
        reject_template_placeholder_run_id(request.run_id)
    except ValueError as exc:
        raise RunMechanismExperimentUsageError(str(exc)) from exc
    resolution = _resolve_experiment_inputs(
        vault,
        run_id=request.run_id,
        policy_path=request.policy_path,
        primary_targets=request.primary_targets,
        supporting_targets=request.supporting_targets,
        test_files=request.test_files,
        log_summary=request.log_summary,
        mutation_command=request.mutation_command,
        check_command=request.check_command,
        proposal_id=request.proposal_id,
        proposal_report_path=request.proposal_report_path,
        scaffold_only=request.scaffold_only,
        scope_freeze_path=request.scope_freeze_path,
        routing_report_paths=request.routing_report_paths,
        executor_report_paths=request.executor_report_paths,
        context=request.context,
    )
    scaffold = _scaffold_or_load_run(
        vault,
        run_id=request.run_id,
        resolution=resolution,
        scaffold_only=request.scaffold_only,
    )

    if request.scaffold_only:
        return _build_scaffold_only_result(
            vault,
            run_id=request.run_id,
            scaffold=scaffold,
            resolution=resolution,
        )

    _freeze_seed_scope(vault, run_id=request.run_id, resolution=resolution)
    baseline_artifacts = _capture_baseline_step(
        vault,
        run_id=request.run_id,
        resolution=resolution,
    )
    result = _run_workspace_experiment_phase(
        vault,
        request=request,
        scaffold=scaffold,
        resolution=resolution,
        baseline_artifacts=baseline_artifacts,
    )
    if isinstance(result, dict):
        return result
    return _build_completed_run_result(
        vault,
        run_id=request.run_id,
        scaffold=scaffold,
        resolution=resolution,
        baseline_artifacts=baseline_artifacts,
        candidate_artifacts=result.candidate_artifacts,
        steps=CompletedRunSteps(
            mutation_step=result.mutation_step,
            generated_artifact_convergence=result.generated_artifact_convergence,
            repo_health=result.repo_health,
            promotion=result.promotion,
                finalize_step=result.finalize_step,
                workspace_apply=result.workspace_apply,
                workspace_preparation=result.workspace_preparation,
                candidate_changed_files_snapshot=result.candidate_changed_files_snapshot,
            ),
        )


def _resolve_apply_mode(
    request: RunMechanismExperimentRequest,
    resolution: Any,
) -> str:
    apply_mode = request.apply_mode or str(
        resolution.policy["auto_improve_policy"].get("apply_mode", "live")
    )
    if apply_mode not in {"canary_only", "live"}:
        raise RunMechanismExperimentUsageError(f"unsupported apply mode: {apply_mode}")
    return apply_mode


def _record_post_mutation_generated_artifact_convergence(
    vault: Path,
    *,
    run_id: str,
    resolution: Any,
    workspace_vault: Path,
) -> dict[str, Any]:
    selected_targets = [*resolution.primary_targets, *resolution.supporting_targets]
    summary = run_post_mutation_generated_artifact_convergence(
        vault,
        workspace_vault,
        run_id=run_id,
        policy_path_text=resolution.policy_path_text,
        selected_targets=selected_targets,
        context=resolution.context,
    )
    append_ledger_event(
        vault,
        run_id,
        event_type="generated_artifact_convergence_checked",
        summary=(
            "Checked post-mutation generated artifact convergence before candidate capture."
        ),
        artifacts=[summary["artifact"], *summary["artifacts"]],
        decision=summary["status"],
        context=resolution.context,
    )
    return summary


def _capture_candidate_artifacts_from_workspace(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    workspace_vault: Path,
    workspace: Any,
) -> dict[str, Any]:
    with _mechanism_temporary_directory(
        prefix=f"{request.run_id}-candidate-report-workspace-"
    ) as candidate_report_workspace_root:
        candidate_report_vault = _prepare_candidate_report_workspace(
            vault,
            workspace_vault,
            run_id=request.run_id,
            workspace_root=candidate_report_workspace_root,
            baseline_file_digests=workspace.baseline_file_digests,
            diff_model=str(workspace.telemetry.get("diff_model", "full_workspace")),
        )
        return _capture_candidate_step(
            vault,
            workspace_vault,
            run_id=request.run_id,
            resolution=resolution,
            report_source_vault=candidate_report_vault,
        )


def _promotion_workspace_phase_result(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    baseline_artifacts: dict[str, Any],
    candidate_artifacts: dict[str, Any],
    workspace_vault: Path,
    workspace_preparation: dict[str, Any],
    mutation_step: CommandStepResult,
    generated_artifact_convergence: dict[str, Any],
    repo_health: RepoHealthStepResult,
) -> _WorkspaceExperimentResult:
    contract_eval_artifacts = _write_mechanism_contract_eval_artifacts(
        vault,
        request=request,
        resolution=resolution,
        repo_health=repo_health,
    )
    baseline_artifacts = {
        **baseline_artifacts,
        "mechanism_contract_eval": contract_eval_artifacts["baseline"],
    }
    candidate_artifacts = {
        **candidate_artifacts,
        "mechanism_contract_eval": contract_eval_artifacts["candidate"],
    }
    promotion = _evaluate_promotion_step(
        vault,
        run_id=request.run_id,
        resolution=resolution,
        changed_files_manifest=repo_health.changed_files_manifest,
        behavior_delta=repo_health.behavior_delta,
        require_signoff=request.require_signoff,
        signoff_status=request.signoff_status,
        signoff_by=request.signoff_by,
        signoff_ts=request.signoff_ts,
    )
    canonical_decision = decision_from_report(promotion.report, require_record=True)
    workspace_apply = _apply_or_discard_workspace_changes(
        vault,
        workspace_vault,
        run_id=request.run_id,
        context=resolution.context,
        decision=canonical_decision,
        changed_files_manifest=repo_health.changed_files_manifest,
        allowed_apply_roots=resolution.policy["auto_improve_policy"]["allowed_apply_roots"],
        apply_mode=_resolve_apply_mode(request, resolution),
    )
    candidate_changed_files_snapshot = ""
    if canonical_decision in {"HOLD", "DISCARD"} and not workspace_apply.live_applied:
        candidate_changed_files_snapshot = _write_candidate_changed_files_snapshot(
            vault,
            workspace_vault,
            run_id=request.run_id,
            context=resolution.context,
            changed_files_manifest=repo_health.changed_files_manifest,
            decision=canonical_decision,
            apply_mode=workspace_apply.apply_mode,
            apply_status=workspace_apply.apply_status,
            live_applied=workspace_apply.live_applied,
            capture_reason="non_promoted_decision",
        )
    _record_promotion_step(
        vault,
        run_id=request.run_id,
        resolution=resolution,
        baseline_artifacts=baseline_artifacts,
        candidate_artifacts=candidate_artifacts,
        changed_files_manifest=repo_health.changed_files_manifest,
        behavior_delta=repo_health.behavior_delta,
        decision=canonical_decision,
        decision_record=promotion.report["decision_record"],
        candidate_changed_files_snapshot=candidate_changed_files_snapshot,
    )
    finalize_step = _finalize_step(
        vault,
        run_id=request.run_id,
        promotion_report=promotion.report,
        finalize=request.finalize and workspace_apply.live_applied,
        context=resolution.context,
    )
    return _WorkspaceExperimentResult(
        workspace_preparation=workspace_preparation,
        mutation_step=mutation_step,
        generated_artifact_convergence=generated_artifact_convergence,
        candidate_artifacts=candidate_artifacts,
        repo_health=repo_health,
        promotion=promotion,
        finalize_step=finalize_step,
        workspace_apply=workspace_apply,
        candidate_changed_files_snapshot=candidate_changed_files_snapshot,
    )


def _write_mechanism_contract_eval_artifacts(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    repo_health: RepoHealthStepResult,
) -> dict[str, str]:
    contract_eval_request = MechanismContractEvalRequest(
        vault=vault,
        run_id=request.run_id,
        policy=resolution.policy,
        resolved_policy_path=resolution.resolved_policy_path,
        policy_path_text=resolution.policy_path_text,
        changed_files_manifest_path=repo_health.changed_files_manifest,
        behavior_delta_path=repo_health.behavior_delta,
        context=resolution.context,
    )
    return write_mechanism_contract_eval_pair(contract_eval_request)


def _same_session_repair_context_rel(run_id: str) -> str:
    return run_rel(run_id, SAME_SESSION_REPAIR_CONTEXT_FILENAME)


def _copy_repair_context_into_workspace(vault: Path, workspace_vault: Path, *, run_id: str) -> None:
    rel_path = _same_session_repair_context_rel(run_id)
    source = vault / rel_path
    if not source.is_file():
        return
    destination = workspace_vault / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _attempt_artifact_rel(run_id: str, attempt_index: int, rel_path: str) -> str:
    return f"runs/{run_id}/attempts/{attempt_index}/{Path(rel_path).name}"


def _copy_attempt_artifact(
    vault: Path,
    *,
    run_id: str,
    attempt_index: int,
    rel_path: str,
) -> str:
    if not rel_path:
        return ""
    source = vault / rel_path
    if not source.is_file():
        return rel_path
    destination_rel = _attempt_artifact_rel(run_id, attempt_index, rel_path)
    destination = vault / destination_rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination_rel


def _preserve_parent_failure_artifacts(
    vault: Path,
    *,
    run_id: str,
    failure: _WorkspaceParentValidationFailure,
) -> dict[str, Any]:
    attempt_index = failure.attempt_index
    generated_artifact_convergence = str(
        failure.generated_artifact_convergence.get("artifact", "")
    ).strip()
    return {
        "changed_files_manifest": _copy_attempt_artifact(
            vault,
            run_id=run_id,
            attempt_index=attempt_index,
            rel_path=failure.repo_health.changed_files_manifest,
        ),
        "structural_complexity_budget": _copy_attempt_artifact(
            vault,
            run_id=run_id,
            attempt_index=attempt_index,
            rel_path=failure.repo_health.structural_complexity_budget,
        ),
        "behavior_delta": _copy_attempt_artifact(
            vault,
            run_id=run_id,
            attempt_index=attempt_index,
            rel_path=failure.repo_health.behavior_delta,
        ),
        "candidate_changed_files_snapshot": _copy_attempt_artifact(
            vault,
            run_id=run_id,
            attempt_index=attempt_index,
            rel_path=failure.candidate_changed_files_snapshot,
        ),
        "generated_artifact_convergence": _copy_attempt_artifact(
            vault,
            run_id=run_id,
            attempt_index=attempt_index,
            rel_path=generated_artifact_convergence,
        ),
        "mutation_logs": [
            copied
            for rel_path in failure.mutation_step.logs
            if (
                copied := _copy_attempt_artifact(
                    vault,
                    run_id=run_id,
                    attempt_index=attempt_index,
                    rel_path=rel_path,
                )
            )
        ],
        "repo_health_logs": [
            copied
            for rel_path in failure.repo_health.logs
            if (
                copied := _copy_attempt_artifact(
                    vault,
                    run_id=run_id,
                    attempt_index=attempt_index,
                    rel_path=rel_path,
                )
            )
        ],
    }


def _same_session_repair_allowed(
    failure: _WorkspaceParentValidationFailure,
    *,
    repair_attempts_used: int,
) -> bool:
    repo_health = failure.repo_health
    return (
        repair_attempts_used < SAME_SESSION_REPAIR_MAX_ATTEMPTS
        and _repo_health_failure_taxonomy(repo_health) in REPAIRABLE_PARENT_VALIDATION_FAILURES
        and repo_health.result["returncode"] == 0
        and not bool(repo_health.result.get("timed_out", False))
    )


def _write_same_session_repair_context(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    failure: _WorkspaceParentValidationFailure,
    repair_attempt_index: int,
) -> tuple[str, dict[str, Any]]:
    preserved = _preserve_parent_failure_artifacts(
        vault,
        run_id=request.run_id,
        failure=failure,
    )
    repo_health = failure.repo_health
    failure_taxonomy = _repo_health_failure_taxonomy(repo_health)
    payload = {
        "$schema": SAME_SESSION_REPAIR_CONTEXT_SCHEMA,
        "run_id": request.run_id,
        "generated_at": resolution.context.isoformat_z(),
        "artifact_kind": "same_session_repair_context",
        "schema_version": 1,
        "status": "scheduled",
        "trigger": "parent_validation_failure",
        "repair_model": "same_session_bounded_full_chain",
        "repair_attempt_index": repair_attempt_index,
        "max_repair_attempts": SAME_SESSION_REPAIR_MAX_ATTEMPTS,
        "failure_taxonomy": failure_taxonomy,
        "previous_attempt": {
            "attempt_index": failure.attempt_index,
            "repo_health": {
                "returncode": repo_health.result["returncode"],
                "timed_out": bool(repo_health.result.get("timed_out", False)),
                "termination_reason": str(repo_health.result.get("termination_reason", "")),
                "structural_complexity_budget_status": (
                    repo_health.structural_complexity_budget_status
                ),
                "failure_taxonomy": failure_taxonomy,
            },
            "artifacts": preserved,
        },
        "instructions": [
            "Use the previous attempt evidence to repair the candidate inside the same run session.",
            "Rerun the full executor responsibility chain; do not treat this as a worker-only retry.",
            "Keep the repair narrowly focused on the parent validation blocker before adding new behavior.",
        ],
    }
    rel_path = _same_session_repair_context_rel(request.run_id)
    write_json(vault, rel_path, payload, SAME_SESSION_REPAIR_CONTEXT_SCHEMA)
    return rel_path, preserved


def _record_same_session_repair_scheduled(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    repair_context: str,
    preserved_artifacts: dict[str, Any],
) -> None:
    previous_artifacts = [
        str(preserved_artifacts.get("changed_files_manifest", "")).strip(),
        str(preserved_artifacts.get("structural_complexity_budget", "")).strip(),
        str(preserved_artifacts.get("behavior_delta", "")).strip(),
        str(preserved_artifacts.get("candidate_changed_files_snapshot", "")).strip(),
        str(preserved_artifacts.get("generated_artifact_convergence", "")).strip(),
        *[str(item).strip() for item in preserved_artifacts.get("mutation_logs", [])],
        *[str(item).strip() for item in preserved_artifacts.get("repo_health_logs", [])],
    ]
    append_ledger_event(
        vault,
        request.run_id,
        event_type="same_session_repair_attempt_scheduled",
        summary=(
            "Parent validation blocked the candidate; scheduled one bounded "
            "same-session repair attempt with preserved failure evidence."
        ),
        artifacts=[repair_context, *[item for item in previous_artifacts if item]],
        decision="same_session_repair_scheduled",
        context=resolution.context,
        status="running",
    )


def _workspace_parent_validation_failure(
    vault: Path,
    workspace_vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    attempt_index: int,
    workspace_preparation: dict[str, Any],
    mutation_step: CommandStepResult,
    generated_artifact_convergence: dict[str, Any],
    candidate_artifacts: dict[str, Any],
    repo_health: RepoHealthStepResult,
) -> _WorkspaceParentValidationFailure:
    candidate_changed_files_snapshot = _write_candidate_changed_files_snapshot(
        vault,
        workspace_vault,
        run_id=request.run_id,
        context=resolution.context,
        changed_files_manifest=repo_health.changed_files_manifest,
        decision="SKIPPED",
        apply_mode=_resolve_apply_mode(request, resolution),
        apply_status="not_applicable",
        live_applied=False,
        capture_reason=_repo_health_failure_taxonomy(repo_health),
    )
    return _WorkspaceParentValidationFailure(
        attempt_index=attempt_index,
        workspace_preparation=workspace_preparation,
        mutation_step=mutation_step,
        generated_artifact_convergence=generated_artifact_convergence,
        candidate_artifacts=candidate_artifacts,
        repo_health=repo_health,
        candidate_changed_files_snapshot=candidate_changed_files_snapshot,
    )


def _repo_health_blocked_result_from_failure(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    scaffold: Any,
    resolution: Any,
    baseline_artifacts: dict[str, Any],
    failure: _WorkspaceParentValidationFailure,
) -> dict[str, Any]:
    return _build_repo_health_blocked_result(
        vault,
        run_id=request.run_id,
        scaffold=scaffold,
        resolution=resolution,
        baseline_artifacts=baseline_artifacts,
        candidate_artifacts=failure.candidate_artifacts,
        workspace_preparation=failure.workspace_preparation,
        generated_artifact_convergence=failure.generated_artifact_convergence,
        repo_health=failure.repo_health,
        candidate_changed_files_snapshot=failure.candidate_changed_files_snapshot,
    )


def _run_single_workspace_attempt(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    resolution: Any,
    baseline_artifacts: dict[str, Any],
    attempt_index: int,
) -> _WorkspaceExperimentResult | _WorkspaceParentValidationFailure:
    with _mechanism_temporary_directory(
        prefix=f"{request.run_id}-workspace-attempt-{attempt_index}-"
    ) as workspace_root:
        workspace = _prepare_workspace_copy(
            vault,
            run_id=request.run_id,
            workspace_root=workspace_root,
            mode=workspace_preparation_mode_from_policy(resolution.policy),
            allowed_apply_roots=resolution.policy["auto_improve_policy"]["allowed_apply_roots"],
            primary_targets=resolution.primary_targets,
            supporting_targets=resolution.supporting_targets,
            test_files=resolution.test_files,
            declared_dependencies=workspace_preparation_declared_dependencies_from_policy(
                resolution.policy
            ),
        )
        workspace_vault = workspace.workspace_vault
        _copy_repair_context_into_workspace(vault, workspace_vault, run_id=request.run_id)
        mutation_step = _execute_mutation_step(
            vault,
            workspace_vault,
            run_id=request.run_id,
            resolution=resolution,
        )
        generated_artifact_convergence = _record_post_mutation_generated_artifact_convergence(
            vault,
            run_id=request.run_id,
            resolution=resolution,
            workspace_vault=workspace_vault,
        )
        candidate_artifacts = _capture_candidate_artifacts_from_workspace(
            vault,
            request=request,
            resolution=resolution,
            workspace_vault=workspace_vault,
            workspace=workspace,
        )
        repo_health = _repo_health_step(
            vault,
            workspace_vault,
            run_id=request.run_id,
            resolution=resolution,
            baseline_file_digests=workspace.baseline_file_digests,
            diff_model=str(workspace.telemetry.get("diff_model", "full_workspace")),
        )
        if not repo_health.passed:
            return _workspace_parent_validation_failure(
                vault,
                workspace_vault,
                request=request,
                resolution=resolution,
                attempt_index=attempt_index,
                workspace_preparation=workspace.telemetry,
                mutation_step=mutation_step,
                generated_artifact_convergence=generated_artifact_convergence,
                candidate_artifacts=candidate_artifacts,
                repo_health=repo_health,
            )

        return _promotion_workspace_phase_result(
            vault,
            request=request,
            resolution=resolution,
            baseline_artifacts=baseline_artifacts,
            candidate_artifacts=candidate_artifacts,
            workspace_vault=workspace_vault,
            workspace_preparation=workspace.telemetry,
            mutation_step=mutation_step,
            generated_artifact_convergence=generated_artifact_convergence,
            repo_health=repo_health,
        )


def _run_workspace_experiment_phase(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    scaffold: Any,
    resolution: Any,
    baseline_artifacts: dict[str, Any],
) -> _WorkspaceExperimentResult | dict[str, Any]:
    repair_attempts_used = 0
    attempt_index = 1
    while True:
        attempt_result = _run_single_workspace_attempt(
            vault,
            request=request,
            resolution=resolution,
            baseline_artifacts=baseline_artifacts,
            attempt_index=attempt_index,
        )
        if isinstance(attempt_result, _WorkspaceExperimentResult):
            return attempt_result

        if not _same_session_repair_allowed(
            attempt_result,
            repair_attempts_used=repair_attempts_used,
        ):
            return _repo_health_blocked_result_from_failure(
                vault,
                request=request,
                scaffold=scaffold,
                resolution=resolution,
                baseline_artifacts=baseline_artifacts,
                failure=attempt_result,
            )

        repair_attempts_used += 1
        repair_context, preserved_artifacts = _write_same_session_repair_context(
            vault,
            request=request,
            resolution=resolution,
            failure=attempt_result,
            repair_attempt_index=repair_attempts_used,
        )
        _record_same_session_repair_scheduled(
            vault,
            request=request,
            resolution=resolution,
            repair_context=repair_context,
            preserved_artifacts=preserved_artifacts,
        )
        attempt_index += 1
