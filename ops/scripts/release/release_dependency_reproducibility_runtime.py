from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

DEPENDENCY_REPRODUCIBILITY_FILES = (
    "pyproject.toml",
    "uv.lock",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependency_reproducibility_record(vault: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for rel_path in DEPENDENCY_REPRODUCIBILITY_FILES:
        path = vault / rel_path
        exists = path.is_file()
        files.append(
            {
                "path": rel_path,
                "exists": exists,
                "sha256": _sha256_file(path) if exists else "",
                "canonical_lockfile": rel_path == "uv.lock",
            }
        )
    canonical = next(item for item in files if item["canonical_lockfile"])
    present_files = [item for item in files if item["exists"]]
    combined = hashlib.sha256()
    for item in sorted(present_files, key=lambda value: str(value["path"])):
        combined.update(str(item["path"]).encode("utf-8"))
        combined.update(b"\0")
        combined.update(str(item["sha256"]).encode("utf-8"))
        combined.update(b"\0")
    dependency_fingerprint = combined.hexdigest() if present_files else ""
    status = "locked" if canonical["exists"] else "missing_lockfile"
    return {
        "schema_version": 1,
        "status": status,
        "canonical_lockfile_path": "uv.lock",
        "canonical_lockfile_sha256": canonical["sha256"],
        "dependency_fingerprint": dependency_fingerprint,
        "dependency_files": files,
        "range_latest_lane": "advisory_only",
        "replay_contract": "source_tree_fingerprint + dependency_fingerprint",
        "summary": (
            f"dependency_reproducibility status={status}; "
            f"canonical_lockfile=uv.lock; "
            f"dependency_file_count={len(present_files)}"
        ),
    }
