from __future__ import annotations

import unittest

import pytest

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.subagent_routing_runtime import build_routing_decision
from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]


class SelectSubagentRungLadderTests(unittest.TestCase):
    def test_policy_ladder_matches_project_approved_subagent_rungs(self) -> None:
        policy, _ = load_policy(REPO_ROOT, None)
        ladder = policy["subagent_routing_policy"]["ladder"]

        self.assertEqual(
            [(entry["rung"], entry["model"], entry["reasoning_effort"]) for entry in ladder],
            [
                (1, "gpt-6.1-sol", "high"),
                (2, "gpt-6.1-sol", "xhigh"),
                (3, "gpt-6.1-sol", "max"),
                (4, "gpt-6-astra", "high"),
            ],
        )

    def test_worker_score_boundaries_select_all_four_model_effort_pairs(self) -> None:
        policy, _ = load_policy(REPO_ROOT, None)
        dimensions = dict.fromkeys(policy["complexity_policy"]["dimensions"], 0)
        for score, rung, model, effort in (
            (24, 1, "gpt-6.1-sol", "high"),
            (25, 2, "gpt-6.1-sol", "xhigh"),
            (44, 2, "gpt-6.1-sol", "xhigh"),
            (45, 3, "gpt-6.1-sol", "max"),
            (64, 3, "gpt-6.1-sol", "max"),
            (65, 4, "gpt-6-astra", "high"),
            (100, 4, "gpt-6-astra", "high"),
        ):
            with self.subTest(score=score):
                decision = build_routing_decision(policy, "worker", dimensions, score)
                self.assertEqual(
                    (decision["selected_rung"], decision["model"], decision["reasoning_effort"]),
                    (rung, model, effort),
                )

    def test_extreme_or_manual_escalation_preserves_discovery_caps_and_auditor_floors(self) -> None:
        policy, _ = load_policy(REPO_ROOT, None)
        dimensions = dict.fromkeys(policy["complexity_policy"]["dimensions"], 0)
        for role, role_policy in policy["subagent_routing_policy"]["roles"].items():
            discovery = role in {"explorer", "owner-boundary-mapper"}
            for score, requested_rung in ((65, None), (0, 4)):
                with self.subTest(role=role, score=score, requested_rung=requested_rung):
                    decision = build_routing_decision(policy, role, dimensions, score, requested_rung)
                    self.assertEqual(
                        (decision["selected_rung"], decision["model"], decision["reasoning_effort"]),
                        (2, "gpt-6.1-sol", "xhigh") if discovery else (4, "gpt-6-astra", "high"),
                    )
                    self.assertEqual(decision["sandbox_mode"], role_policy["sandbox_mode"])
            with self.subTest(role=role, requested_rung=1):
                decision = build_routing_decision(policy, role, dimensions, 0, requested_rung=1)
                self.assertEqual(
                    decision["selected_rung"],
                    1 if role in {"explorer", "owner-boundary-mapper", "worker"} else role_policy["default_rung"],
                )


if __name__ == "__main__":
    unittest.main()
