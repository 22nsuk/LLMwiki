from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.eval.doc_graph_integrity import ROOT_DOCS
from ops.scripts.public.export_public_repo import (
    export_public_repo,
    should_export_public,
)
from ops.scripts.public.public_surface_policy import (
    PUBLIC_EXCLUDED_LOCAL_FILE_PATTERNS,
    PUBLIC_EXCLUDED_SEGMENTS,
    PUBLIC_GITIGNORE_END,
    PUBLIC_GITIGNORE_START,
    PUBLIC_GITIGNORE_TEMPLATE,
    PUBLIC_INCLUDE_FILES,
    PUBLIC_INCLUDE_PREFIXES,
    PUBLIC_INCLUDED_REPORT_FILES,
    PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS,
    find_public_local_path_leaks,
    render_public_gitignore_block,
)

pytestmark = pytest.mark.public
REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_check_ignored(repo: Path, paths: tuple[str, ...]) -> set[str]:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=repo,
        input="".join(f"{path}\n" for path in paths),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(f"git check-ignore failed: {result.stderr}")
    return set(result.stdout.splitlines())


class PublicSurfacePolicyTests(unittest.TestCase):
    def test_root_docs_are_included_in_public_export_allowlist(self) -> None:
        missing = sorted(set(ROOT_DOCS) - set(PUBLIC_INCLUDE_FILES))
        self.assertEqual(
            missing, [], msg=f"ROOT_DOCS missing from PUBLIC_INCLUDE_FILES: {missing}"
        )

    def test_public_mirror_gitignore_template_matches_policy(self) -> None:
        gitignore_text = Path(PUBLIC_GITIGNORE_TEMPLATE).read_text(encoding="utf-8")
        start = gitignore_text.index(PUBLIC_GITIGNORE_START)
        end = gitignore_text.index(PUBLIC_GITIGNORE_END) + len(PUBLIC_GITIGNORE_END)
        block = gitignore_text[start:end] + "\n"
        self.assertEqual(block, render_public_gitignore_block())

    def test_public_mirror_gitignore_reblocks_local_state_after_allowlist(self) -> None:
        block = render_public_gitignore_block()

        for segment in PUBLIC_EXCLUDED_SEGMENTS:
            self.assertIn(segment, block)
        for pattern in PUBLIC_EXCLUDED_LOCAL_FILE_PATTERNS:
            self.assertIn(pattern, block)

    def test_public_mirror_gitignore_and_export_policy_reblock_allowlist_local_state(
        self,
    ) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for public mirror .gitignore probes")

        ignored_paths = (
            "ops/reports/example.json",
            "ops/reports/nested/example.json",
            "ops/operator/summary.json",
            "ops/operator/nested/summary.json",
            "ops/manifest.json",
            "ops/raw-registry.json",
            "docs/__pycache__/x.pyc",
            "ops/.pytest_cache/v/cache",
            "tests/.mypy_cache/a",
            "tools/.ruff_cache/a",
            "ops/.codebase-memory/graph.db.zst",
            "ops/.cache/tool/state",
            "docs/.idea/workspace.xml",
            "docs/.vscode/settings.json",
            "tools/.venv/bin/python",
            "tests/.hypothesis/examples/x",
            "tools/helper.pyc",
            "tools/helper.pyo",
            "tools/native.pyd",
            "docs/.coverage",
            "docs/.coverage.worker",
            "mk/.DS_Store",
            "tests/Thumbs.db",
            "tools/notes.swp",
            "tools/notes.swo",
            "tools/notes~",
            "docs/sub/.git",
            "ops/nested/.git",
            "tools/worktree/.git",
            "docs/.coverage/data",
            "tools/helper.pyc/output",
            "ops/.coverage.worker/cache",
            "tests/foo.pyc/bar",
        )
        public_paths = (
            "docs/development.md",
            "ops/scripts/example.py",
            "tests/test_example.py",
            "tools/helper.py",
            "mk/public.mk",
            ".agents/skills/example-skill/SKILL.md",
            ".codex/agents/worker.toml",
            ".github/workflows/ci.yml",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / ".gitignore").write_text(
                render_public_gitignore_block(), encoding="utf-8"
            )

            self.assertEqual(
                _git_check_ignored(repo, ignored_paths), set(ignored_paths)
            )
            self.assertEqual(_git_check_ignored(repo, public_paths), set())

        for rel_path in ignored_paths:
            self.assertFalse(should_export_public(rel_path), rel_path)
        for rel_path in public_paths:
            self.assertTrue(should_export_public(rel_path), rel_path)

    def test_root_gitignore_is_full_vault_hygiene_not_public_policy(self) -> None:
        gitignore_text = Path(".gitignore").read_text(encoding="utf-8")

        if Path("PUBLIC-EXPORT-MANIFEST.json").exists():
            self.assertIn(PUBLIC_GITIGNORE_START, gitignore_text)
            self.assertIn("ops/reports/*", gitignore_text)
            self.assertIn("ops/operator/*", gitignore_text)
            return

        self.assertNotIn(PUBLIC_GITIGNORE_START, gitignore_text)
        self.assertIn("ops/reports/", gitignore_text)
        self.assertIn("ops/operator/", gitignore_text)
        self.assertIn("raw/", gitignore_text)
        self.assertIn("external-reports/", gitignore_text)

    def test_root_gitignore_ignores_agent_state_but_tracks_repo_skills(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for root .gitignore probes")

        ignored_paths = (
            ".agents/session.json",
            ".agents/private/state.json",
        )
        repo_skill_paths = (
            ".agents/skills/example-skill/SKILL.md",
            ".agents/skills/example-skill/agents/openai.yaml",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / ".gitignore").write_text(
                Path(".gitignore").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            self.assertEqual(
                _git_check_ignored(repo, ignored_paths), set(ignored_paths)
            )
            self.assertEqual(_git_check_ignored(repo, repo_skill_paths), set())

    def test_public_export_uses_policy_and_generated_gitignore_for_sample_vault(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            sample_files = {
                "AGENTS.md": "# Agents\n",
                "AGENTS.local.md": "# Local Agents\n",
                "ARCHITECTURE.md": "# Architecture\n",
                "CHANGELOG.md": "# Changelog\n",
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
                ".agents/skills/example-skill/SKILL.md": "# Skill\n",
                ".agents/skills/example-skill/agents/openai.yaml": "interface: {}\n",
                ".codex/agents/worker.toml": "name = 'worker'\n",
                "mk/core.mk": "all:\n\t@true\n",
                "ops/scripts/example.py": "print('ok')\n",
                "ops/.codebase-memory/graph.db.zst": "binary\n",
                "ops/README.md": "# ops\n",
                "ops/manifest.json": "{}\n",
                "ops/raw-registry.json": "{}\n",
                "ops/operator/operator-release-summary.json": "{}\n",
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
                "external-reports/active-review.md": "# local review\n",
                ".obsidian/app.json": "{}\n",
                "tmp/public.txt": "tmp\n",
            }

            for rel_path, content in sample_files.items():
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            export_dir = Path(temp_dir) / "public-repo"
            manifest = export_public_repo(vault, export_dir)
            exported = set(manifest["files"])
            expected_exported = {
                path for path in sample_files if should_export_public(path)
            }

            self.assertEqual(exported, expected_exported)
            self.assertEqual(PUBLIC_INCLUDED_REPORT_FILES, ())
            self.assertIn("docs/README.md", exported)
            self.assertIn("docs/development.md", exported)
            self.assertIn(
                ".agents/skills/example-skill/SKILL.md",
                exported,
            )
            self.assertNotIn("requirements.txt", exported)
            self.assertNotIn("requirements-dev.txt", exported)
            self.assertNotIn("ops/operator/operator-release-summary.json", exported)
            self.assertNotIn("ops/reports/example.json", exported)
            self.assertNotIn("ops/reports/goal-worktree-guard.json", exported)
            self.assertNotIn("ops/reports/release-workflow-order-guard.json", exported)
            self.assertNotIn("ops/reports/workflow-dependency-planner.json", exported)
            self.assertNotIn("external-reports/active-review.md", exported)
            self.assertNotIn("ops/.codebase-memory/graph.db.zst", exported)
            self.assertEqual(
                (export_dir / ".gitignore").read_text(encoding="utf-8"),
                render_public_gitignore_block(),
            )

    def test_local_graph_artifacts_are_not_public_surface(self) -> None:
        self.assertIn(".codebase-memory", PUBLIC_EXCLUDED_SEGMENTS)
        self.assertFalse(should_export_public(".codebase-memory/graph.db.zst"))
        self.assertFalse(should_export_public("ops/.codebase-memory/graph.db.zst"))


@pytest.mark.parametrize(
    "marker",
    [
        "/home/alice/work/repo",
        "/mnt/c/Users/alice/repo",
        "/workspace/LLMwiki/repo",
        "/Users/alice/work/repo",
        "/var/folders/ab/tmp/repo",
        "/private/var/folders/ab/tmp/repo",
        "/" + "tmp/run-123-workspace/vault/wiki/page.md",
        "/" + "var/tmp/run-123/vault",
        "/" + "private/tmp/run-123/vault",
        "workspace:/home/alice/work/repo",
        "source:/Users/alice/work/repo",
        "file:///" + "home/alice/work/repo",
        "file://localhost/" + "home/alice/work/repo",
        "vscode://file/" + "home/alice/work/repo",
        "file:///" + "C" + ":" + "/" + "Users/alice/repo",
        "vscode://file/" + "C" + ":" + "/" + "Users/alice/repo",
        r"C:\Users\alice\repo",
        r"C:\USERS\alice\repo",
        r"c:\temp\repo",
        "d:/a/project",
        "d" + ":/n",
        r"\\WSL$\Ubuntu\home\alice\repo",
        r"\USERS\alice\repo",
    ],
)
def test_public_local_path_guard_recognizes_common_local_roots(marker: str) -> None:
    assert find_public_local_path_leaks(marker)


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com/docs",
        "https://example.com/home/alice",
        "https://example.com/workspace/LLMwiki",
        "https://example.com/Users/alice",
        "https://example.com/private/var/folders/ab/tmp/repo",
        "https://example.com/tmp/artifact",
        "https://example.com/var/tmp/artifact",
        "https://example.com/private/tmp/artifact",
        "vscode-remote://ssh-remote+example/home/alice/repo",
        "docs.example/home/alice",
        "GET /users/{id}",
        "/users/me",
        r"    if a:\n",
        r"        if b:\n",
    ],
)
def test_public_local_path_guard_does_not_treat_routes_or_urls_as_local_paths(
    text: str,
) -> None:
    assert find_public_local_path_leaks(text) == ()


def test_public_local_path_guard_applies_url_context_to_current_source_root() -> None:
    source_root = "/" + "workspace/LLMwiki"

    assert (
        find_public_local_path_leaks(
            "https://example.com" + source_root,
            source_root=source_root,
        )
        == ()
    )
    assert find_public_local_path_leaks(
        "source:" + source_root + "/private",
        source_root=source_root,
    )


def test_intentional_local_path_literal_does_not_exempt_longer_prefix() -> None:
    rel_path = "tests/test_public_check_summary.py"
    allowed_path = "/" + "workspace/example"

    assert (
        find_public_local_path_leaks(
            f'FIXTURE_ROOT = "{allowed_path}"\n',
            rel_path=rel_path,
        )
        == ()
    )
    assert find_public_local_path_leaks(
        f'DEV_ROOT = "{allowed_path}-secret/private"\n',
        rel_path=rel_path,
    )


def test_intentional_local_path_literals_are_exact_public_source_exemptions() -> None:
    missing_or_private = [
        path
        for path in sorted(PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS)
        if not (REPO_ROOT / path).is_file() or not should_export_public(path)
    ]

    assert missing_or_private == []

    candidate_paths = {
        REPO_ROOT / path
        for path in PUBLIC_INCLUDE_FILES
        if (REPO_ROOT / path).is_file()
    }
    for prefix in PUBLIC_INCLUDE_PREFIXES:
        root = REPO_ROOT / prefix
        if root.is_dir():
            candidate_paths.update(path for path in root.rglob("*") if path.is_file())

    observed_literal_files: set[str] = set()
    for path in candidate_paths:
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        if not should_export_public(rel_path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if find_public_local_path_leaks(text):
            observed_literal_files.add(rel_path)
        assert find_public_local_path_leaks(text, rel_path=rel_path) == (), rel_path

    assert observed_literal_files == set(PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS)
    for rel_path, exemptions in PUBLIC_INTENTIONAL_LOCAL_PATH_LITERALS.items():
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        for exemption in exemptions:
            assert exemption.text in text, (
                rel_path,
                exemption.text,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
