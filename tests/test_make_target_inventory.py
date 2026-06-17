from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.make_target_inventory import build_report, write_report
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
MAKE_TARGET_INVENTORY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "make-target-inventory.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 30, 9, 0, tzinfo=dt.UTC),
    )


class MakeTargetInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "Makefile").write_text(
            ".PHONY: alpha beta\n"
            "alpha: beta\n"
            "\t@echo alpha\n"
            "beta:\n"
            "\t@echo beta\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_report_validates_clean_phony_inventory(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["target_count"], 2)
        self.assertEqual(report["summary"]["phony_count"], 2)
        self.assertEqual(report["summary"]["module_invocation_count"], 0)
        self.assertEqual(report["missing_phony_definitions"], [])
        self.assertEqual(report["non_phony_targets"], [])
        self.assertEqual(report["targets"][0]["module_invocations"], [])
        self.assertEqual(validate_with_schema(report, load_schema(MAKE_TARGET_INVENTORY_SCHEMA_PATH)), [])

    def test_non_phony_targets_are_visible_attention(self) -> None:
        (self.vault / "Makefile").write_text(
            ".PHONY: alpha\n"
            "alpha: beta\n"
            "\t@echo alpha\n"
            "beta:\n"
            "\t@echo beta\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["non_phony_targets"], ["beta"])
        self.assertEqual(validate_with_schema(report, load_schema(MAKE_TARGET_INVENTORY_SCHEMA_PATH)), [])

    def test_missing_phony_definition_fails(self) -> None:
        (self.vault / "Makefile").write_text(
            ".PHONY: alpha beta\n"
            "alpha:\n"
            "\t@echo alpha\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing_phony_definitions"], ["beta"])

    def test_included_mk_files_are_part_of_inventory(self) -> None:
        (self.vault / "mk").mkdir()
        (self.vault / "Makefile").write_text(
            "include mk/release.mk\n",
            encoding="utf-8",
        )
        (self.vault / "mk" / "release.mk").write_text(
            ".PHONY: release-evidence-converge\n"
            "release-evidence-converge:\n"
            "\t@echo release\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertIn("release-evidence-converge", report["phony_targets"])
        self.assertIn(
            "mk/release.mk",
            report["input_fingerprints"],
        )

    def test_recipe_module_invocations_are_recorded_per_target(self) -> None:
        (self.vault / "Makefile").write_text(
            ".PHONY: alpha beta\n"
            "alpha beta:\n"
            "\t$(PYTHON) -m ops.scripts.core.sample_report --vault .\n"
            "gamma:\n"
            "\t$(PYTHON) -m ops.scripts.release.sample_release --vault .\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        targets = {target["name"]: target for target in report["targets"]}
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["module_invocation_count"], 3)
        self.assertEqual(
            targets["alpha"]["module_invocations"],
            ["ops.scripts.core.sample_report"],
        )
        self.assertEqual(
            targets["beta"]["module_invocations"],
            ["ops.scripts.core.sample_report"],
        )
        self.assertEqual(
            targets["gamma"]["module_invocations"],
            ["ops.scripts.release.sample_release"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(MAKE_TARGET_INVENTORY_SCHEMA_PATH)), [])

    def test_inventory_write_report_validates_schema(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/make-target-inventory.json")

        self.assertEqual(destination, self.vault / "ops" / "reports" / "make-target-inventory.json")
        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
