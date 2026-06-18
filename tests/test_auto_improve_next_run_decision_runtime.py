from __future__ import annotations

import datetime as dt
import unittest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism.auto_improve_next_run_decision_runtime import (
    CARRY_FORWARD_DECISION,
    CHOOSE_ALTERNATIVE_DECISION,
    IGNORE_RETRYABLE_DECISION,
    OPEN_DECISION_STATUS,
    REPAIR_FAILURE_ACTION,
    SELECT_ALTERNATIVE_ACTION,
    WAIT_FOR_CAPACITY_ACTION,
    NextRunDecisionRequest,
    build_next_run_decision,
)
from ops.scripts.mechanism.auto_improve_outcome_runtime import ExecutionOutcome
from ops.scripts.mechanism.failure_taxonomy_runtime import (
    GENERATED_EVIDENCE_SETTLE_REQUIRED,
)


def _context() -> RuntimeContext:
    instant = dt.datetime(2026, 5, 20, 12, 0, tzinfo=dt.UTC)
    return RuntimeContext(clock=lambda: instant, display_timezone=dt.UTC)


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

    def test_generated_evidence_settle_is_recorded_without_repair_target(self) -> None:
        decision = build_next_run_decision(
            session_id="auto-improve-session",
            iteration=1,
            run_id="auto-improve-session-run-01-example-runtime",
            proposal=_proposal(),
            outcome=ExecutionOutcome(
                outcome=GENERATED_EVIDENCE_SETTLE_REQUIRED,
                next_consecutive_failures=0,
            ),
            roles=["worker"],
            scope_freeze_rel="runs/run-01/scope-freeze.json",
            routing_report_rels=["runs/run-01/subagent-routing.worker.json"],
            telemetry_rel="runs/run-01/run-telemetry.json",
            context=_context(),
        )

        assert decision is not None
        self.assertEqual(decision["failure_taxonomy"], GENERATED_EVIDENCE_SETTLE_REQUIRED)
        self.assertEqual(decision["decision"], CHOOSE_ALTERNATIVE_DECISION)
        self.assertEqual(decision["next_run_action"], SELECT_ALTERNATIVE_ACTION)
        self.assertEqual(decision["status"], "closed")
        self.assertEqual(decision["target_proposal_id"], "")
        self.assertEqual(decision["blocking_role"], "repo_health")
        self.assertIn("settle outside the repair queue", decision["reason"])

    def test_promotion_failure_taxonomy_override_is_carried_forward(self) -> None:
        decision = build_next_run_decision(
            session_id="auto-improve-session",
            iteration=3,
            run_id="auto-improve-session-run-03-example-runtime",
            proposal=_proposal(),
            outcome=ExecutionOutcome(
                outcome="discarded",
                next_consecutive_failures=1,
                result={"decision": "DISCARD"},
            ),
            roles=["worker", "reviewer"],
            scope_freeze_rel="runs/run-03/scope-freeze.json",
            routing_report_rels=[
                "runs/run-03/subagent-routing.worker.json",
                "runs/run-03/subagent-routing.reviewer.json",
            ],
            telemetry_rel="runs/run-03/run-telemetry.json",
            context=_context(),
            failure_taxonomy_override="changed_files_manifest_scope",
        )

        assert decision is not None
        self.assertEqual(decision["decision"], CARRY_FORWARD_DECISION)
        self.assertEqual(decision["failure_taxonomy"], "changed_files_manifest_scope")
        self.assertEqual(decision["blocking_role"], "promotion_gate")
        self.assertEqual(
            decision["target_proposal_id"],
            "next_run_failure_repair__example-runtime__changed-files-manifest-scope",
        )

    def test_request_object_cannot_be_combined_with_legacy_kwargs(self) -> None:
        request = NextRunDecisionRequest(
            session_id="auto-improve-session",
            iteration=1,
            run_id="auto-improve-session-run-01-example-runtime",
            proposal=_proposal(),
            outcome=ExecutionOutcome(outcome="review_blocked", next_consecutive_failures=1),
            roles=["worker"],
            scope_freeze_rel="runs/run-01/scope-freeze.json",
            routing_report_rels=["runs/run-01/subagent-routing.worker.json"],
            telemetry_rel="runs/run-01/run-telemetry.json",
            context=_context(),
        )

        with self.assertRaisesRegex(
            TypeError,
            "request cannot be combined with legacy keyword arguments: session_id",
        ):
            build_next_run_decision(request=request, session_id="legacy-session")


if __name__ == "__main__":
    unittest.main()
