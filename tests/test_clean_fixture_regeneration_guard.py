from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.public.clean_fixture_regeneration_guard import (
    CleanFixtureRegenerationGuardRequest,
    build_report,
    write_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "clean-fixture-regeneration-guard.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 20, 0, 0, tzinfo=dt.UTC),
    )


class CleanFixtureRegenerationGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/clean-fixture-regeneration-guard.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def test_dirty_ops_reports_block_clean_fixture_regeneration(self) -> None:
        report = build_report(
            CleanFixtureRegenerationGuardRequest(
                vault=self.vault,
                git_status_lines=(
                    " M ops/reports/auto-improve-readiness.json",
                    " M tests/fixtures/report_schema_samples.json",
                ),
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["dirty_ops_report_paths"],
            ["ops/reports/auto-improve-readiness.json"],
        )
        self.assertEqual(
            report["dirty_public_surface_paths"],
            ["tests/fixtures/report_schema_samples.json"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_dirty_ops_reports_always_block_regeneration(self) -> None:
        report = build_report(
            CleanFixtureRegenerationGuardRequest(
                vault=self.vault,
                git_status_lines=(" M ops/reports/goal-run-status.json",),
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["dirty_ops_report_count"], 1)
        self.assertIn("clean checkout/worktree", report["summary"]["next_action"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_surface_dirty_without_ops_reports_passes(self) -> None:
        report = build_report(
            CleanFixtureRegenerationGuardRequest(
                vault=self.vault,
                git_status_lines=(" M ops/script-output-surfaces.json",),
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["dirty_ops_report_paths"], [])
        self.assertEqual(report["dirty_public_surface_paths"], ["ops/script-output-surfaces.json"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_report_uses_schema_backed_output(self) -> None:
        report = build_report(
            CleanFixtureRegenerationGuardRequest(
                vault=self.vault,
                git_status_lines=(),
                context=fixed_context(),
            )
        )

        out_path = write_report(self.vault, report)

        self.assertEqual(out_path, self.vault / "tmp/clean-fixture-regeneration-guard.json")
        self.assertTrue(out_path.is_file())


if __name__ == "__main__":
    unittest.main()
