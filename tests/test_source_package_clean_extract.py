from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
import zipfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.command_runtime import CommandHeartbeat, TimedProcessResult
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_package_clean_extract import SourcePackageCleanExtractRequest, build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "source-package-clean-extract.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 9, 12, 0, tzinfo=dt.timezone.utc),
    )


class SourcePackageCleanExtractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/source-package-clean-extract.schema.json")
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_zip_smoke(self, *, archive_budget_pass: bool = True) -> None:
        path = self.vault / "tmp" / "release-distribution-zip-smoke.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "manifest_comparison": {"pass": True},
                    "archive_budget": {"pass": archive_budget_pass},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _write_source_zip(self, root_name: str) -> Path:
        path = self.vault / "tmp" / "LLMwiki-source.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                f"{root_name}/release-archive-self-description.json",
                json.dumps({"archive_root_name": root_name}, sort_keys=True),
            )
            archive.writestr(f"{root_name}/README.md", "# source package\n")
            archive.writestr(f"{root_name}/ops/scripts/example.py", "print('ok')\n")
        return path

    def test_clean_extract_report_records_source_package_checks(self) -> None:
        extract_parent = self.vault / "tmp" / "source-package-check" / "extract"
        source_zip = self._write_source_zip("LLMwiki")
        self._write_zip_smoke()
        calls: list[str] = []

        def fake_run(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: int,
            heartbeat_interval_seconds: int | None = None,
            heartbeat_callback: Callable[[CommandHeartbeat], None] | None = None,
        ) -> TimedProcessResult:
            calls.append(" ".join(command))
            heartbeat_count = 0
            quiet_seconds = 0
            if "ops.scripts.script_output_surfaces" in command:
                out_path = cwd / command[command.index("--out") + 1]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text("{}", encoding="utf-8")
            if "ops.scripts.test_execution_summary" in command:
                heartbeat_count = 1
                quiet_seconds = heartbeat_interval_seconds or 0
                if heartbeat_callback is not None:
                    heartbeat_callback(
                        CommandHeartbeat(
                            args=command,
                            heartbeat_index=1,
                            elapsed_seconds=float(quiet_seconds),
                            timeout_seconds=timeout_seconds,
                            quiet_seconds=quiet_seconds,
                        )
                    )
                self.assertTrue((cwd / "ops" / "script-output-surfaces.json").is_file())
                out_path = cwd / command[command.index("--out") + 1]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(
                        {
                            "status": "pass",
                            "deselection_lifecycle": {
                                "status": "pass",
                                "actual_deselected_count": 0,
                                "max_allowed_deselected_count": 0,
                                "over_budget": False,
                                "expires_at": "",
                                "next_action": "none",
                            },
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            return TimedProcessResult(
                args=command,
                returncode=0,
                stdout="ok",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="",
                heartbeat_count=heartbeat_count,
                heartbeat_interval_seconds=heartbeat_interval_seconds or 0,
                quiet_seconds=quiet_seconds,
                observation_mode="process_heartbeat",
            )

        with patch("ops.scripts.source_package_clean_extract.run_with_timeout", fake_run):
            report = build_report(
                self.vault,
                source_zip=source_zip,
                extract_parent=extract_parent,
                source_python="/usr/bin/python3",
                ruff_targets="ops/scripts tests",
                mypy_targets="@ops/mypy-allowlist.txt",
                test_summary_out="tmp/source-package-pytest-summary.json",
                deselection_policy="ops/policies/report-contract-deselections.json",
                pytest_mark_expr="not release_sealing",
                tests="tests",
                deselects="--deselect=tests/test_external_report_lifecycle_static.py",
                pytest_flags="-q",
                zip_smoke_report="tmp/release-distribution-zip-smoke.json",
                heartbeat_interval_seconds=30,
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["script_output_surfaces_status"], "pass")
        self.assertEqual(report["ruff_status"], "pass")
        self.assertEqual(report["mypy_status"], "pass")
        self.assertEqual(report["test_source_package_status"], "pass")
        self.assertEqual(report["deselection_budget_status"]["status"], "pass")
        self.assertEqual(report["source_package_reproducibility_status"], "pass")
        self.assertEqual(report["heartbeat_observability"]["status"], "pass")
        self.assertEqual(report["heartbeat_observability"]["command_count"], 4)
        self.assertEqual(report["heartbeat_observability"]["heartbeat_enabled_command_count"], 4)
        self.assertEqual(report["heartbeat_observability"]["heartbeat_event_count"], 1)
        self.assertEqual(report["heartbeat_observability"]["max_quiet_seconds"], 30)
        self.assertEqual(report["heartbeat_observability"]["quiet_command_names"], ["source-package-pytest"])
        self.assertEqual(report["extract"]["parent"], "tmp/source-package-check/extract")
        self.assertEqual(report["extract"]["root"], "tmp/source-package-check/extract/LLMwiki")
        self.assertEqual(report["extract"]["archive_root_name"], "LLMwiki")
        self.assertEqual(report["extract"]["archive_root_source"], "archive_self_description")
        self.assertEqual(len(report["commands"]), 4)
        self.assertEqual(report["commands"][0]["name"], "script-output-surfaces")
        self.assertEqual(report["commands"][0]["observation_mode"], "process_heartbeat")
        self.assertEqual(report["commands"][0]["heartbeat_interval_seconds"], 30)
        self.assertEqual(report["commands"][3]["heartbeat_count"], 1)
        self.assertEqual(report["commands"][3]["quiet_seconds"], 30)
        self.assertEqual(report["commands"][3]["heartbeat_events"][0]["heartbeat_index"], 1)
        self.assertEqual(len(calls), 4)
        self.assertIn("ops.scripts.script_output_surfaces", calls[0])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

    def test_clean_extract_fails_when_zip_smoke_archive_budget_fails(self) -> None:
        extract_root = self.vault / "tmp" / "source-package-check" / "extract" / "LLMwiki"
        source_zip = self._write_source_zip(extract_root.name)
        self._write_zip_smoke(archive_budget_pass=False)

        def fake_run(
            command: list[str],
            *,
            cwd: Path,
            timeout_seconds: int,
            heartbeat_interval_seconds: int | None = None,
            heartbeat_callback: Callable[[CommandHeartbeat], None] | None = None,
        ) -> TimedProcessResult:
            if "ops.scripts.test_execution_summary" in command:
                out_path = cwd / command[command.index("--out") + 1]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps({"status": "pass", "deselection_lifecycle": {"status": "pass"}}, sort_keys=True),
                    encoding="utf-8",
                )
            return TimedProcessResult(
                args=command,
                returncode=0,
                stdout="ok",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="",
                heartbeat_interval_seconds=heartbeat_interval_seconds or 0,
                observation_mode="process_heartbeat",
            )

        with patch("ops.scripts.source_package_clean_extract.run_with_timeout", fake_run):
            report = build_report(
                SourcePackageCleanExtractRequest(
                    vault=self.vault,
                    source_zip=source_zip,
                    extract_root=extract_root,
                    source_python="/usr/bin/python3",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="@ops/mypy-allowlist.txt",
                    test_summary_out="tmp/source-package-pytest-summary.json",
                    deselection_policy="ops/policies/report-contract-deselections.json",
                    pytest_mark_expr="not release_sealing",
                    tests="tests",
                    deselects="",
                    pytest_flags="-q",
                    zip_smoke_report="tmp/release-distribution-zip-smoke.json",
                    context=fixed_context(),
                )
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["source_package_reproducibility_status"], "fail")
        self.assertEqual(report["extract"]["archive_root_source"], "explicit_extract_root")
        self.assertFalse(report["zip_smoke_report"]["archive_budget_pass"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
