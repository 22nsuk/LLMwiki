from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    configured_secondary_axes,
    lint_comparison_tuple,
    mechanism_target_matches,
    total_structural_metrics,
    validate_json_artifact,
)


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
    baseline_score: int
    candidate_score: int
    score_improves: bool
    score_equal: bool
    improvement_check_status: str
    lint_non_regression: bool
    lint_improves: bool
    structural_non_regression: bool
    structural_improves: bool
    baseline_test_file_count: int
    candidate_test_file_count: int
    baseline_test_case_count: int
    candidate_test_case_count: int
    tests_non_regression: bool
    tests_increase: bool
    baseline_complexity_score: int
    candidate_complexity_score: int
    baseline_risk_flags: list[str]
    candidate_risk_flags: list[str]
    selected_secondary_axes: list[str]
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
    baseline_score: int
    candidate_score: int
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
    non_regression: bool
    improves: bool


@dataclass(frozen=True)
class TestCoverageState:
    baseline_file_count: int
    candidate_file_count: int
    baseline_case_count: int
    candidate_case_count: int
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


def collect_mechanism_gate_inputs(
    vault: Path,
    baseline_eval_path: str,
    candidate_eval_path: str,
    baseline_lint_path: str,
    candidate_lint_path: str,
    baseline_mechanism_path: str,
    candidate_mechanism_path: str,
    changed_files_manifest_path: str,
    run_ledger_path: str,
    behavior_delta_path: str | None = None,
) -> MechanismGateInputs:
    baseline_eval_report, baseline_eval_rel = validate_json_artifact(
        vault,
        baseline_eval_path,
        EVAL_REPORT_SCHEMA,
    )
    candidate_eval_report, candidate_eval_rel = validate_json_artifact(
        vault,
        candidate_eval_path,
        EVAL_REPORT_SCHEMA,
    )
    baseline_lint_report, baseline_lint_rel = validate_json_artifact(
        vault,
        baseline_lint_path,
        LINT_REPORT_SCHEMA,
    )
    candidate_lint_report, candidate_lint_rel = validate_json_artifact(
        vault,
        candidate_lint_path,
        LINT_REPORT_SCHEMA,
    )
    baseline_mechanism_report, baseline_mechanism_rel = validate_json_artifact(
        vault,
        baseline_mechanism_path,
        MECHANISM_REPORT_SCHEMA,
    )
    candidate_mechanism_report, candidate_mechanism_rel = validate_json_artifact(
        vault,
        candidate_mechanism_path,
        MECHANISM_REPORT_SCHEMA,
    )
    changed_files_manifest_report, changed_files_manifest_rel = validate_json_artifact(
        vault,
        changed_files_manifest_path,
        CHANGED_FILES_MANIFEST_SCHEMA,
    )
    run_ledger_report, run_ledger_rel = validate_json_artifact(
        vault,
        run_ledger_path,
        RUN_LEDGER_SCHEMA,
    )
    behavior_delta_report = None
    behavior_delta_rel = ""
    if behavior_delta_path:
        behavior_delta_report, behavior_delta_rel = validate_json_artifact(
            vault,
            behavior_delta_path,
            BEHAVIOR_DELTA_SCHEMA,
        )
    return MechanismGateInputs(
        baseline_eval_report=baseline_eval_report,
        baseline_eval_rel=baseline_eval_rel,
        candidate_eval_report=candidate_eval_report,
        candidate_eval_rel=candidate_eval_rel,
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


def _score_state(bundle: MechanismArtifactBundle) -> ScoreState:
    baseline_score = bundle.baseline_eval_report["total_score"]
    candidate_score = bundle.candidate_eval_report["total_score"]
    score_improves = candidate_score > baseline_score
    score_equal = candidate_score == baseline_score
    return ScoreState(
        baseline_eval_pass=bundle.baseline_eval_report["status"] == "pass",
        candidate_eval_pass=bundle.candidate_eval_report["status"] == "pass",
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        score_improves=score_improves,
        score_equal=score_equal,
        improvement_check_status="PASS" if score_improves else ("WARN" if score_equal else "FAIL"),
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
    return score.candidate_eval_pass or (
        not score.baseline_eval_pass and score.candidate_score >= score.baseline_score
    )


def _nonempty_line_growth_within_equal_score_budget(
    *,
    baseline_metrics: dict[str, int],
    candidate_metrics: dict[str, int],
    equal_score_policy: dict,
) -> bool:
    nonempty_line_growth = (
        candidate_metrics["nonempty_line_count_total"]
        - baseline_metrics["nonempty_line_count_total"]
    )
    if nonempty_line_growth <= 0:
        return True
    added_test_cases = max(
        0,
        candidate_metrics["test_case_count"] - baseline_metrics["test_case_count"],
    )
    line_budget_per_test_case = int(
        equal_score_policy.get("nonempty_line_growth_budget_per_added_test_case", 0)
    )
    return nonempty_line_growth <= added_test_cases * line_budget_per_test_case


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
    nonempty_line_non_regression = _nonempty_line_growth_within_equal_score_budget(
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        equal_score_policy=equal_score_policy,
    )
    return StructuralState(
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        non_regression=semantic_non_regression and nonempty_line_non_regression,
        improves=any(candidate_metrics[key] < baseline_metrics[key] for key in STRUCTURAL_METRIC_KEYS),
    )


def _test_coverage_state(structural: StructuralState) -> TestCoverageState:
    baseline_file_count = structural.baseline_metrics["test_file_count"]
    candidate_file_count = structural.candidate_metrics["test_file_count"]
    baseline_case_count = structural.baseline_metrics["test_case_count"]
    candidate_case_count = structural.candidate_metrics["test_case_count"]
    return TestCoverageState(
        baseline_file_count=baseline_file_count,
        candidate_file_count=candidate_file_count,
        baseline_case_count=baseline_case_count,
        candidate_case_count=candidate_case_count,
        non_regression=(
            candidate_file_count >= baseline_file_count
            and candidate_case_count >= baseline_case_count
        ),
        increases=(
            candidate_file_count > baseline_file_count
            or candidate_case_count > baseline_case_count
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
        baseline_score=score.baseline_score,
        candidate_score=score.candidate_score,
        score_improves=score.score_improves,
        score_equal=score.score_equal,
        improvement_check_status=score.improvement_check_status,
        lint_non_regression=lint.non_regression,
        lint_improves=lint.improves,
        structural_non_regression=structural.non_regression,
        structural_improves=structural.improves,
        baseline_test_file_count=tests.baseline_file_count,
        candidate_test_file_count=tests.candidate_file_count,
        baseline_test_case_count=tests.baseline_case_count,
        candidate_test_case_count=tests.candidate_case_count,
        tests_non_regression=tests.non_regression,
        tests_increase=tests.increases,
        baseline_complexity_score=risk.baseline_complexity_score,
        candidate_complexity_score=risk.candidate_complexity_score,
        baseline_risk_flags=risk.baseline_risk_flags,
        candidate_risk_flags=risk.candidate_risk_flags,
        selected_secondary_axes=secondary.selected_axes,
        selected_non_regression=secondary.selected_non_regression,
        selected_any_improvement=secondary.selected_any_improvement,
        equal_score_allowed=secondary.equal_score_allowed,
        equal_score_secondary_eligibility=secondary.equal_score_secondary_eligibility,
        signoff_status=signoff_state.status,
        signoff_check_status=signoff_state.check_status,
    )
