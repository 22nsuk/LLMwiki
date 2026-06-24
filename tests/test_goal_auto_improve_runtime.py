from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.mechanism.auto_improve_loop import main as auto_improve_loop_main

pytestmark = pytest.mark.public


def test_auto_improve_loop_goal_contract_uses_canonical_session_path() -> None:
    with mock.patch(
        "ops.scripts.mechanism.auto_improve_loop.run_auto_improve_session",
        return_value={
            "session_id": "goal-session",
            "session_report": "ops/reports/auto-improve-sessions/goal-session.json",
        },
    ) as run_session, mock.patch("builtins.print") as printed:
        auto_improve_loop_main(
            [
                "--vault",
                ".",
                "--session-id",
                "goal-session",
                "--goal-contract",
                "ops/reports/codex-goal-contract.json",
                "--max-minutes",
                "30",
                "--max-proposals",
                "1",
                "--max-consecutive-failures",
                "1",
                "--maintain-until-budget",
                "--maintenance-interval-seconds",
                "300",
                "--post-promote-maintenance-cycles",
                "2",
            ]
        )

    run_session.assert_called_once()
    kwargs = run_session.call_args.kwargs
    assert run_session.call_args.args == (Path(),)
    assert kwargs["goal_contract_path"] == "ops/reports/codex-goal-contract.json"
    assert kwargs["session_id"] == "goal-session"
    assert kwargs["max_minutes"] == 30
    assert kwargs["max_proposals"] == 1
    assert kwargs["max_consecutive_failures"] == 1
    assert kwargs["maintain_until_budget"] is True
    assert kwargs["maintenance_interval_seconds"] == 300
    assert kwargs["post_promote_maintenance_cycles"] == 2
    payload = json.loads(printed.call_args.args[0])
    assert payload["session_id"] == "goal-session"


def test_auto_improve_loop_prints_maintenance_action_next_budget() -> None:
    with (
        mock.patch(
            "ops.scripts.mechanism.auto_improve_loop.maintenance_action_resume_plan",
            return_value={
                "decisions": {"can_resume": True},
                "next_max_proposals": 2,
                "recommended_next_action": "run resume",
            },
        ) as action_plan,
        mock.patch(
            "ops.scripts.mechanism.auto_improve_loop.write_maintenance_action_resume_plan",
        ) as write_plan,
        mock.patch("builtins.print") as printed,
    ):
        auto_improve_loop_main(
            [
                "--vault",
                ".",
                "--resume-session",
                "goal-session",
                "--print-maintenance-action-next-max-proposals",
                "--maintenance-action-plan-out",
                "tmp/goal-runtime-maintenance-action.json",
            ]
        )

    action_plan.assert_called_once_with(Path(), session_id="goal-session")
    write_plan.assert_called_once()
    printed.assert_called_once_with(2)


def test_auto_improve_loop_rejects_maintenance_action_plan_outside_vault(tmp_path: Path) -> None:
    outside_path = tmp_path / "outside-maintenance-action.json"
    with (
        mock.patch(
            "ops.scripts.mechanism.auto_improve_loop.maintenance_action_resume_plan",
            return_value={
                "decisions": {"can_resume": True},
                "next_max_proposals": 2,
                "recommended_next_action": "run resume",
            },
        ) as action_plan,
        mock.patch(
            "ops.scripts.mechanism.auto_improve_loop.write_maintenance_action_resume_plan",
        ) as write_plan,
        pytest.raises(SystemExit) as exc_info,
    ):
        auto_improve_loop_main(
            [
                "--vault",
                ".",
                "--resume-session",
                "goal-session",
                "--print-maintenance-action-next-max-proposals",
                "--maintenance-action-plan-out",
                outside_path.as_posix(),
            ]
        )

    action_plan.assert_called_once_with(Path(), session_id="goal-session")
    write_plan.assert_not_called()
    assert exc_info.value.code == 8
    assert not outside_path.exists()
