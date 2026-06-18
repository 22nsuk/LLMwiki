from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism.auto_improve_route_scaffold_runtime import (
    RouteScaffoldDependencies,
    route_scaffold_phase,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
        session_id="auto-session",
        executor_id="codex_exec",
    )


class AutoImproveRouteScaffoldRuntimeTests(unittest.TestCase):
    def test_route_scaffold_phase_routes_reviewer_validator_and_auditor_then_scaffolds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text("version: 1\n", encoding="utf-8")
            captured_calls: dict[str, object] = {}
            ledger_events: list[dict[str, object]] = []

            def fake_build_scope_freeze(*_: object, **__: object) -> dict[str, object]:
                return {
                    "status": "runnable",
                    "inputs": {
                        "primary_targets": ["ops/scripts/example.py"],
                        "supporting_targets": [],
                    },
                    "resolution": {
                        "test_files": ["tests/test_example.py"],
                        "risk_flags": ["contract_change"],
                    },
                    "dispatch": {
                        "reviewer": False,
                        "validator": True,
                        "auditors": ["provenance-auditor"],
                    },
                }

            def fake_write_scope_freeze(vault_path: Path, scope_freeze: dict, *, run_id: str) -> Path:
                path = vault_path / "runs" / run_id / "scope-freeze.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(scope_freeze, ensure_ascii=False, indent=2), encoding="utf-8")
                return path

            def fake_run_selector(
                *,
                vault: Path,
                role: str,
                out_path: str,
                **_: object,
            ) -> tuple[dict[str, object], Path]:
                path = vault / out_path
                path.parent.mkdir(parents=True, exist_ok=True)
                score_band = "high" if role == "worker" else "low"
                report: dict[str, object] = {
                    "role": role,
                    "routing_decision": {
                        "selected_rung": 3 if role != "worker" else 2,
                        "score_band": score_band,
                        "sandbox_mode": "read-only" if role != "worker" else "workspace-write",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                    "complexity_profile": {"risk_flags": ["contract_change"]},
                }
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                return report, path

            def fake_run_mechanism_experiment(vault_path: Path, **kwargs: object) -> dict[str, object]:
                captured_calls["vault"] = vault_path
                captured_calls["kwargs"] = kwargs
                return {"run_id": kwargs["run_id"], "scaffold_only": True}

            def fake_append_ledger_event(_vault: Path, run_id: str, **kwargs: object) -> None:
                ledger_events.append({"run_id": run_id, **kwargs})

            def fake_role_report_path(run_id: str, role: str) -> str:
                return f"runs/{run_id}/{role}-executor-report.json"

            policy = {
                "version": 1,
                "auto_improve_policy": {
                    "scope_resolution": {
                        "reviewer_score_bands": ["high"],
                    }
                },
            }
            proposal = {
                "proposal_id": "proposal-example",
                "primary_targets": ["ops/scripts/example.py"],
                "supporting_targets": [],
            }

            result = route_scaffold_phase(
                vault,
                policy,
                policy_path,
                run_id="run-route",
                proposal=proposal,
                proposal_report_path="ops/reports/mutation-proposals.json",
                context=fixed_context(),
                dependencies=RouteScaffoldDependencies(
                    build_scope_freeze=fake_build_scope_freeze,
                    write_scope_freeze=fake_write_scope_freeze,
                    run_selector=fake_run_selector,
                    run_mechanism_experiment=fake_run_mechanism_experiment,
                    append_ledger_event=fake_append_ledger_event,
                    role_report_path=fake_role_report_path,
                ),
            )

            self.assertEqual(
                result.roles,
                ["worker", "reviewer", "validator", "provenance-auditor"],
            )
            self.assertEqual(
                result.routing_report_rels,
                [
                    "runs/run-route/subagent-routing.worker.json",
                    "runs/run-route/subagent-routing.reviewer.json",
                    "runs/run-route/subagent-routing.validator.json",
                    "runs/run-route/subagent-routing.provenance-auditor.json",
                ],
            )
            kwargs = dict(cast(dict[str, object], captured_calls["kwargs"]))
            self.assertTrue(kwargs["scaffold_only"])
            self.assertEqual(
                kwargs["executor_report_paths"],
                [
                    "runs/run-route/worker-executor-report.json",
                    "runs/run-route/reviewer-executor-report.json",
                    "runs/run-route/validator-executor-report.json",
                    "runs/run-route/provenance-auditor-executor-report.json",
                ],
            )
            self.assertEqual(
                [event["event_type"] for event in ledger_events],
                ["scope_frozen", "subagent_routed"],
            )
            self.assertEqual(ledger_events[0]["decision"], "runnable")
            self.assertEqual(ledger_events[1]["artifacts"], result.routing_report_rels)
            self.assertEqual(set(result.phase_durations), {"scope_freeze", "routing", "scaffold"})

    def test_route_scaffold_phase_keeps_blocked_scope_on_worker_only_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text("version: 1\n", encoding="utf-8")
            captured_calls: list[dict[str, object]] = []

            def fake_build_scope_freeze(*_: object, **__: object) -> dict[str, object]:
                return {
                    "status": "blocked",
                    "inputs": {
                        "primary_targets": ["ops/scripts/example.py"],
                        "supporting_targets": [],
                    },
                    "resolution": {
                        "test_files": [],
                        "risk_flags": [],
                    },
                    "dispatch": {
                        "reviewer": False,
                        "validator": False,
                        "auditors": [],
                    },
                }

            def fake_write_scope_freeze(vault_path: Path, scope_freeze: dict, *, run_id: str) -> Path:
                path = vault_path / "runs" / run_id / "scope-freeze.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(scope_freeze, ensure_ascii=False, indent=2), encoding="utf-8")
                return path

            def fake_run_selector(
                *,
                vault: Path,
                role: str,
                out_path: str,
                **_: object,
            ) -> tuple[dict[str, object], Path]:
                path = vault / out_path
                path.parent.mkdir(parents=True, exist_ok=True)
                report: dict[str, object] = {
                    "role": role,
                    "routing_decision": {
                        "selected_rung": 2,
                        "score_band": "low",
                        "sandbox_mode": "workspace-write",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                    "complexity_profile": {"risk_flags": []},
                }
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                return report, path

            def fake_run_mechanism_experiment(_vault_path: Path, **kwargs: object) -> dict[str, object]:
                captured_calls.append(dict(kwargs))
                return {"run_id": kwargs["run_id"], "scaffold_only": True}

            def fake_append_ledger_event(*_: object, **__: object) -> None:
                return None

            result = route_scaffold_phase(
                vault,
                {
                    "version": 1,
                    "auto_improve_policy": {"scope_resolution": {"reviewer_score_bands": []}},
                },
                policy_path,
                run_id="run-route-blocked",
                proposal={
                    "proposal_id": "proposal-blocked",
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                },
                proposal_report_path="ops/reports/mutation-proposals.json",
                context=fixed_context(),
                dependencies=RouteScaffoldDependencies(
                    build_scope_freeze=fake_build_scope_freeze,
                    write_scope_freeze=fake_write_scope_freeze,
                    run_selector=fake_run_selector,
                    run_mechanism_experiment=fake_run_mechanism_experiment,
                    append_ledger_event=fake_append_ledger_event,
                    role_report_path=lambda run_id, role: f"runs/{run_id}/{role}-executor-report.json",
                ),
            )

            self.assertEqual(result.scope_freeze["status"], "blocked")
            self.assertEqual(result.roles, ["worker"])
            self.assertEqual(len(captured_calls), 1)
            self.assertEqual(captured_calls[0]["test_files"], [])
            self.assertTrue(captured_calls[0]["scaffold_only"])
