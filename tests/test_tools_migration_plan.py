from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.tools_migration_plan import build_report

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class ToolsMigrationPlanTests(unittest.TestCase):
    def test_plan_retains_live_tools_and_marks_unreferenced_tools_as_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "tools").mkdir()
            (vault / "mk").mkdir()
            (vault / "tools" / "live.py").write_text("print('live')\n", encoding="utf-8")
            (vault / "tools" / "stale.py").write_text("print('stale')\n", encoding="utf-8")
            (vault / "Makefile").write_text("include mk/static.mk\n", encoding="utf-8")
            (vault / "mk" / "static.mk").write_text(
                "live:\n\t$(PYTHON) tools/live.py\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        tools = {item["path"]: item for item in report["tools"]}
        self.assertEqual(report["status"], "attention")
        self.assertEqual(tools["tools/live.py"]["retained_reason"], "live_make_target")
        self.assertFalse(tools["tools/live.py"]["deletion_candidate"])
        self.assertTrue(tools["tools/stale.py"]["deletion_candidate"])
        self.assertEqual(report["deletion_candidates"], ["tools/stale.py"])
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/tools-migration-plan.schema.json")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
