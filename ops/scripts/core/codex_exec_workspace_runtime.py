from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Protocol

from ops.scripts.core.workspace_python_identity_runtime import (
    WorkspacePythonIdentity,
    build_workspace_python_identity,
    read_workspace_python_identity,
    verify_workspace_python_shim,
)


class _WorkspacePythonRequest(Protocol):
    @property
    def workspace_root(self) -> Path: ...

    @property
    def artifact_root(self) -> Path: ...


def workspace_virtualenv_python(workspace_root: Path) -> Path | None:
    venv_root = workspace_root / ".venv"
    for rel_path in ("bin/python", "Scripts/python.exe", "Scripts/python"):
        python_path = venv_root / rel_path
        if python_path.exists():
            return python_path
    return None


def workspace_virtualenv_bin(workspace_root: Path) -> Path | None:
    python_path = workspace_virtualenv_python(workspace_root)
    if python_path is None:
        return None
    return python_path.parent


def trusted_workspace_python_source(artifact_root: Path) -> Path:
    repo_python = artifact_root / ".venv" / "bin" / "python"
    if repo_python.exists():
        return repo_python
    return Path(sys.executable).resolve()


def expected_external_workspace_python_shim(artifact_root: Path) -> str:
    source_python = trusted_workspace_python_source(artifact_root)
    return f"#!/bin/sh\nexec {shlex.quote(str(source_python))} \"$@\"\n"


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def path_is_inside_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except (OSError, ValueError):
        try:
            path.absolute().relative_to(workspace_root.absolute())
            return True
        except ValueError:
            return False


def path_without_workspace_virtualenv(workspace_root: Path) -> str:
    path_text = os.environ.get("PATH", "")
    venv_bin = workspace_virtualenv_bin(workspace_root)
    if venv_bin is None or not path_text:
        return path_text
    entries: list[str] = []
    for entry in path_text.split(os.pathsep):
        if entry and same_path(Path(entry), venv_bin):
            continue
        entries.append(entry)
    return os.pathsep.join(entries)


def path_has_workspace_entry(path_text: str, workspace_root: Path) -> bool:
    for entry in path_text.split(os.pathsep):
        if entry in {"", "."}:
            return True
        entry_path = Path(entry)
        if not entry_path.is_absolute():
            return True
        if path_is_inside_workspace(entry_path, workspace_root):
            return True
    return False


def workspace_codex_candidate_exists(workspace_root: Path) -> bool:
    venv_bin = workspace_virtualenv_bin(workspace_root)
    candidates = [workspace_root / name for name in ("codex", "codex.exe", "codex.cmd")]
    if venv_bin is not None:
        candidates.extend(
            venv_bin / name
            for name in ("codex", "codex.exe", "codex.cmd", "codex.ps1", "codex.js")
        )
    return any(path.exists() for path in candidates)


def resolve_codex_executable(workspace_root: Path) -> str:
    path_text = path_without_workspace_virtualenv(workspace_root)
    if not path_text or path_has_workspace_entry(path_text, workspace_root):
        if workspace_codex_candidate_exists(workspace_root):
            _raise_codex_contract_error(
                "unable to resolve codex from trusted PATH; refusing to launch a workspace codex"
            )
        _raise_codex_contract_error(
            "unable to resolve codex from trusted PATH; refusing workspace-relative fallback"
        )
    resolved = shutil.which("codex", path=path_text)
    if resolved:
        return resolved
    if workspace_codex_candidate_exists(workspace_root):
        _raise_codex_contract_error(
            "unable to resolve codex from trusted PATH; refusing to launch a workspace codex"
        )
    return "codex"


def execution_env(workspace_root: Path) -> dict[str, str] | None:
    venv_bin = workspace_virtualenv_bin(workspace_root)
    if venv_bin is None:
        return None
    env = dict(os.environ)
    existing_path = env.get("PATH", "")
    env["PATH"] = (
        str(venv_bin)
        if not existing_path
        else f"{venv_bin}{os.pathsep}{existing_path}"
    )
    env["VIRTUAL_ENV"] = str(workspace_root / ".venv")
    return env


def is_workspace_python_shim(content: str) -> bool:
    return content.startswith("#!/bin/sh\nexec ")


def _trusted_artifact_identity_issue(
    provisioned_identity: WorkspacePythonIdentity,
    *,
    artifact_root: Path,
) -> str:
    try:
        expected_identity = build_workspace_python_identity(
            source_python=trusted_workspace_python_source(artifact_root),
            shim_content=expected_external_workspace_python_shim(artifact_root),
        )
    except OSError as exc:
        return f"trusted workspace python source is unreadable: {exc}"
    except ValueError:
        return "trusted workspace python source is not a regular file"

    if (
        provisioned_identity.shim_content != expected_identity.shim_content
        or provisioned_identity.shim_sha256 != expected_identity.shim_sha256
    ):
        return "workspace python identity manifest does not match trusted artifact shim"
    if (
        provisioned_identity.source_realpath != expected_identity.source_realpath
        or provisioned_identity.source_device != expected_identity.source_device
        or provisioned_identity.source_inode != expected_identity.source_inode
        or provisioned_identity.source_sha256 != expected_identity.source_sha256
    ):
        return "trusted workspace python source identity changed since workspace provisioning"
    return ""


def external_workspace_python_issue(
    request: _WorkspacePythonRequest,
    *,
    workspace_python: Path,
) -> str:
    is_external_workspace = not same_path(request.workspace_root, request.artifact_root)
    if is_external_workspace:
        loaded_identity = read_workspace_python_identity(request.workspace_root)
        if loaded_identity.issue:
            return loaded_identity.issue
        assert loaded_identity.identity is not None
        identity_issue = verify_workspace_python_shim(
            request.workspace_root,
            workspace_python=workspace_python,
            expected_identity=loaded_identity.identity,
        )
        if identity_issue:
            return identity_issue
        return _trusted_artifact_identity_issue(
            loaded_identity.identity,
            artifact_root=request.artifact_root,
        )
    identity_issue = verify_workspace_python_shim(
        request.workspace_root,
        workspace_python=workspace_python,
    )
    if identity_issue and identity_issue != "missing workspace python identity manifest":
        return identity_issue
    if identity_issue == "missing workspace python identity manifest":
        try:
            content = workspace_python.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return f"workspace virtualenv python shim is unreadable: {exc}"
        if is_workspace_python_shim(content):
            return identity_issue
        if not same_path(request.workspace_root, request.artifact_root):
            return identity_issue
    return ""


def _raise_codex_contract_error(message: str) -> None:
    from .codex_exec_executor import ExecutorContractError

    raise ExecutorContractError(message)
