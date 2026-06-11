from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism import auto_improve_loop_decision_runtime as loop_decisions
from tests.auto_improve_test_utils import _incrementing_runtime_context


class AutoImproveLoopDecisionRuntimeTests(unittest.TestCase):
    def test_reconstructed_loop_state_counts_specific_failure_taxonomy(self) -> None:
        session = {
            "iterations": [
                {
                    "run_id": "run-discard-specific",
                    "outcome": "discarded",
                    "decision": "DISCARD",
                    "failure_taxonomy": "changed_files_manifest_scope",
                }
            ]
        }

        loop_state = loop_decisions._reconstructed_loop_state(
            session,
            context=_incrementing_runtime_context(),
        )

        self.assertEqual(loop_state["last_outcome"], "discarded")
        self.assertEqual(loop_state["last_blocking_reason"], "changed_files_manifest_scope")
        self.assertEqual(
            loop_state["blocking_reason_counts"],
            {"changed_files_manifest_scope": 1},
        )

    def test_normalize_loop_state_replaces_stale_generic_discard_reason(self) -> None:
        session = {
            "iterations": [
                {
                    "run_id": "run-discard-specific",
                    "outcome": "discarded",
                    "decision": "DISCARD",
                    "failure_taxonomy": "changed_files_manifest_scope",
                }
            ],
            "loop_state": {
                "consecutive_failures": 1,
                "last_outcome": "discarded",
                "last_decision": "DISCARD",
                "last_run_id": "run-discard-specific",
                "last_blocking_reason": "discarded",
                "blocking_reason_counts": {"discarded": 1},
                "repeated_blocker_stop": True,
                "repeated_blocker_reason": "discarded",
                "remediation_backlog_path": "ops/reports/remediation-backlog.json",
                "updated_at": "2026-04-15T00:00:00Z",
            },
        }

        loop_state = loop_decisions._normalize_loop_state(
            session,
            context=_incrementing_runtime_context(),
        )

        self.assertEqual(loop_state["last_outcome"], "discarded")
        self.assertEqual(loop_state["last_blocking_reason"], "changed_files_manifest_scope")
        self.assertEqual(
            loop_state["blocking_reason_counts"],
            {"changed_files_manifest_scope": 1},
        )
        self.assertTrue(loop_state["repeated_blocker_stop"])
        self.assertEqual(loop_state["repeated_blocker_reason"], "changed_files_manifest_scope")

    def test_stop_reason_before_iteration_detects_time_budget_exhaustion(self) -> None:
        context = _incrementing_runtime_context()
        session = {
            "iterations": [],
            "budget": {
                "max_proposals": 10,
                "max_minutes": 1,
                "max_consecutive_failures": 3,
            },
            "loop_state": loop_decisions._empty_loop_state(context),
        }
        state = loop_decisions.AutoImproveLoopState(
            attempted=set(),
            quarantined=set(),
            consecutive_failures=0,
            stop_reason="queue_exhausted",
            start_monotonic=0.0,
            pre_promotion_failure_outcomes=set(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            reason = loop_decisions._stop_reason_before_iteration(
                Path(temp_dir),
                session,
                state,
                context=context,
                check_open_repeat_backlog=False,
                monotonic=lambda: 61.0,
            )

        self.assertEqual(reason, "time_budget_exhausted")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
