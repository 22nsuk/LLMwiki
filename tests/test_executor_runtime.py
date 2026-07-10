from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import pytest

from ops.scripts.core import workspace_python_identity_runtime
from ops.scripts.core.codex_exec_dependency_preflight_decision_runtime import (
    non_worker_dependency_preflight,
)
from ops.scripts.core.codex_exec_dependency_preflight_runtime import (
    trusted_dependency_preflight_python,
)
from ops.scripts.core.codex_exec_execution_types_runtime import ExecutionRequest
from ops.scripts.core.codex_exec_executor import (
    ExecutorContractError,
    ExecutorReportRequest,
    _build_executor_report,
    _ExecutionSummary,
    _ExecutorArtifacts,
    _expected_external_workspace_python_shim,
    _SyntheticCompleted,
    build_execution_request,
    execute_codex_exec_role,
)
from ops.scripts.core.codex_exec_workspace_runtime import (
    external_workspace_python_issue,
)
from ops.scripts.core.executor import main as executor_cli_main
from ops.scripts.core.executor_runtime import (
    ExecutorRuntimeExecutionError,
    run_executor_pipeline,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.trusted_candidate_runner import TrustedCandidateRunOutcome
from ops.scripts.core.workspace_python_identity_runtime import (
    build_workspace_python_identity,
    load_workspace_python_identity,
    workspace_python_identity_path,
    write_workspace_python_identity,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.executor_model_output_test_utils import write_valid_model_output
from tests.minimal_vault_runtime import (
    REPO_ROOT,
    seed_minimal_vault,
    seed_subagent_profiles,
    set_policy_value,
)

pytestmark = pytest.mark.slow


def _provision_workspace_python_symlink(
    vault: Path,
    *,
    source_python: Path | None = None,
) -> Path:
    resolved_source = source_python or Path(sys.executable).absolute()
    workspace_python = vault / ".venv" / "bin" / "python"
    workspace_python.parent.mkdir(parents=True, exist_ok=True)
    if workspace_python.exists() or workspace_python.is_symlink():
        workspace_python.unlink()
    try:
        workspace_python.symlink_to(resolved_source)
    except OSError as exc:
        raise unittest.SkipTest(f"workspace symlink setup unavailable: {exc}") from exc
    return workspace_python


def _write_workspace_python_delegate(vault: Path) -> Path:
    delegate = vault.parent / f"{vault.name}-trusted-python"
    delegate.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    delegate.chmod(0o755)
    return delegate


def _seed_executor_vault(vault: Path) -> None:
    seed_minimal_vault(vault)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    venv_bin = vault / ".venv" / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)
    _provision_workspace_python_symlink(
        vault,
        source_python=_write_workspace_python_delegate(vault),
    )
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


def _write_external_workspace_python_shim(artifact_root: Path, workspace_root: Path) -> Path:
    source_python = artifact_root / ".venv" / "bin" / "python"
    if not source_python.exists():
        source_python = Path(sys.executable).resolve()
    workspace_python = workspace_root / ".venv" / "bin" / "python"
    workspace_python.parent.mkdir(parents=True, exist_ok=True)
    shim_content = f"#!/bin/sh\nexec {shlex.quote(str(source_python))} \"$@\"\n"
    workspace_python.write_text(shim_content, encoding="utf-8")
    workspace_python.chmod(0o755)
    write_workspace_python_identity(
        workspace_root,
        build_workspace_python_identity(source_python=source_python, shim_content=shim_content),
    )
    return workspace_python


def _json_integer_literal_exceeding_digit_limit() -> str | None:
    get_int_max_str_digits = getattr(sys, "get_int_max_str_digits", None)
    if get_int_max_str_digits is None or get_int_max_str_digits() <= 0:
        return None
    return "1" * (get_int_max_str_digits() + 1)


def _executor_subprocess_completed(
    argv: list[str],
    *,
    preflight_stdout: str = "repo health ok\n",
    preflight_stderr: str = "",
    preflight_returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    if _is_git_rev_parse_head(argv):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
    if len(argv) >= 2 and argv[1] == "-c":
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    if len(argv) >= 4 and argv[1:4] == ["-I", "-B", "-c"]:
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    if _is_worker_repo_health_preflight(argv):
        return subprocess.CompletedProcess(
            argv,
            preflight_returncode,
            stdout=preflight_stdout,
            stderr=preflight_stderr,
        )
    raise AssertionError(f"unexpected subprocess command: {argv!r}")


def _is_git_rev_parse_head(argv: list[str]) -> bool:
    return (
        len(argv) >= 3
        and Path(argv[0]).name == "git"
        and argv[1:3] == ["rev-parse", "HEAD"]
    )


def _is_worker_repo_health_preflight(argv: list[str]) -> bool:
    return _is_full_worker_repo_health_preflight(argv) or _is_focused_worker_repo_health_preflight(argv)


def _is_full_worker_repo_health_preflight(argv: list[str]) -> bool:
    return (
        len(argv) == 3
        and Path(argv[0]).name == "make"
        and argv[1].startswith("PYTHON=")
        and argv[2] == "check"
    )


def _is_focused_worker_repo_health_preflight(argv: list[str]) -> bool:
    return (
        len(argv) >= 7
        and argv[1:6] == ["-B", "-m", "pytest", "-p", "no:cacheprovider"]
        and argv[-1].startswith("tests/")
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


def _prompt_fenced_json(prompt: str, heading: str) -> dict[str, Any]:
    marker = f"{heading}:\n```json\n"
    start = prompt.index(marker) + len(marker)
    end = prompt.index("\n```", start)
    parsed = json.loads(prompt[start:end])
    if not isinstance(parsed, dict):
        raise AssertionError(f"{heading} fenced JSON must be an object")
    return parsed


def _dependency_preflight_request(vault: Path) -> ExecutionRequest:
    return ExecutionRequest(
        artifact_root=vault,
        workspace_root=vault,
        run_id="run-executor",
        role="validator",
        routing_report={},
        scope_freeze={},
        profile={},
        routing_report_rel="",
        scope_freeze_rel="",
        proposal_snapshot_rel="",
        repair_context_rel="",
        repair_context=None,
        artifacts=_ExecutorArtifacts("", "", "", "", "", "", ""),
        argv=[],
        sanitized_argv=[],
        prompt_path=vault / "prompt.md",
        timeout_seconds=30,
        context=RuntimeContext(display_timezone=dt.UTC),
    )


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


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
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="worker", notes=["ok"])
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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
            self.assertEqual(
                report["artifacts"]["stdout"],
                "runs/run-executor/worker.stdout-trace.txt",
            )
            self.assertEqual(
                report["artifacts"]["stderr"],
                "runs/run-executor/worker.stderr-trace.txt",
            )
            self.assertEqual(
                report["artifacts"]["command_log_summary"],
                "runs/run-executor/command-log-summary.json",
            )
            self.assertTrue((vault / "runs" / "run-executor" / "worker-executor-report.json").exists())
            self.assertTrue((vault / "runs" / "run-executor" / "worker.stdout.txt").exists())
            self.assertTrue((vault / "runs" / "run-executor" / "worker.stdout-trace.txt").exists())
            self.assertTrue((vault / "runs" / "run-executor" / "command-log-summary.json").exists())
            prompt = (vault / "runs" / "run-executor" / "worker-prompt.md").read_text(encoding="utf-8")
            self.assertIn("Return JSON only.", prompt)
            self.assertIn("proposal_snapshot", prompt)
            self.assertIn("Repository-required local skills", prompt)
            self.assertIn("$CODEX_HOME/skills/<skill>/SKILL.md", prompt)
            self.assertIn("do not fail solely because the system available-skills list omitted", prompt)
            self.assertIn("Worker structural budget guardrails:", prompt)
            self.assertIn("changed-files-manifest.json", prompt)
            self.assertIn("do not generate or require those artifacts inside the worker phase", prompt)
            self.assertIn("actual changed source and `tests/**` files", prompt)
            self.assertIn("skip promotion even when executor roles report pass", prompt)
            self.assertIn("Before editing, inspect the primary target's current shape", prompt)
            self.assertIn("line, function, and branch footprint", prompt)
            self.assertIn("For structural-complexity repairs", prompt)
            self.assertIn("measured simplification or decomposition slice", prompt)
            self.assertIn("broad fallback branches", prompt)
            self.assertLess(
                prompt.index("Repository write boundary:"),
                prompt.index("Worker structural budget guardrails:"),
            )
            self.assertLess(
                prompt.index("Worker structural budget guardrails:"),
                prompt.index("Execution environment guidance:"),
            )
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
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="validator", notes=["validated"])
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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
            self.assertEqual(report["diagnostics"]["dependency_preflight"]["status"], "pass")
            self.assertTrue(report["diagnostics"]["dependency_preflight"]["python"]["exists"])
            module_statuses = {
                item["package"]: item["status"]
                for item in report["diagnostics"]["dependency_preflight"]["required_modules"]
            }
            self.assertEqual(
                module_statuses,
                {"pytest": "available", "jsonschema": "available", "PyYAML": "available"},
            )
            prompt = (vault / "runs" / "run-executor" / "validator-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("workspace-local `.venv/bin/python`", prompt)
            self.assertIn(
                "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider <focused-selector>",
                prompt,
            )
            self.assertIn("make test-all", prompt)
            self.assertIn("make test-execution-summary-full-current-or-refresh", prompt)
            self.assertIn("PYTHONDONTWRITEBYTECODE=1", prompt)
            self.assertIn("-p no:cacheprovider", prompt)
            self.assertIn("post-worker repo-health preflight", prompt)
            self.assertIn("Executor roles still run before final repo-health capture", prompt)
            self.assertIn("candidate-mechanism-assessment.json", prompt)
            self.assertNotIn("Worker structural budget guardrails:", prompt)
            self.assertNotIn("do not generate or require those artifacts inside the worker phase", prompt)

    def test_execute_codex_exec_role_includes_same_session_repair_context_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            repair_context_rel = "runs/run-executor/same-session-repair-context.json"
            (vault / repair_context_rel).write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/same-session-repair-context.schema.json",
                        "run_id": "run-executor",
                        "failure_taxonomy": "structural_complexity_non_regression",
                        "previous_attempt": {
                            "attempt_index": 1,
                            "artifacts": {
                                "structural_complexity_budget": (
                                    "runs/run-executor/attempts/1/"
                                    "structural-complexity-budget.json"
                                )
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="worker", notes=["repaired"])
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
                execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="worker",
                    routing_report_rel="runs/run-executor/subagent-routing.worker.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    repair_context_rel=repair_context_rel,
                    context=RuntimeContext(display_timezone=dt.UTC),
                )

            prompt = (vault / "runs" / "run-executor" / "worker-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Same-session repair context:", prompt)
            self.assertIn("bounded same-session repair attempt", prompt)
            self.assertIn("not a worker-only retry", prompt)
            self.assertIn("structural_complexity_non_regression", prompt)
            self.assertIn(repair_context_rel, prompt)

    def test_validator_prompt_characterization_preserves_json_template_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            build_execution_request(
                artifact_root=vault,
                workspace_root=vault,
                run_id="run-executor",
                role="validator",
                routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                scope_freeze_rel="runs/run-executor/scope-freeze.json",
                proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                context=RuntimeContext(
                    display_timezone=dt.UTC,
                    clock=lambda: dt.datetime(2026, 5, 1, 12, 34, 56, tzinfo=dt.UTC),
                ),
                timeout_seconds=1800,
            )

            prompt = (vault / "runs" / "run-executor" / "validator-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(
                hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "adcf40b14b547fd5de863c8de19b352129c1a2d0d8b0a9ccde24a163bc870528",
            )
            section_positions = [
                prompt.index(section)
                for section in (
                    "Role profile:",
                    "Developer instructions:",
                    "Run context:",
                    "Repository write boundary:",
                    "Execution environment guidance:",
                    "Repository-required local skills:",
                    "Executor phase boundary:",
                    "Scope freeze summary:",
                    "Routing summary:",
                    "Final response requirements:",
                    "JSON template:",
                )
            ]
            self.assertEqual(section_positions, sorted(section_positions))
            self.assertTrue(prompt.endswith("```\n"))
            self.assertIn('"model_reasoning_effort=\\"xhigh\\""', prompt)
            self.assertNotIn('model_reasoning_effort=/"xhigh/"', prompt)

            template = _prompt_fenced_json(prompt, "JSON template")
            self.assertEqual(template["generated_at"], "2026-05-01T12:34:56Z")
            self.assertEqual(template["command"]["argv"][9], 'model_reasoning_effort="xhigh"')
            self.assertEqual(
                template["diagnostics"]["dependency_preflight"]["status"],
                "not_checked",
            )
            self.assertEqual(
                template["diagnostics"]["dependency_preflight"]["python"]["path"],
                ".venv/bin/python",
            )
            self.assertEqual(
                _prompt_fenced_json(prompt, "Scope freeze summary")["run_id"],
                "run-executor",
            )
            self.assertEqual(
                _prompt_fenced_json(prompt, "Routing summary")["routing_decision"]["sandbox_mode"],
                "workspace-write",
            )

    def test_build_executor_report_is_byte_stable_for_fixed_inputs(self) -> None:
        context = RuntimeContext(
            display_timezone=dt.UTC,
            clock=lambda: dt.datetime(2026, 5, 2, 1, 2, 3, tzinfo=dt.UTC),
        )
        routing_report = _routing_report(
            "validator",
            sandbox_mode="read-only",
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
            selected_rung=3,
        )
        artifacts = _ExecutorArtifacts(
            output_last_message_rel="runs/run-executor/validator-last-message.json",
            stdout_rel="runs/run-executor/validator.stdout-trace.txt",
            stderr_rel="runs/run-executor/validator.stderr-trace.txt",
            raw_stdout_rel="runs/run-executor/validator.stdout.txt",
            raw_stderr_rel="runs/run-executor/validator.stderr.txt",
            command_log_summary_rel="runs/run-executor/command-log-summary.json",
            prompt_rel="runs/run-executor/validator-prompt.md",
        )
        summary = _ExecutionSummary(
            status="fail",
            decision="blocked",
            notes=["validator blocked", "missing dependency evidence"],
            timed_out=True,
            timeout_seconds=1800,
            termination_reason="timeout",
        )
        completed = _SyntheticCompleted(
            returncode=124,
            stdout="validator stdout",
            stderr="validator stderr",
            timed_out=True,
            timeout_seconds=1800,
            termination_reason="timeout",
            launch_succeeded=True,
            signal_sent="sigterm",
            final_state_observed="waitpid",
            stdout_received=True,
            stderr_received=True,
            heartbeat_count=2,
            heartbeat_interval_seconds=30,
            quiet_seconds=90,
            last_stdout_at="2026-05-02T01:01:00Z",
            last_stderr_at="2026-05-02T01:01:30Z",
            last_artifact_touch_at="2026-05-02T01:01:45Z",
            observation_mode="heartbeat",
        )
        dependency_preflight = {
            "role_requires_project_check": True,
            "status": "failed",
            "command": {
                "argv": [".venv/bin/python", "-I", "-B", "-c", "<project-dependency-preflight>"],
                "project_check_lane": "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider <focused-selector>",
            },
            "python": {
                "path": ".venv/bin/python",
                "executable": "/usr/bin/python3",
                "version": "3.13.0",
                "exists": True,
            },
            "required_modules": [
                {
                    "import_name": "pytest",
                    "package": "pytest",
                    "status": "missing",
                    "version": "",
                    "detail": "pytest missing",
                }
            ],
            "returncode": 1,
        }
        request = ExecutorReportRequest(
            run_id="run-executor",
            role="validator",
            scope_freeze={"run_id": "run-executor", "proposal_id": "proposal-example"},
            routing_report=routing_report,
            routing_report_rel="runs/run-executor/subagent-routing.validator.json",
            scope_freeze_rel="runs/run-executor/scope-freeze.json",
            artifacts=artifacts,
            sanitized_argv=["codex", "exec", "-s", "read-only", "-"],
            completed=completed,
            summary=summary,
            dependency_preflight=dependency_preflight,
            context=context,
        )

        first_payload = _build_executor_report(request)
        second_payload = _build_executor_report(request)

        first_bytes = _canonical_bytes(first_payload)
        second_bytes = _canonical_bytes(second_payload)

        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_payload["generated_at"], "2026-05-02T01:02:03Z")
        self.assertEqual(
            first_payload["input_digest"],
            second_payload["input_digest"],
        )
        self.assertEqual(first_payload["result"]["returncode"], 124)
        self.assertTrue(first_payload["result"]["timed_out"])
        self.assertEqual(first_payload["diagnostics"]["notes"], ["validator blocked", "missing dependency evidence"])
        self.assertEqual(
            hashlib.sha256(first_bytes).hexdigest(),
            "87dac62f8eeb0a7a65e2fe4faff58679da38cf240c8d1eb434b07ce813a55ded",
        )

    def test_codex_exec_prefers_workspace_virtualenv_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            venv_bin = vault / ".venv" / "bin"
            venv_bin.mkdir(parents=True, exist_ok=True)
            (venv_bin / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "codex").chmod(0o755)
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)
            captured_env: dict[str, str] = {}

            def fake_run(argv: list[str], **kwargs: object) -> object:
                self.assertEqual(argv[0], str(outer_codex))
                self.assertEqual(kwargs["cwd"], vault)
                self.assertEqual(argv[argv.index("--cd") + 1], str(vault))
                out_index = argv.index("-o") + 1
                env = kwargs.get("env")
                self.assertIsInstance(env, dict)
                captured_env.update(cast(dict[str, str], env))
                write_valid_model_output(
                    Path(argv[out_index]),
                    vault,
                    run_id="run-executor",
                    role="validator",
                    notes=["validated"],
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch.dict(
                os.environ,
                {"PATH": f"{venv_bin}{os.pathsep}{outer_codex.parent}"},
            ), mock.patch(
                "ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run
            ):
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
            self.assertEqual(report["command"]["argv"][0], "codex")
            self.assertEqual(report["command"]["argv"][report["command"]["argv"].index("--cd") + 1], ".")
            self.assertEqual(captured_env["VIRTUAL_ENV"], str(vault / ".venv"))
            self.assertEqual(captured_env["PATH"].split(os.pathsep)[0], str(venv_bin))
            python_check = subprocess.run(
                ["python", "-c", "print('workspace-python-ok')"],
                cwd=vault,
                env=captured_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(python_check.stdout, "workspace-python-ok\n")
            prompt = (vault / "runs" / "run-executor" / "validator-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(str(outer_codex), prompt)

    def test_non_worker_dependency_preflight_blocks_when_workspace_python_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            venv_python = vault / ".venv" / "bin" / "python"
            venv_python.unlink()
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout") as run:
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

            run.assert_not_called()
            self.assertEqual(report["status"], "fail")
            self.assertFalse(report["result"]["launch_succeeded"])
            self.assertEqual(report["result"]["final_state_observed"], "preflight_blocked")
            self.assertEqual(report["diagnostics"]["dependency_preflight"]["status"], "fail")
            self.assertEqual(
                report["diagnostics"]["dependency_preflight"]["command"]["project_check_lane"],
                "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider <focused-selector>",
            )
            self.assertFalse(report["diagnostics"]["dependency_preflight"]["python"]["exists"])
            notes = "\n".join(report["diagnostics"]["notes"])
            self.assertIn("executor dependency preflight blocked validator", notes)
            self.assertIn("missing workspace virtualenv python", notes)
            self.assertTrue((vault / "runs" / "run-executor" / "validator.stdout.txt").is_file())
            self.assertTrue((vault / "runs" / "run-executor" / "validator.stderr.txt").is_file())

    def test_non_worker_dependency_preflight_uses_trusted_candidate_runner_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            expected_trusted_python = trusted_dependency_preflight_python(
                vault,
                workspace_root=vault,
            ).absolute()

            def fake_preflight(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if _is_git_rev_parse_head(argv):
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
                workspace_python = vault / ".venv" / "bin" / "python"
                self.assertEqual(argv[0], str(expected_trusted_python))
                self.assertNotEqual(Path(argv[0]), workspace_python)
                self.assertEqual(Path(str(kwargs.get("cwd"))), vault)
                payload = {
                    "python": {"executable": str(expected_trusted_python), "version": "3.test"},
                    "modules": [
                        {
                            "import_name": "pytest",
                            "package": "pytest",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "jsonschema",
                            "package": "jsonschema",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "yaml",
                            "package": "PyYAML",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                    ],
                }
                return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="validator", notes=["validated"])
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
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
            self.assertEqual(
                report["diagnostics"]["dependency_preflight"]["python"]["path"],
                ".venv/bin/python",
            )
            self.assertEqual(
                report["diagnostics"]["dependency_preflight"]["python"]["executable"],
                str(expected_trusted_python),
            )

    def test_non_worker_dependency_preflight_blocks_probe_execution_failures(self) -> None:
        cases = (
            (124, True, "late timeout detail", "dependency preflight timed out"),
            (126, False, "trusted candidate launch denied", "trusted candidate launch denied"),
        )
        for returncode, timed_out, stderr, expected_detail in cases:
            with self.subTest(returncode=returncode), tempfile.TemporaryDirectory() as temp_dir:
                vault = Path(temp_dir) / "vault"
                vault.mkdir()
                _seed_executor_vault(vault)
                request = _dependency_preflight_request(vault)
                outcome = TrustedCandidateRunOutcome(
                    returncode=returncode,
                    stdout="",
                    stderr=stderr,
                    timed_out=timed_out,
                    argv=[],
                    audit_record={},
                )

                with (
                    mock.patch(
                        "ops.scripts.core.codex_exec_dependency_preflight_runtime.sys.executable",
                        str(vault / ".venv" / "bin" / "python"),
                    ),
                    mock.patch(
                        "ops.scripts.core.codex_exec_dependency_preflight_decision_runtime.run_trusted_candidate_command",
                        return_value=outcome,
                    ),
                ):
                    preflight, summary = non_worker_dependency_preflight(request)

                self.assertEqual(preflight["status"], "fail")
                self.assertEqual(preflight["returncode"], 1)
                self.assertEqual(preflight["python"]["path"], ".venv/bin/python")
                self.assertTrue(preflight["python"]["exists"])
                self.assertTrue(
                    all(
                        module["status"] == "unknown"
                        and module["detail"] == expected_detail
                        for module in preflight["required_modules"]
                    )
                )
                self.assertIsNotNone(summary)
                assert summary is not None
                self.assertEqual(summary.decision, "blocked")
                self.assertEqual(summary.timed_out, timed_out)
                self.assertIn(expected_detail, " ".join(summary.notes))

    def test_trusted_dependency_preflight_python_preserves_workspace_symlink_to_external_python(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            try:
                workspace_python.symlink_to(Path(sys.executable).resolve(strict=True))
            except OSError as exc:
                self.skipTest(f"workspace symlink setup unavailable: {exc}")

            with mock.patch(
                "ops.scripts.core.codex_exec_dependency_preflight_runtime.sys.executable",
                str(workspace_python),
            ):
                trusted_python = trusted_dependency_preflight_python(
                    vault,
                    workspace_root=vault,
                )

            self.assertEqual(trusted_python, workspace_python.absolute())
            self.assertNotEqual(trusted_python, Path(sys.executable).resolve(strict=True))

    def test_same_root_dependency_preflight_captures_workspace_symlink_realpath(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            source_python = Path(temp_dir) / "source-python"
            source_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source_python.chmod(0o755)
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            try:
                workspace_python.symlink_to(source_python)
            except OSError as exc:
                self.skipTest(f"workspace symlink setup unavailable: {exc}")
            request = _dependency_preflight_request(vault)
            captured_request: Any | None = None

            def fake_run_trusted_candidate(run_request: Any) -> TrustedCandidateRunOutcome:
                nonlocal captured_request
                captured_request = run_request
                payload = {
                    "python": {"executable": str(workspace_python), "version": "3.test"},
                    "modules": [
                        {
                            "import_name": "pytest",
                            "package": "pytest",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "jsonschema",
                            "package": "jsonschema",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "yaml",
                            "package": "PyYAML",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                    ],
                }
                return TrustedCandidateRunOutcome(
                    returncode=0,
                    stdout=json.dumps(payload),
                    stderr="",
                    timed_out=False,
                    argv=run_request.argv,
                    audit_record={},
                )

            with (
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_runtime.sys.executable",
                    str(workspace_python),
                ),
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_decision_runtime.run_trusted_candidate_command",
                    side_effect=fake_run_trusted_candidate,
                ),
            ):
                preflight, summary = non_worker_dependency_preflight(request)

            self.assertEqual(preflight["status"], "pass")
            self.assertIsNone(summary)
            self.assertIsNotNone(captured_request)
            assert captured_request is not None
            self.assertEqual(captured_request.trusted_python, workspace_python.absolute())
            self.assertEqual(captured_request.trusted_python_realpath, source_python.resolve(strict=True))

    def test_same_root_dependency_preflight_preserves_workspace_venv_for_external_current_python(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            source_python = Path(temp_dir) / "source-python"
            source_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source_python.chmod(0o755)
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            try:
                workspace_python.symlink_to(source_python)
            except OSError as exc:
                self.skipTest(f"workspace symlink setup unavailable: {exc}")
            request = _dependency_preflight_request(vault)
            captured_request: Any | None = None

            def fake_run_trusted_candidate(run_request: Any) -> TrustedCandidateRunOutcome:
                nonlocal captured_request
                captured_request = run_request
                payload = {
                    "python": {"executable": str(workspace_python), "version": "3.test"},
                    "modules": [
                        {
                            "import_name": "pytest",
                            "package": "pytest",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "jsonschema",
                            "package": "jsonschema",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "yaml",
                            "package": "PyYAML",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                    ],
                }
                return TrustedCandidateRunOutcome(
                    returncode=0,
                    stdout=json.dumps(payload),
                    stderr="",
                    timed_out=False,
                    argv=run_request.argv,
                    audit_record={},
                )

            with (
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_runtime.sys.executable",
                    str(source_python),
                ),
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_decision_runtime.run_trusted_candidate_command",
                    side_effect=fake_run_trusted_candidate,
                ),
            ):
                preflight, summary = non_worker_dependency_preflight(request)

            self.assertEqual(preflight["status"], "pass")
            self.assertIsNone(summary)
            self.assertIsNotNone(captured_request)
            assert captured_request is not None
            self.assertEqual(captured_request.trusted_python, workspace_python.absolute())
            self.assertEqual(captured_request.trusted_python_realpath, source_python.resolve(strict=True))

    def test_same_root_dependency_preflight_blocks_symlink_swapped_inside_before_realpath_capture(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            source_python = Path(temp_dir) / "source-python"
            source_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source_python.chmod(0o755)
            malicious_python = vault / "malicious-python"
            malicious_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            malicious_python.chmod(0o755)
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            try:
                workspace_python.symlink_to(source_python)
            except OSError as exc:
                self.skipTest(f"workspace symlink setup unavailable: {exc}")
            request = _dependency_preflight_request(vault)

            def fake_trusted_python(*_: Any, **__: Any) -> Path:
                workspace_python.unlink()
                workspace_python.symlink_to(malicious_python)
                return workspace_python.absolute()

            with (
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_decision_runtime.trusted_dependency_preflight_python",
                    side_effect=fake_trusted_python,
                ),
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_decision_runtime.run_trusted_candidate_command"
                ) as run,
            ):
                preflight, summary = non_worker_dependency_preflight(request)

            run.assert_not_called()
            self.assertEqual(preflight["status"], "fail")
            self.assertEqual(preflight["returncode"], 126)
            self.assertIsNotNone(summary)
            assert summary is not None
            notes = " ".join(summary.notes)
            self.assertIn("workspace Python trust check", notes)
            self.assertIn("symlink resolves inside the workspace", notes)

    def test_same_root_workspace_python_allows_symlink_resolving_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            source_python = Path(temp_dir) / "source-python"
            source_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source_python.chmod(0o755)
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            try:
                workspace_python.symlink_to(source_python)
            except OSError as exc:
                self.skipTest(f"workspace symlink setup unavailable: {exc}")
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=vault,
                    workspace_root=vault,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(issue, "")

    def test_same_root_workspace_python_blocks_symlink_resolving_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            source_python = vault / "target-python"
            source_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source_python.chmod(0o755)
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            try:
                workspace_python.symlink_to(source_python)
            except OSError as exc:
                self.skipTest(f"workspace symlink setup unavailable: {exc}")
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=vault,
                    workspace_root=vault,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(issue, "workspace virtualenv python symlink resolves inside the workspace")

    def test_same_root_workspace_python_blocks_local_file_without_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            workspace_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            workspace_python.chmod(0o755)
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=vault,
                    workspace_root=vault,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(issue, "missing workspace python identity manifest")

    def test_same_root_workspace_python_blocks_self_signed_identity_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            shim_content = "#!/bin/sh\nexit 0\n"
            workspace_python.write_text(shim_content, encoding="utf-8")
            workspace_python.chmod(0o755)
            write_workspace_python_identity(
                vault,
                build_workspace_python_identity(
                    source_python=workspace_python,
                    shim_content=shim_content,
                ),
            )
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=vault,
                    workspace_root=vault,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(issue, "same-root workspace python identity manifest is self-signed")

    def test_same_root_dependency_preflight_blocks_untrusted_workspace_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            marker = vault / "workspace-python-executed.txt"
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            workspace_python.write_text(
                "#!/bin/sh\n"
                f"touch {shlex.quote(str(marker))}\n"
                "printf '%s\\n' '{\"python\":{\"executable\":\"workspace-python\",\"version\":\"0\"},\"modules\":[{\"import_name\":\"pytest\",\"package\":\"pytest\",\"status\":\"available\",\"version\":\"x\",\"detail\":\"\"},{\"import_name\":\"jsonschema\",\"package\":\"jsonschema\",\"status\":\"available\",\"version\":\"x\",\"detail\":\"\"},{\"import_name\":\"yaml\",\"package\":\"PyYAML\",\"status\":\"available\",\"version\":\"x\",\"detail\":\"\"}]}'\n",
                encoding="utf-8",
            )
            workspace_python.chmod(0o755)
            request = _dependency_preflight_request(vault)

            with mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run") as run:
                preflight, summary = non_worker_dependency_preflight(request)

            run.assert_not_called()
            self.assertEqual(preflight["status"], "fail")
            self.assertEqual(preflight["returncode"], 126)
            self.assertIsNotNone(summary)
            self.assertFalse(marker.exists())
            self.assertEqual(preflight["command"]["argv"][0], ".venv/bin/python")
            self.assertEqual(preflight["python"]["path"], ".venv/bin/python")
            assert summary is not None
            notes = " ".join(summary.notes)
            self.assertIn("workspace Python trust check", notes)
            self.assertIn("missing workspace python identity manifest", notes)

    def test_same_root_dependency_preflight_blocks_self_signed_workspace_python_without_execution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            marker = vault / "workspace-python-executed.txt"
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            payload = json.dumps(
                {
                    "python": {"executable": "workspace-python", "version": "0"},
                    "modules": [
                        {
                            "import_name": "pytest",
                            "package": "pytest",
                            "status": "available",
                            "version": "x",
                            "detail": "",
                        },
                        {
                            "import_name": "jsonschema",
                            "package": "jsonschema",
                            "status": "available",
                            "version": "x",
                            "detail": "",
                        },
                        {
                            "import_name": "yaml",
                            "package": "PyYAML",
                            "status": "available",
                            "version": "x",
                            "detail": "",
                        },
                    ],
                },
                sort_keys=True,
            )
            shim_content = (
                "#!/bin/sh\n"
                f"touch {shlex.quote(str(marker))}\n"
                f"printf '%s\\n' {shlex.quote(payload)}\n"
            )
            workspace_python.write_text(shim_content, encoding="utf-8")
            workspace_python.chmod(0o755)
            write_workspace_python_identity(
                vault,
                build_workspace_python_identity(
                    source_python=workspace_python,
                    shim_content=shim_content,
                ),
            )
            request = _dependency_preflight_request(vault)

            with mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run") as run:
                preflight, summary = non_worker_dependency_preflight(request)

            run.assert_not_called()
            self.assertEqual(preflight["status"], "fail")
            self.assertEqual(preflight["returncode"], 126)
            self.assertIsNotNone(summary)
            self.assertFalse(marker.exists())
            self.assertEqual(preflight["command"]["argv"][0], ".venv/bin/python")
            self.assertEqual(preflight["python"]["path"], ".venv/bin/python")
            assert summary is not None
            notes = " ".join(summary.notes)
            self.assertIn("workspace Python trust check", notes)
            self.assertIn("self-signed", notes)

    def test_same_root_dependency_preflight_blocks_untrusted_sys_executable_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            marker = vault / "workspace-python-executed.txt"
            workspace_python = vault / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            workspace_python.write_text(
                "#!/bin/sh\n"
                f"touch {shlex.quote(str(marker))}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            workspace_python.chmod(0o755)
            request = _dependency_preflight_request(vault)

            with (
                mock.patch(
                    "ops.scripts.core.codex_exec_dependency_preflight_runtime.sys.executable",
                    str(workspace_python),
                ),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run") as run,
            ):
                preflight, summary = non_worker_dependency_preflight(request)

            run.assert_not_called()
            self.assertEqual(preflight["status"], "fail")
            self.assertEqual(preflight["returncode"], 126)
            self.assertFalse(marker.exists())
            self.assertIsNotNone(summary)
            assert summary is not None
            notes = " ".join(summary.notes)
            self.assertIn("workspace Python trust check", notes)
            self.assertIn("missing workspace python identity manifest", notes)

    def test_external_workspace_dependency_preflight_executes_artifact_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            _seed_executor_vault(artifact_root)
            seed_subagent_profiles(artifact_root, ["validator"])
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            _write_routing_report(
                artifact_root,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            artifact_python = (artifact_root / ".venv" / "bin" / "python").absolute()
            trusted_artifact_python = artifact_python.resolve(strict=True)
            captured_preflight_argv: list[str] = []

            def fake_preflight(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if _is_git_rev_parse_head(argv):
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
                captured_preflight_argv[:] = argv
                self.assertEqual(argv[0], str(trusted_artifact_python))
                self.assertNotEqual(Path(argv[0]), workspace_python.absolute())
                self.assertEqual(Path(str(kwargs.get("cwd"))), workspace_root)
                payload = {
                    "python": {"executable": str(artifact_python), "version": "3.test"},
                    "modules": [
                        {
                            "import_name": "pytest",
                            "package": "pytest",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "jsonschema",
                            "package": "jsonschema",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                        {
                            "import_name": "yaml",
                            "package": "PyYAML",
                            "status": "available",
                            "version": "test",
                            "detail": "",
                        },
                    ],
                }
                return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(
                    Path(argv[out_index]),
                    artifact_root,
                    run_id="run-executor",
                    role="validator",
                    notes=["validated"],
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
                report = execute_codex_exec_role(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=dt.UTC),
                )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(captured_preflight_argv[0], str(trusted_artifact_python))
            self.assertEqual(
                report["diagnostics"]["dependency_preflight"]["python"]["path"],
                ".venv/bin/python",
            )
            self.assertEqual(
                report["diagnostics"]["dependency_preflight"]["python"]["executable"],
                ".venv/bin/python",
            )

    def test_non_worker_dependency_preflight_ignores_workspace_import_shadowing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            marker = vault / "shadow-executed.txt"
            (vault / "pytest.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="validator", notes=["validated"])
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch.dict(os.environ, {"PYTHONPATH": str(vault)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
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
            self.assertEqual(report["diagnostics"]["dependency_preflight"]["status"], "pass")
            self.assertEqual(
                report["diagnostics"]["dependency_preflight"]["command"]["argv"],
                [".venv/bin/python", "-I", "-B", "-c", "<project-dependency-preflight>"],
            )
            self.assertFalse(marker.exists())

    def test_external_workspace_python_shim_preserves_artifact_venv_symlink(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            base_python = Path(temp_dir) / "base-python"
            base_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            base_python.chmod(0o755)
            try:
                artifact_python.symlink_to(base_python)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            expected = f"#!/bin/sh\nexec {shlex.quote(str(artifact_python))} \"$@\"\n"

            self.assertEqual(_expected_external_workspace_python_shim(artifact_root), expected)
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            self.assertEqual(workspace_python.read_text(encoding="utf-8"), expected)
            self.assertNotIn(str(base_python), expected)
            identity = load_workspace_python_identity(workspace_root)
            self.assertIsNotNone(identity)
            assert identity is not None
            self.assertEqual(identity.source_realpath, str(base_python.resolve()))
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )
            self.assertEqual(
                external_workspace_python_issue(
                    request,
                    workspace_python=workspace_python,
                ),
                "",
            )

    def test_external_workspace_python_rejects_forged_manifest_and_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)

            workspace_python = workspace_root / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            malicious_content = "#!/bin/sh\necho MALICIOUS_PYTHON_ACTIVE\nexit 42\n"
            workspace_python.write_text(malicious_content, encoding="utf-8")
            workspace_python.chmod(0o755)
            write_workspace_python_identity(
                workspace_root,
                build_workspace_python_identity(
                    source_python=workspace_python,
                    shim_content=malicious_content,
                ),
            )

            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )
            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertIn("identity manifest does not match trusted artifact shim", issue)

    def test_external_workspace_python_requires_identity_manifest_for_external_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            workspace_python_identity_path(workspace_root).unlink()
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(issue, "missing workspace python identity manifest")

    def test_external_workspace_python_reports_malformed_identity_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            workspace_python_identity_path(workspace_root).write_text("{bad json", encoding="utf-8")
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertIn("workspace python identity manifest is invalid JSON", issue)

    def test_external_workspace_python_reports_parser_valueerror_identity_manifest(self) -> None:
        manifest_text = _json_integer_literal_exceeding_digit_limit()
        if manifest_text is None:
            self.skipTest("Python JSON integer digit limit is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            workspace_python_identity_path(workspace_root).write_text(
                manifest_text,
                encoding="utf-8",
            )
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertIn("workspace python identity manifest is invalid JSON", issue)

    def test_external_workspace_python_reports_invalid_identity_manifest_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            identity = load_workspace_python_identity(workspace_root)
            self.assertIsNotNone(identity)
            assert identity is not None
            payload = identity.to_payload()
            payload["source_device"] = "not-an-int"
            workspace_python_identity_path(workspace_root).write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertIn("workspace python identity manifest has invalid fields", issue)

    def test_external_workspace_python_rejects_artifact_source_identity_changed_after_provisioning(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            first_python = Path(temp_dir) / "first-python"
            second_python = Path(temp_dir) / "second-python"
            for python_path in (first_python, second_python):
                python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                python_path.chmod(0o755)
            try:
                artifact_python.symlink_to(first_python)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            artifact_python.unlink()
            artifact_python.symlink_to(second_python)
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(
                issue,
                "trusted workspace python source identity changed since workspace provisioning",
            )

    def test_external_workspace_python_rejects_artifact_source_digest_changed_after_provisioning(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)
            source_stat = artifact_python.stat()
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            with artifact_python.open("w", encoding="utf-8") as file:
                file.write("#!/bin/sh\nexit 99\n")
            artifact_python.chmod(0o755)
            self.assertEqual(artifact_python.stat().st_ino, source_stat.st_ino)
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            issue = external_workspace_python_issue(
                request,
                workspace_python=workspace_python,
            )

            self.assertEqual(
                issue,
                "trusted workspace python source digest changed since workspace provisioning",
            )

    def test_external_workspace_python_reuses_verified_identity_manifest_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.parent.mkdir(parents=True)
            artifact_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            artifact_python.chmod(0o755)
            trusted_content = _expected_external_workspace_python_shim(artifact_root)
            trusted_identity = build_workspace_python_identity(
                source_python=artifact_python,
                shim_content=trusted_content,
            )
            workspace_python = workspace_root / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            malicious_content = "#!/bin/sh\necho MALICIOUS_PYTHON_ACTIVE\nexit 42\n"
            workspace_python.write_text(malicious_content, encoding="utf-8")
            workspace_python.chmod(0o755)
            write_workspace_python_identity(
                workspace_root,
                build_workspace_python_identity(
                    source_python=workspace_python,
                    shim_content=malicious_content,
                ),
            )
            request = cast(
                Any,
                SimpleNamespace(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                ),
            )

            def verify_and_swap_manifest(
                workspace_root_arg: Path,
                *,
                workspace_python: Path,
                expected_identity: object,
            ) -> str:
                write_workspace_python_identity(workspace_root, trusted_identity)
                return workspace_python_identity_runtime.verify_workspace_python_shim(
                    workspace_root_arg,
                    workspace_python=workspace_python,
                    expected_identity=cast(Any, expected_identity),
                )

            with mock.patch(
                "ops.scripts.core.codex_exec_workspace_runtime.verify_workspace_python_shim",
                side_effect=verify_and_swap_manifest,
            ):
                issue = external_workspace_python_issue(
                    request,
                    workspace_python=workspace_python,
                )

            self.assertIn("identity manifest does not match trusted artifact shim", issue)

    def test_codex_exec_uses_workspace_output_when_artifact_root_differs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            _seed_executor_vault(artifact_root)
            seed_subagent_profiles(artifact_root, ["validator"])
            artifact_python = artifact_root / ".venv" / "bin" / "python"
            artifact_python.write_text(
                f"#!/bin/sh\n"
                f"if [ \"${{1:-}}\" = \"-c\" ]; then exec {json.dumps(sys.executable)} \"$@\"; fi\n"
                "printf 'artifact-python\\n'\n",
                encoding="utf-8",
            )
            artifact_python.chmod(0o755)
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            workspace_venv_bin = workspace_python.parent
            (workspace_root / "ops" / "schemas").mkdir(parents=True)
            (workspace_root / "ops" / "schemas" / "executor-report.schema.json").write_text(
                (REPO_ROOT / "ops" / "schemas" / "executor-report.schema.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            _write_routing_report(
                artifact_root,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)
            captured_env: dict[str, str] = {}

            def fake_run(argv: list[str], **kwargs: object) -> object:
                self.assertEqual(kwargs["cwd"], workspace_root)
                self.assertEqual(argv[argv.index("--cd") + 1], str(workspace_root))
                self.assertEqual(
                    argv[argv.index("--output-schema") + 1],
                    str(workspace_root / "ops/schemas/executor-report.schema.json"),
                )
                env = kwargs.get("env")
                self.assertIsInstance(env, dict)
                captured_env.update(cast(dict[str, str], env))
                out_index = argv.index("-o") + 1
                self.assertTrue(Path(argv[out_index]).is_relative_to(workspace_root))
                write_valid_model_output(
                    Path(argv[out_index]),
                    artifact_root,
                    run_id="run-executor",
                    role="validator",
                    notes=["validated"],
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch.dict(
                os.environ,
                {"PATH": f"{workspace_venv_bin}{os.pathsep}{outer_codex.parent}"},
            ), mock.patch(
                "ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run
            ):
                report = execute_codex_exec_role(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "pass")
            self.assertIn("--full-auto", report["command"]["argv"])
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", report["command"]["argv"])
            self.assertEqual(captured_env["VIRTUAL_ENV"], str(workspace_root / ".venv"))
            self.assertEqual(captured_env["PATH"].split(os.pathsep)[0], str(workspace_venv_bin))
            self.assertTrue(
                (artifact_root / "runs" / "run-executor" / "validator-last-message.json").is_file()
            )
            python_check = subprocess.run(
                ["python"],
                cwd=workspace_root,
                env=captured_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(python_check.stdout, "artifact-python\n")

    def test_codex_exec_uses_external_workspace_sandbox_for_read_only_temp_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            _seed_executor_vault(artifact_root)
            seed_subagent_profiles(artifact_root, ["provenance-auditor"])
            _write_external_workspace_python_shim(artifact_root, workspace_root)
            (workspace_root / "ops" / "schemas").mkdir(parents=True)
            (workspace_root / "ops" / "schemas" / "executor-report.schema.json").write_text(
                (REPO_ROOT / "ops" / "schemas" / "executor-report.schema.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            _write_routing_report(
                artifact_root,
                "provenance-auditor",
                sandbox_mode="read-only",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **kwargs: object) -> object:
                self.assertEqual(kwargs["cwd"], workspace_root)
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
                self.assertEqual(argv[2:5], ["-s", "read-only", "--skip-git-repo-check"])
                out_index = argv.index("-o") + 1
                self.assertTrue(Path(argv[out_index]).is_relative_to(workspace_root))
                write_valid_model_output(
                    Path(argv[out_index]),
                    artifact_root,
                    run_id="run-executor",
                    role="provenance-auditor",
                    notes=["audited"],
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
                report = execute_codex_exec_role(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                    run_id="run-executor",
                    role="provenance-auditor",
                    routing_report_rel="runs/run-executor/subagent-routing.provenance-auditor.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["executor"]["sandbox_mode"], "read-only")
            prompt = (artifact_root / "runs" / "run-executor" / "provenance-auditor-prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("disposable mechanism workspace copy", prompt)

    def test_non_worker_dependency_preflight_blocks_modified_external_workspace_python_shim(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            _seed_executor_vault(artifact_root)
            seed_subagent_profiles(artifact_root, ["validator"])
            workspace_python = _write_external_workspace_python_shim(artifact_root, workspace_root)
            workspace_python.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            workspace_python.chmod(0o755)
            _write_routing_report(
                artifact_root,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            with (
                mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout") as run,
            ):
                report = execute_codex_exec_role(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            run.assert_not_called()
            self.assertEqual(report["status"], "fail")
            notes = "\n".join(report["diagnostics"]["notes"])
            self.assertIn("workspace Python trust check", notes)
            self.assertIn("shim content does not match identity manifest", notes)

    def test_non_worker_dependency_preflight_blocks_missing_external_workspace_python_identity_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            _seed_executor_vault(artifact_root)
            seed_subagent_profiles(artifact_root, ["validator"])
            _write_external_workspace_python_shim(artifact_root, workspace_root)
            workspace_python_identity_path(workspace_root).unlink()
            _write_routing_report(
                artifact_root,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            with (
                mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout") as run,
            ):
                report = execute_codex_exec_role(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            run.assert_not_called()
            self.assertEqual(report["status"], "fail")
            notes = "\n".join(report["diagnostics"]["notes"])
            self.assertIn("workspace Python trust check", notes)
            self.assertIn("missing workspace python identity manifest", notes)

    def test_non_worker_dependency_preflight_blocks_malformed_external_workspace_python_identity_manifest(
        self,
    ) -> None:
        manifest_cases = {
            "json-decode-error": "{bad json",
        }
        parser_value_error_manifest = _json_integer_literal_exceeding_digit_limit()
        if parser_value_error_manifest is not None:
            manifest_cases["parser-value-error"] = parser_value_error_manifest
        for case_name, manifest_text in manifest_cases.items():
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as temp_dir:
                artifact_root = Path(temp_dir) / "artifact"
                workspace_root = Path(temp_dir) / "workspace"
                artifact_root.mkdir()
                workspace_root.mkdir()
                _seed_executor_vault(artifact_root)
                seed_subagent_profiles(artifact_root, ["validator"])
                _write_external_workspace_python_shim(artifact_root, workspace_root)
                workspace_python_identity_path(workspace_root).write_text(
                    manifest_text,
                    encoding="utf-8",
                )
                _write_routing_report(
                    artifact_root,
                    "validator",
                    sandbox_mode="workspace-write",
                    model="gpt-5.6-sol",
                    reasoning_effort="xhigh",
                    selected_rung=3,
                )
                outer_codex = Path(temp_dir) / "outer-bin" / "codex"
                outer_codex.parent.mkdir()
                outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
                outer_codex.chmod(0o755)

                with (
                    mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                    mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout") as run,
                ):
                    report = execute_codex_exec_role(
                        artifact_root=artifact_root,
                        workspace_root=workspace_root,
                        run_id="run-executor",
                        role="validator",
                        routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                        scope_freeze_rel="runs/run-executor/scope-freeze.json",
                        proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                        context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                    )

                run.assert_not_called()
                self.assertEqual(report["status"], "fail")
                notes = "\n".join(report["diagnostics"]["notes"])
                self.assertIn("workspace Python trust check", notes)
                self.assertIn("workspace python identity manifest is invalid JSON", notes)

    def test_codex_exec_blocks_workspace_virtualenv_codex_when_no_outer_codex_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            venv_bin = vault / ".venv" / "bin"
            venv_bin.mkdir(parents=True, exist_ok=True)
            (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "python").chmod(0o755)
            (venv_bin / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (venv_bin / "codex").chmod(0o755)
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            with (
                mock.patch.dict(os.environ, {"PATH": str(venv_bin)}),
                self.assertRaisesRegex(
                    ExecutorContractError,
                    "refusing to launch a workspace codex",
                ),
            ):
                execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

    def test_codex_exec_blocks_workspace_root_codex_with_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            (vault / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (vault / "codex").chmod(0o755)
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            with (
                mock.patch.dict(os.environ, {"PATH": ""}),
                self.assertRaisesRegex(
                    ExecutorContractError,
                    "refusing to launch a workspace codex",
                ),
            ):
                execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

    def test_codex_exec_blocks_workspace_subdirectory_codex_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            workspace_bin = vault / "tools" / "bin"
            workspace_bin.mkdir(parents=True)
            (workspace_bin / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (workspace_bin / "codex").chmod(0o755)
            _write_routing_report(
                vault,
                "validator",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            with (
                mock.patch.dict(os.environ, {"PATH": str(workspace_bin)}),
                self.assertRaisesRegex(
                    ExecutorContractError,
                    "refusing workspace-relative fallback",
                ),
            ):
                execute_codex_exec_role(
                    artifact_root=vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    role="validator",
                    routing_report_rel="runs/run-executor/subagent-routing.validator.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

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
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="reviewer", notes=["reviewed"])
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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
            self.assertIn("post-worker repo-health preflight", prompt)
            self.assertIn("Executor roles still run before final repo-health capture", prompt)

    def test_non_worker_tmp_replay_artifacts_do_not_trip_mutation_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["reviewer"])
            _write_routing_report(
                vault,
                "reviewer",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                tmp_dir = vault / "tmp"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                (tmp_dir / "reviewer-mechanism-assessment.json").write_text(
                    "{}\n",
                    encoding="utf-8",
                )
                (tmp_dir / "reviewer-promotion-report.json").write_text(
                    "{}\n",
                    encoding="utf-8",
                )
                write_valid_model_output(
                    Path(argv[out_index]),
                    vault,
                    run_id="run-executor",
                    role="reviewer",
                    notes=["reviewed"],
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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
            self.assertNotIn(
                "non-worker workspace mutation guard blocked",
                "\n".join(report["diagnostics"]["notes"]),
            )
            self.assertTrue((vault / "tmp" / "reviewer-mechanism-assessment.json").is_file())
            self.assertTrue((vault / "tmp" / "reviewer-promotion-report.json").is_file())

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
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
                selected_rung=3,
            )

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="validator", notes=["validated"])
                (vault / "ops" / "scripts" / "example.py").write_text(
                    "def subject():\n    return 2\n",
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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
                model="gpt-5.6-sol",
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

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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
            self.assertEqual(
                timeout_failure["artifacts"]["stderr"],
                "runs/run-executor/worker.stderr-trace.txt",
            )
            self.assertEqual(
                timeout_failure["artifacts"]["command_log_summary"],
                "runs/run-executor/command-log-summary.json",
            )
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
                model="gpt-5.6-sol",
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

            with mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run):
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

    def test_successful_codex_exit_without_model_output_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            def fake_run(_argv: list[str], **_: object) -> object:
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
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
            self.assertIn("without model output", "\n".join(report["diagnostics"]["notes"]))

    def test_successful_codex_exit_ignores_stale_model_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            stale_output = vault / "runs" / "run-executor" / "worker-last-message.json"
            stale_output.write_text(
                json.dumps({"status": "pass", "diagnostics": {"notes": ["stale pass"]}}),
                encoding="utf-8",
            )
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            def fake_run(_argv: list[str], **_: object) -> object:
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
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
            notes = "\n".join(report["diagnostics"]["notes"])
            self.assertIn("without model output", notes)
            self.assertNotIn("stale pass", notes)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics are required")
    def test_successful_codex_exit_rejects_symlinked_workspace_model_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifact"
            workspace_root = Path(temp_dir) / "workspace"
            artifact_root.mkdir()
            workspace_root.mkdir()
            _seed_executor_vault(artifact_root)
            seed_subagent_profiles(artifact_root, ["worker"])
            _write_routing_report(
                artifact_root,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)
            outside_output = Path(temp_dir) / "outside-last-message.json"
            outside_output.write_text(
                json.dumps({"status": "pass", "diagnostics": {"notes": ["outside pass"]}}),
                encoding="utf-8",
            )

            def fake_run(argv: list[str], **_: object) -> object:
                output_path = Path(argv[argv.index("-o") + 1])
                output_path.unlink(missing_ok=True)
                os.symlink(outside_output, output_path)
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
                report = execute_codex_exec_role(
                    artifact_root=artifact_root,
                    workspace_root=workspace_root,
                    run_id="run-executor",
                    role="worker",
                    routing_report_rel="runs/run-executor/subagent-routing.worker.json",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

            self.assertEqual(report["status"], "fail")
            notes = "\n".join(report["diagnostics"]["notes"])
            self.assertIn("invalid model output file", notes)
            self.assertNotIn("outside pass", notes)
            self.assertFalse(
                (artifact_root / "runs" / "run-executor" / "worker-last-message.json").exists()
            )

    def test_successful_codex_exit_with_invalid_model_output_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            _write_routing_report(
                vault,
                "worker",
                sandbox_mode="workspace-write",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                selected_rung=2,
            )
            outer_codex = Path(temp_dir) / "outer-bin" / "codex"
            outer_codex.parent.mkdir()
            outer_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            outer_codex.chmod(0o755)

            def fake_run(argv: list[str], **_: object) -> object:
                Path(argv[argv.index("-o") + 1]).write_text("{", encoding="utf-8")
                return mock.Mock(returncode=0, stdout="ok\n", stderr="")

            with (
                mock.patch.dict(os.environ, {"PATH": str(outer_codex.parent)}),
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
            ):
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
            self.assertIn("invalid model output JSON", "\n".join(report["diagnostics"]["notes"]))

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
                write_valid_model_output(output_path, vault, run_id="run-executor", role=role, notes=[f"{role} ok"])
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            def fake_preflight(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if _is_worker_repo_health_preflight(argv):
                    self.assertEqual(Path(str(kwargs.get("cwd"))), vault)
                    self.assertTrue(_is_full_worker_repo_health_preflight(argv))
                    self.assertEqual(kwargs.get("timeout"), 5400)
                    executed_roles.append("post-worker-repo-health")
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
            ):
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

            self.assertEqual(executed_roles, ["worker", "post-worker-repo-health", "validator"])
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
                [event["type"] for event in ledger["events"][-3:]],
                [
                    "executor_completed",
                    "worker_repo_health_preflight_checked",
                    "executor_completed",
                ],
            )
            self.assertEqual(ledger["events"][-2]["decision"], "worker_repo_health_preflight_pass")

    def test_run_executor_pipeline_keeps_sparse_worker_repo_health_preflight_focused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            set_policy_value(
                vault,
                ("auto_improve_policy", "workspace_preparation"),
                {"mode": "sparse_manifest", "declared_dependencies": ["tools/"]},
            )
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
            captured_preflight: list[list[str]] = []

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                write_valid_model_output(output_path, vault, run_id="run-executor", role=role, notes=[f"{role} ok"])
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            def fake_preflight(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if _is_worker_repo_health_preflight(argv):
                    self.assertEqual(Path(str(kwargs.get("cwd"))), vault)
                    self.assertTrue(_is_focused_worker_repo_health_preflight(argv))
                    self.assertEqual(kwargs.get("timeout"), 5400)
                    captured_preflight.append(argv)
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
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

            self.assertEqual(len(captured_preflight), 1)
            self.assertEqual(captured_preflight[0][-1], "tests/test_example.py")

    def test_run_executor_pipeline_refreshes_script_output_surfaces_after_ops_script_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            (vault / "ops" / "scripts" / "core").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts" / "core" / "script_output_surfaces.py").write_text(
                "# script-output-surfaces marker\n",
                encoding="utf-8",
            )
            (vault / "ops" / "schemas" / "script-output-surfaces.schema.json").write_text(
                (REPO_ROOT / "ops" / "schemas" / "script-output-surfaces.schema.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            scope_path = vault / "runs" / "run-executor" / "scope-freeze.json"
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["inputs"]["supporting_targets"] = ["ops/script-output-surfaces.json"]
            scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
            (vault / "ops" / "script-output-surfaces.json").write_text("stale\n", encoding="utf-8")
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
                write_valid_model_output(
                    output_path,
                    vault,
                    run_id="run-executor",
                    role=role,
                    notes=[f"{role} ok"],
                )
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            def fake_preflight(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if _is_worker_repo_health_preflight(argv):
                    events.append("post-worker-repo-health")
                    self.assertEqual(Path(str(kwargs.get("cwd"))), vault)
                    return subprocess.CompletedProcess(argv, 0, stdout="repo health ok\n", stderr="")
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
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

            self.assertEqual(events, ["worker", "post-worker-repo-health", "validator"])
            refreshed = json.loads(
                (vault / "ops" / "script-output-surfaces.json").read_text(encoding="utf-8")
            )
            self.assertEqual(refreshed["artifact_kind"], "script_output_surfaces")

    def test_run_executor_pipeline_blocks_script_output_refresh_when_generator_changed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            generator_path = vault / "ops" / "scripts" / "core" / "script_output_surfaces.py"
            generator_path.parent.mkdir(parents=True, exist_ok=True)
            generator_path.write_text("# old generator\n", encoding="utf-8")
            scope_path = vault / "runs" / "run-executor" / "scope-freeze.json"
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["inputs"]["primary_targets"] = ["ops/scripts/core/script_output_surfaces.py"]
            scope["inputs"]["supporting_targets"] = ["ops/script-output-surfaces.json"]
            scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
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
                    generator_path.write_text("# new generator\n", encoding="utf-8")
                write_valid_model_output(output_path, vault, run_id="run-executor", role=role, notes=[f"{role} ok"])
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "refusing to refresh ops/script-output-surfaces.json",
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

    def test_run_executor_pipeline_blocks_script_output_refresh_when_generator_changed_as_extra_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
            seed_subagent_profiles(vault, ["worker", "validator"])
            generator_path = vault / "ops" / "scripts" / "core" / "script_output_surfaces.py"
            generator_path.parent.mkdir(parents=True, exist_ok=True)
            generator_path.write_text("# old generator\n", encoding="utf-8")
            scope_path = vault / "runs" / "run-executor" / "scope-freeze.json"
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["inputs"]["primary_targets"] = ["ops/scripts/example.py"]
            scope["inputs"]["supporting_targets"] = ["ops/script-output-surfaces.json"]
            scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
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
                        "def subject():\n    return 3\n",
                        encoding="utf-8",
                    )
                    generator_path.write_text("# extra generator change\n", encoding="utf-8")
                write_valid_model_output(output_path, vault, run_id="run-executor", role=role, notes=[f"{role} ok"])
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "refusing to refresh ops/script-output-surfaces.json",
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

    def test_run_executor_pipeline_blocks_non_worker_roles_when_post_worker_repo_health_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_executor_vault(vault)
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
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
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

            def fake_preflight(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if _is_worker_repo_health_preflight(argv):
                    events.append("post-worker-repo-health")
                    self.assertEqual(Path(str(kwargs.get("cwd"))), vault)
                    return _executor_subprocess_completed(
                        argv,
                        preflight_returncode=1,
                        preflight_stdout="",
                        preflight_stderr="ruff check failed\n",
                    )
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
                self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "worker repo-health preflight failed.*ruff check failed",
                ),
            ):
                run_executor_pipeline(
                    vault,
                    workspace_root=vault,
                    run_id="run-executor",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    scope_freeze_rel="runs/run-executor/scope-freeze.json",
                    proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                    roles=["worker", "validator", "provenance-auditor"],
                    routing_reports=[worker_routing, validator_routing, auditor_routing],
                )

            self.assertEqual(events, ["worker", "post-worker-repo-health"])
            run_dir = vault / "runs" / "run-executor"
            self.assertTrue((run_dir / "worker-executor-report.json").exists())
            self.assertFalse((run_dir / "validator-executor-report.json").exists())
            self.assertFalse((run_dir / "provenance-auditor-executor-report.json").exists())
            self.assertEqual(
                (run_dir / "worker-repo-health-preflight.stderr.txt").read_text(encoding="utf-8"),
                "ruff check failed\n",
            )
            ledger = json.loads((run_dir / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["status"], "blocked")
            self.assertEqual(ledger["events"][-1]["type"], "worker_repo_health_preflight_checked")
            self.assertEqual(ledger["events"][-1]["decision"], "worker_repo_health_preflight_fail")

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
            executed_roles: list[str] = []

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                executed_roles.append(role)
                write_valid_model_output(output_path, vault, run_id="run-executor", role=role, notes=[f"{role} ok"])
                return mock.Mock(returncode=0, stdout=f"{role} ok\n", stderr="")

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                self.assertRaisesRegex(
                    ExecutorRuntimeExecutionError,
                    "without modifying any declared primary target",
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
                model="gpt-5.6-sol",
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
                write_valid_model_output(Path(argv[out_index]), vault, run_id="run-executor", role="worker", notes=["cli ok"])
                return mock.Mock(returncode=0, stdout="cli ok\n", stderr="")

            def fake_preflight(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
            ):
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

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                write_valid_model_output(
                    output_path,
                    vault,
                    run_id="run-executor",
                    role=role,
                    notes=["validator blocked"] if role == "validator" else [f"{role} ok"],
                    status="fail" if role == "validator" else "pass",
                )
                return mock.Mock(returncode=0, stdout=f"{role}\n", stderr="")

            def fake_preflight(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
            ):
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

            def fake_run(argv: list[str], **_: object) -> object:
                out_index = argv.index("-o") + 1
                output_path = Path(argv[out_index])
                role = output_path.name.replace("-last-message.json", "")
                returncode = 0
                if role == "worker":
                    (vault / "ops" / "scripts" / "example.py").write_text(
                        "def subject():\n    return 2\n",
                        encoding="utf-8",
                    )
                write_valid_model_output(
                    output_path,
                    vault,
                    run_id="run-executor",
                    role=role,
                    notes=["validator blocked"] if role == "validator" else [f"{role} ok"],
                    status="fail" if role == "validator" else "pass",
                )
                return mock.Mock(returncode=returncode, stdout=f"{role}\n", stderr="")

            def fake_preflight(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                return _executor_subprocess_completed(argv)

            with (
                mock.patch("ops.scripts.core.codex_exec_execution_outcome_runtime.run_with_timeout", side_effect=fake_run),
                mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run", side_effect=fake_preflight),
                self.assertRaises(ExecutorRuntimeExecutionError),
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

            validator_report = json.loads(
                (vault / "runs" / "run-executor" / "validator-executor-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(validator_report["status"], "fail")
            self.assertEqual(validator_report["diagnostics"]["notes"], ["validator blocked"])
            ledger = json.loads((vault / "runs" / "run-executor" / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["status"], "blocked")
            self.assertEqual(ledger["events"][-1]["type"], "validation_blocked")
