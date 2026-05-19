from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts import (
    filesystem_runtime,
    mechanism_run_capture_runtime,
    mechanism_run_promotion_runtime,
    mechanism_run_workspace_runtime,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.run_mechanism_experiment_runtime import (
    run_mechanism_experiment,
)
from tests.minimal_vault_runtime import set_policy_value
from tests.run_mechanism_experiment_test_utils import (
    ForcedPromotionReportPatch,
    PENDING_SIGNOFF_DECISION_CONTRACT,
    PromotionReportCallExpectation,
    forced_promotion_report_builder,
    seed_wrapper_vault,
    successful_command_result,
    write_stubbed_capture_artifacts,
)

pytestmark = pytest.mark.integration


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
    )


class RunMechanismExperimentTests(unittest.TestCase):
    def test_wrapper_runs_full_promote_and_finalize_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            result = run_mechanism_experiment(
                vault,
                run_id="run-wrapper-promote",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                log_summary="Wrapper-driven mechanism experiment",
                mutation_command=f"{sys.executable} tools/mutate_success.py",
                check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                require_signoff=False,
                signoff_status="approved",
                signoff_by="human",
                signoff_ts="2026-04-14T00:00:00Z",
                apply_mode="live",
                finalize=True,
                context=fixed_context(),
            )

            run_dir = vault / "runs" / "run-wrapper-promote"
            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            run_artifact_fingerprint = json.loads((run_dir / "run-artifact-fingerprint.json").read_text(encoding="utf-8"))
            promotion_decision_trends = json.loads(
                (vault / "ops" / "reports" / "promotion-decision-trends.json").read_text(encoding="utf-8")
            )
            run_ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            planning_validation = json.loads((run_dir / "planning-validation.json").read_text(encoding="utf-8"))
            changed_manifest = json.loads((run_dir / "changed-files-manifest.json").read_text(encoding="utf-8"))
            shadow_apply_report = json.loads((run_dir / "shadow-apply-report.json").read_text(encoding="utf-8"))
            rollback_rehearsal_report = json.loads(
                (run_dir / "rollback-rehearsal-report.json").read_text(encoding="utf-8")
            )
            behavior_delta = json.loads((run_dir / "behavior-delta.json").read_text(encoding="utf-8"))
            run_telemetry = json.loads((run_dir / "run-telemetry.json").read_text(encoding="utf-8"))
            baseline_eval = json.loads((run_dir / "baseline-eval.json").read_text(encoding="utf-8"))
            candidate_lint = json.loads((run_dir / "candidate-lint.json").read_text(encoding="utf-8"))
            candidate_mechanism = json.loads(
                (run_dir / "candidate-mechanism-assessment.json").read_text(encoding="utf-8")
            )
            system_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")
            example_text = (vault / "ops" / "scripts" / "example.py").read_text(encoding="utf-8")
            test_text = (vault / "tests" / "test_example.py").read_text(encoding="utf-8")

            self.assertEqual(result["decision"], "PROMOTE")
            self.assertEqual(result["decision_record"]["decision"], "PROMOTE")
            self.assertTrue(result["finalized"])
            self.assertEqual(result["planning_gate"]["phase"], "mechanism_finalized")
            self.assertEqual(result["planning_gate"]["status"], "pass")
            self.assertEqual(result["changed_files_manifest"], "runs/run-wrapper-promote/changed-files-manifest.json")
            self.assertEqual(result["behavior_delta"], "runs/run-wrapper-promote/behavior-delta.json")
            self.assertEqual(result["workspace_preparation"]["mode"], "full_copy")
            self.assertEqual(
                result["workspace_preparation"]["copied_file_count"],
                result["workspace_preparation"]["baseline_file_count"],
            )
            self.assertGreaterEqual(result["workspace_preparation"]["phase_durations"]["digest"], 0.0)
            self.assertGreaterEqual(result["workspace_preparation"]["phase_durations"]["copy"], 0.0)
            self.assertGreaterEqual(result["workspace_preparation"]["phase_durations"]["total"], 0.0)
            self.assertEqual(result["apply_mode"], "live")
            self.assertEqual(result["apply_status"], "live_applied")
            self.assertTrue(result["live_applied"])
            self.assertEqual(result["shadow_apply_report"], "runs/run-wrapper-promote/shadow-apply-report.json")
            self.assertEqual(
                result["rollback_rehearsal_report"],
                "runs/run-wrapper-promote/rollback-rehearsal-report.json",
            )
            self.assertEqual(result["improvement_observations"], "runs/run-wrapper-promote/improvement-observations.json")
            self.assertEqual(result["run_artifact_fingerprint"], "runs/run-wrapper-promote/run-artifact-fingerprint.json")
            self.assertEqual(result["promotion_decision_trends"], "ops/reports/promotion-decision-trends.json")
            self.assertEqual(promotion_report["log"]["status"], "recorded")
            self.assertEqual(promotion_report["decision_record"]["decision"], "PROMOTE")
            self.assertEqual(run_telemetry["decision_record"]["decision"], "PROMOTE")
            self.assertEqual(run_artifact_fingerprint["summary"]["artifact_count"], len(run_artifact_fingerprint["artifacts"]))
            self.assertIn(
                "runs/run-wrapper-promote/run-telemetry.json",
                [item["path"] for item in run_artifact_fingerprint["artifacts"]],
            )
            behavior_fingerprint = next(
                item for item in run_artifact_fingerprint["artifacts"]
                if item["path"] == "runs/run-wrapper-promote/behavior-delta.json"
            )
            self.assertEqual(behavior_fingerprint["artifact_role"], "behavior_delta")
            self.assertEqual(behavior_fingerprint["schema"], "ops/schemas/behavior-delta.schema.json")
            shadow_fingerprint = next(
                item for item in run_artifact_fingerprint["artifacts"]
                if item["path"] == "runs/run-wrapper-promote/shadow-apply-report.json"
            )
            self.assertEqual(shadow_fingerprint["artifact_role"], "shadow_apply_report")
            self.assertEqual(shadow_fingerprint["schema"], "ops/schemas/shadow-apply-report.schema.json")
            rollback_fingerprint = next(
                item for item in run_artifact_fingerprint["artifacts"]
                if item["path"] == "runs/run-wrapper-promote/rollback-rehearsal-report.json"
            )
            self.assertEqual(rollback_fingerprint["artifact_role"], "rollback_rehearsal_report")
            self.assertEqual(rollback_fingerprint["schema"], "ops/schemas/rollback-rehearsal-report.schema.json")
            self.assertEqual(promotion_decision_trends["decision_counts"], {"PROMOTE": 1})
            self.assertEqual(run_ledger["status"], "complete")
            rehearsed_event = next(
                event for event in run_ledger["events"] if event["type"] == "workspace_rollback_rehearsed"
            )
            self.assertIn("runs/run-wrapper-promote/rollback-rehearsal-report.json", rehearsed_event["artifacts"])
            applied_event = next(event for event in run_ledger["events"] if event["type"] == "workspace_applied")
            self.assertIn("runs/run-wrapper-promote/shadow-apply-report.json", applied_event["artifacts"])
            self.assertIn("runs/run-wrapper-promote/rollback-rehearsal-report.json", applied_event["artifacts"])
            finalized_event = next(event for event in run_ledger["events"] if event["type"] == "finalized")
            self.assertEqual(finalized_event["decision_event"]["decision"], "PROMOTE")
            self.assertEqual(planning_validation["status"], "PASS")
            self.assertEqual(
                promotion_report["inputs"]["behavior_delta"],
                "runs/run-wrapper-promote/behavior-delta.json",
            )
            self.assertEqual(run_telemetry["behavior_delta"], "runs/run-wrapper-promote/behavior-delta.json")
            self.assertEqual(run_telemetry["apply_mode"], "live")
            self.assertEqual(run_telemetry["apply_status"], "live_applied")
            self.assertTrue(run_telemetry["live_applied"])
            self.assertEqual(
                run_telemetry["shadow_apply_report"],
                "runs/run-wrapper-promote/shadow-apply-report.json",
            )
            self.assertEqual(
                run_telemetry["rollback_rehearsal_report"],
                "runs/run-wrapper-promote/rollback-rehearsal-report.json",
            )
            self.assertEqual(run_telemetry["workspace_preparation"], result["workspace_preparation"])
            self.assertEqual(baseline_eval["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(candidate_lint["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(candidate_mechanism["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(changed_manifest["summary"]["total_changed_files"], 2)
            self.assertEqual(
                [item["path"] for item in changed_manifest["files"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertEqual(shadow_apply_report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(shadow_apply_report["status"], "ready_for_live_apply")
            self.assertEqual(shadow_apply_report["summary"]["total_changed_files"], 2)
            self.assertEqual(
                [item["path"] for item in shadow_apply_report["files"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertEqual(rollback_rehearsal_report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(rollback_rehearsal_report["status"], "pass")
            self.assertEqual(rollback_rehearsal_report["summary"]["total_changed_files"], 2)
            self.assertEqual(rollback_rehearsal_report["summary"]["apply_verified"], 2)
            self.assertEqual(rollback_rehearsal_report["summary"]["rollback_verified"], 2)
            self.assertEqual(rollback_rehearsal_report["summary"]["failed"], 0)
            self.assertEqual(
                [item["path"] for item in rollback_rehearsal_report["files"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertTrue(behavior_delta["summary"]["behavior_changed"])
            self.assertEqual(
                [item["target"] for item in behavior_delta["deltas"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertIn("Finalize mechanism run run-wrapper-promote (PROMOTE)", system_log)
            self.assertTrue((run_dir / "baseline-eval.json").exists())
            self.assertTrue((run_dir / "candidate-eval.json").exists())
            self.assertTrue((run_dir / "improvement-observations.json").exists())
            self.assertIn("return 1 if value > 0 else -1", example_text)
            self.assertIn("test_subject_zero", test_text)
            self.assertTrue((run_dir / "mutation-command.stdout.txt").exists())
            self.assertTrue((run_dir / "repo-health.stdout.txt").exists())

    def test_wrapper_defaults_to_live_apply_and_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            result = run_mechanism_experiment(
                vault,
                run_id="run-wrapper-default-live",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                log_summary="Wrapper-driven default live mechanism experiment",
                mutation_command=f"{sys.executable} tools/mutate_success.py",
                check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                require_signoff=False,
                signoff_status="approved",
                signoff_by="human",
                signoff_ts="2026-04-14T00:00:00Z",
                finalize=True,
                context=fixed_context(),
            )

            run_dir = vault / "runs" / "run-wrapper-default-live"
            run_ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            run_telemetry = json.loads((run_dir / "run-telemetry.json").read_text(encoding="utf-8"))
            example_text = (vault / "ops" / "scripts" / "example.py").read_text(encoding="utf-8")
            test_text = (vault / "tests" / "test_example.py").read_text(encoding="utf-8")
            system_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")

            self.assertEqual(result["decision"], "PROMOTE")
            self.assertEqual(result["workspace_preparation"]["mode"], "full_copy")
            self.assertEqual(result["apply_mode"], "live")
            self.assertEqual(result["apply_status"], "live_applied")
            self.assertTrue(result["live_applied"])
            self.assertTrue(result["finalized"])
            self.assertEqual(result["finalize_result"]["run_id"], "run-wrapper-default-live")
            self.assertEqual(
                result["shadow_apply_report"],
                "runs/run-wrapper-default-live/shadow-apply-report.json",
            )
            self.assertEqual(
                result["rollback_rehearsal_report"],
                "runs/run-wrapper-default-live/rollback-rehearsal-report.json",
            )
            self.assertTrue((run_dir / "shadow-apply-report.json").exists())
            self.assertTrue((run_dir / "rollback-rehearsal-report.json").exists())
            self.assertIn("return 1 if value > 0 else -1", example_text)
            self.assertIn("test_subject_zero", test_text)
            self.assertIn("Finalize mechanism run run-wrapper-default-live (PROMOTE)", system_log)
            self.assertEqual(run_telemetry["apply_mode"], "live")
            self.assertEqual(run_telemetry["apply_status"], "live_applied")
            self.assertTrue(run_telemetry["live_applied"])
            self.assertTrue(run_telemetry["finalized"])
            self.assertEqual(run_telemetry["workspace_preparation"], result["workspace_preparation"])
            event_types = [event["type"] for event in run_ledger["events"]]
            self.assertIn("workspace_rollback_rehearsed", event_types)
            self.assertIn("workspace_applied", event_types)
            self.assertIn("finalized", event_types)

    def test_wrapper_sparse_manifest_uses_copied_universe_diff_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            set_policy_value(
                vault,
                ("auto_improve_policy", "workspace_preparation"),
                {"mode": "sparse_manifest", "declared_dependencies": ["tools/"]},
            )

            def fake_capture_reports(
                _vault: Path,
                *,
                run_id: str,
                phase: str,
                policy: dict,
                policy_path_text: str,
                primary_targets: list[str],
                supporting_targets: list[str],
                test_files: list[str],
                artifact_vault: Path | None = None,
                context: RuntimeContext | None = None,
            ) -> dict:
                self.assertEqual(run_id, "run-wrapper-sparse")
                self.assertEqual(policy_path_text, "ops/policies/wiki-maintainer-policy.yaml")
                self.assertTrue(policy)
                self.assertIn(artifact_vault, {None, vault.resolve()})
                artifacts = write_stubbed_capture_artifacts(
                    vault,
                    run_id=run_id,
                    phase=phase,
                    primary_targets=primary_targets,
                    supporting_targets=supporting_targets,
                    test_files=test_files,
                )
                if phase == "candidate":
                    mechanism_path = vault / artifacts["mechanism"]
                    mechanism_report = json.loads(mechanism_path.read_text(encoding="utf-8"))
                    for key in ("structural_metrics", "total_structural_metrics"):
                        mechanism_report[key]["test_case_count"] = len(test_files) + 1
                    mechanism_path.write_text(
                        json.dumps(mechanism_report, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                return artifacts

            def fake_run_command(
                command: str,
                *,
                cwd: Path,
                timeout_seconds: int,
                argv: list[str] | None = None,
            ) -> dict:
                self.assertNotEqual(cwd, vault.resolve())
                self.assertEqual(cwd.name, "vault")
                self.assertIsNotNone(argv)
                if "repo health ok" in command:
                    return successful_command_result(command, stdout="repo health ok\n")
                (cwd / "ops" / "scripts" / "example.py").write_text(
                    "def subject(value):\n"
                    "    if value == 0:\n"
                    "        return 0\n"
                    "    return 1 if value > 0 else -1\n",
                    encoding="utf-8",
                )
                test_path = cwd / "tests" / "test_example.py"
                test_path.write_text(
                    test_path.read_text(encoding="utf-8")
                    + "\n\ndef test_subject_zero():\n    assert True\n",
                    encoding="utf-8",
                )
                return successful_command_result(command, stdout="mutation applied\n")

            with (
                mock.patch.object(
                    mechanism_run_capture_runtime,
                    "_capture_reports",
                    side_effect=fake_capture_reports,
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    side_effect=fake_run_command,
                ),
            ):
                result = run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-sparse",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary="Wrapper-driven sparse mechanism experiment",
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-14T00:00:00Z",
                    apply_mode="canary_only",
                    finalize=True,
                    context=fixed_context(),
                )

            run_dir = vault / "runs" / "run-wrapper-sparse"
            run_telemetry = json.loads((run_dir / "run-telemetry.json").read_text(encoding="utf-8"))
            changed_manifest = json.loads((run_dir / "changed-files-manifest.json").read_text(encoding="utf-8"))
            example_text = (vault / "ops" / "scripts" / "example.py").read_text(encoding="utf-8")
            test_text = (vault / "tests" / "test_example.py").read_text(encoding="utf-8")

            self.assertEqual(result["decision"], "PROMOTE")
            self.assertEqual(result["workspace_preparation"]["mode"], "sparse_manifest")
            self.assertEqual(result["workspace_preparation"]["diff_model"], "copied_universe")
            self.assertLess(
                result["workspace_preparation"]["copied_file_count"],
                result["workspace_preparation"]["baseline_file_count"],
            )
            self.assertEqual(result["apply_status"], "canary_ready")
            self.assertFalse(result["live_applied"])
            self.assertFalse(result["finalized"])
            self.assertEqual(run_telemetry["workspace_preparation"], result["workspace_preparation"])
            self.assertEqual(changed_manifest["diff_universe"]["model"], "copied_universe")
            self.assertEqual(
                changed_manifest["diff_universe"]["baseline_file_count"],
                result["workspace_preparation"]["diff_universe_file_count"],
            )
            self.assertEqual(
                [item["path"] for item in changed_manifest["files"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertIn("return 1\n", example_text)
            self.assertNotIn("test_subject_zero", test_text)

    def test_wrapper_holds_without_finalization_when_signoff_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            def fake_capture_reports(
                _vault: Path,
                *,
                run_id: str,
                phase: str,
                policy: dict,
                policy_path_text: str,
                primary_targets: list[str],
                supporting_targets: list[str],
                test_files: list[str],
                artifact_vault: Path | None = None,
                context: RuntimeContext | None = None,
            ) -> dict:
                self.assertEqual(run_id, "run-wrapper-hold")
                self.assertEqual(primary_targets, ["ops/scripts/example.py"])
                self.assertEqual(supporting_targets, [])
                self.assertEqual(test_files, ["tests/test_example.py"])
                self.assertTrue(policy)
                self.assertEqual(policy_path_text, "ops/policies/wiki-maintainer-policy.yaml")
                self.assertIn(artifact_vault, {None, vault.resolve()})
                return {
                    "lint": f"runs/{run_id}/{phase}-lint.json",
                    "eval": f"runs/{run_id}/{phase}-eval.json",
                    "mechanism": f"runs/{run_id}/{phase}-mechanism-assessment.json",
                }

            def fake_run_command(
                command: str,
                *,
                cwd: Path,
                timeout_seconds: int,
                argv: list[str] | None = None,
            ) -> dict:
                self.assertNotEqual(cwd, vault.resolve())
                self.assertEqual(cwd.name, "vault")
                self.assertIsNotNone(argv)
                if "repo health ok" in command:
                    return successful_command_result(command, stdout="repo health ok\n")
                return successful_command_result(command, stdout="mutation applied\n")

            fake_build_promotion_report = forced_promotion_report_builder(
                PromotionReportCallExpectation(
                    run_id="run-wrapper-hold",
                    primary_targets=("ops/scripts/example.py",),
                    supporting_targets=(),
                    log_summary="Wrapper-driven mechanism experiment hold",
                    require_signoff=False,
                    signoff_status="pending",
                    signoff_by="",
                    signoff_ts="",
                    changed_files_manifest_path="runs/run-wrapper-hold/changed-files-manifest.json",
                    behavior_delta_path="runs/run-wrapper-hold/behavior-delta.json",
                ),
                ForcedPromotionReportPatch(
                    decision="HOLD",
                    signoff_status="pending",
                    signoff_by="",
                    signoff_ts="",
                    decision_contract_entries=PENDING_SIGNOFF_DECISION_CONTRACT,
                ),
            )

            with (
                mock.patch.object(
                    mechanism_run_capture_runtime,
                    "_capture_reports",
                    side_effect=fake_capture_reports,
                ) as capture_reports,
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    side_effect=fake_run_command,
                ) as run_command,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "_build_promotion_report",
                    side_effect=fake_build_promotion_report,
                ) as build_promotion_report,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "validate_run_dir",
                    return_value={"phase": "mechanism_evaluated", "status": "pass"},
                ) as validate_run_dir,
                mock.patch.object(mechanism_run_promotion_runtime, "finalize_run") as finalize_run,
            ):
                result = run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-hold",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary="Wrapper-driven mechanism experiment hold",
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=False,
                    signoff_status="pending",
                    signoff_by="",
                    signoff_ts="",
                    finalize=True,
                )

            run_dir = vault / "runs" / "run-wrapper-hold"
            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            run_ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            changed_manifest = json.loads((run_dir / "changed-files-manifest.json").read_text(encoding="utf-8"))
            system_log = (vault / "system" / "system-log.md").read_text(encoding="utf-8")

            self.assertEqual(capture_reports.call_count, 2)
            self.assertEqual(run_command.call_count, 2)
            build_promotion_report.assert_called_once()
            validate_run_dir.assert_called_once()
            finalize_run.assert_not_called()
            self.assertEqual(result["decision"], "HOLD")
            self.assertFalse(result["finalized"])
            self.assertEqual(result["planning_gate"]["phase"], "mechanism_evaluated")
            self.assertEqual(result["planning_gate"]["status"], "pass")
            self.assertEqual(result["improvement_observations"], "runs/run-wrapper-hold/improvement-observations.json")
            self.assertEqual(promotion_report["log"]["status"], "pending")
            self.assertEqual(run_ledger["status"], "ready")
            self.assertEqual(changed_manifest["summary"]["total_changed_files"], 0)
            self.assertNotIn("run-wrapper-hold", system_log)

    def test_wrapper_hold_keeps_nonempty_candidate_changes_run_local(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            def fake_capture_reports(
                _vault: Path,
                *,
                run_id: str,
                phase: str,
                policy: dict,
                policy_path_text: str,
                primary_targets: list[str],
                supporting_targets: list[str],
                test_files: list[str],
                artifact_vault: Path | None = None,
                context: RuntimeContext | None = None,
            ) -> dict:
                self.assertEqual(run_id, "run-wrapper-hold-nonempty")
                self.assertEqual(policy_path_text, "ops/policies/wiki-maintainer-policy.yaml")
                self.assertTrue(policy)
                self.assertIn(artifact_vault, {None, vault.resolve()})
                return write_stubbed_capture_artifacts(
                    vault,
                    run_id=run_id,
                    phase=phase,
                    primary_targets=primary_targets,
                    supporting_targets=supporting_targets,
                    test_files=test_files,
                )

            def fake_run_command(
                command: str,
                *,
                cwd: Path,
                timeout_seconds: int,
                argv: list[str] | None = None,
            ) -> dict:
                self.assertNotEqual(cwd, vault.resolve())
                self.assertEqual(cwd.name, "vault")
                self.assertIsNotNone(argv)
                if "repo health ok" in command:
                    return successful_command_result(command, stdout="repo health ok\n")
                (cwd / "ops" / "scripts" / "example.py").write_text(
                    "def subject(value):\n"
                    "    if value == 0:\n"
                    "        return 0\n"
                    "    return 1 if value > 0 else -1\n",
                    encoding="utf-8",
                )
                test_path = cwd / "tests" / "test_example.py"
                test_path.write_text(
                    test_path.read_text(encoding="utf-8") + "\n\ndef test_subject_zero():\n    assert True\n",
                    encoding="utf-8",
                )
                return successful_command_result(command, stdout="mutation applied\n")

            fake_build_promotion_report = forced_promotion_report_builder(
                PromotionReportCallExpectation(
                    run_id="run-wrapper-hold-nonempty",
                    primary_targets=("ops/scripts/example.py",),
                    supporting_targets=(),
                    log_summary="Wrapper-driven mechanism experiment hold with candidate changes",
                    require_signoff=True,
                    signoff_status="pending",
                    signoff_by="",
                    signoff_ts="",
                    changed_files_manifest_path="runs/run-wrapper-hold-nonempty/changed-files-manifest.json",
                    behavior_delta_path="runs/run-wrapper-hold-nonempty/behavior-delta.json",
                ),
                ForcedPromotionReportPatch(
                    decision="HOLD",
                    signoff_required=True,
                    signoff_status="pending",
                    signoff_by="",
                    signoff_ts="",
                    decision_contract_entries=PENDING_SIGNOFF_DECISION_CONTRACT,
                ),
            )

            with (
                mock.patch.object(
                    mechanism_run_capture_runtime,
                    "_capture_reports",
                    side_effect=fake_capture_reports,
                ) as capture_reports,
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    side_effect=fake_run_command,
                ) as run_command,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "_build_promotion_report",
                    side_effect=fake_build_promotion_report,
                ) as build_promotion_report,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "validate_run_dir",
                    return_value={"phase": "mechanism_evaluated", "status": "pass"},
                ) as validate_run_dir,
                mock.patch.object(mechanism_run_promotion_runtime, "finalize_run") as finalize_run,
            ):
                result = run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-hold-nonempty",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary="Wrapper-driven mechanism experiment hold with candidate changes",
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=True,
                    signoff_status="pending",
                    signoff_by="",
                    signoff_ts="",
                    finalize=True,
                )

            run_dir = vault / "runs" / "run-wrapper-hold-nonempty"
            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            changed_manifest = json.loads((run_dir / "changed-files-manifest.json").read_text(encoding="utf-8"))
            example_text = (vault / "ops" / "scripts" / "example.py").read_text(encoding="utf-8")
            test_text = (vault / "tests" / "test_example.py").read_text(encoding="utf-8")

            self.assertEqual(capture_reports.call_count, 2)
            self.assertEqual(run_command.call_count, 2)
            build_promotion_report.assert_called_once()
            validate_run_dir.assert_called_once()
            finalize_run.assert_not_called()
            self.assertEqual(result["decision"], "HOLD")
            self.assertFalse(result["finalized"])
            self.assertEqual(result["planning_gate"]["phase"], "mechanism_evaluated")
            self.assertEqual(result["planning_gate"]["status"], "pass")
            self.assertEqual(
                result["improvement_observations"],
                "runs/run-wrapper-hold-nonempty/improvement-observations.json",
            )
            self.assertEqual(promotion_report["decision"], "HOLD")
            self.assertEqual(changed_manifest["summary"]["total_changed_files"], 2)
            self.assertEqual(
                [item["path"] for item in changed_manifest["files"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertIn("return 1", example_text)
            self.assertNotIn("test_subject_zero", test_text)

    def test_wrapper_discards_out_of_scope_workspace_changes_without_applying_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            def fake_capture_reports(
                _vault: Path,
                *,
                run_id: str,
                phase: str,
                policy: dict,
                policy_path_text: str,
                primary_targets: list[str],
                supporting_targets: list[str],
                test_files: list[str],
                artifact_vault: Path | None = None,
                context: RuntimeContext | None = None,
            ) -> dict:
                self.assertEqual(run_id, "run-wrapper-discard")
                self.assertEqual(policy_path_text, "ops/policies/wiki-maintainer-policy.yaml")
                self.assertTrue(policy)
                self.assertIn(artifact_vault, {None, vault.resolve()})
                return write_stubbed_capture_artifacts(
                    vault,
                    run_id=run_id,
                    phase=phase,
                    primary_targets=primary_targets,
                    supporting_targets=supporting_targets,
                    test_files=test_files,
                )

            def fake_run_command(
                command: str,
                *,
                cwd: Path,
                timeout_seconds: int,
                argv: list[str] | None = None,
            ) -> dict:
                self.assertNotEqual(cwd, vault.resolve())
                self.assertEqual(cwd.name, "vault")
                self.assertIsNotNone(argv)
                if "repo health ok" in command:
                    return successful_command_result(command, stdout="repo health ok\n")
                (cwd / "README.md").write_text("workspace-only out of scope change\n", encoding="utf-8")
                (cwd / "ops" / "scripts" / "example.py").write_text(
                    "def subject(value):\n"
                    "    return 2 if value > 0 else 0\n",
                    encoding="utf-8",
                )
                return successful_command_result(command, stdout="mutation applied\n")

            with (
                mock.patch.object(
                    mechanism_run_capture_runtime,
                    "_capture_reports",
                    side_effect=fake_capture_reports,
                ) as capture_reports,
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    side_effect=fake_run_command,
                ) as run_command,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "validate_run_dir",
                    return_value={"phase": "mechanism_evaluated", "status": "pass"},
                ) as validate_run_dir,
            ):
                result = run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-discard",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary="Wrapper-driven mechanism experiment discard",
                    mutation_command=f"{sys.executable} tools/mutate_out_of_scope.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-14T00:00:00Z",
                    finalize=False,
                )

            run_dir = vault / "runs" / "run-wrapper-discard"
            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            changed_manifest = json.loads((run_dir / "changed-files-manifest.json").read_text(encoding="utf-8"))
            example_text = (vault / "ops" / "scripts" / "example.py").read_text(encoding="utf-8")

            self.assertEqual(capture_reports.call_count, 2)
            self.assertEqual(run_command.call_count, 2)
            validate_run_dir.assert_called_once()
            self.assertEqual(result["decision"], "DISCARD")
            self.assertFalse(result["finalized"])
            self.assertEqual(result["planning_gate"]["phase"], "mechanism_evaluated")
            self.assertEqual(result["planning_gate"]["status"], "pass")
            self.assertEqual(result["improvement_observations"], "runs/run-wrapper-discard/improvement-observations.json")
            self.assertEqual(promotion_report["decision"], "DISCARD")
            self.assertEqual(
                [item["path"] for item in changed_manifest["files"]],
                ["README.md", "ops/scripts/example.py"],
            )
            scope_check = next(
                check for check in promotion_report["checks"] if check["id"] == "changed_files_manifest_scope"
            )
            self.assertEqual(scope_check["status"], "FAIL")
            self.assertIn("README.md", scope_check["detail"])
            self.assertIn("return 1", example_text)
            self.assertFalse((vault / "README.md").exists())

    def test_wrapper_apply_barrier_rejects_promoted_changes_outside_allowed_apply_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            (vault / "README.md").write_text("live readme\n", encoding="utf-8")

            def fake_capture_reports(
                _vault: Path,
                *,
                run_id: str,
                phase: str,
                policy: dict,
                policy_path_text: str,
                primary_targets: list[str],
                supporting_targets: list[str],
                test_files: list[str],
                artifact_vault: Path | None = None,
                context: RuntimeContext | None = None,
            ) -> dict:
                self.assertEqual(run_id, "run-wrapper-apply-guard")
                self.assertEqual(policy_path_text, "ops/policies/wiki-maintainer-policy.yaml")
                self.assertTrue(policy)
                self.assertIn(artifact_vault, {None, vault.resolve()})
                return write_stubbed_capture_artifacts(
                    vault,
                    run_id=run_id,
                    phase=phase,
                    primary_targets=primary_targets,
                    supporting_targets=supporting_targets,
                    test_files=test_files,
                )

            def fake_run_command(
                command: str,
                *,
                cwd: Path,
                timeout_seconds: int,
                argv: list[str] | None = None,
            ) -> dict:
                self.assertNotEqual(cwd, vault.resolve())
                self.assertEqual(cwd.name, "vault")
                self.assertIsNotNone(argv)
                if "repo health ok" in command:
                    return successful_command_result(command, stdout="repo health ok\n")
                (cwd / "README.md").write_text("workspace readme\n", encoding="utf-8")
                (cwd / "ops" / "scripts" / "example.py").write_text(
                    "def subject(value):\n"
                    "    return 2 if value > 0 else 0\n",
                    encoding="utf-8",
                )
                return successful_command_result(command, stdout="mutation applied\n")

            fake_build_promotion_report = forced_promotion_report_builder(
                PromotionReportCallExpectation(
                    run_id="run-wrapper-apply-guard",
                    primary_targets=("ops/scripts/example.py",),
                    supporting_targets=("README.md",),
                    log_summary="Wrapper apply guard rejects README changes",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-16T00:00:00Z",
                    changed_files_manifest_path="runs/run-wrapper-apply-guard/changed-files-manifest.json",
                    behavior_delta_path="runs/run-wrapper-apply-guard/behavior-delta.json",
                ),
                ForcedPromotionReportPatch(
                    decision="PROMOTE",
                    checks=(
                        {
                            "id": "changed_files_manifest_allowed_apply_roots",
                            "status": "PASS",
                            "detail": "forced promotion to verify apply barrier independently of gate output",
                        },
                    ),
                ),
            )

            with (
                mock.patch.object(
                    mechanism_run_capture_runtime,
                    "_capture_reports",
                    side_effect=fake_capture_reports,
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    side_effect=fake_run_command,
                ),
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "_build_promotion_report",
                    side_effect=fake_build_promotion_report,
                ),
            ):
                with self.assertRaisesRegex(
                    filesystem_runtime.FilesystemTransactionError,
                    "outside allowed_apply_roots: README.md",
                ):
                    run_mechanism_experiment(
                        vault,
                        run_id="run-wrapper-apply-guard",
                        policy_path="ops/policies/wiki-maintainer-policy.yaml",
                        primary_targets=["ops/scripts/example.py"],
                        supporting_targets=["README.md"],
                        test_files=["tests/test_example.py"],
                        log_summary="Wrapper apply guard rejects README changes",
                        mutation_command=f"{sys.executable} tools/mutate_out_of_scope.py",
                        check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                        require_signoff=False,
                        signoff_status="approved",
                        signoff_by="human",
                        signoff_ts="2026-04-16T00:00:00Z",
                        finalize=False,
                    )

            changed_manifest = json.loads(
                (vault / "runs" / "run-wrapper-apply-guard" / "changed-files-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                [item["path"] for item in changed_manifest["files"]],
                ["README.md", "ops/scripts/example.py"],
            )
            self.assertEqual(
                (vault / "README.md").read_text(encoding="utf-8"),
                "live readme\n",
            )
            self.assertIn(
                "return 1",
                (vault / "ops" / "scripts" / "example.py").read_text(encoding="utf-8"),
            )

    def test_wrapper_ignores_ephemeral_workspace_noise_in_changed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            (vault / ".obsidian").mkdir(exist_ok=True)
            (vault / ".obsidian" / "workspace.json").write_text('{"workspace": "live"}\n', encoding="utf-8")
            (vault / ".venv").mkdir(exist_ok=True)
            (vault / ".venv" / "marker.txt").write_text("live env marker\n", encoding="utf-8")
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "raw-registry-preflight-report.json").write_text(
                '{"status": "live"}\n',
                encoding="utf-8",
            )
            (vault / "tmp").mkdir(exist_ok=True)
            (vault / "tmp" / "artifact-freshness-report-check.json").write_text(
                '{"status": "live"}\n',
                encoding="utf-8",
            )
            (vault / "tmp" / "script-output-surfaces.candidate.json").write_text(
                '{"candidate": true}\n',
                encoding="utf-8",
            )

            def fake_capture_reports(
                _vault: Path,
                *,
                run_id: str,
                phase: str,
                policy: dict,
                policy_path_text: str,
                primary_targets: list[str],
                supporting_targets: list[str],
                test_files: list[str],
                artifact_vault: Path | None = None,
                context: RuntimeContext | None = None,
            ) -> dict:
                self.assertEqual(run_id, "run-wrapper-ephemeral-noise")
                self.assertEqual(policy_path_text, "ops/policies/wiki-maintainer-policy.yaml")
                self.assertTrue(policy)
                self.assertIn(artifact_vault, {None, vault.resolve()})
                return write_stubbed_capture_artifacts(
                    vault,
                    run_id=run_id,
                    phase=phase,
                    primary_targets=primary_targets,
                    supporting_targets=supporting_targets,
                    test_files=test_files,
                )

            def fake_run_command(
                command: str,
                *,
                cwd: Path,
                timeout_seconds: int,
                argv: list[str] | None = None,
            ) -> dict:
                self.assertNotEqual(cwd, vault.resolve())
                self.assertEqual(cwd.name, "vault")
                self.assertIsNotNone(argv)
                if "repo health ok" in command:
                    return successful_command_result(command, stdout="repo health ok\n")
                (cwd / "ops" / "scripts" / "example.py").write_text(
                    "def subject(value):\n"
                    "    if value == 0:\n"
                    "        return 0\n"
                    "    return 1 if value > 0 else -1\n",
                    encoding="utf-8",
                )
                test_path = cwd / "tests" / "test_example.py"
                test_path.write_text(
                    test_path.read_text(encoding="utf-8") + "\n\ndef test_subject_zero():\n    assert True\n",
                    encoding="utf-8",
                )
                (cwd / ".obsidian").mkdir(parents=True, exist_ok=True)
                (cwd / ".obsidian" / "workspace.json").write_text('{"workspace": "noise"}\n', encoding="utf-8")
                (cwd / ".venv" / "lib64" / "python3.12" / "site-packages").mkdir(parents=True, exist_ok=True)
                (cwd / ".venv" / "lib64" / "python3.12" / "site-packages" / "noise.py").write_text(
                    "sentinel = 1\n",
                    encoding="utf-8",
                )
                (cwd / "ops" / "reports" / "raw-registry-preflight-report.json").write_text(
                    '{"status": "candidate"}\n',
                    encoding="utf-8",
                )
                (cwd / "tmp" / "artifact-freshness-report-check.json").write_text(
                    '{"status": "candidate"}\n',
                    encoding="utf-8",
                )
                (cwd / "tmp" / "script-output-surfaces.candidate.json").unlink()
                return successful_command_result(command, stdout="mutation applied\n")

            fake_build_promotion_report = forced_promotion_report_builder(
                PromotionReportCallExpectation(
                    run_id="run-wrapper-ephemeral-noise",
                    primary_targets=("ops/scripts/example.py",),
                    supporting_targets=(),
                    log_summary="Wrapper-driven mechanism experiment ignores ephemeral workspace noise",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-15T00:00:00Z",
                    changed_files_manifest_path="runs/run-wrapper-ephemeral-noise/changed-files-manifest.json",
                    behavior_delta_path="runs/run-wrapper-ephemeral-noise/behavior-delta.json",
                ),
                ForcedPromotionReportPatch(
                    decision="PROMOTE",
                    checks=(
                        {
                            "id": "changed_files_manifest_scope",
                            "status": "PASS",
                            "detail": "thin wrapper smoke keeps the PASS decision visible to the caller",
                        },
                    ),
                ),
            )

            with (
                mock.patch.object(
                    mechanism_run_capture_runtime,
                    "_capture_reports",
                    side_effect=fake_capture_reports,
                ) as capture_reports,
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    side_effect=fake_run_command,
                ) as run_command,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "_build_promotion_report",
                    side_effect=fake_build_promotion_report,
                ) as build_promotion_report,
                mock.patch.object(
                    mechanism_run_promotion_runtime,
                    "validate_run_dir",
                    return_value={"phase": "mechanism_evaluated", "status": "pass"},
                ) as validate_run_dir,
            ):
                result = run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-ephemeral-noise",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary="Wrapper-driven mechanism experiment ignores ephemeral workspace noise",
                    mutation_command=f"{sys.executable} tools/mutate_success_with_ephemeral_noise.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-15T00:00:00Z",
                    finalize=False,
                )

            run_dir = vault / "runs" / "run-wrapper-ephemeral-noise"
            promotion_report = json.loads((run_dir / "promotion-report.json").read_text(encoding="utf-8"))
            changed_manifest = json.loads((run_dir / "changed-files-manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(capture_reports.call_count, 2)
            self.assertEqual(run_command.call_count, 2)
            build_promotion_report.assert_called_once()
            validate_run_dir.assert_called_once()
            self.assertEqual(result["decision"], "PROMOTE")
            self.assertEqual(result["planning_gate"]["phase"], "mechanism_evaluated")
            self.assertEqual(result["planning_gate"]["status"], "pass")
            self.assertEqual(
                result["improvement_observations"],
                "runs/run-wrapper-ephemeral-noise/improvement-observations.json",
            )
            scope_check = next(
                check for check in promotion_report["checks"] if check["id"] == "changed_files_manifest_scope"
            )
            self.assertEqual(scope_check["status"], "PASS")
            self.assertEqual(
                [item["path"] for item in changed_manifest["files"]],
                ["ops/scripts/example.py", "tests/test_example.py"],
            )
            self.assertEqual(changed_manifest["summary"]["total_changed_files"], 2)
            self.assertEqual(
                {
                    item["path"]: item["reason"]
                    for item in changed_manifest["ignored_changes"]["files"]
                },
                {
                    "ops/reports/raw-registry-preflight-report.json": "generated_report_surface",
                    "tmp/artifact-freshness-report-check.json": "transient_workspace_surface",
                    "tmp/script-output-surfaces.candidate.json": "transient_workspace_surface",
                },
            )
            self.assertEqual(changed_manifest["ignored_changes"]["summary"]["total_ignored_files"], 3)

if __name__ == "__main__":
    unittest.main()
