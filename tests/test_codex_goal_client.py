from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from ops.scripts.codex_goal_client import (
    FakeGoalBackend,
    FileGoalBackend,
    GoalBackendUnavailableError,
    backend_capabilities,
    detect_goal_backend,
    get_goal,
    require_persistent_goal_backend,
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


def test_file_goal_backend_persists_across_client_instances(tmp_path: Path) -> None:
    _copy_goal_schema(tmp_path)
    contract_path = tmp_path / "ops" / "reports" / "codex-goal-contract.json"
    contract = _contract()

    stored = set_goal(contract, vault=tmp_path, goal_contract_path=contract_path.relative_to(tmp_path))
    patched = update_goal(
        {"status": "blocked", "promotion_policy": {"can_promote_result": False}},
        vault=tmp_path,
        goal_contract_path=contract_path.relative_to(tmp_path),
    )
    reloaded = get_goal(
        vault=tmp_path,
        goal_contract_path=contract_path.relative_to(tmp_path),
    )

    assert stored["goal_id"] == "goal-20260515-5day-auto-improve-runtime"
    assert patched["status"] == "blocked"
    assert patched["promotion_policy"]["requires_sealed_authority_clean_pass"] is True
    assert reloaded == patched
    assert backend_capabilities(
        FileGoalBackend(path=contract_path, vault=tmp_path)
    )["persistent_across_processes"] is True


def test_file_goal_backend_rejects_invalid_merged_update(tmp_path: Path) -> None:
    _copy_goal_schema(tmp_path)
    backend = FileGoalBackend(
        path=tmp_path / "ops" / "reports" / "codex-goal-contract.json",
        vault=tmp_path,
    )
    backend.set_goal(_contract())

    with pytest.raises(ValueError, match="codex goal contract schema validation failed"):
        backend.update_goal({"duration": {"min_sustained_days": 4}})

    assert backend.get_goal()["duration"]["min_sustained_days"] == 5


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


def test_detect_goal_backend_requires_explicit_fake_opt_in() -> None:
    with pytest.raises(GoalBackendUnavailableError, match="no goal backend configured"):
        detect_goal_backend()

    assert detect_goal_backend(allow_fake=True).name == "fake"


def test_require_persistent_goal_backend_rejects_fake_backend() -> None:
    with pytest.raises(ValueError, match="process-persistent goal backend"):
        require_persistent_goal_backend(FakeGoalBackend())


def test_set_goal_rejects_invalid_contract(tmp_path: Path) -> None:
    _copy_goal_schema(tmp_path)

    with pytest.raises(ValueError, match="codex goal contract schema validation failed"):
        set_goal({"goal_id": "missing-fields"}, vault=tmp_path, backend=FakeGoalBackend())
