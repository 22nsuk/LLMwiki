from __future__ import annotations

from pathlib import Path
from typing import cast

from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    EVAL_REPORT_SCHEMA_PATH,
    LINT_REPORT_SCHEMA_PATH,
)
from ops.scripts.wiki_eval import evaluate
from ops.scripts.wiki_lint import lint
from ops.scripts.wiki_snapshot_runtime import build_wiki_runtime_snapshot

from .mechanism_assess import (
    _dedupe_preserve_order,
    build_report as build_mechanism_report,
    normalize_targets,
    write_report as write_mechanism_report,
)
from .mechanism_run_common_runtime import (
    ExperimentResolution,
    RunMechanismExperimentArtifactError,
    sanitize_payload,
    write_json,
)
from .mechanism_run_ledger_runtime import append_ledger_event, run_rel

LINT_REPORT_SCHEMA = LINT_REPORT_SCHEMA_PATH
EVAL_REPORT_SCHEMA = EVAL_REPORT_SCHEMA_PATH


def _capture_reports(
    source_vault: Path,
    *,
    run_id: str,
    phase: str,
    policy: dict,
    policy_path_text: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
    artifact_vault: Path | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    report_vault = artifact_vault or source_vault
    sanitize_roots = [source_vault, report_vault]
    runtime_snapshot = build_wiki_runtime_snapshot(source_vault, registry_contract=policy["registry_contract"])
    lint_report = lint(
        source_vault,
        policy_path_text,
        snapshot=runtime_snapshot,
        context=context,
    )
    lint_report = cast(dict, sanitize_payload(lint_report, roots=sanitize_roots))
    lint_report["vault"] = report_path(report_vault, report_vault)
    write_json(report_vault, run_rel(run_id, f"{phase}-lint.json"), lint_report, LINT_REPORT_SCHEMA)

    eval_report = evaluate(
        source_vault,
        policy_path_text,
        snapshot=runtime_snapshot,
        context=context,
    )
    eval_report = cast(dict, sanitize_payload(eval_report, roots=sanitize_roots))
    eval_report["vault"] = report_path(report_vault, report_vault)
    write_json(report_vault, run_rel(run_id, f"{phase}-eval.json"), eval_report, EVAL_REPORT_SCHEMA)

    try:
        primary_target_pairs = normalize_targets(source_vault, _dedupe_preserve_order(primary_targets))
        supporting_target_pairs = normalize_targets(source_vault, _dedupe_preserve_order(supporting_targets))
        test_file_pairs = normalize_targets(source_vault, _dedupe_preserve_order(test_files))
    except ValueError as exc:
        raise RunMechanismExperimentArtifactError(str(exc)) from exc
    mechanism_report = build_mechanism_report(
        source_vault,
        policy,
        source_vault / policy_path_text,
        primary_target_pairs,
        supporting_target_pairs,
        test_file_pairs,
        context=context,
    )
    mechanism_report = cast(dict, sanitize_payload(mechanism_report, roots=sanitize_roots))
    mechanism_report["vault"] = report_path(report_vault, report_vault)
    write_mechanism_report(
        report_vault,
        mechanism_report,
        run_rel(run_id, f"{phase}-mechanism-assessment.json"),
    )

    return {
        "lint": run_rel(run_id, f"{phase}-lint.json"),
        "eval": run_rel(run_id, f"{phase}-eval.json"),
        "mechanism": run_rel(run_id, f"{phase}-mechanism-assessment.json"),
    }


def _capture_baseline_step(vault: Path, *, run_id: str, resolution: ExperimentResolution) -> dict:
    baseline_artifacts = _capture_reports(
        vault,
        run_id=run_id,
        phase="baseline",
        policy=resolution.policy,
        policy_path_text=resolution.policy_path_text,
        primary_targets=resolution.primary_targets,
        supporting_targets=resolution.supporting_targets,
        test_files=resolution.test_files,
        context=resolution.context,
    )
    append_ledger_event(
        vault,
        run_id,
        event_type="baseline_captured",
        summary="Captured baseline lint, eval, and mechanism assessment artifacts.",
        artifacts=[
            *resolution.primary_targets,
            *resolution.supporting_targets,
            *resolution.test_files,
            *baseline_artifacts.values(),
        ],
        decision="baseline_ready",
        context=resolution.context,
        status="running",
    )
    return baseline_artifacts


def _capture_candidate_step(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    report_source_vault: Path | None = None,
) -> dict:
    candidate_artifacts = _capture_reports(
        report_source_vault or workspace_vault,
        run_id=run_id,
        phase="candidate",
        policy=resolution.policy,
        policy_path_text=resolution.policy_path_text,
        primary_targets=resolution.primary_targets,
        supporting_targets=resolution.supporting_targets,
        test_files=resolution.test_files,
        artifact_vault=vault,
        context=resolution.context,
    )
    append_ledger_event(
        vault,
        run_id,
        event_type="candidate_captured",
        summary="Captured candidate lint, eval, and mechanism assessment artifacts from the disposable workspace.",
        artifacts=[
            *resolution.primary_targets,
            *resolution.supporting_targets,
            *resolution.test_files,
            *candidate_artifacts.values(),
        ],
        decision="ready_for_repo_health_gate",
        context=resolution.context,
        status="running",
    )
    return candidate_artifacts
