from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, NamedTuple

from ops.scripts.wiki_manifest import (
    DEFAULT_EXCLUDED_FILES,
    DEFAULT_EXCLUDED_PREFIXES,
    DEFAULT_EXCLUDED_SEGMENTS,
    DEFAULT_EXCLUDED_SUFFIXES,
    exclusion_policy,
)


DEFAULT_RELEASE_MANIFEST_PATH = "ops/manifest.json"
DEFAULT_SOURCE_TREE_CHANGE_PATH_LIMIT = 10
_SOURCE_TREE_CACHE: dict[tuple[str, tuple[str, ...]], tuple[tuple[tuple[str, int, int], ...], str]] = {}

# Note: Scratch and diagnostic directories (tmp/, ops/reports/, runs/, etc.)
# are already excluded from release source tree fingerprinting via
# DEFAULT_EXCLUDED_PREFIXES imported from wiki_manifest.py.
# tests/test_source_tree_fingerprint_runtime.py verifies this exclusion.


class _FileEntry(NamedTuple):
    path: str
    rel_path: str
    size: int
    mtime_ns: int


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def release_source_tree_fingerprint(vault: Path, *, extra_excluded_files: tuple[str, ...] = ()) -> str:
    resolved_vault = vault.resolve()
    extra_excluded = _normalized_extra_excluded_files(extra_excluded_files)
    _, signature = _build_release_source_manifest(
        resolved_vault,
        hash_files=False,
        extra_excluded_files=extra_excluded,
    )
    cache_key = (resolved_vault.as_posix(), extra_excluded)
    cached = _SOURCE_TREE_CACHE.get(cache_key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    manifest, signature = _build_release_source_manifest(
        resolved_vault,
        hash_files=True,
        extra_excluded_files=extra_excluded,
    )
    fingerprint = _sha256_json(manifest)
    _SOURCE_TREE_CACHE[cache_key] = (signature, fingerprint)
    return fingerprint


def release_source_tree_change_sample(
    vault: Path,
    *,
    generated_at: str,
    extra_excluded_files: tuple[str, ...] = (),
    path_limit: int = DEFAULT_SOURCE_TREE_CHANGE_PATH_LIMIT,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    extra_excluded = _normalized_extra_excluded_files(extra_excluded_files)
    generated_dt = _parse_iso_z(generated_at)
    entries = _iter_release_source_entries(
        resolved_vault.as_posix(),
        "",
        _release_source_excluded_files(extra_excluded),
    )
    changed_after_generated_at: list[dict[str, str]] = []
    if generated_dt is not None:
        for entry in entries:
            mtime_dt = _mtime_ns_datetime(entry.mtime_ns)
            if mtime_dt <= generated_dt:
                continue
            changed_after_generated_at.append(
                {
                    "path": entry.rel_path,
                    "mtime": _isoformat_z(mtime_dt),
                }
            )
    changed_after_generated_at.sort(key=lambda item: (item["mtime"], item["path"]))
    normalized_limit = max(0, int(path_limit))
    return {
        "changed_after_generated_at_count": len(changed_after_generated_at),
        "changed_after_generated_at_path_limit": normalized_limit,
        "changed_after_generated_at": changed_after_generated_at[:normalized_limit],
    }


def _build_release_source_manifest(
    vault: Path,
    *,
    hash_files: bool,
    extra_excluded_files: tuple[str, ...] = (),
) -> tuple[dict[str, Any], tuple[tuple[str, int, int], ...]]:
    excluded_files = _release_source_excluded_files(extra_excluded_files)
    files: list[dict[str, Any]] = []
    entries = _iter_release_source_entries(vault.as_posix(), "", excluded_files)
    signature = [(entry.rel_path, entry.size, entry.mtime_ns) for entry in entries]
    for entry in entries:
        if hash_files:
            files.append(
                {
                    "path": entry.rel_path,
                    "sha256": _sha256_file(entry.path),
                    "size_bytes": entry.size,
                }
            )
    files.sort(key=lambda item: str(item["path"]))
    manifest = {
        "files": files,
        "exclusion_policy": {
            **exclusion_policy(),
            "excluded_files": sorted(excluded_files),
        },
    }
    return manifest, tuple(signature)


def _normalized_extra_excluded_files(extra_excluded_files: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(str(path).strip("/") for path in extra_excluded_files if str(path).strip("/")))


def _release_source_excluded_files(extra_excluded_files: tuple[str, ...]) -> set[str]:
    excluded_files = set(DEFAULT_EXCLUDED_FILES)
    excluded_files.add(DEFAULT_RELEASE_MANIFEST_PATH)
    excluded_files.update(extra_excluded_files)
    return excluded_files


def _iter_release_source_entries(root: str, rel_root: str, excluded_files: set[str]) -> list[_FileEntry]:
    entries: list[_FileEntry] = []
    try:
        with os.scandir(root) as iterator:
            dir_entries = sorted(list(iterator), key=lambda entry: entry.name)
    except OSError:
        return entries
    for entry in dir_entries:
        rel_path = f"{rel_root}/{entry.name}" if rel_root else entry.name
        try:
            if entry.is_dir(follow_symlinks=False):
                if _should_descend(rel_path):
                    entries.extend(_iter_release_source_entries(entry.path, rel_path, excluded_files))
                continue
            if not entry.is_file(follow_symlinks=False) or not _should_include(rel_path, excluded_files):
                continue
            stat = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        entries.append(_FileEntry(entry.path, rel_path, stat.st_size, stat.st_mtime_ns))
    return entries


def _should_include(rel_path: str, excluded_files: set[str]) -> bool:
    if rel_path in excluded_files:
        return False
    if any(rel_path.startswith(prefix) for prefix in DEFAULT_EXCLUDED_PREFIXES):
        return False
    if rel_path.endswith(DEFAULT_EXCLUDED_SUFFIXES):
        return False
    return not any(part in DEFAULT_EXCLUDED_SEGMENTS or part.endswith(".egg-info") for part in rel_path.split("/"))


def _should_descend(rel_dir: str) -> bool:
    rel_dir_prefix = f"{rel_dir}/"
    if any(rel_dir_prefix.startswith(prefix) for prefix in DEFAULT_EXCLUDED_PREFIXES):
        return False
    return not any(part in DEFAULT_EXCLUDED_SEGMENTS or part.endswith(".egg-info") for part in rel_dir.split("/"))


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_iso_z(value: str) -> dt.datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _mtime_ns_datetime(value: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(value / 1_000_000_000, tz=dt.timezone.utc)


def _isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def producer_input_fingerprint(payload: dict[str, Any]) -> str:
    input_fingerprints = payload.get("input_fingerprints")
    if not isinstance(input_fingerprints, dict):
        return ""
    normalized = {str(key): str(value) for key, value in input_fingerprints.items()}
    return _sha256_json(normalized)
