from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.command_runtime import TimedProcessResult
from ops.scripts.release.source_package_smoke import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "source-package-smoke.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.timezone.utc),
    )


class SourcePackageSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/source-package-smoke.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy(self, rel_path: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_source_zip(self) -> Path:
        path = self.vault / "build" / "release" / "LLMwiki-source.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "LLMwiki/release-archive-self-description.json",
                json.dumps({"archive_root_name": "LLMwiki"}, sort_keys=True),
            )
            archive.writestr("LLMwiki/README.md", "# source package\n")
            archive.writestr("LLMwiki/ops/scripts/__init__.py", "")
            archive.writestr("LLMwiki/tests/test_import_fallback_contract.py", "def test_ok():\n    assert True\n")
        return path

    def test_source_package_smoke_passes_without_ops_reports_or_external_reports(self) -> None:
        source_zip = self._write_source_zip()
        calls: list[tuple[str, Path]] = []

        def fake_run(command: list[str], *, cwd: Path, timeout_seconds: int) -> TimedProcessResult:
            calls.append((" ".join(command), cwd))
            return TimedProcessResult(
                args=command,
                returncode=0,
                stdout="ok",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="",
            )

        with patch("ops.scripts.release.source_package_smoke.run_with_timeout", fake_run):
            report = build_report(
                self.vault,
                source_zip=source_zip.relative_to(self.vault).as_posix(),
                extract_parent="build/source-package-smoke/extract",
                source_python="/usr/bin/python3",
                ruff_targets="ops/scripts tests",
                mypy_targets="@ops/mypy-allowlist.txt",
                timeout_seconds=60,
                context=fixed_context(),
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["extract"]["archive_root_name"], "LLMwiki")
        self.assertEqual(report["extract"]["status"], "pass")
        self.assertEqual([item["name"] for item in report["commands"]], ["import-runtime", "ruff", "mypy", "fast-smoke"])
        self.assertTrue(all(cwd.name == "LLMwiki" for _, cwd in calls))
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report, "build/source-package-smoke/source-package-smoke.json").exists())


if __name__ == "__main__":
    unittest.main()
