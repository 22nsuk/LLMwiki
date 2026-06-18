from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.rule_registry_runtime import (
    RuleMetadata,
    RuleSpec,
    configured_rule_metadata,
    status_rule_reducer,
)

from .mechanism_run_validation_runtime import (
    MechanismArtifactBundle,
    build_behavior_delta_presence_check,
    build_changed_files_allowed_apply_roots_check,
    build_changed_files_nonempty_check,
    build_changed_files_primary_target_touched_check,
    build_changed_files_scope_gate_check,
    build_manifest_declared_targets_check,
    build_mechanism_primary_target_check,
    build_report_consistency_checks,
    build_run_ledger_target_coverage_check,
    mechanism_gate_check,
)
from .promotion_gate_common_runtime import (
    PromotionGatePolicyError,
    lint_comparison_tuple,
    report_target_list,
    total_structural_metric_tuple,
)
from .promotion_gate_mechanism_state_runtime import (
    MechanismGateInputs,
    MechanismPromotionState,
    mechanism_equal_score_decision,
    mechanism_signoff_decision,
)


@dataclass(frozen=True)
class _MechanismRuleRegistryContext:
    vault: Path
    run_id: str
    policy: dict
    primary_targets: list[str]
    supporting_targets: list[str]
    signoff: dict
    inputs: MechanismGateInputs
    state: MechanismPromotionState
    auto_improve_run: bool

    @property
    def bundle(self) -> MechanismArtifactBundle:
        return self.state.bundle

    @property
    def decision_rules(self) -> dict:
        return self.policy["promotion_policy"]["decision_rules"]["system_mechanism"]


MechanismRuleEvaluator = Callable[[_MechanismRuleRegistryContext], list[dict]]


def _primary_target_scope_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        mechanism_gate_check(
            "primary_target_scope",
            "FAIL" if state.invalid_targets else "PASS",
            (
                "all primary targets match artifact-class scope"
                if not state.invalid_targets
                else f"invalid primary targets: {', '.join(state.invalid_targets)}"
            ),
        )
    ]


def _primary_target_exists_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        mechanism_gate_check(
            "primary_target_exists",
            "FAIL" if state.missing_targets else "PASS",
            (
                "all primary targets exist"
                if not state.missing_targets
                else f"missing primary targets: {', '.join(state.missing_targets)}"
            ),
        )
    ]


def _report_consistency_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    bundle = ctx.bundle
    return build_report_consistency_checks(
        ctx.vault,
        bundle,
        run_id=ctx.run_id,
        expected_policy_path=ctx.state.expected_policy_path,
        expected_policy_version=ctx.state.expected_policy_version,
    )


def _run_ledger_target_coverage_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    bundle = ctx.bundle
    return [build_run_ledger_target_coverage_check(bundle, primary_targets=ctx.primary_targets)]


def _mechanism_report_primary_target_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    bundle = ctx.bundle
    return [build_mechanism_primary_target_check(bundle, primary_targets=ctx.primary_targets)]


def _changed_files_manifest_declared_target_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    bundle = ctx.bundle
    return [
        build_manifest_declared_targets_check(
            bundle,
            primary_targets=ctx.primary_targets,
            supporting_targets=ctx.supporting_targets,
            test_files=sorted(report_target_list(bundle.candidate_mechanism_report, "test_files")),
        )
    ]


def _changed_files_manifest_scope_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    return [build_changed_files_scope_gate_check(ctx.bundle)]


def _changed_files_manifest_allowed_apply_root_checks(
    ctx: _MechanismRuleRegistryContext,
) -> list[dict]:
    return [
        build_changed_files_allowed_apply_roots_check(
            ctx.bundle,
            allowed_apply_roots=ctx.policy["auto_improve_policy"]["allowed_apply_roots"],
        )
    ]


def _changed_files_manifest_nonempty_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    return [build_changed_files_nonempty_check(ctx.bundle)]


def _changed_files_manifest_primary_targets_touched_checks(
    ctx: _MechanismRuleRegistryContext,
) -> list[dict]:
    return [
        build_changed_files_primary_target_touched_check(
            ctx.bundle,
            primary_targets=ctx.primary_targets,
        )
    ]


def _behavior_delta_presence_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        build_behavior_delta_presence_check(
            ctx.policy,
            ctx.inputs.behavior_delta_report,
            auto_improve_run=ctx.auto_improve_run,
            score_equal=state.score_equal,
        )
    ]


def _candidate_lint_pass_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    bundle = ctx.bundle
    baseline_status = str(bundle.baseline_lint_report["status"])
    candidate_status = str(bundle.candidate_lint_report["status"])
    acceptance = (
        "candidate_pass"
        if state.candidate_lint_pass
        else "baseline_fail_non_regression"
        if state.candidate_lint_accepted
        else "not_accepted"
    )
    return [
        {
            "id": "candidate_lint_pass",
            "status": "PASS" if state.candidate_lint_accepted else "FAIL",
            "detail": (
                f"baseline lint status={baseline_status}, "
                f"candidate lint status={candidate_status}, "
                f"non_regression={str(state.lint_non_regression).lower()}, "
                f"acceptance={acceptance}"
            ),
        }
    ]


def _candidate_eval_pass_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    bundle = ctx.bundle
    baseline_status = str(bundle.baseline_eval_report["status"])
    candidate_status = str(bundle.candidate_eval_report["status"])
    acceptance = (
        "candidate_pass"
        if state.candidate_eval_pass
        else "baseline_fail_non_regression"
        if state.candidate_eval_accepted
        else "not_accepted"
    )
    return [
        {
            "id": "candidate_eval_pass",
            "status": "PASS" if state.candidate_eval_accepted else "FAIL",
            "detail": (
                f"baseline eval status={baseline_status}, "
                f"candidate eval status={candidate_status}, "
                "candidate eval "
                f"{bundle.candidate_eval_report['total_score']}/"
                f"{bundle.candidate_eval_report['max_score']}, "
                f"baseline={state.baseline_score}, candidate={state.candidate_score}, "
                f"acceptance={acceptance}"
            ),
        }
    ]


def _eval_score_improves_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "eval_score_improves",
            "status": state.improvement_check_status,
            "detail": f"baseline={state.baseline_score}, candidate={state.candidate_score}",
        }
    ]


def _lint_non_regression_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    bundle = ctx.bundle
    return [
        {
            "id": "lint_non_regression",
            "status": "PASS" if state.lint_non_regression else "FAIL",
            "detail": (
                f"baseline={lint_comparison_tuple(bundle.baseline_lint_report)}, "
                f"candidate={lint_comparison_tuple(bundle.candidate_lint_report)}"
            ),
        }
    ]


def _lint_improves_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    bundle = ctx.bundle
    return [
        {
            "id": "lint_improves",
            "status": "PASS" if state.lint_improves else "WARN",
            "detail": (
                f"baseline={lint_comparison_tuple(bundle.baseline_lint_report)}, "
                f"candidate={lint_comparison_tuple(bundle.candidate_lint_report)}"
            ),
        }
    ]


def _structural_complexity_non_regression_checks(
    ctx: _MechanismRuleRegistryContext,
) -> list[dict]:
    state = ctx.state
    bundle = ctx.bundle
    return [
        {
            "id": "structural_complexity_non_regression",
            "status": "PASS" if state.structural_non_regression else "FAIL",
            "detail": (
                f"baseline_total={total_structural_metric_tuple(bundle.baseline_mechanism_report)}, "
                f"candidate_total={total_structural_metric_tuple(bundle.candidate_mechanism_report)}"
            ),
        }
    ]


def _structural_complexity_improves_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    bundle = ctx.bundle
    return [
        {
            "id": "structural_complexity_improves",
            "status": "PASS" if state.structural_improves else "WARN",
            "detail": (
                f"baseline_total={total_structural_metric_tuple(bundle.baseline_mechanism_report)}, "
                f"candidate_total={total_structural_metric_tuple(bundle.candidate_mechanism_report)}"
            ),
        }
    ]


def _tests_non_regression_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "tests_non_regression",
            "status": "PASS" if state.tests_non_regression else "FAIL",
            "detail": (
                f"baseline=(files={state.baseline_test_file_count}, cases={state.baseline_test_case_count}), "
                f"candidate=(files={state.candidate_test_file_count}, cases={state.candidate_test_case_count})"
            ),
        }
    ]


def _tests_increase_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "tests_increase",
            "status": "PASS" if state.tests_increase else "WARN",
            "detail": (
                f"baseline=(files={state.baseline_test_file_count}, cases={state.baseline_test_case_count}), "
                f"candidate=(files={state.candidate_test_file_count}, cases={state.candidate_test_case_count})"
            ),
        }
    ]


def _complexity_profile_score_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "complexity_profile_score",
            "status": (
                "PASS"
                if state.candidate_complexity_score <= state.baseline_complexity_score
                else "WARN"
            ),
            "detail": (
                f"baseline={state.baseline_complexity_score}, "
                f"candidate={state.candidate_complexity_score}"
            ),
        }
    ]


def _risk_flag_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "risk_flags",
            "status": "WARN" if state.candidate_risk_flags else "PASS",
            "detail": f"baseline={state.baseline_risk_flags}, candidate={state.candidate_risk_flags}",
        }
    ]


def _equal_score_secondary_eligibility_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "equal_score_secondary_eligibility",
            "status": "PASS" if state.equal_score_secondary_eligibility else "WARN",
            "detail": (
                f"allowed={str(state.equal_score_allowed).lower()}, "
                f"score_equal={str(state.score_equal).lower()}, "
                f"selected_axes={state.selected_secondary_axes}, "
                f"candidate_lint_accepted={str(state.candidate_lint_accepted).lower()}, "
                f"candidate_eval_accepted={str(state.candidate_eval_accepted).lower()}, "
                f"selected_non_regression={str(state.selected_non_regression).lower()}, "
                f"selected_any_improvement={str(state.selected_any_improvement).lower()}"
            ),
        }
    ]


def _signoff_status_checks(ctx: _MechanismRuleRegistryContext) -> list[dict]:
    state = ctx.state
    return [
        {
            "id": "signoff_status",
            "status": state.signoff_check_status,
            "detail": f"required={str(ctx.signoff['required']).lower()}, status={state.signoff_status}",
        }
    ]


MECHANISM_RULE_EVALUATORS: dict[str, MechanismRuleEvaluator] = {
    "primary_target_scope": _primary_target_scope_checks,
    "primary_target_exists": _primary_target_exists_checks,
    "report_consistency": _report_consistency_checks,
    "run_ledger_target_coverage": _run_ledger_target_coverage_checks,
    "mechanism_report_primary_targets": _mechanism_report_primary_target_checks,
    "changed_files_manifest_declared_targets": _changed_files_manifest_declared_target_checks,
    "changed_files_manifest_scope": _changed_files_manifest_scope_checks,
    "changed_files_manifest_allowed_apply_roots": _changed_files_manifest_allowed_apply_root_checks,
    "changed_files_manifest_nonempty": _changed_files_manifest_nonempty_checks,
    "changed_files_manifest_primary_targets_touched": _changed_files_manifest_primary_targets_touched_checks,
    "behavior_delta_presence": _behavior_delta_presence_checks,
    "candidate_lint_pass": _candidate_lint_pass_checks,
    "candidate_eval_pass": _candidate_eval_pass_checks,
    "eval_score_improves": _eval_score_improves_checks,
    "lint_non_regression": _lint_non_regression_checks,
    "lint_improves": _lint_improves_checks,
    "structural_complexity_non_regression": _structural_complexity_non_regression_checks,
    "structural_complexity_improves": _structural_complexity_improves_checks,
    "tests_non_regression": _tests_non_regression_checks,
    "tests_increase": _tests_increase_checks,
    "complexity_profile_score": _complexity_profile_score_checks,
    "risk_flags": _risk_flag_checks,
    "equal_score_secondary_eligibility": _equal_score_secondary_eligibility_checks,
    "signoff_status": _signoff_status_checks,
}


def _mechanism_rule_reducer(
    ctx: _MechanismRuleRegistryContext,
    metadata: RuleMetadata,
) -> Callable[[list[dict]], str | None] | None:
    if metadata.reducer == "none":
        return None
    if metadata.reducer == "status_fail_discard":
        return status_rule_reducer(fail="DISCARD")
    if metadata.reducer == "candidate_lint_status":
        if ctx.decision_rules["discard_on_candidate_lint_not_pass"]:
            return status_rule_reducer(fail="DISCARD")
        return None
    if metadata.reducer == "candidate_eval_status":
        if ctx.decision_rules["discard_on_candidate_eval_not_pass"]:
            return status_rule_reducer(fail="DISCARD")
        return None
    if metadata.reducer == "equal_score_secondary":
        return lambda _checks: mechanism_equal_score_decision(
            score_equal=ctx.state.score_equal,
            mutation_policy=ctx.policy["mutation_policy"],
            equal_score_policy=ctx.policy["equal_score_promotion"],
            selected_non_regression=ctx.state.selected_non_regression,
            equal_score_secondary_eligibility=ctx.state.equal_score_secondary_eligibility,
        )
    if metadata.reducer == "signoff_status":
        return lambda _checks: mechanism_signoff_decision(
            decision_rules=ctx.decision_rules,
            signoff_status=ctx.state.signoff_status,
        )
    raise PromotionGatePolicyError(
        f"unsupported mechanism promotion rule reducer: {metadata.rule_id} -> {metadata.reducer}"
    )


def _mechanism_rule_spec(
    ctx: _MechanismRuleRegistryContext,
    metadata: RuleMetadata,
) -> RuleSpec:
    evaluator = MECHANISM_RULE_EVALUATORS.get(metadata.rule_id)
    if evaluator is None:
        raise PromotionGatePolicyError(
            f"promotion rule metadata references unknown mechanism evaluator: {metadata.rule_id}"
        )

    def build_checks() -> list[dict]:
        return evaluator(ctx)

    return RuleSpec(
        rule_id=metadata.rule_id,
        build_checks=build_checks,
        reduce_decision=_mechanism_rule_reducer(ctx, metadata),
        metadata=metadata,
    )


def build_mechanism_rule_registry(
    vault: Path,
    *,
    run_id: str,
    policy: dict,
    primary_targets: list[str],
    supporting_targets: list[str],
    signoff: dict,
    inputs: MechanismGateInputs,
    state: MechanismPromotionState,
    auto_improve_run: bool,
) -> dict[str, RuleSpec]:
    ctx = _MechanismRuleRegistryContext(
        vault=vault,
        run_id=run_id,
        policy=policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        signoff=signoff,
        inputs=inputs,
        state=state,
        auto_improve_run=auto_improve_run,
    )
    metadata_by_rule = configured_rule_metadata(policy, "system_mechanism")
    return {
        rule_id: _mechanism_rule_spec(ctx, metadata)
        for rule_id, metadata in metadata_by_rule.items()
    }
