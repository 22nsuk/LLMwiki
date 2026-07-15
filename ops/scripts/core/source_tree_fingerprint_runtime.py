from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, NamedTuple

from ops.scripts.eval.wiki_manifest import (
    DEFAULT_EXCLUDED_FILES,
    DEFAULT_EXCLUDED_PREFIXES,
    exclusion_policy,
    should_descend as release_manifest_should_descend,
    should_include as release_manifest_should_include,
)

DEFAULT_RELEASE_MANIFEST_PATH = "ops/manifest.json"
DEFAULT_SOURCE_TREE_CHANGE_PATH_LIMIT = 10

# Note: Scratch and diagnostic directories (tmp/, ops/reports/, runs/, etc.)
# are already excluded from release source tree fingerprinting via
# DEFAULT_EXCLUDED_PREFIXES imported from wiki_manifest.py.
# tests/test_source_tree_fingerprint_runtime.py verifies this exclusion.


class _FileEntry(NamedTuple):
    path: str
    rel_path: str
    size: int
    mtime_ns: int
    ctime_ns: int


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def release_source_tree_fingerprint(
    vault: Path,
    *,
    extra_excluded_files: tuple[str, ...] = (),
    included_prefixes: tuple[str, ...] = (),
) -> str:
    resolved_vault = vault.resolve()
    normalized_included_prefixes = _normalized_included_prefixes(included_prefixes)
    extra_excluded = _effective_extra_excluded_files(
        extra_excluded_files,
        included_prefixes=normalized_included_prefixes,
    )
    manifest, _signature = _build_release_source_manifest(
        resolved_vault,
        hash_files=True,
        extra_excluded_files=extra_excluded,
        included_prefixes=normalized_included_prefixes,
    )
    return _sha256_json(manifest)


def release_source_tree_change_sample(
    vault: Path,
    *,
    generated_at: str,
    extra_excluded_files: tuple[str, ...] = (),
    included_prefixes: tuple[str, ...] = (),
    path_limit: int = DEFAULT_SOURCE_TREE_CHANGE_PATH_LIMIT,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    normalized_included_prefixes = _normalized_included_prefixes(included_prefixes)
    extra_excluded = _effective_extra_excluded_files(
        extra_excluded_files,
        included_prefixes=normalized_included_prefixes,
    )
    generated_dt = _parse_iso_z(generated_at)
    entries = _iter_release_source_entries(
        resolved_vault.as_posix(),
        "",
        _release_source_excluded_files(extra_excluded),
        normalized_included_prefixes,
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


def release_source_tree_divergence_diagnostics(
    vault: Path,
    components: list[dict[str, Any]],
    *,
    current_source_tree_fingerprint: str,
    path_limit: int = DEFAULT_SOURCE_TREE_CHANGE_PATH_LIMIT,
) -> dict[str, Any]:
    normalized_limit = max(0, int(path_limit))
    diagnostics: list[dict[str, Any]] = []
    for item in components:
        if item.get("load_status") != "ok":
            continue
        source_tree_fingerprint = str(item.get("source_tree_fingerprint", "")).strip()
        modified_after_generated_at = bool(item.get("modified_after_generated_at"))
        matches_current_source_tree_fingerprint = (
            bool(source_tree_fingerprint)
            and source_tree_fingerprint == current_source_tree_fingerprint
        )
        if matches_current_source_tree_fingerprint and not modified_after_generated_at:
            continue
        sample = release_source_tree_change_sample(
            vault,
            generated_at=str(item.get("generated_at", "")).strip(),
            path_limit=normalized_limit,
        )
        diagnostics.append(
            {
                "name": str(item.get("name", "")).strip(),
                "path": str(item.get("path", "")).strip(),
                "generated_at": str(item.get("generated_at", "")).strip(),
                "source_tree_fingerprint": source_tree_fingerprint,
                "matches_current_source_tree_fingerprint": matches_current_source_tree_fingerprint,
                "modified_after_generated_at": modified_after_generated_at,
                "changed_after_generated_at_count": int(sample["changed_after_generated_at_count"]),
                "changed_after_generated_at": list(sample["changed_after_generated_at"]),
            }
        )
    return {
        "path_limit": normalized_limit,
        "components": diagnostics,
    }


def _build_release_source_manifest(
    vault: Path,
    *,
    hash_files: bool,
    extra_excluded_files: tuple[str, ...] = (),
    included_prefixes: tuple[str, ...] = (),
) -> tuple[dict[str, Any], tuple[tuple[str, int, int, int], ...]]:
    excluded_files = _release_source_excluded_files(extra_excluded_files)
    files: list[dict[str, Any]] = []
    entries = _iter_release_source_entries(
        vault.as_posix(),
        "",
        excluded_files,
        included_prefixes,
    )
    signature = [(entry.rel_path, entry.size, entry.mtime_ns, entry.ctime_ns) for entry in entries]
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
            "included_prefixes": list(included_prefixes),
        },
    }
    return manifest, tuple(signature)


def _normalized_extra_excluded_files(extra_excluded_files: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(str(path).strip("/") for path in extra_excluded_files if str(path).strip("/")))


def _normalized_included_prefixes(included_prefixes: tuple[str, ...]) -> tuple[str, ...]:
    normalized = {
        str(prefix).strip("/")
        for prefix in included_prefixes
        if str(prefix).strip("/")
    }
    return tuple(sorted(normalized))


def _effective_extra_excluded_files(
    extra_excluded_files: tuple[str, ...],
    *,
    included_prefixes: tuple[str, ...] = (),
) -> tuple[str, ...]:
    base_excluded_files = set(DEFAULT_EXCLUDED_FILES)
    base_excluded_files.add(DEFAULT_RELEASE_MANIFEST_PATH)
    return tuple(
        rel_path
        for rel_path in _normalized_extra_excluded_files(extra_excluded_files)
        if _should_include(rel_path, base_excluded_files, included_prefixes)
    )


def _release_source_excluded_files(extra_excluded_files: tuple[str, ...]) -> set[str]:
    excluded_files = set(DEFAULT_EXCLUDED_FILES)
    excluded_files.add(DEFAULT_RELEASE_MANIFEST_PATH)
    excluded_files.update(_effective_extra_excluded_files(extra_excluded_files))
    return excluded_files


def _iter_release_source_entries(
    root: str,
    rel_root: str,
    excluded_files: set[str],
    included_prefixes: tuple[str, ...],
) -> list[_FileEntry]:
    entries: list[_FileEntry] = []
    try:
        with os.scandir(root) as iterator:
            dir_entries = sorted(iterator, key=lambda entry: entry.name)
    except OSError:
        return entries
    for entry in dir_entries:
        rel_path = f"{rel_root}/{entry.name}" if rel_root else entry.name
        try:
            if entry.is_dir(follow_symlinks=False):
                if _should_descend(rel_path, included_prefixes):
                    entries.extend(
                        _iter_release_source_entries(
                            entry.path,
                            rel_path,
                            excluded_files,
                            included_prefixes,
                        )
                    )
                continue
            if not entry.is_file(follow_symlinks=False) or not _should_include(
                rel_path,
                excluded_files,
                included_prefixes,
            ):
                continue
            stat = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        entries.append(
            _FileEntry(
                entry.path,
                rel_path,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
            )
        )
    return entries


def _matches_included_prefixes(rel_path: str, included_prefixes: tuple[str, ...]) -> bool:
    if not included_prefixes:
        return True
    return any(rel_path == prefix or rel_path.startswith(f"{prefix}/") for prefix in included_prefixes)


def _should_include(
    rel_path: str,
    excluded_files: set[str],
    included_prefixes: tuple[str, ...] = (),
) -> bool:
    if not release_manifest_should_include(
        rel_path,
        excluded_files,
        DEFAULT_EXCLUDED_PREFIXES,
    ):
        return False
    return _matches_included_prefixes(rel_path, included_prefixes)


def _directory_may_contain_included_paths(
    rel_dir: str,
    included_prefixes: tuple[str, ...],
) -> bool:
    if not included_prefixes:
        return True
    return any(
        prefix == rel_dir
        or prefix.startswith(f"{rel_dir}/")
        or rel_dir.startswith(f"{prefix}/")
        for prefix in included_prefixes
    )


def _should_descend(rel_dir: str, included_prefixes: tuple[str, ...] = ()) -> bool:
    if not release_manifest_should_descend(rel_dir, DEFAULT_EXCLUDED_PREFIXES):
        return False
    return _directory_may_contain_included_paths(rel_dir, included_prefixes)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
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
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _mtime_ns_datetime(value: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(value / 1_000_000_000, tz=dt.UTC)


def _isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def producer_input_fingerprint(payload: dict[str, Any]) -> str:
    input_fingerprints = payload.get("input_fingerprints")
    if not isinstance(input_fingerprints, dict):
        return ""
    normalized = {str(key): str(value) for key, value in input_fingerprints.items()}
    return _sha256_json(normalized)
