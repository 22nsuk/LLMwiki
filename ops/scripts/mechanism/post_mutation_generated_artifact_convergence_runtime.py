from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.path_runtime import normalize_repo_path_text
from ops.scripts.policy_runtime import report_path
from ops.scripts.raw_registry_preflight import (
    DEFAULT_OUT as RAW_REGISTRY_PREFLIGHT_REPORT_OUT,
    REPRODUCIBILITY_DEFAULT_OUT as RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT,
    build_reproducibility_report,
    load_stored_preflight_report,
    preflight as raw_registry_preflight,
    write_report as write_raw_registry_preflight_report,
    write_reproducibility_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH

from .mechanism_run_common_runtime import RunMechanismExperimentMutationError, write_json
from .mechanism_run_ledger_runtime import run_rel

RAW_REGISTRY_PREFLIGHT_TARGET = RAW_REGISTRY_PREFLIGHT_REPORT_OUT
RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_TARGET = RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT
GENERATED_ARTIFACT_CONVERGENCE_SCHEMA = GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH
GENERATED_ARTIFACT_CONVERGENCE_REPORT = "generated-artifact-convergence.json"


@dataclass(frozen=True)
class PostMutationGeneratedArtifactConvergenceRequest:
    workspace_vault: Path
    policy_path_text: str
    selected_targets: set[str]
    context: RuntimeContext | None


@dataclass(frozen=True)
class PostMutationGeneratedArtifactConvergenceService:
    service_id: str
    trigger_targets: frozenset[str]
    refresh: Callable[[PostMutationGeneratedArtifactConvergenceRequest], dict[str, Any]]

    def selected_for(self, selected_targets: set[str]) -> bool:
        return bool(self.trigger_targets.intersection(selected_targets))


def _normalize_selected_targets(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        target = normalize_repo_path_text(value)
        if target:
            normalized.add(target)
    return normalized


def _refresh_raw_registry_preflight_artifacts(
    request: PostMutationGeneratedArtifactConvergenceRequest,
) -> dict[str, Any]:
    live_report = raw_registry_preflight(
        request.workspace_vault,
        request.policy_path_text,
        context=request.context,
    )
    report_path_written = write_raw_registry_preflight_report(
        request.workspace_vault,
        live_report,
        RAW_REGISTRY_PREFLIGHT_TARGET,
    )
    stored_report, stored_diagnostics = load_stored_preflight_report(
        request.workspace_vault,
        report_path_written,
    )
    reproducibility_report = build_reproducibility_report(
        request.workspace_vault,
        live_report=live_report,
        stored_report=stored_report,
        stored_diagnostics=stored_diagnostics,
        stored_report_path=report_path_written,
        policy_path=request.policy_path_text,
        context=request.context,
    )
    reproducibility_path_written = write_reproducibility_report(
        request.workspace_vault,
        reproducibility_report,
        RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_TARGET,
    )
    if live_report.get("status") != "pass":
        raise RunMechanismExperimentMutationError(
            "selected raw registry preflight report did not pass after post-mutation refresh"
        )
    if (
        reproducibility_report.get("status") != "pass"
        or reproducibility_report.get("diff_status") != "match"
    ):
        raise RunMechanismExperimentMutationError(
            "selected raw registry preflight reproducibility did not match after post-mutation refresh"
        )
    return {
        "target": RAW_REGISTRY_PREFLIGHT_TARGET,
        "status": str(live_report.get("status", "unknown")),
        "artifacts": [
            report_path(request.workspace_vault, report_path_written),
            report_path(request.workspace_vault, reproducibility_path_written),
        ],
        "reproducibility_status": str(reproducibility_report.get("status", "unknown")),
        "reproducibility_diff_status": str(
            reproducibility_report.get("diff_status", "unknown")
        ),
    }


POST_MUTATION_GENERATED_ARTIFACT_CONVERGENCE_SERVICES = (
    PostMutationGeneratedArtifactConvergenceService(
        service_id="raw_registry_preflight_refresh",
        trigger_targets=frozenset(
            {
                RAW_REGISTRY_PREFLIGHT_TARGET,
                RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_TARGET,
            }
        ),
        refresh=_refresh_raw_registry_preflight_artifacts,
    ),
)


def converge_post_mutation_generated_artifacts(
    _vault: Path,
    workspace_vault: Path,
    *,
    policy_path_text: str,
    selected_targets: list[str],
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    normalized_selected_targets = _normalize_selected_targets(selected_targets)
    request = PostMutationGeneratedArtifactConvergenceRequest(
        workspace_vault=workspace_vault,
        policy_path_text=policy_path_text,
        selected_targets=normalized_selected_targets,
        context=context,
    )
    refreshed: list[dict[str, Any]] = []
    for service in POST_MUTATION_GENERATED_ARTIFACT_CONVERGENCE_SERVICES:
        if service.selected_for(request.selected_targets):
            refreshed.append(service.refresh(request))

    return {
        "status": "refreshed" if refreshed else "noop",
        "phase": "post_mutation_generated_artifact_convergence",
        "refreshed_targets": [item["target"] for item in refreshed],
        "artifacts": [
            artifact
            for item in refreshed
            for artifact in item.get("artifacts", [])
        ],
        "details": refreshed,
    }


def summarize_post_mutation_generated_artifact_convergence(
    report_rel: str,
    convergence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact": report_rel,
        "phase": str(
            convergence.get("phase", "post_mutation_generated_artifact_convergence")
        ),
        "status": str(convergence.get("status", "noop")),
        "refreshed_targets": [
            str(target).strip()
            for target in convergence.get("refreshed_targets", [])
            if str(target).strip()
        ],
        "artifacts": [
            str(artifact).strip()
            for artifact in convergence.get("artifacts", [])
            if str(artifact).strip()
        ],
    }


def build_post_mutation_generated_artifact_convergence_report(
    *,
    run_id: str,
    selected_targets: list[str],
    convergence: dict[str, Any],
    context: RuntimeContext,
) -> dict[str, Any]:
    normalized_targets = sorted(_normalize_selected_targets(selected_targets))
    refreshed_targets = [
        str(target).strip()
        for target in convergence.get("refreshed_targets", [])
        if str(target).strip()
    ]
    artifacts = [
        str(artifact).strip()
        for artifact in convergence.get("artifacts", [])
        if str(artifact).strip()
    ]
    details = [
        detail
        for detail in convergence.get("details", [])
        if isinstance(detail, dict)
    ]
    return {
        "$schema": GENERATED_ARTIFACT_CONVERGENCE_SCHEMA,
        "run_id": run_id,
        "generated_at": context.isoformat_z(),
        "phase": str(
            convergence.get("phase", "post_mutation_generated_artifact_convergence")
        ),
        "status": str(convergence.get("status", "noop")),
        "selected_targets": normalized_targets,
        "refreshed_targets": refreshed_targets,
        "artifacts": artifacts,
        "summary": {
            "selected_target_count": len(normalized_targets),
            "refreshed_target_count": len(refreshed_targets),
            "artifact_count": len(artifacts),
        },
        "details": details,
    }


def write_post_mutation_generated_artifact_convergence_report(
    vault: Path,
    *,
    run_id: str,
    selected_targets: list[str],
    convergence: dict[str, Any],
    context: RuntimeContext,
) -> str:
    rel_path = run_rel(run_id, GENERATED_ARTIFACT_CONVERGENCE_REPORT)
    payload = build_post_mutation_generated_artifact_convergence_report(
        run_id=run_id,
        selected_targets=selected_targets,
        convergence=convergence,
        context=context,
    )
    write_json(vault, rel_path, payload, GENERATED_ARTIFACT_CONVERGENCE_SCHEMA)
    return rel_path


def run_post_mutation_generated_artifact_convergence(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    policy_path_text: str,
    selected_targets: list[str],
    context: RuntimeContext,
) -> dict[str, Any]:
    convergence = converge_post_mutation_generated_artifacts(
        vault,
        workspace_vault,
        policy_path_text=policy_path_text,
        selected_targets=selected_targets,
        context=context,
    )
    report_rel = write_post_mutation_generated_artifact_convergence_report(
        vault,
        run_id=run_id,
        selected_targets=selected_targets,
        convergence=convergence,
        context=context,
    )
    return summarize_post_mutation_generated_artifact_convergence(report_rel, convergence)
