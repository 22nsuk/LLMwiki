from __future__ import annotations

import posixpath
import unicodedata
from functools import lru_cache
from pathlib import Path


def normalize_repo_path_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = unicodedata.normalize("NFC", str(value).strip())
    if not text:
        return None

    text = text.replace("\\", "/")
    normalized = posixpath.normpath(text)
    return unicodedata.normalize("NFC", normalized)


def _absolute_from_cwd(path: Path, cwd: Path) -> Path:
    return path if path.is_absolute() else cwd / path


@lru_cache(maxsize=16384)
def _path_has_symlink_between(vault_text: str, path_text: str) -> bool:
    absolute_vault = Path(vault_text)
    absolute_path = Path(path_text)
    try:
        relative = absolute_path.relative_to(absolute_vault)
    except ValueError:
        return True

    probe = absolute_vault
    for part in relative.parts:
        probe = probe / part
        if probe.is_symlink():
            return True
    return False


def _fast_relative_report_path(vault: Path, path: Path, cwd: Path) -> str | None:
    absolute_vault = _absolute_from_cwd(vault, cwd)
    absolute_path = path if path.is_absolute() else absolute_vault / path
    try:
        relative = absolute_path.relative_to(absolute_vault)
    except ValueError:
        return None

    normalized = normalize_repo_path_text(relative.as_posix())
    if normalized is None or normalized == ".." or normalized.startswith("../"):
        return None
    if _path_has_symlink_between(absolute_vault.as_posix(), absolute_path.as_posix()):
        return None
    return normalized


@lru_cache(maxsize=16384)
def _stable_report_path_cached(cwd_text: str, vault_text: str, path_text: str) -> str:
    cwd = Path(cwd_text)
    vault = Path(vault_text)
    path = Path(path_text)

    fast_relative = _fast_relative_report_path(vault, path, cwd)
    if fast_relative is not None:
        return fast_relative

    resolved_vault = _absolute_from_cwd(vault, cwd).resolve()
    resolved_path = _absolute_from_cwd(path, cwd).resolve()
    try:
        relative = resolved_path.relative_to(resolved_vault).as_posix()
        return unicodedata.normalize("NFC", relative)
    except ValueError:
        return unicodedata.normalize("NFC", resolved_path.as_posix().replace("\\", "/"))


def stable_report_path(vault: Path, path: Path) -> str:
    return _stable_report_path_cached(
        Path.cwd().as_posix(),
        vault.as_posix(),
        path.as_posix(),
    )
