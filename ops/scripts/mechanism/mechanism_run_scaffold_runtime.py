from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.observability_artifacts_runtime import (
    write_run_artifact_fingerprint,
)
from ops.scripts.core.output_runtime import write_output_text
from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.run_id_runtime import reject_template_placeholder_run_id
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    PLANNING_VALIDATION_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
    PROPOSAL_SNAPSHOT_SCHEMA_PATH,
    RUN_LEDGER_SCHEMA_PATH,
    SEED_SCHEMA_PATH,
)
from ops.scripts.core.starter_bundle_runtime import (
    SYSTEM_MECHANISM_STARTER_BUNDLE,
    starter_bundle_path,
)

from .improvement_observations_runtime import (
    IMPROVEMENT_OBSERVATIONS_FILENAME,
    IMPROVEMENT_OBSERVATIONS_SCHEMA,
    build_run_improvement_observations,
)
from .mechanism_run_common_runtime import (
    ExperimentResolution,
    RunMechanismExperimentArtifactError,
    RunMechanismExperimentUsageError,
    ScaffoldedRun,
    load_json,
    timestamp,
    write_json,
)
from .mechanism_run_ledger_runtime import (
    append_ledger_event,
    load_run_ledger,
    run_rel,
    write_experiment_telemetry,
)
from .mechanism_run_scaffold_resolution_runtime import (
    DEFAULT_MUTATION_PROPOSAL_REPORT,
    SHELL_CONTROL_TOKENS,
    _command_argv,
    _default_check_command,
    _load_mutation_proposal,
    _normalize_target_rel_paths,
    _prepare_execution_commands,
    _resolve_command_executable,
    _resolve_experiment_inputs,
)
from .mechanism_run_scaffold_templates_runtime import (
    default_log_summary,
    initial_planning_validation,
    initial_run_ledger,
    placeholder_promotion_report,
    proposal_snapshot,
    starter_open_questions,
    starter_plan_text,
    starter_seed_text,
    yaml_quoted,
)
from .planning_gate_validate import validate_run_dir

__all__ = [
    "DEFAULT_MUTATION_PROPOSAL_REPORT",
    "PLANNING_VALIDATION_SCHEMA",
    "PROMOTION_REPORT_SCHEMA",
    "PROPOSAL_SNAPSHOT_SCHEMA",
    "RUNTIME_OWNED_STARTER_FILES",
    "RUN_LEDGER_SCHEMA",
    "SEED_SCHEMA",
    "SHELL_CONTROL_TOKENS",
    "_command_argv",
    "_default_check_command",
    "_load_mutation_proposal",
    "_normalize_target_rel_paths",
    "_prepare_execution_commands",
    "_resolve_command_executable",
    "_resolve_experiment_inputs",
    "timestamp",
]


PLANNING_VALIDATION_SCHEMA = PLANNING_VALIDATION_SCHEMA_PATH
PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
PROPOSAL_SNAPSHOT_SCHEMA = PROPOSAL_SNAPSHOT_SCHEMA_PATH
RUN_LEDGER_SCHEMA = RUN_LEDGER_SCHEMA_PATH
SEED_SCHEMA = SEED_SCHEMA_PATH
RUNTIME_OWNED_STARTER_FILES = {
    "seed.yaml",
    "plan.md",
    "open-questions.md",
    IMPROVEMENT_OBSERVATIONS_FILENAME,
    "planning-validation.json",
    "run-ledger.json",
    "promotion-report.json",
    "proposal-snapshot.json",
}

_default_log_summary = default_log_summary
_yaml_quoted = yaml_quoted
_proposal_snapshot = proposal_snapshot
_starter_seed_text = starter_seed_text
_starter_plan_text = starter_plan_text
_starter_open_questions = starter_open_questions
_initial_planning_validation = initial_planning_validation
_initial_run_ledger = initial_run_ledger
_placeholder_promotion_report = placeholder_promotion_report


@dataclass(frozen=True)
class ScaffoldRunDirRequest:
    starter_bundle_dir: Path
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]
    log_summary: str
    proposal: dict | None
    proposal_source_report: str | None
    seed_state: str
    context: RuntimeContext | None = None


def _copy_starter_bundle_extras(starter_bundle_dir: Path, run_dir: Path) -> None:
    for source_path in starter_bundle_dir.rglob("*"):
        if not source_path.is_file():
            continue
        rel_path = source_path.relative_to(starter_bundle_dir)
        if len(rel_path.parts) == 1 and rel_path.name in RUNTIME_OWNED_STARTER_FILES:
            continue
        destination = run_dir / rel_path
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source_path, destination)
        except OSError as exc:
            raise RunMechanismExperimentArtifactError(
                f"failed to copy starter bundle artifact {rel_path.as_posix()}: {exc}"
            ) from exc


def _scaffold_run_dir(
    vault: Path,
    run_id: str,
    request: ScaffoldRunDirRequest,
) -> Path:
    try:
        reject_template_placeholder_run_id(run_id)
    except ValueError as exc:
        raise RunMechanismExperimentUsageError(str(exc)) from exc
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if not request.starter_bundle_dir.exists():
        raise RunMechanismExperimentArtifactError(
            f"missing configured system_mechanism starter bundle: {report_path(vault, request.starter_bundle_dir)}"
        )
    _copy_starter_bundle_extras(request.starter_bundle_dir, run_dir)

    if request.proposal is not None:
        snapshot_path = run_dir / "proposal-snapshot.json"
        if snapshot_path.exists():
            snapshot = load_json(snapshot_path)
            existing_id = snapshot.get("proposal", {}).get("proposal_id")
            if existing_id != request.proposal["proposal_id"]:
                raise RunMechanismExperimentUsageError(
                    f"run {run_id} already freezes proposal {existing_id}, not {request.proposal['proposal_id']}"
                )
        else:
            write_json(
                vault,
                run_rel(run_id, "proposal-snapshot.json"),
                _proposal_snapshot(
                    run_id,
                    proposal=request.proposal,
                    source_report=request.proposal_source_report or DEFAULT_MUTATION_PROPOSAL_REPORT,
                    context=request.context,
                ),
                PROPOSAL_SNAPSHOT_SCHEMA,
            )
    if not (run_dir / "seed.yaml").exists():
        write_output_text(
            run_dir / "seed.yaml",
            _starter_seed_text(
                run_id,
                request.primary_targets,
                request.supporting_targets,
                request.test_files,
                proposal=request.proposal,
                seed_state=request.seed_state,
            ),
        )
    if not (run_dir / "plan.md").exists():
        write_output_text(
            run_dir / "plan.md",
            _starter_plan_text(
                run_id,
                request.primary_targets,
                request.supporting_targets,
                proposal=request.proposal,
            ),
        )
    if not (run_dir / "open-questions.md").exists():
        write_output_text(
            run_dir / "open-questions.md",
            _starter_open_questions(request.test_files, proposal=request.proposal),
        )
    if not (run_dir / IMPROVEMENT_OBSERVATIONS_FILENAME).exists():
        write_json(
            vault,
            run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME),
            build_run_improvement_observations(run_id, context=request.context),
            IMPROVEMENT_OBSERVATIONS_SCHEMA,
        )
    # planning-validation has no own timestamp, so its envelope derives currentness from run-ledger.
    if not (run_dir / "run-ledger.json").exists():
        write_json(
            vault,
            run_rel(run_id, "run-ledger.json"),
            _initial_run_ledger(
                run_id,
                include_proposal_snapshot=request.proposal is not None,
                context=request.context,
            ),
            RUN_LEDGER_SCHEMA,
        )
    if not (run_dir / "planning-validation.json").exists():
        write_json(
            vault,
            run_rel(run_id, "planning-validation.json"),
            _initial_planning_validation(
                run_id,
                request.primary_targets,
                request.test_files,
                proposal=request.proposal,
            ),
            PLANNING_VALIDATION_SCHEMA,
        )
    if not (run_dir / "promotion-report.json").exists():
        write_json(
            vault,
            run_rel(run_id, "promotion-report.json"),
            _placeholder_promotion_report(
                run_id,
                request.primary_targets,
                request.supporting_targets,
                request.log_summary,
            ),
            PROMOTION_REPORT_SCHEMA,
        )
    return run_dir


def _scaffold_or_load_run(
    vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    scaffold_only: bool,
) -> ScaffoldedRun:
    run_dir = _scaffold_run_dir(
        vault,
        run_id,
        ScaffoldRunDirRequest(
            starter_bundle_dir=starter_bundle_path(
                vault,
                resolution.policy,
                SYSTEM_MECHANISM_STARTER_BUNDLE,
            ),
            primary_targets=resolution.primary_targets,
            supporting_targets=resolution.supporting_targets,
            test_files=resolution.test_files,
            log_summary=resolution.log_summary,
            proposal=resolution.proposal,
            proposal_source_report=resolution.proposal_source_report,
            seed_state="SEED_DRAFT" if scaffold_only else "SEED_FROZEN",
            context=resolution.context,
        ),
    )
    ledger = load_run_ledger(vault, run_id)
    if ledger.get("status") == "complete":
        raise RunMechanismExperimentUsageError(f"run {run_id} is already complete")
    return ScaffoldedRun(
        run_dir=run_dir,
        proposal_snapshot=(
            run_rel(run_id, "proposal-snapshot.json")
            if resolution.proposal is not None
            else ""
        ),
    )


def _build_scaffold_only_result(
    vault: Path,
    *,
    run_id: str,
    scaffold: ScaffoldedRun,
    resolution: ExperimentResolution,
) -> dict:
    planning_gate = validate_run_dir(vault, scaffold.run_dir, context=resolution.context)
    result = {
        "run_id": run_id,
        "run_dir": report_path(vault, scaffold.run_dir),
        "proposal_snapshot": scaffold.proposal_snapshot,
        "improvement_observations": run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME),
        "scope_freeze": resolution.scope_freeze_path,
        "routing_reports": resolution.routing_report_paths,
        "executor_reports": resolution.executor_report_paths,
        "resolved_primary_targets": resolution.primary_targets,
        "resolved_supporting_targets": resolution.supporting_targets,
        "planning_gate": {
            "phase": planning_gate["phase"],
            "status": planning_gate["status"],
        },
        "scaffold_only": True,
    }
    write_experiment_telemetry(vault, run_id=run_id, resolution=resolution, result=result)
    result["run_artifact_fingerprint"] = write_run_artifact_fingerprint(
        vault,
        run_id,
        context=resolution.context,
    )
    return result


def _freeze_seed_scope(vault: Path, *, run_id: str, resolution: ExperimentResolution) -> None:
    append_ledger_event(
        vault,
        run_id,
        event_type="seed_frozen",
        summary=(
            f"Frozen mechanism scope to primary target {resolution.primary_targets[0]} "
            "and prepared wrapper-driven execution."
        ),
        artifacts=[
            run_rel(run_id, "seed.yaml"),
            run_rel(run_id, "plan.md"),
            run_rel(run_id, IMPROVEMENT_OBSERVATIONS_FILENAME),
            run_rel(run_id, "promotion-report.json"),
        ],
        decision="ready_for_baseline_capture",
        context=resolution.context,
        status="running",
    )
