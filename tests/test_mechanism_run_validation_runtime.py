from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism_run_validation_runtime import (
    build_changed_files_primary_target_touched_check,
    build_changed_files_scope_gate_check,
    build_event_sequence_phase_checks,
    build_report_consistency_checks,
    build_test_surface_phase_check,
    display_report_vault,
    normalize_mechanism_artifact_bundle,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.promotion_gate_mechanism_runtime import (
    MechanismGateInputs,
    mechanism_class_report,
)

from tests.test_promotion_gate_equal_score import (
    LIVE_POLICY_VERSION,
    behavior_delta_report,
    changed_files_manifest,
    eval_report,
    lint_report,
    mechanism_report,
    run_ledger,
    seed_promotion_vault,
)


def evaluated_run_ledger(primary_target: str) -> dict:
    return {
        "$schema": "ops/schemas/run-ledger.schema.json",
        "run_id": "run-equal-score",
        "status": "ready",
        "events": [
            {"ts": "2026-04-13T00:00:00Z", "type": "created", "summary": "", "artifacts": [], "decision": ""},
            {"ts": "2026-04-13T00:00:01Z", "type": "seed_frozen", "summary": "", "artifacts": [], "decision": ""},
            {"ts": "2026-04-13T00:00:02Z", "type": "baseline_captured", "summary": "", "artifacts": [], "decision": ""},
            {"ts": "2026-04-13T00:00:03Z", "type": "mutation_applied", "summary": "", "artifacts": [], "decision": ""},
            {"ts": "2026-04-13T00:00:04Z", "type": "candidate_captured", "summary": "", "artifacts": [], "decision": ""},
            {"ts": "2026-04-13T00:00:05Z", "type": "repo_health_checked", "summary": "", "artifacts": [], "decision": ""},
            {
                "ts": "2026-04-13T00:00:06Z",
                "type": "promotion_evaluated",
                "summary": "",
                "artifacts": [primary_target],
                "decision": "PROMOTE",
            },
        ],
    }


def mechanism_gate_report(
    vault: Path,
    *,
    changed_manifest: dict,
    signoff_status: str,
) -> dict:
    policy, resolved_policy_path = load_policy(vault)
    primary_target = "ops/scripts/example.py"
    behavior_report = behavior_delta_report(changed_manifest)
    inputs = MechanismGateInputs(
        baseline_eval_report=eval_report(vault, 10),
        baseline_eval_rel="artifacts/baseline-eval.json",
        candidate_eval_report=eval_report(vault, 10),
        candidate_eval_rel="artifacts/candidate-eval.json",
        baseline_lint_report=lint_report(vault, status="warn", warning_count=1),
        baseline_lint_rel="artifacts/baseline-lint.json",
        candidate_lint_report=lint_report(vault),
        candidate_lint_rel="artifacts/candidate-lint.json",
        baseline_mechanism_report=mechanism_report(
            vault,
            primary_targets=[primary_target],
            nonempty=10,
            functions=2,
            branches=1,
            headings=0,
            test_file_count=1,
            test_case_count=1,
            complexity_score=15,
        ),
        baseline_mechanism_rel="artifacts/baseline-mechanism.json",
        candidate_mechanism_report=mechanism_report(
            vault,
            primary_targets=[primary_target],
            nonempty=10,
            functions=2,
            branches=1,
            headings=0,
            test_file_count=1,
            test_case_count=1,
            complexity_score=15,
        ),
        candidate_mechanism_rel="artifacts/candidate-mechanism.json",
        changed_files_manifest_report=changed_manifest,
        changed_files_manifest_rel="artifacts/changed-files-manifest.json",
        behavior_delta_report=behavior_report,
        behavior_delta_rel="artifacts/behavior-delta.json",
        run_ledger_report=run_ledger(primary_target),
        run_ledger_rel="runs/run-equal-score/run-ledger.json",
    )
    return mechanism_class_report(
        vault,
        run_id="run-equal-score",
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        artifact_class="system_mechanism",
        primary_targets=[primary_target],
        supporting_targets=[],
        signoff={
            "required": True,
            "status": signoff_status,
            "by": "",
            "ts": "",
        },
        log={
            "required": True,
            "page": "system/system-log.md",
            "summary": "mechanism decision flow regression test",
            "status": "pending",
            "entry_ref": "",
        },
        inputs=inputs,
    )


class MechanismRunValidationRuntimeTests(unittest.TestCase):
    def test_report_consistency_checks_preserve_order_and_flag_vault_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            bundle = normalize_mechanism_artifact_bundle(
                {
                    "baseline_eval_report": eval_report(vault, 10),
                    "candidate_eval_report": eval_report(vault, 10),
                    "baseline_lint_report": lint_report(vault),
                    "candidate_lint_report": lint_report(vault),
                    "baseline_mechanism_report": mechanism_report(
                        vault,
                        primary_targets=["ops/scripts/example.py"],
                        nonempty=10,
                        functions=2,
                        branches=1,
                        headings=0,
                        test_file_count=1,
                        test_case_count=1,
                        complexity_score=15,
                    ),
                    "candidate_mechanism_report": mechanism_report(
                        vault,
                        primary_targets=["ops/scripts/example.py"],
                        nonempty=10,
                        functions=2,
                        branches=1,
                        headings=0,
                        test_file_count=1,
                        test_case_count=1,
                        complexity_score=15,
                    ),
                    "changed_files_manifest_report": changed_files_manifest("ops/scripts/example.py"),
                    "run_ledger_report": run_ledger("ops/scripts/example.py"),
                }
            )
            bundle.candidate_eval_report["vault"] = str((vault / "other").resolve())

            checks = build_report_consistency_checks(
                vault,
                bundle,
                run_id="run-equal-score",
                expected_policy_path="ops/policies/wiki-maintainer-policy.yaml",
                expected_policy_version=LIVE_POLICY_VERSION,
            )

            self.assertEqual(
                [check["id"] for check in checks],
                [
                    "run_id_consistency",
                    "changed_files_manifest_run_id_consistency",
                    "report_policy_consistency",
                    "report_vault_consistency",
                ],
            )
            vault_check = checks[-1]
            self.assertEqual(vault_check["status"], "FAIL")
            self.assertIn("candidate_eval=", vault_check["detail"])
            self.assertNotIn(str(vault.resolve()), vault_check["detail"])
            self.assertNotIn(str((vault / "other").resolve()), vault_check["detail"])

    def test_report_consistency_check_detail_uses_public_safe_vault_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            bundle = normalize_mechanism_artifact_bundle(
                {
                    "baseline_eval_report": eval_report(vault, 10),
                    "candidate_eval_report": eval_report(vault, 10),
                    "baseline_lint_report": lint_report(vault),
                    "candidate_lint_report": lint_report(vault),
                    "baseline_mechanism_report": mechanism_report(
                        vault,
                        primary_targets=["ops/scripts/example.py"],
                        nonempty=10,
                        functions=2,
                        branches=1,
                        headings=0,
                        test_file_count=1,
                        test_case_count=1,
                        complexity_score=15,
                    ),
                    "candidate_mechanism_report": mechanism_report(
                        vault,
                        primary_targets=["ops/scripts/example.py"],
                        nonempty=10,
                        functions=2,
                        branches=1,
                        headings=0,
                        test_file_count=1,
                        test_case_count=1,
                        complexity_score=15,
                    ),
                    "changed_files_manifest_report": changed_files_manifest("ops/scripts/example.py"),
                    "run_ledger_report": run_ledger("ops/scripts/example.py"),
                }
            )

            checks = build_report_consistency_checks(
                vault,
                bundle,
                run_id="run-equal-score",
                expected_policy_path="ops/policies/wiki-maintainer-policy.yaml",
                expected_policy_version=LIVE_POLICY_VERSION,
            )

            vault_check = checks[-1]
            self.assertEqual(vault_check["status"], "PASS")
            self.assertIn("expected=.", vault_check["detail"])
            self.assertIn("baseline_eval=.", vault_check["detail"])
            self.assertNotIn(str(vault.resolve()), vault_check["detail"])

    def test_display_report_vault_hides_absolute_paths_that_escape_after_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            raw_outside_vault = vault / ".." / "outside-vault"

            self.assertEqual(
                display_report_vault(vault, raw_outside_vault.as_posix()),
                "<outside-vault>",
            )
            self.assertNotIn(temp_dir, display_report_vault(vault, raw_outside_vault.as_posix()))

    def test_event_sequence_checks_flag_invalid_order(self) -> None:
        ledger = evaluated_run_ledger("ops/scripts/example.py")
        events = ledger["events"]
        events[1], events[2] = events[2], events[1]
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": {},
                "run_ledger_report": ledger,
            }
        )

        checks = build_event_sequence_phase_checks(bundle, phase="mechanism_evaluated")

        order_check = next(check for check in checks if check["check"] == "mechanism_run_event_order")
        self.assertFalse(order_check["pass"])
        self.assertIn("baseline_captured", order_check["detail"])

    def test_event_sequence_checks_ignore_malformed_ledger_events(self) -> None:
        ledger = evaluated_run_ledger("ops/scripts/example.py")
        ledger["events"][2:2] = [
            "not an event",
            {"summary": "missing type"},
            {"type": 42, "summary": "non-string type"},
        ]
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": {},
                "run_ledger_report": ledger,
            }
        )

        checks = build_event_sequence_phase_checks(bundle, phase="mechanism_evaluated")

        by_check = {check["check"]: check for check in checks}
        self.assertTrue(by_check["mechanism_run_required_events_present"]["pass"])
        self.assertTrue(by_check["mechanism_run_event_order"]["pass"])
        self.assertTrue(by_check["mechanism_run_terminal_event"]["pass"])

    def test_event_sequence_checks_allow_history_update_after_finalized(self) -> None:
        ledger = evaluated_run_ledger("ops/scripts/example.py")
        ledger["events"].append(
            {
                "ts": "2026-04-13T00:00:07Z",
                "type": "finalized",
                "summary": "",
                "artifacts": [],
                "decision": "PROMOTE",
            }
        )
        ledger["events"].append(
            {
                "ts": "2026-04-13T00:00:08Z",
                "type": "history_status_updated",
                "summary": "Marked mechanism run history as archived.",
                "artifacts": [],
                "decision": "archived",
            }
        )
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": {},
                "run_ledger_report": ledger,
            }
        )

        checks = build_event_sequence_phase_checks(bundle, phase="mechanism_finalized")

        by_check = {check["check"]: check for check in checks}
        self.assertTrue(by_check["mechanism_run_event_order"]["pass"])
        self.assertTrue(by_check["mechanism_run_terminal_event"]["pass"])

    def test_event_sequence_checks_reject_required_event_replay_after_terminal(self) -> None:
        ledger = evaluated_run_ledger("ops/scripts/example.py")
        ledger["events"].append(
            {
                "ts": "2026-04-13T00:00:07Z",
                "type": "baseline_captured",
                "summary": "invalid replay",
                "artifacts": [],
                "decision": "",
            }
        )
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": {},
                "run_ledger_report": ledger,
            }
        )

        checks = build_event_sequence_phase_checks(bundle, phase="mechanism_evaluated")

        by_check = {check["check"]: check for check in checks}
        self.assertFalse(by_check["mechanism_run_event_order"]["pass"])
        self.assertFalse(by_check["mechanism_run_terminal_event"]["pass"])
        self.assertIn("baseline_captured", by_check["mechanism_run_event_order"]["detail"])

    def test_event_sequence_checks_reject_finalized_event_for_evaluated_phase(self) -> None:
        ledger = evaluated_run_ledger("ops/scripts/example.py")
        ledger["events"].append(
            {
                "ts": "2026-04-13T00:00:07Z",
                "type": "finalized",
                "summary": "invalid finalized event for evaluated phase",
                "artifacts": [],
                "decision": "finalized",
            }
        )
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": {},
                "run_ledger_report": ledger,
            }
        )

        checks = build_event_sequence_phase_checks(bundle, phase="mechanism_evaluated")

        by_check = {check["check"]: check for check in checks}
        self.assertTrue(by_check["mechanism_run_event_order"]["pass"])
        self.assertFalse(by_check["mechanism_run_terminal_event"]["pass"])
        self.assertIn("finalized", by_check["mechanism_run_terminal_event"]["detail"])

    def test_test_surface_phase_check_requires_discovered_test_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            bundle = normalize_mechanism_artifact_bundle(
                {
                    "baseline_eval_report": {},
                    "candidate_eval_report": {},
                    "baseline_lint_report": {},
                    "candidate_lint_report": {},
                    "baseline_mechanism_report": mechanism_report(
                        vault,
                        primary_targets=["ops/scripts/example.py"],
                        test_file_count=1,
                        test_case_count=0,
                    ),
                    "candidate_mechanism_report": mechanism_report(
                        vault,
                        primary_targets=["ops/scripts/example.py"],
                        test_file_count=1,
                        test_case_count=0,
                    ),
                    "changed_files_manifest_report": {},
                    "run_ledger_report": {},
                }
            )

            check = build_test_surface_phase_check(bundle, ready=True)

            self.assertFalse(check["pass"])
            self.assertIn("baseline_test_case_count=0", check["detail"])
            self.assertIn("candidate_test_case_count=0", check["detail"])

    def test_changed_files_scope_normalizes_manifest_paths_before_matching(self) -> None:
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": changed_files_manifest(
                    "ops/scripts/example.py",
                    changed_files=[
                        {
                            "path": "ops/scripts/example.py/../other.py",
                            "change_type": "modified",
                        }
                    ],
                ),
                "run_ledger_report": run_ledger("ops/scripts/example.py"),
            }
        )

        check = build_changed_files_scope_gate_check(bundle)

        self.assertEqual(check["status"], "FAIL")
        self.assertIn("ops/scripts/other.py", check["detail"])

    def test_changed_files_scope_rejects_manifest_paths_that_escape_repo_root(self) -> None:
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": changed_files_manifest(
                    "ops/scripts/example.py",
                    changed_files=[
                        {
                            "path": "ops/scripts/example.py/../../../../outside.py",
                            "change_type": "modified",
                        }
                    ],
                ),
                "run_ledger_report": run_ledger("ops/scripts/example.py"),
            }
        )

        check = build_changed_files_scope_gate_check(bundle)

        self.assertEqual(check["status"], "FAIL")
        self.assertIn("../outside.py", check["detail"])

    def test_changed_files_scope_normalizes_declared_targets_before_matching(self) -> None:
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": changed_files_manifest(
                    "ops/scripts/example.py/../other.py",
                    changed_files=[
                        {
                            "path": "ops/scripts/other.py",
                            "change_type": "modified",
                        }
                    ],
                ),
                "run_ledger_report": run_ledger("ops/scripts/example.py"),
            }
        )

        check = build_changed_files_scope_gate_check(bundle)

        self.assertEqual(check["status"], "PASS")

    def test_changed_files_scope_rejects_invalid_self_declared_manifest_paths(self) -> None:
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": changed_files_manifest(
                    "../outside.py",
                    changed_files=[
                        {
                            "path": "../outside.py",
                            "change_type": "modified",
                        }
                    ],
                ),
                "run_ledger_report": run_ledger("ops/scripts/example.py"),
            }
        )

        check = build_changed_files_scope_gate_check(bundle)

        self.assertEqual(check["status"], "FAIL")
        self.assertIn("!invalid-repo-path:../outside.py", check["detail"])

    def test_primary_target_touch_discard_detail_names_scope_and_changed_files(self) -> None:
        bundle = normalize_mechanism_artifact_bundle(
            {
                "baseline_eval_report": {},
                "candidate_eval_report": {},
                "baseline_lint_report": {},
                "candidate_lint_report": {},
                "baseline_mechanism_report": {},
                "candidate_mechanism_report": {},
                "changed_files_manifest_report": changed_files_manifest(
                    "ops/scripts/example.py",
                    changed_files=[
                        {
                            "path": "README.md",
                            "change_type": "modified",
                        }
                    ],
                ),
                "run_ledger_report": run_ledger("ops/scripts/example.py"),
            }
        )

        check = build_changed_files_primary_target_touched_check(
            bundle,
            primary_targets=["ops/scripts/example.py"],
        )

        self.assertEqual(check["status"], "FAIL")
        self.assertIn("expected_primary_targets=['ops/scripts/example.py']", check["detail"])
        self.assertIn("changed_files=['README.md']", check["detail"])

    def test_rule_registry_decision_flow_keeps_discard_before_hold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)

            discard_report = mechanism_gate_report(
                vault,
                changed_manifest=changed_files_manifest(
                    "ops/scripts/example.py",
                    changed_files=[
                        {"path": "ops/scripts/example.py", "change_type": "modified"},
                        {"path": "README.md", "change_type": "modified"},
                    ],
                ),
                signoff_status="pending",
            )
            hold_report = mechanism_gate_report(
                vault,
                changed_manifest=changed_files_manifest("ops/scripts/example.py"),
                signoff_status="pending",
            )
            promote_report = mechanism_gate_report(
                vault,
                changed_manifest=changed_files_manifest("ops/scripts/example.py"),
                signoff_status="approved",
            )

            discard_scope = next(
                check
                for check in discard_report["checks"]
                if check["id"] == "changed_files_manifest_scope"
            )
            discard_signoff = next(
                check
                for check in discard_report["checks"]
                if check["id"] == "signoff_status"
            )
            hold_scope = next(
                check
                for check in hold_report["checks"]
                if check["id"] == "changed_files_manifest_scope"
            )
            hold_signoff = next(
                check
                for check in hold_report["checks"]
                if check["id"] == "signoff_status"
            )
            promote_signoff = next(
                check
                for check in promote_report["checks"]
                if check["id"] == "signoff_status"
            )

            self.assertEqual(discard_scope["status"], "FAIL")
            self.assertEqual(discard_signoff["status"], "WARN")
            self.assertEqual(discard_report["decision"], "DISCARD")

            self.assertEqual(hold_scope["status"], "PASS")
            self.assertEqual(hold_signoff["status"], "WARN")
            self.assertEqual(hold_report["decision"], "PROMOTE")

            self.assertEqual(promote_signoff["status"], "PASS")
            self.assertEqual(promote_report["decision"], "PROMOTE")


if __name__ == "__main__":
    unittest.main()
