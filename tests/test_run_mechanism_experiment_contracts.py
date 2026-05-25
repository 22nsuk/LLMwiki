from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from ops.scripts.run_mechanism_experiment_runtime import (
    RunMechanismExperimentUsageError,
    run_mechanism_experiment,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.run_mechanism_experiment_test_utils import (
    mutation_proposal_report,
    seed_wrapper_vault,
)


class RunMechanismExperimentContractTests(unittest.TestCase):
    def test_wrapper_uses_policy_defined_system_mechanism_starter_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            custom_bundle = vault / "custom-starters" / "system-mechanism"
            custom_bundle.mkdir(parents=True, exist_ok=True)
            (custom_bundle / "bundle-note.md").write_text(
                "# bundle note\n\ncustom starter extras should be copied into the run directory.\n",
                encoding="utf-8",
            )
            (vault / "ops" / "templates" / "mechanism-run").rmdir()

            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    "  system_mechanism:\n    path: ops/templates/mechanism-run\n",
                    "  system_mechanism:\n    path: custom-starters/system-mechanism\n",
                    1,
                ),
                encoding="utf-8",
            )

            result = run_mechanism_experiment(
                vault,
                run_id="run-wrapper-policy-starter",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                log_summary="Policy starter lookup regression test",
                mutation_command=None,
                check_command=None,
                require_signoff=False,
                signoff_status=None,
                signoff_by=None,
                signoff_ts=None,
                finalize=False,
                scaffold_only=True,
            )

            self.assertTrue(result["scaffold_only"])
            self.assertEqual(
                result["improvement_observations"],
                "runs/run-wrapper-policy-starter/improvement-observations.json",
            )
            self.assertTrue((vault / "runs" / "run-wrapper-policy-starter" / "seed.yaml").exists())
            self.assertTrue(
                (vault / "runs" / "run-wrapper-policy-starter" / "improvement-observations.json").exists()
            )
            self.assertTrue((vault / "runs" / "run-wrapper-policy-starter" / "bundle-note.md").exists())

    def test_wrapper_scaffolds_from_selected_proposal_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            proposal_path = vault / "ops" / "reports" / "mutation-proposals.json"
            proposal_path.write_text(
                json.dumps(mutation_proposal_report("ops/scripts/example.py"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            result = run_mechanism_experiment(
                vault,
                run_id="run-wrapper-scaffold",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=[],
                supporting_targets=[],
                test_files=[],
                log_summary=None,
                mutation_command=None,
                check_command=None,
                require_signoff=False,
                signoff_status=None,
                signoff_by=None,
                signoff_ts=None,
                finalize=False,
                proposal_id="repeated_same_eval_or_discard__example",
                proposal_report_path="ops/reports/mutation-proposals.json",
                scaffold_only=True,
            )

            run_dir = vault / "runs" / "run-wrapper-scaffold"
            seed = (run_dir / "seed.yaml").read_text(encoding="utf-8")
            plan = (run_dir / "plan.md").read_text(encoding="utf-8")
            proposal_snapshot = json.loads((run_dir / "proposal-snapshot.json").read_text(encoding="utf-8"))
            run_ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            improvement_observations = json.loads(
                (run_dir / "improvement-observations.json").read_text(encoding="utf-8")
            )
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")

            self.assertTrue(result["scaffold_only"])
            self.assertEqual(result["planning_gate"]["phase"], "mechanism_in_progress")
            self.assertEqual(result["planning_gate"]["status"], "pass")
            self.assertEqual(result["proposal_snapshot"], "runs/run-wrapper-scaffold/proposal-snapshot.json")
            self.assertEqual(
                result["improvement_observations"],
                "runs/run-wrapper-scaffold/improvement-observations.json",
            )
            self.assertIn("current: SEED_DRAFT", seed)
            self.assertIn("proposal-snapshot.json", seed)
            self.assertIn("repeated_same_eval_or_discard__example", seed)
            self.assertIn("Expected binary signal", plan)
            self.assertEqual(proposal_snapshot["proposal"]["proposal_id"], "repeated_same_eval_or_discard__example")
            self.assertEqual(run_ledger["status"], "draft")
            self.assertTrue((run_dir / "improvement-observations.json").exists())
            self.assertEqual(validate_with_schema(improvement_observations, schema), [])
            self.assertFalse((run_dir / "baseline-eval.json").exists())

    def test_wrapper_requires_focused_test_file_for_full_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(
                RunMechanismExperimentUsageError,
                "at least one --test-file is required",
            ):
                run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-no-tests",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=[],
                    log_summary="Wrapper-driven mechanism experiment",
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-14T00:00:00Z",
                    finalize=False,
                )

    def test_wrapper_rejects_missing_test_file_before_scaffolding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(RunMechanismExperimentUsageError, "missing target: tests/test_typo.py"):
                run_mechanism_experiment(
                    vault,
                    run_id="run-wrapper-missing-test-file",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_typo.py"],
                    log_summary="Wrapper-driven mechanism experiment with missing test file",
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('repo health ok')\"",
                    require_signoff=False,
                    signoff_status="approved",
                    signoff_by="human",
                    signoff_ts="2026-04-14T00:00:00Z",
                    finalize=False,
                )

            self.assertFalse((vault / "runs" / "run-wrapper-missing-test-file").exists())

    def test_wrapper_rejects_shell_control_operators_before_scaffolding(self) -> None:
        command_cases = [
            (
                "mutation",
                "echo ok && echo still-not-allowed",
                f"{sys.executable} -c \"print('repo health ok')\"",
            ),
            (
                "check",
                f"{sys.executable} tools/mutate_success.py",
                "echo ok && echo still-not-allowed",
            ),
        ]
        for label, mutation_command, check_command in command_cases:
            with (
                self.subTest(command_surface=label),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                vault = Path(temp_dir) / "vault"
                vault.mkdir()
                seed_wrapper_vault(vault)

                with self.assertRaisesRegex(
                    RunMechanismExperimentUsageError,
                    "shell operators are not supported",
                ):
                    run_mechanism_experiment(
                        vault,
                        run_id=f"run-wrapper-shell-control-{label}",
                        policy_path="ops/policies/wiki-maintainer-policy.yaml",
                        primary_targets=["ops/scripts/example.py"],
                        supporting_targets=[],
                        test_files=["tests/test_example.py"],
                        log_summary=f"Wrapper-driven mechanism experiment shell control {label}",
                        mutation_command=mutation_command,
                        check_command=check_command,
                        require_signoff=False,
                        signoff_status="approved",
                        signoff_by="human",
                        signoff_ts="2026-04-14T00:00:00Z",
                        finalize=False,
                    )

                self.assertFalse((vault / "runs" / f"run-wrapper-shell-control-{label}").exists())


if __name__ == "__main__":
    unittest.main()
