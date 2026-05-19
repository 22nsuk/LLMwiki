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
        "objective": "Run bounded auto-improve only after profile evidence is durable.",
        "non_goals": [
            "Do not claim sustained runtime before profile verification.",
            "Do not promote while blockers remain.",
        ],
        "allowed_roots": [
            {"path": "ops/", "purpose": "runtime contracts"},
            {"path": "tests/", "purpose": "regression coverage"},
        ],
        "budgets": {
            "max_wall_clock_seconds": 1800,
            "max_proposals": 1,
            "max_consecutive_failures": 1,
            "heartbeat_interval_seconds": 300,
            "checkpoint_interval_seconds": 1800,
            "profile_ladder": [
                {
                    "profile": "30m_trial",
                    "max_wall_clock_seconds": 1800,
                    "max_proposals": 1,
                    "max_consecutive_failures": 1,
                    "required_before_next_profile": (
                        "one-proposal trial evidence includes runtime maintenance "
                        "and stays promotion-blocked"
                    ),
                }
            ],
        },
        "created_at": "2026-05-17T00:00:00Z",
        "created_by": "codex",
        "status": "active",
        "runtime_profile": {
            "current_profile": "30m_trial",
            "verified_profiles": [],
            "next_profile": "30m_trial",
            "max_unattended_seconds": 1800,
        },
        "goal_backend": {
            "backend_type": "file",
            "process_persistent": True,
            "storage_path": "ops/reports/codex-goal-contract.json",
        },
        "stop_conditions": [
            {
                "condition_id": "profile_gate_failed",
                "description": "Stop if the active profile cannot be verified.",
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
            }
        ],
        "promotion_guard": {
            "can_promote_result": False,
            "promotion_blockers": ["profile ladder incomplete"],
            "sealed_authority_clean": False,
            "profile_verified": "unverified",
            "sustained_runtime_claimed": False,
            "no_sustained_claim_before_profile_verified": True,
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
            "runtime_profile",
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

    def test_sustained_runtime_claim_requires_verified_five_day_profile(self) -> None:
        payload = sample_goal_contract()
        payload["promotion_guard"].update(
            {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
                "profile_verified": "2d_candidate",
                "sustained_runtime_claimed": True,
            }
        )

        errors = validate_with_schema(payload, self.schema)

        self.assertTrue(any("profile_verified" in error for error in errors), errors)

    def test_sustained_runtime_claim_allows_verified_five_day_profile(self) -> None:
        payload = deepcopy(sample_goal_contract())
        payload["promotion_guard"].update(
            {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
                "profile_verified": "5d_sustained",
                "sustained_runtime_claimed": True,
            }
        )

        self.assertEqual(validate_with_schema(payload, self.schema), [])


if __name__ == "__main__":
    unittest.main()
