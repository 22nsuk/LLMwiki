from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.eval.wiki_lint_review_classification import (
    build_report,
    classify_review_candidates,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-lint-review-classification.schema.json"


class WikiLintReviewClassificationTests(unittest.TestCase):
    def test_classifies_review_candidates_into_primary_buckets(self) -> None:
        rows = classify_review_candidates(
            [
                {
                    "type": "python_function_budget_candidate",
                    "page": "ops/scripts/example.py",
                    "symbol": "main",
                    "line": 10,
                    "profile": "ops_runtime",
                    "triggered_budgets": ["function_lines"],
                    "value": 44,
                    "threshold": 30,
                    "suggested_action": "review_function_budget",
                },
                {
                    "type": "wiki_synthesis_multi_question_watch_candidate",
                    "page": "wiki/synthesis--broad.md",
                    "value": 7,
                    "threshold": 5,
                    "suggested_action": "watch_scope_boundary",
                },
                {
                    "type": "synthesis_follow_up_split_candidate",
                    "page": "wiki/synthesis--split.md",
                    "value": 1,
                    "threshold": 0,
                    "suggested_action": "rewrite_refresh",
                },
            ]
        )

        self.assertEqual(
            [row["primary_bucket"] for row in rows],
            ["function_budget", "documentation_candidate", "true_refactor_target"],
        )
        self.assertTrue(rows[0]["refactor_candidate"])
        self.assertEqual(rows[0]["symbol"], "main")
        self.assertEqual(rows[0]["line"], 10)
        self.assertEqual(rows[0]["profile"], "ops_runtime")
        self.assertEqual(rows[0]["triggered_budgets"], ["function_lines"])
        self.assertFalse(rows[1]["refactor_candidate"])
        self.assertTrue(rows[2]["refactor_candidate"])

    def test_build_report_accepts_existing_lint_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            lint_report = vault / "tmp" / "lint.json"
            lint_report.parent.mkdir()
            lint_report.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "review_candidates": [
                            {
                                "type": "page_lines_over_threshold",
                                "page": "wiki/example.md",
                                "value": 101,
                                "threshold": 100,
                                "suggested_action": "review_for_split",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, lint_report_path=str(lint_report))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["documentation_candidate_count"], 1)
            self.assertEqual(report["lint_report"]["review_candidate_count"], 1)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
