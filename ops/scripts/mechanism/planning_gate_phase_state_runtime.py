from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mechanism_run_validation_runtime import (
    MechanismArtifactBundle,
    normalize_mechanism_artifact_bundle,
)
from .planning_gate_artifact_runtime import (
    COMPLETED_MECHANISM_INPUT_SCHEMAS,
    OPTIONAL_COMPLETED_MECHANISM_INPUT_SCHEMAS,
    ArtifactPayload,
    load_and_validate_reported_json_artifact,
)
from ops.scripts.starter_bundle_runtime import StarterBundleDefinition


@dataclass(frozen=True)
class MechanismPhaseState:
    artifact_dir_report: str
    phase: str
    promotion_report: ArtifactPayload
    run_ledger: ArtifactPayload
    planning_validation: ArtifactPayload | None


@dataclass(frozen=True)
class CompletedMechanismInputsState:
    local_input_failures: tuple[str, ...]
    input_validation_failures: tuple[str, ...]
    loaded_input_artifacts: dict[str, ArtifactPayload]
    bundle_for_phase_checks: MechanismArtifactBundle

    @property
    def ready(self) -> bool:
        return not self.input_validation_failures


def classify_mechanism_phase(
    *,
    starter_bundle: StarterBundleDefinition | None,
    promotion_report: ArtifactPayload,
    run_ledger: ArtifactPayload,
) -> str:
    if starter_bundle is not None:
        return starter_bundle.phase
    if promotion_report.get("artifact_class") != "system_mechanism":
        return "starter"
    ledger_status = run_ledger.get("status")
    if ledger_status == "complete":
        return "mechanism_finalized"
    if ledger_status == "ready":
        return "mechanism_evaluated"
    return "mechanism_in_progress"


def mechanism_phase_state(
    artifact_dir_report: str,
    loaded_data: dict[str, ArtifactPayload],
    *,
    starter_bundle: StarterBundleDefinition | None,
) -> MechanismPhaseState | None:
    promotion_report = loaded_data.get("promotion-report.json")
    run_ledger = loaded_data.get("run-ledger.json")
    if not isinstance(promotion_report, dict) or not isinstance(run_ledger, dict):
        return None
    planning_validation = loaded_data.get("planning-validation.json")
    return MechanismPhaseState(
        artifact_dir_report=artifact_dir_report,
        phase=classify_mechanism_phase(
            starter_bundle=starter_bundle,
            promotion_report=promotion_report,
            run_ledger=run_ledger,
        ),
        promotion_report=promotion_report,
        run_ledger=run_ledger,
        planning_validation=planning_validation if isinstance(planning_validation, dict) else None,
    )


def mechanism_phase(
    artifact_dir_report: str,
    loaded_data: dict[str, ArtifactPayload],
    *,
    starter_bundle: StarterBundleDefinition | None,
) -> str:
    phase_state = mechanism_phase_state(
        artifact_dir_report,
        loaded_data,
        starter_bundle=starter_bundle,
    )
    return phase_state.phase if phase_state is not None else "starter"


def placeholder_mechanism_bundle(run_ledger: ArtifactPayload) -> MechanismArtifactBundle:
    return normalize_mechanism_artifact_bundle(
        {
            "baseline_eval_report": {},
            "candidate_eval_report": {},
            "baseline_lint_report": {},
            "candidate_lint_report": {},
            "baseline_mechanism_report": {},
            "candidate_mechanism_report": {},
            "changed_files_manifest_report": {},
            "run_ledger_report": run_ledger,
        }
    )


def load_completed_mechanism_inputs(
    vault: Path,
    phase_state: MechanismPhaseState,
) -> CompletedMechanismInputsState:
    inputs = phase_state.promotion_report.get("inputs", {})
    local_input_failures: list[str] = []
    input_validation_failures: list[str] = []
    loaded_input_artifacts: dict[str, ArtifactPayload] = {}
    for key, schema_rel_path in COMPLETED_MECHANISM_INPUT_SCHEMAS.items():
        rel_path = inputs.get(key) if isinstance(inputs, dict) else None
        if not isinstance(rel_path, str) or not rel_path.strip():
            input_validation_failures.append(f"missing inputs.{key}")
            continue
        if not rel_path.startswith(f"{phase_state.artifact_dir_report}/"):
            local_input_failures.append(f"{key}={rel_path}")
        data, detail = load_and_validate_reported_json_artifact(vault, rel_path, schema_rel_path)
        if data is None:
            input_validation_failures.append(detail)
            continue
        loaded_input_artifacts[key] = data
    for key, schema_rel_path in OPTIONAL_COMPLETED_MECHANISM_INPUT_SCHEMAS.items():
        rel_path = inputs.get(key) if isinstance(inputs, dict) else None
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        if not rel_path.startswith(f"{phase_state.artifact_dir_report}/"):
            local_input_failures.append(f"{key}={rel_path}")
        data, detail = load_and_validate_reported_json_artifact(vault, rel_path, schema_rel_path)
        if data is None:
            input_validation_failures.append(detail)
            continue
        loaded_input_artifacts[key] = data

    phase_bundle = None
    if not input_validation_failures:
        phase_bundle = normalize_mechanism_artifact_bundle(
            {
                **loaded_input_artifacts,
                "changed_files_manifest_report": loaded_input_artifacts["changed_files_manifest"],
                "run_ledger_report": phase_state.run_ledger,
            }
        )
    bundle_for_phase_checks = phase_bundle or placeholder_mechanism_bundle(phase_state.run_ledger)
    return CompletedMechanismInputsState(
        local_input_failures=tuple(local_input_failures),
        input_validation_failures=tuple(input_validation_failures),
        loaded_input_artifacts=loaded_input_artifacts,
        bundle_for_phase_checks=bundle_for_phase_checks,
    )
