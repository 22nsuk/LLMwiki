from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from .promotion_gate_common_runtime import (
    PROMOTION_REPORT_SCHEMA,
    build_history_status,
    decision_to_next_action,
    decision_to_outcome,
)
from .promotion_gate_mechanism_state_runtime import (
    MECHANISM_CONTRACT_EVAL_SCORE_SOURCE,
    MISSING_MECHANISM_CONTRACT_EVAL_SCORE_SOURCE,
    MechanismGateInputs,
)


@dataclass(frozen=True)
class MechanismPromotionReportAssemblyRequest:
    run_id: str
    artifact_class: str
    primary_targets: list[str]
    supporting_targets: list[str]
    signoff: dict
    log: dict
    inputs: MechanismGateInputs
    checks: list[dict]
    decision: str
    decision_record: dict | None = None
    decision_reduction: dict | None = None


@dataclass(frozen=True)
class MechanismReportInputsPayload:
    baseline_eval_report: str
    candidate_eval_report: str
    baseline_lint_report: str
    candidate_lint_report: str
    baseline_mechanism_report: str
    candidate_mechanism_report: str
    changed_files_manifest: str
    run_ledger: str
    behavior_delta: str = ""
    baseline_mechanism_contract_eval_report: str = ""
    candidate_mechanism_contract_eval_report: str = ""

    @classmethod
    def from_gate_inputs(cls, inputs: MechanismGateInputs) -> MechanismReportInputsPayload:
        return cls(
            baseline_eval_report=inputs.baseline_eval_rel,
            candidate_eval_report=inputs.candidate_eval_rel,
            baseline_mechanism_contract_eval_report=(
                inputs.baseline_mechanism_contract_eval_rel
            ),
            candidate_mechanism_contract_eval_report=(
                inputs.candidate_mechanism_contract_eval_rel
            ),
            baseline_lint_report=inputs.baseline_lint_rel,
            candidate_lint_report=inputs.candidate_lint_rel,
            baseline_mechanism_report=inputs.baseline_mechanism_rel,
            candidate_mechanism_report=inputs.candidate_mechanism_rel,
            changed_files_manifest=inputs.changed_files_manifest_rel,
            run_ledger=inputs.run_ledger_rel,
            behavior_delta=inputs.behavior_delta_rel,
        )

    def to_wire(self) -> dict[str, str]:
        report_inputs = {
            "baseline_eval_report": self.baseline_eval_report,
            "candidate_eval_report": self.candidate_eval_report,
            "baseline_lint_report": self.baseline_lint_report,
            "candidate_lint_report": self.candidate_lint_report,
            "baseline_mechanism_report": self.baseline_mechanism_report,
            "candidate_mechanism_report": self.candidate_mechanism_report,
            "changed_files_manifest": self.changed_files_manifest,
            "run_ledger": self.run_ledger,
        }
        if self.behavior_delta:
            report_inputs["behavior_delta"] = self.behavior_delta
        if self.baseline_mechanism_contract_eval_report:
            report_inputs["baseline_mechanism_contract_eval_report"] = (
                self.baseline_mechanism_contract_eval_report
            )
        if self.candidate_mechanism_contract_eval_report:
            report_inputs["candidate_mechanism_contract_eval_report"] = (
                self.candidate_mechanism_contract_eval_report
            )
        return report_inputs


def build_mechanism_report_inputs(inputs: MechanismGateInputs) -> dict:
    return MechanismReportInputsPayload.from_gate_inputs(inputs).to_wire()


def _eval_failure_counts(report: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for page in report.get("pages", []):
        if not isinstance(page, dict):
            continue
        for result in page.get("results", []):
            if not isinstance(result, dict) or result.get("pass") is not False:
                continue
            eval_id = str(result.get("eval") or "unknown")
            counts[eval_id] = counts.get(eval_id, 0) + 1
    return dict(sorted(counts.items()))


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


def _failed_page_count(report: dict) -> int:
    failed_pages = 0
    for page in report.get("pages", []):
        if not isinstance(page, dict):
            continue
        if any(
            isinstance(result, dict) and result.get("pass") is False
            for result in page.get("results", [])
        ):
            failed_pages += 1
    return failed_pages


def _failure_count_items(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"eval": eval_id, "count": count} for eval_id, count in counts.items()]


def _failure_delta_items(
    baseline_counts: dict[str, int],
    candidate_counts: dict[str, int],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for eval_id in sorted(set(baseline_counts) | set(candidate_counts)):
        baseline_count = baseline_counts.get(eval_id, 0)
        candidate_count = candidate_counts.get(eval_id, 0)
        delta = candidate_count - baseline_count
        if delta != 0:
            items.append(
                {
                    "eval": eval_id,
                    "baseline_count": baseline_count,
                    "candidate_count": candidate_count,
                    "delta": delta,
                }
            )
    return items


def _global_eval_delta(inputs: MechanismGateInputs) -> dict[str, Any]:
    baseline = inputs.baseline_eval_report
    candidate = inputs.candidate_eval_report
    return {
        "baseline_status": baseline["status"],
        "candidate_status": candidate["status"],
        "baseline_total_score": baseline["total_score"],
        "candidate_total_score": candidate["total_score"],
        "total_score_delta": candidate["total_score"] - baseline["total_score"],
        "baseline_max_score": baseline["max_score"],
        "candidate_max_score": candidate["max_score"],
        "max_score_delta": candidate["max_score"] - baseline["max_score"],
        "score_regressed": candidate["total_score"] < baseline["total_score"],
        "status_regressed": baseline["status"] == "pass" and candidate["status"] != "pass",
    }


def _global_eval_failure_summary(inputs: MechanismGateInputs) -> dict[str, Any]:
    baseline_counts = _eval_failure_counts(inputs.baseline_eval_report)
    candidate_counts = _eval_failure_counts(inputs.candidate_eval_report)
    baseline_failure_keys = _eval_failure_keys(inputs.baseline_eval_report)
    candidate_failure_keys = _eval_failure_keys(inputs.candidate_eval_report)
    baseline_failed_checks = sum(baseline_counts.values())
    candidate_failed_checks = sum(candidate_counts.values())
    baseline_failed_pages = _failed_page_count(inputs.baseline_eval_report)
    candidate_failed_pages = _failed_page_count(inputs.candidate_eval_report)
    return {
        "baseline_failed_check_count": baseline_failed_checks,
        "candidate_failed_check_count": candidate_failed_checks,
        "failed_check_delta": candidate_failed_checks - baseline_failed_checks,
        "baseline_failed_page_count": baseline_failed_pages,
        "candidate_failed_page_count": candidate_failed_pages,
        "failed_page_delta": candidate_failed_pages - baseline_failed_pages,
        "baseline_failures_by_eval": _failure_count_items(baseline_counts),
        "candidate_failures_by_eval": _failure_count_items(candidate_counts),
        "changed_failures_by_eval": _failure_delta_items(baseline_counts, candidate_counts),
        "candidate_new_failure_count": len(candidate_failure_keys - baseline_failure_keys),
        "candidate_resolved_failure_count": len(baseline_failure_keys - candidate_failure_keys),
    }


CONTENT_CORPUS_EVAL_IDS = frozenset({"source_page_substance"})


def _count_selected_eval_failures(counts: dict[str, int], selected: set[str] | frozenset[str]) -> int:
    return sum(count for eval_id, count in counts.items() if eval_id in selected)


def _global_eval_lane_summary(inputs: MechanismGateInputs) -> dict[str, Any]:
    baseline_counts = _eval_failure_counts(inputs.baseline_eval_report)
    candidate_counts = _eval_failure_counts(inputs.candidate_eval_report)
    baseline_content_backlog = _count_selected_eval_failures(
        baseline_counts,
        CONTENT_CORPUS_EVAL_IDS,
    )
    candidate_content_backlog = _count_selected_eval_failures(
        candidate_counts,
        CONTENT_CORPUS_EVAL_IDS,
    )
    candidate_new_failure_keys = _eval_failure_keys(inputs.candidate_eval_report) - _eval_failure_keys(
        inputs.baseline_eval_report
    )
    content_eval_ids = sorted(CONTENT_CORPUS_EVAL_IDS & set(candidate_counts))
    return {
        "global_eval_role": "non_regression_guard",
        "content_corpus_eval_ids": sorted(CONTENT_CORPUS_EVAL_IDS),
        "candidate_content_corpus_backlog_count": candidate_content_backlog,
        "content_corpus_backlog_delta": candidate_content_backlog - baseline_content_backlog,
        "content_corpus_backlog_like": candidate_content_backlog > 0
        and not candidate_new_failure_keys,
        "content_corpus_backlog_evals_present": content_eval_ids,
        "mechanism_local_failure_count": sum(
            count for eval_id, count in candidate_counts.items() if eval_id not in CONTENT_CORPUS_EVAL_IDS
        ),
        "mechanism_local_new_failure_count": len(
            {
                key
                for key in candidate_new_failure_keys
                if key[1] not in CONTENT_CORPUS_EVAL_IDS
            }
        ),
        "recommended_lane": (
            "content_corpus"
            if candidate_content_backlog > 0 and not candidate_new_failure_keys
            else "mechanism_or_global_regression"
            if candidate_new_failure_keys
            else "none"
        ),
    }


def _mechanism_contract_eval_delta(inputs: MechanismGateInputs) -> dict[str, Any]:
    baseline = inputs.baseline_mechanism_contract_eval_report
    candidate = inputs.candidate_mechanism_contract_eval_report
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return {
            "source": "missing",
            "score_source": MISSING_MECHANISM_CONTRACT_EVAL_SCORE_SOURCE,
            "baseline_report": "",
            "candidate_report": "",
            "baseline_status": "",
            "candidate_status": "",
            "baseline_total_score": 0,
            "candidate_total_score": 0,
            "total_score_delta": 0,
            "score_improves": False,
            "score_equal": False,
        }
    delta = candidate["total_score"] - baseline["total_score"]
    return {
        "source": "provided",
        "score_source": MECHANISM_CONTRACT_EVAL_SCORE_SOURCE,
        "baseline_report": inputs.baseline_mechanism_contract_eval_rel,
        "candidate_report": inputs.candidate_mechanism_contract_eval_rel,
        "baseline_status": baseline["status"],
        "candidate_status": candidate["status"],
        "baseline_total_score": baseline["total_score"],
        "candidate_total_score": candidate["total_score"],
        "total_score_delta": delta,
        "score_improves": delta > 0,
        "score_equal": delta == 0,
    }


def _candidate_failure_mode(
    *,
    delta: dict[str, Any],
    failure_summary: dict[str, Any],
) -> str:
    if delta["candidate_status"] == "pass":
        return "candidate_clean"
    if delta["score_regressed"] or delta["status_regressed"] or failure_summary["candidate_new_failure_count"] > 0:
        return "candidate_regression"
    return "baseline_backlog_non_regression"


def build_mechanism_report_diagnostics(
    artifact_class: str,
    inputs: MechanismGateInputs,
) -> dict[str, Any]:
    delta = _global_eval_delta(inputs)
    failure_summary = _global_eval_failure_summary(inputs)
    lane_summary = _global_eval_lane_summary(inputs)
    contract_eval = _mechanism_contract_eval_delta(inputs)
    failure_mode = _candidate_failure_mode(delta=delta, failure_summary=failure_summary)
    mechanism_class = artifact_class == "system_mechanism"
    local_eval_available = contract_eval["source"] == "provided"
    return {
        "global_eval_delta": delta,
        "global_eval_failure_summary": failure_summary,
        "global_eval_lane_summary": lane_summary,
        "mechanism_contract_eval": contract_eval,
        "mechanism_eval_applicability": {
            "artifact_class": artifact_class,
            "classification": (
                "mechanism_contract_eval"
                if mechanism_class and local_eval_available
                else "global_health_guard_only"
                if mechanism_class
                else "direct_eval_signal"
            ),
            "candidate_failure_mode": failure_mode,
            "candidate_regression": failure_mode == "candidate_regression",
            "corpus_backlog_like": failure_mode == "baseline_backlog_non_regression",
            "reason": (
                "mechanism_contract_eval scores changed targets, behavior-delta, "
                "promotion contract, and telemetry/schema contract while wiki_eval remains "
                "a global non-regression guard"
                if mechanism_class and local_eval_available
                else
                "mechanism_contract_eval pair is missing, so wiki_eval remains only "
                "a global non-regression health guard and cannot authorize promotion"
                if mechanism_class
                else "wiki_eval directly applies to page-class promotion candidates"
            ),
        },
    }


def assemble_mechanism_promotion_report(
    *args: object,
    request: MechanismPromotionReportAssemblyRequest | None = None,
    **kwargs: object,
) -> dict:
    request = _coerce_mechanism_promotion_report_assembly_request(
        request=request,
        args=args,
        kwargs=kwargs,
    )
    report = {
        "$schema": PROMOTION_REPORT_SCHEMA,
        "run_id": request.run_id,
        "mode": "report_only",
        "artifact_class": request.artifact_class,
        "decision": request.decision,
        "outcome": decision_to_outcome(request.decision),
        "summary": request.log["summary"],
        "primary_targets": request.primary_targets,
        "supporting_targets": request.supporting_targets,
        "checks": request.checks,
        "signoff": request.signoff,
        "log": request.log,
        "history": build_history_status(),
        "next_action": decision_to_next_action(
            request.decision,
            request.signoff["required"],
            request.log["required"],
        ),
        "inputs": build_mechanism_report_inputs(request.inputs),
        "diagnostics": build_mechanism_report_diagnostics(
            request.artifact_class,
            request.inputs,
        ),
    }
    if request.decision_record is not None:
        report["decision_record"] = request.decision_record
    if request.decision_reduction is not None:
        report["decision_reduction"] = request.decision_reduction
    return report


def _coerce_mechanism_promotion_report_assembly_request(
    *,
    request: MechanismPromotionReportAssemblyRequest | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> MechanismPromotionReportAssemblyRequest:
    if request is not None:
        if args or kwargs:
            raise TypeError("request cannot be combined with positional or keyword report fields")
        return request

    field_names = [
        "run_id",
        "artifact_class",
        "primary_targets",
        "supporting_targets",
        "signoff",
        "log",
        "inputs",
        "checks",
        "decision",
        "decision_record",
        "decision_reduction",
    ]
    if len(args) > len(field_names):
        raise TypeError(f"expected at most {len(field_names)} positional arguments")
    values = dict(zip(field_names, args, strict=False))
    values.update(kwargs)
    missing = [
        name
        for name in (
            "run_id",
            "artifact_class",
            "primary_targets",
            "supporting_targets",
            "signoff",
            "log",
            "inputs",
            "checks",
            "decision",
        )
        if name not in values
    ]
    if missing:
        raise TypeError(f"missing mechanism promotion report fields: {', '.join(missing)}")
    return MechanismPromotionReportAssemblyRequest(
        run_id=str(values["run_id"]),
        artifact_class=str(values["artifact_class"]),
        primary_targets=cast(list[str], values["primary_targets"]),
        supporting_targets=cast(list[str], values["supporting_targets"]),
        signoff=cast(dict, values["signoff"]),
        log=cast(dict, values["log"]),
        inputs=cast(MechanismGateInputs, values["inputs"]),
        checks=cast(list[dict], values["checks"]),
        decision=str(values["decision"]),
        decision_record=cast(dict | None, values.get("decision_record")),
        decision_reduction=cast(dict | None, values.get("decision_reduction")),
    )
