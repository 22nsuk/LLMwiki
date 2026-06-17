from __future__ import annotations

import unittest
from types import SimpleNamespace

from ops.scripts.mechanism.failure_taxonomy_runtime import (
    GENERATED_EVIDENCE_SETTLE_REQUIRED,
    blocking_role_for_failure_taxonomy,
    failure_taxonomy_from_iteration,
    failure_taxonomy_from_outcome,
    is_actionable_repair_failure_taxonomy,
    is_budget_consuming_failure_taxonomy,
    is_generated_evidence_settle_required,
    is_retryable_failure_taxonomy,
    is_settle_failure_taxonomy,
)


class FailureTaxonomyRuntimeTests(unittest.TestCase):
    def test_iteration_discard_prefers_actual_blocking_check_over_reason_code(self) -> None:
        failure_taxonomy = failure_taxonomy_from_iteration(
            "discarded",
            decision_record={"reason_code": "equal_score_secondary_eligibility"},
            discard_evidence={
                "blocking_check_ids": ["structural_complexity_non_regression"],
            },
        )

        self.assertEqual(failure_taxonomy, "structural_complexity_non_regression")

    def test_outcome_override_wins_before_generic_promotion_reason(self) -> None:
        failure_taxonomy = failure_taxonomy_from_outcome(
            SimpleNamespace(
                outcome="discarded",
                result={
                    "decision_record": {
                        "decision": "DISCARD",
                        "reason_code": "equal_score_secondary_eligibility",
                    }
                },
            ),
            override="changed_files_manifest_scope",
        )

        self.assertEqual(failure_taxonomy, "changed_files_manifest_scope")

    def test_taxonomy_sets_drive_repair_actionability_and_blocking_role(self) -> None:
        self.assertTrue(is_retryable_failure_taxonomy("executor_usage_limited"))
        self.assertFalse(is_actionable_repair_failure_taxonomy("executor_usage_limited"))
        self.assertTrue(is_generated_evidence_settle_required(GENERATED_EVIDENCE_SETTLE_REQUIRED))
        self.assertTrue(is_settle_failure_taxonomy(GENERATED_EVIDENCE_SETTLE_REQUIRED))
        self.assertFalse(is_budget_consuming_failure_taxonomy(GENERATED_EVIDENCE_SETTLE_REQUIRED))
        self.assertFalse(is_actionable_repair_failure_taxonomy(GENERATED_EVIDENCE_SETTLE_REQUIRED))
        self.assertTrue(is_actionable_repair_failure_taxonomy("tests_non_regression"))
        self.assertEqual(
            blocking_role_for_failure_taxonomy(GENERATED_EVIDENCE_SETTLE_REQUIRED, ["worker"]),
            "repo_health",
        )
        self.assertEqual(
            blocking_role_for_failure_taxonomy(
                "validation_blocked",
                ["worker", "release-authority-auditor"],
            ),
            "release-authority-auditor",
        )
        self.assertEqual(
            blocking_role_for_failure_taxonomy("changed_files_manifest_scope", ["worker"]),
            "promotion_gate",
        )


if __name__ == "__main__":
    unittest.main()
