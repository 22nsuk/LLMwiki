from __future__ import annotations

import datetime as dt
import unittest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism.mechanism_run_scaffold_templates_runtime import (
    initial_planning_validation,
    initial_run_ledger,
    placeholder_promotion_report,
    proposal_snapshot,
    starter_open_questions,
    starter_plan_text,
    starter_seed_text,
)
from tests.run_mechanism_experiment_test_utils import mutation_proposal_report


class MechanismRunScaffoldTemplatesRuntimeTests(unittest.TestCase):
    def test_starter_text_templates_include_proposal_and_scope_signals(self) -> None:
        proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

        seed_text = starter_seed_text(
            "run-template",
            ["ops/scripts/example.py"],
            ["tests/test_example.py"],
            ["tests/test_example.py"],
            proposal=proposal,
            seed_state="SEED_DRAFT",
        )
        plan_text = starter_plan_text(
            "run-template",
            ["ops/scripts/example.py"],
            ["tests/test_example.py"],
            proposal=proposal,
        )
        questions = starter_open_questions(["tests/test_example.py"], proposal=proposal)

        self.assertIn('current: SEED_DRAFT', seed_text)
        self.assertIn("proposal-snapshot.json", seed_text)
        self.assertIn(proposal["proposal_id"], seed_text)
        self.assertIn("Expected binary signal", plan_text)
        self.assertIn(proposal["expected_binary_signal"], plan_text)
        self.assertIn(proposal["proposal_id"], questions)

    def test_initial_json_templates_use_context_and_schema_paths(self) -> None:
        proposal = mutation_proposal_report("ops/scripts/example.py")["proposals"][0]
        fixed_now = dt.datetime(2026, 4, 16, 1, 2, 3, tzinfo=dt.UTC)
        context = RuntimeContext(
            display_timezone=dt.UTC,
            clock=lambda: fixed_now,
        )

        snapshot = proposal_snapshot(
            "run-template",
            proposal=proposal,
            source_report="ops/reports/mutation-proposals.json",
            context=context,
        )
        planning = initial_planning_validation(
            "run-template",
            ["ops/scripts/example.py"],
            ["tests/test_example.py"],
            proposal=proposal,
        )
        ledger = initial_run_ledger(
            "run-template",
            include_proposal_snapshot=True,
            context=context,
        )
        promotion = placeholder_promotion_report(
            "run-template",
            ["ops/scripts/example.py"],
            ["tests/test_example.py"],
            "scaffold template regression",
        )

        self.assertEqual(snapshot["captured_at"], "2026-04-16T01:02:03Z")
        self.assertEqual(snapshot["proposal"]["proposal_id"], proposal["proposal_id"])
        self.assertEqual(snapshot["proposal"]["blast_radius_score"], proposal["blast_radius_score"])
        self.assertEqual(snapshot["proposal"]["must_change_tests"], proposal["must_change_tests"])
        self.assertTrue(snapshot["proposal"]["must_not_expand_apply_roots"])
        self.assertTrue(snapshot["proposal"]["must_not_increase_untyped_surface"])
        self.assertEqual(planning["$schema"], "ops/schemas/planning-validation.schema.json")
        self.assertEqual(planning["status"], "WARN")
        self.assertIn("proposal_snapshot_captured", [item["id"] for item in planning["checks"]])
        self.assertEqual(ledger["events"][0]["ts"], "2026-04-16T01:02:03Z")
        self.assertIn("proposal-snapshot.json", ledger["events"][0]["artifacts"])
        self.assertEqual(promotion["$schema"], "ops/schemas/promotion-report.schema.json")
        self.assertEqual(
            promotion["inputs"]["candidate_mechanism_report"],
            "runs/run-template/candidate-mechanism-assessment.json",
        )


if __name__ == "__main__":
    unittest.main()
