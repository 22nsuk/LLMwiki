from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.goal_worktree_guard import (
    GitCommandResult,
    GoalWorktreeGuardRequest,
    build_report,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-worktree-guard.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC),
    )


class FakeGit:
    def __init__(self, responses: dict[tuple[str, ...], GitCommandResult]) -> None:
        self.responses = responses

    def __call__(self, args: list[str]) -> GitCommandResult:
        key = tuple(args)
        if key[:5] == (
            "status",
            "--porcelain=v1",
            "--ignored=matching",
            "--untracked-files=all",
            "--",
        ):
            return self.responses.get(("ignored-status",), GitCommandResult(0, "", ""))
        if key == (
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
        ):
            return self.responses.get(key, GitCommandResult(0, "", ""))
        return self.responses.get(key, GitCommandResult(1, "", "unexpected git command"))


class GoalWorktreeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/goal-worktree-guard.schema.json")
        self._copy_support_file("ops/scripts/mechanism/goal_worktree_guard.py")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_public_layout(self) -> None:
        for rel_path in ("ops", "tests", "mk", "docs"):
            (self.vault / rel_path).mkdir(exist_ok=True)
        for rel_path in ("README.md", "Makefile"):
            (self.vault / rel_path).write_text("placeholder\n", encoding="utf-8")

    def test_git_worktree_report_passes_when_clean(self) -> None:
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(0, "true", ""),
                ("rev-parse", "--show-toplevel"): GitCommandResult(0, str(self.vault), ""),
                ("rev-parse", "--verify", "HEAD"): GitCommandResult(0, "a" * 40, ""),
                ("branch", "--show-current"): GitCommandResult(0, "main", ""),
                ("status", "--porcelain=v1", "--untracked-files=normal"): GitCommandResult(0, "", ""),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["artifact_kind"], "goal_worktree_guard")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["detected_mode"], "git_worktree")
        self.assertEqual(report["git"]["worktree_root"], ".")
        self.assertEqual(report["git"]["dirty_entry_count"], 0)
        self.assertEqual(report["git"]["durable_private_ignored_entry_count"], 0)
        self.assertEqual(report["decisions"]["can_execute_goal_runtime"], True)
        self.assertEqual(report["decisions"]["can_promote_result"], True)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_dirty_git_worktree_blocks_promotion_but_not_execution(self) -> None:
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(0, "true", ""),
                ("rev-parse", "--show-toplevel"): GitCommandResult(0, str(self.vault), ""),
                ("rev-parse", "--verify", "HEAD"): GitCommandResult(0, "b" * 40, ""),
                ("branch", "--show-current"): GitCommandResult(0, "main", ""),
                ("status", "--porcelain=v1", "--untracked-files=normal"): GitCommandResult(
                    0,
                    " M ops/scripts/example.py\n?? tests/test_example.py",
                    "",
                ),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["decisions"]["can_execute_goal_runtime"], True)
        self.assertEqual(report["decisions"]["can_promote_result"], False)
        self.assertEqual(report["decisions"]["promotion_blockers"], ["git_worktree_dirty"])
        self.assertEqual(report["git"]["dirty_entry_count"], 2)
        self.assertEqual(report["git"]["status_codes"], {"??": 1, "M": 1})
        self.assertEqual(report["git"]["self_output_dirty_entry_count"], 0)
        self.assertEqual(report["git"]["self_output_dirty_status_codes"], {})
        self.assertEqual(report["git"]["durable_private_ignored_entry_count"], 0)
        self.assertNotIn("ops/scripts/example.py", json.dumps(report))
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_self_output_dirty_status_is_ignored_for_reentrant_report_refresh(self) -> None:
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(0, "true", ""),
                ("rev-parse", "--show-toplevel"): GitCommandResult(0, str(self.vault), ""),
                ("rev-parse", "--verify", "HEAD"): GitCommandResult(0, "e" * 40, ""),
                ("branch", "--show-current"): GitCommandResult(0, "main", ""),
                ("status", "--porcelain=v1", "--untracked-files=normal"): GitCommandResult(
                    0,
                    "M ops/reports/goal-worktree-guard.json",
                    "",
                ),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["decisions"]["can_promote_result"], True)
        self.assertEqual(report["git"]["dirty_entry_count"], 0)
        self.assertEqual(report["git"]["status_codes"], {})
        self.assertEqual(report["git"]["self_output_dirty_entry_count"], 1)
        self.assertEqual(report["git"]["self_output_dirty_status_codes"], {"M": 1})
        self.assertEqual(report["blockers"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ignored_local_only_surfaces_do_not_block_promotion_or_leak_paths(self) -> None:
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(0, "true", ""),
                ("rev-parse", "--show-toplevel"): GitCommandResult(0, str(self.vault), ""),
                ("rev-parse", "--verify", "HEAD"): GitCommandResult(0, "d" * 40, ""),
                ("branch", "--show-current"): GitCommandResult(0, "main", ""),
                ("status", "--porcelain=v1", "--untracked-files=normal"): GitCommandResult(
                    0,
                    "",
                    "",
                ),
                ("ignored-status",): GitCommandResult(
                    0,
                    "\n".join(
                        [
                            "!! external-reports/private-new-review.md",
                            "!! ops/reports/goal-worktree-guard.json",
                            "!! raw/source.pdf",
                        ]
                    ),
                    "",
                ),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )
        serialized = json.dumps(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["decisions"]["can_execute_goal_runtime"], True)
        self.assertEqual(report["decisions"]["can_promote_result"], True)
        self.assertEqual(report["decisions"]["promotion_blockers"], [])
        self.assertEqual(report["git"]["durable_private_ignored_entry_count"], 0)
        self.assertEqual(report["git"]["durable_private_ignored_status_codes"], {})
        self.assertNotIn("private-new-review.md", serialized)
        self.assertNotIn("source.pdf", serialized)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_ignored_external_report_archive_is_local_only_retained_evidence(self) -> None:
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(0, "true", ""),
                ("rev-parse", "--show-toplevel"): GitCommandResult(0, str(self.vault), ""),
                ("rev-parse", "--verify", "HEAD"): GitCommandResult(0, "f" * 40, ""),
                ("branch", "--show-current"): GitCommandResult(0, "main", ""),
                ("status", "--porcelain=v1", "--untracked-files=normal"): GitCommandResult(
                    0,
                    "",
                    "",
                ),
                ("ignored-status",): GitCommandResult(
                    0,
                    "\n".join(
                        [
                            "!! external-reports/archive/closed-review.md",
                            "!! external-reports/report-reference-manifest.json",
                        ]
                    ),
                    "",
                ),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["decisions"]["can_promote_result"], True)
        self.assertEqual(report["git"]["durable_private_ignored_entry_count"], 0)
        self.assertEqual(report["git"]["durable_private_ignored_status_codes"], {})
        self.assertEqual(report["blockers"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_zip_extract_mode_is_distinct_and_non_promotable(self) -> None:
        self._write_public_layout()
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(
                    128,
                    "",
                    "not a git repository",
                ),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="auto",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["detected_mode"], "zip_extract")
        self.assertEqual(report["decisions"]["zip_mode_replay_only"], True)
        self.assertEqual(report["decisions"]["can_execute_goal_runtime"], False)
        self.assertEqual(report["decisions"]["can_promote_result"], False)
        self.assertEqual(report["decisions"]["promotion_blockers"], ["zip_mode_non_promotable"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_git_mode_fails_inside_zip_extract(self) -> None:
        self._write_public_layout()
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(
                    128,
                    "",
                    "not a git repository",
                ),
            }
        )

        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("git_worktree_required", report["decisions"]["fatal_blockers"])
        self.assertIn("zip_mode_non_promotable", report["decisions"]["promotion_blockers"])

    def test_write_report_uses_tmp_default_without_absolute_path_leak(self) -> None:
        fake_git = FakeGit(
            {
                ("--version",): GitCommandResult(0, "git version 2.0", ""),
                ("rev-parse", "--is-inside-work-tree"): GitCommandResult(0, "true", ""),
                ("rev-parse", "--show-toplevel"): GitCommandResult(0, str(self.vault), ""),
                ("rev-parse", "--verify", "HEAD"): GitCommandResult(0, "c" * 40, ""),
                ("branch", "--show-current"): GitCommandResult(0, "main", ""),
                ("status", "--porcelain=v1", "--untracked-files=normal"): GitCommandResult(0, "", ""),
            }
        )
        report = build_report(
            GoalWorktreeGuardRequest(
                vault=self.vault,
                requested_mode="git",
                git_runner=fake_git,
                context=fixed_context(),
            )
        )

        path = write_report(self.vault, report)
        payload = path.read_text(encoding="utf-8")

        self.assertEqual(path, self.vault / "ops" / "reports" / "goal-worktree-guard.json")
        self.assertNotIn(str(self.vault), payload)


if __name__ == "__main__":
    unittest.main()
