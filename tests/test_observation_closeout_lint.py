from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.observation_closeout_lint import build_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


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


if __name__ == "__main__":
    unittest.main()
