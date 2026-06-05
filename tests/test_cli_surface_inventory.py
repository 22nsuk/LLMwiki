from __future__ import annotations

import datetime as dt
import json
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


def _write_lifecycle_policy(vault: Path, *, include_status: bool = True) -> None:
    modules = [
        {
            "canonical_module": "ops.scripts.core.sample_cli",
            "path": "ops/scripts/core/sample_cli.py",
            "lifecycle": "report_generator",
            "install_state": "transitional_installed",
            "console_scripts": ["llmwiki-sample"],
            "replacement": "make sample",
            "removal_ready": False,
            "rationale": "sample fixture lifecycle",
        },
        {
            "canonical_module": "ops.scripts.core.retired_report",
            "path": "ops/scripts/core/retired_report.py",
            "lifecycle": "report_generator",
            "install_state": "not_installed",
            "console_scripts": [],
            "replacement": "make retired-report",
            "removal_ready": False,
            "rationale": "sample fixture lifecycle",
        }
    ]
    if include_status:
        modules.append(
            {
                "canonical_module": "ops.scripts.release.status_cli",
                "path": "ops/scripts/release/status_cli.py",
                "lifecycle": "make_only",
                "install_state": "not_installed",
                "console_scripts": [],
                "replacement": "make status",
                "removal_ready": False,
                "rationale": "sample fixture lifecycle",
            }
        )
    (vault / "ops").mkdir(exist_ok=True)
    (vault / "ops" / "script-lifecycle-policy.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/script-lifecycle-policy.schema.json",
                "version": 1,
                "description": "sample lifecycle policy",
                "lifecycle_values": [
                    "public_cli",
                    "make_only",
                    "report_generator",
                    "helper",
                    "test_only",
                    "legacy_delete",
                ],
                "install_state_values": [
                    "public_cli",
                    "transitional_installed",
                    "not_installed",
                ],
                "modules": modules,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class CliSurfaceInventoryTests(unittest.TestCase):
    def test_repository_inventory_has_no_unclassified_lifecycle_modules(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["unclassified_module_count"], 0)
        self.assertEqual(
            report["summary"]["pyproject_script_count"],
            report["summary"]["public_cli_module_count"]
            + report["summary"]["transitional_installed_module_count"],
        )
        self.assertEqual(
            report["summary"]["installed_non_public_module_count"],
            report["summary"]["transitional_installed_module_count"],
        )
        self.assertEqual(report["unclassified_modules"], [])
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(REPO_ROOT / "ops" / "schemas" / "cli-surface-inventory.schema.json"),
            ),
            [],
        )

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
                "retired-report:\n\tpython -m ops.scripts.core.retired_report --help\n"
                "status:\n\tpython -m ops.scripts.release.status_cli --vault .\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "core" / "sample_cli.py").write_text(
                "if __package__ in (None, \"\"):  # pragma: no cover - direct script fallback\n"
                "    pass\n"
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "core" / "retired_report.py").write_text(
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
                '{"surfaces":['
                '{"path":"ops/scripts/core/sample_cli.py","direct_fallback_eligible":true},'
                '{"path":"ops/scripts/core/retired_report.py","direct_fallback_eligible":true}'
                "]}\n",
                encoding="utf-8",
            )
            _write_lifecycle_policy(vault)

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["module_count"], 3)
        self.assertEqual(report["summary"]["unclassified_module_count"], 0)
        self.assertEqual(report["summary"]["transitional_installed_module_count"], 1)
        modules = {item["module"]: item for item in report["modules"]}
        self.assertEqual(modules["ops.scripts.core.sample_cli"]["path"], "ops/scripts/core/sample_cli.py")
        self.assertEqual(modules["ops.scripts.core.sample_cli"]["lifecycle"], "report_generator")
        self.assertEqual(modules["ops.scripts.core.sample_cli"]["install_state"], "transitional_installed")
        self.assertEqual(modules["ops.scripts.core.sample_cli"]["console_scripts"], ["llmwiki-sample"])
        self.assertEqual(modules["ops.scripts.core.sample_cli"]["make_targets"], ["sample"])
        self.assertTrue(modules["ops.scripts.core.sample_cli"]["direct_fallback"])
        self.assertEqual(
            set(modules["ops.scripts.core.sample_cli"]["aliases"]),
            {"ops.scripts.core.sample_cli", "ops.scripts.sample_cli"},
        )
        self.assertEqual(
            set(modules["ops.scripts.core.sample_cli"]["sources"]),
            {"pyproject_scripts", "makefile_module_invocations", "direct_fallback_modules"},
        )
        self.assertEqual(modules["ops.scripts.core.retired_report"]["lifecycle"], "report_generator")
        self.assertEqual(modules["ops.scripts.core.retired_report"]["install_state"], "not_installed")
        self.assertEqual(modules["ops.scripts.core.retired_report"]["console_scripts"], [])
        self.assertEqual(modules["ops.scripts.core.retired_report"]["make_targets"], ["retired-report"])
        self.assertTrue(modules["ops.scripts.core.retired_report"]["direct_fallback"])
        self.assertEqual(
            set(modules["ops.scripts.core.retired_report"]["sources"]),
            {"makefile_module_invocations", "direct_fallback_modules"},
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
        self.assertEqual(modules["ops.scripts.release.status_cli"]["lifecycle"], "make_only")
        self.assertEqual(modules["ops.scripts.release.status_cli"]["install_state"], "not_installed")
        self.assertEqual(modules["ops.scripts.release.status_cli"]["make_targets"], ["status"])
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(REPO_ROOT / "ops" / "schemas" / "cli-surface-inventory.schema.json"),
            ),
            [],
        )

    def test_inventory_fails_when_lifecycle_policy_omits_surface_module(self) -> None:
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
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "release" / "status_cli.py").write_text(
                "def main(): pass\n",
                encoding="utf-8",
            )
            (vault / "ops" / "script-output-surfaces.json").write_text(
                '{"surfaces":[]}\n',
                encoding="utf-8",
            )
            _write_lifecycle_policy(vault, include_status=False)

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["unclassified_module_count"], 1)
        self.assertEqual(
            report["unclassified_modules"],
            ["ops.scripts.release.status_cli"],
        )


if __name__ == "__main__":
    unittest.main()
