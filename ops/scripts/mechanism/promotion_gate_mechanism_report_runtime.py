from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from .promotion_gate_common_runtime import (
    PROMOTION_REPORT_SCHEMA,
    build_history_status,
    decision_to_next_action,
)
from .promotion_gate_mechanism_state_runtime import MechanismGateInputs


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

    @classmethod
    def from_gate_inputs(cls, inputs: MechanismGateInputs) -> MechanismReportInputsPayload:
        return cls(
            baseline_eval_report=inputs.baseline_eval_rel,
            candidate_eval_report=inputs.candidate_eval_rel,
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
        return report_inputs


def build_mechanism_report_inputs(inputs: MechanismGateInputs) -> dict:
    return MechanismReportInputsPayload.from_gate_inputs(inputs).to_wire()


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
