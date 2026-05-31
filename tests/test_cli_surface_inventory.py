from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.cli_surface_inventory import build_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class CliSurfaceInventoryTests(unittest.TestCase):
    def test_inventory_resolves_pyproject_makefile_and_direct_fallback_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts" / "core").mkdir(parents=True)
            (vault / "ops" / "scripts" / "release").mkdir(parents=True)
            (vault / "mk").mkdir()
            (vault / "pyproject.toml").write_text(
                "[project]\nname = 'sample'\n[project.scripts]\nllmwiki-sample = 'ops.scripts.core.sample_cli:main'\n",
                encoding="utf-8",
            )
            (vault / "Makefile").write_text("include mk/core.mk\n", encoding="utf-8")
            (vault / "mk" / "core.mk").write_text(
                "sample:\n\tpython -m ops.scripts.sample_cli --help\n"
                "status:\n\tpython -m ops.scripts.release.status_cli --vault .\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "core" / "sample_cli.py").write_text(
                "if __package__ in (None, \"\"):  # pragma: no cover - direct script fallback\n"
                "    pass\n"
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "release" / "status_cli.py").write_text(
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-output-surfaces.json").write_text(
                '{"surfaces":[{"path":"ops/scripts/core/sample_cli.py","direct_fallback_eligible":true}]}\n',
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["module_count"], 2)
        modules = {item["module"]: item for item in report["modules"]}
        self.assertEqual(modules["ops.scripts.core.sample_cli"]["path"], "ops/scripts/core/sample_cli.py")
        self.assertEqual(
            set(modules["ops.scripts.core.sample_cli"]["aliases"]),
            {"ops.scripts.core.sample_cli", "ops.scripts.sample_cli"},
        )
        self.assertEqual(
            set(modules["ops.scripts.core.sample_cli"]["sources"]),
            {"pyproject_scripts", "makefile_module_invocations", "direct_fallback_modules"},
        )
        self.assertEqual(
            modules["ops.scripts.release.status_cli"]["path"],
            "ops/scripts/release/status_cli.py",
        )
        self.assertEqual(
            modules["ops.scripts.release.status_cli"]["aliases"],
            ["ops.scripts.release.status_cli"],
        )
        self.assertEqual(
            modules["ops.scripts.release.status_cli"]["sources"],
            ["makefile_module_invocations"],
        )
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(REPO_ROOT / "ops" / "schemas" / "cli-surface-inventory.schema.json"),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
