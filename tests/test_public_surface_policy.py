from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.export_public_repo import export_public_repo, should_export_public
from ops.scripts.public_surface_policy import (
    PUBLIC_EXCLUDED_SEGMENTS,
    PUBLIC_GITIGNORE_END,
    PUBLIC_GITIGNORE_START,
    PUBLIC_INCLUDED_REPORT_FILES,
    render_public_gitignore_block,
)

pytestmark = pytest.mark.public


class PublicSurfacePolicyTests(unittest.TestCase):
    def test_gitignore_public_block_matches_policy(self) -> None:
        gitignore_text = Path(".gitignore").read_text(encoding="utf-8")
        start = gitignore_text.index(PUBLIC_GITIGNORE_START)
        end = gitignore_text.index(PUBLIC_GITIGNORE_END) + len(PUBLIC_GITIGNORE_END)
        block = gitignore_text[start:end] + "\n"
        self.assertEqual(block, render_public_gitignore_block())

    def test_root_gitignore_and_export_match_for_sample_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            sample_files = {
                "AGENTS.md": "# Agents\n",
                "AGENTS.local.md": "# Local Agents\n",
                "ARCHITECTURE.md": "# Architecture\n",
                "CONTRIBUTING.md": "# Contributing\n",
                "LICENSE": "Apache License\n",
                "README.md": "# Readme\n",
                "SECURITY.md": "# Security\n",
                "THIRD_PARTY_NOTICES.md": "# Notices\n",
                "docs/README.md": "# Docs\n",
                "docs/development.md": "# Development\n",
                "Makefile": "all:\n\t@true\n",
                "pyproject.toml": "[build-system]\nrequires = ['setuptools']\n",
                "requirements.txt": "PyYAML\n",
                "requirements-dev.txt": "-r requirements.txt\npytest\n",
                "pytest.ini": "[pytest]\n",
                "uv.lock": "version = 1\n",
                ".gitignore": Path(".gitignore").read_text(encoding="utf-8"),
                ".gitattributes": Path(".gitattributes").read_text(encoding="utf-8"),
                ".github/CODEOWNERS": "* @example\n",
                ".github/dependabot.yml": "version: 2\nupdates: []\n",
                ".github/pull_request_template.md": "## Summary\n",
                ".github/workflows/ci.yml": "name: CI\n",
                ".codex/agents/worker.toml": "name = 'worker'\n",
                "mk/core.mk": "all:\n\t@true\n",
                "ops/scripts/example.py": "print('ok')\n",
                "ops/templates/codebase-memory-mcp.cbmignore": "raw/\n",
                "ops/.codebase-memory/graph.db.zst": "binary\n",
                "ops/README.md": "# ops\n",
                "ops/manifest.json": "{}\n",
                "ops/raw-registry.json": "{}\n",
                "ops/reports/example.json": "{}\n",
                "ops/reports/goal-worktree-guard.json": "{}\n",
                "ops/reports/release-workflow-order-guard.json": "{}\n",
                "ops/reports/workflow-dependency-planner.json": "{}\n",
                "tests/test_example.py": "def test_ok():\n    assert True\n",
                "tools/helper.py": "print('helper')\n",
                "raw/source.pdf": "pdf\n",
                "runs/README.md": "# runs\n",
                "wiki/.gitkeep": "",
                "system/system-index.md": "# system\n",
                ".obsidian/app.json": "{}\n",
                "tmp/public.txt": "tmp\n",
            }

            for rel_path, content in sample_files.items():
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            subprocess.run(["git", "init", "-q"], cwd=vault, check=True)

            status = subprocess.run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=vault,
                text=True,
                capture_output=True,
                check=True,
            )
            tracked = {
                line[3:]
                for line in status.stdout.splitlines()
                if line.startswith("?? ")
            }

            export_dir = Path(temp_dir) / "public-repo"
            manifest = export_public_repo(vault, export_dir)
            exported = set(manifest["files"])

            self.assertEqual(tracked, exported)
            self.assertTrue(set(PUBLIC_INCLUDED_REPORT_FILES).issubset(exported))
            self.assertIn("docs/README.md", exported)
            self.assertIn("docs/development.md", tracked)
            self.assertIn("ops/templates/codebase-memory-mcp.cbmignore", exported)
            self.assertNotIn("ops/reports/example.json", exported)
            self.assertNotIn("ops/.codebase-memory/graph.db.zst", exported)
            self.assertNotIn("ops/.codebase-memory/graph.db.zst", tracked)

    def test_codebase_memory_graph_artifacts_are_not_public_surface(self) -> None:
        self.assertIn(".codebase-memory", PUBLIC_EXCLUDED_SEGMENTS)
        self.assertFalse(should_export_public(".codebase-memory/graph.db.zst"))
        self.assertFalse(should_export_public("ops/.codebase-memory/graph.db.zst"))
        self.assertTrue(should_export_public("ops/templates/codebase-memory-mcp.cbmignore"))

    def test_generated_report_contracts_skip_full_vault_checks_in_public_export(self) -> None:
        text = Path("tests/test_generated_report_contracts.py").read_text(encoding="utf-8")

        self.assertIn(
            "PUBLIC_EXPORT_MANIFEST_PATH.exists() and not ARTIFACT_FRESHNESS_REPORT_PATH.exists()",
            text,
        )
        self.assertNotIn('not (REPO_ROOT / "ops" / "reports").exists()', text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
