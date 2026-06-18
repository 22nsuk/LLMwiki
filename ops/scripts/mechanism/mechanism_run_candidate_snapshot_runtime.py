from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ops.scripts.core.path_runtime import normalize_repo_path_text
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH,
)

from .mechanism_run_common_runtime import (
    RunMechanismExperimentUsageError,
    load_json,
    timestamp,
    write_json,
)
from .mechanism_run_ledger_runtime import run_rel

CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA = CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH
CANDIDATE_CHANGED_FILES_SNAPSHOT_FILENAME = "candidate-changed-files-snapshot.json"
MAX_CAPTURE_BYTES_PER_FILE = 512 * 1024


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_manifest_path(value: object) -> str:
    normalized = normalize_repo_path_text(str(value))
    if (
        normalized is None
        or normalized in {".", ".."}
        or normalized.startswith(("../", "/"))
    ):
        raise RunMechanismExperimentUsageError(f"invalid changed file path in manifest: {value}")
    return normalized


def _file_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"exists": False, "sha256": "", "size_bytes": 0}
    return {
        "exists": True,
        "sha256": _file_digest(path),
        "size_bytes": path.stat().st_size,
    }


def _candidate_state(path: Path) -> tuple[dict[str, object], dict[str, str]]:
    state = _file_state(path)
    if not state["exists"]:
        return state, {"status": "metadata_only", "reason": "candidate_deleted"}
    size_raw = state["size_bytes"]
    size_bytes = size_raw if isinstance(size_raw, int) else 0
    if size_bytes > MAX_CAPTURE_BYTES_PER_FILE:
        return state, {"status": "omitted", "reason": "file_too_large"}

    content = path.read_bytes()
    if b"\x00" in content:
        return state, {"status": "omitted", "reason": "binary_file"}
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return state, {"status": "omitted", "reason": "non_utf8_file"}

    captured = dict(state)
    captured["content_encoding"] = "utf-8"
    captured["content_utf8"] = text
    return captured, {"status": "captured", "reason": ""}


def _snapshot_file_entry(
    vault: Path,
    workspace_vault: Path,
    manifest_entry: dict[str, Any],
) -> dict[str, object]:
    rel_path = _normalized_manifest_path(manifest_entry.get("path", ""))
    change_type = str(manifest_entry.get("change_type", "")).strip()
    candidate, capture = _candidate_state(workspace_vault / rel_path)
    return {
        "path": rel_path,
        "change_type": change_type,
        "baseline": _file_state(vault / rel_path),
        "candidate": candidate,
        "capture": capture,
    }


def _snapshot_summary(files: list[dict[str, object]]) -> dict[str, int]:
    counts = {"added": 0, "modified": 0, "deleted": 0}
    captured_text_files = 0
    metadata_only_files = 0
    omitted_files = 0
    captured_text_bytes = 0
    for file_entry in files:
        change_type = str(file_entry["change_type"])
        counts[change_type] = counts.get(change_type, 0) + 1
        capture = file_entry["capture"]
        if not isinstance(capture, dict):
            continue
        status = str(capture.get("status", ""))
        if status == "captured":
            captured_text_files += 1
            candidate = file_entry["candidate"]
            if isinstance(candidate, dict):
                captured_text_bytes += int(candidate.get("size_bytes", 0))
        elif status == "metadata_only":
            metadata_only_files += 1
        elif status == "omitted":
            omitted_files += 1

    return {
        "total_changed_files": len(files),
        "added": counts["added"],
        "modified": counts["modified"],
        "deleted": counts["deleted"],
        "captured_text_files": captured_text_files,
        "metadata_only_files": metadata_only_files,
        "omitted_files": omitted_files,
        "captured_text_bytes": captured_text_bytes,
        "max_capture_bytes_per_file": MAX_CAPTURE_BYTES_PER_FILE,
    }


def write_candidate_changed_files_snapshot(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    changed_files_manifest: str,
    decision: str,
    apply_mode: str,
    apply_status: str,
    live_applied: bool,
    capture_reason: str,
    context: RuntimeContext | None = None,
) -> str:
    manifest = load_json(vault / changed_files_manifest)
    manifest_files = [
        entry for entry in manifest.get("files", []) if isinstance(entry, dict)
    ]
    if not manifest_files or live_applied:
        return ""

    files = [_snapshot_file_entry(vault, workspace_vault, entry) for entry in manifest_files]
    payload = {
        "$schema": CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA,
        "run_id": run_id,
        "generated_at": timestamp(context),
        "changed_files_manifest": changed_files_manifest,
        "changed_files_manifest_sha256": _file_digest(vault / changed_files_manifest),
        "decision": decision,
        "apply_mode": apply_mode,
        "apply_status": apply_status,
        "live_applied": live_applied,
        "capture_reason": capture_reason,
        "changed_files_summary": manifest.get("summary", {}),
        "summary": _snapshot_summary(files),
        "files": files,
    }
    diff_universe = manifest.get("diff_universe")
    if isinstance(diff_universe, dict):
        payload["diff_universe"] = diff_universe
    snapshot_rel = run_rel(run_id, CANDIDATE_CHANGED_FILES_SNAPSHOT_FILENAME)
    write_json(
        vault,
        snapshot_rel,
        payload,
        CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA,
    )
    return snapshot_rel
