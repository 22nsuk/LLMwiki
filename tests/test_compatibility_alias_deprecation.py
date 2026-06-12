from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.compatibility_alias_deprecation import build_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class CompatibilityAliasDeprecationTests(unittest.TestCase):
    def test_inventory_retains_aliases_until_migration_window_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "mk").mkdir()
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "ops" / "scripts" / "core").mkdir()
            (vault / "ops" / "scripts" / "test").mkdir()
            (vault / "ops").mkdir(exist_ok=True)
            (vault / "Makefile").write_text("include mk/test.mk\n", encoding="utf-8")
            (vault / "mk" / "test.mk").write_text(
                "old-target: new-target\n"
                "\t@echo \"old-target is a compatibility alias; prefer new-target.\"\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "__init__.py").write_text(
                "class _ReexportFinder: pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "core" / "legacy_runtime.py").write_text(
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "test" / "lane_runtime.py").write_text(
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-module-surfaces.json").write_text(
                json.dumps(
                    {
                        "stable_import_surfaces": [
                            {
                                "path": "ops/scripts/core/legacy_runtime.py",
                                "role": "compatibility_facade",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        aliases = {(item["alias_type"], item["name"]) for item in report["aliases"]}
        self.assertIn(("make_target", "old-target"), aliases)
        self.assertIn(("flat_import_reexport", "ops.scripts.legacy_runtime"), aliases)
        self.assertIn(("flat_import_reexport", "ops.scripts.lane_runtime"), aliases)
        self.assertIn(("stable_import_surface", "legacy_runtime"), aliases)
        replacements = {
            item["name"]: item["preferred_replacement"]
            for item in report["aliases"]
            if item["alias_type"] == "flat_import_reexport"
        }
        self.assertEqual(
            replacements,
            {
                "ops.scripts.legacy_runtime": "ops.scripts.core.legacy_runtime",
                "ops.scripts.lane_runtime": "ops.scripts.test.lane_runtime",
            },
        )
        self.assertEqual(report["summary"]["flat_import_reexport_count"], 2)
        self.assertEqual(report["summary"]["stable_import_surface_count"], 1)
        self.assertEqual(report["summary"]["make_alias_count"], 1)
        self.assertEqual(report["summary"]["removal_ready_count"], 0)
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/compatibility-alias-deprecation.schema.json")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
