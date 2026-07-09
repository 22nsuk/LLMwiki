from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TRUSTED_CANDIDATE_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "USERPROFILE",
        "WINDIR",
    }
)
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
    env: dict[str, str] = {}
    for key in TRUSTED_CANDIDATE_ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHON"] = str(trusted_python)
    if extra_env:
        env.update(extra_env)
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
    trusted = str(trusted_python.resolve())
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
        return shlex.split(
            f"make PYTHON={shlex.quote(str(trusted_python))} check",
            posix=True,
        )
    makefile = trusted_vault_root / "Makefile"
    if not makefile.is_file():
        raise ValueError("trusted vault root is missing Makefile for repo-health preflight")
    make_path = shutil.which("make")
    if make_path is None:
        raise ValueError("make executable is unavailable for trusted repo-health preflight")
    return [
        make_path,
        "-C",
        str(trusted_vault_root),
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
    env = build_trusted_candidate_env(
        trusted_python=request.trusted_python,
        extra_env=request.extra_env,
    )
    cwd = request.cwd or request.workspace_root
    timed_out = False
    stdout = ""
    stderr = ""
    returncode = 1
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
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
    except OSError as exc:
        stderr = str(exc)
        returncode = 126
    audit_record = {
        "purpose": request.purpose,
        "argv": argv,
        "cwd": cwd.as_posix(),
        "trusted_python": str(request.trusted_python.resolve()),
        "workspace_root": request.workspace_root.as_posix(),
        "trusted_vault_root": request.trusted_vault_root.as_posix(),
        "returncode": returncode,
        "timed_out": timed_out,
        "env_stripped": sorted(TRUSTED_CANDIDATE_ENV_STRIP),
        "network_policy": "default_deny_not_enforced_by_subprocess_wrapper",
    }
    if request.audit_rel_path:
        audit_path = request.trusted_vault_root / request.audit_rel_path
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return TrustedCandidateRunOutcome(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        argv=argv,
        audit_record=audit_record,
    )
