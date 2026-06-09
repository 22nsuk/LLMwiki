from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from ops.scripts.artifact_freshness_runtime import EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
from ops.scripts.auto_improve_execute_runtime import (
    ExecuteEvaluateDependencies,
    ExecuteEvaluatePhaseResult,
    ExecuteEvaluateRequest,
)
from ops.scripts.auto_improve_iteration_persistence_runtime import (
    IterationTelemetryRequest,
    PersistIterationDependencies,
    PersistIterationPhaseResult,
    persist_iteration_phase,
    write_iteration_telemetry,
)
from ops.scripts.auto_improve_iteration_runtime import (
    AutoImproveIterationDependencies,
    AutoImproveIterationRequest,
    execute_evaluate_iteration_phase,
    run_auto_improve_iteration,
)
from ops.scripts.auto_improve_outcome_runtime import ExecutionOutcome
from ops.scripts.mechanism_run_scaffold_templates_runtime import (
    initial_run_ledger,
    placeholder_promotion_report,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.promotion_decision_registry_runtime import reduce_decision_proposals
from ops.scripts.python_function_budget_runtime import python_function_budget_candidates
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema

from ops.scripts import auto_improve_iteration_persistence_runtime
from ops.scripts.mechanism.failure_taxonomy_runtime import (
    GENERATED_EVIDENCE_SETTLE_REQUIRED,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.report_contract
REPO_ROOT = Path(__file__).resolve().parents[1]


def _expected_timeout_summary(
    *,
    timed_out: bool,
    timeout_seconds: int,
    termination_reason: str,
) -> dict[str, object]:
    return {
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "termination_reason": termination_reason,
        "launch_succeeded": True,
        "signal_sent": "none",
        "final_state_observed": "",
        "stdout_received": False,
        "stderr_received": False,
    }


def _context() -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.UTC)


def _execute_dependencies() -> ExecuteEvaluateDependencies:
    return ExecuteEvaluateDependencies(
        mutation_command=lambda **_: "",
        run_mechanism_experiment=lambda *_args, **_kwargs: {},
        role_report_path=lambda run_id, role: f"runs/{run_id}/{role}-executor-report.json",
        evaluate_scope_blocked=lambda consecutive_failures: ExecutionOutcome(
            outcome="scope_blocked",
            next_consecutive_failures=consecutive_failures + 1,
            quarantine_proposal=True,
        ),
        evaluate_experiment_result=lambda result, consecutive_failures: ExecutionOutcome(
            outcome="hold",
            next_consecutive_failures=consecutive_failures + 1,
            result=result,
        ),
        evaluate_mutation_error=lambda **_: ExecutionOutcome(
            outcome="mutation_failed",
            next_consecutive_failures=1,
        ),
        evaluate_experiment_error=lambda consecutive_failures: ExecutionOutcome(
            outcome="repo_health_blocked",
            next_consecutive_failures=consecutive_failures + 1,
            quarantine_proposal=True,
        ),
    )


def _persist_dependencies() -> PersistIterationDependencies:
    return PersistIterationDependencies(
        apply_execution_outcome=lambda *_args, **_kwargs: 0,
        write_iteration_telemetry=lambda *_args, **_kwargs: "",
        write_run_artifact_fingerprint=lambda *_args, **_kwargs: "",
        write_session_report=lambda *_args, **_kwargs: Path("ops/reports/session.json"),
    )


def _write_iteration_executor_report(
    vault: Path,
    run_id: str,
    *,
    role: str,
    status: str,
) -> str:
    report_rel = f"runs/{run_id}/{role}-executor-report.json"
    report_path = vault / report_rel
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/executor-report.schema.json",
                "run_id": run_id,
                "role": role,
                "generated_at": "2026-05-20T12:00:00Z",
                "executor": {"name": "unit-test", "sandbox_mode": "workspace-write"},
                "status": status,
                "command": {"argv": ["unit-test"]},
                "artifacts": {},
                "result": {"returncode": 0, "timed_out": False},
                "diagnostics": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_rel


def _write_placeholder_history_run(vault: Path, run_id: str) -> None:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "promotion-report.json").write_text(
        json.dumps(
            placeholder_promotion_report(
                run_id,
                ["ops/scripts/mechanism/example_runtime.py"],
                ["ops/schemas/run-telemetry.schema.json"],
                "placeholder promotion evidence",
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "run-ledger.json").write_text(
        json.dumps(
            initial_run_ledger(
                run_id,
                include_proposal_snapshot=False,
                context=_context(),
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class AutoImproveIterationRuntimeTests(unittest.TestCase):
    def test_iteration_persistence_runtime_stays_under_function_budget(self) -> None:
        policy, _ = load_policy(REPO_ROOT)
        runtime_profile = policy["system_refactor_policy"]["python_function_review"]["profiles"][
            "runtime"
        ]

        candidates = python_function_budget_candidates(
            REPO_ROOT,
            {
                "profiles": {
                    "runtime": {
                        **runtime_profile,
                        "include_prefixes": [
                            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                        ],
                    }
                }
            },
        )

        self.assertEqual(candidates, [])

    def test_run_telemetry_preservation_contract_matches_schema_surface(self) -> None:
        schema = load_schema(
            REPO_ROOT / "ops" / "schemas" / "run-telemetry.schema.json"
        )
        schema_fields = set(schema["properties"]) - {"$schema"}
        written_fields = auto_improve_iteration_persistence_runtime.ITERATION_TELEMETRY_WRITTEN_FIELDS
        merged_fields = auto_improve_iteration_persistence_runtime.ITERATION_TELEMETRY_MERGED_FIELDS
        preserved_fields = auto_improve_iteration_persistence_runtime.PRESERVED_RUN_TELEMETRY_FIELDS

        self.assertTrue(written_fields.isdisjoint(merged_fields))
        self.assertTrue(written_fields.isdisjoint(preserved_fields))
        self.assertTrue(merged_fields.isdisjoint(preserved_fields))
        self.assertEqual(
            preserved_fields,
            schema_fields - written_fields - merged_fields,
        )
        self.assertEqual(
            schema_fields,
            written_fields | merged_fields | preserved_fields,
        )

    def test_write_iteration_telemetry_preserves_existing_workspace_apply_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-01"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            existing_workspace_preparation = {
                "mode": "full_copy",
                "baseline_file_count": 10,
                "copied_file_count": 8,
                "phase_durations": {"digest": 0.1, "copy": 0.2, "total": 0.3},
            }
            existing_metadata = {
                "properties": [
                    {
                        "name": "urn:openai:artifact-envelope",
                        "value": "{\"artifact_kind\":\"run_telemetry\"}",
                    }
                ]
            }
            (run_dir / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/run-telemetry.schema.json",
                        "run_id": run_id,
                        "generated_at": "2026-04-15T00:00:00Z",
                        "metadata": existing_metadata,
                        "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                        "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                        "routing_reports": [],
                        "executor_reports": [],
                        "primary_targets": ["ops/scripts/example.py"],
                        "supporting_targets": ["tests/test_example.py"],
                        "test_files": ["tests/test_example.py"],
                        "workspace_preparation": existing_workspace_preparation,
                        "behavior_delta": f"runs/{run_id}/behavior-delta.json",
                        "structural_complexity_budget": (
                            f"runs/{run_id}/structural-complexity-budget.json"
                        ),
                        "apply_mode": "live",
                        "apply_status": "live_applied",
                        "live_applied": True,
                        "shadow_apply_report": f"runs/{run_id}/shadow-apply-report.json",
                        "rollback_rehearsal_report": (
                            f"runs/{run_id}/rollback-rehearsal-report.json"
                        ),
                        "decision": "PROMOTE",
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
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
                    proposal={
                        "proposal_id": "proposal-1",
                        "source_candidate_id": "candidate-1",
                    },
                    scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                    routing_report_rels=[f"runs/{run_id}/subagent-routing.worker.json"],
                    roles=["worker"],
                    phase_durations={"routing": 0.2, "experiment": 0.5},
                    outcome="promoted",
                    result={
                        "decision": "PROMOTE",
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["source_candidate_id"], "candidate-1")
            metadata_properties = payload["metadata"]["properties"]
            embedded_envelopes = [
                json.loads(item["value"])
                for item in metadata_properties
                if item["name"] == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
            ]
            self.assertEqual(len(embedded_envelopes), 1)
            self.assertEqual(embedded_envelopes[0]["artifact_kind"], "run_telemetry")
            runtime_source = (
                Path(__file__).resolve().parents[1]
                / "ops"
                / "scripts"
                / "mechanism"
                / "auto_improve_iteration_persistence_runtime.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("_existing_run_telemetry", runtime_source)
            self.assertEqual(payload["workspace_preparation"], existing_workspace_preparation)
            self.assertEqual(payload["primary_targets"], ["ops/scripts/example.py"])
            self.assertEqual(payload["supporting_targets"], ["tests/test_example.py"])
            self.assertEqual(payload["test_files"], ["tests/test_example.py"])
            self.assertEqual(payload["apply_mode"], "live")
            self.assertEqual(payload["apply_status"], "live_applied")
            self.assertTrue(payload["live_applied"])
            self.assertEqual(payload["shadow_apply_report"], f"runs/{run_id}/shadow-apply-report.json")
            self.assertEqual(
                payload["rollback_rehearsal_report"],
                f"runs/{run_id}/rollback-rehearsal-report.json",
            )
            self.assertEqual(payload["behavior_delta"], f"runs/{run_id}/behavior-delta.json")
            self.assertEqual(
                payload["structural_complexity_budget"],
                f"runs/{run_id}/structural-complexity-budget.json",
            )
            self.assertEqual(payload["phase_durations"], {"routing": 0.2, "experiment": 0.5})

    def test_write_iteration_telemetry_merges_nested_timeout_fields_from_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-timeouts"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)

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
                    outcome="validation_blocked",
                    result={
                        "decision": "HOLD",
                        "finalized": False,
                        "finalize_result": {},
                        "mutation_command": {
                            "timed_out": True,
                            "timeout_seconds": 1800,
                            "termination_reason": "timeout",
                        },
                        "command_timeouts": {
                            "repo_health": {
                                "timed_out": False,
                                "timeout_seconds": 5400,
                                "termination_reason": "completed",
                            }
                        },
                        "timeout_failure_artifacts": [
                            f"runs/{run_id}/worker-executor-timeout-failure.json"
                        ],
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(
                payload["command_timeouts"],
                {
                    "mutation_command": _expected_timeout_summary(
                        timed_out=True,
                        timeout_seconds=1800,
                        termination_reason="timeout",
                    ),
                    "repo_health": _expected_timeout_summary(
                        timed_out=False,
                        timeout_seconds=5400,
                        termination_reason="completed",
                    ),
                },
            )
            self.assertEqual(
                payload["timeout_failure_artifacts"],
                [f"runs/{run_id}/worker-executor-timeout-failure.json"],
            )

    def test_write_iteration_telemetry_records_pre_promotion_failure_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-pre-promotion-failure"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            for name in (
                "mutation-command.stdout.txt",
                "mutation-command.stderr.txt",
                "repo-health.stderr.txt",
                "repo-health-artifact-freshness-report-check.json",
                "structural-complexity-budget.json",
            ):
                (run_dir / name).write_text(f"{name}\n", encoding="utf-8")

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
                    outcome="mutation_failed",
                    result=None,
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(
                payload["pre_promotion_failure_artifacts"],
                [
                    f"runs/{run_id}/mutation-command.stdout.txt",
                    f"runs/{run_id}/mutation-command.stderr.txt",
                    f"runs/{run_id}/repo-health.stderr.txt",
                    f"runs/{run_id}/repo-health-artifact-freshness-report-check.json",
                    f"runs/{run_id}/structural-complexity-budget.json",
                ],
            )

    def test_write_iteration_telemetry_preserves_specific_repo_health_failure_taxonomy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-structural-budget"
            (vault / "runs" / run_id).mkdir(parents=True)

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
                    outcome="repo_health_blocked",
                    result={
                        "decision": "SKIPPED",
                        "failure_taxonomy": "structural_complexity_non_regression",
                        "finalized": False,
                        "finalize_result": {},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["failure_taxonomy"], "structural_complexity_non_regression")

    def test_write_iteration_telemetry_omits_stale_pre_promotion_logs_for_hold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-hold"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "mutation-command.stderr.txt").write_text("old failure\n", encoding="utf-8")
            (run_dir / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "pre_promotion_failure_artifacts": [
                            f"runs/{run_id}/mutation-command.stderr.txt"
                        ]
                    }
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
                    outcome="hold",
                    result={"decision": "HOLD"},
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertNotIn("pre_promotion_failure_artifacts", payload)

    def test_write_iteration_telemetry_records_only_existing_executor_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-missing-planned-reports"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            worker_report = _write_iteration_executor_report(
                vault,
                run_id,
                role="worker",
                status="pass",
            )

            rel_path = write_iteration_telemetry(
                request=IterationTelemetryRequest(
                    vault=vault,
                    run_id=run_id,
                    session_id="auto-session",
                    proposal={"proposal_id": "proposal-1"},
                    scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                    routing_report_rels=[
                        f"runs/{run_id}/subagent-routing.worker.json",
                        f"runs/{run_id}/subagent-routing.reviewer.json",
                        f"runs/{run_id}/subagent-routing.validator.json",
                    ],
                    roles=["worker", "reviewer", "validator"],
                    phase_durations={"routing": 0.1, "experiment": 0.2},
                    outcome="mutation_failed",
                    result=None,
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["executor_reports"], [worker_report])
            self.assertNotIn(
                f"runs/{run_id}/reviewer-executor-report.json",
                payload["executor_reports"],
            )
            self.assertNotIn(
                f"runs/{run_id}/validator-executor-report.json",
                payload["executor_reports"],
            )

    def test_persist_iteration_phase_uses_existing_executor_reports_for_decision_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-auditor-blocked"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            for role in ("worker", "reviewer", "validator", "provenance-auditor"):
                (run_dir / f"subagent-routing.{role}.json").write_text("{}", encoding="utf-8")
            worker_report = _write_iteration_executor_report(
                vault,
                run_id,
                role="worker",
                status="pass",
            )
            validator_report = _write_iteration_executor_report(
                vault,
                run_id,
                role="validator",
                status="pass",
            )
            auditor_report = _write_iteration_executor_report(
                vault,
                run_id,
                role="provenance-auditor",
                status="fail",
            )
            session: dict[str, Any] = {
                "iterations": [],
                "next_run_decisions": [],
                "loop_state": {},
            }
            proposal = {
                "proposal_id": "proposal-1",
                "source_candidate_id": "candidate-1",
                "family": "next_run_failure_repair",
                "tier": "supporting",
                "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
                "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                "must_change_tests": ["tests/test_example_runtime.py"],
            }
            route_scaffold = SimpleNamespace(
                run_id=run_id,
                phase_durations={"routing": 0.1},
                scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                routing_report_rels=[
                    f"runs/{run_id}/subagent-routing.worker.json",
                    f"runs/{run_id}/subagent-routing.reviewer.json",
                    f"runs/{run_id}/subagent-routing.validator.json",
                    f"runs/{run_id}/subagent-routing.provenance-auditor.json",
                ],
                roles=["worker", "reviewer", "validator", "provenance-auditor"],
            )
            execution = ExecuteEvaluatePhaseResult(
                outcome=ExecutionOutcome(
                    outcome="validation_blocked",
                    next_consecutive_failures=1,
                    quarantine_proposal=True,
                ),
                phase_durations={"experiment": 0.2},
            )

            persist_iteration_phase(
                vault,
                session,
                session_id="auto-session",
                iteration=1,
                proposal=proposal,
                route_scaffold=route_scaffold,
                execution=execution,
                quarantined=set(),
                context=_context(),
                dependencies=PersistIterationDependencies(
                    apply_execution_outcome=lambda *_args, **_kwargs: 1,
                    write_iteration_telemetry=write_iteration_telemetry,
                    write_run_artifact_fingerprint=lambda *_args, **_kwargs: "",
                    write_session_report=lambda *_args, **_kwargs: Path(
                        "ops/reports/session.json"
                    ),
                ),
            )

            telemetry = json.loads(
                (vault / "runs" / run_id / "run-telemetry.json").read_text(encoding="utf-8")
            )
            decision = session["next_run_decisions"][0]
            self.assertEqual(
                telemetry["executor_reports"],
                [worker_report, validator_report, auditor_report],
            )
            self.assertEqual(decision["blocking_role"], "provenance-auditor")
            self.assertIn(auditor_report, decision["evidence_paths"])
            self.assertNotIn(
                f"runs/{run_id}/reviewer-executor-report.json",
                decision["evidence_paths"],
            )

    def test_persist_iteration_phase_keeps_pre_promotion_placeholder_history_active(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-pre-promotion-failure"
            _write_placeholder_history_run(vault, run_id)
            _write_iteration_executor_report(vault, run_id, role="worker", status="fail")
            (vault / "runs" / run_id / "subagent-routing.worker.json").write_text(
                "{}",
                encoding="utf-8",
            )
            session: dict[str, Any] = {"iterations": [], "next_run_decisions": [], "loop_state": {}}
            proposal = {
                "proposal_id": "proposal-1",
                "source_candidate_id": "candidate-1",
                "family": "contract_regression_signals",
                "tier": "primary",
                "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
                "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                "must_change_tests": ["tests/test_example_runtime.py"],
            }
            route_scaffold = SimpleNamespace(
                run_id=run_id,
                phase_durations={"routing": 0.1},
                scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                routing_report_rels=[f"runs/{run_id}/subagent-routing.worker.json"],
                roles=["worker"],
            )
            execution = ExecuteEvaluatePhaseResult(
                outcome=ExecutionOutcome(
                    outcome="validation_blocked",
                    next_consecutive_failures=1,
                    quarantine_proposal=True,
                ),
                phase_durations={"experiment": 0.2},
            )
            persist_iteration_phase(
                vault,
                session,
                session_id="auto-session",
                iteration=1,
                proposal=proposal,
                route_scaffold=route_scaffold,
                execution=execution,
                quarantined=set(),
                context=_context(),
                dependencies=PersistIterationDependencies(
                    apply_execution_outcome=lambda *_args, **_kwargs: 1,
                    write_iteration_telemetry=write_iteration_telemetry,
                    write_run_artifact_fingerprint=lambda *_args, **_kwargs: "",
                    write_session_report=lambda *_args, **_kwargs: Path(
                        "ops/reports/session.json"
                    ),
                ),
            )

            promotion_report = json.loads(
                (vault / "runs" / run_id / "promotion-report.json").read_text(
                    encoding="utf-8"
                )
            )
            run_ledger = json.loads(
                (vault / "runs" / run_id / "run-ledger.json").read_text(encoding="utf-8")
            )
            self.assertEqual(promotion_report["history"]["status"], "active")
            self.assertNotIn(
                "history_status_updated",
                [event["type"] for event in run_ledger["events"]],
            )

    def test_persist_iteration_phase_does_not_quarantine_report_with_gate_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-gate-decision-present"
            _write_placeholder_history_run(vault, run_id)
            contract = reduce_decision_proposals(
                [],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            promotion_path = vault / "runs" / run_id / "promotion-report.json"
            promotion_report = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_report["decision"] = contract["decision"]
            promotion_report["decision_record"] = contract["decision_record"]
            promotion_path.write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            _write_iteration_executor_report(vault, run_id, role="worker", status="fail")
            (vault / "runs" / run_id / "subagent-routing.worker.json").write_text(
                "{}",
                encoding="utf-8",
            )
            session: dict[str, Any] = {"iterations": [], "next_run_decisions": [], "loop_state": {}}
            proposal = {
                "proposal_id": "proposal-1",
                "source_candidate_id": "candidate-1",
                "family": "contract_regression_signals",
                "tier": "primary",
                "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
                "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                "must_change_tests": ["tests/test_example_runtime.py"],
            }
            route_scaffold = SimpleNamespace(
                run_id=run_id,
                phase_durations={"routing": 0.1},
                scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                routing_report_rels=[f"runs/{run_id}/subagent-routing.worker.json"],
                roles=["worker"],
            )

            persist_iteration_phase(
                vault,
                session,
                session_id="auto-session",
                iteration=1,
                proposal=proposal,
                route_scaffold=route_scaffold,
                execution=ExecuteEvaluatePhaseResult(
                    outcome=ExecutionOutcome(
                        outcome="validation_blocked",
                        next_consecutive_failures=1,
                        quarantine_proposal=True,
                    ),
                    phase_durations={"experiment": 0.2},
                ),
                quarantined=set(),
                context=_context(),
                dependencies=PersistIterationDependencies(
                    apply_execution_outcome=lambda *_args, **_kwargs: 1,
                    write_iteration_telemetry=write_iteration_telemetry,
                    write_run_artifact_fingerprint=lambda *_args, **_kwargs: "",
                    write_session_report=lambda *_args, **_kwargs: Path(
                        "ops/reports/session.json"
                    ),
                ),
            )

            promotion_report = json.loads(promotion_path.read_text(encoding="utf-8"))
            run_ledger = json.loads(
                (vault / "runs" / run_id / "run-ledger.json").read_text(encoding="utf-8")
            )
            self.assertEqual(promotion_report["history"]["status"], "active")
            self.assertNotIn(
                "history_status_updated",
                [event["type"] for event in run_ledger["events"]],
            )

    def test_persist_iteration_phase_carries_specific_discard_failure_taxonomy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-changed-files-scope"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            for role in ("worker", "reviewer"):
                (run_dir / f"subagent-routing.{role}.json").write_text("{}", encoding="utf-8")
            _write_iteration_executor_report(vault, run_id, role="worker", status="pass")
            _write_iteration_executor_report(vault, run_id, role="reviewer", status="pass")
            promotion_rel = f"runs/{run_id}/promotion-report.json"
            contract = reduce_decision_proposals(
                [
                    {
                        "rule_id": "changed_files_manifest_scope",
                        "decision": "DISCARD",
                        "evidence_refs": ["changed_files_manifest_scope"],
                    }
                ],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            (vault / promotion_rel).write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "decision": "DISCARD",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "PASS"},
                            {"id": "eval_score_improves", "status": "WARN"},
                            {"id": "lint_non_regression", "status": "PASS"},
                            {"id": "structural_complexity_non_regression", "status": "PASS"},
                            {"id": "tests_non_regression", "status": "PASS"},
                            {"id": "changed_files_manifest_scope", "status": "FAIL"},
                        ],
                        "decision_record": contract["decision_record"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            session: dict[str, Any] = {
                "iterations": [],
                "next_run_decisions": [],
                "loop_state": {},
            }
            proposal = {
                "proposal_id": (
                    "next_run_failure_repair__example-runtime__validation-blocked"
                ),
                "source_candidate_id": "candidate-1",
                "family": "next_run_failure_repair",
                "tier": "supporting",
                "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
                "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                "must_change_tests": ["tests/test_example_runtime.py"],
            }
            route_scaffold = SimpleNamespace(
                run_id=run_id,
                phase_durations={"routing": 0.1},
                scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                routing_report_rels=[
                    f"runs/{run_id}/subagent-routing.worker.json",
                    f"runs/{run_id}/subagent-routing.reviewer.json",
                ],
                roles=["worker", "reviewer"],
            )
            execution = ExecuteEvaluatePhaseResult(
                outcome=ExecutionOutcome(
                    outcome="discarded",
                    next_consecutive_failures=1,
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                    },
                ),
                phase_durations={"experiment": 0.2},
            )

            persist_iteration_phase(
                vault,
                session,
                session_id="auto-session",
                iteration=1,
                proposal=proposal,
                route_scaffold=route_scaffold,
                execution=execution,
                quarantined=set(),
                context=_context(),
                dependencies=PersistIterationDependencies(
                    apply_execution_outcome=lambda *_args, **_kwargs: 1,
                    write_iteration_telemetry=write_iteration_telemetry,
                    write_run_artifact_fingerprint=lambda *_args, **_kwargs: "",
                    write_session_report=lambda *_args, **_kwargs: Path(
                        "ops/reports/session.json"
                    ),
                ),
            )

            telemetry = json.loads(
                (vault / "runs" / run_id / "run-telemetry.json").read_text(encoding="utf-8")
            )
            iteration_record = session["iterations"][0]
            decision = session["next_run_decisions"][0]
            self.assertEqual(telemetry["failure_taxonomy"], "changed_files_manifest_scope")
            self.assertEqual(iteration_record["outcome"], "discarded")
            self.assertEqual(iteration_record["failure_taxonomy"], "changed_files_manifest_scope")
            self.assertEqual(decision["failure_taxonomy"], "changed_files_manifest_scope")
            self.assertEqual(decision["blocking_role"], "promotion_gate")
            self.assertEqual(
                decision["target_proposal_id"],
                "next_run_failure_repair__example-runtime__changed-files-manifest-scope",
            )
            self.assertEqual(session["loop_state"]["last_outcome"], "discarded")
            self.assertEqual(
                session["loop_state"]["last_blocking_reason"],
                "changed_files_manifest_scope",
            )
            self.assertEqual(
                session["loop_state"]["blocking_reason_counts"],
                {"changed_files_manifest_scope": 1},
            )

    def test_write_iteration_telemetry_records_behavior_delta_digest_and_same_eval_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-behavior-delta"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "behavior-delta.json").write_text(
                '{"summary":"same eval but lint improved"}\n',
                encoding="utf-8",
            )

            rel_path = write_iteration_telemetry(
                request=IterationTelemetryRequest(
                    vault=vault,
                    run_id=run_id,
                    session_id="auto-session",
                    proposal={"proposal_id": "proposal-1"},
                    scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                    routing_report_rels=[],
                    roles=[],
                    phase_durations={},
                    outcome="promoted",
                    result={
                        "decision": "PROMOTE",
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                        "behavior_delta": f"runs/{run_id}/behavior-delta.json",
                        "same_eval_reason": "same eval accepted by lint improvement",
                        "same_eval": {
                            "same_eval_reason_code": "telemetry_discoverability_improved",
                            "strict_secondary_improvement_present": True,
                            "secondary_improvement_axes": ["lint"],
                        },
                    },
                    context=RuntimeContext(
                        display_timezone=dt.UTC,
                        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
                    ),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["observed_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(payload["behavior_delta"], f"runs/{run_id}/behavior-delta.json")
            self.assertEqual(len(payload["behavior_delta_digest"]), 64)
            self.assertEqual(payload["same_eval_reason"], "same eval accepted by lint improvement")
            self.assertEqual(payload["same_eval_reason_code"], "telemetry_discoverability_improved")
            self.assertTrue(payload["strict_secondary_improvement_present"])
            self.assertEqual(payload["secondary_improvement_axes"], ["lint"])

    def test_write_iteration_telemetry_recovers_decision_record_from_promotion_report_path(self) -> None:
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

    def test_write_iteration_telemetry_prefers_promotion_report_over_result_decision_mirror(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-decision-mirror-conflict"
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
            promotion_rel = f"runs/{run_id}/promotion-report.json"
            (vault / promotion_rel).write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "PASS"},
                            {"id": "eval_score_improves", "status": "PASS"},
                            {"id": "lint_non_regression", "status": "PASS"},
                            {"id": "structural_complexity_non_regression", "status": "PASS"},
                            {"id": "tests_non_regression", "status": "PASS"},
                        ],
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
                    outcome=" DISCARDED ",
                    result={
                        "decision": "HOLD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "PROMOTE")
            self.assertEqual(payload["decision_record"], contract["decision_record"])
            self.assertNotIn("discard_non_regression_evidence", payload)

    def test_write_iteration_telemetry_records_discard_evidence_from_actual_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-evidence-path"
            run_dir = vault / "runs" / run_id
            evidence_dir = run_dir / "evidence"
            evidence_dir.mkdir(parents=True)
            promotion_rel = f"runs/{run_id}/evidence/non-default-promotion-report.json"
            contract = reduce_decision_proposals(
                [
                    {
                        "rule_id": "equal_score_secondary_eligibility",
                        "decision": "DISCARD",
                        "evidence_refs": ["equal_score_secondary_eligibility"],
                    }
                ],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            promotion_report = {
                "decision": "DISCARD",
                "checks": [
                    {"id": "candidate_eval_pass", "status": "PASS"},
                    {"id": "eval_score_improves", "status": "WARN"},
                    {"id": "lint_non_regression", "status": "PASS"},
                    {"id": "structural_complexity_non_regression", "status": "FAIL"},
                    {"id": "tests_non_regression", "status": "PASS"},
                    {"id": "equal_score_secondary_eligibility", "status": "WARN"},
                ],
                "decision_record": contract["decision_record"],
            }
            (vault / promotion_rel).write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
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
                    outcome=" DISCARDED ",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "DISCARD")
            evidence = payload["discard_non_regression_evidence"]
            self.assertEqual(evidence["promotion_report_source"], "path")
            self.assertEqual(evidence["promotion_report"], promotion_rel)
            self.assertTrue((vault / evidence["promotion_report"]).is_file())
            self.assertTrue(evidence["candidate_eval_pass"])
            self.assertFalse(evidence["eval_score_improves"])
            self.assertTrue(evidence["lint_non_regression"])
            self.assertFalse(evidence["structural_complexity_non_regression"])
            self.assertTrue(evidence["tests_non_regression"])
            self.assertEqual(
                evidence["non_regression_check_statuses"],
                {
                    "candidate_eval_pass": "PASS",
                    "eval_score_improves": "WARN",
                    "lint_non_regression": "PASS",
                    "structural_complexity_non_regression": "FAIL",
                    "tests_non_regression": "PASS",
                },
            )
            self.assertEqual(payload["failure_taxonomy"], "structural_complexity_non_regression")
            self.assertEqual(
                evidence["blocking_check_ids"], ["structural_complexity_non_regression"]
            )
            self.assertEqual(
                evidence["decision_record_reason_code"],
                "equal_score_secondary_eligibility",
            )

    def test_write_iteration_telemetry_falls_back_to_non_regression_blocker_without_decision_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-evidence-legacy-status"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            promotion_rel = f"runs/{run_id}/promotion-report.json"
            (vault / promotion_rel).write_text(
                json.dumps(
                    {
                        "decision": "DISCARD",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "PASS"},
                            {"id": "eval_score_improves", "status": "WARN"},
                            {"id": "lint_non_regression", "status": "PASS"},
                            {"id": "structural_complexity_non_regression", "status": "PASS"},
                            {"id": "tests_non_regression", "status": "MAYBE"},
                        ],
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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            evidence = payload["discard_non_regression_evidence"]
            self.assertEqual(payload["failure_taxonomy"], "tests_non_regression")
            self.assertEqual(evidence["blocking_check_ids"], ["tests_non_regression"])
            self.assertEqual(evidence["non_regression_check_statuses"]["tests_non_regression"], "UNKNOWN")

    def test_write_iteration_telemetry_names_legacy_equal_score_discard_blocker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-evidence-legacy-equal-score"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            promotion_rel = f"runs/{run_id}/promotion-report.json"
            (vault / promotion_rel).write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "decision": "DISCARD",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "PASS"},
                            {"id": "eval_score_improves", "status": "WARN"},
                            {"id": "lint_non_regression", "status": "PASS"},
                            {"id": "structural_complexity_non_regression", "status": "PASS"},
                            {"id": "tests_non_regression", "status": "PASS"},
                            {"id": "equal_score_secondary_eligibility", "status": "WARN"},
                        ],
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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            evidence = payload["discard_non_regression_evidence"]
            self.assertEqual(payload["failure_taxonomy"], "equal_score_secondary_eligibility")
            self.assertEqual(evidence["blocking_check_ids"], ["equal_score_secondary_eligibility"])
            self.assertEqual(evidence["non_regression_check_statuses"]["eval_score_improves"], "WARN")

    def test_write_iteration_telemetry_ignores_discard_evidence_when_outcome_is_not_discarded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-evidence-non-discard-outcome"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            promotion_rel = f"runs/{run_id}/promotion-report.json"
            contract = reduce_decision_proposals(
                [
                    {
                        "rule_id": "equal_score_secondary_eligibility",
                        "decision": "DISCARD",
                        "evidence_refs": ["equal_score_secondary_eligibility"],
                    }
                ],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            promotion_report = {
                "decision": "DISCARD",
                "checks": [
                    {"id": "candidate_eval_pass", "status": "PASS"},
                    {"id": "eval_score_improves", "status": "WARN"},
                    {"id": "lint_non_regression", "status": "PASS"},
                    {"id": "structural_complexity_non_regression", "status": "PASS"},
                    {"id": "tests_non_regression", "status": "PASS"},
                    {"id": "equal_score_secondary_eligibility", "status": "FAIL"},
                ],
                "decision_record": contract["decision_record"],
            }
            (vault / promotion_rel).write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
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
                    outcome="hold",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "DISCARD")
            self.assertEqual(payload["failure_taxonomy"], "hold")
            self.assertNotIn("discard_non_regression_evidence", payload)

    def test_write_iteration_telemetry_ignores_discard_evidence_for_report_mirror_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-evidence-mirror-drift"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            promotion_rel = f"runs/{run_id}/promotion-report.json"
            contract = reduce_decision_proposals(
                [],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            (vault / promotion_rel).write_text(
                json.dumps(
                    {
                        "decision": "DISCARD",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "FAIL"},
                            {"id": "eval_score_improves", "status": "WARN"},
                            {"id": "lint_non_regression", "status": "PASS"},
                            {"id": "structural_complexity_non_regression", "status": "PASS"},
                            {"id": "tests_non_regression", "status": "PASS"},
                        ],
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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertNotIn("decision_record", payload)
            self.assertNotIn("discard_non_regression_evidence", payload)

    def test_write_iteration_telemetry_does_not_invent_default_path_for_inline_discard_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-evidence-inline"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            contract = reduce_decision_proposals(
                [
                    {
                        "rule_id": "candidate_eval_pass",
                        "decision": "DISCARD",
                        "evidence_refs": ["candidate_eval_pass"],
                    }
                ],
                subject_id=run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            inline_report = {
                "decision": "DISCARD",
                "checks": [
                    {"id": "candidate_eval_pass", "status": "FAIL"},
                    {"id": "eval_score_improves", "status": "WARN"},
                    {"id": "lint_non_regression", "status": "PASS"},
                    {"id": "structural_complexity_non_regression", "status": "PASS"},
                ],
                "decision_record": contract["decision_record"],
            }

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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": inline_report,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            evidence = payload["discard_non_regression_evidence"]
            self.assertEqual(evidence["promotion_report_source"], "inline")
            self.assertNotIn("promotion_report", evidence)
            self.assertFalse((run_dir / "promotion-report.json").exists())
            self.assertFalse(evidence["candidate_eval_pass"])
            self.assertFalse(evidence["tests_non_regression"])
            self.assertEqual(
                evidence["non_regression_check_statuses"],
                {
                    "candidate_eval_pass": "FAIL",
                    "eval_score_improves": "WARN",
                    "lint_non_regression": "PASS",
                    "structural_complexity_non_regression": "PASS",
                    "tests_non_regression": "MISSING",
                },
            )
            self.assertEqual(evidence["blocking_check_ids"], ["candidate_eval_pass"])

    def test_write_iteration_telemetry_rejects_cross_run_promotion_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-current"
            other_run_id = "auto-session-run-discard-other"
            run_dir = vault / "runs" / run_id
            other_run_dir = vault / "runs" / other_run_id
            run_dir.mkdir(parents=True)
            other_run_dir.mkdir(parents=True)
            promotion_rel = f"runs/{other_run_id}/promotion-report.json"
            contract = reduce_decision_proposals(
                [
                    {
                        "rule_id": "candidate_eval_pass",
                        "decision": "DISCARD",
                        "evidence_refs": ["candidate_eval_pass"],
                    }
                ],
                subject_id=other_run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            (vault / promotion_rel).write_text(
                json.dumps(
                    {
                        "run_id": other_run_id,
                        "decision": "DISCARD",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "FAIL"},
                        ],
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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": promotion_rel,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "DISCARD")
            self.assertNotIn("decision_record", payload)
            self.assertNotIn("discard_non_regression_evidence", payload)

    def test_write_iteration_telemetry_rejects_traversal_promotion_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-discard-current"
            other_run_id = "auto-session-run-discard-other"
            run_dir = vault / "runs" / run_id
            other_run_dir = vault / "runs" / other_run_id
            run_dir.mkdir(parents=True)
            other_run_dir.mkdir(parents=True)
            (other_run_dir / "promotion-report.json").write_text(
                json.dumps(
                    {
                        "decision": "DISCARD",
                        "checks": [
                            {"id": "candidate_eval_pass", "status": "FAIL"},
                            {"id": "eval_score_improves", "status": "FAIL"},
                            {"id": "lint_non_regression", "status": "FAIL"},
                            {"id": "structural_complexity_non_regression", "status": "FAIL"},
                            {"id": "tests_non_regression", "status": "FAIL"},
                        ],
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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": f"runs/{run_id}/../{other_run_id}/promotion-report.json",
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "DISCARD")
            self.assertNotIn("decision_record", payload)
            self.assertNotIn("discard_non_regression_evidence", payload)

    def test_write_iteration_telemetry_rejects_inline_promotion_report_subject_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-inline-current"
            other_run_id = "auto-session-run-inline-other"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            contract = reduce_decision_proposals(
                [
                    {
                        "rule_id": "candidate_eval_pass",
                        "decision": "DISCARD",
                        "evidence_refs": ["candidate_eval_pass"],
                    }
                ],
                subject_id=other_run_id,
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )
            inline_report = {
                "run_id": run_id,
                "decision": "DISCARD",
                "checks": [
                    {"id": "candidate_eval_pass", "status": "FAIL"},
                ],
                "decision_record": contract["decision_record"],
            }

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
                    outcome="discarded",
                    result={
                        "decision": "DISCARD",
                        "promotion_report": inline_report,
                        "finalized": True,
                        "finalize_result": {"run_id": run_id},
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "DISCARD")
            self.assertNotIn("decision_record", payload)
            self.assertNotIn("discard_non_regression_evidence", payload)

    def test_execute_evaluate_iteration_phase_builds_request_and_delegates(self) -> None:
        captured: dict[str, ExecuteEvaluateRequest] = {}
        expected = ExecuteEvaluatePhaseResult(
            outcome=ExecutionOutcome(outcome="hold", next_consecutive_failures=3),
            phase_durations={"experiment": 0.5},
        )

        def fake_execute(request: ExecuteEvaluateRequest) -> ExecuteEvaluatePhaseResult:
            captured["request"] = request
            return expected

        scope_freeze = {
            "status": "ready",
            "resolution": {"test_files": ["tests/test_example.py"]},
            "inputs": {
                "primary_targets": ["ops/scripts/example.py"],
                "supporting_targets": ["tests/test_example.py"],
            },
        }

        result = execute_evaluate_iteration_phase(
            Path("/tmp/vault"),
            Path("ops/policies/wiki-maintainer-policy.yaml"),
            run_id="auto-session-run-01",
            proposal={"proposal_id": "proposal-1"},
            scope_freeze=scope_freeze,
            scope_freeze_rel="runs/auto-session-run-01/scope-freeze.json",
            roles=["worker", "validator"],
            routing_report_rels=[
                "runs/auto-session-run-01/subagent-routing.worker.json",
                "runs/auto-session-run-01/subagent-routing.validator.json",
            ],
            consecutive_failures=2,
            pre_promotion_failure_outcomes={"scope_blocked"},
            proposal_report_path="ops/reports/mutation-proposals.json",
            context=_context(),
            dependencies=_execute_dependencies(),
            execute_evaluate_phase_fn=fake_execute,
        )

        self.assertIs(result, expected)
        request = captured["request"]
        self.assertEqual(request.run_id, "auto-session-run-01")
        self.assertEqual(request.proposal["proposal_id"], "proposal-1")
        self.assertEqual(request.scope_freeze, scope_freeze)
        self.assertEqual(request.proposal_report_path, "ops/reports/mutation-proposals.json")
        self.assertEqual(request.roles, ["worker", "validator"])
        self.assertEqual(
            request.routing_report_rels,
            [
                "runs/auto-session-run-01/subagent-routing.worker.json",
                "runs/auto-session-run-01/subagent-routing.validator.json",
            ],
        )

    def test_run_auto_improve_iteration_stops_when_queue_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = {
                "budget": {"max_consecutive_failures": 3},
                "attempted_proposal_ids": [],
                "run_ids": [],
                "queue_snapshot": ["stale"],
            }
            dependencies = AutoImproveIterationDependencies(
                refresh_select_phase=mock.Mock(
                    return_value=SimpleNamespace(
                        proposal=None,
                        queue_snapshot=[],
                        stop_reason="queue_exhausted",
                    )
                ),
                route_scaffold_phase=mock.Mock(),
                execute_evaluate_dependencies=_execute_dependencies(),
                execute_evaluate_phase_fn=mock.Mock(),
                persist_iteration_dependencies=_persist_dependencies(),
                persist_iteration_phase_fn=mock.Mock(),
                append_runtime_event=mock.Mock(),
            )

            result = run_auto_improve_iteration(
                AutoImproveIterationRequest(
                    vault=Path(temp_dir),
                    policy={"version": "2026-04-21"},
                    resolved_policy_path=Path("ops/policies/wiki-maintainer-policy.yaml"),
                    session=session,
                    session_id="auto-session",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    iteration=1,
                    attempted=set(),
                    quarantined=set(),
                    consecutive_failures=1,
                    pre_promotion_failure_outcomes={"scope_blocked"},
                    context=_context(),
                ),
                dependencies=dependencies,
                build_run_id=lambda *_args: "unused",
            )

        self.assertFalse(result.keep_running)
        self.assertEqual(result.stop_reason, "queue_exhausted")
        self.assertEqual(result.consecutive_failures, 1)
        self.assertEqual(session["queue_snapshot"], [])
        dependencies.route_scaffold_phase.assert_not_called()
        dependencies.append_runtime_event.assert_not_called()

    def test_run_auto_improve_iteration_records_runtime_event_and_stops_on_failure_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            proposal = {"proposal_id": "proposal-1", "primary_targets": ["ops/scripts/example.py"]}
            route_scaffold = SimpleNamespace(
                scope_freeze={"status": "blocked"},
                scope_freeze_rel="runs/auto-session-run-01/scope-freeze.json",
                roles=["worker"],
                routing_report_rels=["runs/auto-session-run-01/subagent-routing.worker.json"],
                phase_durations={"scope": 0.1, "route": 0.2},
            )
            execution = ExecuteEvaluatePhaseResult(
                outcome=ExecutionOutcome(
                    outcome="scope_blocked",
                    next_consecutive_failures=3,
                    quarantine_proposal=True,
                ),
                phase_durations={"experiment": 0.4},
            )
            session = {
                "budget": {"max_consecutive_failures": 3},
                "attempted_proposal_ids": [],
                "run_ids": [],
                "queue_snapshot": [],
            }
            dependencies = AutoImproveIterationDependencies(
                refresh_select_phase=mock.Mock(
                    return_value=SimpleNamespace(
                        proposal=proposal,
                        queue_snapshot=["proposal-1"],
                        stop_reason=None,
                    )
                ),
                route_scaffold_phase=mock.Mock(return_value=route_scaffold),
                execute_evaluate_dependencies=_execute_dependencies(),
                execute_evaluate_phase_fn=mock.Mock(return_value=execution),
                persist_iteration_dependencies=_persist_dependencies(),
                persist_iteration_phase_fn=mock.Mock(
                    return_value=PersistIterationPhaseResult(
                        consecutive_failures=3,
                        telemetry_rel="runs/auto-session-run-01/run-telemetry.json",
                    )
                ),
                append_runtime_event=mock.Mock(),
            )

            result = run_auto_improve_iteration(
                AutoImproveIterationRequest(
                    vault=vault,
                    policy={"version": "2026-04-21"},
                    resolved_policy_path=Path("ops/policies/wiki-maintainer-policy.yaml"),
                    session=session,
                    session_id="auto-session",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    iteration=1,
                    attempted=set(),
                    quarantined=set(),
                    consecutive_failures=2,
                    pre_promotion_failure_outcomes={"scope_blocked"},
                    context=_context(),
                ),
                dependencies=dependencies,
                build_run_id=lambda *_args: "auto-session-run-01",
            )

            self.assertFalse(result.keep_running)
            self.assertEqual(result.stop_reason, "failure_budget_exhausted")
            self.assertEqual(result.consecutive_failures, 3)
            self.assertEqual(session["attempted_proposal_ids"], ["proposal-1"])
            self.assertEqual(session["run_ids"], ["auto-session-run-01"])
            self.assertTrue((vault / "runs" / "auto-session-run-01").is_dir())
            dependencies.append_runtime_event.assert_called_once_with(
                vault,
                context=_context(),
                component="auto_improve_session",
                phase="route_scaffold",
                decision="blocked",
                artifact_path="runs/auto-session-run-01/scope-freeze.json",
                duration_ms=300,
                run_id="auto-session-run-01",
                session_id="auto-session",
                policy_version="2026-04-21",
                proposal_id="proposal-1",
                candidate_id="",
                decision_reason="scope_freeze_status",
            )

    def test_run_auto_improve_iteration_stops_on_retryable_executor_usage_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            proposal = {"proposal_id": "proposal-1", "primary_targets": ["ops/scripts/example.py"]}
            route_scaffold = SimpleNamespace(
                scope_freeze={"status": "ready", "resolution": {"test_files": []}},
                scope_freeze_rel="runs/auto-session-run-01/scope-freeze.json",
                roles=["worker"],
                routing_report_rels=["runs/auto-session-run-01/subagent-routing.worker.json"],
                phase_durations={"scope": 0.1, "route": 0.2},
            )
            execution = ExecuteEvaluatePhaseResult(
                outcome=ExecutionOutcome(
                    outcome="executor_usage_limited",
                    next_consecutive_failures=0,
                    quarantine_proposal=False,
                ),
                phase_durations={"experiment": 0.4},
            )
            session = {
                "budget": {"max_consecutive_failures": 1},
                "attempted_proposal_ids": [],
                "run_ids": [],
                "queue_snapshot": [],
            }
            dependencies = AutoImproveIterationDependencies(
                refresh_select_phase=mock.Mock(
                    return_value=SimpleNamespace(
                        proposal=proposal,
                        queue_snapshot=["proposal-1"],
                        stop_reason=None,
                    )
                ),
                route_scaffold_phase=mock.Mock(return_value=route_scaffold),
                execute_evaluate_dependencies=_execute_dependencies(),
                execute_evaluate_phase_fn=mock.Mock(return_value=execution),
                persist_iteration_dependencies=_persist_dependencies(),
                persist_iteration_phase_fn=mock.Mock(
                    return_value=PersistIterationPhaseResult(
                        consecutive_failures=0,
                        telemetry_rel="runs/auto-session-run-01/run-telemetry.json",
                    )
                ),
                append_runtime_event=mock.Mock(),
            )

            result = run_auto_improve_iteration(
                AutoImproveIterationRequest(
                    vault=vault,
                    policy={"version": "2026-04-21"},
                    resolved_policy_path=Path("ops/policies/wiki-maintainer-policy.yaml"),
                    session=session,
                    session_id="auto-session",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    iteration=1,
                    attempted=set(),
                    quarantined=set(),
                    consecutive_failures=0,
                    pre_promotion_failure_outcomes={"mutation_failed"},
                    context=_context(),
                ),
                dependencies=dependencies,
                build_run_id=lambda *_args: "auto-session-run-01",
            )

            self.assertFalse(result.keep_running)
            self.assertEqual(result.stop_reason, "executor_usage_limited")
            self.assertEqual(result.consecutive_failures, 0)
            self.assertEqual(session["attempted_proposal_ids"], ["proposal-1"])
            self.assertEqual(session["run_ids"], ["auto-session-run-01"])

    def test_run_auto_improve_iteration_stops_on_generated_evidence_settle_without_budget(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            proposal = {"proposal_id": "proposal-1", "primary_targets": ["ops/scripts/example.py"]}
            route_scaffold = SimpleNamespace(
                scope_freeze={"status": "ready", "resolution": {"test_files": []}},
                scope_freeze_rel="runs/auto-session-run-01/scope-freeze.json",
                roles=["worker"],
                routing_report_rels=["runs/auto-session-run-01/subagent-routing.worker.json"],
                phase_durations={"scope": 0.1, "route": 0.2},
            )
            execution = ExecuteEvaluatePhaseResult(
                outcome=ExecutionOutcome(
                    outcome=GENERATED_EVIDENCE_SETTLE_REQUIRED,
                    next_consecutive_failures=0,
                    quarantine_proposal=False,
                ),
                phase_durations={"experiment": 0.4},
            )
            session = {
                "budget": {"max_consecutive_failures": 1},
                "attempted_proposal_ids": [],
                "run_ids": [],
                "queue_snapshot": [],
            }
            dependencies = AutoImproveIterationDependencies(
                refresh_select_phase=mock.Mock(
                    return_value=SimpleNamespace(
                        proposal=proposal,
                        queue_snapshot=["proposal-1"],
                        stop_reason=None,
                    )
                ),
                route_scaffold_phase=mock.Mock(return_value=route_scaffold),
                execute_evaluate_dependencies=_execute_dependencies(),
                execute_evaluate_phase_fn=mock.Mock(return_value=execution),
                persist_iteration_dependencies=_persist_dependencies(),
                persist_iteration_phase_fn=mock.Mock(
                    return_value=PersistIterationPhaseResult(
                        consecutive_failures=0,
                        telemetry_rel="runs/auto-session-run-01/run-telemetry.json",
                    )
                ),
                append_runtime_event=mock.Mock(),
            )

            result = run_auto_improve_iteration(
                AutoImproveIterationRequest(
                    vault=vault,
                    policy={"version": "2026-04-21"},
                    resolved_policy_path=Path("ops/policies/wiki-maintainer-policy.yaml"),
                    session=session,
                    session_id="auto-session",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    iteration=1,
                    attempted=set(),
                    quarantined=set(),
                    consecutive_failures=0,
                    pre_promotion_failure_outcomes={"mutation_failed"},
                    context=_context(),
                ),
                dependencies=dependencies,
                build_run_id=lambda *_args: "auto-session-run-01",
            )

            self.assertFalse(result.keep_running)
            self.assertEqual(result.stop_reason, GENERATED_EVIDENCE_SETTLE_REQUIRED)
            self.assertEqual(result.consecutive_failures, 0)
            self.assertEqual(session["attempted_proposal_ids"], ["proposal-1"])
            self.assertEqual(session["run_ids"], ["auto-session-run-01"])
