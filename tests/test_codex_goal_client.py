from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from ops.scripts.codex_goal_client import (
    FakeGoalBackend,
    backend_capabilities,
    detect_goal_backend,
    get_goal,
    set_goal,
    update_goal,
)
from ops.scripts.goal_run_status import default_goal_contract
from ops.scripts.runtime_context import RuntimeContext


pytestmark = pytest.mark.public
REPO_ROOT = Path(__file__).resolve().parents[1]


def _copy_goal_schema(vault: Path) -> None:
    schema_dir = vault / "ops" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        REPO_ROOT / "ops" / "schemas" / "codex-goal-contract.schema.json",
        schema_dir / "codex-goal-contract.schema.json",
    )


def _contract() -> dict:
    context = RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, 0, tzinfo=dt.timezone.utc),
    )
    return default_goal_contract(
        context=context,
        repo_url="https://github.com/22nsuk/LLMwiki",
        visibility="PRIVATE",
        baseline_commit="6c3ca7c46c6369ad043d78da5114c84173a14973",
        branch="goal/5day-auto-improve-runtime",
        worktree_path="../LLMwiki-worktrees/goal-5day-auto-improve-runtime",
    )


def test_fake_goal_backend_supports_set_get_update_with_schema_validation(tmp_path: Path) -> None:
    _copy_goal_schema(tmp_path)
    backend = FakeGoalBackend()
    contract = _contract()

    stored = set_goal(contract, vault=tmp_path, backend=backend)
    patched = update_goal({"status": "blocked"}, backend=backend)

    assert stored["goal_id"] == "goal-20260515-5day-auto-improve-runtime"
    assert patched["status"] == "blocked"
    assert get_goal(backend=backend)["status"] == "blocked"
    assert backend_capabilities(backend)["persistent_across_processes"] is False


def test_detect_goal_backend_uses_injected_callables() -> None:
    state: dict = {}
    backend = detect_goal_backend(
        {
            "set_goal": lambda contract: state.setdefault("goal", dict(contract)),
            "get_goal": lambda: dict(state.get("goal", {})),
            "update_goal": lambda patch: state.setdefault("goal", {}) | patch,
        }
    )

    assert backend.name == "callable"
    backend.set_goal({"goal_id": "demo"})
    assert backend.get_goal() == {"goal_id": "demo"}
    assert backend.update_goal({"status": "running"}) == {"goal_id": "demo", "status": "running"}


def test_set_goal_rejects_invalid_contract(tmp_path: Path) -> None:
    _copy_goal_schema(tmp_path)

    with pytest.raises(ValueError, match="codex goal contract schema validation failed"):
        set_goal({"goal_id": "missing-fields"}, vault=tmp_path, backend=FakeGoalBackend())
