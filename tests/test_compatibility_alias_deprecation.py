from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.compatibility_alias_deprecation import build_report
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]
SCRIPT_FLAT_IMPORT_ALIASES = Path("ops/script-flat-import-aliases.json")
SCRIPT_FLAT_IMPORT_ALIASES_SCHEMA = Path(
    "ops/schemas/script-flat-import-aliases.schema.json"
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class CompatibilityAliasDeprecationTests(unittest.TestCase):
    def test_flat_import_alias_registry_schema_validates(self) -> None:
        payload = json.loads(SCRIPT_FLAT_IMPORT_ALIASES.read_text(encoding="utf-8"))

        self.assertEqual(
            validate_with_schema(payload, load_schema(SCRIPT_FLAT_IMPORT_ALIASES_SCHEMA)),
            [],
        )

    def test_inventory_retains_aliases_until_migration_window_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "mk").mkdir()
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "ops" / "scripts" / "core").mkdir()
            (vault / "ops" / "scripts" / "test").mkdir()
            (vault / "tests").mkdir()
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
            (vault / "ops" / "scripts" / "core" / "unclassified_runtime.py").write_text(
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_flat_caller.py").write_text(
                "from ops.scripts.legacy_runtime import main\n"
                "from ops.scripts.test.lane_runtime import main as canonical_main\n",
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
            (vault / "ops" / "script-lifecycle-policy.json").write_text(
                json.dumps(
                    {
                        "modules": [
                            {
                                "canonical_module": "ops.scripts.test.lane_runtime",
                                "path": "ops/scripts/test/lane_runtime.py",
                                "lifecycle": "test_only",
                                "install_state": "not_installed",
                                "console_scripts": [],
                                "replacement": "python -m ops.scripts.test.lane_runtime",
                                "removal_ready": False,
                                "rationale": "fixture lifecycle contract",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-lifecycle-overrides.json").write_text(
                json.dumps(
                    {
                        "overrides": []
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-flat-import-aliases.json").write_text(
                json.dumps(
                    {
                        "aliases": [
                            {
                                "canonical_module": "ops.scripts.test.lane_runtime",
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
        self.assertNotIn(("flat_import_reexport", "ops.scripts.unclassified_runtime"), aliases)
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
        actual_caller_counts = {
            item["name"]: item.get("actual_caller_count")
            for item in report["aliases"]
            if item["alias_type"] == "flat_import_reexport"
        }
        self.assertEqual(
            actual_caller_counts,
            {
                "ops.scripts.legacy_runtime": 1,
                "ops.scripts.lane_runtime": 0,
            },
        )
        retained_reasons = {
            item["name"]: item["retained_reason"]
            for item in report["aliases"]
            if item["alias_type"] == "flat_import_reexport"
        }
        self.assertEqual(
            retained_reasons,
            {
                "ops.scripts.legacy_runtime": "declared_stable_compatibility_facade",
                "ops.scripts.lane_runtime": "test_only_legacy_module_compatibility",
            },
        )
        self.assertEqual(
            report["flat_import_actual_callers"],
            [
                {
                    "alias": "ops.scripts.legacy_runtime",
                    "preferred_replacement": "ops.scripts.core.legacy_runtime",
                    "path": "tests/test_flat_caller.py",
                    "line": 1,
                    "usage_kind": "from_import",
                }
            ],
        )
        self.assertEqual(report["summary"]["flat_import_reexport_count"], 2)
        self.assertEqual(report["summary"]["flat_import_actual_caller_count"], 1)
        self.assertEqual(report["summary"]["flat_import_actual_alias_count"], 1)
        self.assertEqual(report["summary"]["stable_import_surface_count"], 1)
        self.assertEqual(report["summary"]["make_alias_count"], 1)
        self.assertEqual(report["summary"]["removal_ready_count"], 0)
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/compatibility-alias-deprecation.schema.json")),
            [],
        )

    def test_lifecycle_override_does_not_create_flat_reexport_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "ops" / "scripts" / "core").mkdir()
            (vault / "ops").mkdir(exist_ok=True)
            (vault / "ops" / "scripts" / "__init__.py").write_text(
                "class _ReexportFinder: pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "core" / "new_runtime.py").write_text(
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-lifecycle-policy.json").write_text(
                json.dumps(
                    {
                        "modules": [
                            {
                                "canonical_module": "ops.scripts.core.new_runtime",
                                "lifecycle": "helper",
                                "install_state": "not_installed",
                                "console_scripts": [],
                                "replacement": "python -m ops.scripts.core.new_runtime",
                                "removal_ready": False,
                                "rationale": "fixture lifecycle contract",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-lifecycle-overrides.json").write_text(
                json.dumps(
                    {
                        "overrides": [
                            {
                                "canonical_module": "ops.scripts.core.new_runtime",
                                "lifecycle": "helper",
                                "replacement": "python -m ops.scripts.core.new_runtime",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        aliases = {(item["alias_type"], item["name"]) for item in report["aliases"]}
        self.assertNotIn(("flat_import_reexport", "ops.scripts.new_runtime"), aliases)


if __name__ == "__main__":
    unittest.main()
