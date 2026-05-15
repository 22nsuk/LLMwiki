from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

from ops.scripts.manual_mutate_defect_registry import build_report
from ops.scripts.python_function_budget_runtime import python_function_budget_candidates
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema


REPO_ROOT = Path(__file__).resolve().parents[1]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 23, 12, 0, tzinfo=dt.timezone.utc),
    )


class ManualMutateDefectRegistryTests(unittest.TestCase):
    def test_registry_classifies_manual_mutate_scripts_with_fix_and_regression_status(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())
        schema = load_schema(REPO_ROOT / "ops" / "schemas" / "manual-mutate-defect-registry.schema.json")

        self.assertEqual(validate_with_schema(report, schema), [])
        self.assertEqual(report["artifact_kind"], "manual_mutate_defect_registry")
        self.assertEqual(report["artifact_status"], "current")
        self.assertEqual(report["currentness"]["status"], "current")
        self.assertIn("artifact_envelope_schema", report["input_fingerprints"])
        self.assertIn("manual_mutate_scripts", report["input_fingerprints"])
        self.assertEqual(report["status"], "pass")
        defects = {entry["defect_id"]: entry for entry in report["defects"]}
        self.assertEqual(
            defects["decision_record_promotion_report_absorption_gap"]["canonical_fix_status"],
            "fixed",
        )
        self.assertEqual(
            defects["decision_record_promotion_report_absorption_gap"]["regression_status"],
            "covered",
        )
        self.assertEqual(
            defects["run_telemetry_timeout_merge_loss"]["canonical_fix_status"],
            "fixed",
        )
        self.assertEqual(
            defects["run_telemetry_timeout_merge_loss"]["regression_status"],
            "covered",
        )
        self.assertEqual(
            defects["run_telemetry_existing_report_helper_indirection"]["canonical_fix_status"],
            "fixed",
        )
        self.assertEqual(
            defects["run_telemetry_existing_report_helper_indirection"]["regression_status"],
            "covered",
        )

    def test_manual_mutate_main_functions_stay_below_small_refactor_budget(self) -> None:
        candidates = python_function_budget_candidates(
            REPO_ROOT,
            {
                "profiles": {
                    "manual_mutate_tools": {
                        "include_prefixes": [
                            "tools/manual_mutate_auto_improve_decision_record_fallback.py",
                            "tools/manual_mutate_auto_improve_timeout_telemetry.py",
                        ],
                        "lines": 120,
                        "params": 10,
                        "branches": 18,
                    }
                }
            },
        )

        self.assertEqual(
            [
                (item["page"], item["symbol"], item["triggered_budgets"])
                for item in candidates
            ],
            [],
        )


if __name__ == "__main__":
    unittest.main()
