from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.artifact_freshness_runtime import ENVELOPE_REQUIRED_FIELDS
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.structural_complexity_budget_runtime import (
    build_report as build_structural_complexity_budget_report,
)
from ops.scripts.wiki_eval import evaluate
from ops.scripts.wiki_eval_coverage_runtime import build_report as build_eval_coverage_report
from ops.scripts.wiki_lint import lint
from ops.scripts.mechanism_review_runtime import build_report as build_mechanism_review_report
from ops.scripts.mutation_proposal_runtime import build_report as build_mutation_proposal_report
from ops.scripts.policy_runtime import load_policy
from ops.scripts.wiki_snapshot_runtime import build_wiki_runtime_snapshot
from ops.scripts.wiki_stage2_eval import evaluate as evaluate_stage2

pytestmark = [pytest.mark.integration_heavy, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "eval-report.schema.json"
EVAL_COVERAGE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-eval-coverage-report.schema.json"
LINT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "lint-report.schema.json"
STAGE2_EVAL_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-stage2-eval-report.schema.json"
MECHANISM_REVIEW_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "mechanism-review-candidates.schema.json"
MUTATION_PROPOSAL_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "mutation-proposals.schema.json"
STRUCTURAL_COMPLEXITY_BUDGET_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "structural-complexity-budget-report.schema.json"
)


class ReportGenerationSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._temp_dir = tempfile.TemporaryDirectory(prefix="report-generation-smoke-")
        cls.policy, cls.policy_path = load_policy(REPO_ROOT)
        cls.runtime_snapshot = build_wiki_runtime_snapshot(
            REPO_ROOT,
            registry_contract=cls.policy["registry_contract"],
        )
        cls.schemas = {
            "eval": load_schema(EVAL_SCHEMA_PATH),
            "eval_coverage": load_schema(EVAL_COVERAGE_SCHEMA_PATH),
            "lint": load_schema(LINT_SCHEMA_PATH),
            "stage2": load_schema(STAGE2_EVAL_SCHEMA_PATH),
            "mechanism_review": load_schema(MECHANISM_REVIEW_SCHEMA_PATH),
            "mutation_proposal": load_schema(MUTATION_PROPOSAL_SCHEMA_PATH),
            "structural_complexity_budget": load_schema(STRUCTURAL_COMPLEXITY_BUDGET_SCHEMA_PATH),
        }
        cls.live_reports = {
            "eval": evaluate(REPO_ROOT, snapshot=cls.runtime_snapshot),
            "eval_coverage": build_eval_coverage_report(
                REPO_ROOT,
                cls.policy,
                cls.policy_path,
                snapshot=cls.runtime_snapshot,
            ),
            "lint": lint(REPO_ROOT, snapshot=cls.runtime_snapshot),
            "stage2": evaluate_stage2(REPO_ROOT, snapshot=cls.runtime_snapshot),
            "mechanism_review": build_mechanism_review_report(REPO_ROOT, cls.policy, cls.policy_path),
            "structural_complexity_budget": build_structural_complexity_budget_report(REPO_ROOT),
        }
        mechanism_review_path = Path(cls._temp_dir.name) / "mechanism-review-candidates.json"
        mechanism_review_path.write_text(
            json.dumps(cls.live_reports["mechanism_review"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cls.live_reports["mutation_proposal"] = build_mutation_proposal_report(
            REPO_ROOT,
            cls.policy,
            cls.policy_path,
            mechanism_review_report_path=mechanism_review_path.as_posix(),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp_dir.cleanup()
        super().tearDownClass()

    def test_live_eval_report_validates_against_current_schema(self) -> None:
        self.assertEqual(validate_with_schema(self.live_reports["eval"], self.schemas["eval"]), [])

    def test_live_lint_report_validates_against_current_schema(self) -> None:
        self.assertEqual(validate_with_schema(self.live_reports["lint"], self.schemas["lint"]), [])

    def test_live_eval_coverage_report_validates_against_current_schema(self) -> None:
        self.assertEqual(
            validate_with_schema(self.live_reports["eval_coverage"], self.schemas["eval_coverage"]),
            [],
        )

    def test_live_stage2_eval_report_validates_against_current_schema(self) -> None:
        self.assertEqual(validate_with_schema(self.live_reports["stage2"], self.schemas["stage2"]), [])

    def test_live_mechanism_review_report_validates_against_current_schema(self) -> None:
        self.assertEqual(
            validate_with_schema(self.live_reports["mechanism_review"], self.schemas["mechanism_review"]),
            [],
        )

    def test_canonical_reports_add_artifact_envelope_incrementally(self) -> None:
        expected_schemas = {
            "eval": "ops/schemas/eval-report.schema.json",
            "eval_coverage": "ops/schemas/wiki-eval-coverage-report.schema.json",
            "lint": "ops/schemas/lint-report.schema.json",
            "stage2": "ops/schemas/wiki-stage2-eval-report.schema.json",
            "mechanism_review": "ops/schemas/mechanism-review-candidates.schema.json",
            "mutation_proposal": "ops/schemas/mutation-proposals.schema.json",
            "structural_complexity_budget": "ops/schemas/structural-complexity-budget-report.schema.json",
        }

        for report_name, expected_schema in expected_schemas.items():
            with self.subTest(report_name=report_name):
                report = self.live_reports[report_name]
                self.assertTrue(all(field in report for field in ENVELOPE_REQUIRED_FIELDS))
                self.assertEqual(report["$schema"], expected_schema)
                self.assertEqual(report["artifact_status"], "current")
                self.assertEqual(report["retention_policy"], "canonical_report")
                self.assertEqual(report["currentness"]["status"], "current")

    def test_live_mutation_proposal_report_validates_against_current_schema(self) -> None:
        self.assertEqual(
            validate_with_schema(self.live_reports["mutation_proposal"], self.schemas["mutation_proposal"]),
            [],
        )

    def test_live_structural_complexity_budget_report_validates_against_current_schema(self) -> None:
        report = self.live_reports["structural_complexity_budget"]

        self.assertEqual(validate_with_schema(report, self.schemas["structural_complexity_budget"]), [])
        self.assertIn("high_complexity_helpers", report["profiles"])
        self.assertIn("function_budget_top_n", report["diagnostics"])


if __name__ == "__main__":
    unittest.main()
