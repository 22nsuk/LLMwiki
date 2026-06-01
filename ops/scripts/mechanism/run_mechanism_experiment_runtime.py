from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import (
    workspace_preparation_declared_dependencies_from_policy,
    workspace_preparation_mode_from_policy,
)
from ops.scripts.promotion_decision_registry_runtime import decision_from_report
from ops.scripts.runtime_context import RuntimeContext

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
)
from .mechanism_run_ledger_runtime import append_ledger_event
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
    _repo_health_step,
    _run_command,
    _snapshot_repo_file_digests,
    _write_changed_files_manifest,
)
from .post_mutation_generated_artifact_convergence_runtime import (
    run_post_mutation_generated_artifact_convergence,
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


def _run_workspace_experiment_phase(
    vault: Path,
    *,
    request: RunMechanismExperimentRequest,
    scaffold: Any,
    resolution: Any,
    baseline_artifacts: dict[str, Any],
) -> _WorkspaceExperimentResult | dict[str, Any]:
    with _mechanism_temporary_directory(prefix=f"{request.run_id}-workspace-") as workspace_root:
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
            candidate_artifacts = _capture_candidate_step(
                vault,
                workspace_vault,
                run_id=request.run_id,
                resolution=resolution,
                report_source_vault=candidate_report_vault,
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
            return _build_repo_health_blocked_result(
                vault,
                run_id=request.run_id,
                scaffold=scaffold,
                resolution=resolution,
                baseline_artifacts=baseline_artifacts,
                candidate_artifacts=candidate_artifacts,
                workspace_preparation=workspace.telemetry,
                generated_artifact_convergence=generated_artifact_convergence,
                repo_health=repo_health,
            )

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
        )
        finalize_step = _finalize_step(
            vault,
            run_id=request.run_id,
            promotion_report=promotion.report,
            finalize=request.finalize and workspace_apply.live_applied,
            context=resolution.context,
        )
        return _WorkspaceExperimentResult(
            workspace_preparation=workspace.telemetry,
            mutation_step=mutation_step,
            generated_artifact_convergence=generated_artifact_convergence,
            candidate_artifacts=candidate_artifacts,
            repo_health=repo_health,
            promotion=promotion,
            finalize_step=finalize_step,
            workspace_apply=workspace_apply,
        )
