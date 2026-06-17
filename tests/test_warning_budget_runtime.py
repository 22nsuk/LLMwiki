from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.eval.warning_budget_runtime import (
    build_report,
    evaluate_warning_budget,
    warning_type_counts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _policy() -> dict:
    return {
        "strict_warning_budget": {
            "default_profile": "release_clean",
            "profiles": {
                "release_clean": {
                    "sources": {
                        "raw_registry_preflight": {
                            "warning_type_budgets": {
                                "unregistered_raw_file": 0,
                                "raw_markdown_blank_published": 0,
                            }
                        },
                        "wiki_lint": {
                            "max_total_warnings": 3,
                            "warning_type_budgets": {
                                "unregistered_raw_file": 0,
                            },
                        },
                    }
                }
            },
        }
    }


def _report(*warning_types: str, status: str | None = None) -> dict:
    warnings = [{"type": warning_type} for warning_type in warning_types]
    return {
        "status": status or ("warn" if warnings else "pass"),
        "warnings": warnings,
        "stats": {
            "warning_count": len(warnings),
        },
    }


class WarningBudgetRuntimeTest(unittest.TestCase):
    def test_warning_type_counts_are_derived_from_report_warnings(self) -> None:
        report = _report(
            "unregistered_raw_file",
            "raw_markdown_blank_published",
            "unregistered_raw_file",
        )

        self.assertEqual(
            warning_type_counts(report),
            {
                "raw_markdown_blank_published": 1,
                "unregistered_raw_file": 2,
            },
        )

    def test_evaluate_warning_budget_fails_only_budgeted_warning_types(self) -> None:
        evaluation = evaluate_warning_budget(
            _policy(),
            {
                "raw_registry_preflight": _report(
                    "unregistered_raw_file",
                    "raw_markdown_blank_created",
                ),
                "wiki_lint": _report("raw_markdown_blank_published"),
            },
        )

        failed_checks = {
            check["id"]: check
            for check in evaluation["checks"]
            if check["status"] == "fail"
        }

        self.assertEqual(evaluation["status"], "fail")
        self.assertEqual(evaluation["summary"]["failed_check_count"], 1)
        self.assertEqual(
            failed_checks["raw_registry_preflight.unregistered_raw_file"]["actual"],
            1,
        )
        self.assertNotIn("wiki_lint.raw_markdown_blank_published", failed_checks)

    def test_evaluate_warning_budget_can_cap_total_warnings(self) -> None:
        evaluation = evaluate_warning_budget(
            _policy(),
            {
                "raw_registry_preflight": _report(),
                "wiki_lint": _report(
                    "raw_markdown_blank_created",
                    "frontmatter_field_pending_required",
                    "router_summary_count_drift",
                    "orphan_page",
                ),
            },
        )

        failed_checks = {
            check["id"]: check
            for check in evaluation["checks"]
            if check["status"] == "fail"
        }
        self.assertEqual(evaluation["status"], "fail")
        self.assertEqual(failed_checks["wiki_lint.total_warnings"]["actual"], 4)
        self.assertEqual(failed_checks["wiki_lint.total_warnings"]["budget"], 3)

    def test_evaluate_warning_budget_fails_missing_or_failed_sources(self) -> None:
        missing_source = evaluate_warning_budget(_policy(), {"wiki_lint": _report()})
        failed_source = evaluate_warning_budget(
            _policy(),
            {
                "raw_registry_preflight": _report(status="fail"),
                "wiki_lint": _report(),
            },
        )

        self.assertEqual(missing_source["status"], "fail")
        self.assertEqual(missing_source["summary"]["source_fail_count"], 1)
        self.assertEqual(missing_source["sources"]["raw_registry_preflight"]["status"], "missing")
        self.assertEqual(failed_source["status"], "fail")
        self.assertEqual(failed_source["summary"]["source_fail_count"], 1)

    def test_build_report_uses_injected_clock_and_validates_schema(self) -> None:
        policy, _ = load_policy(REPO_ROOT)
        context = RuntimeContext.from_policy(
            policy,
            clock=lambda: dt.datetime(2026, 4, 19, 0, 0, tzinfo=dt.UTC),
        )

        report = build_report(
            REPO_ROOT,
            context=context,
            source_reports={
                "raw_registry_preflight": _report(),
                "wiki_lint": _report(),
            },
        )

        self.assertEqual(report["$schema"], "ops/schemas/warning-budget-report.schema.json")
        self.assertEqual(report["generated_at"], "2026-04-19T00:00:00Z")
        self.assertEqual(report["profile"], "release_clean")
        self.assertEqual(report["status"], "pass")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
