from __future__ import annotations

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.wiki_lint import lint
from tests.minimal_vault_runtime import seed_minimal_vault, set_policy_value

pytestmark = pytest.mark.slow


def _fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
    )


def _issue_types(report: dict) -> tuple[set[str], set[str]]:
    return (
        {issue["type"] for issue in report["errors"]},
        {issue["type"] for issue in report["warnings"]},
    )


class WikiLintRuntimeTest(unittest.TestCase):
    def test_lint_passes_on_minimal_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = lint(vault, context=_fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["stats"]["error_count"], 0)
            self.assertEqual(report["stats"]["warning_count"], 0)

    def test_release_archive_profile_accepts_public_source_package_without_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            for surface in ("raw", "wiki", "system"):
                shutil.rmtree(vault / surface)

            strict_report = lint(vault, context=_fixed_context())
            release_report = lint(
                vault,
                context=_fixed_context(),
                release_archive_profile=True,
            )

            self.assertEqual(strict_report["status"], "fail")
            self.assertEqual(release_report["status"], "pass")
            self.assertEqual(release_report["stats"]["page_count"], 0)
            self.assertEqual(release_report["stats"]["review_candidate_count"], 0)

    def test_release_archive_profile_still_reports_public_function_budget_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            for surface in ("raw", "wiki", "system"):
                shutil.rmtree(vault / surface)
            long_function = vault / "ops" / "scripts" / "budget_sample.py"
            long_function.parent.mkdir(parents=True, exist_ok=True)
            long_function.write_text(
                "def release_archive_smoke_only():\n" + ("    value = 1\n" * 220),
                encoding="utf-8",
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "runtime", "lines"),
                3,
            )

            release_report = lint(
                vault,
                context=_fixed_context(),
                release_archive_profile=True,
            )
            candidates = [
                item
                for item in release_report["review_candidates"]
                if item["type"] == "python_function_budget_candidate"
            ]

            self.assertEqual(release_report["status"], "pass")
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["page"], "ops/scripts/budget_sample.py")

    def test_lint_reports_duplicate_page_stems_as_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            duplicate_path = vault / "system" / "source--fake.md"
            duplicate_path.write_text(
                """---
title: "Duplicate"
page_type: "source"
corpus: "system"
aliases:
  - "source--fake"
tags:
  - "corpus/system"
  - "type/source"
---

# Duplicate
""",
                encoding="utf-8",
            )

            report = lint(vault)
            error_types, _ = _issue_types(report)

            self.assertEqual(report["status"], "fail")
            self.assertIn("duplicate_page_stem", error_types)

    def test_lint_surfaces_frontmatter_metadata_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            source_path = vault / "wiki" / "source--fake.md"
            source_path.write_text(
                source_path.read_text(encoding="utf-8").replace('  - "source--fake"\n', '  - "alias-only"\n'),
                encoding="utf-8",
            )

            report = lint(vault)
            _, warning_types = _issue_types(report)

            self.assertEqual(report["status"], "warn")
            self.assertIn("frontmatter_alias_missing_stem", warning_types)

    def test_lint_warns_for_frontmatter_fields_before_required_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            source_path = vault / "wiki" / "source--fake.md"
            source_path.write_text(
                source_path.read_text(encoding="utf-8").replace('created: "2026-04-15"\n', ""),
                encoding="utf-8",
            )

            report = lint(vault)
            _, warning_types = _issue_types(report)
            warning = next(
                issue
                for issue in report["warnings"]
                if issue["type"] == "frontmatter_field_pending_required"
            )

            self.assertEqual(report["status"], "warn")
            self.assertIn("frontmatter_field_pending_required", warning_types)
            self.assertEqual(warning["detail"]["missing_field"], "created")
            self.assertEqual(warning["detail"]["frontmatter_contract_version"], 1)

    def test_lint_emits_python_function_budget_review_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            runtime_target = vault / "ops" / "scripts" / "budget_sample.py"
            test_target = vault / "tests" / "test_budget_sample.py"
            runtime_target.parent.mkdir(parents=True, exist_ok=True)
            test_target.parent.mkdir(parents=True, exist_ok=True)

            runtime_target.write_text(
                "def runtime_target(a, b):\n"
                "    if a:\n"
                "        return b\n"
                "    return a\n",
                encoding="utf-8",
            )
            test_target.write_text(
                "def test_target(value):\n"
                "    if value:\n"
                "        return True\n"
                "    return False\n",
                encoding="utf-8",
            )

            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "runtime", "lines"),
                3,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "runtime", "params"),
                1,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "runtime", "branches"),
                0,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "tests", "lines"),
                3,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "tests", "params"),
                0,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "python_function_review", "profiles", "tests", "branches"),
                0,
            )

            report = lint(vault, context=_fixed_context())
            candidates = [
                item
                for item in report["review_candidates"]
                if item["type"] == "python_function_budget_candidate"
            ]

            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0]["page"], "ops/scripts/budget_sample.py")
            self.assertEqual(candidates[0]["profile"], "runtime")
            self.assertEqual(candidates[0]["symbol"], "runtime_target")
            self.assertEqual(
                candidates[0]["triggered_budgets"],
                ["function_lines", "parameter_count", "branch_node_count"],
            )
            self.assertEqual(candidates[1]["page"], "tests/test_budget_sample.py")
            self.assertEqual(candidates[1]["profile"], "tests")
            self.assertEqual(candidates[1]["symbol"], "test_target")
            self.assertEqual(
                candidates[1]["triggered_budgets"],
                ["function_lines", "parameter_count", "branch_node_count"],
            )


if __name__ == "__main__":
    unittest.main()
