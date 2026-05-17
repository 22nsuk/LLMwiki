from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.codex_goal_client import set_goal
from ops.scripts.codex_goal_prompt import build_prompt_text, build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_codex_goal_contract import sample_goal_contract


pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "codex-goal-prompt.schema.json"


class CodexGoalPromptTests(unittest.TestCase):
    def test_prompt_snapshot_includes_promotion_ban_when_promotion_is_blocked(self) -> None:
        prompt = build_prompt_text(sample_goal_contract())

        self.assertEqual(
            prompt,
            """You are Codex continuing a bounded auto-improve goal for this repository.

Goal contract:
- contract_id: goal-20260517-auto-improve-runtime
- status: active
- profile: 30m_trial
- backend_storage: ops/reports/codex-goal-contract.json

Objective:
Run bounded auto-improve only after profile evidence is durable.

Budget limits:
- max_wall_clock_seconds: 1800
- max_unattended_seconds: 1800
- max_proposals: 1
- max_consecutive_failures: 1
- heartbeat_interval_seconds: 300
- checkpoint_interval_seconds: 1800

Allowed roots:
- ops/
- tests/

Required evidence:
- ops/reports/auto-improve-readiness.json

Promotion guard:
- can_promote_result: false
- sealed_authority_clean: false
- profile_verified: unverified

PROMOTION BAN: can_promote_result=false.
Do not promote release, learning, or improvement claims.
Do not claim 5-day sustained operation.
Do not call update_goal complete until blockers are cleared by evidence.

Promotion blockers:
- profile ladder incomplete

SUSTAINED CLAIM BAN: profile_verified is not 5d_sustained.
Do not claim 5-day sustained operation until the full profile ladder is verified.

Resume discipline:
- Keep the same contract digest across resume.
- Stop with budget_limited when wall-clock, proposal, or failure budget is reached.
- Write heartbeat, checkpoint, and status evidence before widening the run profile.
""",
        )

    def test_prompt_report_validates_and_records_ban_flags(self) -> None:
        schema = load_schema(SCHEMA_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            set_goal(sample_goal_contract(), vault=vault)

            report = build_report(
                vault,
                context=RuntimeContext(
                    display_timezone=dt.timezone.utc,
                    clock=lambda: dt.datetime(2026, 5, 17, tzinfo=dt.timezone.utc),
                ),
            )
            destination = write_report(vault, report)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(destination.relative_to(vault).as_posix(), "ops/reports/codex-goal-prompt.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "attention")
            self.assertTrue(persisted["promotion_guard"]["promotion_ban_required"])
            self.assertTrue(persisted["prompt"]["includes_promotion_ban"])
            self.assertTrue(persisted["prompt"]["includes_sustained_claim_ban"])
            self.assertIn("PROMOTION BAN: can_promote_result=false.", persisted["prompt"]["text"])


if __name__ == "__main__":
    unittest.main()
