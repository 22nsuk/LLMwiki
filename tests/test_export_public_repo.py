from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.public.cbm_public_export import (
    CBM_MANIFEST_NAME,
    CbmPublicExportError,
    build_cbm_public_export,
    format_cbm_export_summary,
    validate_cbm_local_paths,
)
from ops.scripts.public.export_public_repo import (
    DEFAULT_PUBLIC_OUT,
    build_parser,
    export_public_repo,
)

pytestmark = pytest.mark.public


class ExportPublicRepoTests(unittest.TestCase):
    def test_export_public_repo_cli_defaults_to_system_tempdir(self) -> None:
        parsed = build_parser().parse_args([])

        self.assertEqual(parsed.out, DEFAULT_PUBLIC_OUT)
        self.assertTrue(Path(DEFAULT_PUBLIC_OUT).is_absolute())
        self.assertEqual(Path(DEFAULT_PUBLIC_OUT).name, "llm-wiki-public-repo")

    def test_export_public_repo_copies_only_public_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            (vault / "AGENTS.local.md").write_text("# Local Agents\n", encoding="utf-8")
            (vault / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
            (vault / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache License\n", encoding="utf-8")
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
            (vault / "THIRD_PARTY_NOTICES.md").write_text("# Third-Party Notices\n", encoding="utf-8")
            (vault / "docs").mkdir()
            (vault / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
            (vault / "docs" / "development.md").write_text("# Development\n", encoding="utf-8")
            (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            (vault / "pyproject.toml").write_text("[build-system]\nrequires = ['setuptools']\n", encoding="utf-8")
            (vault / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
            (vault / "requirements-dev.txt").write_text("-r requirements.txt\npytest\n", encoding="utf-8")
            (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            (vault / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (vault / ".gitignore").write_text("tmp/\n", encoding="utf-8")
            (vault / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
            (vault / ".github" / "workflows").mkdir(parents=True)
            (vault / ".github" / "CODEOWNERS").write_text("* @example\n", encoding="utf-8")
            (vault / ".github" / "dependabot.yml").write_text(
                "version: 2\nupdates: []\n", encoding="utf-8"
            )
            (vault / ".github" / "pull_request_template.md").write_text(
                "## Summary\n", encoding="utf-8"
            )
            (vault / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
            (vault / "tests").mkdir()
            (vault / "tests" / "test_example.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (vault / "tools").mkdir()
            (vault / "tools" / "helper.py").write_text("print('helper')\n", encoding="utf-8")
            (vault / ".codex" / "agents").mkdir(parents=True)
            (vault / ".codex" / "agents" / "worker.toml").write_text("name = 'worker'\n", encoding="utf-8")
            (vault / "raw").mkdir()
            (vault / "raw" / "source.pdf").write_text("pdf", encoding="utf-8")
            (vault / "wiki").mkdir()
            (vault / "wiki" / "index.md").write_text("# index\n", encoding="utf-8")
            (vault / "system").mkdir()
            (vault / "system" / "system-index.md").write_text("# system\n", encoding="utf-8")
            (vault / "runs").mkdir()
            (vault / "runs" / "README.md").write_text("# runs\n", encoding="utf-8")
            (vault / "external-reports").mkdir()
            (vault / "external-reports" / "report.pdf").write_text("pdf", encoding="utf-8")
            (vault / "ops" / "raw-registry.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports").mkdir()
            (vault / "ops" / "reports" / "artifact.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports" / "goal-worktree-guard.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports" / "release-workflow-order-guard.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports" / "workflow-dependency-planner.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "operator").mkdir()
            (vault / "ops" / "operator" / "operator-release-summary.json").write_text(
                "{}",
                encoding="utf-8",
            )

            public_dir = Path(temp_dir) / "public"
            manifest = export_public_repo(vault, public_dir)

            self.assertIn("AGENTS.md", manifest["files"])
            self.assertIn("ARCHITECTURE.md", manifest["files"])
            self.assertIn("CONTRIBUTING.md", manifest["files"])
            self.assertIn("LICENSE", manifest["files"])
            self.assertIn("README.md", manifest["files"])
            self.assertIn("SECURITY.md", manifest["files"])
            self.assertIn("THIRD_PARTY_NOTICES.md", manifest["files"])
            self.assertIn("docs/README.md", manifest["files"])
            self.assertIn("docs/development.md", manifest["files"])
            self.assertIn("pyproject.toml", manifest["files"])
            self.assertIn("uv.lock", manifest["files"])
            self.assertNotIn("requirements.txt", manifest["files"])
            self.assertNotIn("requirements-dev.txt", manifest["files"])
            self.assertIn(".github/CODEOWNERS", manifest["files"])
            self.assertIn(".github/dependabot.yml", manifest["files"])
            self.assertIn(".github/pull_request_template.md", manifest["files"])
            self.assertIn(".github/workflows/ci.yml", manifest["files"])
            self.assertIn(".codex/agents/worker.toml", manifest["files"])
            self.assertIn("ops/scripts/example.py", manifest["files"])
            self.assertIn("tests/test_example.py", manifest["files"])
            self.assertIn("tools/helper.py", manifest["files"])
            self.assertNotIn("raw/source.pdf", manifest["files"])
            self.assertNotIn("wiki/index.md", manifest["files"])
            self.assertNotIn("system/system-index.md", manifest["files"])
            self.assertNotIn("runs/README.md", manifest["files"])
            self.assertNotIn("AGENTS.local.md", manifest["files"])
            self.assertNotIn("ops/raw-registry.json", manifest["files"])
            self.assertNotIn("ops/operator/operator-release-summary.json", manifest["files"])
            self.assertNotIn("ops/reports/artifact.json", manifest["files"])
            self.assertNotIn("ops/reports/goal-worktree-guard.json", manifest["files"])
            self.assertNotIn("ops/reports/release-workflow-order-guard.json", manifest["files"])
            self.assertNotIn("ops/reports/workflow-dependency-planner.json", manifest["files"])
            self.assertEqual(manifest["included_report_files"], [])
            self.assertEqual(manifest["source_vault"], ".")
            self.assertEqual(manifest["output_dir"], ".")
            exported_file_count = len([path for path in public_dir.rglob("*") if path.is_file()])
            self.assertEqual(manifest["source_file_count"], len(manifest["files"]))
            self.assertEqual(manifest["file_count"], exported_file_count)
            self.assertEqual(manifest["manifest_file"], "PUBLIC-EXPORT-MANIFEST.json")
            self.assertTrue((public_dir / "PUBLIC-EXPORT-MANIFEST.json").exists())
            self.assertTrue((public_dir / ".codex" / "agents" / "worker.toml").exists())

    def test_cbm_public_export_prunes_generated_reports_and_writes_boundary_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            for rel_path, content in {
                "AGENTS.md": "# Agents\n",
                "ARCHITECTURE.md": "# Architecture\n",
                "CONTRIBUTING.md": "# Contributing\n",
                "LICENSE": "Apache License\n",
                "README.md": "# Readme\n",
                "SECURITY.md": "# Security\n",
                "THIRD_PARTY_NOTICES.md": "# Notices\n",
                "docs/README.md": "# Docs\n",
                "docs/codebase-memory-mcp.md": "# CBM\n",
                "Makefile": "all:\n\t@true\n",
                "pyproject.toml": "[build-system]\nrequires = ['setuptools']\n",
                "requirements.txt": "PyYAML\n",
                "requirements-dev.txt": "-r requirements.txt\npytest\n",
                "pytest.ini": "[pytest]\n",
                "uv.lock": "version = 1\n",
                ".gitignore": "tmp/\n",
                ".gitattributes": "* text=auto\n",
                "ops/scripts/example.py": "print('ok')\n",
                "ops/templates/codebase-memory-mcp.cbmignore": "raw/\nops/operator/\nops/reports/\n.codebase-memory/\n",
                "ops/operator/operator-release-summary.json": "{}\n",
                "ops/reports/goal-worktree-guard.json": "{}\n",
                "ops/reports/release-workflow-order-guard.json": "{}\n",
                "ops/reports/workflow-dependency-planner.json": "{}\n",
                "ops/reports/extra.json": "{}\n",
                "tests/test_example.py": "def test_ok():\n    assert True\n",
            }.items():
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            out_dir = Path(temp_dir) / "cbm-public"
            template = vault / "ops" / "templates" / "codebase-memory-mcp.cbmignore"
            manifest = build_cbm_public_export(vault, out_dir, cbmignore_template=template)

            self.assertEqual(manifest["manifest_file"], CBM_MANIFEST_NAME)
            self.assertEqual(manifest["index_policy"], "codebase_memory_mcp_public_export")
            self.assertTrue((out_dir / ".cbmignore").exists())
            self.assertTrue((out_dir / CBM_MANIFEST_NAME).exists())
            self.assertFalse((out_dir / "PUBLIC-EXPORT-MANIFEST.json").exists())
            self.assertFalse((out_dir / "ops" / "reports").exists())
            self.assertIn(".cbmignore", manifest["files"])
            self.assertIn("docs/codebase-memory-mcp.md", manifest["files"])
            self.assertIn("ops/templates/codebase-memory-mcp.cbmignore", manifest["files"])
            self.assertNotIn("ops/operator/operator-release-summary.json", manifest["files"])
            self.assertNotIn("ops/reports/goal-worktree-guard.json", manifest["files"])
            self.assertNotIn("ops/reports/release-workflow-order-guard.json", manifest["files"])
            self.assertNotIn("ops/reports/workflow-dependency-planner.json", manifest["files"])
            exported_file_count = len([path for path in out_dir.rglob("*") if path.is_file()])
            self.assertEqual(manifest["file_count"], exported_file_count)
            summary = format_cbm_export_summary(manifest)
            self.assertIn("cbm_public_export=ok", summary)
            self.assertIn("manifest=CBM-EXPORT-MANIFEST.json", summary)
            self.assertIn("source_public_files=", summary)
            self.assertIn("index_files=", summary)
            self.assertIn("total_files=", summary)
            self.assertIn("pruned=ops/operator,ops/reports,PUBLIC-EXPORT-MANIFEST.json", summary)
            self.assertNotIn("tests/test_example.py", summary)

    def test_cbm_local_path_guard_rejects_repo_overlapping_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "vault"
            cache_root = root / "cache"
            vault.mkdir()
            cache_root.mkdir()

            validate_cbm_local_paths(
                vault,
                cache_root / "public-surface",
                cache_dir=cache_root / "index",
                cache_root=cache_root,
            )

            for public_out in (vault, vault / "docs", root):
                with self.subTest(public_out=str(public_out)), self.assertRaisesRegex(
                    CbmPublicExportError,
                    "CBM_PUBLIC_OUT|overlaps vault",
                ):
                    validate_cbm_local_paths(
                        vault,
                        public_out,
                        cache_dir=cache_root / "index",
                        cache_root=cache_root,
                    )

            with self.assertRaisesRegex(CbmPublicExportError, "CBM_CACHE_DIR"):
                validate_cbm_local_paths(
                    vault,
                    cache_root / "public-surface",
                    cache_dir=vault / "tmp" / "cbm-index",
                    cache_root=cache_root,
                )

    def test_export_public_repo_can_reuse_same_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache License\n", encoding="utf-8")
            (vault / "THIRD_PARTY_NOTICES.md").write_text("# Third-Party Notices\n", encoding="utf-8")
            (vault / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
            (vault / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
            (vault / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
            (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            (vault / "pyproject.toml").write_text("[build-system]\nrequires = ['setuptools']\n", encoding="utf-8")
            (vault / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
            (vault / "requirements-dev.txt").write_text("-r requirements.txt\npytest\n", encoding="utf-8")
            (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            (vault / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (vault / ".gitignore").write_text("tmp/\n", encoding="utf-8")
            (vault / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
            (vault / ".github" / "workflows").mkdir(parents=True)
            (vault / ".github" / "dependabot.yml").write_text(
                "version: 2\nupdates: []\n", encoding="utf-8"
            )
            (vault / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
            (vault / ".codex" / "agents").mkdir(parents=True)
            (vault / ".codex" / "agents" / "worker.toml").write_text("name = 'worker'\n", encoding="utf-8")
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
            (vault / "tests").mkdir()
            (vault / "tests" / "test_example.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (vault / "tmp").mkdir()
            (vault / "tmp" / "ignore-me.txt").write_text("ignore\n", encoding="utf-8")

            public_dir = Path(temp_dir) / "public-repo"
            first_manifest = export_public_repo(vault, public_dir)
            self.assertIn("README.md", first_manifest["files"])
            (public_dir / "stale.txt").write_text("stale\n", encoding="utf-8")

            second_manifest = export_public_repo(vault, public_dir)

            self.assertIn("README.md", second_manifest["files"])
            self.assertFalse((public_dir / "stale.txt").exists())
            self.assertTrue((public_dir / "LICENSE").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
