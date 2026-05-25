from __future__ import annotations

import datetime as dt
from pathlib import Path

from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext

from . import finalize_run_artifact_runtime as finalize_run_artifact_runtime
from . import finalize_run_errors_runtime as finalize_run_errors_runtime
from . import finalize_run_state_runtime as finalize_run_state_runtime
from . import finalize_run_write_runtime as finalize_run_write_runtime

CHANGED_FILES_MANIFEST_SCHEMA = finalize_run_artifact_runtime.CHANGED_FILES_MANIFEST_SCHEMA
PROMOTION_REPORT_SCHEMA = finalize_run_artifact_runtime.PROMOTION_REPORT_SCHEMA
RUN_LEDGER_SCHEMA = finalize_run_artifact_runtime.RUN_LEDGER_SCHEMA
PLANNING_VALIDATION_SCHEMA = finalize_run_artifact_runtime.PLANNING_VALIDATION_SCHEMA

FinalizeRunError = finalize_run_errors_runtime.FinalizeRunError
FinalizeRunUsageError = finalize_run_errors_runtime.FinalizeRunUsageError
FinalizeRunArtifactMissingError = finalize_run_errors_runtime.FinalizeRunArtifactMissingError
FinalizeRunArtifactDecodeError = finalize_run_errors_runtime.FinalizeRunArtifactDecodeError
FinalizeRunArtifactSchemaError = finalize_run_errors_runtime.FinalizeRunArtifactSchemaError
FinalizeRunWriteError = finalize_run_errors_runtime.FinalizeRunWriteError


def finalize_run(
    vault: Path,
    run_id: str,
    *,
    promotion_report_rel: str | None = None,
    run_ledger_rel: str | None = None,
    now: dt.datetime | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    policy, _ = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    promotion_rel = promotion_report_rel or f"runs/{run_id}/promotion-report.json"
    ledger_rel = run_ledger_rel or f"runs/{run_id}/run-ledger.json"
    planning_rel = f"runs/{run_id}/planning-validation.json"
    promotion_path = (vault / promotion_rel).resolve()
    ledger_path = (vault / ledger_rel).resolve()
    planning_path = (vault / planning_rel).resolve()

    report = finalize_run_artifact_runtime.load_validated_json(
        vault,
        promotion_path,
        PROMOTION_REPORT_SCHEMA,
        context=f"schema validation failed for {promotion_rel}",
    )
    ledger = finalize_run_artifact_runtime.load_validated_json(
        vault,
        ledger_path,
        RUN_LEDGER_SCHEMA,
        context=f"schema validation failed for {ledger_rel}",
    )

    if report["run_id"] != run_id:
        raise FinalizeRunUsageError(
            f"promotion report run_id mismatch: expected {run_id}, got {report['run_id']}"
        )
    if ledger["run_id"] != run_id:
        raise FinalizeRunUsageError(
            f"run-ledger run_id mismatch: expected {run_id}, got {ledger['run_id']}"
        )

    outputs = finalize_run_state_runtime.build_finalize_run_outputs(
        vault,
        run_id=run_id,
        report=report,
        ledger=ledger,
        promotion_report_rel=promotion_rel,
        run_ledger_rel=ledger_rel,
        context=runtime_context,
        now=now,
    )
    finalize_run_artifact_runtime.validate_finalize_payloads(
        vault,
        report=outputs.report,
        ledger=outputs.ledger,
        planning_validation=outputs.planning_validation,
    )
    finalize_run_write_runtime.write_finalize_atomic_updates(
        finalize_run_write_runtime.build_finalize_atomic_updates(
            promotion_path=promotion_path,
            report=outputs.report,
            ledger_path=ledger_path,
            ledger=outputs.ledger,
            planning_path=planning_path,
            planning_validation=outputs.planning_validation,
            log_path=outputs.log_state.log_path,
            final_log_text=outputs.log_state.final_log_text,
        )
    )

    return {
        "run_id": run_id,
        "decision": outputs.decision,
        "decision_record": outputs.decision_record,
        "promotion_report": report_path(vault, promotion_path),
        "run_ledger": report_path(vault, ledger_path),
        "planning_validation": report_path(vault, planning_path),
        "log_entry_ref": outputs.log_state.entry_ref,
    }
