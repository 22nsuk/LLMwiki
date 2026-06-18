from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.filesystem_runtime import manifest_apply_guard_state
from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.proposal_scope_runtime import (
    build_scope_freeze,
    write_scope_freeze,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import set_policy_value
from tests.run_mechanism_experiment_test_utils import seed_wrapper_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_SCOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "proposal-scope.schema.json"


class ProposalScopeRuntimeTests(unittest.TestCase):
    def test_script_target_resolves_focus_tests_and_runnable_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-scope",
                proposal={
                    "proposal_id": "proposal-example",
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                },
                context=context,
            )

            self.assertEqual(report["status"], "runnable")
            self.assertEqual(report["resolution"]["test_files"], ["tests/test_example.py"])
            self.assertEqual(report["resolution"]["blocked_by"], [])
            self.assertEqual(
                report["apply_guardrails"]["allowed_apply_roots"],
                ["ops/", "tests/", "system/system-log.md"],
            )
            self.assertEqual(report["dispatch"]["worker"], True)
            self.assertEqual(report["dispatch"]["validator"], True)
            self.assertEqual(report["dispatch"]["reviewer"], False)

    def test_policy_target_sets_policy_risk_and_blocks_without_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-policy-scope",
                proposal={
                    "proposal_id": "proposal-policy",
                    "primary_targets": ["ops/policies/wiki-maintainer-policy.yaml"],
                    "supporting_targets": [],
                },
                context=context,
            )

            self.assertEqual(report["status"], "blocked")
            self.assertIn("policy_surface", report["resolution"]["risk_flags"])
            self.assertIn("missing_focused_tests", report["resolution"]["blocked_by"])
            self.assertEqual(report["dispatch"]["reviewer"], True)

    def test_proposal_declared_tests_unblock_scope_when_pattern_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)
            target = vault / "ops" / "scripts" / "mechanism" / "mutation_proposal_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def build_report() -> None:\n    return None\n", encoding="utf-8")
            test_path = vault / "tests" / "test_mutation_proposal.py"
            test_path.write_text("def test_existing_focus() -> None:\n    assert True\n", encoding="utf-8")

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-declared-tests",
                proposal={
                    "proposal_id": "proposal-declared-tests",
                    "primary_targets": ["ops/scripts/mechanism/mutation_proposal_runtime.py"],
                    "supporting_targets": [],
                    "must_change_tests": ["tests/test_mutation_proposal.py"],
                },
                context=context,
            )

            self.assertEqual(report["status"], "runnable")
            self.assertEqual(report["resolution"]["test_files"], ["tests/test_mutation_proposal.py"])
            self.assertEqual(report["resolution"]["blocked_by"], [])
            self.assertEqual(report["dispatch"]["validator"], True)

    def test_supporting_fixture_target_is_not_treated_as_focus_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)
            target = vault / "ops" / "scripts" / "mechanism" / "example_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("VALUE = 1\n", encoding="utf-8")
            fixture = vault / "tests" / "fixtures" / "report_schema_samples.json"
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text("{}\n", encoding="utf-8")
            test_path = vault / "tests" / "test_report_schema_sample_regeneration.py"
            test_path.write_text("def test_regeneration() -> None:\n    assert True\n", encoding="utf-8")

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-fixture-supporting-target",
                proposal={
                    "proposal_id": "proposal-fixture-supporting-target",
                    "primary_targets": ["ops/scripts/mechanism/example_runtime.py"],
                    "supporting_targets": ["tests/fixtures/report_schema_samples.json"],
                    "must_change_tests": ["tests/test_report_schema_sample_regeneration.py"],
                },
                context=context,
            )

            self.assertEqual(report["status"], "runnable")
            self.assertEqual(
                report["resolution"]["test_files"],
                ["tests/test_report_schema_sample_regeneration.py"],
            )
            self.assertNotIn(
                "tests/fixtures/report_schema_samples.json",
                report["resolution"]["test_files"],
            )

    def test_system_log_target_sets_log_risk_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-log-scope",
                proposal={
                    "proposal_id": "proposal-log",
                    "primary_targets": ["system/system-log.md"],
                    "supporting_targets": [],
                },
                context=context,
            )

            self.assertEqual(report["status"], "blocked")
            self.assertIn("log_append_surface", report["resolution"]["risk_flags"])
            self.assertEqual(report["dispatch"]["reviewer"], True)

    def test_scope_freeze_apply_guardrails_stay_aligned_with_policy_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            set_policy_value(
                vault,
                ("auto_improve_policy", "allowed_apply_roots"),
                ["ops/", ".github/workflows/ci.yml"],
            )
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-allowlist-scope",
                proposal={
                    "proposal_id": "proposal-allowlist",
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                },
                context=context,
            )

            allowed_apply_roots = report["apply_guardrails"]["allowed_apply_roots"]
            self.assertEqual(allowed_apply_roots, ["ops/", ".github/workflows/ci.yml"])

            guard_state = manifest_apply_guard_state(
                {
                    "files": [
                        {"path": "ops/scripts/example.py", "change_type": "modified"},
                        {"path": ".github/workflows/ci.yml", "change_type": "modified"},
                        {"path": "README.md", "change_type": "modified"},
                    ]
                },
                allowed_apply_roots,
            )

            self.assertEqual(guard_state.allowed_apply_roots, allowed_apply_roots)
            self.assertEqual(
                guard_state.changed_paths,
                ["ops/scripts/example.py", ".github/workflows/ci.yml", "README.md"],
            )
            self.assertEqual(guard_state.disallowed_paths, ["README.md"])

    def test_write_scope_freeze_uses_schema_backed_repo_relative_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, policy_path = load_policy(vault)
            context = RuntimeContext.from_policy(policy)

            report = build_scope_freeze(
                vault,
                policy,
                policy_path,
                run_id="run-scope-write",
                proposal={
                    "proposal_id": "proposal-write",
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                },
                context=context,
            )

            destination = write_scope_freeze(vault, report, run_id="run-scope-write")

            self.assertEqual(destination, vault / "runs" / "run-scope-write" / "scope-freeze.json")
            self.assertEqual(validate_with_schema(report, load_schema(PROPOSAL_SCOPE_SCHEMA_PATH)), [])
            self.assertTrue(destination.is_file())
