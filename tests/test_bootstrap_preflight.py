from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.bootstrap_preflight import build_report, format_text, main, write_report
from ops.scripts.schema_constants_runtime import BOOTSTRAP_PREFLIGHT_REPORT_SCHEMA_PATH
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _module_available(missing: set[str]):
    return lambda module: module not in missing


class BootstrapPreflightTests(unittest.TestCase):
    def test_runtime_report_passes_when_python_and_runtime_dependencies_exist(self) -> None:
        report = build_report(
            python_version=(3, 12, 1),
            module_available=_module_available(set()),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["artifact_kind"], "bootstrap_preflight_report")
        self.assertEqual(report["summary"]["missing_dependency_count"], 0)
        self.assertFalse(report["include_dev"])
        self.assertEqual(report["environment"]["environment_class"], "developer")
        self.assertEqual(report["environment"]["dependency_source"], "current_python_environment")
        self.assertIn("bootstrap preflight: pass", format_text(report))
        self.assertIn("interpreter:", format_text(report))

    def test_dev_report_fails_with_guidance_when_dependency_is_missing(self) -> None:
        report = build_report(
            include_dev=True,
            python_version=(3, 12, 1),
            module_available=_module_available({"pytest", "ruff"}),
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["missing_packages"], ["pytest", "ruff"])
        text = format_text(report)
        self.assertIn("pytest", text)
        self.assertIn("Run make dev-install", text)

    def test_python_version_is_a_hard_preflight_failure(self) -> None:
        report = build_report(
            python_version=(3, 11, 9),
            module_available=_module_available(set()),
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["python"]["status"], "fail")

    def test_main_returns_nonzero_for_missing_dependency(self) -> None:
        self.assertEqual(main(["--json"]), 0)

    def test_bootstrap_write_report_validates_schema_and_stays_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            report = build_report(
                vault=vault,
                include_dev=True,
                python_version=(3, 14, 3),
                module_available=_module_available(set()),
                environment_class="release-builder-clean",
                clock=lambda: dt.datetime(
                    2026,
                    4,
                    29,
                    8,
                    30,
                    tzinfo=dt.timezone.utc,
                ),
            )
            schema = load_schema(REPO_ROOT / BOOTSTRAP_PREFLIGHT_REPORT_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["environment"]["environment_class"], "release-builder-clean")
            destination = write_report(vault, report)

            self.assertEqual(destination, vault / "ops" / "reports" / "bootstrap-preflight-report.json")
            self.assertTrue(destination.exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
