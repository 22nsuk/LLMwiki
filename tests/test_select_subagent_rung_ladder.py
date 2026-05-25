from __future__ import annotations

import unittest

import pytest
from ops.scripts.policy_runtime import load_policy

from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


class SelectSubagentRungLadderTests(unittest.TestCase):
    def test_policy_ladder_matches_project_subagent_profile_defaults(self) -> None:
        policy, _ = load_policy(REPO_ROOT, None)
        ladder = policy["subagent_routing_policy"]["ladder"]

        self.assertEqual([entry["rung"] for entry in ladder], [1, 2, 3])
        self.assertEqual({entry["model"] for entry in ladder}, {"gpt-5.5"})
        self.assertEqual(
            [entry["reasoning_effort"] for entry in ladder],
            ["medium", "high", "xhigh"],
        )


if __name__ == "__main__":
    unittest.main()
