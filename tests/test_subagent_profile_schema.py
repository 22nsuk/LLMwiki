from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import pytest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.subagent_profile_schema import build_report

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class SubagentProfileSchemaTests(unittest.TestCase):
    def test_profiles_match_policy_roles_and_schema(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["missing_profile_count"], 0)
        self.assertEqual(report["summary"]["extra_profile_count"], 0)
        self.assertEqual(report["summary"]["incomplete_profile_count"], 0)
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/subagent-profile.schema.json")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
