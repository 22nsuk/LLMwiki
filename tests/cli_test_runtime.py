from __future__ import annotations

import io
import os
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CliInvocationResult:
    exit_code: int
    stdout: str
    stderr: str


def _normalize_exit_code(code: object) -> int:
    if code is None:
        return 0
    if isinstance(code, bool):
        return int(code)
    if isinstance(code, int):
        return code
    return 1


def invoke_cli_main(
    main_fn: Callable[[list[str] | None], None],
    args: list[str],
    *,
    cwd: Path | None = None,
) -> CliInvocationResult:
    stdout = io.StringIO()
    stderr = io.StringIO()
    original_cwd = Path.cwd()
    exit_code = 0
    try:
        if cwd is not None:
            os.chdir(cwd)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                main_fn(args)
            except SystemExit as exc:
                exit_code = _normalize_exit_code(exc.code)
    finally:
        os.chdir(original_cwd)

    return CliInvocationResult(
        exit_code=exit_code,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )
