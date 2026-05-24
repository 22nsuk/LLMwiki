from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ops.scripts.public.export_public_repo import should_export_public


@dataclass(frozen=True)
class PublicMirrorBoundaryError(ValueError):
    path: str
    vault: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path} is outside the public mirror boundary: {self.reason}"


def repo_relative_path(vault: Path, path: str | Path) -> str:
    resolved_vault = vault.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = resolved_vault / candidate
    resolved_candidate = candidate.resolve(strict=False)
    try:
        return resolved_candidate.relative_to(resolved_vault).as_posix()
    except ValueError as exc:
        raise PublicMirrorBoundaryError(
            path=str(path),
            vault=resolved_vault.as_posix(),
            reason="path_escapes_vault",
        ) from exc


def assert_within_public_mirror(vault: Path, path: str | Path) -> str:
    rel_path = repo_relative_path(vault, path)
    if should_export_public(rel_path):
        return rel_path
    raise PublicMirrorBoundaryError(
        path=rel_path,
        vault=vault.resolve().as_posix(),
        reason="not_exported_by_public_surface_policy",
    )


def is_within_public_mirror(vault: Path, path: str | Path) -> bool:
    try:
        assert_within_public_mirror(vault, path)
    except PublicMirrorBoundaryError:
        return False
    return True
