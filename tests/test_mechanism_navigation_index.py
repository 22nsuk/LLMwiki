from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.mechanism_navigation_index import build_report

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class MechanismNavigationIndexTests(unittest.TestCase):
    def test_index_links_mechanism_script_to_make_target_schema_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts" / "mechanism").mkdir(parents=True)
            (vault / "mk").mkdir()
            (vault / "ops" / "scripts" / "mechanism" / "sample_mechanism.py").write_text(
                "DEFAULT_OUT = 'ops/reports/sample.json'\n"
                "SCHEMA = 'ops/schemas/sample.schema.json'\n"
                "if __package__ in (None, \"\"):  # pragma: no cover - direct script fallback\n"
                "    pass\n"
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "Makefile").write_text("include mk/mechanism.mk\n", encoding="utf-8")
            (vault / "mk" / "mechanism.mk").write_text(
                "sample-mechanism:\n\tpython -m ops.scripts.sample_mechanism\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["script_count"], 1)
        self.assertEqual(report["scripts"][0]["make_targets"], ["sample-mechanism"])
        self.assertEqual(report["scripts"][0]["default_output_paths"], ["ops/reports/sample.json"])
        self.assertEqual(report["scripts"][0]["schema_refs"], ["ops/schemas/sample.schema.json"])
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/mechanism-navigation-index.schema.json")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
