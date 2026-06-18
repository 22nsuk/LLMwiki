from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.policy_runtime import report_path

from .mechanism_run_validation_runtime import (
    MechanismArtifactBundle,
    normalize_mechanism_artifact_bundle,
)
from .promotion_gate_common_runtime import (
    BEHAVIOR_DELTA_SCHEMA,
    CHANGED_FILES_MANIFEST_SCHEMA,
    EVAL_REPORT_SCHEMA,
    LINT_REPORT_SCHEMA,
    MECHANISM_REPORT_SCHEMA,
    RUN_LEDGER_SCHEMA,
    PromotionGateArtifactSchemaError,
    PromotionGateUsageError,
    configured_secondary_axes,
    lint_comparison_tuple,
    mechanism_target_matches,
    total_structural_metrics,
    validate_json_artifact,
)

MECHANISM_CONTRACT_EVAL_SCORE_SOURCE = "mechanism_contract_eval"
MISSING_MECHANISM_CONTRACT_EVAL_SCORE_SOURCE = "mechanism_contract_eval_missing"


@dataclass(frozen=True)
class MechanismGateInputs:
    baseline_eval_report: dict
    baseline_eval_rel: str
    candidate_eval_report: dict
    candidate_eval_rel: str
    baseline_lint_report: dict
    baseline_lint_rel: str
    candidate_lint_report: dict
    candidate_lint_rel: str
    baseline_mechanism_report: dict
    baseline_mechanism_rel: str
    candidate_mechanism_report: dict
    candidate_mechanism_rel: str
    changed_files_manifest_report: dict
    changed_files_manifest_rel: str
    run_ledger_report: dict
    run_ledger_rel: str
    behavior_delta_report: dict | None = None
    behavior_delta_rel: str = ""
    baseline_mechanism_contract_eval_report: dict | None = None
    baseline_mechanism_contract_eval_rel: str = ""
    candidate_mechanism_contract_eval_report: dict | None = None
    candidate_mechanism_contract_eval_rel: str = ""


@dataclass(frozen=True)
class MechanismGateInputRequest:
    vault: Path
    baseline_eval_path: str
    candidate_eval_path: str
    baseline_lint_path: str
    candidate_lint_path: str
    baseline_mechanism_path: str
    candidate_mechanism_path: str
    changed_files_manifest_path: str
    run_ledger_path: str
    behavior_delta_path: str | None = None
    baseline_mechanism_contract_eval_path: str | None = None
    candidate_mechanism_contract_eval_path: str | None = None


@dataclass(frozen=True)
class MechanismPromotionState:
    bundle: MechanismArtifactBundle
    expected_policy_path: str
    expected_policy_version: int | None
    invalid_targets: list[str]
    missing_targets: list[str]
    baseline_lint_pass: bool
    candidate_lint_pass: bool
    candidate_lint_accepted: bool
    baseline_eval_pass: bool
    candidate_eval_pass: bool
    candidate_eval_accepted: bool
    eval_score_source: str
    baseline_score_report: str
    candidate_score_report: str
    baseline_score: int
    candidate_score: int
    candidate_score_report_pass: bool
    global_baseline_score: int
    global_candidate_score: int
    global_eval_non_regression: bool
    global_eval_new_failure_count: int
    score_improves: bool
    score_equal: bool
    improvement_check_status: str
    lint_non_regression: bool
    lint_improves: bool
    structural_non_regression: bool
    structural_improves: bool
    nonempty_line_growth: int
    added_test_functions: int
    added_test_guardrails: int
    allowed_line_growth: int
    baseline_test_file_count: int
    candidate_test_file_count: int
    baseline_test_case_count: int
    candidate_test_case_count: int
    baseline_test_guardrail_count: int
    candidate_test_guardrail_count: int
    tests_non_regression: bool
    tests_increase: bool
    baseline_complexity_score: int
    candidate_complexity_score: int
    baseline_risk_flags: list[str]
    candidate_risk_flags: list[str]
    selected_secondary_axes: list[str]
    failed_secondary_axes: list[str]
    improved_secondary_axes: list[str]
    selected_non_regression: bool
    selected_any_improvement: bool
    equal_score_allowed: bool
    equal_score_secondary_eligibility: bool
    signoff_status: str
    signoff_check_status: str


@dataclass(frozen=True)
class TargetValidationState:
    invalid_targets: list[str]
    missing_targets: list[str]


@dataclass(frozen=True)
class ScoreState:
    baseline_eval_pass: bool
    candidate_eval_pass: bool
    eval_score_source: str
    baseline_score_report: str
    candidate_score_report: str
    baseline_score: int
    candidate_score: int
    candidate_score_report_pass: bool
    global_baseline_score: int
    global_candidate_score: int
    global_eval_non_regression: bool
    global_eval_new_failure_count: int
    score_improves: bool
    score_equal: bool
    improvement_check_status: str


@dataclass(frozen=True)
class LintState:
    baseline_lint_pass: bool
    candidate_lint_pass: bool
    non_regression: bool
    improves: bool


@dataclass(frozen=True)
class StructuralState:
    baseline_metrics: dict[str, int]
    candidate_metrics: dict[str, int]
    line_budget: EqualScoreLineBudgetState
    non_regression: bool
    improves: bool


@dataclass(frozen=True)
class EqualScoreLineBudgetState:
    nonempty_line_growth: int
    added_test_functions: int
    added_test_guardrails: int
    allowed_line_growth: int
    within_budget: bool


@dataclass(frozen=True)
class TestCoverageState:
    baseline_file_count: int
    candidate_file_count: int
    baseline_case_count: int
    candidate_case_count: int
    baseline_guardrail_count: int
    candidate_guardrail_count: int
    non_regression: bool
    increases: bool


@dataclass(frozen=True)
class RiskState:
    baseline_complexity_score: int
    candidate_complexity_score: int
    baseline_risk_flags: list[str]
    candidate_risk_flags: list[str]


@dataclass(frozen=True)
class SecondaryAxisState:
    selected_axes: list[str]
    failed_axes: list[str]
    improved_axes: list[str]
    selected_non_regression: bool
    selected_any_improvement: bool
    equal_score_allowed: bool
    equal_score_secondary_eligibility: bool


@dataclass(frozen=True)
class SignoffState:
    status: str
    check_status: str


STRUCTURAL_METRIC_KEYS = (
    "nonempty_line_count_total",
    "python_function_count",
    "python_branch_node_count",
    "markdown_heading_count",
)
SEMANTIC_STRUCTURAL_METRIC_KEYS = (
    "python_function_count",
    "python_branch_node_count",
    "markdown_heading_count",
)
MECHANISM_CONTRACT_EVAL_ARTIFACT_KIND = "mechanism_contract_eval_report"


_MECHANISM_GATE_INPUT_POSITIONAL_FIELDS = (
    "baseline_eval_path",
    "candidate_eval_path",
    "baseline_lint_path",
    "candidate_lint_path",
    "baseline_mechanism_path",
    "candidate_mechanism_path",
    "changed_files_manifest_path",
    "run_ledger_path",
    "behavior_delta_path",
)


def _require_mechanism_contract_eval_identity(report: dict, rel_path: str, *, phase: str) -> None:
    artifact_kind = report.get("artifact_kind")
    if artifact_kind != MECHANISM_CONTRACT_EVAL_ARTIFACT_KIND:
        raise PromotionGateArtifactSchemaError(
            f"{rel_path}: artifact_kind={artifact_kind!r}; "
            f"expected {MECHANISM_CONTRACT_EVAL_ARTIFACT_KIND!r}"
        )
    report_phase = report.get("phase")
    if report_phase != phase:
        raise PromotionGateArtifactSchemaError(
            f"{rel_path}: phase={report_phase!r}; expected {phase!r}"
        )


def collect_mechanism_gate_inputs(
    vault_or_request: Path | MechanismGateInputRequest,
    *legacy_args: Any,
    **legacy_fields: Any,
) -> MechanismGateInputs:
    request = _coerce_mechanism_gate_input_request(
        vault_or_request,
        legacy_args,
        legacy_fields,
    )
    return collect_mechanism_gate_inputs_from_request(request)


def _coerce_mechanism_gate_input_request(
    vault_or_request: Path | MechanismGateInputRequest,
    legacy_args: tuple[Any, ...],
    legacy_fields: dict[str, Any],
) -> MechanismGateInputRequest:
    if isinstance(vault_or_request, MechanismGateInputRequest):
        if legacy_args or legacy_fields:
            raise TypeError("collect_mechanism_gate_inputs accepts either a request object or legacy fields")
        return vault_or_request
    if len(legacy_args) > len(_MECHANISM_GATE_INPUT_POSITIONAL_FIELDS):
        raise TypeError("too many positional arguments for collect_mechanism_gate_inputs")
    fields = dict(legacy_fields)
    for name, value in zip(_MECHANISM_GATE_INPUT_POSITIONAL_FIELDS, legacy_args, strict=False):
        if name in fields:
            raise TypeError(f"collect_mechanism_gate_inputs got multiple values for argument '{name}'")
        fields[name] = value
    return MechanismGateInputRequest(vault=vault_or_request, **fields)


def _load_mechanism_contract_eval_pair(
    request: MechanismGateInputRequest,
) -> tuple[dict | None, str, dict | None, str]:
    baseline_path = request.baseline_mechanism_contract_eval_path
    candidate_path = request.candidate_mechanism_contract_eval_path
    if bool(baseline_path) != bool(candidate_path):
        raise PromotionGateUsageError(
            "mechanism contract eval requires both baseline and candidate reports"
        )
    if not baseline_path or not candidate_path:
        return None, "", None, ""

    baseline_report, baseline_rel = validate_json_artifact(
        request.vault,
        baseline_path,
        EVAL_REPORT_SCHEMA,
    )
    candidate_report, candidate_rel = validate_json_artifact(
        request.vault,
        candidate_path,
        EVAL_REPORT_SCHEMA,
    )
    _require_mechanism_contract_eval_identity(
        baseline_report,
        baseline_rel,
        phase="baseline",
    )
    _require_mechanism_contract_eval_identity(
        candidate_report,
        candidate_rel,
        phase="candidate",
    )
    return baseline_report, baseline_rel, candidate_report, candidate_rel


def collect_mechanism_gate_inputs_from_request(
    request: MechanismGateInputRequest,
) -> MechanismGateInputs:
    baseline_eval_report, baseline_eval_rel = validate_json_artifact(
        request.vault,
        request.baseline_eval_path,
        EVAL_REPORT_SCHEMA,
    )
    candidate_eval_report, candidate_eval_rel = validate_json_artifact(
        request.vault,
        request.candidate_eval_path,
        EVAL_REPORT_SCHEMA,
    )
    (
        baseline_mechanism_contract_eval_report,
        baseline_mechanism_contract_eval_rel,
        candidate_mechanism_contract_eval_report,
        candidate_mechanism_contract_eval_rel,
    ) = _load_mechanism_contract_eval_pair(request)
    baseline_lint_report, baseline_lint_rel = validate_json_artifact(
        request.vault,
        request.baseline_lint_path,
        LINT_REPORT_SCHEMA,
    )
    candidate_lint_report, candidate_lint_rel = validate_json_artifact(
        request.vault,
        request.candidate_lint_path,
        LINT_REPORT_SCHEMA,
    )
    baseline_mechanism_report, baseline_mechanism_rel = validate_json_artifact(
        request.vault,
        request.baseline_mechanism_path,
        MECHANISM_REPORT_SCHEMA,
    )
    candidate_mechanism_report, candidate_mechanism_rel = validate_json_artifact(
        request.vault,
        request.candidate_mechanism_path,
        MECHANISM_REPORT_SCHEMA,
    )
    changed_files_manifest_report, changed_files_manifest_rel = validate_json_artifact(
        request.vault,
        request.changed_files_manifest_path,
        CHANGED_FILES_MANIFEST_SCHEMA,
    )
    run_ledger_report, run_ledger_rel = validate_json_artifact(
        request.vault,
        request.run_ledger_path,
        RUN_LEDGER_SCHEMA,
    )
    behavior_delta_report = None
    behavior_delta_rel = ""
    if request.behavior_delta_path:
        behavior_delta_report, behavior_delta_rel = validate_json_artifact(
            request.vault,
            request.behavior_delta_path,
            BEHAVIOR_DELTA_SCHEMA,
        )
    return MechanismGateInputs(
        baseline_eval_report=baseline_eval_report,
        baseline_eval_rel=baseline_eval_rel,
        candidate_eval_report=candidate_eval_report,
        candidate_eval_rel=candidate_eval_rel,
        baseline_mechanism_contract_eval_report=baseline_mechanism_contract_eval_report,
        baseline_mechanism_contract_eval_rel=baseline_mechanism_contract_eval_rel,
        candidate_mechanism_contract_eval_report=candidate_mechanism_contract_eval_report,
        candidate_mechanism_contract_eval_rel=candidate_mechanism_contract_eval_rel,
        baseline_lint_report=baseline_lint_report,
        baseline_lint_rel=baseline_lint_rel,
        candidate_lint_report=candidate_lint_report,
        candidate_lint_rel=candidate_lint_rel,
        baseline_mechanism_report=baseline_mechanism_report,
        baseline_mechanism_rel=baseline_mechanism_rel,
        candidate_mechanism_report=candidate_mechanism_report,
        candidate_mechanism_rel=candidate_mechanism_rel,
        changed_files_manifest_report=changed_files_manifest_report,
        changed_files_manifest_rel=changed_files_manifest_rel,
        behavior_delta_report=behavior_delta_report,
        behavior_delta_rel=behavior_delta_rel,
        run_ledger_report=run_ledger_report,
        run_ledger_rel=run_ledger_rel,
    )


def mechanism_equal_score_decision(
    *,
    score_equal: bool,
    mutation_policy: dict,
    equal_score_policy: dict,
    selected_non_regression: bool,
    equal_score_secondary_eligibility: bool,
) -> str | None:
    if not score_equal or not mutation_policy["default_requires_eval_improvement"]:
        return None
    if equal_score_policy["require_secondary_non_regression"] and not selected_non_regression:
        return "DISCARD"
    if equal_score_policy["require_any_secondary_improvement"] and not equal_score_secondary_eligibility:
        return "DISCARD"
    return None


def mechanism_signoff_decision(
    *,
    decision_rules: dict,
    signoff_status: str,
) -> str | None:
    if signoff_status == "rejected":
        return "DISCARD"
    if decision_rules["hold_on_signoff_pending"] and signoff_status == "pending":
        return "HOLD"
    if decision_rules["promote_only_if_signoff_approved"] and signoff_status != "approved":
        return "HOLD"
    return None


def _target_validation_state(
    vault: Path,
    *,
    artifact_spec: dict,
    primary_targets: list[str],
) -> TargetValidationState:
    return TargetValidationState(
        invalid_targets=sorted(
            target for target in primary_targets if not mechanism_target_matches(target, artifact_spec)
        ),
        missing_targets=sorted(target for target in primary_targets if not (vault / target).exists()),
    )


def _eval_failure_keys(report: dict) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for page in report.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page") or "unknown")
        for result in page.get("results", []):
            if not isinstance(result, dict) or result.get("pass") is not False:
                continue
            eval_id = str(result.get("eval") or "unknown")
            keys.add((page_id, eval_id))
    return keys


def _score_source_reports(bundle: MechanismArtifactBundle) -> tuple[str, dict, dict]:
    if (
        isinstance(bundle.baseline_mechanism_contract_eval_report, dict)
        and isinstance(bundle.candidate_mechanism_contract_eval_report, dict)
    ):
        return (
            MECHANISM_CONTRACT_EVAL_SCORE_SOURCE,
            bundle.baseline_mechanism_contract_eval_report,
            bundle.candidate_mechanism_contract_eval_report,
        )
    return (
        MISSING_MECHANISM_CONTRACT_EVAL_SCORE_SOURCE,
        bundle.baseline_eval_report,
        bundle.candidate_eval_report,
    )


def _score_state(bundle: MechanismArtifactBundle) -> ScoreState:
    eval_score_source, baseline_score_report, candidate_score_report = _score_source_reports(bundle)
    mechanism_contract_eval_available = (
        eval_score_source == MECHANISM_CONTRACT_EVAL_SCORE_SOURCE
    )
    baseline_score = (
        baseline_score_report["total_score"] if mechanism_contract_eval_available else 0
    )
    candidate_score = (
        candidate_score_report["total_score"] if mechanism_contract_eval_available else 0
    )
    candidate_score_report_pass = (
        mechanism_contract_eval_available
        and candidate_score_report["status"] == "pass"
    )
    global_baseline_score = bundle.baseline_eval_report["total_score"]
    global_candidate_score = bundle.candidate_eval_report["total_score"]
    global_new_failures = _eval_failure_keys(bundle.candidate_eval_report) - _eval_failure_keys(
        bundle.baseline_eval_report
    )
    global_eval_non_regression = (
        global_candidate_score >= global_baseline_score
        and not (
            bundle.baseline_eval_report["status"] == "pass"
            and bundle.candidate_eval_report["status"] != "pass"
        )
        and not global_new_failures
    )
    score_improves = mechanism_contract_eval_available and candidate_score > baseline_score
    score_equal = mechanism_contract_eval_available and candidate_score == baseline_score
    if not mechanism_contract_eval_available or not candidate_score_report_pass:
        improvement_check_status = "FAIL"
    else:
        improvement_check_status = "PASS" if score_improves else ("WARN" if score_equal else "FAIL")
    return ScoreState(
        baseline_eval_pass=bundle.baseline_eval_report["status"] == "pass",
        candidate_eval_pass=bundle.candidate_eval_report["status"] == "pass",
        eval_score_source=eval_score_source,
        baseline_score_report=(
            "baseline_mechanism_contract_eval_report"
            if mechanism_contract_eval_available
            else "missing_mechanism_contract_eval_report"
        ),
        candidate_score_report=(
            "candidate_mechanism_contract_eval_report"
            if mechanism_contract_eval_available
            else "missing_mechanism_contract_eval_report"
        ),
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        candidate_score_report_pass=candidate_score_report_pass,
        global_baseline_score=global_baseline_score,
        global_candidate_score=global_candidate_score,
        global_eval_non_regression=global_eval_non_regression,
        global_eval_new_failure_count=len(global_new_failures),
        score_improves=score_improves,
        score_equal=score_equal,
        improvement_check_status=improvement_check_status,
    )


def _lint_state(bundle: MechanismArtifactBundle) -> LintState:
    candidate_lint = lint_comparison_tuple(bundle.candidate_lint_report)
    baseline_lint = lint_comparison_tuple(bundle.baseline_lint_report)
    return LintState(
        baseline_lint_pass=bundle.baseline_lint_report["status"] == "pass",
        candidate_lint_pass=bundle.candidate_lint_report["status"] == "pass",
        non_regression=candidate_lint <= baseline_lint,
        improves=candidate_lint < baseline_lint,
    )


def _candidate_lint_accepted(lint: LintState) -> bool:
    return lint.candidate_lint_pass or (not lint.baseline_lint_pass and lint.non_regression)


def _candidate_eval_accepted(score: ScoreState) -> bool:
    return score.global_eval_non_regression


def _equal_score_line_budget_state(
    *,
    baseline_metrics: dict[str, int],
    candidate_metrics: dict[str, int],
    equal_score_policy: dict,
) -> EqualScoreLineBudgetState:
    nonempty_line_growth = (
        candidate_metrics["nonempty_line_count_total"]
        - baseline_metrics["nonempty_line_count_total"]
    )
    added_test_functions = max(
        0,
        candidate_metrics["test_case_count"] - baseline_metrics["test_case_count"],
    )
    added_test_guardrails = max(
        0,
        candidate_metrics.get("test_guardrail_count", 0)
        - baseline_metrics.get("test_guardrail_count", 0),
    )
    line_budget_per_test_case = int(
        equal_score_policy.get("nonempty_line_growth_budget_per_added_test_case", 0)
    )
    allowed_line_growth = (
        added_test_functions + added_test_guardrails
    ) * line_budget_per_test_case
    return EqualScoreLineBudgetState(
        nonempty_line_growth=nonempty_line_growth,
        added_test_functions=added_test_functions,
        added_test_guardrails=added_test_guardrails,
        allowed_line_growth=allowed_line_growth,
        within_budget=nonempty_line_growth <= allowed_line_growth,
    )


def _structural_state(
    bundle: MechanismArtifactBundle,
    *,
    equal_score_policy: dict,
) -> StructuralState:
    baseline_metrics = total_structural_metrics(bundle.baseline_mechanism_report)
    candidate_metrics = total_structural_metrics(bundle.candidate_mechanism_report)
    semantic_non_regression = all(
        candidate_metrics[key] <= baseline_metrics[key] for key in SEMANTIC_STRUCTURAL_METRIC_KEYS
    )
    line_budget = _equal_score_line_budget_state(
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        equal_score_policy=equal_score_policy,
    )
    return StructuralState(
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        line_budget=line_budget,
        non_regression=semantic_non_regression and line_budget.within_budget,
        improves=any(candidate_metrics[key] < baseline_metrics[key] for key in STRUCTURAL_METRIC_KEYS),
    )


def _test_coverage_state(structural: StructuralState) -> TestCoverageState:
    baseline_file_count = structural.baseline_metrics["test_file_count"]
    candidate_file_count = structural.candidate_metrics["test_file_count"]
    baseline_case_count = structural.baseline_metrics["test_case_count"]
    candidate_case_count = structural.candidate_metrics["test_case_count"]
    baseline_guardrail_count = structural.baseline_metrics.get("test_guardrail_count", 0)
    candidate_guardrail_count = structural.candidate_metrics.get("test_guardrail_count", 0)
    return TestCoverageState(
        baseline_file_count=baseline_file_count,
        candidate_file_count=candidate_file_count,
        baseline_case_count=baseline_case_count,
        candidate_case_count=candidate_case_count,
        baseline_guardrail_count=baseline_guardrail_count,
        candidate_guardrail_count=candidate_guardrail_count,
        non_regression=(
            candidate_file_count >= baseline_file_count
            and candidate_case_count >= baseline_case_count
            and candidate_guardrail_count >= baseline_guardrail_count
        ),
        increases=(
            candidate_file_count > baseline_file_count
            or candidate_case_count > baseline_case_count
            or candidate_guardrail_count > baseline_guardrail_count
        ),
    )


def _risk_state(bundle: MechanismArtifactBundle) -> RiskState:
    baseline_profile = bundle.baseline_mechanism_report["complexity_profile"]
    candidate_profile = bundle.candidate_mechanism_report["complexity_profile"]
    return RiskState(
        baseline_complexity_score=baseline_profile["complexity_score"],
        candidate_complexity_score=candidate_profile["complexity_score"],
        baseline_risk_flags=baseline_profile["risk_flags"],
        candidate_risk_flags=candidate_profile["risk_flags"],
    )


def _secondary_axis_state(
    *,
    policy: dict,
    artifact_class: str,
    equal_score_policy: dict,
    score: ScoreState,
    lint: LintState,
    structural: StructuralState,
    tests: TestCoverageState,
) -> SecondaryAxisState:
    selected_axes = configured_secondary_axes(policy)
    axis_states = {
        "lint": {"non_regression": lint.non_regression, "improves": lint.improves},
        "complexity": {
            "non_regression": structural.non_regression,
            "improves": structural.improves,
        },
        "tests": {"non_regression": tests.non_regression, "improves": tests.increases},
    }
    selected_non_regression = all(axis_states[axis]["non_regression"] for axis in selected_axes)
    selected_any_improvement = any(axis_states[axis]["improves"] for axis in selected_axes)
    equal_score_allowed = artifact_class in equal_score_policy["allowed_artifact_classes"]
    return SecondaryAxisState(
        selected_axes=selected_axes,
        failed_axes=[
            axis for axis in selected_axes if not axis_states[axis]["non_regression"]
        ],
        improved_axes=[axis for axis in selected_axes if axis_states[axis]["improves"]],
        selected_non_regression=selected_non_regression,
        selected_any_improvement=selected_any_improvement,
        equal_score_allowed=equal_score_allowed,
        equal_score_secondary_eligibility=(
            equal_score_allowed
            and score.score_equal
            and _candidate_lint_accepted(lint)
            and _candidate_eval_accepted(score)
            and selected_non_regression
            and selected_any_improvement
        ),
    )


def _signoff_state(signoff: dict) -> SignoffState:
    signoff_status = signoff["status"]
    check_status = "PASS"
    if signoff_status == "pending":
        check_status = "WARN"
    elif signoff_status == "rejected":
        check_status = "FAIL"
    return SignoffState(status=signoff_status, check_status=check_status)


def build_mechanism_promotion_state(
    vault: Path,
    *,
    policy: dict,
    resolved_policy_path: Path,
    artifact_class: str,
    primary_targets: list[str],
    signoff: dict,
    inputs: MechanismGateInputs,
) -> MechanismPromotionState:
    artifact_spec = policy["promotion_policy"]["artifact_classes"][artifact_class]
    equal_score_policy = policy["equal_score_promotion"]
    bundle = normalize_mechanism_artifact_bundle(inputs)
    expected_policy_path = report_path(vault, resolved_policy_path)
    expected_policy_version = policy.get("version")
    targets = _target_validation_state(
        vault,
        artifact_spec=artifact_spec,
        primary_targets=primary_targets,
    )
    score = _score_state(bundle)
    lint = _lint_state(bundle)
    structural = _structural_state(bundle, equal_score_policy=equal_score_policy)
    tests = _test_coverage_state(structural)
    risk = _risk_state(bundle)
    candidate_lint_accepted = _candidate_lint_accepted(lint)
    candidate_eval_accepted = _candidate_eval_accepted(score)
    secondary = _secondary_axis_state(
        policy=policy,
        artifact_class=artifact_class,
        equal_score_policy=equal_score_policy,
        score=score,
        lint=lint,
        structural=structural,
        tests=tests,
    )
    signoff_state = _signoff_state(signoff)

    return MechanismPromotionState(
        bundle=bundle,
        expected_policy_path=expected_policy_path,
        expected_policy_version=expected_policy_version,
        invalid_targets=targets.invalid_targets,
        missing_targets=targets.missing_targets,
        baseline_lint_pass=lint.baseline_lint_pass,
        candidate_lint_pass=lint.candidate_lint_pass,
        candidate_lint_accepted=candidate_lint_accepted,
        baseline_eval_pass=score.baseline_eval_pass,
        candidate_eval_pass=score.candidate_eval_pass,
        candidate_eval_accepted=candidate_eval_accepted,
        eval_score_source=score.eval_score_source,
        baseline_score_report=score.baseline_score_report,
        candidate_score_report=score.candidate_score_report,
        baseline_score=score.baseline_score,
        candidate_score=score.candidate_score,
        candidate_score_report_pass=score.candidate_score_report_pass,
        global_baseline_score=score.global_baseline_score,
        global_candidate_score=score.global_candidate_score,
        global_eval_non_regression=score.global_eval_non_regression,
        global_eval_new_failure_count=score.global_eval_new_failure_count,
        score_improves=score.score_improves,
        score_equal=score.score_equal,
        improvement_check_status=score.improvement_check_status,
        lint_non_regression=lint.non_regression,
        lint_improves=lint.improves,
        structural_non_regression=structural.non_regression,
        structural_improves=structural.improves,
        nonempty_line_growth=structural.line_budget.nonempty_line_growth,
        added_test_functions=structural.line_budget.added_test_functions,
        added_test_guardrails=structural.line_budget.added_test_guardrails,
        allowed_line_growth=structural.line_budget.allowed_line_growth,
        baseline_test_file_count=tests.baseline_file_count,
        candidate_test_file_count=tests.candidate_file_count,
        baseline_test_case_count=tests.baseline_case_count,
        candidate_test_case_count=tests.candidate_case_count,
        baseline_test_guardrail_count=tests.baseline_guardrail_count,
        candidate_test_guardrail_count=tests.candidate_guardrail_count,
        tests_non_regression=tests.non_regression,
        tests_increase=tests.increases,
        baseline_complexity_score=risk.baseline_complexity_score,
        candidate_complexity_score=risk.candidate_complexity_score,
        baseline_risk_flags=risk.baseline_risk_flags,
        candidate_risk_flags=risk.candidate_risk_flags,
        selected_secondary_axes=secondary.selected_axes,
        failed_secondary_axes=secondary.failed_axes,
        improved_secondary_axes=secondary.improved_axes,
        selected_non_regression=secondary.selected_non_regression,
        selected_any_improvement=secondary.selected_any_improvement,
        equal_score_allowed=secondary.equal_score_allowed,
        equal_score_secondary_eligibility=secondary.equal_score_secondary_eligibility,
        signoff_status=signoff_state.status,
        signoff_check_status=signoff_state.check_status,
    )
