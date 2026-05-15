from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_io_runtime import read_json_object, write_vault_schema_validated_json


def load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return read_json_object(path)
    except (OSError, ValueError):
        return None


def write_schema_backed_json(
    vault: Path,
    rel_path: str,
    payload: dict,
    schema_rel_path: str,
    *,
    context: str,
) -> str:
    return write_vault_schema_validated_json(
        vault,
        rel_path,
        payload,
        schema_rel_path,
        context=context,
    )


def increment(counter: dict[str, int], key: object) -> None:
    text = "" if key is None else str(key).strip()
    if not text:
        return
    counter[text] = counter.get(text, 0) + 1


def run_rel(run_id: str, filename: str) -> str:
    return f"runs/{run_id}/{filename}"


def _repo_rel_path(vault: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(vault.resolve()).as_posix()
    except ValueError:
        return ""


def run_dir_candidates(vault: Path, run_id: str) -> list[Path]:
    run_id = str(run_id).strip()
    if not run_id:
        return []
    candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in (vault / "runs" / run_id, vault / "runs" / "archive" / run_id):
        resolved = candidate.resolve()
        if candidate.is_dir() and resolved not in seen:
            candidates.append(candidate)
            seen.add(resolved)
    archive_root = vault / "runs" / "archive"
    if archive_root.is_dir():
        for candidate in sorted(path for path in archive_root.rglob("*") if path.is_dir() and path.name == run_id):
            resolved = candidate.resolve()
            if resolved not in seen:
                candidates.append(candidate)
                seen.add(resolved)
    return candidates


def resolve_run_artifact_rel(vault: Path, run_id: str, filename: str) -> str:
    for run_dir in run_dir_candidates(vault, run_id):
        candidate = run_dir / filename
        if candidate.is_file():
            return _repo_rel_path(vault, candidate)
    return ""


def run_artifact_glob_rels(vault: Path, run_id: str, pattern: str) -> list[str]:
    rel_paths: list[str] = []
    seen: set[str] = set()
    for run_dir in run_dir_candidates(vault, run_id):
        for path in sorted(run_dir.glob(pattern)):
            if not path.is_file():
                continue
            rel_path = _repo_rel_path(vault, path)
            if rel_path and rel_path not in seen:
                rel_paths.append(rel_path)
                seen.add(rel_path)
    return rel_paths


def list_strings_any(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def dict_value(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
