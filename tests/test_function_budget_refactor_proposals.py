from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.eval.function_budget_refactor_proposals import (
    build_report,
    write_report,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "function-budget-refactor-proposals.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 10, 5, 0, tzinfo=dt.UTC),
    )


class FunctionBudgetRefactorProposalsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/function-budget-refactor-proposals.schema.json")
        (self.vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
        (self.vault / "ops" / "scripts" / "helper_runtime.py").write_text("def helper():\n    pass\n", encoding="utf-8")
        (self.vault / "ops" / "scripts" / "cli_tool.py").write_text("def main():\n    pass\n", encoding="utf-8")
        (self.vault / "ops" / "scripts" / "external_report_reference_manifest.py").write_text(
            "def build_report():\n    pass\n",
            encoding="utf-8",
        )
        (self.vault / "tests").mkdir(parents=True, exist_ok=True)
        (self.vault / "tests" / "test_helper.py").write_text("def test_helper():\n    pass\n", encoding="utf-8")
        (self.vault / "tests" / "test_external_report_reference_manifest.py").write_text(
            "def test_manifest():\n    pass\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_classification(
        self,
        manifest_page: str = "ops/scripts/external_report_reference_manifest.py",
    ) -> str:
        path = self.vault / "tmp" / "classification.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "summary": {"function_budget_count": 3},
                    "classifications": [
                        {
                            "primary_bucket": "function_budget",
                            "page": "ops/scripts/helper_runtime.py",
                            "symbol": "build_helper",
                            "line": 12,
                            "profile": "ops_runtime",
                            "triggered_budgets": ["function_lines"],
                            "metrics": {
                                "function_lines": 132,
                                "parameter_count": 3,
                                "branch_node_count": 2,
                            },
                            "thresholds": {
                                "function_lines": 120,
                                "parameter_count": 10,
                                "branch_node_count": 18,
                            },
                        },
                        {
                            "primary_bucket": "function_budget",
                            "page": "ops/scripts/cli_tool.py",
                            "symbol": "main",
                            "line": 20,
                            "profile": "ops_runtime",
                            "triggered_budgets": ["function_lines"],
                            "metrics": {
                                "function_lines": 160,
                                "parameter_count": 1,
                                "branch_node_count": 1,
                            },
                            "thresholds": {
                                "function_lines": 120,
                                "parameter_count": 10,
                                "branch_node_count": 18,
                            },
                        },
                        {
                            "primary_bucket": "function_budget",
                            "page": manifest_page,
                            "symbol": "build_report",
                            "line": 42,
                            "profile": "ops_runtime",
                            "triggered_budgets": ["parameter_count"],
                            "metrics": {
                                "function_lines": 100,
                                "parameter_count": 14,
                                "branch_node_count": 1,
                            },
                            "thresholds": {
                                "function_lines": 120,
                                "parameter_count": 10,
                                "branch_node_count": 18,
                            },
                        },
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return "tmp/classification.json"

    def test_build_report_groups_candidates_and_limits_small_proposals(self) -> None:
        classification_path = self._write_classification()

        report = build_report(
            self.vault,
            classification_path=classification_path,
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["function_budget_candidate_count"], 3)
        self.assertEqual(report["summary"]["shared_runtime_helper_count"], 1)
        self.assertEqual(report["summary"]["large_main_without_tests_or_docs_count"], 1)
        self.assertEqual(report["summary"]["proposal_count"], 1)
        self.assertEqual(report["summary"]["owner_backlog_count"], 2)
        self.assertEqual(report["proposals"][0]["recommended_action"], "extract_private_runtime_helper")
        blocked = next(item for item in report["candidates"] if item["symbol"] == "main")
        self.assertFalse(blocked["proposal_eligible"])
        self.assertIn("needs_direct_test_or_doc_before_refactor", blocked["proposal_blockers"])
        backlog = {item["backlog_theme"]: item for item in report["owner_backlog"]}
        self.assertEqual(
            backlog["external_report_reference_manifest_request_object"]["priority"],
            "P0",
        )
        self.assertEqual(
            backlog["external_report_reference_manifest_request_object"]["recommended_strategy"],
            "introduce_request_object_for_parameter_budget",
        )
        self.assertEqual(backlog["owner_design_backlog"]["priority"], "P1")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

    def test_build_report_groups_canonical_external_report_manifest_path(self) -> None:
        classification_path = self._write_classification(
            "ops/scripts/release/external_report_reference_manifest.py"
        )

        report = build_report(
            self.vault,
            classification_path=classification_path,
            context=fixed_context(),
        )

        backlog = {item["backlog_theme"]: item for item in report["owner_backlog"]}
        self.assertEqual(
            backlog["external_report_reference_manifest_request_object"]["priority"],
            "P0",
        )


if __name__ == "__main__":
    unittest.main()
