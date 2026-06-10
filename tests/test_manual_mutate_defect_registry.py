from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

from ops.scripts.core.manual_mutate_defect_registry import build_report
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema

REPO_ROOT = Path(__file__).resolve().parents[1]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 23, 12, 0, tzinfo=dt.UTC),
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

    def test_manual_mutate_scripts_are_archived_after_canonical_fixes(self) -> None:
        archived_scripts = [
            "tools/manual_mutate_auto_improve_decision_record_fallback.py",
            "tools/manual_mutate_auto_improve_timeout_telemetry.py",
            "tools/manual_mutate_auto_improve_existing_telemetry_inline.py",
        ]
        for rel_path in archived_scripts:
            with self.subTest(rel_path=rel_path):
                self.assertFalse((REPO_ROOT / rel_path).exists())


if __name__ == "__main__":
    unittest.main()
