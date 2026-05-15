#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected snippet not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _patch_runtime_imports(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """from .auto_improve_session_runtime import load_optional_json
from .experiment_telemetry_runtime import run_rel, write_run_telemetry
from .runtime_context import RuntimeContext
""",
        """from .auto_improve_session_runtime import load_optional_json
from .experiment_telemetry_runtime import run_rel, write_run_telemetry
from .promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_record_from_payload,
    decision_record_from_report,
)
from .runtime_context import RuntimeContext
""",
    )


def _patch_runtime_decision_record_helper(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """def _existing_run_telemetry(vault: Path, run_id: str) -> dict:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    return existing_report if isinstance(existing_report, dict) else {}


def _preserve_existing_telemetry_fields(payload: dict[str, Any], existing_report: dict) -> None:
""",
        """def _iteration_decision_record(
    vault: Path,
    run_id: str,
    result: dict | None,
    existing_report: dict,
) -> dict | None:
    for source in (result, existing_report):
        if not isinstance(source, dict):
            continue
        decision_record = source.get("decision_record")
        if isinstance(decision_record, dict):
            try:
                return decision_record_from_payload(
                    {"decision_record": decision_record},
                    require_record=False,
                )
            except PromotionDecisionRegistryError:
                pass
        promotion_report = source.get("promotion_report")
        if isinstance(promotion_report, dict):
            try:
                return decision_record_from_report(promotion_report, require_record=False)
            except PromotionDecisionRegistryError:
                pass
        if isinstance(promotion_report, str) and promotion_report.strip():
            promotion_payload = load_optional_json(vault / promotion_report)
            if isinstance(promotion_payload, dict):
                try:
                    return decision_record_from_report(promotion_payload, require_record=False)
                except PromotionDecisionRegistryError:
                    pass
        try:
            return decision_record_from_payload(source, require_record=False)
        except PromotionDecisionRegistryError:
            pass
    promotion_payload = load_optional_json(vault / run_rel(run_id, "promotion-report.json"))
    if not isinstance(promotion_payload, dict):
        return None
    try:
        return decision_record_from_report(promotion_payload, require_record=False)
    except PromotionDecisionRegistryError:
        return None


def _existing_run_telemetry(vault: Path, run_id: str) -> dict:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    return existing_report if isinstance(existing_report, dict) else {}


def _preserve_existing_telemetry_fields(payload: dict[str, Any], existing_report: dict) -> None:
""",
    )


def _patch_runtime_decision_record_call(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """    decision_record = (request.result or {}).get("decision_record")
    if not isinstance(decision_record, dict):
        decision_record = existing_report.get("decision_record")
    if isinstance(decision_record, dict):
        payload["decision_record"] = decision_record
""",
        """    decision_record = _iteration_decision_record(
        request.vault,
        request.run_id,
        request.result,
        existing_report,
    )
    if isinstance(decision_record, dict):
        payload["decision_record"] = decision_record
""",
    )


def _patch_test_imports(test_path: Path) -> None:
    replace_once(
        test_path,
        """from ops.scripts.auto_improve_outcome_runtime import ExecutionOutcome
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema
""",
        """from ops.scripts.auto_improve_outcome_runtime import ExecutionOutcome
from ops.scripts.promotion_decision_registry_runtime import reduce_decision_proposals
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema
""",
    )


def _patch_test_regression(test_path: Path) -> None:
    replace_once(
        test_path,
        """    def test_execute_evaluate_iteration_phase_builds_request_and_delegates(self) -> None:
""",
        """    def test_write_iteration_telemetry_recovers_decision_record_from_promotion_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-promotion-record"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            contract = reduce_decision_proposals(
                [],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            (run_dir / "promotion-report.json").write_text(
                json.dumps(
                    {
                        "decision": contract["decision"],
                        "decision_record": contract["decision_record"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            rel_path = write_iteration_telemetry(
                request=IterationTelemetryRequest(
                    vault=vault,
                    run_id=run_id,
                    session_id="auto-session",
                    proposal={"proposal_id": "proposal-1"},
                    scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                    routing_report_rels=[f"runs/{run_id}/subagent-routing.worker.json"],
                    roles=["worker"],
                    phase_durations={"routing": 0.1, "experiment": 0.2},
                    outcome="promoted",
                    result={
                        "decision": contract["decision"],
                        "promotion_report": f"runs/{run_id}/promotion-report.json",
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision_record"], contract["decision_record"])

    def test_execute_evaluate_iteration_phase_builds_request_and_delegates(self) -> None:
""",
    )


def main() -> None:
    repo = Path.cwd()
    runtime_path = repo / "ops" / "scripts" / "auto_improve_iteration_persistence_runtime.py"
    test_path = repo / "tests" / "test_auto_improve_iteration_runtime.py"
    _patch_runtime_imports(runtime_path)
    _patch_runtime_decision_record_helper(runtime_path)
    _patch_runtime_decision_record_call(runtime_path)
    _patch_test_imports(test_path)
    _patch_test_regression(test_path)


if __name__ == "__main__":
    main()
