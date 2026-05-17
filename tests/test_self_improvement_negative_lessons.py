from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.self_improvement_negative_lessons import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault


pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "self-improvement-negative-lessons.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 17, 13, 0, tzinfo=dt.timezone.utc),
    )


def write_json(vault: Path, rel_path: str, payload: dict) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def seed_negative_lesson_inputs(vault: Path) -> None:
    write_json(
        vault,
        "ops/reports/learning_claim_activation_report.json",
        {
            "status": "pass",
            "negative_learning_ledger": {
                "patterns": [
                    {
                        "pattern_id": "blocked_queue_recent_log_overlap",
                        "decisions": ["BLOCKED"],
                        "run_ids": [],
                        "occurrence_count": 2,
                        "forbidden_repeat": "Do not repeat this run shape.",
                        "repair_target": "Resolve queue blocked reason recent_log_overlap.",
                        "evidence_digests": [
                            {
                                "path": "ops/reports/auto-improve-readiness.json",
                                "exists": True,
                                "sha256": "a" * 64,
                                "status": "present",
                            }
                        ],
                    }
                ]
            },
        },
    )
    write_json(
        vault,
        "ops/reports/session-synopsis.json",
        {
            "forbidden_repeat_patterns": [
                {
                    "id": "blocked_queue_recent_log_overlap",
                    "decisions": ["BLOCKED"],
                    "run_ids": [],
                    "occurrence_count": 2,
                    "forbidden_repeat": "Do not repeat this run shape.",
                    "repair_target": "Resolve queue blocked reason recent_log_overlap.",
                }
            ]
        },
    )


class SelfImprovementNegativeLessonsTests(unittest.TestCase):
    def test_report_promotes_embedded_negative_learning_to_standalone_lessons(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_negative_lesson_inputs(vault)

            report = build_report(vault, context=fixed_context())
            lesson = report["lessons"][0]

            self.assertEqual(report["artifact_kind"], "self_improvement_negative_lessons")
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["lesson_count"], 1)
            self.assertEqual(report["summary"]["backlog_candidate_count"], 1)
            self.assertEqual(lesson["lesson_id"], "blocked_queue_recent_log_overlap")
            self.assertEqual(lesson["source"], "learning_claim_activation.negative_learning_ledger+session_synopsis")
            self.assertEqual(lesson["repeat_policy"], "do_not_repeat_until_repaired")
            self.assertTrue(lesson["backlog_candidate"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_report_validates_and_uses_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_negative_lesson_inputs(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)

            self.assertEqual(
                destination,
                vault / "ops" / "reports" / "self-improvement-negative-lessons.json",
            )
            self.assertTrue(destination.exists())

    def test_next_action_distinguishes_advisory_lessons_from_empty_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_json(
                vault,
                "ops/reports/learning_claim_activation_report.json",
                {
                    "status": "pass",
                    "negative_learning_ledger": {
                        "patterns": [
                            {
                                "pattern_id": "discard_specific_single",
                                "decisions": ["DISCARD"],
                                "run_ids": ["run-discard"],
                                "occurrence_count": 1,
                                "forbidden_repeat": "Do not repeat this run shape.",
                                "repair_target": "Change the evidence predicate.",
                                "evidence_digests": [],
                            }
                        ]
                    },
                },
            )
            write_json(vault, "ops/reports/session-synopsis.json", {})

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["summary"]["backlog_candidate_count"], 0)
            self.assertEqual(
                report["summary"]["next_action"],
                "Negative lessons are advisory only; no repeated backlog candidates detected.",
            )


if __name__ == "__main__":
    unittest.main()
