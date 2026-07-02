from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.planning_gate_validate import validate_run_dir

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = [pytest.mark.report_contract, pytest.mark.report_contract_core]


class RunTemplateTests(unittest.TestCase):
    def _assert_template_validation_preserves_runtime_events(
        self, template_dir: Path, runtime_events: Path
    ) -> None:
        before = runtime_events.read_text(encoding="utf-8") if runtime_events.exists() else None

        report = validate_run_dir(REPO_ROOT, template_dir)

        self.assertEqual(report["status"], "pass")
        if before is None:
            self.assertFalse(runtime_events.exists())
        else:
            self.assertEqual(runtime_events.read_text(encoding="utf-8"), before)

    def test_root_template_bundle_includes_plan_and_open_questions_helpers(self) -> None:
        self.assertTrue((REPO_ROOT / "ops" / "templates" / "plan.md").exists())
        self.assertTrue((REPO_ROOT / "ops" / "templates" / "open-questions.md").exists())
        self.assertTrue((REPO_ROOT / "ops" / "templates" / "improvement-observations.json").exists())

    def test_root_template_bundle_passes_planning_gate_validation(self) -> None:
        runtime_events = REPO_ROOT / "runs" / "run-YYYYMMDD-slug" / "runtime-events.jsonl"
        self._assert_template_validation_preserves_runtime_events(
            REPO_ROOT / "ops" / "templates",
            runtime_events,
        )

    def test_mechanism_run_template_bundle_includes_plan_and_open_questions_helpers(self) -> None:
        self.assertTrue((REPO_ROOT / "ops" / "templates" / "mechanism-run" / "plan.md").exists())
        self.assertTrue((REPO_ROOT / "ops" / "templates" / "mechanism-run" / "open-questions.md").exists())
        self.assertTrue(
            (REPO_ROOT / "ops" / "templates" / "mechanism-run" / "improvement-observations.json").exists()
        )

    def test_mechanism_run_template_bundle_passes_planning_gate_validation(self) -> None:
        runtime_events = (
            REPO_ROOT
            / "runs"
            / "run-YYYYMMDD-mechanism-slug"
            / "runtime-events.jsonl"
        )
        self._assert_template_validation_preserves_runtime_events(
            REPO_ROOT / "ops" / "templates" / "mechanism-run",
            runtime_events,
        )

    def test_mechanism_run_promotion_report_template_validates(self) -> None:
        schema = load_schema(REPO_ROOT / "ops" / "schemas" / "promotion-report.schema.json")
        data = json.loads(
            (REPO_ROOT / "ops" / "templates" / "mechanism-run" / "promotion-report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(validate_with_schema(data, schema), [])

    def test_mechanism_run_improvement_observations_template_validates(self) -> None:
        schema = load_schema(REPO_ROOT / "ops" / "schemas" / "improvement-observations.schema.json")
        data = json.loads(
            (REPO_ROOT / "ops" / "templates" / "mechanism-run" / "improvement-observations.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(validate_with_schema(data, schema), [])

    def test_root_improvement_observations_template_validates(self) -> None:
        schema = load_schema(REPO_ROOT / "ops" / "schemas" / "improvement-observations.schema.json")
        data = json.loads(
            (REPO_ROOT / "ops" / "templates" / "improvement-observations.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(validate_with_schema(data, schema), [])


if __name__ == "__main__":
    unittest.main()
