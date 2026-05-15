from __future__ import annotations

import time
from pathlib import Path
from typing import TypedDict

from .planning_gate_artifact_runtime import (
    ARTIFACT_SCHEMAS,
    OPTIONAL_ARTIFACT_SCHEMAS,
    ArtifactPayload,
    ArtifactValidationResult,
    artifact_result_without_data,
    validate_artifact,
    validate_optional_artifact,
)
from .planning_gate_phase_checks_runtime import mechanism_phase_checks
from .planning_gate_phase_state_runtime import mechanism_phase_state
from ops.scripts.policy_runtime import load_policy
from ops.scripts.path_runtime import stable_report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.runtime_event_logging_runtime import append_runtime_event
from ops.scripts.starter_bundle_runtime import (
    StarterBundleDefinition,
    starter_bundle_allowed_promotion_input_paths,
    starter_bundle_for_artifact_dir,
)
from ops.scripts.validation_check_types_runtime import ValidationCheckResult, validation_check


class PlanningValidationReport(TypedDict):
    artifact_dir: str
    generated_at: str
    phase: str
    status: str
    artifacts: list[ArtifactValidationResult]
    cross_checks: list[ValidationCheckResult]
    phase_checks: list[ValidationCheckResult]


def artifact_dir_report_path(vault: Path, artifact_dir: Path) -> str:
    return stable_report_path(vault, artifact_dir)


def load_validated_artifacts(
    vault: Path,
    artifact_dir: Path,
) -> tuple[list[ArtifactValidationResult], dict[str, ArtifactPayload]]:
    results: list[ArtifactValidationResult] = []
    loaded_data: dict[str, ArtifactPayload] = {}

    for artifact_name, schema_rel_path in ARTIFACT_SCHEMAS.items():
        result = validate_artifact(vault, artifact_dir, artifact_name, schema_rel_path)
        results.append(artifact_result_without_data(result))
        if result.get("pass") and "data" in result:
            loaded_data[artifact_name] = result["data"]

    for artifact_name, schema_rel_path in OPTIONAL_ARTIFACT_SCHEMAS.items():
        optional_result = validate_optional_artifact(
            vault,
            artifact_dir,
            artifact_name,
            schema_rel_path,
        )
        if optional_result is None:
            continue
        results.append(artifact_result_without_data(optional_result))
        if optional_result.get("pass") and "data" in optional_result:
            loaded_data[artifact_name] = optional_result["data"]

    return results, loaded_data


def run_id_alignment_checks(
    loaded_data: dict[str, ArtifactPayload],
) -> tuple[list[ValidationCheckResult], dict[str, object]]:
    run_ids = {
        name: data.get("run_id")
        for name, data in loaded_data.items()
        if isinstance(data, dict) and "run_id" in data
    }
    if len(set(run_ids.values())) > 1:
        return [validation_check("run_id_alignment", False, run_ids)], run_ids
    return [
        validation_check(
            "run_id_alignment",
            len(run_ids) >= len(ARTIFACT_SCHEMAS),
            run_ids,
        )
    ], run_ids


def mechanism_promotion_input_alignment_checks(
    *,
    artifact_dir_report: str,
    loaded_data: dict[str, ArtifactPayload],
    starter_bundle: StarterBundleDefinition | None,
) -> list[ValidationCheckResult]:
    promotion_report = loaded_data.get("promotion-report.json")
    if not (
        isinstance(promotion_report, dict)
        and promotion_report.get("artifact_class") == "system_mechanism"
    ):
        return []

    inputs = promotion_report.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    alignment_specs = [
        ("run_ledger", "mechanism_promotion_run_ledger_alignment", "run-ledger.json"),
        (
            "changed_files_manifest",
            "mechanism_promotion_changed_files_manifest_alignment",
            "changed-files-manifest.json",
        ),
    ]
    if "behavior_delta" in inputs or "behavior-delta.json" in loaded_data:
        alignment_specs.append(
            (
                "behavior_delta",
                "mechanism_promotion_behavior_delta_alignment",
                "behavior-delta.json",
            )
        )

    checks: list[ValidationCheckResult] = []
    for input_key, check_name, artifact_name in alignment_specs:
        expected_path = f"{artifact_dir_report}/{artifact_name}"
        actual_path = inputs.get(input_key, "")
        if not isinstance(actual_path, str):
            actual_path = ""
        allowed_paths = set(
            starter_bundle_allowed_promotion_input_paths(
                starter_bundle,
                input_key,
                expected_path=expected_path,
            )
        )
        checks.append(
            validation_check(
                check_name,
                actual_path in allowed_paths,
                {
                    "expected": expected_path,
                    "actual": actual_path,
                    "allowed": sorted(allowed_paths),
                },
            )
        )
    return checks


def build_planning_validation_report(
    *,
    artifact_dir_report: str,
    generated_at: str,
    phase: str,
    artifacts: list[ArtifactValidationResult],
    cross_checks: list[ValidationCheckResult],
    phase_checks: list[ValidationCheckResult],
) -> PlanningValidationReport:
    overall_pass = (
        all(item["pass"] for item in artifacts)
        and all(item["pass"] for item in cross_checks)
        and all(item["pass"] for item in phase_checks)
    )
    return {
        "artifact_dir": artifact_dir_report,
        "generated_at": generated_at,
        "phase": phase,
        "status": "pass" if overall_pass else "fail",
        "artifacts": artifacts,
        "cross_checks": cross_checks,
        "phase_checks": phase_checks,
    }


def append_planning_validation_event(
    vault: Path,
    *,
    context: RuntimeContext,
    phase: str,
    decision: str,
    artifact_dir_report: str,
    duration_ms: int,
    run_ids: dict[str, object],
    policy_version: object,
) -> None:
    aligned_run_ids = {
        str(value).strip()
        for value in run_ids.values()
        if isinstance(value, str) and str(value).strip()
    }
    append_runtime_event(
        vault,
        context=context,
        component="planning_gate_validate",
        phase=phase,
        decision=decision,
        artifact_path=artifact_dir_report,
        duration_ms=duration_ms,
        run_id=next(iter(aligned_run_ids)) if len(aligned_run_ids) == 1 else "",
        policy_version=policy_version,
    )


def validate_run_dir(
    vault: Path,
    artifact_dir: Path,
    *,
    policy: dict | None = None,
    context: RuntimeContext | None = None,
) -> PlanningValidationReport:
    started_at = time.monotonic()
    active_policy = policy or load_policy(vault)[0]
    runtime_context = context or RuntimeContext.from_policy(active_policy)
    artifact_dir_report = artifact_dir_report_path(vault, artifact_dir)
    starter_bundle = starter_bundle_for_artifact_dir(active_policy, artifact_dir_report)

    artifacts, loaded_data = load_validated_artifacts(vault, artifact_dir)
    cross_checks, run_ids = run_id_alignment_checks(loaded_data)
    cross_checks.extend(
        mechanism_promotion_input_alignment_checks(
            artifact_dir_report=artifact_dir_report,
            loaded_data=loaded_data,
            starter_bundle=starter_bundle,
        )
    )

    phase_state = mechanism_phase_state(
        artifact_dir_report,
        loaded_data,
        starter_bundle=starter_bundle,
    )
    phase = phase_state.phase if phase_state is not None else "starter"
    phase_checks = mechanism_phase_checks(vault, phase_state)
    report = build_planning_validation_report(
        artifact_dir_report=artifact_dir_report,
        generated_at=runtime_context.isoformat_z(),
        phase=phase,
        artifacts=artifacts,
        cross_checks=cross_checks,
        phase_checks=phase_checks,
    )
    append_planning_validation_event(
        vault,
        context=runtime_context,
        phase=phase,
        decision=report["status"],
        artifact_dir_report=artifact_dir_report,
        duration_ms=int(round((time.monotonic() - started_at) * 1000)),
        run_ids=run_ids,
        policy_version=active_policy.get("version"),
    )
    return report
