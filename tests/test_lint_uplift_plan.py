from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.lint_uplift_plan import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "strict-lint-inventory.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 24, 8, 0, tzinfo=dt.UTC),
    )


class LintUpliftPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "mk").mkdir(exist_ok=True)
        (self.vault / "tools").mkdir(exist_ok=True)
        (self.vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
        (self.vault / "tests").mkdir(exist_ok=True)
        (self.vault / "ops" / "scripts" / "alpha.py").write_text("x = 1\n", encoding="utf-8")
        (self.vault / "tests" / "test_alpha.py").write_text("def test_alpha(): pass\n", encoding="utf-8")
        (self.vault / "tools" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
        (self.vault / "tools" / "ruff_strict_preview.py").write_text("", encoding="utf-8")
        (self.vault / "tools" / "strict_preview_audit.py").write_text("", encoding="utf-8")
        (self.vault / "mk" / "static.mk").write_text(
            "RUFF_STRICT_PREVIEW_TARGETS ?= ops/scripts tests tools\n"
            "ruff-strict-preview:\n"
            "\tpython tools/ruff_strict_preview.py --targets \"$(RUFF_STRICT_PREVIEW_TARGETS)\"\n",
            encoding="utf-8",
        )
        (self.vault / "tmp").mkdir(exist_ok=True)
        (self.vault / "tmp" / "strict-preview-audit.json").write_text(
            json.dumps({"status": "attention", "summary": {"total_error_count": 4, "ruff_error_count": 3}}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_report_uses_full_scope_preview_targets_without_blocking_static(self) -> None:
        report = build_report(self.vault, targets=["ops/scripts", "tests", "tools"], context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["strict_preview"]["target_mode"], "full_scope_targets")
        self.assertFalse(report["strict_preview"]["gate_blocks_static"])
        self.assertTrue(report["target_contract"]["preview_full_scope_targets_enforced"])
        self.assertEqual(report["strict_preview"]["audit_ruff_error_count"], 3)
        self.assertEqual(report["full_scope"]["python_file_count"], 5)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_indirect_preview_target_mode_is_visible(self) -> None:
        (self.vault / "mk" / "static.mk").write_text(
            "ruff-strict-preview:\n"
            "\tpython tools/ruff_strict_preview.py @ops/indirect-ruff-targets.txt\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, targets=["ops/scripts"], context=fixed_context())

        self.assertEqual(report["strict_preview"]["target_mode"], "indirect_target_list")
        self.assertFalse(report["target_contract"]["preview_full_scope_targets_enforced"])

    def test_write_report_validates_schema(self) -> None:
        report = build_report(self.vault, targets=["ops/scripts"], context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/lint-uplift-plan.json")

        self.assertTrue(destination.exists())

    def test_example_report_tracks_promoted_rule_families_and_remaining_debt(self) -> None:
        (self.vault / "pyproject.toml").write_text(
            "[tool.ruff]\n"
            'target-version = "py312"\n\n'
            "[tool.ruff.lint]\n"
            'select = ["E4", "E7", "E9", "F", "UP"]\n',
            encoding="utf-8",
        )
        (self.vault / "tmp" / "strict-preview-audit.json").write_text(
            json.dumps(
                {
                    "status": "attention",
                    "summary": {"total_error_count": 5, "ruff_error_count": 5},
                    "ruff": {
                        "rule_counts": {
                            "B904": 3,
                            "I001": 2,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, targets=["ops/scripts", "tests", "tools"], context=fixed_context())

        self.assertEqual(report["enforced_rule_families"], ["UP"])
        self.assertEqual(report["remaining_violations"], {"B": 3, "SIM": 0, "I": 2})
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
