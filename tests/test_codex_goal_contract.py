from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from ops.scripts.goal_run_status import default_goal_contract
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema


pytestmark = pytest.mark.public
REPO_ROOT = Path(__file__).resolve().parents[1]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, 0, tzinfo=dt.timezone.utc),
    )


def test_default_codex_goal_contract_validates_and_preserves_5_day_ladder() -> None:
    contract = default_goal_contract(
        context=fixed_context(),
        repo_url="https://github.com/22nsuk/LLMwiki",
        visibility="PRIVATE",
        baseline_commit="6c3ca7c46c6369ad043d78da5114c84173a14973",
        branch="goal/5day-auto-improve-runtime",
        worktree_path="../LLMwiki-worktrees/goal-5day-auto-improve-runtime",
    )

    schema = load_schema(REPO_ROOT / "ops" / "schemas" / "codex-goal-contract.schema.json")

    assert validate_with_schema(contract, schema) == []
    assert contract["duration"] == {"min_sustained_days": 5, "max_minutes": 7200}
    assert contract["promotion_policy"]["can_promote_result"] is False
    assert contract["promotion_policy"]["requires_sealed_authority_clean_pass"] is True
    assert [item["profile"] for item in contract["execution_ladder"]] == [
        "30-minute-trial",
        "6-hour-ramp",
        "2-day-candidate",
        "5-day-sustained",
    ]
    assert contract["execution_ladder"][-1]["max_proposals"] == 60
    assert contract["execution_ladder"][-1]["heartbeat_interval_minutes"] == 5
