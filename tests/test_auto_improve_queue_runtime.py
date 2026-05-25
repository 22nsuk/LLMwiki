from __future__ import annotations

import unittest

from ops.scripts.auto_improve_queue_runtime import (
    build_proposal_queue,
    select_next_proposal,
)


class AutoImproveQueueRuntimeTests(unittest.TestCase):
    def test_build_proposal_queue_filters_attempted_quarantined_and_blocked_proposals(self) -> None:
        proposals_report = {
            "proposals": [
                {
                    "proposal_id": "attempted",
                    "priority": 100,
                    "blocked_by": [],
                },
                {
                    "proposal_id": "quarantined",
                    "priority": 90,
                    "blocked_by": [],
                },
                {
                    "proposal_id": "blocked",
                    "priority": 80,
                    "blocked_by": ["scope_blocked"],
                },
                {
                    "proposal_id": "runnable-low",
                    "priority": 10,
                    "blocked_by": [],
                },
                {
                    "proposal_id": "runnable-high-b",
                    "priority": 50,
                    "blocked_by": [],
                },
                {
                    "proposal_id": "runnable-high-a",
                    "priority": 50,
                    "blocked_by": [],
                },
            ]
        }

        queue = build_proposal_queue(
            proposals_report,
            attempted={"attempted"},
            quarantined={"quarantined"},
        )

        self.assertEqual(
            [proposal["proposal_id"] for proposal in queue],
            ["runnable-high-a", "runnable-high-b", "runnable-low"],
        )

    def test_select_next_proposal_returns_next_proposal_and_queue_snapshot(self) -> None:
        proposals_report = {
            "proposals": [
                {
                    "proposal_id": "proposal-b",
                    "priority": 20,
                    "blocked_by": [],
                },
                {
                    "proposal_id": "proposal-a",
                    "priority": 20,
                    "blocked_by": [],
                },
                {
                    "proposal_id": "proposal-c",
                    "priority": 10,
                    "blocked_by": [],
                },
            ]
        }

        proposal, queue_snapshot = select_next_proposal(
            proposals_report,
            attempted=set(),
            quarantined=set(),
        )

        self.assertEqual(proposal["proposal_id"], "proposal-a")
        self.assertEqual(queue_snapshot, ["proposal-a", "proposal-b", "proposal-c"])

    def test_select_next_proposal_returns_empty_snapshot_when_queue_is_exhausted(self) -> None:
        proposals_report = {
            "proposals": [
                {
                    "proposal_id": "already-attempted",
                    "priority": 20,
                    "blocked_by": [],
                }
            ]
        }

        proposal, queue_snapshot = select_next_proposal(
            proposals_report,
            attempted={"already-attempted"},
            quarantined=set(),
        )

        self.assertIsNone(proposal)
        self.assertEqual(queue_snapshot, [])

    def test_blank_blocker_placeholders_do_not_close_the_queue(self) -> None:
        proposals_report = {
            "proposals": [
                {
                    "proposal_id": "placeholder-blockers",
                    "priority": 20,
                    "blocked_by": ["", "  "],
                },
                {
                    "proposal_id": "named-blocker",
                    "priority": 30,
                    "blocked_by": ["recent_log_overlap"],
                },
            ]
        }

        queue = build_proposal_queue(
            proposals_report,
            attempted=set(),
            quarantined=set(),
        )

        self.assertEqual([proposal["proposal_id"] for proposal in queue], ["placeholder-blockers"])
        self.assertEqual(queue[0]["blocked_by"], [])
        self.assertEqual(proposals_report["proposals"][0]["blocked_by"], ["", "  "])


if __name__ == "__main__":
    unittest.main()
