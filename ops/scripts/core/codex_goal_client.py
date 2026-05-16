from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .artifact_io_runtime import read_json_object, write_json_object
from .schema_runtime import load_schema_with_vault_override, validate_or_raise


GOAL_CONTRACT_SCHEMA = "ops/schemas/codex-goal-contract.schema.json"
DEFAULT_GOAL_CONTRACT_PATH = "ops/reports/codex-goal-contract.json"


class GoalBackendUnavailableError(RuntimeError):
    pass


class GoalBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def persistent_across_processes(self) -> bool: ...

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]: ...

    def get_goal(self) -> dict[str, Any]: ...

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class FakeGoalBackend:
    """Small local backend used when Codex goal tools are unavailable to Python."""

    state: dict[str, Any] = field(default_factory=dict)
    name: str = "fake"
    persistent_across_processes: bool = False

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]:
        self.state = copy.deepcopy(contract)
        return copy.deepcopy(self.state)

    def get_goal(self) -> dict[str, Any]:
        return copy.deepcopy(self.state)

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]:
        self.state = _deep_merge(self.state, patch)
        return copy.deepcopy(self.state)


@dataclass(frozen=True)
class CallableGoalBackend:
    set_goal_fn: Callable[[dict[str, Any]], dict[str, Any]]
    get_goal_fn: Callable[[], dict[str, Any]]
    update_goal_fn: Callable[[dict[str, Any]], dict[str, Any]]
    name: str = "callable"
    persistent_across_processes: bool = True

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]:
        return self.set_goal_fn(contract)

    def get_goal(self) -> dict[str, Any]:
        return self.get_goal_fn()

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.update_goal_fn(patch)


@dataclass(frozen=True)
class FileGoalBackend:
    path: Path
    vault: Path | None = None
    name: str = "file"
    persistent_across_processes: bool = True

    def _vault(self) -> Path:
        if self.vault is not None:
            return self.vault
        return _infer_vault_from_goal_contract_path(self.path)

    def _validate(self, contract: dict[str, Any]) -> None:
        _validate_goal_contract(self._vault(), contract)

    def set_goal(self, contract: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(contract)
        self._validate(payload)
        _write_goal_contract(self.path, payload)
        return payload

    def get_goal(self) -> dict[str, Any]:
        payload = read_json_object(self.path, context="codex goal contract")
        self._validate(payload)
        return payload

    def update_goal(self, patch: dict[str, Any]) -> dict[str, Any]:
        payload = _deep_merge(self.get_goal(), patch)
        self._validate(payload)
        _write_goal_contract(self.path, payload)
        return payload


_DEFAULT_FAKE_BACKEND = FakeGoalBackend()


def _validate_goal_contract(vault: Path, contract: dict[str, Any]) -> None:
    schema = load_schema_with_vault_override(vault, GOAL_CONTRACT_SCHEMA)
    validate_or_raise(
        contract,
        schema,
        context="codex goal contract schema validation failed",
    )


def _write_goal_contract(path: Path, payload: dict[str, Any]) -> None:
    write_json_object(path, payload, trailing_newline=True)


def _deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _infer_vault_from_goal_contract_path(path: Path) -> Path:
    parts = path.parts
    suffix = Path(DEFAULT_GOAL_CONTRACT_PATH).parts
    if len(parts) >= len(suffix) and parts[-len(suffix) :] == suffix:
        return Path(*parts[: -len(suffix)]) if len(parts) > len(suffix) else Path(".")
    return path.parent


def _resolve_goal_contract_path(vault: Path | str, goal_contract_path: str | Path) -> Path:
    path = Path(goal_contract_path)
    if path.is_absolute():
        return path
    return Path(vault) / path


def default_file_goal_backend(
    *,
    vault: Path | str = ".",
    goal_contract_path: str | Path = DEFAULT_GOAL_CONTRACT_PATH,
) -> FileGoalBackend:
    return FileGoalBackend(
        path=_resolve_goal_contract_path(vault, goal_contract_path),
        vault=Path(vault),
    )


def detect_goal_backend(
    namespace: dict[str, Any] | None = None,
    *,
    allow_fake: bool = False,
) -> GoalBackend:
    """Return a callable backend when set/get/update goal callables are supplied.

    The in-memory fake backend is only available by explicit opt-in so production
    runtime paths cannot silently lose goal state at a process boundary.
    """

    source = namespace or {}
    set_goal_fn = source.get("set_goal")
    get_goal_fn = source.get("get_goal")
    update_goal_fn = source.get("update_goal")
    if callable(set_goal_fn) and callable(get_goal_fn) and callable(update_goal_fn):
        return CallableGoalBackend(set_goal_fn, get_goal_fn, update_goal_fn)
    if allow_fake:
        return _DEFAULT_FAKE_BACKEND
    raise GoalBackendUnavailableError(
        "no goal backend configured; pass FileGoalBackend/callables or allow_fake=True for tests"
    )


def require_persistent_goal_backend(
    backend: GoalBackend | None = None,
    *,
    vault: Path | str = ".",
    goal_contract_path: str | Path = DEFAULT_GOAL_CONTRACT_PATH,
) -> GoalBackend:
    active_backend = backend or default_file_goal_backend(
        vault=vault,
        goal_contract_path=goal_contract_path,
    )
    if not bool(getattr(active_backend, "persistent_across_processes", False)):
        raise ValueError(
            "goal auto-improve production runtime requires a process-persistent goal backend"
        )
    return active_backend


def _resolve_active_backend(
    backend: GoalBackend | None,
    *,
    vault: Path | str,
    goal_contract_path: str | Path,
) -> GoalBackend:
    if backend is not None:
        return backend
    return default_file_goal_backend(vault=vault, goal_contract_path=goal_contract_path)


def set_goal(
    contract: dict[str, Any],
    *,
    vault: Path | str = ".",
    goal_contract_path: str | Path = DEFAULT_GOAL_CONTRACT_PATH,
    backend: GoalBackend | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    vault_path = Path(vault)
    if validate:
        _validate_goal_contract(vault_path, contract)
    active_backend = _resolve_active_backend(
        backend,
        vault=vault_path,
        goal_contract_path=goal_contract_path,
    )
    return active_backend.set_goal(contract)


def get_goal(
    *,
    vault: Path | str = ".",
    goal_contract_path: str | Path = DEFAULT_GOAL_CONTRACT_PATH,
    backend: GoalBackend | None = None,
) -> dict[str, Any]:
    active_backend = _resolve_active_backend(
        backend,
        vault=vault,
        goal_contract_path=goal_contract_path,
    )
    return active_backend.get_goal()


def update_goal(
    patch: dict[str, Any],
    *,
    vault: Path | str = ".",
    goal_contract_path: str | Path = DEFAULT_GOAL_CONTRACT_PATH,
    backend: GoalBackend | None = None,
) -> dict[str, Any]:
    active_backend = _resolve_active_backend(
        backend,
        vault=vault,
        goal_contract_path=goal_contract_path,
    )
    return active_backend.update_goal(patch)


def backend_capabilities(
    backend: GoalBackend | None = None,
    *,
    vault: Path | str = ".",
    goal_contract_path: str | Path = DEFAULT_GOAL_CONTRACT_PATH,
) -> dict[str, Any]:
    active_backend = _resolve_active_backend(
        backend,
        vault=vault,
        goal_contract_path=goal_contract_path,
    )
    return {
        "backend": active_backend.name,
        "set_goal": hasattr(active_backend, "set_goal"),
        "get_goal": hasattr(active_backend, "get_goal"),
        "update_goal": hasattr(active_backend, "update_goal"),
        "persistent_across_processes": bool(
            getattr(active_backend, "persistent_across_processes", False)
        ),
    }
