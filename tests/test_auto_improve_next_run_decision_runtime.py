from __future__ import annotations

import datetime as dt
import unittest

from ops.scripts.auto_improve_next_run_decision_runtime import (
    CARRY_FORWARD_DECISION,
    IGNORE_RETRYABLE_DECISION,
    OPEN_DECISION_STATUS,
    REPAIR_FAILURE_ACTION,
    WAIT_FOR_CAPACITY_ACTION,
    build_next_run_decision,
)
from ops.scripts.auto_improve_outcome_runtime import ExecutionOutcome
from ops.scripts.runtime_context import RuntimeContext


def _context() -> RuntimeContext:
    instant = dt.datetime(2026, 5, 20, 12, 0, tzinfo=dt.timezone.utc)
    return RuntimeContext(clock=lambda: instant, display_timezone=dt.timezone.utc)


def _proposal() -> dict:
    return {
        "proposal_id": "proposal-runtime-repair",
        "source_candidate_id": "candidate-runtime-repair",
        "family": "contract_regression_signals",
        "tier": "supporting",
        "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
        "supporting_targets": ["ops/script-output-surfaces.json"],
        "must_change_tests": ["tests/test_example_runtime.py"],
    }


class AutoImproveNextRunDecisionRuntimeTests(unittest.TestCase):
    def test_actionable_failure_becomes_open_carry_forward_decision(self) -> None:
        decision = build_next_run_decision(
            session_id="auto-improve-session",
            iteration=2,
            run_id="auto-improve-session-run-02-example-runtime",
            proposal=_proposal(),
            outcome=ExecutionOutcome(
                outcome="review_blocked",
                next_consecutive_failures=1,
                quarantine_proposal=True,
            ),
            roles=["worker", "reviewer"],
            scope_freeze_rel="runs/run-02/scope-freeze.json",
            routing_report_rels=[
                "runs/run-02/subagent-routing.worker.json",
                "runs/run-02/subagent-routing.reviewer.json",
            ],
            telemetry_rel="runs/run-02/run-telemetry.json",
            context=_context(),
        )

        assert decision is not None
        self.assertEqual(decision["decision"], CARRY_FORWARD_DECISION)
        self.assertEqual(decision["next_run_action"], REPAIR_FAILURE_ACTION)
        self.assertEqual(decision["status"], OPEN_DECISION_STATUS)
        self.assertEqual(decision["failure_taxonomy"], "review_blocked")
        self.assertEqual(decision["blocking_role"], "reviewer")
        self.assertTrue(decision["quarantined_source_proposal"])
        self.assertEqual(
            decision["target_proposal_id"],
            "next_run_failure_repair__example-runtime__review-blocked",
        )
        self.assertIn(
            "runs/auto-improve-session-run-02-example-runtime/reviewer-executor-report.json",
            decision["evidence_paths"],
        )

    def test_retryable_executor_capacity_is_recorded_but_not_carried_forward(self) -> None:
        decision = build_next_run_decision(
            session_id="auto-improve-session",
            iteration=1,
            run_id="auto-improve-session-run-01-example-runtime",
            proposal=_proposal(),
            outcome=ExecutionOutcome(
                outcome="executor_usage_limited",
                next_consecutive_failures=0,
            ),
            roles=["worker"],
            scope_freeze_rel="runs/run-01/scope-freeze.json",
            routing_report_rels=["runs/run-01/subagent-routing.worker.json"],
            telemetry_rel="runs/run-01/run-telemetry.json",
            context=_context(),
        )

        assert decision is not None
        self.assertEqual(decision["decision"], IGNORE_RETRYABLE_DECISION)
        self.assertEqual(decision["next_run_action"], WAIT_FOR_CAPACITY_ACTION)
        self.assertEqual(decision["status"], "closed")
        self.assertEqual(decision["target_proposal_id"], "")


if __name__ == "__main__":
    unittest.main()
