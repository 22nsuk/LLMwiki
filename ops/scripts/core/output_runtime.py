from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re

from .filesystem_runtime import atomic_write_text
from .path_runtime import normalize_repo_path_text, stable_report_path


TEMP_ROOT_RE = re.compile(r"(?<![\w.:-])/tmp/tmp[A-Za-z0-9_.-]+")
HOME_ROOT_RE = re.compile(r"(?<![\w.:-])/home/[^/\s\"']+")


def _coerce_output_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    normalized = normalize_repo_path_text(path.as_posix())
    return Path(normalized) if normalized is not None else path


def resolve_vault_path(vault: Path, raw_path: str | Path) -> Path:
    path = _coerce_output_path(raw_path)
    if path.is_absolute():
        return path
    return (vault / path).resolve()


def resolve_output_path(
    vault: Path,
    out_path: str | Path | None,
    *,
    default_relative_path: str | None = None,
) -> Path:
    if out_path:
        return resolve_vault_path(vault, out_path)
    if default_relative_path is None:
        raise ValueError("default_relative_path is required when out_path is not provided")
    return resolve_vault_path(vault, default_relative_path)


def resolve_repo_output_path(
    vault: Path,
    out_path: str | Path | None,
    *,
    default_relative_path: str | None = None,
) -> Path:
    raw_path: str | Path | None = out_path or default_relative_path
    if raw_path is None:
        raise ValueError("default_relative_path is required when out_path is not provided")
    vault_root = vault.resolve()
    path = _coerce_output_path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (vault_root / path).resolve()
    if not resolved.is_relative_to(vault_root):
        raise ValueError(
            "repo output path must stay under vault: "
            f"{resolved.as_posix()}"
        )
    return resolved


def display_path(vault: Path, path: Path) -> str:
    return stable_report_path(vault, path)


def sanitize_report_text(
    vault: Path,
    text: str,
    *,
    temp_roots: Sequence[Path] = (),
) -> str:
    sanitized = str(text).replace("\\", "/")
    vault_text = vault.resolve().as_posix()
    sanitized = sanitized.replace(f"{vault_text}/", "")
    sanitized = sanitized.replace(vault_text, ".")
    for root in temp_roots:
        root_text = root.resolve().as_posix()
        sanitized = sanitized.replace(f"{root_text}/", "<tmp>/")
        sanitized = sanitized.replace(root_text, "<tmp>")
    sanitized = TEMP_ROOT_RE.sub("<tmp>", sanitized)
    return HOME_ROOT_RE.sub("<home>", sanitized)


def write_output_text(path: Path, text: str) -> Path:
    return atomic_write_text(path, text)
