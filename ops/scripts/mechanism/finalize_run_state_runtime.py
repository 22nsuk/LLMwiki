from __future__ import annotations

import datetime as dt
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_event_from_record,
    decision_record_from_report,
)
from ops.scripts.core.runtime_context import RuntimeContext

from .finalize_run_artifact_runtime import PLANNING_VALIDATION_SCHEMA
from .finalize_run_errors_runtime import FinalizeRunUsageError
from .finalize_run_log_runtime import (
    resolve_finalize_log_state,
)


@dataclass(frozen=True)
class FinalizeLogState:
    required: bool
    entry_ref: str
    log_path: Path | None
    final_log_text: str | None


@dataclass(frozen=True)
class FinalizeRunOutputs:
    report: dict
    ledger: dict
    planning_validation: dict
    decision: str
    decision_record: dict
    log_state: FinalizeLogState


def finalize_allowed(report: dict) -> dict:
    try:
        decision_record = decision_record_from_report(report, require_record=True)
    except PromotionDecisionRegistryError as exc:
        raise FinalizeRunUsageError(str(exc)) from exc
    if not bool(decision_record.get("finalizable")):
        blockers = decision_record.get("finalize_blockers", [])
        blocker_text = ", ".join(str(item) for item in blockers) or "decision_not_finalizable"
        raise FinalizeRunUsageError(
            f"cannot finalize promotion decision {decision_record['decision']}: {blocker_text}"
        )
    signoff = report.get("signoff", {})
    if signoff.get("required") and signoff.get("status") != "approved":
        raise FinalizeRunUsageError("required signoff must be approved before finalization")
    return decision_record


def build_planning_validation_payload(
    *,
    run_id: str,
    decision: str,
    signoff: dict,
    log_required: bool,
    log_entry_ref: str,
) -> dict:
    log_detail = (
        f"append-only log entry was recorded at `{log_entry_ref}`."
        if log_required
        else "current policy does not require a system/system-log.md append for this finalized run."
    )
    return {
        "$schema": PLANNING_VALIDATION_SCHEMA,
        "run_id": run_id,
        "status": "PASS",
        "summary": (
            f"Mechanism run {run_id} is finalized with decision {decision}; "
            "baseline/candidate artifacts, promotion report, and run-ledger are now aligned."
        ),
        "checks": [
            {
                "id": "mechanism_artifacts_complete",
                "status": "PASS",
                "detail": "baseline/candidate eval, lint, and mechanism assessment artifacts are present under the same run directory.",
                "required_artifacts": [
                    "run-ledger.json",
                    "promotion-report.json",
                    "baseline-eval.json",
                    "candidate-eval.json",
                    "baseline-lint.json",
                    "candidate-lint.json",
                    "baseline-mechanism-assessment.json",
                    "candidate-mechanism-assessment.json",
                ],
            },
            {
                "id": "promotion_decision_finalized",
                "status": "PASS",
                "detail": f"promotion gate decision is finalized as `{decision}` and persisted in `promotion-report.json`.",
                "required_artifacts": [
                    "promotion-report.json",
                    "run-ledger.json",
                ],
            },
            {
                "id": "system_log_finalization",
                "status": "PASS",
                "detail": log_detail,
                "required_artifacts": [
                    "promotion-report.json",
                    "run-ledger.json",
                ],
            },
        ],
        "open_questions": [],
        "signoff": {
            "required": bool(signoff.get("required")),
            "status": signoff.get("status", ""),
            "by": signoff.get("by", ""),
            "ts": signoff.get("ts", ""),
        },
        "next_action": "Use this finalized run as future history input for mechanism_review and mutation_proposal.",
    }


def build_finalize_run_outputs(
    vault: Path,
    *,
    run_id: str,
    report: dict,
    ledger: dict,
    promotion_report_rel: str,
    run_ledger_rel: str,
    context: RuntimeContext,
    now: dt.datetime | None,
) -> FinalizeRunOutputs:
    mutable_report = deepcopy(report)
    mutable_ledger = deepcopy(ledger)
    decision_record = finalize_allowed(mutable_report)
    decision = decision_record["decision"]

    log_state, utc_ts = resolve_finalize_log_state(
        vault,
        report=mutable_report,
        run_id=run_id,
        decision=decision,
        promotion_report_rel=promotion_report_rel,
        run_ledger_rel=run_ledger_rel,
        context=context,
        now=now,
        log_state_factory=FinalizeLogState,
    )

    report_log = mutable_report.get("log", {})
    if not isinstance(report_log, dict):
        raise FinalizeRunUsageError("promotion report log must be an object")
    report_log["status"] = "recorded" if log_state.required else "not_required"
    report_log["entry_ref"] = log_state.entry_ref
    mutable_report["log"] = report_log
    mutable_report["next_action"] = (
        "Persist the finalized run artifacts and use them as future history inputs."
    )

    event_types = [
        event.get("type") for event in mutable_ledger.get("events", []) if isinstance(event, dict)
    ]
    if "promotion_evaluated" not in event_types:
        promotion_artifacts = [
            promotion_report_rel,
            *[
                value
                for key, value in sorted(mutable_report.get("inputs", {}).items())
                if isinstance(value, str) and value
            ],
        ]
        mutable_ledger["events"].append(
            {
                "ts": utc_ts,
                "type": "promotion_evaluated",
                "summary": f"Promotion gate finalized decision {decision} for {run_id}.",
                "artifacts": promotion_artifacts,
                "decision": decision,
                "decision_event": decision_event_from_record(
                    decision_record,
                    ledger_event_type="promotion_evaluated",
                    effective_at=utc_ts,
                ),
            }
        )

    if "finalized" not in event_types:
        finalized_artifacts = [promotion_report_rel, run_ledger_rel]
        if log_state.required:
            finalized_artifacts.append(report_log["page"])
        mutable_ledger["events"].append(
            {
                "ts": utc_ts,
                "type": "finalized",
                "summary": "Recorded the finalized mechanism run in system-log and persisted the promotion report.",
                "artifacts": finalized_artifacts,
                "decision": "complete",
                "decision_event": decision_event_from_record(
                    decision_record,
                    ledger_event_type="finalized",
                    effective_at=utc_ts,
                ),
            }
        )
    mutable_ledger["status"] = "complete"

    planning_validation = build_planning_validation_payload(
        run_id=run_id,
        decision=decision,
        signoff=mutable_report.get("signoff", {}),
        log_required=log_state.required,
        log_entry_ref=log_state.entry_ref,
    )
    return FinalizeRunOutputs(
        report=mutable_report,
        ledger=mutable_ledger,
        planning_validation=planning_validation,
        decision=decision,
        decision_record=decision_record,
        log_state=log_state,
    )
