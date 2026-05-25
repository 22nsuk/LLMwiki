from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.type_uplift_plan import build_report, write_report

from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "strict-type-inventory.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 24, 8, 5, tzinfo=dt.UTC),
    )


class TypeUpliftPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "mk").mkdir(exist_ok=True)
        (self.vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
        (self.vault / "tests").mkdir(exist_ok=True)
        (self.vault / "tools").mkdir(exist_ok=True)
        (self.vault / "ops" / "scripts" / "alpha.py").write_text("x = 1\n", encoding="utf-8")
        (self.vault / "tests" / "test_alpha.py").write_text("def test_alpha(): pass\n", encoding="utf-8")
        (self.vault / "tools" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
        (self.vault / "mk" / "static.mk").write_text(
            "MYPY_TARGETS ?= ops/scripts\n"
            "MYPY_STRICT_PREVIEW_TARGETS ?= ops/scripts tests tools\n",
            encoding="utf-8",
        )
        (self.vault / "tmp").mkdir(exist_ok=True)
        (self.vault / "tmp" / "strict-preview-audit.json").write_text(
            json.dumps({"status": "attention", "summary": {"total_error_count": 5, "mypy_error_count": 2}}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_report_tracks_full_scope_type_targets(self) -> None:
        report = build_report(self.vault, targets=["ops/scripts", "tests", "tools"], context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["default_mypy"]["target_mode"], "full_scope_targets")
        self.assertEqual(report["strict_preview"]["target_mode"], "full_scope_targets")
        self.assertTrue(report["target_contract"]["default_full_scope_targets_enforced"])
        self.assertTrue(report["target_contract"]["strict_preview_full_scope_targets_enforced"])
        self.assertEqual(report["strict_preview"]["audit_mypy_error_count"], 2)
        self.assertEqual(report["full_scope"]["python_file_count"], 3)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_indirect_target_file_mode_is_visible(self) -> None:
        (self.vault / "mk" / "static.mk").write_text(
            "MYPY_TARGETS ?= @ops/indirect-mypy-targets.txt\n"
            "MYPY_STRICT_PREVIEW_TARGETS ?= @ops/indirect-strict-preview-targets.txt\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, targets=["ops/scripts"], context=fixed_context())

        self.assertEqual(report["default_mypy"]["target_mode"], "indirect_target_list")
        self.assertEqual(report["strict_preview"]["target_mode"], "indirect_target_list")
        self.assertFalse(report["target_contract"]["default_full_scope_targets_enforced"])
        self.assertFalse(report["target_contract"]["strict_preview_full_scope_targets_enforced"])

    def test_write_report_validates_schema(self) -> None:
        report = build_report(self.vault, targets=["ops/scripts"], context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/type-uplift-plan.json")

        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
