from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .path_runtime import normalize_repo_path_text


class FilesystemTransactionError(OSError):
    pass


SHADOW_APPLY_REPORT_SCHEMA = "ops/schemas/shadow-apply-report.schema.json"
ROLLBACK_REHEARSAL_REPORT_SCHEMA = "ops/schemas/rollback-rehearsal-report.schema.json"


@dataclass(frozen=True)
class AtomicTextUpdate:
    path: Path
    text: str


AtomicTextUpdateSpec = AtomicTextUpdate | dict[str, Any] | tuple[Path | str, str]


@dataclass(frozen=True)
class AllowedApplyRoot:
    normalized_path: str
    prefix_match: bool


@dataclass(frozen=True)
class ManifestApplyGuardState:
    allowed_apply_roots: list[str]
    changed_paths: list[str]
    invalid_paths: list[str]
    disallowed_paths: list[str]


@dataclass
class _AtomicWriteState:
    path: Path
    text: str
    original_text: str | None
    staged_path: Path | None = None


def _existing_text_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _stage_atomic_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:  # broad-exception: platform_cleanup_boundary
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            Path(staged_path).unlink()
        except FileNotFoundError:
            pass
        raise
    return Path(staged_path)


def _cleanup_staged_file(staged_path: Path | None) -> None:
    if staged_path is None:
        return
    try:
        staged_path.unlink()
    except FileNotFoundError:
        return


def _restore_text_update(path: Path, original_text: str | None) -> None:
    if original_text is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        return
    staged_path = _stage_atomic_text(path, original_text)
    try:
        os.replace(staged_path, path)
    finally:
        _cleanup_staged_file(staged_path)


def atomic_write_text(path: Path, text: str) -> Path:
    staged_path: Path | None = None
    try:
        staged_path = _stage_atomic_text(path, text)
        os.replace(staged_path, path)
    except OSError as exc:
        raise FilesystemTransactionError(str(exc)) from exc
    finally:
        _cleanup_staged_file(staged_path)
    return path


def atomic_write_json(path: Path, payload: Any) -> Path:
    return atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _canonical_atomic_target(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def _coerce_atomic_text_update(update: AtomicTextUpdateSpec) -> AtomicTextUpdate:
    if isinstance(update, AtomicTextUpdate):
        return update
    if isinstance(update, tuple):
        path, text = update
        return AtomicTextUpdate(path=Path(path), text=str(text))
    return AtomicTextUpdate(path=Path(update["path"]), text=str(update["text"]))


def build_atomic_text_updates(updates: Sequence[AtomicTextUpdateSpec]) -> list[AtomicTextUpdate]:
    normalized: list[AtomicTextUpdate] = []
    canonical_targets: dict[str, list[str]] = {}
    for update in updates:
        normalized_update = _coerce_atomic_text_update(update)
        display_path = normalized_update.path.as_posix()
        canonical_target = _canonical_atomic_target(normalized_update.path)
        canonical_targets.setdefault(canonical_target, []).append(display_path)
        normalized.append(normalized_update)

    duplicate_targets = sorted(
        {
            display_path
            for display_paths in canonical_targets.values()
            if len(display_paths) > 1
            for display_path in display_paths
        }
    )
    if duplicate_targets:
        raise FilesystemTransactionError(
            "atomic_multi_write received duplicate target paths: "
            + ", ".join(duplicate_targets)
        )
    return normalized


def atomic_multi_write(updates: Sequence[AtomicTextUpdateSpec]) -> None:
    normalized = [
        _AtomicWriteState(
            path=update.path,
            text=update.text,
            original_text=_existing_text_or_none(update.path),
        )
        for update in build_atomic_text_updates(updates)
    ]

    staged_updates: list[_AtomicWriteState] = []
    committed_updates: list[_AtomicWriteState] = []
    try:
        for update in normalized:
            update.staged_path = _stage_atomic_text(update.path, update.text)
            staged_updates.append(update)
        for update in normalized:
            if update.staged_path is None:
                continue
            os.replace(update.staged_path, update.path)
            update.staged_path = None
            committed_updates.append(update)
    except OSError as exc:
        rollback_errors: list[str] = []
        for update in reversed(committed_updates):
            try:
                _restore_text_update(update.path, update.original_text)
            except OSError as rollback_exc:
                rollback_errors.append(f"{update.path.as_posix()}: {rollback_exc}")
        for update in staged_updates:
            _cleanup_staged_file(update.staged_path)
        detail = str(exc)
        if rollback_errors:
            detail += " | rollback issues: " + "; ".join(rollback_errors)
        raise FilesystemTransactionError(detail) from exc
    finally:
        for update in staged_updates:
            _cleanup_staged_file(update.staged_path)


def stage_replace_file(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_path = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=destination_path.parent,
    )
    os.close(fd)
    staged = Path(staged_path)
    backup_path: Path | None = None
    try:
        shutil.copy2(source_path, staged)
        if destination_path.exists():
            fd, backup_tmp = tempfile.mkstemp(
                prefix=f".{destination_path.name}.",
                suffix=".bak",
                dir=destination_path.parent,
            )
            os.close(fd)
            backup_path = Path(backup_tmp)
            shutil.copy2(destination_path, backup_path)
        os.replace(staged, destination_path)
    except OSError as exc:
        if backup_path is not None and backup_path.exists():
            try:
                os.replace(backup_path, destination_path)
            except OSError:
                pass
        raise FilesystemTransactionError(str(exc)) from exc
    finally:
        _cleanup_staged_file(staged)
        _cleanup_staged_file(backup_path)


def _remove_empty_parent_dirs(path: Path, *, stop_at: Path) -> None:
    current = path.parent
    resolved_stop = stop_at.resolve()
    while current != resolved_stop and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _normalize_manifest_repo_path(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("\\", "/")
    if not raw or Path(raw).is_absolute():
        return None
    normalized = normalize_repo_path_text(raw)
    if normalized is None or normalized in {".", ".."} or normalized.startswith("../"):
        return None
    return normalized


def _parse_allowed_apply_root(value: str) -> AllowedApplyRoot:
    if not isinstance(value, str):
        raise ValueError("allowed_apply_roots entries must be strings")
    raw = value.strip().replace("\\", "/")
    if not raw:
        raise ValueError("allowed_apply_roots entries must not be empty")
    prefix_match = raw.endswith("/")
    normalized = _normalize_manifest_repo_path(raw[:-1] if prefix_match else raw)
    if normalized is None:
        raise ValueError(f"invalid allowed_apply_roots entry: {value}")
    return AllowedApplyRoot(
        normalized_path=normalized,
        prefix_match=prefix_match,
    )


def normalized_allowed_apply_roots(allowed_apply_roots: Sequence[str]) -> list[str]:
    normalized_roots: list[str] = []
    seen: set[str] = set()
    for value in allowed_apply_roots:
        root = _parse_allowed_apply_root(value)
        canonical = (
            f"{root.normalized_path}/"
            if root.prefix_match
            else root.normalized_path
        )
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized_roots.append(canonical)
    return normalized_roots


def _path_matches_allowed_apply_root(path: str, root: AllowedApplyRoot) -> bool:
    if root.prefix_match:
        return path == root.normalized_path or path.startswith(f"{root.normalized_path}/")
    return path == root.normalized_path


def _path_has_symlink_segments(root: Path, repo_relative_path: str) -> bool:
    probe = root
    for part in Path(repo_relative_path).parts:
        probe = probe / part
        if probe.is_symlink():
            return True
    return False


def _resolve_manifest_apply_path(
    root: Path,
    repo_relative_path: str,
    *,
    path_label: str,
) -> Path:
    if _path_has_symlink_segments(root, repo_relative_path):
        raise FilesystemTransactionError(
            f"{path_label} path resolves through symlink segments for {repo_relative_path}"
        )
    resolved_root = root.resolve()
    resolved_path = (root / repo_relative_path).resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise FilesystemTransactionError(
            f"{path_label} path escapes root after resolve for {repo_relative_path}"
        ) from exc
    return resolved_path


def manifest_apply_guard_state(
    manifest_payload: dict[str, Any],
    allowed_apply_roots: Sequence[str],
) -> ManifestApplyGuardState:
    files = manifest_payload.get("files", [])
    if not isinstance(files, list):
        raise ValueError("changed-files manifest must contain a files list")

    parsed_roots = [_parse_allowed_apply_root(value) for value in allowed_apply_roots]
    invalid_paths: list[str] = []
    changed_paths: list[str] = []
    disallowed_paths: list[str] = []
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            invalid_paths.append(f"<invalid-entry:{index}>")
            continue
        rel_path = entry.get("path")
        normalized_path = _normalize_manifest_repo_path(rel_path)
        if normalized_path is None:
            invalid_paths.append(str(rel_path))
            continue
        changed_paths.append(normalized_path)
        if not any(_path_matches_allowed_apply_root(normalized_path, root) for root in parsed_roots):
            disallowed_paths.append(normalized_path)

    return ManifestApplyGuardState(
        allowed_apply_roots=normalized_allowed_apply_roots(allowed_apply_roots),
        changed_paths=changed_paths,
        invalid_paths=sorted(set(invalid_paths)),
        disallowed_paths=sorted(set(disallowed_paths)),
    )


def validate_manifest_apply_guard(
    manifest_payload: dict[str, Any],
    allowed_apply_roots: Sequence[str],
) -> ManifestApplyGuardState:
    state = manifest_apply_guard_state(manifest_payload, allowed_apply_roots)
    problems: list[str] = []
    if state.invalid_paths:
        problems.append("invalid paths: " + ", ".join(state.invalid_paths))
    if state.disallowed_paths:
        problems.append(
            "paths outside allowed_apply_roots: " + ", ".join(state.disallowed_paths)
        )
    if problems:
        allowed = ", ".join(state.allowed_apply_roots)
        raise FilesystemTransactionError(
            "changed-files manifest violates apply guardrails ("
            + "; ".join(problems)
            + f"; allowed_apply_roots={allowed})"
        )
    return state


def _manifest_apply_summary(prepared: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {"total_changed_files": len(prepared), "added": 0, "modified": 0, "deleted": 0}
    for item in prepared:
        change_type = str(item["change_type"])
        if change_type in {"added", "modified", "deleted"}:
            counts[change_type] += 1
    return counts


def build_shadow_apply_report(
    manifest_payload: dict[str, Any],
    guard_state: ManifestApplyGuardState,
    prepared: Sequence[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    files = []
    for item in prepared:
        change_type = str(item["change_type"])
        workspace_path = item["workspace_path"]
        files.append(
            {
                "path": str(item["rel_path"]),
                "change_type": change_type,
                "live_exists": bool(item["existed_before"]),
                "workspace_exists": bool(workspace_path is not None and workspace_path.exists()),
                "would_write": change_type != "deleted",
                "would_delete": change_type == "deleted",
            }
        )
    return {
        "$schema": SHADOW_APPLY_REPORT_SCHEMA,
        "mode": "shadow",
        "status": "ready_for_live_apply",
        "generated_at": generated_at,
        "source_manifest": {
            "schema": str(manifest_payload.get("$schema", "")),
            "run_id": str(manifest_payload.get("run_id", "")),
        },
        "guard": {
            "allowed_apply_roots": guard_state.allowed_apply_roots,
            "changed_paths": guard_state.changed_paths,
            "invalid_paths": guard_state.invalid_paths,
            "disallowed_paths": guard_state.disallowed_paths,
        },
        "summary": _manifest_apply_summary(prepared),
        "files": files,
    }


def write_shadow_apply_report(path: Path, report: dict[str, Any]) -> Path:
    return atomic_write_json(path, report)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rollback_rehearsal_summary(files: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_changed_files": len(files),
        "apply_verified": sum(1 for item in files if item["apply_verified"]),
        "rollback_verified": sum(1 for item in files if item["rollback_verified"]),
        "failed": sum(
            1
            for item in files
            if not item["apply_verified"] or not item["rollback_verified"]
        ),
    }


def build_rollback_rehearsal_report(
    manifest_payload: dict[str, Any],
    guard_state: ManifestApplyGuardState,
    files: Sequence[dict[str, Any]],
    *,
    generated_at: str,
    shadow_report_ref: str = "",
    diagnostics: Sequence[str] = (),
) -> dict[str, Any]:
    summary = _rollback_rehearsal_summary(files)
    report_diagnostics = [str(item) for item in diagnostics if str(item).strip()]
    status = "pass" if summary["failed"] == 0 and not report_diagnostics else "fail"
    return {
        "$schema": ROLLBACK_REHEARSAL_REPORT_SCHEMA,
        "mode": "rollback_rehearsal",
        "status": status,
        "generated_at": generated_at,
        "source_shadow_apply_report": shadow_report_ref,
        "source_manifest": {
            "schema": str(manifest_payload.get("$schema", "")),
            "run_id": str(manifest_payload.get("run_id", "")),
        },
        "guard": {
            "allowed_apply_roots": guard_state.allowed_apply_roots,
            "changed_paths": guard_state.changed_paths,
            "invalid_paths": guard_state.invalid_paths,
            "disallowed_paths": guard_state.disallowed_paths,
        },
        "summary": summary,
        "files": list(files),
        "diagnostics": report_diagnostics,
    }


def write_rollback_rehearsal_report(path: Path, report: dict[str, Any]) -> Path:
    return atomic_write_json(path, report)


def _seed_rehearsal_live_root(
    live_root: Path,
    rehearsal_live_root: Path,
    manifest_payload: dict[str, Any],
) -> dict[str, str]:
    baseline_digests: dict[str, str] = {}
    for entry in manifest_payload.get("files", []):
        if not isinstance(entry, dict):
            continue
        normalized_rel_path = _normalize_manifest_repo_path(entry.get("path"))
        if normalized_rel_path is None:
            continue
        source_path = _resolve_manifest_apply_path(
            live_root,
            normalized_rel_path,
            path_label="live",
        )
        target_path = _resolve_manifest_apply_path(
            rehearsal_live_root,
            normalized_rel_path,
            path_label="rehearsal live",
        )
        if not source_path.exists():
            baseline_digests[normalized_rel_path] = ""
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        baseline_digests[normalized_rel_path] = _file_sha256(source_path)
    return baseline_digests


def _verify_rehearsal_apply(item: dict[str, Any]) -> tuple[bool, list[str]]:
    live_path: Path = item["live_path"]
    workspace_path: Path | None = item["workspace_path"]
    rel_path = str(item["rel_path"])
    change_type = str(item["change_type"])
    try:
        if change_type == "deleted":
            if not live_path.exists():
                return True, []
            return False, [f"{rel_path}: rehearsal apply left deleted file present"]
        if workspace_path is None or not workspace_path.exists():
            return False, [f"{rel_path}: workspace candidate missing during rehearsal"]
        if not live_path.exists():
            return False, [f"{rel_path}: rehearsal apply did not create live file"]
        if _file_sha256(live_path) == _file_sha256(workspace_path):
            return True, []
        return False, [f"{rel_path}: rehearsal apply digest mismatch"]
    except OSError as exc:
        return False, [f"{rel_path}: rehearsal apply verification failed: {exc}"]


def _verify_rehearsal_rollback(
    item: dict[str, Any],
    baseline_digest: str,
) -> tuple[bool, list[str]]:
    live_path: Path = item["live_path"]
    rel_path = str(item["rel_path"])
    try:
        if not baseline_digest:
            if not live_path.exists():
                return True, []
            return False, [f"{rel_path}: rehearsal rollback left new file present"]
        if not live_path.exists():
            return False, [f"{rel_path}: rehearsal rollback did not restore live file"]
        if _file_sha256(live_path) == baseline_digest:
            return True, []
        return False, [f"{rel_path}: rehearsal rollback digest mismatch"]
    except OSError as exc:
        return False, [f"{rel_path}: rehearsal rollback verification failed: {exc}"]


def _rehearsal_file_result(
    item: dict[str, Any],
    *,
    apply_verified: bool,
    rollback_verified: bool,
    diagnostics: Sequence[str],
) -> dict[str, Any]:
    workspace_path: Path | None = item["workspace_path"]
    return {
        "path": str(item["rel_path"]),
        "change_type": str(item["change_type"]),
        "live_exists_before": bool(item["existed_before"]),
        "workspace_exists": bool(workspace_path is not None and workspace_path.exists()),
        "apply_verified": apply_verified,
        "rollback_verified": rollback_verified,
        "diagnostics": [str(diagnostic) for diagnostic in diagnostics],
    }


def _rehearsal_file_results(
    prepared: Sequence[dict[str, Any]],
    baseline_digests: dict[str, str],
    apply_results: dict[str, bool],
    rollback_results: dict[str, bool],
    item_diagnostics: dict[str, list[str]],
) -> list[dict[str, Any]]:
    return [
        _rehearsal_file_result(
            item,
            apply_verified=apply_results.get(str(item["rel_path"]), False),
            rollback_verified=rollback_results.get(str(item["rel_path"]), False),
            diagnostics=item_diagnostics.get(str(item["rel_path"]), []),
        )
        for item in prepared
        if str(item["rel_path"]) in baseline_digests
    ]


def rehearse_manifest_apply_rollback(
    live_root: Path,
    workspace_root: Path,
    manifest_payload: dict[str, Any],
    *,
    allowed_apply_roots: Sequence[str],
    rollback_rehearsal_report_path: Path,
    rollback_rehearsal_generated_at: str,
    shadow_report_ref: str = "",
) -> dict[str, Any]:
    if not rollback_rehearsal_generated_at:
        raise FilesystemTransactionError("rollback_rehearsal_generated_at is required")
    try:
        guard_state = validate_manifest_apply_guard(manifest_payload, allowed_apply_roots)
    except ValueError as exc:
        raise FilesystemTransactionError(str(exc)) from exc

    prepared: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    deleted_live_paths: list[Path] = []
    baseline_digests: dict[str, str] = {}
    apply_results: dict[str, bool] = {}
    rollback_results: dict[str, bool] = {}
    item_diagnostics: dict[str, list[str]] = {}
    diagnostics: list[str] = []

    tmp_root = Path(tempfile.mkdtemp(prefix=".rollback-rehearsal-", dir=live_root))
    try:
        rehearsal_live_root = tmp_root / "live"
        rehearsal_live_root.mkdir(parents=True, exist_ok=True)
        tmp_dir = tmp_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        baseline_digests = _seed_rehearsal_live_root(
            live_root,
            rehearsal_live_root,
            manifest_payload,
        )
        prepared = _prepare_manifest_apply_items(
            rehearsal_live_root,
            workspace_root,
            tmp_dir,
            manifest_payload.get("files", []),
        )
        try:
            _apply_prepared_manifest_items_in_place(prepared, applied, deleted_live_paths)
        except OSError as exc:
            diagnostics.append(f"rehearsal apply failed: {exc}")
        for item in prepared:
            rel_path = str(item["rel_path"])
            apply_results[rel_path], apply_diagnostics = _verify_rehearsal_apply(item)
            item_diagnostics.setdefault(rel_path, []).extend(apply_diagnostics)
        rollback_errors = _rollback_manifest_items(applied)
        diagnostics.extend(f"rehearsal rollback failed: {error}" for error in rollback_errors)
        for item in prepared:
            rel_path = str(item["rel_path"])
            rollback_results[rel_path], rollback_diagnostics = _verify_rehearsal_rollback(
                item,
                baseline_digests.get(rel_path, ""),
            )
            item_diagnostics.setdefault(rel_path, []).extend(rollback_diagnostics)
    except OSError as exc:
        diagnostics.append(f"rollback rehearsal failed before verification: {exc}")
        diagnostics.extend(f"rehearsal rollback failed: {error}" for error in _rollback_manifest_items(applied))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    report = build_rollback_rehearsal_report(
        manifest_payload,
        guard_state,
        _rehearsal_file_results(
            prepared,
            baseline_digests,
            apply_results,
            rollback_results,
            item_diagnostics,
        ),
        generated_at=rollback_rehearsal_generated_at,
        shadow_report_ref=shadow_report_ref,
        diagnostics=diagnostics,
    )
    write_rollback_rehearsal_report(rollback_rehearsal_report_path, report)
    return report


def _prepare_manifest_apply_items(
    live_root: Path,
    workspace_root: Path,
    tmp_dir: Path,
    files: Sequence[Any],
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise FilesystemTransactionError(f"invalid manifest entry at index {index}")
        rel_path = entry.get("path")
        change_type = entry.get("change_type")
        normalized_rel_path = _normalize_manifest_repo_path(rel_path)
        if normalized_rel_path is None:
            raise FilesystemTransactionError(f"invalid manifest path at index {index}")
        if change_type not in {"added", "modified", "deleted"}:
            raise FilesystemTransactionError(
                f"invalid manifest change_type for {normalized_rel_path}: {change_type}"
            )
        live_path = _resolve_manifest_apply_path(
            live_root,
            normalized_rel_path,
            path_label="live",
        )
        workspace_path = (
            _resolve_manifest_apply_path(
                workspace_root,
                normalized_rel_path,
                path_label="workspace",
            )
            if change_type != "deleted"
            else None
        )
        backup_path = tmp_dir / f"{index}.backup"
        staged_path = tmp_dir / f"{index}.staged"
        existed_before = live_path.exists()
        if existed_before:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live_path, backup_path)
        if change_type != "deleted":
            if workspace_path is None or not workspace_path.exists():
                raise FilesystemTransactionError(
                    f"workspace candidate file is missing for {normalized_rel_path}"
                )
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace_path, staged_path)
        prepared.append(
            {
                "rel_path": normalized_rel_path,
                "change_type": change_type,
                "live_path": live_path,
                "workspace_path": workspace_path,
                "backup_path": backup_path if existed_before else None,
                "staged_path": staged_path if change_type != "deleted" else None,
                "existed_before": existed_before,
            }
        )
    return prepared


def _apply_prepared_manifest_items(
    prepared: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[Path]]:
    applied: list[dict[str, Any]] = []
    deleted_live_paths: list[Path] = []
    _apply_prepared_manifest_items_in_place(prepared, applied, deleted_live_paths)
    return applied, deleted_live_paths


def _apply_prepared_manifest_items_in_place(
    prepared: Sequence[dict[str, Any]],
    applied: list[dict[str, Any]],
    deleted_live_paths: list[Path],
) -> None:
    for item in prepared:
        live_path = item["live_path"]
        if item["change_type"] == "deleted":
            if live_path.exists():
                live_path.unlink()
                deleted_live_paths.append(live_path)
            applied.append(item)
            continue
        live_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(item["staged_path"], live_path)
        applied.append(item)


def _rollback_manifest_items(applied: Sequence[dict[str, Any]]) -> list[str]:
    rollback_errors: list[str] = []
    for item in reversed(applied):
        try:
            live_path = item["live_path"]
            backup_path = item["backup_path"]
            if backup_path is None:
                try:
                    live_path.unlink()
                except FileNotFoundError:
                    pass
            else:
                live_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup_path, live_path)
        except OSError as rollback_exc:
            rollback_errors.append(f"{item['rel_path']}: {rollback_exc}")
    return rollback_errors


def plan_manifest_apply_transaction(
    live_root: Path,
    workspace_root: Path,
    manifest_payload: dict[str, Any],
    *,
    allowed_apply_roots: Sequence[str],
    shadow_report_path: Path,
    shadow_report_generated_at: str,
) -> list[str]:
    if not shadow_report_generated_at:
        raise FilesystemTransactionError("shadow_report_generated_at is required")
    try:
        guard_state = validate_manifest_apply_guard(manifest_payload, allowed_apply_roots)
    except ValueError as exc:
        raise FilesystemTransactionError(str(exc)) from exc
    tmp_dir = Path(tempfile.mkdtemp(prefix=".manifest-plan-", dir=live_root))
    try:
        prepared = _prepare_manifest_apply_items(
            live_root,
            workspace_root,
            tmp_dir,
            manifest_payload.get("files", []),
        )
        shadow_report = build_shadow_apply_report(
            manifest_payload,
            guard_state,
            prepared,
            generated_at=shadow_report_generated_at,
        )
        write_shadow_apply_report(shadow_report_path, shadow_report)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return guard_state.changed_paths


def apply_manifest_transaction(
    live_root: Path,
    workspace_root: Path,
    manifest_payload: dict[str, Any],
    *,
    allowed_apply_roots: Sequence[str],
    shadow_report_path: Path | None = None,
    shadow_report_generated_at: str = "",
) -> list[str]:
    try:
        guard_state = validate_manifest_apply_guard(
            manifest_payload,
            allowed_apply_roots,
        )
    except ValueError as exc:
        raise FilesystemTransactionError(str(exc)) from exc
    files = manifest_payload.get("files", [])

    prepared: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    deleted_live_paths: list[Path] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix=".manifest-apply-", dir=live_root))
    try:
        prepared = _prepare_manifest_apply_items(live_root, workspace_root, tmp_dir, files)

        if shadow_report_path is not None:
            if not shadow_report_generated_at:
                raise FilesystemTransactionError(
                    "shadow_report_generated_at is required when shadow_report_path is provided"
                )
            shadow_report = build_shadow_apply_report(
                manifest_payload,
                guard_state,
                prepared,
                generated_at=shadow_report_generated_at,
            )
            write_shadow_apply_report(shadow_report_path, shadow_report)

        _apply_prepared_manifest_items_in_place(prepared, applied, deleted_live_paths)
    except OSError as exc:
        rollback_errors = _rollback_manifest_items(applied)
        detail = str(exc)
        if rollback_errors:
            detail += " | rollback issues: " + "; ".join(rollback_errors)
        raise FilesystemTransactionError(detail) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    for live_path in deleted_live_paths:
        _remove_empty_parent_dirs(live_path, stop_at=live_root)
    return guard_state.changed_paths
