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
    shim_sha256: str
    shim_content: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_realpath": self.source_realpath,
            "source_device": self.source_device,
            "source_inode": self.source_inode,
            "shim_sha256": self.shim_sha256,
            "shim_content": self.shim_content,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WorkspacePythonIdentity:
        return cls(
            source_realpath=str(payload.get("source_realpath", "")),
            source_device=int(payload.get("source_device", 0)),
            source_inode=int(payload.get("source_inode", 0)),
            shim_sha256=str(payload.get("shim_sha256", "")),
            shim_content=str(payload.get("shim_content", "")),
        )


def workspace_python_identity_path(workspace_root: Path) -> Path:
    return workspace_root / WORKSPACE_PYTHON_IDENTITY_REL


def _shim_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_workspace_python_identity(*, source_python: Path, shim_content: str) -> WorkspacePythonIdentity:
    resolved = source_python.resolve()
    source_stat = resolved.lstat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("workspace python source must be a regular file")
    return WorkspacePythonIdentity(
        source_realpath=str(resolved),
        source_device=int(source_stat.st_dev),
        source_inode=int(source_stat.st_ino),
        shim_sha256=_shim_sha256(shim_content),
        shim_content=shim_content,
    )


def write_workspace_python_identity(workspace_root: Path, identity: WorkspacePythonIdentity) -> Path:
    path = workspace_python_identity_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity.to_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_workspace_python_identity(workspace_root: Path) -> WorkspacePythonIdentity | None:
    path = workspace_python_identity_path(workspace_root)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return WorkspacePythonIdentity.from_payload(payload)


def verify_workspace_python_shim(
    workspace_root: Path,
    *,
    workspace_python: Path,
    expected_identity: WorkspacePythonIdentity | None = None,
) -> str:
    identity = expected_identity or load_workspace_python_identity(workspace_root)
    if identity is None:
        return "missing workspace python identity manifest"
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
    return ""
