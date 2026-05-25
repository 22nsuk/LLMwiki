from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.filesystem_runtime import FilesystemTransactionError
from ops.scripts.finalize_run_runtime import (
    FinalizeRunUsageError,
    FinalizeRunWriteError,
    finalize_run,
)
from ops.scripts.finalize_run_write_runtime import build_finalize_atomic_updates
from ops.scripts.promotion_decision_registry_runtime import attach_decision_contract

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_planning_gate_validate import seed_mechanism_run_artifacts


class FinalizeRunTests(unittest.TestCase):
    def test_build_finalize_atomic_updates_builds_ordered_batch_and_rejects_duplicate_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "nested").mkdir()
            promotion_path = root / "promotion-report.json"
            ledger_path = root / "run-ledger.json"
            planning_path = root / "planning-validation.json"
            log_path = root / "system-log.md"

            updates = build_finalize_atomic_updates(
                promotion_path=promotion_path,
                report={"kind": "promotion"},
                ledger_path=ledger_path,
                ledger={"kind": "ledger"},
                planning_path=planning_path,
                planning_validation={"kind": "planning"},
                log_path=log_path,
                final_log_text="log entry\n",
            )

            self.assertEqual(
                [update.path for update in updates],
                [promotion_path, ledger_path, planning_path, log_path],
            )
            self.assertEqual(json.loads(updates[0].text), {"kind": "promotion"})
            self.assertEqual(updates[-1].text, "log entry\n")

            with self.assertRaisesRegex(
                FilesystemTransactionError,
                "atomic_multi_write received duplicate target paths: .*promotion-report.json",
            ):
                build_finalize_atomic_updates(
                    promotion_path=promotion_path,
                    report={"kind": "promotion"},
                    ledger_path=root / "nested" / ".." / "promotion-report.json",
                    ledger={"kind": "ledger"},
                    planning_path=planning_path,
                    planning_validation={"kind": "planning"},
                    log_path=None,
                    final_log_text=None,
                )

    def test_finalize_run_records_log_and_refreshes_planning_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-finalize")

            result = finalize_run(vault, "run-finalize")

            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            run_ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            planning_validation = json.loads((run_dir / "planning-validation.json").read_text(encoding="utf-8"))
            system_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")

            self.assertEqual(result["decision"], "PROMOTE")
            self.assertEqual(promotion_report["log"]["status"], "recorded")
            self.assertTrue(promotion_report["log"]["entry_ref"])
            self.assertEqual(promotion_report["log"]["entry_ref"], result["log_entry_ref"])
            self.assertEqual(run_ledger["status"], "complete")
            self.assertIn("finalized", [event["type"] for event in run_ledger["events"]])
            finalized_event = next(event for event in run_ledger["events"] if event["type"] == "finalized")
            self.assertEqual(finalized_event["decision_event"]["decision"], "PROMOTE")
            self.assertEqual(finalized_event["decision_event"]["ledger_event_type"], "finalized")
            self.assertEqual(planning_validation["status"], "PASS")
            self.assertEqual(
                planning_validation["next_action"],
                "Use this finalized run as future history input for mechanism_review and mutation_proposal.",
            )
            self.assertIn("Finalize mechanism run run-finalize (PROMOTE)", system_log)

    def test_finalize_run_log_artifacts_follow_changed_files_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_mechanism_run_artifacts(vault, "run-finalize-artifacts")

            finalize_run(vault, "run-finalize-artifacts")
            system_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")

            self.assertIn("`runs/run-finalize-artifacts/changed-files-manifest.json`", system_log)
            self.assertIn("`ops/scripts/example.py`", system_log)
            self.assertNotIn("`tests/test_example.py`", system_log)
            self.assertNotIn("`tests/test_example_0.py`", system_log)
            self.assertEqual(system_log.count("`runs/run-finalize-artifacts/run-ledger.json`"), 1)

    def test_finalize_run_is_idempotent_for_recorded_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-finalize-idempotent")

            finalize_run(vault, "run-finalize-idempotent")
            first_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")
            first_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))

            finalize_run(vault, "run-finalize-idempotent")
            second_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")
            second_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))

            self.assertEqual(first_log, second_log)
            self.assertEqual(first_report["log"]["entry_ref"], second_report["log"]["entry_ref"])

    def test_finalize_run_rejects_hold_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-hold")
            promotion_report_path = run_dir / "promotion-report.json"
            promotion_report = json.loads(promotion_report_path.read_text(encoding="utf-8"))
            promotion_report["decision"] = "HOLD"
            promotion_report = attach_decision_contract(
                promotion_report,
                [
                    {
                        "rule_id": "signoff_status",
                        "decision": "HOLD",
                        "reason_code": "signoff_status",
                        "reason_detail": "required signoff is pending",
                        "evidence_refs": ["signoff_status"],
                    }
                ],
                subject_id="run-hold",
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff=promotion_report["signoff"],
            )
            promotion_report_path.write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaises(FinalizeRunUsageError):
                finalize_run(vault, "run-hold")

    def test_finalize_run_requires_canonical_decision_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-missing-decision-record")
            promotion_report_path = run_dir / "promotion-report.json"
            promotion_report = json.loads(promotion_report_path.read_text(encoding="utf-8"))
            promotion_report.pop("decision_record")
            promotion_report.pop("decision_reduction")
            promotion_report_path.write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(FinalizeRunUsageError, "missing canonical decision_record"):
                finalize_run(vault, "run-missing-decision-record")

    def test_finalize_run_rejects_decision_record_mirror_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-decision-mismatch")
            promotion_report_path = run_dir / "promotion-report.json"
            promotion_report = json.loads(promotion_report_path.read_text(encoding="utf-8"))
            promotion_report["decision"] = "DISCARD"
            promotion_report_path.write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(FinalizeRunUsageError, "decision mirror does not match"):
                finalize_run(vault, "run-decision-mismatch")

    def test_finalize_run_respects_log_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-no-log")
            promotion_report_path = run_dir / "promotion-report.json"
            promotion_report = json.loads(promotion_report_path.read_text(encoding="utf-8"))
            promotion_report["log"]["required"] = False
            promotion_report["log"]["status"] = "pending"
            promotion_report_path.write_text(
                json.dumps(promotion_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            result = finalize_run(vault, "run-no-log")
            updated_report = json.loads(promotion_report_path.read_text(encoding="utf-8"))

            self.assertEqual(updated_report["log"]["status"], "not_required")
            self.assertEqual(updated_report["log"]["entry_ref"], "")
            self.assertEqual(result["log_entry_ref"], "")

    def test_finalize_run_does_not_append_log_when_artifact_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-atomic-artifact-fail")

            promotion_path = run_dir / "promotion-report.json"
            ledger_path = run_dir / "run-ledger.json"
            planning_path = run_dir / "planning-validation.json"
            log_path = vault / "system" / "system-log.md"

            original_promotion = promotion_path.read_text(encoding="utf-8")
            original_ledger = ledger_path.read_text(encoding="utf-8")
            original_planning = planning_path.read_text(encoding="utf-8")
            original_log = log_path.read_text(encoding="utf-8")
            real_replace = __import__("os").replace
            replace_calls = {"count": 0}

            def fail_on_planning(src: str | Path, dst: str | Path) -> None:
                replace_calls["count"] += 1
                if replace_calls["count"] == 3:
                    raise OSError("simulated planning commit failure")
                real_replace(src, dst)

            with (
                mock.patch(
                    "ops.scripts.filesystem_runtime.os.replace",
                    side_effect=fail_on_planning,
                ),
                self.assertRaises(FinalizeRunWriteError),
            ):
                finalize_run(vault, "run-atomic-artifact-fail")

            self.assertEqual(promotion_path.read_text(encoding="utf-8"), original_promotion)
            self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)
            self.assertEqual(planning_path.read_text(encoding="utf-8"), original_planning)
            self.assertEqual(log_path.read_text(encoding="utf-8"), original_log)

    def test_finalize_run_uses_policy_display_timezone_for_log_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_mechanism_run_artifacts(vault, "run-finalize-timezone")

            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    "  display_timezone:\n    label: KST\n    utc_offset: \"+09:00\"\n",
                    "  display_timezone:\n    label: UTC\n    utc_offset: \"+00:00\"\n",
                    1,
                ),
                encoding="utf-8",
            )

            finalize_run(
                vault,
                "run-finalize-timezone",
                now=dt.datetime(2026, 4, 14, 12, 34, tzinfo=dt.UTC),
            )
            system_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")

            self.assertIn("[2026-04-14 12:34 UTC] improve | Finalize mechanism run run-finalize-timezone (PROMOTE)", system_log)

    def test_finalize_run_rolls_back_artifacts_when_log_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-atomic-log-fail")

            promotion_path = run_dir / "promotion-report.json"
            ledger_path = run_dir / "run-ledger.json"
            planning_path = run_dir / "planning-validation.json"
            log_path = vault / "system" / "system-log.md"

            original_promotion = promotion_path.read_text(encoding="utf-8")
            original_ledger = ledger_path.read_text(encoding="utf-8")
            original_planning = planning_path.read_text(encoding="utf-8")
            original_log = log_path.read_text(encoding="utf-8")
            real_replace = __import__("os").replace
            replace_calls = {"count": 0}

            def fail_on_log(src: str | Path, dst: str | Path) -> None:
                replace_calls["count"] += 1
                if replace_calls["count"] == 4:
                    raise OSError("simulated log commit failure")
                real_replace(src, dst)

            with (
                mock.patch("ops.scripts.filesystem_runtime.os.replace", side_effect=fail_on_log),
                self.assertRaises(FinalizeRunWriteError),
            ):
                finalize_run(vault, "run-atomic-log-fail")

            self.assertEqual(promotion_path.read_text(encoding="utf-8"), original_promotion)
            self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)
            self.assertEqual(planning_path.read_text(encoding="utf-8"), original_planning)
            self.assertEqual(log_path.read_text(encoding="utf-8"), original_log)


if __name__ == "__main__":
    unittest.main()
