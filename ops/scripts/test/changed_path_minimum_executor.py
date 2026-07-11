from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.schema_constants_runtime import (
    WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_or_raise
from ops.scripts.test.test_lane_registry_runtime import load_registry

RunCommand = Callable[..., subprocess.CompletedProcess[str]]
MAKE_TARGET_RE = re.compile(r"^[A-Za-z0-9_.%/@-]+$")
PYTEST_ARGV_PREFIX = (
    ".venv/bin/python",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
)
ALLOWED_ENVIRONMENT = {"PYTHONDONTWRITEBYTECODE": "1"}


def _load_plan(vault: Path, plan_path: str) -> dict[str, Any]:
    path = (vault / plan_path).resolve()
    if not path.is_relative_to(vault):
        raise ValueError("changed-path plan must stay inside the repository")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("changed-path plan must be a JSON object")
    validate_or_raise(
        payload,
        load_schema(vault / WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH),
        context="changed-path minimum plan validation failed",
    )
    return payload


def _command_environment(overrides: Mapping[str, object]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({str(name): str(value) for name, value in overrides.items()})
    return environment


def _safe_command_text(command: str) -> str:
    return json.dumps(command, ensure_ascii=True)


def _allowed_make_targets(vault: Path) -> set[str]:
    config = load_registry(vault)["changed_path_minimums"]
    command_groups = [
        *(rule.get("commands", []) for rule in config.get("rules", [])),
        config.get("unknown_path", {}).get("commands", []),
    ]
    targets: set[str] = set()
    for commands in command_groups:
        for command in commands:
            tokens = shlex.split(str(command), posix=True)
            while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
                tokens.pop(0)
            if len(tokens) == 2 and tokens[0] == "make":
                targets.add(tokens[1])
    return targets


def _resolved_argv(vault: Path, argv: Sequence[object]) -> list[str]:
    resolved = [str(token) for token in argv]
    if not resolved:
        raise ValueError("changed-path command argv must not be empty")
    if resolved[0] == ".venv/bin/python":
        candidates = (
            vault / ".venv/bin/python",
            vault / ".venv/Scripts/python.exe",
        )
        workspace_python = next((path for path in candidates if path.is_file()), None)
        if workspace_python is None:
            raise RuntimeError(
                "workspace Python is unavailable; run `make dev-install` before "
                "changed-path-minimum-test"
            )
        resolved[0] = str(workspace_python)
    return resolved


def _validate_repo_test_selector(selector: str) -> None:
    file_part = selector.split("::", 1)[0]
    path = Path(file_part)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "tests":
        raise ValueError(f"changed-path pytest selector must stay under tests/: {selector!r}")


def _validate_command_spec(
    argv: Sequence[object],
    env: Mapping[str, object],
    *,
    allowed_make_targets: set[str],
) -> None:
    tokens = tuple(str(token) for token in argv)
    normalized_env = {str(name): str(value) for name, value in env.items()}
    if tokens[:1] == ("make",):
        if len(tokens) != 2 or MAKE_TARGET_RE.fullmatch(tokens[1]) is None:
            raise ValueError(f"unsupported changed-path make command: {tokens!r}")
        if tokens[1] not in allowed_make_targets:
            raise ValueError(f"changed-path make target is not registry-owned: {tokens[1]!r}")
        if normalized_env:
            raise ValueError("changed-path make commands must not override the environment")
        return
    if tokens[: len(PYTEST_ARGV_PREFIX)] == PYTEST_ARGV_PREFIX:
        if len(tokens) != len(PYTEST_ARGV_PREFIX) + 1:
            raise ValueError(f"unsupported changed-path pytest command: {tokens!r}")
        if normalized_env != ALLOWED_ENVIRONMENT:
            raise ValueError("changed-path pytest commands require the cache-safe environment")
        _validate_repo_test_selector(tokens[-1])
        return
    raise ValueError(f"unsupported changed-path executable: {tokens[:1]!r}")


def _command_text_from_spec(
    argv: Sequence[object],
    env: Mapping[str, object],
) -> str:
    environment = [f"{name}={value}" for name, value in env.items()]
    return " ".join([*environment, *(str(token) for token in argv)])


def execute_plan(
    vault: Path,
    report: Mapping[str, object],
    *,
    run_command: RunCommand = subprocess.run,
) -> int:
    raw_plan = report.get("changed_path_minimum_plan")
    if not isinstance(raw_plan, dict):
        raise ValueError("report missing changed_path_minimum_plan")
    raw_specs = raw_plan.get("selected_command_specs")
    if not isinstance(raw_specs, list):
        raise ValueError("changed-path plan missing selected_command_specs")
    selected_commands = raw_plan.get("selected_commands")
    if not isinstance(selected_commands, list) or selected_commands != [
        spec.get("command") if isinstance(spec, dict) else None for spec in raw_specs
    ]:
        raise ValueError("changed-path command strings and executable specs do not match")

    total = len(raw_specs)
    allowed_make_targets = _allowed_make_targets(vault)
    for index, raw_spec in enumerate(raw_specs, start=1):
        if not isinstance(raw_spec, dict):
            raise ValueError("changed-path command spec must be an object")
        command = str(raw_spec.get("command", ""))
        argv = raw_spec.get("argv")
        env = raw_spec.get("env")
        if not command.strip() or not isinstance(argv, list) or not isinstance(env, dict):
            raise ValueError(f"invalid changed-path command spec: {command or '<unnamed>'}")
        if command != _command_text_from_spec(argv, env):
            raise ValueError("changed-path display command does not match argv and env")
        _validate_command_spec(
            argv,
            env,
            allowed_make_targets=allowed_make_targets,
        )
        print(
            f"changed-path minimum [{index}/{total}]: {_safe_command_text(command)}",
            flush=True,
        )
        completed = run_command(
            _resolved_argv(vault, argv),
            cwd=vault,
            env=_command_environment(env),
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            print(
                "changed-path minimum failed with exit code "
                f"{completed.returncode}: {_safe_command_text(command)}",
                file=sys.stderr,
            )
            return int(completed.returncode)

    checkpoint_commands = raw_plan.get("final_checkpoint_commands", [])
    checkpoint_text = ", ".join(
        _safe_command_text(str(command)) for command in checkpoint_commands
    )
    print(
        "changed-path minimum complete; release proof remains outstanding"
        + (f": {checkpoint_text}" if checkpoint_text else ""),
        flush=True,
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute a schema-backed changed-path minimum test plan."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--plan", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = _load_plan(vault, args.plan)
    print(
        "changed-path minimum plan: "
        f"{_safe_command_text(display_path(vault, vault / args.plan))}"
    )
    return execute_plan(vault, report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
