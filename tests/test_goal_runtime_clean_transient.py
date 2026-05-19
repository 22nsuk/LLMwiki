from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.goal_runtime_clean_transient import (
    GoalRuntimeCleanTransientRequest,
    build_report,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-clean-transient.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 19, 12, 0, tzinfo=dt.timezone.utc),
    )


class GoalRuntimeCleanTransientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/goal-runtime-clean-transient.schema.json")
        self._seed_goal_status()
        self._seed_transients()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write(self, rel_path: str, text: str = "stale\n") -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _seed_goal_status(self) -> None:
        self._write(
            "ops/reports/goal-run-status.json",
            json.dumps(
                {
                    "goal": {
                        "contract_path": "runs/goal-active/state/codex-goal-contract.json",
                    },
                    "run": {"run_id": "active", "status": "blocked"},
                    "artifacts": {
                        "status_report_path": "runs/goal-active/state/goal-run-status.json",
                        "status_markdown_path": "runs/goal-active/state/status.md",
                        "audit_log_path": "runs/goal-active/state/audit-log.jsonl",
                        "resume_metadata_path": "runs/goal-active/state/resume-metadata.json",
                        "checkpoint_command_log_path": "runs/goal-active/state/checkpoint-command-events.jsonl",
                    },
                },
                sort_keys=True,
            ),
        )

    def _seed_transients(self) -> None:
        for rel_path in (
            "ops/reports/goal-status.md",
            "ops/reports/goal-resume-metadata.json",
            "ops/reports/goal-prompt.md",
            "ops/reports/goal-audit-log.jsonl",
            "ops/reports/runtime-events/auto-improve-session/active.jsonl",
            "ops/reports/runtime-events/observability-artifacts/active.jsonl",
            "runs/goal-active/state/auto-improve-goal-session-result.json",
            "runs/goal-old/state/status.md",
            "tmp/source-package-check/extract/file.txt",
        ):
            self._write(rel_path)
        for rel_path in (
            "ops/reports/codex-goal-prompt.json",
            "runs/goal-active/state/status.md",
            "runs/goal-active/state/audit-log.jsonl",
        ):
            self._write(rel_path, "current\n")

    def test_report_only_identifies_non_protected_transients(self) -> None:
        report = build_report(
            GoalRuntimeCleanTransientRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertEqual(report["summary"]["would_remove_count"], 9)
        paths = {item["path"] for item in report["cleanup_candidates"]}
        self.assertIn("ops/reports/goal-status.md", paths)
        self.assertIn("runs/goal-active/state/auto-improve-goal-session-result.json", paths)
        self.assertIn("runs/goal-old", paths)
        self.assertNotIn("runs/goal-active", paths)
        self.assertNotIn("ops/reports/codex-goal-prompt.json", paths)

    def test_apply_removes_transients_and_keeps_active_goal_state(self) -> None:
        report = build_report(
            GoalRuntimeCleanTransientRequest(
                vault=self.vault,
                apply=True,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["removed_count"], 9)
        self.assertFalse((self.vault / "ops/reports/goal-status.md").exists())
        self.assertFalse(
            (self.vault / "runs/goal-active/state/auto-improve-goal-session-result.json").exists()
        )
        self.assertFalse((self.vault / "runs/goal-old").exists())
        self.assertFalse((self.vault / "tmp/source-package-check").exists())
        self.assertTrue((self.vault / "runs/goal-active/state/status.md").is_file())
        self.assertTrue((self.vault / "ops/reports/codex-goal-prompt.json").is_file())
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_report_uses_schema_backed_output(self) -> None:
        report = build_report(
            GoalRuntimeCleanTransientRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        out_path = write_report(self.vault, report)

        self.assertEqual(out_path, self.vault / "tmp/goal-runtime-clean-transient.json")
        self.assertTrue(out_path.is_file())

    def test_outside_status_report_path_is_sanitized_and_does_not_unlock_run_tree_cleanup(
        self,
    ) -> None:
        outside_status = Path(self.temp_dir.name) / "outside-status.json"
        outside_status.write_text(
            json.dumps(
                {
                    "goal": {"contract_path": "/private/contract.json"},
                    "run": {"run_id": "active"},
                    "artifacts": {"status_markdown_path": "/private/status.md"},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        report = build_report(
            GoalRuntimeCleanTransientRequest(
                vault=self.vault,
                status_report_path=str(outside_status),
                context=fixed_context(),
            )
        )

        serialized = json.dumps(report, sort_keys=True)
        self.assertEqual(report["status_report_path"], "<outside-vault>")
        self.assertNotIn(str(outside_status), serialized)
        self.assertNotIn("/private/contract.json", serialized)
        self.assertNotIn("runs/goal-active", {item["path"] for item in report["cleanup_candidates"]})
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
