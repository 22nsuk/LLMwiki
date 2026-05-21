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
- runtime_mode: self_improvement_loop
- backend_storage: ops/reports/codex-goal-contract.json

Objective:
Run bounded auto-improve only after the loop certificate is durable.

Budget limits:
- max_wall_clock_seconds: 3600
- max_unattended_seconds: 3600
- max_proposals: 1
- max_consecutive_failures: 1
- heartbeat_interval_seconds: 300
- checkpoint_interval_seconds: 1800

Allowed roots:
- ops/
- tests/

Required evidence:
- ops/reports/auto-improve-readiness.json
- ops/reports/goal-run-status.json
- ops/reports/session-synopsis.json
- ops/reports/remediation-backlog.json
- ops/reports/source-package-clean-extract.json
- ops/reports/public-check-summary.json
- ops/reports/release-closeout-summary.json
- tmp/goal-worktree-guard.json

Promotion guard:
- can_promote_result: false
- sealed_authority_clean: false
- runtime_certificate_verified: false

PROMOTION BAN: can_promote_result=false.
Do not promote release, learning, or improvement claims.
Do not claim sustained unattended operation.
Do not call update_goal complete until blockers are cleared by evidence.

Promotion blockers:
- self-improvement loop certificate incomplete

SUSTAINED CLAIM BAN: runtime_certificate_verified=false.
Do not claim sustained unattended operation until the self-improvement loop certificate is verified.

Promotion gate guidance:
- Work toward promotion by making required evidence current and blocker-free.
- Treat readiness, source-package, public-check, release closeout, goal status, session synopsis, and remediation backlog as independent evidence surfaces.
- Fix underlying code, tests, docs, or report generators that create blockers.
- Do not lower thresholds, remove guard checks, edit output-only reports, or relabel risks merely to make can_promote_result true.
- If blockers remain, record the next repair in remediation/session evidence and keep promotion banned.

Run admission discipline:
- If tracked canonical reports need refresh, run `make goal-runtime-run-admission-converge`, settle those generated changes, then rerun `make goal-runtime-run-admission`.
- Before starting or resuming a goal run, pass `make goal-runtime-run-admission` instead of relying on remembered cleanup steps.
- Treat `tmp/goal-runtime-run-admission.json` as the start gate: dirty/stale worktree, fixed-point drift, or zero runnable proposals means pause and follow `recommended_next_action`.
- A promotion-only attention result may still allow bounded repair work, but it never weakens the final promotion gate.

Resume discipline:
- Keep the same contract digest across resume.
- Treat the wall-clock duration as a maximum budget, not as proof by itself.
- Stop with proposal_budget_exhausted or failure_budget_exhausted when those separate caps are reached.
- Write heartbeat, checkpoint, status, readiness, source-package, public-check, and release evidence before certifying the loop.

Generated artifact convergence:
- After code or report-generator edits, do not use test failure -> patch -> full rerun as the auto-improve loop.
- Prefer `make goal-runtime-closeout` to run the fingerprint-based cheap closeout plan before any full-suite retry.
- Treat that closeout as run-local candidate-converge -> single canonical publish boundary -> post-publish finalization when expensive evidence is already current.
- If the cheap closeout plan reports stale expensive evidence, stop after the run-local candidate step and escalate to the full closeout budget instead of publishing canonical reports.
- Use `make goal-runtime-closeout-full` only when the closeout plan shows stale expensive evidence and the source fingerprint changed.
- Run `make report-schema-samples-check` before generated index/freshness so schema fixture drift is caught before report currentness work.
- First converge `make script-output-surfaces`, `make generated-artifact-index`, and `make artifact-freshness`.
- Run `make release-smoke-full-reuse` when release source-tree evidence may have changed.
- Treat full-suite evidence as max-once per unchanged source fingerprint; reuse it after a pass instead of rerunning for report-only drift.
- Run artifact finalization only after that convergence, through `make report-contract-closeout` or `make test-artifact-finalization`.
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
            self.assertIn("Promotion gate guidance:", persisted["prompt"]["text"])
            self.assertIn("Do not lower thresholds", persisted["prompt"]["text"])
            self.assertIn("Generated artifact convergence:", persisted["prompt"]["text"])
            self.assertIn("make goal-runtime-closeout", persisted["prompt"]["text"])
            self.assertIn("single canonical publish boundary", persisted["prompt"]["text"])
            self.assertIn("make report-schema-samples-check", persisted["prompt"]["text"])
            self.assertIn("make script-output-surfaces", persisted["prompt"]["text"])
            self.assertIn("make test-artifact-finalization", persisted["prompt"]["text"])

    def test_prompt_guides_promotion_work_without_reward_hacking(self) -> None:
        prompt = build_prompt_text(sample_goal_contract())

        self.assertIn("Work toward promotion by making required evidence current", prompt)
        self.assertIn("Fix underlying code, tests, docs, or report generators", prompt)
        self.assertIn("Do not lower thresholds", prompt)
        self.assertIn("keep promotion banned", prompt)

    def test_self_improvement_docs_name_generated_artifact_convergence_order(self) -> None:
        required_phrases = (
            "make script-output-surfaces",
            "make report-schema-samples-check",
            "make generated-artifact-index",
            "make artifact-freshness",
            "make goal-runtime-closeout",
            "make release-smoke-full-reuse",
            "make test-artifact-finalization",
        )
        surfaces = {
            "prompt": build_prompt_text(sample_goal_contract()),
            "README.md": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            "ops/README.md": (REPO_ROOT / "ops" / "README.md").read_text(encoding="utf-8"),
        }
        for name, text in surfaces.items():
            for phrase in required_phrases:
                with self.subTest(surface=name, phrase=phrase):
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
