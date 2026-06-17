from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.goal_runtime_clean_transient import (
    GoalRuntimeCleanTransientRequest,
    build_report,
    write_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-clean-transient.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 19, 12, 0, tzinfo=dt.UTC),
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
            "build/source-package-check/extract/LLMwiki/raw/private.md",
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
        self.assertEqual(report["summary"]["would_remove_count"], 10)
        paths = {item["path"] for item in report["cleanup_candidates"]}
        self.assertIn("build/source-package-check", paths)
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
        self.assertEqual(report["summary"]["removed_count"], 10)
        self.assertFalse((self.vault / "build/source-package-check").exists())
        self.assertFalse((self.vault / "ops/reports/goal-status.md").exists())
        self.assertFalse(
            (self.vault / "runs/goal-active/state/auto-improve-goal-session-result.json").exists()
        )
        self.assertFalse((self.vault / "runs/goal-old").exists())
        self.assertFalse((self.vault / "tmp/source-package-check").exists())
        self.assertTrue((self.vault / "runs/goal-active/state/status.md").is_file())
        self.assertTrue((self.vault / "ops/reports/codex-goal-prompt.json").is_file())
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_apply_removes_contract_state_session_result_when_run_id_differs(self) -> None:
        self._write(
            "ops/reports/goal-run-status.json",
            json.dumps(
                {
                    "goal": {
                        "contract_path": "runs/goal-active/state/codex-goal-contract.json",
                    },
                    "run": {"run_id": "active-rerun12-self-improvement-loop", "status": "blocked"},
                    "artifacts": {
                        "status_report_path": "runs/goal-active/state/goal-run-status.json",
                    },
                },
                sort_keys=True,
            ),
        )

        report = build_report(
            GoalRuntimeCleanTransientRequest(
                vault=self.vault,
                apply=True,
                context=fixed_context(),
            )
        )

        removed_paths = {
            item["path"]
            for item in report["cleanup_candidates"]
            if item["action"] == "removed"
        }
        self.assertIn("runs/goal-active/state/auto-improve-goal-session-result.json", removed_paths)
        self.assertFalse(
            (self.vault / "runs/goal-active/state/auto-improve-goal-session-result.json").exists()
        )

    def test_verified_certificate_evidence_tree_is_protected_from_stale_cleanup(self) -> None:
        self._write("runs/goal-old/state/codex-goal-contract.json", "{}\n")
        self._write("runs/goal-old/state/goal-run-status.json", "{}\n")
        self._write("runs/goal-old/state/audit-log.jsonl", "{}\n")
        self._write("ops/reports/auto-improve-sessions/old.json", "{}\n")
        self._write(
            "ops/reports/goal-runtime-certificate.json",
            json.dumps(
                {
                    "artifact_kind": "goal_runtime_certificate",
                    "status": "pass",
                    "certificate": {"verification_status": "already_verified", "eligible": True},
                    "contract_update": {"runtime_certificate_verified_after": True},
                    "goal": {"contract_path": "runs/goal-old/state/codex-goal-contract.json"},
                    "run": {"status_report_path": "runs/goal-old/state/goal-run-status.json"},
                    "session_evidence": {"path": "ops/reports/auto-improve-sessions/old.json"},
                    "run_artifacts": {
                        "checks": [
                            {"path": "runs/goal-old/state/audit-log.jsonl", "status": "pass"}
                        ]
                    },
                    "evidence_paths": [],
                },
                sort_keys=True,
            ),
        )

        report = build_report(
            GoalRuntimeCleanTransientRequest(
                vault=self.vault,
                apply=True,
                context=fixed_context(),
            )
        )

        self.assertIn("runs/goal-old", report["protected_paths"])
        self.assertTrue((self.vault / "runs/goal-old/state/goal-run-status.json").is_file())
        self.assertNotIn(
            "runs/goal-old",
            {item["path"] for item in report["cleanup_candidates"] if item["action"] == "removed"},
        )

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
