from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import ops.scripts.set_mechanism_run_history as set_history_runtime
from ops.scripts.filesystem_runtime import FilesystemTransactionError
from ops.scripts.mechanism_review_runtime import build_report
from ops.scripts.policy_runtime import load_policy
from ops.scripts.set_mechanism_run_history import (
    SetMechanismRunHistoryUsageError,
    set_mechanism_run_history,
)

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_planning_gate_validate import seed_mechanism_run_artifacts


class SetMechanismRunHistoryTests(unittest.TestCase):
    def test_build_history_atomic_updates_builds_batch_and_rejects_duplicate_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "nested").mkdir()
            promotion_path = root / "promotion-report.json"
            ledger_path = root / "run-ledger.json"

            updates = set_history_runtime._build_history_atomic_updates(
                promotion_path=promotion_path,
                promotion_report={"kind": "promotion"},
                ledger_path=ledger_path,
                run_ledger={"kind": "ledger"},
            )

            self.assertEqual([update.path for update in updates], [promotion_path, ledger_path])
            self.assertEqual(json.loads(updates[0].text), {"kind": "promotion"})
            self.assertEqual(json.loads(updates[1].text), {"kind": "ledger"})

            with self.assertRaisesRegex(
                FilesystemTransactionError,
                "atomic_multi_write received duplicate target paths: .*promotion-report.json",
            ):
                set_history_runtime._build_history_atomic_updates(
                    promotion_path=promotion_path,
                    promotion_report={"kind": "promotion"},
                    ledger_path=root / "nested" / ".." / "promotion-report.json",
                    run_ledger={"kind": "ledger"},
                )

    def test_set_mechanism_run_history_archives_run_and_appends_ledger_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-history-status")

            result = set_mechanism_run_history(
                vault,
                "run-history-status",
                status="archived",
                reason="false discard from runner defect",
                by="human",
                ts="2026-04-15T00:00:00Z",
            )

            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            run_ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))

            self.assertTrue(result["changed"])
            self.assertEqual(promotion_report["history"]["status"], "archived")
            self.assertEqual(
                promotion_report["history"]["reason"],
                "false discard from runner defect",
            )
            self.assertEqual(promotion_report["history"]["by"], "human")
            self.assertEqual(promotion_report["history"]["ts"], "2026-04-15T00:00:00Z")
            self.assertEqual(run_ledger["events"][-1]["type"], "history_status_updated")
            self.assertEqual(run_ledger["events"][-1]["decision"], "archived")

    def test_set_mechanism_run_history_requires_reason_for_non_active_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_mechanism_run_artifacts(vault, "run-history-missing-reason")

            with self.assertRaises(SetMechanismRunHistoryUsageError):
                set_mechanism_run_history(
                    vault,
                    "run-history-missing-reason",
                    status="quarantined",
                    reason="",
                    by="human",
                    ts="2026-04-15T00:00:00Z",
                )

    def test_mechanism_review_excludes_non_active_runs_from_active_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_mechanism_run_artifacts(vault, "run-history-active")
            seed_mechanism_run_artifacts(vault, "run-history-archived")

            set_mechanism_run_history(
                vault,
                "run-history-archived",
                status="archived",
                reason="buggy runner discard",
                by="human",
                ts="2026-04-15T00:00:00Z",
            )

            policy, policy_path = load_policy(vault)
            report = build_report(vault, policy, policy_path)

            self.assertEqual(report["summary"]["runs_discovered"], 2)
            self.assertEqual(report["summary"]["runs_considered"], 1)
            self.assertEqual(report["summary"]["runs_excluded"], 1)
            self.assertEqual(report["summary"]["runs_skipped"], 0)
            self.assertEqual(report["diagnostics"]["excluded_runs"][0]["run_id"], "run-history-archived")
            self.assertEqual(report["diagnostics"]["excluded_runs"][0]["status"], "archived")
            self.assertEqual(
                report["diagnostics"]["excluded_runs"][0]["reason"],
                "buggy runner discard",
            )


if __name__ == "__main__":
    unittest.main()
