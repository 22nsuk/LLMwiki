from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from ops.scripts.codex_goal_client import (
    DEFAULT_CONTRACT_PATH,
    FakeGoalBackend,
    FileGoalBackend,
    GoalBackendUnavailableError,
    GoalContractValidationError,
    RunLocalFileGoalBackend,
    build_auto_improve_goal_contract,
    detect_goal_backend,
    get_goal,
    main,
    require_persistent_goal_backend,
    set_goal,
    update_goal,
)

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_codex_goal_contract import sample_goal_contract

pytestmark = pytest.mark.public


class CodexGoalClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_file_backend_persists_schema_valid_goal_contract(self) -> None:
        contract = sample_goal_contract()

        written = set_goal(contract, vault=self.vault)
        loaded = get_goal(vault=self.vault)

        self.assertEqual(written, contract)
        self.assertEqual(loaded, contract)
        self.assertTrue((self.vault / DEFAULT_CONTRACT_PATH).is_file())
        self.assertTrue(FileGoalBackend(self.vault).process_persistent)

    def test_update_goal_merges_patch_and_revalidates_full_contract(self) -> None:
        contract = sample_goal_contract()
        contract["metadata"] = {"attempt": {"count": 1, "note": "seed"}}
        set_goal(contract, vault=self.vault)

        updated = update_goal(
            {
                "status": "paused",
                "metadata": {"attempt": {"count": 2}, "operator": "local"},
            },
            vault=self.vault,
        )

        self.assertEqual(updated["status"], "paused")
        self.assertEqual(updated["metadata"]["attempt"], {"count": 2, "note": "seed"})
        self.assertEqual(updated["metadata"]["operator"], "local")

        with self.assertRaises(GoalContractValidationError):
            update_goal(
                {
                    "promotion_guard": {
                        "can_promote_result": True,
                        "promotion_blockers": ["still blocked"],
                    }
                },
                vault=self.vault,
            )

        persisted = json.loads((self.vault / DEFAULT_CONTRACT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(persisted["promotion_guard"]["can_promote_result"], False)

    def test_backend_detection_requires_explicit_persistent_backend_or_vault(self) -> None:
        with self.assertRaises(GoalBackendUnavailableError):
            detect_goal_backend()

        selected = detect_goal_backend(vault=self.vault)

        self.assertIsInstance(selected, FileGoalBackend)
        self.assertTrue(selected.process_persistent)

    def test_fake_backend_is_explicit_and_non_persistent(self) -> None:
        fake = FakeGoalBackend()

        with self.assertRaises(GoalBackendUnavailableError):
            detect_goal_backend(backend=fake)
        with self.assertRaises(GoalBackendUnavailableError):
            require_persistent_goal_backend(backend=fake)

        selected = detect_goal_backend(backend=fake, allow_fake=True)
        self.assertIs(selected, fake)
        self.assertFalse(selected.process_persistent)

        contract = sample_goal_contract()
        self.assertEqual(set_goal(contract, backend=fake, allow_fake=True), contract)
        self.assertEqual(get_goal(backend=fake, allow_fake=True), contract)

    def test_contract_path_without_vault_does_not_select_silent_fake_backend(self) -> None:
        with self.assertRaises(GoalBackendUnavailableError):
            detect_goal_backend(contract_path="ops/reports/other-goal.json")

    def test_default_auto_improve_contract_is_bounded_and_promotion_blocked(self) -> None:
        contract = build_auto_improve_goal_contract(created_at="2026-05-17T00:00:00Z")

        self.assertIn("non_goals", contract)
        self.assertIn(
            "Do not treat native Codex goal state as durable proof without file-backed goal, status, checkpoint, and certificate evidence.",
            contract["non_goals"],
        )
        self.assertIn("allowed_roots", contract)
        self.assertEqual(contract["budgets"]["max_wall_clock_seconds"], 21600)
        self.assertEqual(contract["budgets"]["max_proposals"], 1)
        self.assertEqual(contract["runtime"]["mode"], "self_improvement_loop")
        self.assertEqual(contract["runtime"]["duration_seconds"], 21600)
        self.assertEqual(contract["runtime"]["certificate_status"], "unverified")
        self.assertEqual(
            contract["execution_policy"]["learning_uncertain"],
            {
                "allow_bounded_trial": True,
                "requires_explicit_authorization": True,
                "authorization_source": "codex_goal_contract",
                "command_flag": "--allow-learning-uncertain",
            },
        )
        self.assertEqual(
            contract["execution_policy"]["post_promote_maintenance"],
            {
                "minimum_meaningful_cycles": 1,
                "allow_zero_cycles_for_certificate": False,
                "completion_condition": "post_promote_observation",
                "command_flag": "--post-promote-maintenance-cycles",
            },
        )
        self.assertEqual(contract["promotion_guard"]["can_promote_result"], False)
        self.assertEqual(contract["promotion_guard"]["sustained_runtime_claimed"], False)
        self.assertEqual(set_goal(contract, vault=self.vault), contract)

    def test_cli_writes_default_auto_improve_contract_to_file_backend(self) -> None:
        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/custom-goal-contract.json",
                "--contract-id",
                "custom-goal",
                "--created-at",
                "2026-05-17T00:00:00Z",
            ]
        )

        self.assertEqual(exit_code, 0)
        loaded = get_goal(vault=self.vault, contract_path="ops/reports/custom-goal-contract.json")
        self.assertEqual(loaded["contract_id"], "custom-goal")
        self.assertEqual(
            loaded["goal_backend"]["storage_path"],
            "ops/reports/custom-goal-contract.json",
        )

    def test_cli_embeds_artifact_envelope_metadata_when_policy_available(self) -> None:
        seed_minimal_vault(self.vault)

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/custom-goal-contract.json",
                "--contract-id",
                "custom-goal",
                "--created-at",
                "2026-05-17T00:00:00Z",
            ]
        )

        self.assertEqual(exit_code, 0)
        raw = json.loads(
            (self.vault / "ops" / "reports" / "custom-goal-contract.json").read_text(
                encoding="utf-8"
            )
        )
        properties = raw["metadata"]["properties"]
        envelope = json.loads(
            next(
                item["value"]
                for item in properties
                if item["name"] == "urn:openai:artifact-envelope"
            )
        )
        self.assertEqual(envelope["artifact_kind"], "codex_goal_contract")
        self.assertEqual(envelope["producer"], "ops.scripts.codex_goal_client")

    def test_cli_uses_injected_runtime_clock_for_artifact_envelope(self) -> None:
        seed_minimal_vault(self.vault)

        with patch.dict(os.environ, {"LLMWIKI_RUNTIME_UTC_NOW": "2026-05-21T16:00:00Z"}):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/injected-clock-goal-contract.json",
                    "--contract-id",
                    "injected-clock-goal",
                ]
            )

        self.assertEqual(exit_code, 0)
        raw = json.loads(
            (self.vault / "ops" / "reports" / "injected-clock-goal-contract.json").read_text(
                encoding="utf-8"
            )
        )
        envelope = json.loads(
            next(
                item["value"]
                for item in raw["metadata"]["properties"]
                if item["name"] == "urn:openai:artifact-envelope"
            )
        )
        self.assertEqual(raw["created_at"], "2026-05-21T16:00:00Z")
        self.assertEqual(envelope["generated_at"], "2026-05-21T16:00:00Z")

    def test_cli_reuses_initial_timestamp_for_created_at_and_envelope(self) -> None:
        seed_minimal_vault(self.vault)

        with patch(
            "ops.scripts.codex_goal_client._utc_now",
            side_effect=["2026-05-21T16:00:00Z", "2026-05-21T16:00:01Z"],
        ):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/default-clock-goal-contract.json",
                    "--contract-id",
                    "default-clock-goal",
                ]
            )

        self.assertEqual(exit_code, 0)
        raw = json.loads(
            (self.vault / "ops" / "reports" / "default-clock-goal-contract.json").read_text(
                encoding="utf-8"
            )
        )
        envelope = json.loads(
            next(
                item["value"]
                for item in raw["metadata"]["properties"]
                if item["name"] == "urn:openai:artifact-envelope"
            )
        )
        self.assertEqual(raw["created_at"], "2026-05-21T16:00:00Z")
        self.assertEqual(envelope["generated_at"], "2026-05-21T16:00:00Z")

    def test_cli_preserves_existing_created_at_for_same_contract_refresh(self) -> None:
        contract_path = "ops/reports/stable-goal-contract.json"
        first = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                contract_path,
                "--contract-id",
                "stable-goal",
                "--created-at",
                "2026-05-17T00:00:00Z",
            ]
        )
        second = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                contract_path,
                "--contract-id",
                "stable-goal",
            ]
        )

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        loaded = get_goal(vault=self.vault, contract_path=contract_path)
        self.assertEqual(loaded["created_at"], "2026-05-17T00:00:00Z")

    def test_cli_resets_created_at_for_new_contract_id(self) -> None:
        contract_path = "ops/reports/reused-path-goal-contract.json"
        self.assertEqual(
            main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    contract_path,
                    "--contract-id",
                    "old-goal",
                    "--created-at",
                    "2026-05-17T00:00:00Z",
                ]
            ),
            0,
        )

        self.assertEqual(
            main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    contract_path,
                    "--contract-id",
                    "new-goal",
                    "--created-at",
                    "2026-05-18T00:00:00Z",
                ]
            ),
            0,
        )
        loaded = get_goal(vault=self.vault, contract_path=contract_path)
        self.assertEqual(loaded["contract_id"], "new-goal")
        self.assertEqual(loaded["created_at"], "2026-05-18T00:00:00Z")

    def test_cli_syncs_promotion_guard_from_clean_readiness(self) -> None:
        seed_minimal_vault(self.vault)
        readiness_path = self.vault / "ops" / "reports" / "auto-improve-readiness.json"
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text(
            json.dumps(
                {
                    "can_promote_result": True,
                    "promotion_blockers": [],
                    "diagnostics": {
                        "release_authority_preflight_summary": {
                            "artifact_kind": "release_closeout_sealed_rehearsal_check",
                            "status": "pass",
                            "preflight_status": "sealed_clean_pass",
                            "distribution_binding_status": "pass",
                            "authority_preflight_status": "clean",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/clean-goal-contract.json",
                "--created-at",
                "2026-05-17T00:00:00Z",
            ]
        )

        self.assertEqual(exit_code, 0)
        loaded = get_goal(vault=self.vault, contract_path="ops/reports/clean-goal-contract.json")
        self.assertTrue(loaded["promotion_guard"]["can_promote_result"])
        self.assertTrue(loaded["promotion_guard"]["sealed_authority_clean"])
        self.assertEqual(loaded["promotion_guard"]["promotion_blockers"], [])
        self.assertFalse(loaded["promotion_guard"]["runtime_certificate_verified"])
        self.assertFalse(loaded["promotion_guard"]["sustained_runtime_claimed"])
        envelope = json.loads(
            next(
                item["value"]
                for item in loaded["metadata"]["properties"]
                if item["name"] == "urn:openai:artifact-envelope"
            )
        )
        self.assertNotEqual(
            envelope["input_fingerprints"]["auto_improve_readiness"],
            "missing",
        )

    def test_cli_worktree_guard_blocks_promotion_from_clean_readiness(self) -> None:
        seed_minimal_vault(self.vault)
        readiness_path = self.vault / "ops" / "reports" / "auto-improve-readiness.json"
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text(
            json.dumps(
                {
                    "can_promote_result": True,
                    "promotion_blockers": [],
                    "diagnostics": {
                        "release_authority_preflight_summary": {
                            "artifact_kind": "release_closeout_sealed_rehearsal_check",
                            "status": "pass",
                            "preflight_status": "sealed_clean_pass",
                            "distribution_binding_status": "pass",
                            "authority_preflight_status": "clean",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        guard_path = self.vault / "ops" / "reports" / "goal-worktree-guard.json"
        guard_path.parent.mkdir(parents=True, exist_ok=True)
        guard_path.write_text(
            json.dumps(
                {
                    "artifact_kind": "goal_worktree_guard",
                    "decisions": {
                        "can_promote_result": False,
                        "promotion_blockers": ["git_worktree_dirty"],
                        "fatal_blockers": [],
                    },
                }
            ),
            encoding="utf-8",
        )

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/dirty-goal-contract.json",
                "--created-at",
                "2026-05-17T00:00:00Z",
                "--worktree-guard-report",
                "ops/reports/goal-worktree-guard.json",
            ]
        )

        self.assertEqual(exit_code, 0)
        loaded = get_goal(vault=self.vault, contract_path="ops/reports/dirty-goal-contract.json")
        self.assertFalse(loaded["promotion_guard"]["can_promote_result"])
        self.assertTrue(loaded["promotion_guard"]["sealed_authority_clean"])
        self.assertEqual(loaded["promotion_guard"]["promotion_blockers"], ["git_worktree_dirty"])
        self.assertFalse(loaded["promotion_guard"]["sustained_runtime_claimed"])
        envelope = json.loads(
            next(
                item["value"]
                for item in loaded["metadata"]["properties"]
                if item["name"] == "urn:openai:artifact-envelope"
            )
        )
        self.assertNotEqual(
            envelope["input_fingerprints"]["auto_improve_readiness"],
            "missing",
        )
        self.assertNotEqual(
            envelope["input_fingerprints"]["goal_worktree_guard_report"],
            "missing",
        )

    def test_cli_treats_completed_queue_exhausted_loop_as_result_promotable(self) -> None:
        seed_minimal_vault(self.vault)
        reports = self.vault / "ops" / "reports"
        readiness_path = reports / "auto-improve-readiness.json"
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text(
            json.dumps(
                {
                    "can_promote_result": False,
                    "promotion_blockers": [
                        {"id": "execution_blocked_by_no_runnable_proposal"},
                        {"id": "learning_blocked_by_execution_not_runnable"},
                    ],
                    "diagnostics": {
                        "release_authority_preflight_summary": {
                            "artifact_kind": "release_closeout_sealed_rehearsal_check",
                            "status": "pass",
                            "preflight_status": "sealed_clean_pass",
                            "distribution_binding_status": "pass",
                            "authority_preflight_status": "clean",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        goal_status_path = (
            self.vault
            / "runs"
            / "goal-terminal-loop"
            / "state"
            / "goal-run-status.json"
        )
        goal_status_path.parent.mkdir(parents=True, exist_ok=True)
        goal_status_path.write_text(
            json.dumps(
                {
                    "run": {
                        "run_id": "terminal-loop",
                        "status": "completed",
                        "runtime_mode": "self_improvement_loop",
                    }
                }
            ),
            encoding="utf-8",
        )
        session_path = reports / "auto-improve-sessions" / "terminal-loop.json"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "status": "complete",
                    "stop_reason": "queue_exhausted",
                    "iterations": [{"decision": "PROMOTE", "outcome": "promoted"}],
                }
            ),
            encoding="utf-8",
        )
        guard_path = self.vault / "ops" / "reports" / "goal-worktree-guard.json"
        guard_path.parent.mkdir(parents=True, exist_ok=True)
        guard_path.write_text(
            json.dumps(
                {
                    "artifact_kind": "goal_worktree_guard",
                    "decisions": {
                        "can_promote_result": True,
                        "promotion_blockers": [],
                        "fatal_blockers": [],
                    },
                }
            ),
            encoding="utf-8",
        )

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/terminal-goal-contract.json",
                "--created-at",
                "2026-05-17T00:00:00Z",
                "--goal-status-path",
                "runs/goal-terminal-loop/state/goal-run-status.json",
                "--worktree-guard-report",
                "ops/reports/goal-worktree-guard.json",
            ]
        )

        self.assertEqual(exit_code, 0)
        loaded = get_goal(vault=self.vault, contract_path="ops/reports/terminal-goal-contract.json")
        self.assertTrue(loaded["promotion_guard"]["can_promote_result"])
        self.assertEqual(loaded["promotion_guard"]["promotion_blockers"], [])
        envelope = json.loads(
            next(
                item["value"]
                for item in loaded["metadata"]["properties"]
                if item["name"] == "urn:openai:artifact-envelope"
            )
        )
        self.assertNotEqual(envelope["input_fingerprints"]["goal_run_status"], "missing")
        self.assertNotEqual(envelope["input_fingerprints"]["auto_improve_session"], "missing")

    def test_cli_preserves_existing_runtime_certificate_state(self) -> None:
        contract_path = "ops/reports/preserved-goal-contract.json"
        contract = build_auto_improve_goal_contract(
            created_at="2026-05-17T00:00:00Z",
            storage_path=contract_path,
        )
        contract["objective"] = "Keep the operator-requested runtime goal wording stable."
        contract["metadata"] = {
            "requested_by": "user",
            "source_reports_reviewed": ["external-reports/long-run.md"],
        }
        contract["runtime"]["certificate_status"] = "verified"
        contract["runtime"]["verified_at"] = "2026-05-17T01:00:00Z"
        contract["promotion_guard"]["runtime_certificate_verified"] = True
        set_goal(contract, vault=self.vault, contract_path=contract_path)

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                contract_path,
                "--created-at",
                "2026-05-17T00:00:00Z",
            ]
        )

        self.assertEqual(exit_code, 0)
        loaded = get_goal(vault=self.vault, contract_path=contract_path)
        self.assertEqual(loaded["runtime"]["certificate_status"], "verified")
        self.assertEqual(loaded["runtime"]["verified_at"], "2026-05-17T01:00:00Z")
        self.assertTrue(loaded["promotion_guard"]["runtime_certificate_verified"])
        self.assertFalse(loaded["promotion_guard"]["sustained_runtime_claimed"])
        self.assertEqual(
            loaded["objective"],
            "Keep the operator-requested runtime goal wording stable.",
        )
        self.assertEqual(loaded["metadata"]["requested_by"], "user")
        self.assertEqual(
            loaded["metadata"]["source_reports_reviewed"],
            ["external-reports/long-run.md"],
        )

    def test_run_local_contract_marks_backend_and_status_path(self) -> None:
        contract = build_auto_improve_goal_contract(
            created_at="2026-05-17T00:00:00Z",
            storage_path="runs/goal-trial/state/codex-goal-contract.json",
            backend_type="run_local_file",
            goal_status_path="runs/goal-trial/state/goal-run-status.json",
        )

        backend = RunLocalFileGoalBackend(
            self.vault,
            contract_path="runs/goal-trial/state/codex-goal-contract.json",
        )
        written = set_goal(contract, backend=backend)

        self.assertEqual(written["goal_backend"]["backend_type"], "run_local_file")
        self.assertEqual(backend.name, "run_local_file")
        self.assertEqual(
            next(
                item["path"]
                for item in written["required_evidence"]
                if item["evidence_id"] == "goal_run_status"
            ),
            "runs/goal-trial/state/goal-run-status.json",
        )
        self.assertTrue((self.vault / "runs" / "goal-trial" / "state" / "codex-goal-contract.json").is_file())


if __name__ == "__main__":
    unittest.main()
