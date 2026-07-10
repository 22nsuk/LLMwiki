from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.core.executor_runtime import (
    ExecutorRuntimeExecutionError,
    _worker_source_digest_snapshot,
    run_executor_pipeline,
)
from tests.executor_model_output_test_utils import write_valid_model_output
from tests.minimal_vault_runtime import seed_subagent_profiles
from tests.test_executor_runtime import (
    _executor_subprocess_completed,
    _is_worker_repo_health_preflight,
    _seed_executor_vault,
    _write_routing_report,
)


class ExecutorWorkerPreflightRuntimeTests(unittest.TestCase):
    def test_source_snapshot_tracks_only_public_and_local_contract_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            included = {
                "AGENTS.local.md": "local contract\n",
                "docs/operator.md": "# operator\n",
                "ops/scripts/new.py": "def subject():\n    return 1\n",
                "tests/test_new.py": "def test_subject():\n    assert True\n",
            }
            excluded = {
                "ops/script-output-surfaces.json": "{}\n",
                "ops/manifest.json": "{}\n",
                "ops/raw-registry.json": "{}\n",
                "ops/operator/generated.json": "{}\n",
                "ops/reports/report.json": "{}\n",
                "raw/source.md": "# raw\n",
                "wiki/page.md": "# wiki\n",
                "system/page.md": "# system\n",
                "runs/run-x/report.json": "{}\n",
                "external-reports/report.md": "# report\n",
                "tmp/scratch.py": "def scratch():\n    return 1\n",
            }
            for rel_path, content in {**included, **excluded}.items():
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            snapshot = _worker_source_digest_snapshot(vault)

            for rel_path in included:
                self.assertIn(rel_path, snapshot)
            for rel_path in excluded:
                self.assertNotIn(rel_path, snapshot)

    def test_blocks_non_worker_roles_when_worker_structural_complexity_regresses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            policy_path = vault / "ops" / "policies" / "custom-policy.yaml"
            shutil.copy2(
                vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_path,
            )
            seed_subagent_profiles(vault, ["worker", "validator", "provenance-auditor"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            auditor_routing = _write_routing_report(
                vault,
                "provenance-auditor",
                sandbox_mode="read-only",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            events: list[str] = []

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                events.append(role)
                if role == "worker":
                    long_body = "\n".join(f"    value_{index} = {index}" for index in range(125))
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        f"def subject():\n{long_body}\n    return value_124\n",
                        encoding="utf-8",
                    )
                    (vault / "tests" / "test_example.py").write_text(
                        "\n".join(f"def test_subject_{index}():\n    assert True\n" for index in range(61)),
                        encoding="utf-8",
                    )
                write_valid_model_output(
                    output_path,
                    vault,
                    run_id="run-executor",
                    role=role,
                    notes=[f"{role} ok"],
                )
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            def fake_preflight(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if _is_worker_repo_health_preflight(argv):
                    events.append("post-worker-repo-health")
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
                self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "worker structural complexity preflight blocked",
                ),
            ):
                run_executor_pipeline(
                    vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    policy_path="ops/policies/custom-policy.yaml",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    roles=["worker", "validator", "provenance-auditor"],
                    routing_reports=[worker_routing, validator_routing, auditor_routing],
                )

            self.assertEqual(events, ["worker"])
            run_dir = vault / "runs" / "run-executor"
            self.assertFalse((run_dir / "validator-executor-report.json").exists())
            self.assertFalse((run_dir / "worker-repo-health-preflight.stdout.txt").exists())
            structural_report = json.loads(
                (run_dir / "worker-structural-complexity-preflight.json").read_text(encoding="utf-8")
            )
            self.assertEqual(structural_report["status"], "attention")
            self.assertEqual(structural_report["policy"]["path"], "ops/policies/custom-policy.yaml")
            ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["status"], "blocked")
            self.assertEqual(ledger["events"][-1]["type"], "validation_blocked")
            self.assertEqual(
                ledger["events"][-1]["decision"],
                "worker_structural_complexity_preflight_attention",
            )

    def test_structural_preflight_includes_undeclared_new_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            events: list[str] = []

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                events.append(role)
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                    long_body = "\n".join(f"    value_{index} = {index}" for index in range(125))
                    (vault / "ops" / "scripts" / "new_big.py").write_text(
                        f"def new_big_subject():\n{long_body}\n    return value_124\n",
                        encoding="utf-8",
                    )
                write_valid_model_output(
                    output_path,
                    vault,
                    run_id="run-executor",
                    role=role,
                    notes=[f"{role} ok"],
                )
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            def fake_preflight(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if _is_worker_repo_health_preflight(argv):
                    events.append("post-worker-repo-health")
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
                self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "worker structural complexity preflight blocked",
                ),
            ):
                run_executor_pipeline(
                    vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    roles=["worker", "validator"],
                    routing_reports=[worker_routing, validator_routing],
                )

            self.assertEqual(events, ["worker"])
            run_dir = vault / "runs" / "run-executor"
            self.assertFalse((run_dir / "validator-executor-report.json").exists())
            self.assertFalse((run_dir / "worker-repo-health-preflight.stdout.txt").exists())
            structural_report = json.loads(
                (run_dir / "worker-structural-complexity-preflight.json").read_text(encoding="utf-8")
            )
            self.assertEqual(structural_report["status"], "attention")
            self.assertIn(
                "ops/scripts/new_big.py",
                {target["path"] for target in structural_report["targets"]},
            )


if __name__ == "__main__":
    unittest.main()
