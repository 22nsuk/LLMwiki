from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKSPACE_PYTHON_IDENTITY_REL = ".llmwiki/workspace-python-identity.json"


@dataclass(frozen=True)
class WorkspacePythonIdentity:
    source_realpath: str
    source_device: int
    source_inode: int
    source_sha256: str
    shim_sha256: str
    shim_content: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_realpath": self.source_realpath,
            "source_device": self.source_device,
            "source_inode": self.source_inode,
            "source_sha256": self.source_sha256,
            "shim_sha256": self.shim_sha256,
            "shim_content": self.shim_content,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WorkspacePythonIdentity:
        return cls(
            source_realpath=_required_str(payload, "source_realpath"),
            source_device=_required_int(payload, "source_device"),
            source_inode=_required_int(payload, "source_inode"),
            source_sha256=_required_str(payload, "source_sha256"),
            shim_sha256=_required_str(payload, "shim_sha256"),
            shim_content=_required_str(payload, "shim_content"),
        )


@dataclass(frozen=True)
class WorkspacePythonIdentityLoadResult:
    identity: WorkspacePythonIdentity | None
    issue: str


def workspace_python_identity_path(workspace_root: Path) -> Path:
    return workspace_root / WORKSPACE_PYTHON_IDENTITY_REL


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _shim_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_workspace_python_identity(*, source_python: Path, shim_content: str) -> WorkspacePythonIdentity:
    resolved = source_python.resolve()
    source_stat = resolved.lstat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("workspace python source must be a regular file")
    return WorkspacePythonIdentity(
        source_realpath=str(resolved),
        source_device=int(source_stat.st_dev),
        source_inode=int(source_stat.st_ino),
        source_sha256=_file_sha256(resolved),
        shim_sha256=_shim_sha256(shim_content),
        shim_content=shim_content,
    )


def write_workspace_python_identity(workspace_root: Path, identity: WorkspacePythonIdentity) -> Path:
    path = workspace_python_identity_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity.to_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_workspace_python_identity(workspace_root: Path) -> WorkspacePythonIdentityLoadResult:
    path = workspace_python_identity_path(workspace_root)
    if not path.is_file():
        return WorkspacePythonIdentityLoadResult(None, "missing workspace python identity manifest")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return WorkspacePythonIdentityLoadResult(
            None,
            f"workspace python identity manifest is invalid JSON: {exc}",
        )
    except (OSError, UnicodeDecodeError) as exc:
        return WorkspacePythonIdentityLoadResult(
            None,
            f"workspace python identity manifest is unreadable: {exc}",
        )
    if not isinstance(payload, dict):
        return WorkspacePythonIdentityLoadResult(
            None,
            "workspace python identity manifest must be a JSON object",
        )
    try:
        return WorkspacePythonIdentityLoadResult(WorkspacePythonIdentity.from_payload(payload), "")
    except (TypeError, ValueError) as exc:
        return WorkspacePythonIdentityLoadResult(
            None,
            f"workspace python identity manifest has invalid fields: {exc}",
        )


def load_workspace_python_identity(workspace_root: Path) -> WorkspacePythonIdentity | None:
    return read_workspace_python_identity(workspace_root).identity


def verify_workspace_python_shim(
    workspace_root: Path,
    *,
    workspace_python: Path,
    expected_identity: WorkspacePythonIdentity | None = None,
) -> str:
    if expected_identity is None:
        loaded_identity = read_workspace_python_identity(workspace_root)
        if loaded_identity.issue:
            return loaded_identity.issue
        assert loaded_identity.identity is not None
        identity = loaded_identity.identity
    else:
        identity = expected_identity
    try:
        python_stat = workspace_python.lstat()
    except OSError as exc:
        return f"workspace virtualenv python shim is unreadable: {exc}"
    if not stat.S_ISREG(python_stat.st_mode):
        return "workspace virtualenv python shim must be a regular file"
    if not os.access(workspace_python, os.X_OK):
        return "workspace virtualenv python shim is not executable"
    try:
        actual_content = workspace_python.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"workspace virtualenv python shim is unreadable: {exc}"
    if actual_content != identity.shim_content:
        return "workspace virtualenv python shim content does not match identity manifest"
    if _shim_sha256(actual_content) != identity.shim_sha256:
        return "workspace virtualenv python shim digest does not match identity manifest"
    try:
        source_path = Path(identity.source_realpath)
        source_stat = source_path.lstat()
    except OSError as exc:
        return f"trusted workspace python source is unreadable: {exc}"
    if int(source_stat.st_dev) != identity.source_device or int(source_stat.st_ino) != identity.source_inode:
        return "trusted workspace python source identity changed since workspace provisioning"
    if not stat.S_ISREG(source_stat.st_mode):
        return "trusted workspace python source is not a regular file"
    try:
        source_sha256 = _file_sha256(source_path)
    except OSError as exc:
        return f"trusted workspace python source is unreadable: {exc}"
    if source_sha256 != identity.source_sha256:
        return "trusted workspace python source digest changed since workspace provisioning"
    return ""
