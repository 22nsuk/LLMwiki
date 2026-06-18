from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.core.bootstrap_preflight import (
    build_report,
    format_text,
    main,
    write_report,
)
from ops.scripts.core.schema_constants_runtime import (
    BOOTSTRAP_PREFLIGHT_REPORT_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _module_available(missing: set[str]) -> Callable[[str], bool]:
    return lambda module: module not in missing


class BootstrapPreflightTests(unittest.TestCase):
    def test_runtime_report_passes_when_python_and_runtime_dependencies_exist(self) -> None:
        report = build_report(
            python_version=(3, 12, 1),
            module_available=_module_available(set()),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["artifact_kind"], "bootstrap_preflight_report")
        self.assertIn("ops/scripts/core/bootstrap_preflight.py", report["input_fingerprints"])
        self.assertEqual(report["summary"]["missing_dependency_count"], 0)
        self.assertEqual(report["summary"]["executor_tooling_failure_count"], 0)
        self.assertFalse(report["include_dev"])
        self.assertEqual(report["environment"]["environment_class"], "developer")
        self.assertEqual(report["environment"]["dependency_source"], "current_python_environment")
        self.assertEqual(report["environment"]["executor_tooling"]["status"], "pass")
        self.assertIn("bootstrap preflight: pass", format_text(report))
        self.assertIn("interpreter:", format_text(report))
        self.assertIn("codex executor:", format_text(report))

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

    def test_goal_runtime_report_blocks_workspace_virtualenv_codex_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            venv_bin = vault / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "python").chmod(0o755)
            (venv_bin / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "codex").chmod(0o755)

            with mock.patch.dict(os.environ, {"PATH": str(venv_bin)}):
                report = build_report(
                    vault=vault,
                    environment_class="goal-runtime",
                    python_version=(3, 12, 1),
                    module_available=_module_available(set()),
                )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["environment"]["executor_tooling"]["status"], "fail")
        self.assertTrue(
            report["environment"]["executor_tooling"]["workspace_virtualenv_codex_shadowing_path"]
        )
        self.assertEqual(
            report["summary"]["executor_tooling_failures"],
            ["workspace_virtualenv_codex_shadow"],
        )

    def test_goal_runtime_report_requires_workspace_virtualenv_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            with mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}):
                report = build_report(
                    vault=vault,
                    include_dev=True,
                    environment_class="goal-runtime",
                    python_version=(3, 12, 1),
                    module_available=_module_available(set()),
                )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["environment"]["executor_tooling"]["status"], "fail")
        self.assertEqual(
            report["summary"]["executor_tooling_failures"],
            ["workspace_virtualenv_python_missing"],
        )
        self.assertFalse(report["environment"]["install_attempted"])
        self.assertIn("make goal-runtime-python-preflight", report["guidance"])

    def test_goal_runtime_report_allows_outer_codex_when_workspace_virtualenv_is_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            venv_bin = vault / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "python").chmod(0o755)
            (venv_bin / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "codex").chmod(0o755)
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            with mock.patch.dict(
                os.environ,
                {"PATH": f"{venv_bin}{os.pathsep}{outer_codex.parent}"},
            ):
                report = build_report(
                    vault=vault,
                    environment_class="goal-runtime",
                    python_version=(3, 12, 1),
                    module_available=_module_available(set()),
                )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["environment"]["executor_tooling"]["status"], "pass")
        self.assertTrue(
            report["environment"]["executor_tooling"]["workspace_virtualenv_codex_shadowing_path"]
        )
        self.assertTrue(report["environment"]["executor_tooling"]["codex_outside_workspace_virtualenv"])

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
                    tzinfo=dt.UTC,
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
