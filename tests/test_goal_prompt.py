from __future__ import annotations

import pytest

from ops.scripts.goal_prompt import PROMOTION_BAN_HEADER, build_goal_prompt, promotion_ban_lines


pytestmark = pytest.mark.public


def test_goal_prompt_injects_promotion_ban_until_clean_authority_is_current() -> None:
    contract = {
        "goal_id": "goal-demo",
        "objective": "Run bounded auto-improve for five days.",
        "promotion_policy": {
            "can_promote_result": False,
            "requires_sealed_authority_clean_pass": True,
            "promotion_ban_reason": "sealed authority clean pass is not current",
        },
        "execution_ladder": [
            {"profile": "30-minute-trial", "max_minutes": 30, "max_proposals": 1},
            {"profile": "5-day-sustained", "max_minutes": 7200, "max_proposals": 60},
        ],
        "stop_conditions": ["allowed-root violation"],
    }

    prompt = build_goal_prompt(contract)

    assert PROMOTION_BAN_HEADER in prompt
    assert "do not promote, release, or claim a learning improvement" in prompt
    assert "- 5-day-sustained: max_minutes=7200, max_proposals=60" in prompt
    assert "- allowed-root violation" in prompt


def test_promotion_ban_lines_disappear_only_when_promotion_policy_is_open() -> None:
    assert promotion_ban_lines(
        {
            "promotion_policy": {
                "can_promote_result": True,
                "requires_sealed_authority_clean_pass": False,
            }
        }
    ) == []
