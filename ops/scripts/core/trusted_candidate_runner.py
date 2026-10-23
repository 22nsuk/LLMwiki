from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .candidate_sandbox_runtime import (
    candidate_environment,
    candidate_sandbox_argv,
    validate_candidate_workspace,
)
from .filesystem_runtime import atomic_write_text

TRUSTED_CANDIDATE_ENV_STRIP = frozenset(
    {
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSAFEPATH",
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
    }
)


@dataclass(frozen=True)
class TrustedCandidateRunRequest:
    purpose: str
    argv: list[str]
    workspace_root: Path
    trusted_vault_root: Path
    trusted_python: Path
    timeout_seconds: int
    cwd: Path | None = None
    extra_env: dict[str, str] | None = None
    audit_rel_path: str | None = None
    trusted_python_realpath: Path | None = None


@dataclass(frozen=True)
class TrustedCandidateRunOutcome:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    argv: list[str]
    audit_record: dict[str, Any]


def build_trusted_candidate_env(
    *,
    trusted_python: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = candidate_environment(python=trusted_python)
    if extra_env:
        raise ValueError("candidate validation does not accept environment overrides")
    for stripped in TRUSTED_CANDIDATE_ENV_STRIP:
        env.pop(stripped, None)
    return env


def _workspace_python_token(workspace_root: Path) -> str:
    return str((workspace_root / ".venv" / "bin" / "python").resolve())


def rewrite_argv_trusted_python(
    argv: list[str],
    *,
    workspace_root: Path,
    trusted_python: Path,
) -> list[str]:
    workspace_python_path = workspace_root / ".venv" / "bin" / "python"
    if trusted_python.absolute() == workspace_python_path.absolute():
        return list(argv)
    workspace_python = _workspace_python_token(workspace_root)
    trusted = str(trusted_python.absolute())
    rewritten: list[str] = []
    for token in argv:
        if token == workspace_python:
            rewritten.append(trusted)
            continue
        if token.endswith("/.venv/bin/python") and Path(token).resolve() == Path(workspace_python):
            rewritten.append(trusted)
            continue
        rewritten.append(token)
    return rewritten


def resolve_trusted_repo_health_argv(
    *,
    test_files: list[str],
    workspace_mode: str,
    workspace_root: Path,
    trusted_vault_root: Path,
    trusted_python: Path,
) -> list[str]:
    selectors = [str(path).strip() for path in test_files if str(path).strip()]
    if workspace_mode == "sparse_manifest" and selectors:
        quoted_selectors = " ".join(shlex.quote(path) for path in selectors)
        command = (
            f"{shlex.quote(str(trusted_python))} -B -m pytest "
            f"-p no:cacheprovider {quoted_selectors}"
        )
        return shlex.split(command, posix=True)
    if workspace_root.resolve() == trusted_vault_root.resolve():
        return shlex.split(f"make PYTHON={shlex.quote(str(trusted_python))} check", posix=True)
    makefile = workspace_root / "Makefile"
    if not makefile.is_file():
        raise ValueError("candidate workspace is missing Makefile for repo-health preflight")
    make_path = shutil.which("make")
    if make_path is None:
        raise ValueError("make executable is unavailable for trusted repo-health preflight")
    return [
        make_path,
        "-C",
        str(workspace_root),
        f"PYTHON={trusted_python}",
        f"VAULT={workspace_root}",
        "check",
    ]


def run_trusted_candidate_command(request: TrustedCandidateRunRequest) -> TrustedCandidateRunOutcome:
    argv = rewrite_argv_trusted_python(
        request.argv,
        workspace_root=request.workspace_root,
        trusted_python=request.trusted_python,
    )
    cwd = request.cwd or request.workspace_root
    timed_out = False
    stdout = ""
    stderr = ""
    returncode = 1
    if request.trusted_python_realpath is not None:
        try:
            actual_realpath = request.trusted_python.resolve(strict=True)
        except OSError:
            actual_realpath = None
        if actual_realpath != request.trusted_python_realpath:
            stderr = "trusted python symlink target changed before launch"
            returncode = 126
    interpreter_alias = None
    if returncode != 126:
        try:
            workspace_python = request.workspace_root.resolve() / ".venv" / "bin" / "python"
            if request.workspace_root.resolve() == request.trusted_vault_root.resolve() and workspace_python.is_symlink():
                # Preserve the existing same-root interpreter link without
                # exposing its target; require it to remain unchanged afterward.
                interpreter_alias = (workspace_python, workspace_python.resolve(strict=True))
            env = build_trusted_candidate_env(
                trusted_python=request.trusted_python, extra_env=request.extra_env,
            )
            sandbox_argv = candidate_sandbox_argv(
                argv, workspace_root=request.workspace_root, cwd=cwd,
                trusted_python=request.trusted_python, interpreter_alias=interpreter_alias,
            )
            completed = subprocess.run(
                sandbox_argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                timeout=request.timeout_seconds,
                check=False,
            )
            returncode = int(completed.returncode)
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
            returncode = 124
        except (OSError, ValueError) as exc:
            stderr = str(exc)
            returncode = 126
    try:
        validate_candidate_workspace(request.workspace_root, interpreter_alias=interpreter_alias)
    except (OSError, ValueError) as exc:
        # Callers write logs and ledgers after receiving an outcome. An unsafe
        # tree must stop that entire path, including audit writes on failure.
        raise ValueError(f"unsafe candidate workspace after validation: {exc}") from exc
    audit_record = {
        "purpose": request.purpose,
        "argv": argv,
        "cwd": cwd.as_posix(),
        "trusted_python": str(request.trusted_python.absolute()),
        "workspace_root": request.workspace_root.as_posix(),
        "trusted_vault_root": request.trusted_vault_root.as_posix(),
        "returncode": returncode,
        "timed_out": timed_out,
        "env_stripped": sorted(TRUSTED_CANDIDATE_ENV_STRIP),
        "network_policy": "isolated_network_namespace",
        "execution_isolation": "bubblewrap",
    }
    if request.trusted_python_realpath is not None:
        audit_record["trusted_python_realpath"] = str(request.trusted_python_realpath)
    if request.audit_rel_path:
        audit_path = request.trusted_vault_root / request.audit_rel_path
        if not audit_path.resolve().is_relative_to(request.trusted_vault_root.resolve()):
            raise ValueError("candidate audit path must remain inside the trusted vault")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(audit_path, json.dumps(audit_record, ensure_ascii=False, indent=2) + "\n")
    return TrustedCandidateRunOutcome(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        argv=argv,
        audit_record=audit_record,
    )
