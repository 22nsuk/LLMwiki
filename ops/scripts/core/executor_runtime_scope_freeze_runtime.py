from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

from ops.scripts.core.path_classification_runtime import (
    LOCAL_SOURCE_CONTRACT_FILES,
    PUBLIC_SOURCE_FILES,
    PUBLIC_SOURCE_PREFIXES,
    classify_path,
)

OPS_SCRIPTS_PREFIX = "ops/scripts/"
SCRIPT_OUTPUT_SURFACES_TARGET = "ops/script-output-surfaces.json"
SCRIPT_OUTPUT_SURFACES_MODULE = "ops/scripts/core/script_output_surfaces.py"
WORKER_SOURCE_SNAPSHOT_CATEGORIES = {"public_source", "local_source_contract"}
WORKER_SOURCE_SNAPSHOT_IGNORE_DIRS = {
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
WORKER_SOURCE_SNAPSHOT_IGNORE_SUFFIXES = {".pyc", ".pyo"}


def normalized_scope_rel_paths(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        rel_path = str(value).strip().replace("\\", "/")
        if not rel_path:
            continue
        path = Path(rel_path)
        if path.is_absolute() or ".." in path.parts:
            continue
        normalized.append(rel_path)
    return normalized


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scope_freeze_targets(
    artifact_root: Path,
    scope_freeze_rel: str,
    key: str,
) -> list[str]:
    payload = json.loads((artifact_root / scope_freeze_rel).read_text(encoding="utf-8"))
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        return []
    return normalized_scope_rel_paths(inputs.get(key, []))


def scope_freeze_resolution_paths(
    artifact_root: Path,
    scope_freeze_rel: str,
    key: str,
) -> list[str]:
    payload = json.loads((artifact_root / scope_freeze_rel).read_text(encoding="utf-8"))
    resolution = payload.get("resolution", {})
    if not isinstance(resolution, dict):
        return []
    return normalized_scope_rel_paths(resolution.get(key, []))


def primary_targets_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return scope_freeze_targets(artifact_root, scope_freeze_rel, "primary_targets")


def supporting_targets_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return scope_freeze_targets(artifact_root, scope_freeze_rel, "supporting_targets")


def test_files_from_scope_freeze(artifact_root: Path, scope_freeze_rel: str) -> list[str]:
    return scope_freeze_resolution_paths(artifact_root, scope_freeze_rel, "test_files")


def target_digest_snapshot(workspace_root: Path, targets: list[str]) -> dict[str, str | None]:
    snapshot: dict[str, str | None] = {}
    for rel_path in targets:
        path = workspace_root / rel_path
        snapshot[rel_path] = file_digest(path) if path.is_file() else None
    return snapshot


def is_worker_source_snapshot_path(rel_path: str) -> bool:
    return classify_path(rel_path) in WORKER_SOURCE_SNAPSHOT_CATEGORIES


def is_worker_source_snapshot_file(path: Path, rel_path: str) -> bool:
    return (
        path.is_file()
        and path.suffix not in WORKER_SOURCE_SNAPSHOT_IGNORE_SUFFIXES
        and is_worker_source_snapshot_path(rel_path)
    )


def worker_source_digest_snapshot(workspace_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for rel_path in sorted([*PUBLIC_SOURCE_FILES, *LOCAL_SOURCE_CONTRACT_FILES]):
        path = workspace_root / rel_path
        if is_worker_source_snapshot_file(path, rel_path):
            snapshot[rel_path] = file_digest(path)

    for prefix in sorted(PUBLIC_SOURCE_PREFIXES):
        root_rel = prefix.rstrip("/")
        root = workspace_root / root_rel
        if not root.is_dir():
            continue
        for current_root, dir_names, file_names in os.walk(root):
            current = Path(current_root)
            rel_current = current.relative_to(workspace_root).as_posix()
            dir_names[:] = [
                name
                for name in dir_names
                if name not in WORKER_SOURCE_SNAPSHOT_IGNORE_DIRS
                and is_worker_source_snapshot_path(f"{rel_current}/{name}")
            ]
            for file_name in sorted(file_names):
                path = current / file_name
                rel_path = path.relative_to(workspace_root).as_posix()
                if is_worker_source_snapshot_file(path, rel_path):
                    snapshot[rel_path] = file_digest(path)
    return snapshot


def changed_targets(
    before: Mapping[str, str | None],
    after: Mapping[str, str | None],
) -> list[str]:
    return [
        target
        for target in sorted(set(before) | set(after))
        if before.get(target) != after.get(target)
    ]


def should_refresh_script_output_surfaces(
    *,
    changed_primary_targets: list[str],
    supporting_targets: list[str],
) -> bool:
    return (
        SCRIPT_OUTPUT_SURFACES_TARGET in supporting_targets
        and any(target.startswith(OPS_SCRIPTS_PREFIX) for target in changed_primary_targets)
    )
