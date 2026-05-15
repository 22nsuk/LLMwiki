from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .schema_runtime import load_schema, validate_or_raise


GOAL_CONTRACT_SCHEMA = "ops/schemas/codex-goal-contract.schema.json"


class GoalBackend(Protocol):
    @property
    def name(self) -> str: ...

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]: ...

    def get_goal(self) -> dict[str, Any]: ...

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class FakeGoalBackend:
    """Small local backend used when Codex goal tools are unavailable to Python."""

    state: dict[str, Any] = field(default_factory=dict)
    name: str = "fake"

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]:
        self.state = dict(contract)
        return dict(self.state)

    def get_goal(self) -> dict[str, Any]:
        return dict(self.state)

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]:
        self.state = {**self.state, **patch}
        return dict(self.state)


@dataclass(frozen=True)
class CallableGoalBackend:
    set_goal_fn: Callable[[dict[str, Any]], dict[str, Any]]
    get_goal_fn: Callable[[], dict[str, Any]]
    update_goal_fn: Callable[[dict[str, Any]], dict[str, Any]]
    name: str = "callable"

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]:
        return self.set_goal_fn(contract)

    def get_goal(self) -> dict[str, Any]:
        return self.get_goal_fn()

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.update_goal_fn(patch)


_DEFAULT_FAKE_BACKEND = FakeGoalBackend()


def _validate_goal_contract(vault: Path, contract: dict[str, Any]) -> None:
    schema = load_schema(vault / GOAL_CONTRACT_SCHEMA)
    validate_or_raise(
        contract,
        schema,
        context="codex goal contract schema validation failed",
    )


def detect_goal_backend(namespace: dict[str, Any] | None = None) -> GoalBackend:
    """Return a callable backend when set/get/update goal callables are supplied.

    The Codex tool runtime is not importable from repo Python, so production CLI
    paths intentionally fall back to the fake backend unless a harness injects
    compatible callables.
    """

    source = namespace or {}
    set_goal_fn = source.get("set_goal")
    get_goal_fn = source.get("get_goal")
    update_goal_fn = source.get("update_goal")
    if callable(set_goal_fn) and callable(get_goal_fn) and callable(update_goal_fn):
        return CallableGoalBackend(set_goal_fn, get_goal_fn, update_goal_fn)
    return _DEFAULT_FAKE_BACKEND


def set_goal(
    contract: dict[str, Any],
    *,
    vault: Path | str = ".",
    backend: GoalBackend | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    vault_path = Path(vault)
    if validate:
        _validate_goal_contract(vault_path, contract)
    active_backend = backend or detect_goal_backend()
    return active_backend.set_goal(contract)


def get_goal(*, backend: GoalBackend | None = None) -> dict[str, Any]:
    active_backend = backend or detect_goal_backend()
    return active_backend.get_goal()


def update_goal(
    patch: dict[str, Any],
    *,
    backend: GoalBackend | None = None,
) -> dict[str, Any]:
    active_backend = backend or detect_goal_backend()
    return active_backend.update_goal(patch)


def backend_capabilities(backend: GoalBackend | None = None) -> dict[str, Any]:
    active_backend = backend or detect_goal_backend()
    return {
        "backend": active_backend.name,
        "set_goal": hasattr(active_backend, "set_goal"),
        "get_goal": hasattr(active_backend, "get_goal"),
        "update_goal": hasattr(active_backend, "update_goal"),
        "persistent_across_processes": active_backend.name != "fake",
    }
