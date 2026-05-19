from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.auto_improve_loop import main as auto_improve_loop_main


pytestmark = pytest.mark.public


def test_auto_improve_loop_goal_contract_uses_canonical_session_path() -> None:
    with mock.patch(
        "ops.scripts.mechanism.auto_improve_loop.run_auto_improve_session",
        return_value={
            "session_id": "goal-session",
            "session_report": "ops/reports/auto-improve-sessions/goal-session.json",
        },
    ) as run_session:
        with mock.patch("builtins.print") as printed:
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
                ]
            )

    run_session.assert_called_once()
    kwargs = run_session.call_args.kwargs
    assert run_session.call_args.args == (Path("."),)
    assert kwargs["goal_contract_path"] == "ops/reports/codex-goal-contract.json"
    assert kwargs["session_id"] == "goal-session"
    assert kwargs["max_minutes"] == 30
    assert kwargs["max_proposals"] == 1
    assert kwargs["max_consecutive_failures"] == 1
    assert kwargs["maintain_until_budget"] is True
    assert kwargs["maintenance_interval_seconds"] == 300
    payload = json.loads(printed.call_args.args[0])
    assert payload["session_id"] == "goal-session"


def test_auto_improve_loop_retires_legacy_goal_wrapper_flags() -> None:
    with pytest.raises(SystemExit) as exc:
        auto_improve_loop_main(
            [
                "--vault",
                ".",
                "--goal-contract",
                "ops/reports/codex-goal-contract.json",
                "--goal-profile",
                "30-minute-trial",
                "--goal-dry-run",
            ]
        )

    assert exc.value.code == 2
