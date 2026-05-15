from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    read_json_object,
    write_schema_backed_report,
)
from ops.scripts.mechanism_assess import (
    MechanismAssessmentState,
    count_nonempty_lines,
    markdown_heading_count,
    python_branch_node_count,
    python_function_count,
    python_test_case_count,
)
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.python_function_budget_runtime import python_function_budget_candidates
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)

STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA = STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH
DEFAULT_REPORT = "ops/reports/structural-complexity-budget.json"
FUNCTION_BUDGET_TOP_N = 10
PRODUCER = "ops.scripts.structural_complexity_budget_runtime"
SOURCE_COMMAND = (
    "python -m ops.scripts.structural_complexity_budget "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)
DEFAULT_TARGET_PROFILES: dict[str, dict[str, Any]] = {
    "critical_runtime_orchestrators": {
        "targets": [
            "ops/scripts/mechanism/auto_improve_runtime.py",
            "ops/scripts/mechanism/auto_improve_readiness_runtime.py",
            "ops/scripts/mechanism/promotion_gate_mechanism_runtime.py",
            "ops/scripts/mechanism/mechanism_run_workspace_runtime.py",
            "ops/scripts/mechanism/mutation_proposal_runtime.py",
            "ops/scripts/mechanism/mechanism_review_candidate_runtime.py",
            "ops/scripts/mechanism/mechanism_review_outcome_metrics_calibration_runtime.py",
            "ops/scripts/core/codex_exec_executor.py",
            "ops/scripts/core/filesystem_runtime.py",
            "ops/scripts/core/policy_runtime.py",
        ],
        "budgets": {
            "nonempty_line_count_total": 900,
            "python_function_count": 45,
            "python_branch_node_count": 110,
        },
        "notes": [
            "Deterministic preview budget for the largest orchestration runtimes.",
            "Use this report as a tracked preview artifact before promoting any hard gate into make check-strict.",
        ],
    },
    "high_complexity_helpers": {
        "targets": [
            "ops/scripts/eval/wiki_doc_audit_runtime.py",
            "ops/scripts/registry/raw_intake_promotion_runtime.py",
            "ops/scripts/core/registry_review_candidate_passes_runtime.py",
            "ops/scripts/eval/wiki_lint_review_runtime.py",
            "ops/scripts/eval/wiki_eval.py",
            "ops/scripts/core/observability_artifacts_runtime.py",
            "ops/scripts/core/policy_validation_runtime.py",
            "ops/scripts/eval/structural_complexity_budget_runtime.py",
            "tests/minimal_vault_seed_core.py",
            "tests/minimal_vault_seed_smoke.py",
        ],
        "budgets": {
            "nonempty_line_count_total": 650,
            "python_function_count": 24,
            "python_branch_node_count": 70,
        },
        "notes": [
            "Preview-only profile for helper-heavy runtime modules repeatedly flagged by code review.",
            "Existing inherited attention should be reduced deliberately before making this profile a hard gate.",
            "Function-level hot spots are summarized separately in diagnostics.function_budget_top_n.",
        ],
    },
    "runtime_closeout_orchestrators": {
        "targets": [
            "ops/scripts/mechanism/finalize_run_state_runtime.py",
            "ops/scripts/mechanism/planning_gate_report_runtime.py",
        ],
        "budgets": {
            "nonempty_line_count_total": 260,
            "python_function_count": 18,
            "python_branch_node_count": 40,
        },
        "notes": [
            "Preview budget for the owner modules that now carry closeout and planning state-transition assembly.",
        ],
    },
    "release_report_builders": {
        "targets": [
            "ops/scripts/release/release_closeout_batch_manifest.py",
            "ops/scripts/release/release_evidence_dashboard.py",
            "ops/scripts/release/release_closeout_summary.py",
            "ops/scripts/test/test_execution_summary.py",
        ],
        "budgets": {
            "nonempty_line_count_total": 1200,
            "python_function_count": 50,
            "python_branch_node_count": 90,
        },
        "notes": [
            "Preview budget for large release and test report builders slated for load-normalize-classify-decide-render-seal decomposition.",
            "Use attention here to prioritize pure decision extraction before tightening hard gates.",
        ],
    },
    "learning_claim_report_builders": {
        "targets": [
            "ops/scripts/learning/learning_delta_scoreboard.py",
            "ops/scripts/learning/learning_claim_evidence_bundle.py",
            "ops/scripts/learning/learning_claim_model.py",
            "ops/scripts/learning/learning_claim_unlock_review.py",
            "ops/scripts/learning/learning_confirmed_evidence_cohort.py",
            "ops/scripts/learning/learning_confirmed_legacy_reconstruction.py",
        ],
        "budgets": {
            "nonempty_line_count_total": 900,
            "python_function_count": 36,
            "python_branch_node_count": 60,
        },
        "notes": [
            "Preview budget for self-improvement claim model builders and compatibility reconstruction surfaces.",
            "Keep regression-safe evidence, same-eval gain, cross-eval gain, persistence, and production learning decisions separated as these modules shrink.",
        ],
    },
}


@dataclass(frozen=True)
class StructuralComplexityBudgetInputs:
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    profiles: dict[str, dict[str, Any]]
    state: MechanismAssessmentState
    function_candidates: list[dict[str, Any]]
    monitored_targets: set[str]
    candidate_by_page: dict[str, list[dict[str, Any]]]


@dataclass(frozen=True)
class TargetReportResult:
    report: dict[str, Any]
    status: str


@dataclass(frozen=True)
class TargetReportSummary:
    reports: list[dict[str, Any]]
    attention_count: int
    failure_count: int


def _budget_metrics(metrics: dict[str, Any]) -> dict[str, int]:
    return {
        "nonempty_line_count_total": int(metrics["nonempty_line_count_total"]),
        "python_function_count": int(metrics["python_function_count"]),
        "python_branch_node_count": int(metrics["python_branch_node_count"]),
    }


def _measured_metrics(state: MechanismAssessmentState, rel_path: str, path: Path) -> dict[str, int]:
    test_case_count = 0
    if rel_path.startswith("tests/") and path.suffix == ".py":
        test_case_count = python_test_case_count(state, rel_path, path)
    return {
        "nonempty_line_count_total": count_nonempty_lines(state, rel_path, path),
        "python_function_count": (
            python_function_count(state, rel_path, path) if path.suffix == ".py" else 0
        ),
        "python_branch_node_count": (
            python_branch_node_count(state, rel_path, path) if path.suffix == ".py" else 0
        ),
        "markdown_heading_count": (
            markdown_heading_count(state, rel_path, path) if path.suffix == ".md" else 0
        ),
        "test_case_count": test_case_count,
    }


def _budget_deltas(metrics: dict[str, int], budgets: dict[str, int]) -> dict[str, int]:
    return {
        metric: int(metrics[metric]) - int(budgets[metric])
        for metric in budgets
    }


def _normalize_target_profiles(configured: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for profile_name, profile in configured.items():
        budgets = _budget_metrics(profile["budgets"])
        targets = [str(path) for path in profile["targets"]]
        profiles[profile_name] = {
            "targets": targets,
            "budgets": budgets,
            "notes": [str(note) for note in profile.get("notes", [])],
        }
    return profiles


def _dedupe_paths(paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path).strip().replace("\\", "/").lstrip("./")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def target_paths_from_changed_files_manifest(vault: Path, manifest_path: str) -> list[str]:
    path = Path(manifest_path)
    if not path.is_absolute():
        path = vault / path
    try:
        payload = read_json_object(
            path,
            context=f"changed files manifest root must be an object: {manifest_path}",
        )
    except JSONDecodeError as exc:
        raise ValueError(f"changed files manifest is not valid JSON: {manifest_path}: {exc.msg}") from exc
    except ValueError as exc:
        raise ValueError(f"changed files manifest root must be an object: {manifest_path}") from exc
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError(f"changed files manifest must contain a files list: {manifest_path}")
    return _dedupe_paths([
        str(entry.get("path", ""))
        for entry in files
        if isinstance(entry, dict)
    ])


def touched_target_profiles(
    configured: dict[str, dict[str, Any]],
    target_paths: list[str],
) -> dict[str, dict[str, Any]]:
    requested = set(_dedupe_paths(target_paths))
    profiles: dict[str, dict[str, Any]] = {}
    matched: set[str] = set()
    for profile_name, profile in _normalize_target_profiles(configured).items():
        targets = [path for path in profile["targets"] if path in requested]
        if not targets:
            continue
        matched.update(targets)
        profiles[profile_name] = {
            "targets": targets,
            "budgets": profile["budgets"],
            "notes": [
                *profile["notes"],
                "Touched-surface subset generated from explicit target or changed-files manifest input.",
            ],
        }

    unmatched = [path for path in _dedupe_paths(target_paths) if path not in matched]
    if unmatched:
        fallback = _normalize_target_profiles(configured)["critical_runtime_orchestrators"]
        profiles["touched_targets"] = {
            "targets": unmatched,
            "budgets": fallback["budgets"],
            "notes": [
                "Touched-surface fallback profile for targets outside the default monitored set.",
                "Budgets reuse the critical runtime orchestrator preview thresholds.",
            ],
        }
    if not profiles:
        fallback = _normalize_target_profiles(configured)["critical_runtime_orchestrators"]
        profiles["touched_targets"] = {
            "targets": [],
            "budgets": fallback["budgets"],
            "notes": [
                "Touched-surface check received no file targets and therefore has no targets to evaluate.",
            ],
        }
    return profiles


def _candidate_pages(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["page"])].append(candidate)
    return dict(grouped)


def _function_budget_overage(candidate: dict[str, Any], metric: str) -> int:
    value = candidate.get("value", {})
    threshold = candidate.get("threshold", {})
    if not isinstance(value, dict) or not isinstance(threshold, dict):
        return 0
    return int(value.get(metric, 0)) - int(threshold.get(metric, 0))


def _function_budget_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int, str, int, str]:
    value = candidate.get("value", {})
    if not isinstance(value, dict):
        value = {}
    return (
        -len(candidate.get("triggered_budgets", [])),
        -_function_budget_overage(candidate, "function_lines"),
        -_function_budget_overage(candidate, "branch_node_count"),
        -_function_budget_overage(candidate, "parameter_count"),
        -int(value.get("function_lines", 0)),
        -int(value.get("branch_node_count", 0)),
        str(candidate.get("page", "")),
        int(candidate.get("line", 0)),
        str(candidate.get("symbol", "")),
    )


def _function_budget_top_n(
    candidates: list[dict[str, Any]],
    *,
    monitored_targets: set[str],
    top_n: int = FUNCTION_BUDGET_TOP_N,
) -> dict[str, Any]:
    ranked = sorted(candidates, key=_function_budget_sort_key)
    return {
        "top_n": top_n,
        "total_candidate_count": len(candidates),
        "monitored_candidate_count": sum(
            1 for candidate in candidates if candidate["page"] in monitored_targets
        ),
        "unmonitored_candidate_count": sum(
            1 for candidate in candidates if candidate["page"] not in monitored_targets
        ),
        "candidates": [
            {
                **candidate,
                "monitored": candidate["page"] in monitored_targets,
            }
            for candidate in ranked[:top_n]
        ],
    }


def _function_budget_monitoring(
    candidates: list[dict[str, Any]],
    *,
    monitored_targets: set[str],
) -> dict[str, Any]:
    monitored_count = sum(1 for candidate in candidates if candidate["page"] in monitored_targets)
    unmonitored_count = len(candidates) - monitored_count
    status = "attention" if unmonitored_count else "pass"
    return {
        "status": status,
        "gate_effect": "preview",
        "total_candidate_count": len(candidates),
        "monitored_candidate_count": monitored_count,
        "unmonitored_candidate_count": unmonitored_count,
        "monitored_target_count": len(monitored_targets),
        "summary": (
            "function budget candidates are covered by monitored target profiles"
            if status == "pass"
            else (
                f"{unmonitored_count} function budget candidate(s) are outside monitored "
                "structural profiles; review diagnostics.function_budget_top_n before "
                "promoting complexity gates."
            )
        ),
    }


def _monitored_targets(profiles: dict[str, dict[str, Any]]) -> set[str]:
    return {
        rel_path
        for profile in profiles.values()
        for rel_path in profile["targets"]
    }


def _monitored_function_candidates(
    function_candidates: list[dict[str, Any]],
    monitored_targets: set[str],
) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in function_candidates
        if candidate["page"] in monitored_targets
    ]


def _load_report_inputs(
    vault: Path,
    policy_path: str | None,
    *,
    context: RuntimeContext | None,
    target_profiles: dict[str, dict[str, Any]] | None,
    function_budget_config: dict[str, Any] | None,
) -> StructuralComplexityBudgetInputs:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    profiles = _normalize_target_profiles(target_profiles or DEFAULT_TARGET_PROFILES)
    function_config = function_budget_config or policy["system_refactor_policy"]["python_function_review"]
    function_candidates = python_function_budget_candidates(vault, function_config)
    monitored_targets = _monitored_targets(profiles)
    monitored_candidates = _monitored_function_candidates(function_candidates, monitored_targets)
    return StructuralComplexityBudgetInputs(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_context=context or RuntimeContext.from_policy(policy),
        profiles=profiles,
        state=MechanismAssessmentState(),
        function_candidates=function_candidates,
        monitored_targets=monitored_targets,
        candidate_by_page=_candidate_pages(monitored_candidates),
    )


def _missing_target_report(
    *,
    rel_path: str,
    profile_name: str,
    budgets: dict[str, int],
) -> dict[str, Any]:
    return {
        "path": rel_path,
        "profile": profile_name,
        "status": "fail",
        "metrics": {
            "nonempty_line_count_total": 0,
            "python_function_count": 0,
            "python_branch_node_count": 0,
            "markdown_heading_count": 0,
            "test_case_count": 0,
        },
        "budget": budgets,
        "budget_deltas": {
            "nonempty_line_count_total": -int(budgets["nonempty_line_count_total"]),
            "python_function_count": -int(budgets["python_function_count"]),
            "python_branch_node_count": -int(budgets["python_branch_node_count"]),
        },
        "over_budget_metrics": [],
        "function_budget_candidate_count": 0,
    }


def _target_report(
    vault: Path,
    inputs: StructuralComplexityBudgetInputs,
    *,
    profile_name: str,
    rel_path: str,
    budgets: dict[str, int],
) -> TargetReportResult:
    path = vault / rel_path
    if not path.exists():
        inputs.state.unreadable_targets.append({"path": rel_path, "reason": "missing_target"})
        return TargetReportResult(
            report=_missing_target_report(
                rel_path=rel_path,
                profile_name=profile_name,
                budgets=budgets,
            ),
            status="fail",
        )

    metrics = _measured_metrics(inputs.state, rel_path, path)
    budget_deltas = _budget_deltas(metrics, budgets)
    over_budget_metrics = [metric for metric, value in budget_deltas.items() if value > 0]
    candidate_count = len(inputs.candidate_by_page.get(rel_path, []))
    status = "warn" if over_budget_metrics or candidate_count else "pass"
    return TargetReportResult(
        report={
            "path": rel_path,
            "profile": profile_name,
            "status": status,
            "metrics": metrics,
            "budget": budgets,
            "budget_deltas": budget_deltas,
            "over_budget_metrics": over_budget_metrics,
            "function_budget_candidate_count": candidate_count,
        },
        status=status,
    )


def _target_reports(vault: Path, inputs: StructuralComplexityBudgetInputs) -> TargetReportSummary:
    reports: list[dict[str, Any]] = []
    attention_count = 0
    failure_count = 0
    for profile_name, profile in inputs.profiles.items():
        budgets = profile["budgets"]
        for rel_path in profile["targets"]:
            result = _target_report(
                vault,
                inputs,
                profile_name=profile_name,
                rel_path=rel_path,
                budgets=budgets,
            )
            reports.append(result.report)
            if result.status == "fail":
                failure_count += 1
            elif result.status == "warn":
                attention_count += 1
    return TargetReportSummary(
        reports=reports,
        attention_count=attention_count,
        failure_count=failure_count,
    )


def _report_diagnostics(inputs: StructuralComplexityBudgetInputs) -> dict[str, Any]:
    return {
        "unreadable_targets": inputs.state.unreadable_targets,
        "python_parse_failures": inputs.state.python_parse_failures,
        "function_budget_top_n": _function_budget_top_n(
            inputs.function_candidates,
            monitored_targets=inputs.monitored_targets,
        ),
        "function_budget_monitoring": _function_budget_monitoring(
            inputs.function_candidates,
            monitored_targets=inputs.monitored_targets,
        ),
    }


def _report_summary(
    inputs: StructuralComplexityBudgetInputs,
    target_summary: TargetReportSummary,
) -> dict[str, int]:
    return {
        "profile_count": len(inputs.profiles),
        "target_count": len(target_summary.reports),
        "targets_with_attention_count": target_summary.attention_count,
        "targets_with_failure_count": target_summary.failure_count,
        "function_budget_candidate_count": sum(len(items) for items in inputs.candidate_by_page.values()),
    }


def _assembled_report(
    vault: Path,
    inputs: StructuralComplexityBudgetInputs,
    target_summary: TargetReportSummary,
) -> dict[str, Any]:
    status = "fail" if target_summary.failure_count else (
        "attention" if target_summary.attention_count else "pass"
    )
    generated_at = inputs.runtime_context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="structural_complexity_budget_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA,
            source_paths=["ops/scripts/eval/structural_complexity_budget_runtime.py"],
            path_group_inputs={
                "monitored_targets": sorted(inputs.monitored_targets),
            },
            text_inputs={
                "profile_names": "\n".join(sorted(inputs.profiles)),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "status": status,
        "profiles": {
            profile_name: {
                "target_count": len(profile["targets"]),
                "budgets": profile["budgets"],
                "notes": profile["notes"],
            }
            for profile_name, profile in inputs.profiles.items()
        },
        "targets": target_summary.reports,
        "function_budget_candidates": _monitored_function_candidates(
            inputs.function_candidates,
            inputs.monitored_targets,
        ),
        "diagnostics": _report_diagnostics(inputs),
        "summary": _report_summary(inputs, target_summary),
    }


def _validate_report(vault: Path, report: dict[str, Any]) -> None:
    schema = load_schema_with_vault_override(vault, STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA)
    validate_or_raise(
        report,
        schema,
        context="structural complexity budget report schema validation failed",
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA,
            out_path=out_path,
            default_relative_path=DEFAULT_REPORT,
            context="structural complexity budget report schema validation failed",
        )
    )


def build_report(
    vault: Path,
    policy_path: str | None = None,
    *,
    context: RuntimeContext | None = None,
    target_profiles: dict[str, dict[str, Any]] | None = None,
    function_budget_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = _load_report_inputs(
        vault,
        policy_path,
        context=context,
        target_profiles=target_profiles,
        function_budget_config=function_budget_config,
    )
    report = _assembled_report(vault, inputs, _target_reports(vault, inputs))
    _validate_report(vault, report)
    return report
