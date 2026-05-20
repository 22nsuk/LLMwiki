from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from ops.scripts.codex_exec_executor import ExecutorContractError, execute_codex_exec_role
from ops.scripts.executor import main as executor_cli_main
from ops.scripts.executor_runtime import (
    ExecutorRuntimeExecutionError,
    run_executor_pipeline,
)
from ops.scripts.runtime_context import RuntimeContext

from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault, seed_subagent_profiles


def _seed_executor_vault(vault: Path) -> None:
    seed_minimal_vault(vault)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas" / "executor-report.schema.json").write_text(
        (REPO_ROOT / "ops" / "schemas" / "executor-report.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "scripts" / "example.py").write_text("def subject():\n    return 1\n", encoding="utf-8")
    (vault / "tests" / "test_example.py").write_text("def test_subject():\n    assert True\n", encoding="utf-8")
    run_dir = vault / "runs" / "run-executor"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-ledger.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": "run-executor",
                "status": "draft",
                "events": [
                    {
                        "ts": "2026-04-15T00:00:00Z",
                        "type": "created",
                        "summary": "created",
                        "artifacts": ["seed.yaml"],
                        "decision": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "proposal-snapshot.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/proposal-snapshot.schema.json",
                "run_id": "run-executor",
                "source_report": "ops/reports/mutation-proposals.json",
                "captured_at": "2026-04-15T00:00:00Z",
                "proposal": {
                    "proposal_id": "proposal-example",
                    "source_candidate_id": "candidate",
                    "source_candidate_type": "mechanism_eval_stagnation_candidate",
                    "family": "contract_regression_signals",
                    "tier": "supporting",
                    "priority": 50,
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "metrics_triggered": ["stage1_same_eval_rate"],
                    "run_ids": ["run-a"],
                    "failure_mode": "repeated_same_eval_or_discard",
                    "single_mechanism_scope": "change example.py only",
                    "change_hypothesis": "narrowed change should help",
                    "expected_binary_signal": "PROMOTE or DISCARD",
                    "blast_radius_score": 15,
                    "must_change_tests": ["tests/test_example.py"],
                    "must_change_budget_signal": {
                        "signal": "candidate_eval.total_score",
                        "expected_change": "increase_or_equal_score_secondary",
                    },
                    "must_not_expand_apply_roots": True,
                    "must_not_increase_untyped_surface": True,
                    "required_artifacts": ["runs/<run-id>/promotion-report.json"],
                    "blocked_by": [],
                    "priority_breakdown": {
                        "base_priority": 50,
                        "historical_calibration_delta": 0,
                        "session_calibration_delta": 0,
                        "review_candidate_priority": 50,
                        "recent_log_overlap_penalty": 0,
                        "final_priority": 50,
                    },
                    "why_now": "test",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "scope-freeze.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/proposal-scope.schema.json",
                "run_id": "run-executor",
                "proposal_id": "proposal-example",
                "source_candidate_id": "candidate-example",
                "generated_at": "2026-04-15T00:00:00Z",
                "policy": {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 1},
                "status": "runnable",
                "inputs": {
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                },
                "resolution": {
                    "test_files": ["tests/test_example.py"],
                    "risk_flags": [],
                    "blocked_by": [],
                },
                "apply_guardrails": {
                    "allowed_apply_roots": ["ops/", "tests/", "system/system-log.md"],
                },
                "dispatch": {
                    "worker": True,
                    "validator": True,
                    "reviewer": False,
                    "auditors": [],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _routing_report(role: str, *, sandbox_mode: str, model: str, reasoning_effort: str, selected_rung: int) -> dict:
    default_rung = selected_rung
    allowed_rungs = [selected_rung]
    if role == "worker":
        default_rung = 2
        allowed_rungs = [2, 3]
    elif role == "validator":
        default_rung = 3
        allowed_rungs = [3]
    elif role == "reviewer":
        default_rung = 2
        allowed_rungs = [2, 3]
    return {
        "$schema": "ops/schemas/subagent-routing-report.schema.json",
        "vault": ".",
        "generated_at": "2026-04-15T00:00:00Z",
        "policy": {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 1},
        "role": role,
        "profile_path": f".codex/agents/{role}.toml",
        "inputs": {
            "primary_targets": ["ops/scripts/example.py"],
            "supporting_targets": [],
            "test_files": ["tests/test_example.py"],
            "manual_risk_flags": [],
        },
        "structural_metrics": {
            "nonempty_line_count_total": 1,
            "python_function_count": 1,
            "python_branch_node_count": 0,
            "markdown_heading_count": 0,
            "test_file_count": 1,
            "test_case_count": 1,
        },
        "total_structural_metrics": {
            "nonempty_line_count_total": 1,
            "python_function_count": 1,
            "python_branch_node_count": 0,
            "markdown_heading_count": 0,
            "test_file_count": 1,
            "test_case_count": 1,
        },
        "diagnostics": {"unreadable_targets": [], "python_parse_failures": []},
        "complexity_profile": {
            "dimensions": {
                "change_surface": 1,
                "dependency_impact": 0,
                "verification_cost": 2,
                "artifact_heterogeneity": 0,
                "environment_risk": 0,
            },
            "complexity_score": 20,
            "risk_flags": [],
            "detected_risk_flags": [],
            "manual_risk_flags": [],
        },
        "routing_decision": {
            "default_rung": default_rung,
            "allowed_rungs": allowed_rungs,
            "score_band": "low",
            "band_rung": selected_rung,
            "requested_rung": selected_rung,
            "selected_rung": selected_rung,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "sandbox_mode": sandbox_mode,
            "escalation_reasons": [],
        },
    }


def _write_routing_report(
    vault: Path,
    role: str,
    *,
    sandbox_mode: str,
    model: str,
    reasoning_effort: str,
    selected_rung: int,
) -> str:
    rel_path = f"runs/run-executor/subagent-routing.{role}.json"
    (vault / rel_path).write_text(
        json.dumps(
            _routing_report(
                role,
                sandbox_mode=sandbox_mode,
                model=model,
                reasoning_effort=reasoning_effort,
                selected_rung=selected_rung,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return rel_path


def _object_schema_paths_with_optional_properties(schema: Any, path: str = "$") -> list[str]:
    if not isinstance(schema, dict):
        return []
    findings: list[str] = []
    properties = schema.get("properties")
    if isinstance(properties, dict):
        required = schema.get("required", [])
        required_keys = set(required) if isinstance(required, list) else set()
        missing = sorted(set(properties) - required_keys)
        if missing:
            findings.append(f"{path}: {', '.join(missing)}")
        for name, subschema in properties.items():
            findings.extend(
                _object_schema_paths_with_optional_properties(
                    subschema,
                    f"{path}.properties.{name}",
                )
            )
    items = schema.get("items")
    if items is not None:
        findings.extend(_object_schema_paths_with_optional_properties(items, f"{path}.items"))
    for keyword in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(keyword)
        if isinstance(variants, list):
            for index, variant in enumerate(variants):
                findings.extend(
                    _object_schema_paths_with_optional_properties(
                        variant,
                        f"{path}.{keyword}[{index}]",
                    )
                )
    return findings


class ExecutorRuntimeTests(unittest.TestCase):
    def test_executor_report_schema_is_codex_output_schema_strict(self) -> None:
        schema = json.loads((REPO_ROOT / "ops" / "schemas" / "executor-report.schema.json").read_text())

        self.assertEqual(_object_schema_paths_with_optional_properties(schema), [])
        self.assertEqual(
            schema["properties"]["artifacts"]["properties"]["timeout_failure"]["type"],
            ["string", "null"],
        )

    def test_worker_role_uses_full_auto_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                Path(argv[out_index]).write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": ["ok"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="worker",
                    routing_report_rel="runs/run-executor/subagent-routing.worker.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "pass")
            self.assertIn("--full-auto", report["command"]["argv"])
            self.assertIn("--skip-git-repo-check", report["command"]["argv"])
            self.assertIsNone(report["artifacts"]["timeout_failure"])
            self.assertTrue((vault / "runs" / "run-executor" / "worker-executor-report.json").exists())
            prompt = (vault / "runs" / "run-executor" / "worker-prompt.md").read_text(encoding="utf-8")
            self.assertIn("Return JSON only.", prompt)
            self.assertIn("proposal_snapshot", prompt)
            self.assertNotIn(str(vault).replace("\\", "/"), prompt)
            event_log = vault / "runs" / "run-executor" / "runtime-events.jsonl"
            events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["component"], "codex_exec_executor")
            self.assertEqual(events[0]["phase"], "executor")
            self.assertEqual(events[0]["decision"], "ready")
            self.assertEqual(events[0]["policy_version"], 1)

    def test_validator_role_uses_workspace_write_sandbox_with_read_only_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                Path(argv[out_index]).write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": ["validated"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "pass")
            self.assertIn("--full-auto", report["command"]["argv"])
            self.assertIn("--skip-git-repo-check", report["command"]["argv"])
            self.assertEqual(report["executor"]["sandbox_mode"], "workspace-write")
            prompt = (vault / "runs" / "run-executor" / "validator-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("workspace-local `.venv/bin/python`", prompt)
            self.assertIn("PYTHONDONTWRITEBYTECODE=1", prompt)
            self.assertIn("-p no:cacheprovider", prompt)
            self.assertIn("Executor roles run before repo-health capture", prompt)
            self.assertIn("candidate-mechanism-assessment.json", prompt)

    def test_reviewer_role_uses_workspace_write_sandbox_with_read_only_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["reviewer"])
            _write_routing_report(
                vault,
                "reviewer",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                Path(argv[out_index]).write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": ["reviewed"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="reviewer",
                    routing_report_rel="runs/run-executor/subagent-routing.reviewer.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "pass")
            self.assertIn("--full-auto", report["command"]["argv"])
            self.assertIn("--skip-git-repo-check", report["command"]["argv"])
            self.assertEqual(report["executor"]["sandbox_mode"], "workspace-write")
            prompt = (vault / "runs" / "run-executor" / "reviewer-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("source and control files", prompt)
            self.assertIn("PYTHONDONTWRITEBYTECODE=1", prompt)
            self.assertIn("Executor roles run before repo-health capture", prompt)

    def test_non_worker_workspace_write_mutation_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                Path(argv[out_index]).write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": ["validated"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                (vault / "ops" / "scripts" / "example.py").write_text(
                    "def subject():\n    return 2\n",
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "fail")
            self.assertIn(
                "non-worker workspace mutation guard blocked validator",
                "\n".join(report["diagnostics"]["notes"]),
            )

    def test_execute_codex_exec_role_raises_domain_error_for_malformed_routing_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            (vault / "runs" / "run-executor" / "subagent-routing.worker.json").write_text(
                "{",
                encoding="utf-8",
            )

            with self.assertRaises(ExecutorContractError):
                execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="worker",
                    routing_report_rel="runs/run-executor/subagent-routing.worker.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

    def test_role_timeout_writes_blocking_executor_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(argv: list[str], **kwargs: object) -> object:
                self.assertEqual(kwargs["timeout_seconds"], 3)
                return mock.Mock(
                    returncode=-15,
                    stdout="",
                    stderr="timed out\n",
                    timed_out=True,
                    timeout_seconds=3,
                    termination_reason="timeout",
                )

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="worker",
                    routing_report_rel="runs/run-executor/subagent-routing.worker.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                    timeout_seconds=3,
                )

            self.assertEqual(report["status"], "fail")
            self.assertTrue(report["result"]["timed_out"])
            self.assertEqual(report["result"]["timeout_seconds"], 3)
            self.assertEqual(report["result"]["termination_reason"], "timeout")
            self.assertIn("codex exec timed out after 3 seconds", report["diagnostics"]["notes"])
            self.assertEqual(
                report["artifacts"]["timeout_failure"],
                "runs/run-executor/worker-executor-timeout-failure.json",
            )
            timeout_failure = json.loads(
                (vault / report["artifacts"]["timeout_failure"]).read_text(encoding="utf-8")
            )
            ledger = json.loads((vault / "runs" / "run-executor" / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(timeout_failure["phase"], "executor")
            self.assertEqual(timeout_failure["role"], "worker")
            self.assertTrue(timeout_failure["result"]["timed_out"])
            self.assertIn(report["artifacts"]["timeout_failure"], ledger["events"][-1]["artifacts"])

    def test_role_usage_limit_adds_retryable_diagnostic_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(_argv: list[str], **_: object) -> object:
                return mock.Mock(
                    returncode=1,
                    stdout="",
                    stderr=(
                        "ERROR: You've hit your usage limit. "
                        "Upgrade to Pro, or try again at May 16th, 2026 12:29 AM.\n"
                    ),
                    timed_out=False,
                    timeout_seconds=1800,
                    termination_reason="completed",
                )

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="worker",
                    routing_report_rel="runs/run-executor/subagent-routing.worker.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "fail")
            self.assertIn("codex exec exited with 1", report["diagnostics"]["notes"])
            self.assertIn(
                "codex exec blocked by usage limit; retry_after=May 16th, 2026 12:29 AM",
                report["diagnostics"]["notes"],
            )

    def test_run_executor_pipeline_orders_roles_and_records_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.5",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            executed_roles: list[str] = []

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                executed_roles.append(role)
                if role == "worker":
                    self.assertIn("--full-auto", argv)
                    self.assertIn("--skip-git-repo-check", argv)
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                if role == "validator":
                    self.assertEqual(argv[2:4], ["-s", "read-only"])
                    self.assertIn("--skip-git-repo-check", argv)
                output_path.write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": [f"{role} ok"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                result = run_executor_pipeline(
                    vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    roles=["validator", "worker"],
                    routing_reports=[validator_routing, worker_routing],
                )

            self.assertEqual(executed_roles, ["worker", "validator"])
            self.assertEqual(result["roles"], ["worker", "validator"])
            self.assertEqual(
                result["reports"],
                {
                    "worker": "runs/run-executor/worker-executor-report.json",
                    "validator": "runs/run-executor/validator-executor-report.json",
                },
            )
            ledger = json.loads((vault / "runs" / "run-executor" / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [event["type"] for event in ledger["events"][-2:]],
                ["executor_completed", "executor_completed"],
            )

    def test_run_executor_pipeline_refreshes_script_output_surfaces_after_ops_script_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            scope_path = vault / "runs" / "run-executor" / "scope-freeze.json"
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["inputs"]["supporting_targets"] = ["ops/script-output-surfaces.json"]
            scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
            (vault / "ops" / "script-output-surfaces.json").write_text("stale\n", encoding="utf-8")
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.5",
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
                output_path.write_text(
                    json.dumps(
                        {"status": "pass", "diagnostics": {"notes": [f"{role} ok"]}},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            def fake_refresh(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                events.append("script-output-surfaces")
                self.assertEqual(
                    argv[1:],
                    [
                        "-m",
                        "ops.scripts.script_output_surfaces",
                        "--vault",
                        ".",
                        "--out",
                        "ops/script-output-surfaces.json",
                    ],
                )
                refresh_cwd_value = kwargs.get("cwd")
                self.assertIsNotNone(refresh_cwd_value)
                refresh_cwd = Path(str(refresh_cwd_value))
                (refresh_cwd / "ops" / "script-output-surfaces.json").write_text(
                    "fresh\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, stdout="fresh\n", stderr="")

            with (
                mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.executor_runtime.subprocess.run", side_effect=fake_refresh),
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

            self.assertEqual(events, ["worker", "script-output-surfaces", "validator"])
            self.assertEqual(
                (vault / "ops" / "script-output-surfaces.json").read_text(encoding="utf-8"),
                "fresh\n",
            )

    def test_run_executor_pipeline_blocks_worker_pass_without_primary_target_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.5",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            executed_roles: list[str] = []

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                executed_roles.append(role)
                output_path.write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": [f"{role} ok"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                with self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "without modifying any declared primary target",
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

            self.assertEqual(executed_roles, ["worker"])
            self.assertTrue((vault / "runs" / "run-executor" / "worker-executor-report.json").exists())
            self.assertFalse((vault / "runs" / "run-executor" / "validator-executor-report.json").exists())

    def test_executor_cli_writes_success_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                Path(argv[out_index]).write_text(
                    json.dumps({"status": "pass", "diagnostics": {"notes": ["cli ok"]}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="cli ok\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                result = invoke_cli_main(
                    executor_cli_main,
                    [
                        "--vault",
                        str(vault),
                        "--workspace-root",
                        str(vault),
                        "--run-id",
                        "run-executor",
                        "--scope-freeze",
                        "runs/run-executor/scope-freeze.json",
                        "--proposal-snapshot",
                        "runs/run-executor/proposal-snapshot.json",
                        "--role",
                        "worker",
                        "--routing-report",
                        worker_routing,
                    ],
                    cwd=vault,
                )

            self.assertEqual(result.exit_code, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["roles"], ["worker"])
            self.assertEqual(payload["reports"]["worker"], "runs/run-executor/worker-executor-report.json")
            report = json.loads((vault / "runs" / "run-executor" / "worker-executor-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["diagnostics"]["notes"], ["cli ok"])

    def test_executor_cli_exits_five_on_blocking_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.5",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                payload = {"status": "pass", "diagnostics": {"notes": [f"{role} ok"]}}
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                if role == "validator":
                    payload = {"status": "fail", "diagnostics": {"notes": ["validator blocked"]}}
                output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return mock.Mock(returncode=0, stdout=f"{role}\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                result = invoke_cli_main(
                    executor_cli_main,
                    [
                        "--vault",
                        str(vault),
                        "--workspace-root",
                        str(vault),
                        "--run-id",
                        "run-executor",
                        "--scope-freeze",
                        "runs/run-executor/scope-freeze.json",
                        "--proposal-snapshot",
                        "runs/run-executor/proposal-snapshot.json",
                        "--role",
                        "worker",
                        "--role",
                        "validator",
                        "--routing-report",
                        worker_routing,
                        "--routing-report",
                        validator_routing,
                    ],
                    cwd=vault,
                )

            self.assertEqual(result.exit_code, 5)
            self.assertIn("validator reported a blocking status", result.stderr)
            validator_report = json.loads(
                (vault / "runs" / "run-executor" / "validator-executor-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(validator_report["status"], "fail")

    def test_executor_direct_script_help_uses_package_context_wrapper(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "ops" / "scripts" / "core" / "executor.py"), "--help"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("--scope-freeze", completed.stdout)
        self.assertIn("--routing-report", completed.stdout)

    def test_executor_runtime_is_not_a_direct_script_entrypoint(self) -> None:
        text = (REPO_ROOT / "ops" / "scripts" / "core" / "executor_runtime.py").read_text(encoding="utf-8")

        self.assertNotIn("direct script fallback", text)
        self.assertNotIn('if __name__ == "__main__"', text)

    def test_run_executor_pipeline_raises_on_blocking_validator_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            worker_routing = _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.5",
                reasoning_effort="high",
                selected_rung=2,
            )
            validator_routing = _write_routing_report(
                vault,
                "validator",
                sandbox_mode="read-only",
                model="gpt-5.5",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                payload = {"status": "pass", "diagnostics": {"notes": [f"{role} ok"]}}
                returncode = 0
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                if role == "validator":
                    payload = {"status": "fail", "diagnostics": {"notes": ["validator blocked"]}}
                output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return mock.Mock(returncode=returncode, stdout=f"{role}\n", stderr="")

            with mock.patch("ops.scripts.codex_exec_executor.run_with_timeout", side_effect=fake_run):
                with self.assertRaises(ExecutorRuntimeExecutionError):
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

            validator_report = json.loads(
                (vault / "runs" / "run-executor" / "validator-executor-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(validator_report["status"], "fail")
            self.assertEqual(validator_report["diagnostics"]["notes"], ["validator blocked"])
            ledger = json.loads((vault / "runs" / "run-executor" / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["status"], "blocked")
            self.assertEqual(ledger["events"][-1]["type"], "validation_blocked")
