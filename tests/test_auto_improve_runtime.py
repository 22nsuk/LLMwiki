from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts import auto_improve_runtime
from ops.scripts.codex_goal_client import set_goal
from ops.scripts.auto_improve_execute_runtime import (
    ExecuteEvaluateDependencies,
    ExecuteEvaluateRequest,
)
from ops.scripts.auto_improve_runtime import (
    AutoImproveLearningReviewRequiredError,
    AutoImproveUsageError,
    refresh_auto_improve_session_report,
    run_auto_improve_session,
)
from ops.scripts.run_mechanism_experiment_runtime import (
    RunMechanismExperimentError,
    RunMechanismExperimentMutationError,
)
from ops.scripts.runtime_context import RuntimeContext

from tests.minimal_vault_runtime import seed_subagent_profiles
from tests.run_mechanism_experiment_test_utils import mutation_proposal_report, seed_wrapper_vault
from tests.test_codex_goal_contract import sample_goal_contract


def _incrementing_runtime_context(start: dt.datetime | None = None) -> RuntimeContext:
    current = {
        "value": start or dt.datetime(2026, 4, 15, 0, 0, tzinfo=dt.timezone.utc)
    }

    def clock() -> dt.datetime:
        value = current["value"]
        current["value"] = value + dt.timedelta(seconds=1)
        return value

    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=clock,
        session_id="auto-incrementing",
        executor_id="codex_exec",
    )


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


def _learning_review_required_report() -> dict[str, object]:
    return {
        "generated_at": "2026-04-15T00:00:00Z",
        "execution_readiness": {
            "status": "pass",
            "can_run": True,
        },
        "learning_readiness": {
            "status": "learning_uncertain",
            "gate_effect": "review_required",
            "can_run": True,
            "likely_to_learn": False,
            "metrics": {
                "session_reports_considered": 0,
            },
            "recommended_next_step": (
                "Execution readiness is pass, but learning readiness still requires explicit operator review. "
                "Rerun auto-improve with --allow-learning-uncertain only if you want a bounded trial."
            ),
        },
        "queue": {
            "runnable_proposal_ids": ["proposal-ready"],
            "runnable_proposal_count": 1,
        },
    }


def _seed_scaffolded_run(vault: Path, run_id: str) -> None:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-ledger.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": run_id,
                "status": "draft",
                "events": [
                    {
                        "ts": "2026-04-15T00:00:00Z",
                        "type": "created",
                        "summary": "created",
                        "artifacts": ["seed.yaml"],
                        "decision": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "proposal-snapshot.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/proposal-snapshot.schema.json",
                "run_id": run_id,
                "source_report": "ops/reports/mutation-proposals.json",
                "captured_at": "2026-04-15T00:00:00Z",
                "proposal": mutation_proposal_report("ops/scripts/example.py")["proposals"][0],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_executor_report(
    vault: Path,
    run_id: str,
    *,
    role: str,
    status: str,
    sandbox_mode: str,
    model: str,
    reasoning_effort: str,
    returncode: int,
    notes: list[str],
) -> None:
    (vault / "runs" / run_id / f"{role}-executor-report.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/executor-report.schema.json",
                "run_id": run_id,
                "role": role,
                "generated_at": "2026-04-15T00:00:00Z",
                "executor": {
                    "name": "codex_exec",
                    "sandbox_mode": sandbox_mode,
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                },
                "status": status,
                "command": {"argv": ["codex", "exec"]},
                "artifacts": {
                    "prompt": f"runs/{run_id}/{role}-prompt.md",
                    "output_last_message": f"runs/{run_id}/{role}-last-message.json",
                    "stdout": f"runs/{run_id}/{role}.stdout.txt",
                    "stderr": f"runs/{run_id}/{role}.stderr.txt",
                },
                "result": {
                    "returncode": returncode,
                    "timed_out": False,
                    "timeout_seconds": 1800,
                    "termination_reason": "completed",
                },
                "diagnostics": {
                    "routing_report": f"runs/{run_id}/subagent-routing.{role}.json",
                    "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                    "notes": notes,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_successful_run_telemetry(
    vault: Path,
    run_id: str,
    *,
    shadow_apply_rel: str,
    rollback_rehearsal_rel: str,
) -> None:
    (vault / "runs" / run_id / "run-telemetry.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "session_id": "",
                "run_id": run_id,
                "generated_at": "2026-04-15T00:00:00Z",
                "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                "routing_reports": [],
                "executor_reports": [],
                "command_timeouts": {
                    "mutation_command": {
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                    },
                    "repo_health": {
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                    },
                },
                "workspace_preparation": {
                    "mode": "full_copy",
                    "baseline_file_count": 10,
                    "copied_file_count": 10,
                    "phase_durations": {
                        "digest": 0.1,
                        "copy": 0.2,
                        "total": 0.3,
                    },
                },
                "apply_mode": "live",
                "apply_status": "live_applied",
                "live_applied": True,
                "shadow_apply_report": shadow_apply_rel,
                "rollback_rehearsal_report": rollback_rehearsal_rel,
                "timeout_failure_artifacts": [
                    f"runs/{run_id}/worker-executor-timeout-failure.json"
                ],
                "decision": "PROMOTE",
                "finalized": True,
                "finalize_result": {"run_id": run_id},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_worker_timeout_failure(vault: Path, run_id: str) -> None:
    (vault / "runs" / run_id / "worker-executor-timeout-failure.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/timeout-failure.schema.json",
                "run_id": run_id,
                "generated_at": "2026-04-15T00:00:00Z",
                "phase": "executor",
                "role": "worker",
                "command": {"argv": ["codex", "exec", "-"]},
                "result": {
                    "returncode": -15,
                    "timed_out": True,
                    "timeout_seconds": 1800,
                    "termination_reason": "timeout",
                },
                "artifacts": {
                    "stdout": f"runs/{run_id}/worker.stdout.txt",
                    "stderr": f"runs/{run_id}/worker.stderr.txt",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_successful_executor_reports(vault: Path, run_id: str) -> None:
    _write_executor_report(
        vault,
        run_id,
        role="worker",
        status="pass",
        sandbox_mode="workspace-write",
        model="gpt-5.5",
        reasoning_effort="high",
        returncode=0,
        notes=["worker applied mutation"],
    )
    _write_executor_report(
        vault,
        run_id,
        role="validator",
        status="pass",
        sandbox_mode="read-only",
        model="gpt-5.5",
        reasoning_effort="xhigh",
        returncode=0,
        notes=["validator approved"],
    )


def _fake_successful_mechanism_experiment(
    vault_path: Path,
    *,
    run_id: str,
    scaffold_only: bool,
    **_: object,
) -> dict:
    if scaffold_only:
        _seed_scaffolded_run(vault_path, run_id)
        return {"run_id": run_id, "scaffold_only": True}
    shadow_apply_rel = f"runs/{run_id}/shadow-apply-report.json"
    rollback_rehearsal_rel = f"runs/{run_id}/rollback-rehearsal-report.json"
    (vault_path / shadow_apply_rel).write_text(
        json.dumps({"status": "ready_for_live_apply"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (vault_path / rollback_rehearsal_rel).write_text(
        json.dumps({"status": "pass"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_successful_run_telemetry(
        vault_path,
        run_id,
        shadow_apply_rel=shadow_apply_rel,
        rollback_rehearsal_rel=rollback_rehearsal_rel,
    )
    _write_worker_timeout_failure(vault_path, run_id)
    _write_successful_executor_reports(vault_path, run_id)
    return {
        "run_id": run_id,
        "decision": "PROMOTE",
        "apply_mode": "live",
        "apply_status": "live_applied",
        "live_applied": True,
        "shadow_apply_report": shadow_apply_rel,
        "rollback_rehearsal_report": rollback_rehearsal_rel,
        "finalized": True,
        "finalize_result": {"run_id": run_id},
        "repo_health": {"passed": True},
    }


def _fake_discarded_mechanism_experiment(
    vault_path: Path,
    *,
    run_id: str,
    scaffold_only: bool,
    **_: object,
) -> dict:
    if scaffold_only:
        _seed_scaffolded_run(vault_path, run_id)
        return {"run_id": run_id, "scaffold_only": True}
    _write_successful_run_telemetry(
        vault_path,
        run_id,
        shadow_apply_rel=f"runs/{run_id}/shadow-apply-report.json",
        rollback_rehearsal_rel=f"runs/{run_id}/rollback-rehearsal-report.json",
    )
    _write_successful_executor_reports(vault_path, run_id)
    return {
        "run_id": run_id,
        "decision": "DISCARD",
        "finalized": True,
        "finalize_result": {"run_id": run_id},
        "repo_health": {"passed": True},
    }


def _load_successful_auto_improve_artifacts(vault: Path, result: dict) -> dict:
    session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
    run_id = session["run_ids"][0]
    run_dir = vault / "runs" / run_id
    return {
        "session": session,
        "provenance_aggregate": json.loads(
            (vault / result["routing_provenance_aggregate"]).read_text(encoding="utf-8")
        ),
        "promotion_trends": json.loads(
            (vault / result["promotion_decision_trends"]).read_text(encoding="utf-8")
        ),
        "run_artifact_fingerprint": json.loads(
            (run_dir / "run-artifact-fingerprint.json").read_text(encoding="utf-8")
        ),
        "telemetry": json.loads((run_dir / "run-telemetry.json").read_text(encoding="utf-8")),
        "run_events": [
            json.loads(line)
            for line in (run_dir / "runtime-events.jsonl").read_text(encoding="utf-8").splitlines()
        ],
        "session_events": [
            json.loads(line)
            for line in (
                vault
                / "ops"
                / "reports"
                / "runtime-events"
                / "auto-improve-session"
                / "auto-session.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ],
        "routing_reports": [
            json.loads((vault / rel_path).read_text(encoding="utf-8"))
            for rel_path in session["iterations"][0]["routing_reports"]
        ],
    }


def _count_routing_decision_field(routing_reports: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in routing_reports:
        routing_decision = report.get("routing_decision", {})
        if not isinstance(routing_decision, dict):
            continue
        value = str(routing_decision.get(field, "")).strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _assert_successful_session_rollups(
    case: unittest.TestCase,
    result: dict,
    proposal: dict,
    artifacts: dict,
) -> None:
    session = artifacts["session"]
    routing_reports = artifacts["routing_reports"]
    case.assertEqual(result["session_id"], "auto-session")
    case.assertEqual(session["iterations"][0]["outcome"], "promoted")
    case.assertEqual(session["attempted_proposal_ids"], [proposal["proposal_id"]])
    case.assertEqual(session["run_ids"][0], session["iterations"][0]["run_id"])
    case.assertEqual(session["rollups"]["iterations"]["outcome_counts"], {"promoted": 1})
    case.assertEqual(session["rollups"]["routing"]["role_counts"], {"validator": 1, "worker": 1})
    for field, rollup_key in (
        ("selected_rung", "selected_rung_counts"),
        ("score_band", "score_band_counts"),
        ("sandbox_mode", "sandbox_mode_counts"),
        ("model", "model_counts"),
        ("reasoning_effort", "reasoning_effort_counts"),
    ):
        case.assertEqual(
            session["rollups"]["routing"][rollup_key],
            _count_routing_decision_field(routing_reports, field),
        )
    case.assertEqual(session["rollups"]["routing"]["risk_flag_counts"], {})
    case.assertEqual(session["rollups"]["executor"]["status_counts"], {"pass": 2})
    case.assertEqual(session["rollups"]["executor"]["returncode_counts"], {"0": 2})
    case.assertEqual(session["rollups"]["telemetry"]["report_count"], 1)
    case.assertIn("routing", session["rollups"]["telemetry"]["phase_totals_seconds"])


def _assert_successful_session_provenance(case: unittest.TestCase, artifacts: dict) -> None:
    session = artifacts["session"]
    provenance_aggregate = artifacts["provenance_aggregate"]
    promotion_trends = artifacts["promotion_trends"]
    case.assertEqual(provenance_aggregate["summary"]["run_count"], 1)
    case.assertEqual(provenance_aggregate["summary"]["artifact_fingerprint_count"], 1)
    case.assertEqual(provenance_aggregate["audit_rollup"]["routing"], session["rollups"]["routing"])
    case.assertEqual(provenance_aggregate["audit_rollup"]["executor"], session["rollups"]["executor"])
    case.assertEqual(provenance_aggregate["audit_rollup"]["telemetry"], session["rollups"]["telemetry"])
    case.assertEqual(provenance_aggregate["audit_rollup"]["coverage"]["runs_with_routing"], 1)
    case.assertEqual(provenance_aggregate["audit_rollup"]["coverage"]["runs_with_executor"], 1)
    case.assertEqual(
        provenance_aggregate["audit_rollup"]["loop_health"]["attempt_count"],
        session["rollups"]["outcome_metrics"]["attempt_count"],
    )
    case.assertEqual(
        provenance_aggregate["audit_rollup"]["loop_health"]["moving_averages"],
        session["rollups"]["outcome_metrics"]["moving_averages"],
    )
    case.assertEqual(provenance_aggregate["audit_rollup"]["loop_health"]["finalized_run_count"], 1)
    case.assertEqual(
        provenance_aggregate["audit_rollup"]["loop_health"]["coverage_ratios"]["promotion_report"],
        0.0,
    )
    case.assertEqual(provenance_aggregate["audit_rollup"]["loop_health"]["health_flags"], [])
    case.assertEqual(promotion_trends["summary"]["promotion_reports_considered"], 0)


def _assert_successful_run_telemetry(case: unittest.TestCase, artifacts: dict) -> None:
    session = artifacts["session"]
    telemetry = artifacts["telemetry"]
    run_artifact_fingerprint = artifacts["run_artifact_fingerprint"]
    run_id = session["run_ids"][0]
    artifact_paths = [item["path"] for item in run_artifact_fingerprint["artifacts"]]
    case.assertIn(f"runs/{run_id}/run-telemetry.json", artifact_paths)
    case.assertEqual(
        telemetry["command_timeouts"],
        {
            "mutation_command": _expected_timeout_summary(
                timed_out=False,
                timeout_seconds=5400,
                termination_reason="completed",
            ),
            "repo_health": _expected_timeout_summary(
                timed_out=False,
                timeout_seconds=5400,
                termination_reason="completed",
            ),
        },
    )
    case.assertEqual(
        telemetry["timeout_failure_artifacts"],
        [f"runs/{run_id}/worker-executor-timeout-failure.json"],
    )
    case.assertEqual(telemetry["apply_mode"], "live")
    case.assertEqual(telemetry["apply_status"], "live_applied")
    case.assertTrue(telemetry["live_applied"])
    case.assertTrue(telemetry["finalized"])
    case.assertEqual(telemetry["shadow_apply_report"], f"runs/{run_id}/shadow-apply-report.json")
    case.assertEqual(
        telemetry["rollback_rehearsal_report"],
        f"runs/{run_id}/rollback-rehearsal-report.json",
    )
    case.assertIn(f"runs/{run_id}/rollback-rehearsal-report.json", artifact_paths)


def _assert_successful_runtime_events_and_learning(case: unittest.TestCase, artifacts: dict) -> None:
    session = artifacts["session"]
    run_events = artifacts["run_events"]
    session_events = artifacts["session_events"]
    case.assertEqual(run_events[0]["phase"], "route_scaffold")
    case.assertEqual(run_events[0]["component"], "auto_improve_session")
    case.assertEqual(run_events[0]["policy_version"], 4)
    case.assertEqual(session_events[-1]["phase"], "complete")
    case.assertEqual(session_events[-1]["decision"], "proposal_budget_exhausted")
    case.assertEqual(
        session["learning_mode"],
        {
            "allow_learning_uncertain": True,
            "bounded_trial": True,
        },
    )
    case.assertEqual(session["pre_run_readiness"]["learning_status"], "learning_uncertain")
    case.assertEqual(session["pre_run_readiness"]["learning_gate_effect"], "review_required")
    case.assertEqual(session["loop_state"]["consecutive_failures"], 0)
    case.assertEqual(session["loop_state"]["last_outcome"], "promoted")
    case.assertEqual(session["loop_state"]["last_decision"], "PROMOTE")
    case.assertEqual(session["loop_state"]["last_run_id"], session["run_ids"][0])
    case.assertEqual(session["loop_state"]["last_blocking_reason"], "")
    case.assertTrue(session["loop_state"]["updated_at"])


class AutoImproveRuntimeTests(unittest.TestCase):
    def test_mutation_error_classifies_codex_usage_limit_as_retryable_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "auto-session-run-01"
            (vault / "runs" / run_id).mkdir(parents=True)
            _write_executor_report(
                vault,
                run_id,
                role="worker",
                status="fail",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                returncode=1,
                notes=[],
            )
            (vault / "runs" / run_id / "worker.stderr.txt").write_text(
                "ERROR: You've hit your usage limit. Try again at May 16th, 2026 12:29 AM.\n",
                encoding="utf-8",
            )

            outcome = auto_improve_runtime.evaluate_mutation_error(
                run_id=run_id,
                roles=["worker"],
                artifact_root=vault,
                pre_promotion_failure_outcomes={"mutation_failed", "executor_usage_limited"},
                consecutive_failures=2,
            )

            self.assertEqual(outcome.outcome, "executor_usage_limited")
            self.assertEqual(outcome.next_consecutive_failures, 2)
            self.assertFalse(outcome.quarantine_proposal)

    def test_refresh_select_phase_returns_selected_proposal_and_queue_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            context = RuntimeContext(display_timezone=dt.timezone.utc)

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            with mock.patch(
                "ops.scripts.auto_improve_runtime._refresh_reports",
                side_effect=fake_refresh_reports,
            ):
                result = auto_improve_runtime._refresh_select_phase(
                    vault,
                    {},
                    Path("ops/policies/wiki-maintainer-policy.yaml"),
                    attempted=set(),
                    quarantined=set(),
                    context=context,
                )

            self.assertEqual(result.proposal, proposal)
            self.assertEqual(result.queue_snapshot, [proposal["proposal_id"]])
            self.assertIsNone(result.stop_reason)

    def test_refresh_select_phase_marks_queue_exhausted_when_no_proposal_is_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            context = RuntimeContext(display_timezone=dt.timezone.utc)

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            with mock.patch(
                "ops.scripts.auto_improve_runtime._refresh_reports",
                side_effect=fake_refresh_reports,
            ):
                result = auto_improve_runtime._refresh_select_phase(
                    vault,
                    {},
                    Path("ops/policies/wiki-maintainer-policy.yaml"),
                    attempted={proposal["proposal_id"]},
                    quarantined=set(),
                    context=context,
                )

            self.assertIsNone(result.proposal)
            self.assertEqual(result.queue_snapshot, [])
            self.assertEqual(result.stop_reason, "queue_exhausted")

    def test_execute_evaluate_phase_uses_scope_blocked_without_full_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            context = RuntimeContext(display_timezone=dt.timezone.utc)
            scope_freeze = {
                "status": "blocked",
                "resolution": {"test_files": []},
            }

            with mock.patch(
                "ops.scripts.auto_improve_runtime.run_mechanism_experiment"
            ) as experiment:
                result = auto_improve_runtime._execute_evaluate_phase(
                    ExecuteEvaluateRequest(
                        vault=vault,
                        resolved_policy_path=Path("ops/policies/wiki-maintainer-policy.yaml"),
                        run_id="auto-session-run-01-example",
                        proposal=proposal,
                        scope_freeze=scope_freeze,
                        scope_freeze_rel="runs/auto-session-run-01-example/scope-freeze.json",
                        roles=["worker"],
                        routing_report_rels=[
                            "runs/auto-session-run-01-example/subagent-routing.worker.json"
                        ],
                        consecutive_failures=2,
                        pre_promotion_failure_outcomes={"scope_blocked"},
                        proposal_report_path="ops/reports/mutation-proposals.json",
                        context=context,
                        dependencies=ExecuteEvaluateDependencies(
                            mutation_command=auto_improve_runtime._mutation_command,
                            run_mechanism_experiment=auto_improve_runtime.run_mechanism_experiment,
                            role_report_path=auto_improve_runtime._role_report_path,
                            evaluate_scope_blocked=auto_improve_runtime.evaluate_scope_blocked,
                            evaluate_experiment_result=auto_improve_runtime.evaluate_experiment_result,
                            evaluate_mutation_error=auto_improve_runtime.evaluate_mutation_error,
                            evaluate_experiment_error=auto_improve_runtime.evaluate_experiment_error,
                        ),
                    )
                )

            experiment.assert_not_called()
            self.assertEqual(result.outcome.outcome, "scope_blocked")
            self.assertEqual(result.outcome.next_consecutive_failures, 3)
            self.assertEqual(set(result.phase_durations), {"experiment"})

    def test_run_auto_improve_session_writes_successful_session_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.run_mechanism_experiment",
                    side_effect=_fake_successful_mechanism_experiment,
                ),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=2,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            artifacts = _load_successful_auto_improve_artifacts(vault, result)
            _assert_successful_session_rollups(self, result, proposal, artifacts)
            _assert_successful_session_provenance(self, artifacts)
            _assert_successful_run_telemetry(self, artifacts)
            _assert_successful_runtime_events_and_learning(self, artifacts)

    def test_run_auto_improve_session_maintains_after_proposal_budget_until_wall_clock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            monotonic = {"now": 0.0}

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_monotonic() -> float:
                return monotonic["now"]

            def fake_sleep(seconds: float) -> None:
                monotonic["now"] += seconds

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports) as refresh,
                mock.patch(
                    "ops.scripts.auto_improve_runtime.run_mechanism_experiment",
                    side_effect=_fake_successful_mechanism_experiment,
                ),
                mock.patch("ops.scripts.auto_improve_runtime.time.monotonic", side_effect=fake_monotonic),
                mock.patch("ops.scripts.auto_improve_runtime.time.sleep", side_effect=fake_sleep) as sleep,
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-maintained",
                    max_proposals=1,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                    maintain_until_budget=True,
                    maintenance_interval_seconds=300,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            maintenance = session["maintenance"]
            self.assertEqual(result["stop_reason"], "time_budget_exhausted")
            self.assertEqual(monotonic["now"], 1800)
            self.assertEqual(maintenance["status"], "complete")
            self.assertEqual(maintenance["mode"], "proposal_budget_runtime_maintenance")
            self.assertEqual(maintenance["target_elapsed_seconds"], 1800)
            self.assertEqual(maintenance["expected_min_cycle_count"], 7)
            self.assertEqual(maintenance["cycle_count"], 7)
            self.assertEqual(maintenance["meaningful_cycle_count"], 7)
            self.assertEqual(maintenance["last_cycle_elapsed_seconds"], 1800)
            self.assertTrue(all(cycle["status"] == "pass" for cycle in maintenance["cycles"]))
            self.assertTrue(
                all(
                    set(cycle["work_items"])
                    >= {
                        "mechanism_review_report",
                        "mutation_proposal_report",
                        "auto_improve_readiness_report",
                        "auto_improve_session_report",
                    }
                    for cycle in maintenance["cycles"]
                )
            )
            self.assertEqual(refresh.call_count, 9)
            self.assertEqual(sleep.call_count, 6)

    def test_run_auto_improve_session_stops_after_discard_without_runtime_maintenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            monotonic = {"now": 0.0}

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_monotonic() -> float:
                return monotonic["now"]

            def fake_sleep(seconds: float) -> None:
                monotonic["now"] += seconds

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports) as refresh,
                mock.patch(
                    "ops.scripts.auto_improve_runtime.run_mechanism_experiment",
                    side_effect=_fake_discarded_mechanism_experiment,
                ),
                mock.patch("ops.scripts.auto_improve_runtime.time.monotonic", side_effect=fake_monotonic),
                mock.patch("ops.scripts.auto_improve_runtime.time.sleep", side_effect=fake_sleep) as sleep,
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-discard-maintained",
                    max_proposals=1,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                    maintain_until_budget=True,
                    maintenance_interval_seconds=300,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(result["stop_reason"], "failure_budget_exhausted")
            self.assertEqual(monotonic["now"], 0)
            self.assertEqual(session["iterations"][0]["decision"], "DISCARD")
            self.assertEqual(session["iterations"][0]["outcome"], "discarded")
            self.assertEqual(session["iterations"][0]["status"], "blocked")
            self.assertEqual(session["iterations"][0]["failure_taxonomy"], "discarded")
            self.assertFalse(any(item.get("decision") == "PROMOTE" for item in session["iterations"]))
            self.assertNotIn("maintenance", session)
            self.assertEqual(session["loop_state"]["consecutive_failures"], 1)
            self.assertEqual(session["loop_state"]["last_blocking_reason"], "discarded")
            self.assertEqual(session["loop_state"]["blocking_reason_counts"], {"discarded": 1})
            self.assertEqual(
                session["rollups"]["telemetry"]["failure_taxonomy_counts"],
                {"discarded": 1},
            )
            self.assertEqual(refresh.call_count, 2)
            sleep.assert_not_called()

    def test_run_auto_improve_session_blocks_learning_uncertain_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            readiness_path = vault / "ops" / "reports" / "auto-improve-readiness.json"

            with (
                mock.patch(
                    "ops.scripts.auto_improve_runtime._refresh_reports",
                    return_value=({}, {"proposals": []}),
                ),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.build_readiness_report",
                    return_value=_learning_review_required_report(),
                ),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.write_readiness_report",
                    return_value=readiness_path,
                ),
            ):
                with self.assertRaisesRegex(
                    AutoImproveLearningReviewRequiredError,
                    "--allow-learning-uncertain",
                ):
                    run_auto_improve_session(
                        vault,
                        policy_path="ops/policies/wiki-maintainer-policy.yaml",
                        session_id="auto-session-blocked",
                        max_proposals=1,
                        max_minutes=30,
                        max_consecutive_failures=1,
                        executor_name="codex_exec",
                    )

            session = json.loads(
                (
                    vault
                    / "ops"
                    / "reports"
                    / "auto-improve-sessions"
                    / "auto-session-blocked.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(session["status"], "blocked")
            self.assertEqual(session["stop_reason"], "learning_review_required")
            self.assertEqual(
                session["learning_mode"],
                {
                    "allow_learning_uncertain": False,
                    "bounded_trial": False,
                },
            )
            self.assertEqual(session["pre_run_readiness"]["learning_gate_effect"], "review_required")
            self.assertEqual(session["queue_snapshot"], ["proposal-ready"])

    def test_run_auto_improve_session_marks_bounded_trial_when_override_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            readiness_path = vault / "ops" / "reports" / "auto-improve-readiness.json"

            def fake_complete(
                vault_path: Path,
                start: auto_improve_runtime.AutoImproveSessionStart,
                state: auto_improve_runtime.AutoImproveLoopState,
            ) -> dict[str, object]:
                start.session["status"] = "complete"
                start.session["stop_reason"] = state.stop_reason
                auto_improve_runtime._write_session_report(
                    vault_path,
                    start.session,
                    context=start.context,
                )
                return {
                    "session_id": start.session_id,
                    "session_report": start.session["path"],
                    "routing_provenance_aggregate": (
                        f"ops/reports/routing-provenance-aggregates/{start.session_id}.json"
                    ),
                    "promotion_decision_trends": "ops/reports/promotion-decision-trends.json",
                    "outcome_metrics": "ops/reports/outcome-metrics.json",
                    "iterations": len(start.session["iterations"]),
                    "stop_reason": state.stop_reason,
                    "run_ids": start.session["run_ids"],
                }

            with (
                mock.patch(
                    "ops.scripts.auto_improve_runtime._refresh_reports",
                    return_value=({}, {"proposals": []}),
                ),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.build_readiness_report",
                    return_value=_learning_review_required_report(),
                ),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.write_readiness_report",
                    return_value=readiness_path,
                ),
                mock.patch(
                    "ops.scripts.auto_improve_runtime._run_auto_improve_iteration",
                    return_value=False,
                ),
                mock.patch(
                    "ops.scripts.auto_improve_runtime._complete_auto_improve_session",
                    side_effect=fake_complete,
                ),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-bounded-trial",
                    max_proposals=1,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(session["status"], "complete")
            self.assertEqual(
                session["learning_mode"],
                {
                    "allow_learning_uncertain": True,
                    "bounded_trial": True,
                },
            )
            self.assertEqual(session["pre_run_readiness"]["learning_status"], "learning_uncertain")
            self.assertEqual(session["queue_snapshot"], ["proposal-ready"])

    def test_run_auto_improve_session_rejects_unsupported_executor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(AutoImproveUsageError, "unsupported executor"):
                run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-unsupported-executor",
                    executor_name="shell_exec",
                )

    def test_run_auto_improve_session_rejects_zero_budget_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(AutoImproveUsageError, "max_proposals"):
                run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-zero-budget",
                    max_proposals=0,
                )

    def test_goal_contract_rejects_policy_and_cli_budgets_above_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            set_goal(sample_goal_contract(), vault=vault)

            with self.assertRaisesRegex(
                AutoImproveUsageError,
                "max_proposals exceeds goal contract budget",
            ):
                run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-policy-contract-budget",
                    goal_contract_path="ops/reports/codex-goal-contract.json",
                    executor_name="codex_exec",
                )

            with self.assertRaisesRegex(
                AutoImproveUsageError,
                "max_proposals exceeds goal contract budget",
            ):
                run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-cli-contract-budget",
                    goal_contract_path="ops/reports/codex-goal-contract.json",
                    max_proposals=2,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                )

    def test_proposal_budget_exhausted_resume_keeps_same_goal_contract_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            set_goal(sample_goal_contract(), vault=vault)
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.run_mechanism_experiment",
                    side_effect=_fake_successful_mechanism_experiment,
                ),
            ):
                first = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-contract-budget-limited",
                    goal_contract_path="ops/reports/codex-goal-contract.json",
                    max_proposals=1,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            first_session = json.loads((vault / first["session_report"]).read_text(encoding="utf-8"))
            contract_digest = first_session["goal_contract"]["contract_sha256"]
            self.assertEqual(first["stop_reason"], "proposal_budget_exhausted")

            with mock.patch(
                "ops.scripts.auto_improve_runtime._refresh_reports",
                side_effect=AssertionError("proposal-budget resume should not refresh proposals"),
            ):
                resumed = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    resume_session="auto-session-contract-budget-limited",
                    goal_contract_path="ops/reports/codex-goal-contract.json",
                    max_proposals=1,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            resumed_session = json.loads((vault / resumed["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(resumed["stop_reason"], "proposal_budget_exhausted")
            self.assertEqual(resumed["iterations"], 1)
            self.assertEqual(resumed_session["goal_contract"]["contract_sha256"], contract_digest)

    def test_resume_budget_override_bounds_maintenance_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch(
                    "ops.scripts.auto_improve_runtime.run_mechanism_experiment",
                    side_effect=_fake_successful_mechanism_experiment,
                ),
            ):
                first = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-resume-maintenance",
                    max_proposals=1,
                    max_minutes=30,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            self.assertEqual(first["stop_reason"], "proposal_budget_exhausted")
            monotonic = {"now": 0.0}

            def fake_monotonic() -> float:
                return monotonic["now"]

            def fake_sleep(seconds: float) -> None:
                monotonic["now"] += seconds

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.time.monotonic", side_effect=fake_monotonic),
                mock.patch("ops.scripts.auto_improve_runtime.time.sleep", side_effect=fake_sleep),
            ):
                resumed = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    resume_session="auto-session-resume-maintenance",
                    max_proposals=1,
                    max_minutes=1,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                    maintain_until_budget=True,
                    maintenance_interval_seconds=300,
                )

            resumed_session = json.loads((vault / resumed["session_report"]).read_text(encoding="utf-8"))
            maintenance = resumed_session["maintenance"]
            self.assertEqual(resumed["stop_reason"], "time_budget_exhausted")
            self.assertEqual(resumed_session["budget"]["max_minutes"], 1)
            self.assertEqual(maintenance["status"], "complete")
            self.assertEqual(maintenance["target_elapsed_seconds"], 60)
            self.assertEqual(maintenance["cycle_count"], 2)
            self.assertEqual(maintenance["meaningful_cycle_count"], 2)

    def test_resume_restores_failure_streak_before_selecting_next_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                return {
                    "run_id": run_id,
                    "decision": "HOLD",
                    "finalized": False,
                    "finalize_result": {},
                    "repo_health": {"passed": True},
                }

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                first = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-resume-failure-budget",
                    max_proposals=2,
                    max_minutes=90,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            first_session_path = vault / first["session_report"]
            first_session = json.loads(first_session_path.read_text(encoding="utf-8"))
            self.assertEqual(first["stop_reason"], "failure_budget_exhausted")
            self.assertEqual(first_session["loop_state"]["consecutive_failures"], 1)
            self.assertEqual(first_session["loop_state"]["last_blocking_reason"], "hold")

            with mock.patch(
                "ops.scripts.auto_improve_runtime._refresh_reports",
                side_effect=AssertionError("resume should stop before refreshing proposals"),
            ):
                resumed = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    resume_session="auto-resume-failure-budget",
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            resumed_session = json.loads((vault / resumed["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(resumed["stop_reason"], "failure_budget_exhausted")
            self.assertEqual(resumed["iterations"], 1)
            self.assertEqual(len(resumed_session["iterations"]), 1)
            self.assertEqual(resumed_session["loop_state"]["consecutive_failures"], 1)

    def test_run_auto_improve_session_quarantines_pre_promotion_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                timeout_failure_rel = f"runs/{run_id}/validator-executor-timeout-failure.json"
                (vault_path / "runs" / run_id / "run-telemetry.json").write_text(
                    json.dumps(
                        {
                            "$schema": "ops/schemas/run-telemetry.schema.json",
                            "session_id": "",
                            "run_id": run_id,
                            "generated_at": "2026-04-15T00:00:00Z",
                            "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                            "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                            "routing_reports": [],
                            "executor_reports": [],
                            "command_timeouts": {
                                "mutation_command": {
                                    "timed_out": True,
                                    "timeout_seconds": 1800,
                                    "termination_reason": "timeout",
                                }
                            },
                            "timeout_failure_artifacts": [timeout_failure_rel],
                            "failure_taxonomy": "validation_blocked",
                            "decision": "",
                            "finalized": False,
                            "finalize_result": {},
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                (vault_path / timeout_failure_rel).write_text(
                    json.dumps(
                        {
                            "$schema": "ops/schemas/timeout-failure.schema.json",
                            "run_id": run_id,
                            "generated_at": "2026-04-15T00:00:00Z",
                            "phase": "executor",
                            "role": "validator",
                            "command": {"argv": ["codex", "exec", "-"]},
                            "result": {
                                "returncode": -15,
                                "timed_out": True,
                                "timeout_seconds": 1800,
                                "termination_reason": "timeout",
                            },
                            "artifacts": {
                                "stdout": f"runs/{run_id}/validator.stdout.txt",
                                "stderr": f"runs/{run_id}/validator.stderr.txt",
                            },
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                _write_executor_report(
                    vault_path,
                    run_id,
                    role="worker",
                    status="pass",
                    sandbox_mode="workspace-write",
                    model="gpt-5.5",
                    reasoning_effort="high",
                    returncode=0,
                    notes=["worker applied mutation"],
                )
                _write_executor_report(
                    vault_path,
                    run_id,
                    role="validator",
                    status="fail",
                    sandbox_mode="read-only",
                    model="gpt-5.5",
                    reasoning_effort="xhigh",
                    returncode=1,
                    notes=["validator blocked"],
                )
                raise RunMechanismExperimentMutationError("validator blocked")

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-fail",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=2,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                    context=_incrementing_runtime_context(),
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            run_id = session["run_ids"][0]
            telemetry = json.loads((vault / "runs" / run_id / "run-telemetry.json").read_text(encoding="utf-8"))
            decision_observed_at = session["next_run_decisions"][0]["observed_at"]
            embedded_envelope = json.loads(
                next(
                    item["value"]
                    for item in session["metadata"]["properties"]
                    if item["name"] == "urn:openai:artifact-envelope"
                )
            )
            self.assertEqual(session["iterations"][0]["outcome"], "validation_blocked")
            self.assertEqual(session["quarantined_proposal_ids"], [proposal["proposal_id"]])
            self.assertEqual(session["rollups"]["executor"]["blocking_role_counts"], {"validator": 1})
            self.assertEqual(session["rollups"]["telemetry"]["failure_taxonomy_counts"], {"validation_blocked": 1})
            self.assertGreaterEqual(session["generated_at"], decision_observed_at)
            self.assertEqual(embedded_envelope["generated_at"], session["generated_at"])
            self.assertEqual(
                embedded_envelope["currentness"]["checked_at"],
                session["generated_at"],
            )
            self.assertEqual(
                telemetry["command_timeouts"],
                {
                    "mutation_command": _expected_timeout_summary(
                        timed_out=True,
                        timeout_seconds=1800,
                        termination_reason="timeout",
                    )
                },
            )
            self.assertEqual(
                telemetry["timeout_failure_artifacts"],
                [f"runs/{run_id}/validator-executor-timeout-failure.json"],
            )
            stale_session = dict(session)
            stale_session["generated_at"] = "2026-04-14T00:00:00Z"
            (vault / result["session_report"]).write_text(
                json.dumps(stale_session, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            refresh_result = refresh_auto_improve_session_report(
                vault,
                session_id="auto-session-fail",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                context=_incrementing_runtime_context(
                    dt.datetime(2026, 4, 16, 0, 0, tzinfo=dt.timezone.utc)
                ),
            )
            refreshed = json.loads((vault / refresh_result["session_report"]).read_text(encoding="utf-8"))

            self.assertEqual(refresh_result["status"], session["status"])
            self.assertEqual(refresh_result["stop_reason"], session["stop_reason"])
            self.assertGreaterEqual(refreshed["generated_at"], decision_observed_at)
            self.assertGreaterEqual(refreshed["generated_at"], "2026-04-16T00:00:00Z")
            self.assertEqual(refresh_result["generated_at"], refreshed["generated_at"])

    def test_run_auto_improve_session_quarantines_scope_blocked_without_full_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            calls = {"scaffold": 0, "full": 0}

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_build_scope_freeze(*_: object, **__: object) -> dict:
                return {
                    "status": "blocked",
                    "inputs": {
                        "primary_targets": proposal["primary_targets"],
                        "supporting_targets": [],
                    },
                    "resolution": {
                        "test_files": [],
                        "risk_flags": [],
                    },
                    "dispatch": {
                        "reviewer": False,
                        "validator": False,
                        "auditors": [],
                    },
                }

            def fake_write_scope_freeze(vault_path: Path, scope_freeze: dict, *, run_id: str) -> Path:
                path = vault_path / "runs" / run_id / "scope-freeze.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(scope_freeze, ensure_ascii=False, indent=2), encoding="utf-8")
                return path

            def fake_run_selector(
                *,
                vault: Path,
                role: str,
                out_path: str,
                **__: object,
            ) -> tuple[dict, Path]:
                path = vault / out_path
                path.parent.mkdir(parents=True, exist_ok=True)
                report = {
                    "role": role,
                    "routing_decision": {
                        "selected_rung": 3,
                        "score_band": "low",
                        "sandbox_mode": "workspace-write",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                    "complexity_profile": {"risk_flags": []},
                }
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                return report, path

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    calls["scaffold"] += 1
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                calls["full"] += 1
                return {}

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.build_scope_freeze", side_effect=fake_build_scope_freeze),
                mock.patch("ops.scripts.auto_improve_runtime.write_scope_freeze", side_effect=fake_write_scope_freeze),
                mock.patch("ops.scripts.auto_improve_runtime.run_selector", side_effect=fake_run_selector),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-scope-blocked",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            run_id = session["run_ids"][0]
            telemetry = json.loads((vault / "runs" / run_id / "run-telemetry.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, {"scaffold": 1, "full": 0})
            self.assertEqual(result["stop_reason"], "failure_budget_exhausted")
            self.assertEqual(session["iterations"][0]["outcome"], "scope_blocked")
            self.assertEqual(session["iterations"][0]["status"], "blocked")
            self.assertEqual(session["quarantined_proposal_ids"], [proposal["proposal_id"]])
            self.assertEqual(telemetry["failure_taxonomy"], "scope_blocked")

    def test_run_auto_improve_session_quarantines_experiment_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                raise RunMechanismExperimentError("repo health command failed")

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-experiment-error",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            run_id = session["run_ids"][0]
            telemetry = json.loads((vault / "runs" / run_id / "run-telemetry.json").read_text(encoding="utf-8"))
            self.assertEqual(result["stop_reason"], "failure_budget_exhausted")
            self.assertEqual(session["iterations"][0]["outcome"], "repo_health_blocked")
            self.assertEqual(session["quarantined_proposal_ids"], [proposal["proposal_id"]])
            self.assertEqual(telemetry["failure_taxonomy"], "repo_health_blocked")

    def test_run_auto_improve_session_quarantines_repo_health_blocked_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                return {
                    "run_id": run_id,
                    "decision": "SKIPPED",
                    "finalized": False,
                    "finalize_result": {},
                    "repo_health": {"passed": False, "returncode": 1},
                }

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-repo-health",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=2,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(session["iterations"][0]["outcome"], "repo_health_blocked")
            self.assertEqual(session["iterations"][0]["status"], "blocked")
            self.assertEqual(session["iterations"][0]["decision"], "SKIPPED")
            self.assertEqual(session["quarantined_proposal_ids"], [proposal["proposal_id"]])
            self.assertEqual(session["rollups"]["telemetry"]["failure_taxonomy_counts"], {"repo_health_blocked": 1})

    def test_run_auto_improve_session_hold_uses_failure_budget_without_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                return {
                    "run_id": run_id,
                    "decision": "HOLD",
                    "finalized": False,
                    "finalize_result": {},
                    "repo_health": {"passed": True},
                }

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-hold",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=1,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(result["stop_reason"], "failure_budget_exhausted")
            self.assertEqual(session["iterations"][0]["outcome"], "hold")
            self.assertEqual(session["iterations"][0]["status"], "blocked")
            self.assertEqual(session["iterations"][0]["decision"], "HOLD")
            self.assertEqual(session["quarantined_proposal_ids"], [])
            self.assertEqual(session["rollups"]["iterations"]["outcome_counts"], {"hold": 1})

    def test_run_auto_improve_session_stops_repeated_blocker_before_third_try(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal_a = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            proposal_b = {
                **proposal_a,
                "proposal_id": f"{proposal_a['proposal_id']}-second",
                "source_candidate_id": "candidate-second",
            }

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal_a, proposal_b]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                return {
                    "run_id": run_id,
                    "decision": "HOLD",
                    "finalized": False,
                    "finalize_result": {},
                    "repo_health": {"passed": True},
                }

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-repeated-blocker",
                    max_proposals=3,
                    max_minutes=90,
                    max_consecutive_failures=3,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(result["stop_reason"], "repeated_blocker_backlog_required")
            self.assertEqual(len(session["iterations"]), 2)
            self.assertEqual(session["loop_state"]["blocking_reason_counts"], {"hold": 2})
            self.assertTrue(session["loop_state"]["repeated_blocker_stop"])
            self.assertEqual(session["loop_state"]["repeated_blocker_reason"], "hold")
            self.assertEqual(
                session["loop_state"]["remediation_backlog_path"],
                "ops/reports/remediation-backlog.json",
            )

    def test_run_auto_improve_session_stops_when_repeat_backlog_is_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            backlog_path = vault / "ops" / "reports" / "remediation-backlog.json"
            backlog_path.parent.mkdir(parents=True, exist_ok=True)
            backlog_path.write_text(
                json.dumps(
                    {
                        "status": "attention",
                        "items": [
                            {
                                "item_id": "negative_lesson_discard_decision_discard",
                                "blocker_id": "discard_decision_discard",
                                "source": "self_improvement_negative_lessons.lessons",
                                "item_type": "repeated_negative_lesson",
                                "status": "open",
                                "severity": "blocks_repeat",
                                "occurrence_count": 2,
                                "evidence_paths": [
                                    "ops/reports/self-improvement-negative-lessons.json"
                                ],
                                "repair_target": "Resolve repeated DISCARD decision shape.",
                                "next_action": "Close the repair target before retrying this blocker.",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with (
                mock.patch("ops.scripts.auto_improve_runtime._preflight_learning_gate") as preflight,
                mock.patch("ops.scripts.auto_improve_runtime._run_auto_improve_iteration") as iteration,
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-session-open-repeat-backlog",
                    max_proposals=3,
                    max_minutes=90,
                    max_consecutive_failures=3,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                )

            preflight.assert_not_called()
            iteration.assert_not_called()
            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            self.assertEqual(result["stop_reason"], "repeated_blocker_backlog_required")
            self.assertEqual(result["iterations"], 0)
            self.assertEqual(session["iterations"], [])
            self.assertTrue(session["loop_state"]["repeated_blocker_stop"])
            self.assertEqual(
                session["loop_state"]["repeated_blocker_reason"],
                "discard_decision_discard",
            )
            self.assertEqual(
                session["loop_state"]["blocking_reason_counts"],
                {"discard_decision_discard": 2},
            )

    def test_run_auto_improve_session_uses_injected_context_for_generated_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
            fixed_now = dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc)
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: fixed_now,
                session_id="auto-deterministic",
                executor_id="codex_exec",
            )

            def fake_refresh_reports(*_: object, **__: object) -> tuple[dict, dict]:
                return {}, {"proposals": [proposal]}

            def fake_run_mechanism_experiment(
                vault_path: Path,
                *,
                run_id: str,
                scaffold_only: bool,
                **_: object,
            ) -> dict:
                if scaffold_only:
                    _seed_scaffolded_run(vault_path, run_id)
                    return {"run_id": run_id, "scaffold_only": True}
                return {
                    "run_id": run_id,
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {"run_id": run_id},
                    "repo_health": {"passed": True},
                }

            with (
                mock.patch("ops.scripts.auto_improve_runtime._refresh_reports", side_effect=fake_refresh_reports),
                mock.patch("ops.scripts.auto_improve_runtime.run_mechanism_experiment", side_effect=fake_run_mechanism_experiment),
            ):
                result = run_auto_improve_session(
                    vault,
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    session_id="auto-deterministic",
                    max_proposals=1,
                    max_minutes=90,
                    max_consecutive_failures=2,
                    executor_name="codex_exec",
                    allow_learning_uncertain=True,
                    context=context,
                )

            session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
            run_id = session["run_ids"][0]
            telemetry = json.loads((vault / "runs" / run_id / "run-telemetry.json").read_text(encoding="utf-8"))
            scope_freeze = json.loads((vault / "runs" / run_id / "scope-freeze.json").read_text(encoding="utf-8"))

            self.assertEqual(session["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(telemetry["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(scope_freeze["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(
                scope_freeze["apply_guardrails"]["allowed_apply_roots"],
                ["ops/", "tests/", "system/system-log.md"],
            )
