from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.auto_improve_outcome_runtime import (
    ExecutionOutcome,
    apply_execution_outcome,
    detect_executor_failure,
    evaluate_experiment_error,
    evaluate_experiment_result,
    evaluate_mutation_error,
    evaluate_scope_blocked,
    role_report_path,
)
from ops.scripts.promotion_decision_registry_runtime import reduce_decision_proposals


def _write_executor_report(
    vault: Path,
    run_id: str,
    role: str,
    status: str,
    *,
    returncode: int | None = None,
) -> None:
    path = vault / role_report_path(run_id, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "role": role,
                "status": status,
                "artifacts": {
                    "stderr": f"runs/{run_id}/{role}.stderr.txt",
                },
                "result": {
                    "returncode": returncode if returncode is not None else 0 if status == "pass" else 1,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class AutoImproveOutcomeRuntimeTests(unittest.TestCase):
    def test_execution_outcome_iteration_record_marks_terminal_success_complete(self) -> None:
        outcome = ExecutionOutcome(
            outcome="promoted",
            next_consecutive_failures=0,
            result={"decision": "PROMOTE"},
        )

        self.assertTrue(outcome.is_terminal_success)
        self.assertEqual(outcome.iteration_status, "complete")
        self.assertEqual(outcome.decision, "PROMOTE")
        self.assertEqual(
            outcome.iteration_record(index=2, proposal_id="proposal-a", run_id="run-a"),
            {
                "index": 2,
                "proposal_id": "proposal-a",
                "run_id": "run-a",
                "status": "complete",
                "outcome": "promoted",
                "decision": "PROMOTE",
            },
        )

    def test_execution_outcome_iteration_record_marks_blocking_outcome_blocked(self) -> None:
        outcome = ExecutionOutcome(outcome="validation_blocked", next_consecutive_failures=3)

        self.assertFalse(outcome.is_terminal_success)
        self.assertEqual(outcome.iteration_status, "blocked")
        self.assertEqual(outcome.decision, "")
        self.assertEqual(
            outcome.iteration_record(index=1, proposal_id="proposal-a", run_id="run-a")["status"],
            "blocked",
        )

    def test_evaluate_scope_blocked_quarantines_and_increments_failures(self) -> None:
        outcome = evaluate_scope_blocked(2)

        self.assertEqual(outcome.outcome, "scope_blocked")
        self.assertEqual(outcome.next_consecutive_failures, 3)
        self.assertTrue(outcome.quarantine_proposal)
        self.assertIsNone(outcome.result)

    def test_evaluate_experiment_result_promote_resets_discard_increments_failure_count(self) -> None:
        promoted = evaluate_experiment_result(
            {"decision": "PROMOTE", "repo_health": {"passed": True}},
            2,
        )
        discarded = evaluate_experiment_result(
            {"decision": "DISCARD", "repo_health": {"passed": True}},
            2,
        )

        self.assertEqual(promoted.outcome, "promoted")
        self.assertEqual(promoted.next_consecutive_failures, 0)
        self.assertFalse(promoted.quarantine_proposal)
        self.assertEqual(discarded.outcome, "discarded")
        self.assertEqual(discarded.next_consecutive_failures, 3)
        self.assertFalse(discarded.quarantine_proposal)
        self.assertFalse(discarded.is_terminal_success)
        self.assertEqual(discarded.iteration_status, "blocked")

    def test_evaluate_experiment_result_hold_increments_without_quarantine(self) -> None:
        outcome = evaluate_experiment_result(
            {"decision": "HOLD", "repo_health": {"passed": True}},
            1,
        )

        self.assertEqual(outcome.outcome, "hold")
        self.assertEqual(outcome.next_consecutive_failures, 2)
        self.assertFalse(outcome.quarantine_proposal)

    def test_evaluate_experiment_result_uses_canonical_decision_record(self) -> None:
        contract = reduce_decision_proposals(
            [{"rule_id": "scope_violation", "decision": "DISCARD"}],
            subject_id="run-canonical",
            subject_kind="system_mechanism",
            policy_version=1,
            source_pass="system_mechanism",
            signoff={"required": False, "status": "not_required"},
        )

        outcome = evaluate_experiment_result(
            {
                "decision": "DISCARD",
                "decision_record": contract["decision_record"],
                "repo_health": {"passed": True},
            },
            3,
        )

        self.assertEqual(outcome.outcome, "discarded")
        self.assertEqual(outcome.next_consecutive_failures, 4)

    def test_evaluate_experiment_result_hold_precedes_failed_repo_health(self) -> None:
        outcome = evaluate_experiment_result(
            {"decision": "HOLD", "repo_health": {"passed": False}},
            1,
        )

        self.assertEqual(outcome.outcome, "hold")
        self.assertEqual(outcome.next_consecutive_failures, 2)
        self.assertFalse(outcome.quarantine_proposal)

    def test_evaluate_experiment_result_failed_repo_health_quarantines(self) -> None:
        outcome = evaluate_experiment_result(
            {"decision": "SKIPPED", "repo_health": {"passed": False}},
            1,
        )

        self.assertEqual(outcome.outcome, "repo_health_blocked")
        self.assertEqual(outcome.next_consecutive_failures, 2)
        self.assertTrue(outcome.quarantine_proposal)

    def test_evaluate_experiment_result_unknown_nonblocking_decision_fails_closed_as_hold(self) -> None:
        outcome = evaluate_experiment_result(
            {"decision": "UNEXPECTED", "repo_health": {"passed": True}},
            1,
        )

        self.assertEqual(outcome.outcome, "hold")
        self.assertEqual(outcome.next_consecutive_failures, 2)
        self.assertFalse(outcome.quarantine_proposal)

    def test_detect_executor_failure_classifies_first_blocking_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "run-a"
            _write_executor_report(vault, run_id, "worker", "pass")
            _write_executor_report(vault, run_id, "reviewer", "fail")
            _write_executor_report(vault, run_id, "validator", "fail")

            self.assertEqual(
                detect_executor_failure(run_id, ["worker", "reviewer", "validator"], vault),
                "review_blocked",
            )

    def test_detect_executor_failure_does_not_treat_review_output_snippets_as_usage_limit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "run-a"
            _write_executor_report(vault, run_id, "worker", "pass")
            _write_executor_report(vault, run_id, "reviewer", "fail", returncode=0)
            stderr_path = vault / "runs" / run_id / "reviewer.stderr.txt"
            stderr_path.write_text(
                "\n".join(
                    [
                        "exec",
                        "rg -n 'executor_usage_limited|usage limit' tests ops",
                        " succeeded in 23ms:",
                        (
                            "tests/test_auto_improve_runtime.py:542:"
                            "\"ERROR: You've hit your usage limit. Try again at May 16th\""
                        ),
                        "ops/scripts/mechanism/auto_improve_outcome_runtime.py:17:"
                        "RETRYABLE_EXECUTOR_FAILURE_OUTCOMES = {'executor_usage_limited'}",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                detect_executor_failure(run_id, ["worker", "reviewer"], vault),
                "review_blocked",
            )

    def test_detect_executor_failure_classifies_validator_and_auditor_as_validation_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "run-a"
            _write_executor_report(vault, run_id, "worker", "pass")
            _write_executor_report(vault, run_id, "validator", "fail")
            _write_executor_report(vault, run_id, "provenance-auditor", "fail")

            self.assertEqual(
                detect_executor_failure(run_id, ["worker", "validator"], vault),
                "validation_blocked",
            )
            self.assertEqual(
                detect_executor_failure(run_id, ["worker", "provenance-auditor"], vault),
                "validation_blocked",
            )

    def test_detect_executor_failure_defaults_to_mutation_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "run-a"
            _write_executor_report(vault, run_id, "worker", "fail")

            self.assertEqual(detect_executor_failure(run_id, ["worker"], vault), "mutation_failed")
            self.assertEqual(detect_executor_failure(run_id, ["missing-role"], vault), "mutation_failed")

    def test_evaluate_mutation_error_uses_quarantine_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            run_id = "run-a"
            _write_executor_report(vault, run_id, "worker", "pass")
            _write_executor_report(vault, run_id, "validator", "fail")

            quarantined = evaluate_mutation_error(
                run_id=run_id,
                roles=["worker", "validator"],
                artifact_root=vault,
                pre_promotion_failure_outcomes={"validation_blocked"},
                consecutive_failures=1,
            )
            not_quarantined = evaluate_mutation_error(
                run_id=run_id,
                roles=["worker", "validator"],
                artifact_root=vault,
                pre_promotion_failure_outcomes={"mutation_failed"},
                consecutive_failures=1,
            )

            self.assertEqual(quarantined.outcome, "validation_blocked")
            self.assertEqual(quarantined.next_consecutive_failures, 2)
            self.assertTrue(quarantined.quarantine_proposal)
            self.assertEqual(not_quarantined.outcome, "validation_blocked")
            self.assertFalse(not_quarantined.quarantine_proposal)

    def test_evaluate_experiment_error_quarantines_repo_health_blocked(self) -> None:
        outcome = evaluate_experiment_error(3)

        self.assertEqual(outcome.outcome, "repo_health_blocked")
        self.assertEqual(outcome.next_consecutive_failures, 4)
        self.assertTrue(outcome.quarantine_proposal)

    def test_apply_execution_outcome_updates_quarantine_state_and_returns_failure_count(self) -> None:
        session = {"quarantined_proposal_ids": ["proposal-b"]}
        quarantined = {"proposal-b"}
        outcome = ExecutionOutcome(
            outcome="repo_health_blocked",
            next_consecutive_failures=2,
            quarantine_proposal=True,
        )

        next_failures = apply_execution_outcome(
            session,
            proposal_id="proposal-a",
            quarantined=quarantined,
            outcome=outcome,
        )

        self.assertEqual(next_failures, 2)
        self.assertEqual(quarantined, {"proposal-a", "proposal-b"})
        self.assertEqual(session["quarantined_proposal_ids"], ["proposal-a", "proposal-b"])

    def test_apply_execution_outcome_leaves_quarantine_state_unchanged_for_non_quarantine(self) -> None:
        session = {"quarantined_proposal_ids": ["proposal-b"]}
        quarantined = {"proposal-b"}
        outcome = ExecutionOutcome(outcome="hold", next_consecutive_failures=2)

        next_failures = apply_execution_outcome(
            session,
            proposal_id="proposal-a",
            quarantined=quarantined,
            outcome=outcome,
        )

        self.assertEqual(next_failures, 2)
        self.assertEqual(quarantined, {"proposal-b"})
        self.assertEqual(session["quarantined_proposal_ids"], ["proposal-b"])


if __name__ == "__main__":
    unittest.main()
