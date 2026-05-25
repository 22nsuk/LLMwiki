from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.improvement_observations_runtime import (
    backfill_improvement_observations,
    build_run_improvement_observations,
    task_improvement_observations_rel,
    write_task_improvement_observations,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.report_contract


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 27, 12, 0, tzinfo=dt.UTC),
    )


class ImprovementObservationsRuntimeTests(unittest.TestCase):
    def test_build_run_improvement_observations_validates_against_schema(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        schema = load_schema(repo_root / "ops" / "schemas" / "improvement-observations.schema.json")
        payload = build_run_improvement_observations(
            "run-improvement-observations",
            context=fixed_context(),
        )
        self.assertEqual(validate_with_schema(payload, schema), [])
        self.assertEqual(payload["artifact_kind"], "run_improvement_observations")
        self.assertEqual(payload["generated_at"], "2026-04-27T12:00:00Z")
        self.assertEqual(payload["currentness"], {"status": "current", "checked_at": "2026-04-27T12:00:00Z"})
        self.assertEqual(payload["record_id"], "run-improvement-observations")
        self.assertEqual(payload["run_id"], "run-improvement-observations")
        self.assertEqual(payload["scope"], "system_mechanism_run")

    def test_write_task_improvement_observations_uses_default_task_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            rel_path = write_task_improvement_observations(
                vault,
                task_id="task-runtime-refactor",
                context=fixed_context(),
            )

            self.assertEqual(
                rel_path,
                task_improvement_observations_rel("task-runtime-refactor"),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")
            self.assertEqual(validate_with_schema(payload, schema), [])
            self.assertEqual(payload["artifact_kind"], "task_improvement_observations")
            self.assertEqual(payload["generated_at"], "2026-04-27T12:00:00Z")
            self.assertEqual(payload["record_id"], "task-runtime-refactor")
            self.assertEqual(payload["task_id"], "task-runtime-refactor")
            self.assertEqual(payload["scope"], "repo_maintenance_task")

    def test_backfill_improvement_observations_preserves_observations_and_captured_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            rel_path = task_improvement_observations_rel("task-legacy")
            legacy_path = vault / rel_path
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/improvement-observations.schema.json",
                        "record_id": "task-legacy",
                        "task_id": "task-legacy",
                        "captured_at": "2026-04-20T00:00:00Z",
                        "scope": "repo_maintenance_task",
                        "summary": "legacy task observation",
                        "observations": [
                            {
                                "observation_id": "legacy_followup",
                                "surface": "ops/scripts/example.py",
                                "problem": "manual follow-up is easy to lose",
                                "why_it_matters": "automation backlog should be durable",
                                "automation_candidate": "add a report writer",
                                "suggested_followup": "backfill the artifact envelope",
                                "status": "planned",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            written = backfill_improvement_observations(
                vault,
                [rel_path],
                context=fixed_context(),
            )
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")

            self.assertEqual(written, [rel_path])
            self.assertEqual(validate_with_schema(payload, schema), [])
            self.assertEqual(payload["captured_at"], "2026-04-20T00:00:00Z")
            self.assertEqual(payload["generated_at"], "2026-04-27T12:00:00Z")
            self.assertEqual(payload["observations"][0]["observation_id"], "legacy_followup")


if __name__ == "__main__":
    unittest.main()
