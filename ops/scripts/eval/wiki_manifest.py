#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.path_runtime import normalize_repo_path_text
    from ops.scripts.core.schema_constants_runtime import WIKI_MANIFEST_SCHEMA_PATH
else:
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.path_runtime import normalize_repo_path_text
    from ops.scripts.core.schema_constants_runtime import WIKI_MANIFEST_SCHEMA_PATH

DEFAULT_EXCLUDED_PREFIXES = (
    "ops/reports/",
    "ops/operator/",
    "external-reports/",
    "raw/",
    "wiki/",
    "system/",
    "review/",
    "runs/",
    "tmp/",
    "build/",
    "dist/",
    ".venv/",
    ".venv-",
    ".coverage",
)
DEFAULT_EXCLUDED_CACHE_DIRS = {
    "__pycache__",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
DEFAULT_EXCLUDED_DEV_HIDDEN_DIRS = {
    ".eggs",
    ".git",
    ".hypothesis",
    ".idea",
    ".nox",
    ".obsidian",
    ".tox",
    ".venv",
    ".vscode",
}
DEFAULT_EXCLUDED_SEGMENTS = DEFAULT_EXCLUDED_CACHE_DIRS | DEFAULT_EXCLUDED_DEV_HIDDEN_DIRS
DEFAULT_EXCLUDED_SUFFIXES = (
    ".pyc",
    ".pyo",
    ":Zone.Identifier",
)
DEFAULT_EXCLUDED_FILES = {
    "AGENTS.local.md",
    "ops/manifest.json",
    "ops/raw-registry.json",
    "ops/script-output-surfaces.json",
}
DEFAULT_OUT = "ops/manifest.json"
RELEASE_MANIFEST_PATH_INCLUDED = "included"
RELEASE_MANIFEST_PATH_EXCLUDED = "excluded"
RELEASE_MANIFEST_PATH_INVALID = "invalid"


@dataclass(frozen=True)
class ReleaseManifestPathClassification:
    normalized_path: str
    status: str
    reason: str

    @property
    def valid(self) -> bool:
        return not self.invalid

    @property
    def included(self) -> bool:
        return self.status == RELEASE_MANIFEST_PATH_INCLUDED

    @property
    def excluded(self) -> bool:
        return self.status == RELEASE_MANIFEST_PATH_EXCLUDED

    @property
    def invalid(self) -> bool:
        return self.status == RELEASE_MANIFEST_PATH_INVALID


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def exclusion_policy() -> dict:
    return {
        "name": "release_manifest_exclusions",
        "excluded_prefixes": list(DEFAULT_EXCLUDED_PREFIXES),
        "excluded_files": sorted(DEFAULT_EXCLUDED_FILES),
        "excluded_cache_dirs": sorted(DEFAULT_EXCLUDED_CACHE_DIRS),
        "excluded_dev_hidden_dirs": sorted(DEFAULT_EXCLUDED_DEV_HIDDEN_DIRS),
        "excluded_suffixes": list(DEFAULT_EXCLUDED_SUFFIXES),
        "excluded_egg_info_dirs": True,
    }


def should_include(rel_path: str, excluded_files: set[str], excluded_prefixes: tuple[str, ...]) -> bool:
    if rel_path in excluded_files:
        return False
    if any(rel_path.startswith(prefix) for prefix in excluded_prefixes):
        return False
    if rel_path.endswith(DEFAULT_EXCLUDED_SUFFIXES):
        return False
    return not any(
        part in DEFAULT_EXCLUDED_SEGMENTS or part.endswith(".egg-info")
        for part in Path(rel_path).parts
    )


def should_descend(rel_dir: str, excluded_prefixes: tuple[str, ...]) -> bool:
    rel_dir_prefix = f"{rel_dir}/"
    if any(rel_dir_prefix.startswith(prefix) for prefix in excluded_prefixes):
        return False
    return not any(
        part in DEFAULT_EXCLUDED_SEGMENTS or part.endswith(".egg-info")
        for part in Path(rel_dir).parts
    )


def _looks_like_windows_drive_path(normalized: str) -> bool:
    return len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":"


def _has_parent_reference(rel_path: str | None) -> bool:
    if rel_path is None:
        return False
    text = str(rel_path).strip().replace("\\", "/")
    return any(part == ".." for part in text.split("/"))


def classify_release_manifest_path(rel_path: str | None) -> ReleaseManifestPathClassification:
    normalized = normalize_repo_path_text(rel_path)
    if normalized is None:
        return ReleaseManifestPathClassification(
            normalized_path="",
            status=RELEASE_MANIFEST_PATH_INVALID,
            reason="empty",
        )
    if normalized == ".":
        return ReleaseManifestPathClassification(
            normalized_path=normalized,
            status=RELEASE_MANIFEST_PATH_INVALID,
            reason="repo-root",
        )
    if _has_parent_reference(rel_path):
        return ReleaseManifestPathClassification(
            normalized_path=normalized,
            status=RELEASE_MANIFEST_PATH_INVALID,
            reason="parent-reference",
        )
    if normalized.startswith("/") or _looks_like_windows_drive_path(normalized):
        return ReleaseManifestPathClassification(
            normalized_path=normalized,
            status=RELEASE_MANIFEST_PATH_INVALID,
            reason="absolute",
        )
    if should_include(normalized, DEFAULT_EXCLUDED_FILES, DEFAULT_EXCLUDED_PREFIXES):
        return ReleaseManifestPathClassification(
            normalized_path=normalized,
            status=RELEASE_MANIFEST_PATH_INCLUDED,
            reason="manifest-included",
        )
    return ReleaseManifestPathClassification(
        normalized_path=normalized,
        status=RELEASE_MANIFEST_PATH_EXCLUDED,
        reason="manifest-excluded",
    )


def release_manifest_excludes_path(rel_path: str | None) -> bool:
    classification = classify_release_manifest_path(rel_path)
    return classification.excluded


def release_manifest_includes_path(rel_path: str | None) -> bool:
    classification = classify_release_manifest_path(rel_path)
    return classification.included


def _is_safe_manifest_file(vault_root: Path, path: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
    except OSError:
        return False
    try:
        path.relative_to(vault_root)
    except ValueError:
        return False
    return True


def _iter_candidate_files(
    vault: Path,
    *,
    excluded_files: set[str],
    excluded_prefixes: tuple[str, ...],
) -> Iterator[tuple[Path, str]]:
    for root, dirnames, filenames in os.walk(vault, followlinks=False):
        root_path = Path(root)
        kept_dirnames = []
        for dirname in dirnames:
            dir_path = root_path / dirname
            rel_dir = dir_path.relative_to(vault).as_posix()
            if not should_descend(rel_dir, excluded_prefixes):
                continue
            try:
                if dir_path.is_symlink():
                    continue
            except OSError:
                continue
            kept_dirnames.append(dirname)
        dirnames[:] = sorted(kept_dirnames)

        for filename in sorted(filenames):
            path = root_path / filename
            rel_path = path.relative_to(vault).as_posix()
            if should_include(rel_path, excluded_files, excluded_prefixes):
                yield path, rel_path


def build_manifest(vault: Path, out_path: Path) -> dict:
    excluded_files = set(DEFAULT_EXCLUDED_FILES)
    with suppress(ValueError):
        excluded_files.add(out_path.relative_to(vault).as_posix())

    files = []
    for p, rel_path in _iter_candidate_files(
        vault,
        excluded_files=excluded_files,
        excluded_prefixes=DEFAULT_EXCLUDED_PREFIXES,
    ):
        if not _is_safe_manifest_file(vault, p):
            continue
        try:
            sha256 = sha256_file(p)
            size_bytes = p.stat().st_size
        except OSError:
            continue
        files.append({
            "path": rel_path,
            "sha256": sha256,
            "size_bytes": size_bytes,
        })
    files.sort(key=lambda item: str(item["path"]))
    return {
        "files": files,
        "exclusion_policy": {
            **exclusion_policy(),
            "excluded_files": sorted(excluded_files),
        },
    }

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    vault = Path(args.vault)
    out_path = resolve_schema_backed_report_output_path(
        vault,
        args.out,
        default_relative_path=DEFAULT_OUT,
    )
    manifest = build_manifest(vault, out_path)
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=WIKI_MANIFEST_SCHEMA_PATH,
            out_path=args.out,
            default_relative_path=DEFAULT_OUT,
            context="wiki release manifest schema validation failed",
            trailing_newline=False,
        )
    )
    print(display_path(vault, destination))

if __name__ == "__main__":
    main()
