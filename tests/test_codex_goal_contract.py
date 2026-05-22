from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
from typing import Any

import pytest

from ops.scripts.schema_runtime import load_schema, validate_with_schema

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "codex-goal-contract.schema.json"


def sample_goal_contract() -> dict[str, Any]:
    return {
        "$schema": "ops/schemas/codex-goal-contract.schema.json",
        "schema_version": 1,
        "contract_id": "goal-20260517-auto-improve-runtime",
        "objective": "Run bounded auto-improve only after the loop certificate is durable.",
        "non_goals": [
            "Do not claim sustained runtime before certificate verification.",
            "Do not promote while blockers remain.",
        ],
        "allowed_roots": [
            {"path": "ops/", "purpose": "runtime contracts"},
            {"path": "tests/", "purpose": "regression coverage"},
        ],
        "budgets": {
            "max_wall_clock_seconds": 3600,
            "max_proposals": 1,
            "max_consecutive_failures": 1,
            "heartbeat_interval_seconds": 300,
            "checkpoint_interval_seconds": 1800,
        },
        "created_at": "2026-05-17T00:00:00Z",
        "created_by": "codex",
        "status": "active",
        "runtime": {
            "mode": "self_improvement_loop",
            "duration_seconds": 3600,
            "max_unattended_seconds": 3600,
            "certificate_status": "unverified",
            "verified_at": "",
        },
        "goal_backend": {
            "backend_type": "file",
            "process_persistent": True,
            "storage_path": "ops/reports/codex-goal-contract.json",
        },
        "stop_conditions": [
            {
                "condition_id": "runtime_certificate_failed",
                "description": "Stop if the loop certificate cannot be verified.",
                "severity": "stop",
            }
        ],
        "required_evidence": [
            {
                "evidence_id": "auto_improve_readiness",
                "path": "ops/reports/auto-improve-readiness.json",
                "description": "Readiness report separates execution from promotion.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "goal_run_status",
                "path": "ops/reports/goal-run-status.json",
                "description": "Goal status records loop observability.",
                "freshness": "current_run",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "session_synopsis",
                "path": "ops/reports/session-synopsis.json",
                "description": "Session synopsis records loop state.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "remediation_backlog",
                "path": "ops/reports/remediation-backlog.json",
                "description": "Remediation backlog agrees with loop state.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "source_package_clean_extract",
                "path": "ops/reports/source-package-clean-extract.json",
                "description": "Source package replay is clean.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "public_check_summary",
                "path": "ops/reports/public-check-summary.json",
                "description": "Public check is clean.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "release_authority",
                "path": "ops/reports/release-closeout-summary.json",
                "description": "Release authority blocks promotion until machine release is allowed.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "goal_worktree_guard",
                "path": "ops/reports/goal-worktree-guard.json",
                "description": "Git/ZIP preflight blocks promotion from dirty, non-Git, or replay-only trees.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            }
        ],
        "promotion_guard": {
            "can_promote_result": False,
            "promotion_blockers": ["self-improvement loop certificate incomplete"],
            "sealed_authority_clean": False,
            "runtime_certificate_verified": False,
            "sustained_runtime_claimed": False,
            "no_sustained_claim_before_certificate_verified": True,
        },
        "metadata": {},
    }


class CodexGoalContractSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_schema(SCHEMA_PATH)

    def test_sample_goal_contract_validates(self) -> None:
        self.assertEqual(validate_with_schema(sample_goal_contract(), self.schema), [])

    def test_schema_requires_durable_goal_runtime_fields(self) -> None:
        required_fields = [
            "objective",
            "non_goals",
            "allowed_roots",
            "budgets",
            "runtime",
            "goal_backend",
            "stop_conditions",
            "required_evidence",
            "promotion_guard",
        ]

        for field_name in required_fields:
            payload = sample_goal_contract()
            payload.pop(field_name)
            with self.subTest(field_name=field_name):
                errors = validate_with_schema(payload, self.schema)
                self.assertTrue(
                    any(f"missing required property '{field_name}'" in error for error in errors),
                    errors,
                )

    def test_goal_backend_must_be_process_persistent(self) -> None:
        payload = sample_goal_contract()
        payload["goal_backend"]["process_persistent"] = False

        errors = validate_with_schema(payload, self.schema)

        self.assertTrue(
            any("expected constant True" in error for error in errors),
            errors,
        )

    def test_promotion_requires_no_blockers_and_clean_sealed_authority(self) -> None:
        payload = sample_goal_contract()
        payload["promotion_guard"]["can_promote_result"] = True

        errors = validate_with_schema(payload, self.schema)

        self.assertTrue(any("promotion_blockers" in error for error in errors), errors)
        self.assertTrue(any("sealed_authority_clean" in error for error in errors), errors)

    def test_sustained_runtime_claim_requires_runtime_certificate(self) -> None:
        payload = sample_goal_contract()
        payload["promotion_guard"].update(
            {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
                "runtime_certificate_verified": False,
                "sustained_runtime_claimed": True,
            }
        )

        errors = validate_with_schema(payload, self.schema)

        self.assertTrue(any("runtime_certificate_verified" in error for error in errors), errors)

    def test_sustained_runtime_claim_allows_verified_runtime_certificate(self) -> None:
        payload = deepcopy(sample_goal_contract())
        payload["promotion_guard"].update(
            {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
                "runtime_certificate_verified": True,
                "sustained_runtime_claimed": True,
            }
        )

        self.assertEqual(validate_with_schema(payload, self.schema), [])


if __name__ == "__main__":
    unittest.main()
