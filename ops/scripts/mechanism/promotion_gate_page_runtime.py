from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.rule_registry_runtime import (
    RuleMetadata,
    RuleSpec,
    collapse_rule_decision_contract,
    configured_rule_ids,
    configured_rule_metadata,
    evaluate_rule_registry,
    status_rule_reducer,
)
from ops.scripts.eval.wiki_eval import evaluate as evaluate_wiki
from ops.scripts.eval.wiki_lint import lint as lint_wiki
from ops.scripts.eval.wiki_stage2_eval import evaluate as evaluate_stage2

from .promotion_gate_common_runtime import (
    PROMOTION_REPORT_SCHEMA,
    PromotionGatePolicyError,
    build_history_status,
    decision_to_next_action,
    decision_to_outcome,
    eval_input_summary,
    extract_policy_identity,
    page_record_map,
    page_target_matches,
)


def _page_signoff_decision(
    *,
    decision_rules: dict,
    signoff: dict,
    signoff_status: str,
) -> str | None:
    if decision_rules["discard_on_signoff_rejected"] and signoff_status == "rejected":
        return "DISCARD"
    if (
        decision_rules["hold_on_required_signoff_pending"]
        and signoff["required"]
        and signoff_status == "pending"
    ):
        return "HOLD"
    return None


@dataclass(frozen=True)
class PageClassReportRequest:
    vault: Path
    run_id: str
    policy: dict
    resolved_policy_path: Path
    artifact_class: str
    primary_targets: list[str]
    supporting_targets: list[str]
    signoff: dict
    log: dict
    lint_report: dict
    eval_report: dict
    stage2_report: dict


@dataclass(frozen=True)
class PageClassReportContext:
    vault: Path
    run_id: str
    policy: dict
    artifact_class: str
    primary_targets: list[str]
    supporting_targets: list[str]
    signoff: dict
    log: dict
    lint_report: dict
    eval_report: dict
    stage2_report: dict
    decision_rules: dict
    expected_policy_path: str
    expected_policy_version: int | None
    invalid_targets: list[str]
    missing_targets: list[str]
    lint_status: str
    lint_policy_path: str | None
    lint_policy_version: int | None
    eval_policy_path: str | None
    eval_policy_version: int | None
    stage2_policy_path: str | None
    stage2_policy_version: int | None
    current_policy_consistent: bool
    failing_eval_targets: list[str]
    failing_stage2_targets: list[str]
    applicable_stage2_targets: list[str]
    signoff_status: str
    signoff_check_status: str


def _signoff_check_status(signoff_status: str) -> str:
    if signoff_status == "pending":
        return "WARN"
    if signoff_status == "rejected":
        return "FAIL"
    return "PASS"


def collect_page_gate_inputs(vault: Path, policy_path: str | None) -> tuple[dict, dict, dict]:
    return (
        lint_wiki(vault, policy_path),
        evaluate_wiki(vault, policy_path),
        evaluate_stage2(vault, policy_path),
    )


def _page_class_report_context(request: PageClassReportRequest) -> PageClassReportContext:
    artifact_spec = request.policy["promotion_policy"]["artifact_classes"][request.artifact_class]
    decision_rules = request.policy["promotion_policy"]["decision_rules"]["page_class"]
    eval_pages = page_record_map(request.vault, request.eval_report)
    stage2_pages = page_record_map(request.vault, request.stage2_report)
    expected_policy_path = report_path(request.vault, request.resolved_policy_path)
    expected_policy_version = request.policy.get("version")

    invalid_targets = sorted(
        target for target in request.primary_targets
        if not page_target_matches(target, artifact_spec)
    )
    missing_targets = sorted(
        target for target in request.primary_targets
        if not (request.vault / target).exists()
    )

    lint_status = request.lint_report["status"]
    lint_policy_path, lint_policy_version = extract_policy_identity(request.lint_report)
    eval_policy_path, eval_policy_version = extract_policy_identity(request.eval_report)
    stage2_policy_path, stage2_policy_version = extract_policy_identity(request.stage2_report)
    current_policy_consistent = (
        lint_policy_path == expected_policy_path
        and eval_policy_path == expected_policy_path
        and stage2_policy_path == expected_policy_path
        and lint_policy_version == expected_policy_version
        and eval_policy_version == expected_policy_version
        and stage2_policy_version == expected_policy_version
    )

    failing_eval_targets = []
    for target in request.primary_targets:
        page_report = eval_pages.get(target)
        if page_report is None or page_report["score"] != page_report["max_score"]:
            failing_eval_targets.append(target)

    failing_stage2_targets = []
    applicable_stage2_targets = []
    for target in request.primary_targets:
        page_report = stage2_pages.get(target)
        if page_report is None:
            continue
        applicable_stage2_targets.append(target)
        if page_report["score"] != page_report["max_score"]:
            failing_stage2_targets.append(target)

    signoff_status = request.signoff["status"]
    signoff_check_status = _signoff_check_status(signoff_status)

    return PageClassReportContext(
        vault=request.vault,
        run_id=request.run_id,
        policy=request.policy,
        artifact_class=request.artifact_class,
        primary_targets=request.primary_targets,
        supporting_targets=request.supporting_targets,
        signoff=request.signoff,
        log=request.log,
        lint_report=request.lint_report,
        eval_report=request.eval_report,
        stage2_report=request.stage2_report,
        decision_rules=decision_rules,
        expected_policy_path=expected_policy_path,
        expected_policy_version=expected_policy_version,
        invalid_targets=invalid_targets,
        missing_targets=missing_targets,
        lint_status=lint_status,
        lint_policy_path=lint_policy_path,
        lint_policy_version=lint_policy_version,
        eval_policy_path=eval_policy_path,
        eval_policy_version=eval_policy_version,
        stage2_policy_path=stage2_policy_path,
        stage2_policy_version=stage2_policy_version,
        current_policy_consistent=current_policy_consistent,
        failing_eval_targets=failing_eval_targets,
        failing_stage2_targets=failing_stage2_targets,
        applicable_stage2_targets=applicable_stage2_targets,
        signoff_status=signoff_status,
        signoff_check_status=signoff_check_status,
    )


PageClassRuleEvaluator = Callable[[PageClassReportContext], list[dict]]


def _primary_target_scope_checks(context: PageClassReportContext) -> list[dict]:
    return [
        {
            "id": "primary_target_scope",
            "status": "FAIL" if context.invalid_targets else "PASS",
            "detail": (
                "all primary targets match artifact-class scope"
                if not context.invalid_targets
                else f"invalid primary targets: {', '.join(context.invalid_targets)}"
            ),
        }
    ]


def _primary_target_exists_checks(context: PageClassReportContext) -> list[dict]:
    return [
        {
            "id": "primary_target_exists",
            "status": "FAIL" if context.missing_targets else "PASS",
            "detail": (
                "all primary targets exist"
                if not context.missing_targets
                else f"missing primary targets: {', '.join(context.missing_targets)}"
            ),
        }
    ]


def _repo_lint_status_checks(context: PageClassReportContext) -> list[dict]:
    return [
        {
            "id": "repo_lint_status",
            "status": (
                "PASS"
                if context.lint_status == "pass"
                else ("WARN" if context.lint_status == "warn" else "FAIL")
            ),
            "detail": (
                f"repo lint status={context.lint_status}; "
                f"errors={len(context.lint_report['errors'])}, "
                f"warnings={len(context.lint_report['warnings'])}"
            ),
        }
    ]


def _current_policy_consistency_checks(context: PageClassReportContext) -> list[dict]:
    return [
        {
            "id": "current_policy_consistency",
            "status": "PASS" if context.current_policy_consistent else "FAIL",
            "detail": (
                f"expected={context.expected_policy_path}@{context.expected_policy_version}, "
                f"lint={context.lint_policy_path}@{context.lint_policy_version}, "
                f"eval={context.eval_policy_path}@{context.eval_policy_version}, "
                f"stage2={context.stage2_policy_path}@{context.stage2_policy_version}"
            ),
        }
    ]


def _primary_target_eval_full_pass_checks(context: PageClassReportContext) -> list[dict]:
    return [
        {
            "id": "primary_target_eval_full_pass",
            "status": "FAIL" if context.failing_eval_targets else "PASS",
            "detail": (
                "all primary targets have full eval score"
                if not context.failing_eval_targets
                else f"targets without full eval score: {', '.join(context.failing_eval_targets)}"
            ),
        }
    ]


def _primary_target_stage2_full_pass_checks(context: PageClassReportContext) -> list[dict]:
    detail = (
        "all applicable primary targets have full Stage 2 eval score"
        if not context.failing_stage2_targets
        else f"targets without full Stage 2 eval score: {', '.join(context.failing_stage2_targets)}"
    )
    if not context.applicable_stage2_targets:
        detail += "; no Stage 2 checks applied to the selected primary targets"
    return [
        {
            "id": "primary_target_stage2_full_pass",
            "status": "FAIL" if context.failing_stage2_targets else "PASS",
            "detail": detail,
        }
    ]


def _signoff_status_checks(context: PageClassReportContext) -> list[dict]:
    return [
        {
            "id": "signoff_status",
            "status": context.signoff_check_status,
            "detail": (
                f"required={str(context.signoff['required']).lower()}, "
                f"status={context.signoff_status}"
            ),
        }
    ]


PAGE_CLASS_RULE_EVALUATORS: dict[str, PageClassRuleEvaluator] = {
    "primary_target_scope": _primary_target_scope_checks,
    "primary_target_exists": _primary_target_exists_checks,
    "repo_lint_status": _repo_lint_status_checks,
    "current_policy_consistency": _current_policy_consistency_checks,
    "primary_target_eval_full_pass": _primary_target_eval_full_pass_checks,
    "primary_target_stage2_full_pass": _primary_target_stage2_full_pass_checks,
    "signoff_status": _signoff_status_checks,
}


def _page_class_rule_reducer(
    context: PageClassReportContext,
    metadata: RuleMetadata,
) -> Callable[[list[dict]], str | None] | None:
    if metadata.reducer == "none":
        return None
    if metadata.reducer == "status_fail_discard":
        return status_rule_reducer(fail="DISCARD")
    if metadata.reducer == "page_repo_lint_status":
        if context.decision_rules["discard_on_repo_lint_fail"]:
            return status_rule_reducer(fail="DISCARD")
        return None
    if metadata.reducer == "page_primary_eval_status":
        if context.decision_rules["discard_on_primary_page_eval_not_max"]:
            return status_rule_reducer(fail="DISCARD")
        return None
    if metadata.reducer == "page_signoff_status":
        return lambda _checks: _page_signoff_decision(
            decision_rules=context.decision_rules,
            signoff=context.signoff,
            signoff_status=context.signoff_status,
        )
    raise PromotionGatePolicyError(
        f"unsupported page promotion rule reducer: {metadata.rule_id} -> {metadata.reducer}"
    )


def _page_class_rule_spec(
    context: PageClassReportContext,
    metadata: RuleMetadata,
) -> RuleSpec:
    evaluator = PAGE_CLASS_RULE_EVALUATORS.get(metadata.rule_id)
    if evaluator is None:
        raise PromotionGatePolicyError(
            f"promotion rule metadata references unknown page evaluator: {metadata.rule_id}"
        )

    def build_checks() -> list[dict]:
        return evaluator(context)

    return RuleSpec(
        rule_id=metadata.rule_id,
        build_checks=build_checks,
        reduce_decision=_page_class_rule_reducer(context, metadata),
        metadata=metadata,
    )


def _page_class_rule_registry(context: PageClassReportContext) -> dict[str, RuleSpec]:
    metadata_by_rule = configured_rule_metadata(context.policy, "page_class")
    return {
        rule_id: _page_class_rule_spec(context, metadata)
        for rule_id, metadata in metadata_by_rule.items()
    }


def _page_class_decision_contract(
    context: PageClassReportContext,
) -> tuple[list[dict], dict]:
    ordered_rule_ids = configured_rule_ids(context.policy, "page_class")
    available_rules = _page_class_rule_registry(context)
    checks, triggered_decisions = evaluate_rule_registry(ordered_rule_ids, available_rules)
    decision_contract = collapse_rule_decision_contract(
        triggered_decisions,
        subject_id=context.run_id,
        subject_kind=context.artifact_class,
        policy_version=context.policy.get("version"),
        source_pass="page_class",
        signoff=context.signoff,
    )
    return checks, decision_contract


def _assemble_page_class_report(
    context: PageClassReportContext,
    *,
    checks: list[dict],
    decision_contract: dict,
) -> dict:
    decision = decision_contract["decision"]

    return {
        "$schema": PROMOTION_REPORT_SCHEMA,
        "run_id": context.run_id,
        "mode": "report_only",
        "artifact_class": context.artifact_class,
        "decision": decision,
        "outcome": decision_to_outcome(decision),
        "decision_record": decision_contract["decision_record"],
        "decision_reduction": decision_contract["decision_reduction"],
        "summary": context.log["summary"],
        "primary_targets": context.primary_targets,
        "supporting_targets": context.supporting_targets,
        "checks": checks,
        "signoff": context.signoff,
        "log": context.log,
        "history": build_history_status(),
        "next_action": decision_to_next_action(
            decision,
            context.signoff["required"],
            context.log["required"],
        ),
        "inputs": {
            "current_lint": {
                "status": context.lint_report["status"],
                "error_count": len(context.lint_report["errors"]),
                "warning_count": len(context.lint_report["warnings"]),
                "review_candidate_count": len(context.lint_report["review_candidates"]),
            },
            "current_eval": eval_input_summary(context.eval_report),
            "current_stage2": eval_input_summary(context.stage2_report),
        },
    }


def page_class_report(request: PageClassReportRequest) -> dict:
    context = _page_class_report_context(request)
    checks, decision_contract = _page_class_decision_contract(context)
    return _assemble_page_class_report(
        context,
        checks=checks,
        decision_contract=decision_contract,
    )
