from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.observation_closeout_lint import build_report

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class ObservationCloseoutLintTests(unittest.TestCase):
    def test_open_observations_must_be_registered_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            obs_path = (
                vault
                / "ops"
                / "reports"
                / "task-improvement-observations"
                / "task-1"
                / "improvement-observations.json"
            )
            obs_path.parent.mkdir(parents=True)
            rel_obs = obs_path.relative_to(vault).as_posix()
            obs_path.write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "observation_id": "keep_tracking",
                                "status": "planned",
                                "surface": "ops/scripts/example.py",
                                "suggested_followup": "keep tracking",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry = {
                "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                "artifact_kind": "observation_closeout_registry",
                "retained_observations": [
                    {
                        "path": rel_obs,
                        "observation_id": "keep_tracking",
                        "status": "planned",
                        "retained_reason": "broad debt remains open",
                        "next_action": "close in a later focused task",
                        "exit_condition": "close when focused task resolves the follow-up",
                        "owner_or_lane": "focused-task",
                    }
                ],
            }
            registry_path.write_text(json.dumps(registry) + "\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(validate_with_schema(registry, schema), [])
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["open_observation_count"], 1)
        self.assertEqual(report["summary"]["unregistered_open_count"], 0)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_unregistered_open_observation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            obs_path = (
                vault
                / "ops"
                / "reports"
                / "task-improvement-observations"
                / "task-1"
                / "improvement-observations.json"
            )
            obs_path.parent.mkdir(parents=True)
            obs_path.write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "observation_id": "missing",
                                "status": "open",
                                "surface": "ops/scripts/example.py",
                                "suggested_followup": "register me",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                        "artifact_kind": "observation_closeout_registry",
                        "retained_observations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["unregistered_open_count"], 1)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_stale_registry_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "runs").mkdir(parents=True)
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                        "artifact_kind": "observation_closeout_registry",
                        "retained_observations": [
                            {
                                "path": "runs/run-1/improvement-observations.json",
                                "observation_id": "missing",
                                "status": "planned",
                                "retained_reason": "kept for follow-up",
                                "next_action": "recheck",
                                "exit_condition": "close when no longer open",
                                "owner_or_lane": "release",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["stale_registry_entry_count"], 1)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_registry_entries_are_unavailable_not_stale_when_observation_roots_absent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry = {
                "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                "artifact_kind": "observation_closeout_registry",
                "retained_observations": [
                    {
                        "path": "ops/reports/task-improvement-observations/task-1/improvement-observations.json",
                        "observation_id": "local_only_followup",
                        "status": "planned",
                        "retained_reason": "local-only generated observation retained in full vault",
                        "next_action": "recheck in full vault",
                        "exit_condition": "close when source observation is present and resolved",
                        "owner_or_lane": "observation-closeout",
                    }
                ],
            }
            registry_path.write_text(json.dumps(registry) + "\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["stale_registry_entry_count"], 0)
        self.assertEqual(report["summary"]["unavailable_registry_entry_count"], 1)
        self.assertEqual(
            report["unavailable_registry_entries"][0]["reason"],
            "observation_root_absent",
        )
        self.assertEqual(validate_with_schema(registry, schema), [])
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_duplicate_registry_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            obs_path = vault / "runs" / "run-1" / "improvement-observations.json"
            obs_path.parent.mkdir(parents=True)
            rel_obs = obs_path.relative_to(vault).as_posix()
            obs_path.write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "observation_id": "dup",
                                "status": "planned",
                                "surface": "ops/scripts/example.py",
                                "suggested_followup": "dedupe registry",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            entry = {
                "path": rel_obs,
                "observation_id": "dup",
                "status": "planned",
                "retained_reason": "kept for follow-up",
                "next_action": "dedupe",
                "exit_condition": "close when deduped",
                "owner_or_lane": "release",
            }
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                        "artifact_kind": "observation_closeout_registry",
                        "retained_observations": [entry, dict(entry)],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["duplicate_registry_key_count"], 1)
        self.assertEqual(report["duplicate_registry_entries"][0]["count"], 2)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_runs_observation_files_are_covered_by_registry_lint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            obs_path = vault / "runs" / "run-1" / "improvement-observations.json"
            obs_path.parent.mkdir(parents=True)
            rel_obs = obs_path.relative_to(vault).as_posix()
            obs_path.write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "observation_id": "run_followup",
                                "status": "planned",
                                "surface": "ops/scripts/example.py",
                                "suggested_followup": "close run follow-up",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                        "artifact_kind": "observation_closeout_registry",
                        "retained_observations": [
                            {
                                "path": rel_obs,
                                "observation_id": "run_followup",
                                "status": "planned",
                                "retained_reason": "kept for follow-up",
                                "next_action": "close run follow-up",
                                "exit_condition": "close when run follow-up is resolved",
                                "owner_or_lane": "run-closeout",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["open_observations"][0]["path"], rel_obs)
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_wontfix_observations_require_resolution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            obs_path = (
                vault
                / "ops"
                / "reports"
                / "task-improvement-observations"
                / "task-1"
                / "improvement-observations.json"
            )
            obs_path.parent.mkdir(parents=True)
            obs_path.write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "observation_id": "hidden_backlog",
                                "status": "wontfix",
                                "surface": "ops/scripts/example.py",
                                "suggested_followup": "do not hide this",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = vault / "ops" / "observation-closeout-registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/observation-closeout-registry.schema.json",
                        "artifact_kind": "observation_closeout_registry",
                        "retained_observations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

        schema = load_schema("ops/schemas/observation-closeout-registry.schema.json")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["terminal_status_issue_count"], 1)
        self.assertEqual(
            report["terminal_status_issues"][0]["reason"],
            "terminal_status_missing_resolution_evidence",
        )
        self.assertEqual(validate_with_schema(report, schema), [])


if __name__ == "__main__":
    unittest.main()
