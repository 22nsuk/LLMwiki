from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .command_log_summary_runtime import COMMAND_LOG_SUMMARY_FILENAME
from .gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_NONE,
)
from .output_runtime import display_path, resolve_repo_output_path, write_output_text

DEFAULT_OUT = "tmp/generated-artifact-retention-clean.json"

DELETE_CANDIDATE_PATHS = (
    "build/source-package-smoke",
    "build/review",
    "tmp/source-package-clean-extract",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "llm_wiki_vnext.egg-info",
)
DISPOSABLE_DIAGNOSTIC_PATHS = ("build/release/release-closeout-sealed-dry-run",)
TEMPLATE_RUN_RESIDUE_PATHS = (
    "runs/run-YYYYMMDD-slug",
    "runs/run-YYYYMMDD-mechanism-slug",
)
TEMPLATE_RUN_RESIDUE_ALLOWED_FILES = frozenset({"runtime-events.jsonl"})
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
GOAL_RUNTIME_LOCK_PATH = "build/goal-runs/goal-runtime.lock.json"
RUN_COMMAND_LOG_FILENAMES = frozenset(
    {
        "mutation-command.stdout.txt",
        "mutation-command.stderr.txt",
        "repo-health.stdout.txt",
        "repo-health.stderr.txt",
    }
)
RUN_REFERENCE_EVIDENCE_PATHS = (
    "build/release/release-auto-promotion-goal-run-identity.json",
    "build/release/release-auto-promotion-preflight.json",
    "build/release/release-auto-promotion-preseal.json",
    "build/release/release-post-commit-finalization.json",
    "build/release/release-post-seal-attestation.json",
    "build/release/release-run-manifest.json",
    "build/release/release-sealed-post-seal-attestation.json",
    "build/release/release-sealed-run-manifest.json",
    "build/release/release-sealed-run-ready-plan.json",
    "ops/reports/auto-improve-readiness.json",
    "ops/reports/goal-run-status.json",
    "ops/reports/goal-runtime-certificate.json",
    "ops/reports/goal-worktree-guard.json",
    "ops/reports/release-clean-blocker-ledger.json",
    "ops/reports/release-closeout-batch-manifest.json",
    "ops/reports/release-closeout-finality-attestation.json",
    "ops/reports/release-closeout-fixed-point.json",
    "ops/reports/release-closeout-summary.json",
    "ops/reports/release-evidence-dashboard.json",
    "ops/reports/remediation-backlog.json",
    "ops/reports/session-synopsis.json",
)
REWORK_CLOSURES_PATH = "ops/reports/rework-closures.json"
RUN_LOG_BLOCKING_REASONS = frozenset(
    {
        "artifact freshness report does not list this zero-byte run log placeholder",
        "artifact freshness report is missing",
        "artifact freshness report is missing run_log_placeholders",
        "command log summary does not record raw log path",
        "command log summary is missing or malformed",
        "command log summary original fingerprint mismatch",
        "command log summary trace fingerprint mismatch",
        "goal runtime lock blocks run-log cleanup",
        "run artifact fingerprint is missing or malformed",
        "run artifact fingerprint records non-empty command log content",
        "run command log path is a symlink",
        "zero-byte run command log is not ignored by git",
    }
)
PROTECTED_PATHS = (
    "build/release",
    "ops/reports",
    "ops/operator",
    "runs",
    "raw",
    "wiki",
    "system",
    "external-reports",
    "AGENTS.local.md",
    "ops/manifest.json",
    "ops/raw-registry.json",
    "ops/script-output-surfaces.json",
)


def _git_ignored(vault: Path, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel_path],
        cwd=vault,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _path_record(vault: Path, rel_path: str, *, category: str) -> dict[str, Any]:
    path = vault / rel_path
    exists = path.exists()
    return {
        "path": rel_path,
        "category": category,
        "exists": exists,
        "ignored": _git_ignored(vault, rel_path) if exists else False,
        "kind": "directory"
        if path.is_dir()
        else "file"
        if path.is_file()
        else "missing",
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _process_group_is_running(pgid: int) -> bool:
    if pgid <= 0 or os.name == "nt":
        return False
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    try:
        killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _int_field(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _goal_runtime_lock_blocker(vault: Path) -> dict[str, str] | None:
    path = vault / GOAL_RUNTIME_LOCK_PATH
    if not path.exists():
        return None
    payload = _read_json_object(path)
    if not payload:
        return {
            "path": GOAL_RUNTIME_LOCK_PATH,
            "reason": "goal runtime lock is unreadable or not a JSON object",
        }
    for field, owner_type, probe in (
        ("child_pgid", "child_process_group", _process_group_is_running),
        ("child_pid", "child_process", _process_is_running),
        ("pid", "runner_process", _process_is_running),
    ):
        value = _int_field(payload, field)
        if value > 0 and probe(value):
            return {
                "path": GOAL_RUNTIME_LOCK_PATH,
                "reason": f"active {owner_type} {value} owns the goal runtime workspace",
            }
    return None


def _freshness_placeholder_paths(vault: Path) -> tuple[set[str], str]:
    report_path = vault / ARTIFACT_FRESHNESS_REPORT_PATH
    if not report_path.is_file():
        return set(), "artifact freshness report is missing"
    report = _read_json_object(report_path)
    placeholders = report.get("run_log_placeholders")
    if not isinstance(placeholders, list):
        return set(), "artifact freshness report is missing run_log_placeholders"
    paths: set[str] = set()
    for item in placeholders:
        if not isinstance(item, dict):
            continue
        rel_path = item.get("path")
        if (
            isinstance(rel_path, str)
            and item.get("artifact_role") == "run_log_placeholder"
            and item.get("size_bytes") == 0
            and item.get("classification") == "empty_run_command_log_placeholder"
        ):
            paths.add(rel_path)
    return paths, ""


def _closed_rework_run_ids(vault: Path) -> set[str]:
    report = _read_json_object(vault / REWORK_CLOSURES_PATH)
    closed_run_ids: set[str] = set()
    closures = report.get("closures")
    if not isinstance(closures, list):
        return closed_run_ids
    for closure in closures:
        if not isinstance(closure, dict):
            continue
        run_ids = closure.get("closed_run_ids")
        if not isinstance(run_ids, list):
            continue
        closed_run_ids.update(
            run_id for run_id in run_ids if isinstance(run_id, str) and run_id
        )
    return closed_run_ids


def _run_reference_evidence(vault: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for rel_path in RUN_REFERENCE_EVIDENCE_PATHS:
        path = vault / rel_path
        if path.is_file():
            records.append((rel_path, _read_text(path)))
    return records


def _owning_run_path(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if len(parts) < 2 or parts[0] != "runs":
        return ""
    if len(parts) >= 3 and parts[1] == "archive":
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def _run_id_from_owning_path(owning_run: str) -> str:
    return Path(owning_run).name if owning_run else ""


def _blocking_run_reference(
    *,
    rel_path: str,
    owning_run: str,
    run_id: str,
    evidence: list[tuple[str, str]],
) -> str | None:
    needles = tuple(value for value in (rel_path, owning_run, run_id) if value)
    for evidence_path, text in evidence:
        if any(needle in text for needle in needles):
            return evidence_path
    return None


def _is_archived_run(owning_run: str) -> bool:
    return owning_run.startswith("runs/archive/")


def _run_artifact_fingerprint_confirmation(
    vault: Path,
    *,
    owning_run: str,
    rel_path: str,
) -> dict[str, Any]:
    fingerprint_path = vault / owning_run / "run-artifact-fingerprint.json"
    fingerprint_rel_path = f"{owning_run}/run-artifact-fingerprint.json"
    if not fingerprint_path.is_file():
        return {
            "fingerprint_path": fingerprint_rel_path,
            "fingerprint_status": "missing",
            "empty_sha256_confirmed": False,
            "fingerprint_blocking_reason": "run artifact fingerprint is missing or malformed",
        }
    payload = _read_json_object(fingerprint_path)
    artifacts = payload.get("artifacts")
    if not payload or not isinstance(artifacts, list):
        return {
            "fingerprint_path": fingerprint_rel_path,
            "fingerprint_status": "invalid",
            "empty_sha256_confirmed": False,
            "fingerprint_blocking_reason": "run artifact fingerprint is missing or malformed",
        }
    for item in artifacts:
        if not isinstance(item, dict) or item.get("path") != rel_path:
            continue
        empty_confirmed = (
            item.get("size_bytes") == 0 and item.get("sha256") == EMPTY_SHA256
        )
        result = {
            "fingerprint_path": fingerprint_rel_path,
            "fingerprint_status": "path_recorded",
            "empty_sha256_confirmed": empty_confirmed,
        }
        if not empty_confirmed:
            result["fingerprint_blocking_reason"] = (
                "run artifact fingerprint records non-empty command log content"
            )
        return result
    return {
        "fingerprint_path": fingerprint_rel_path,
        "fingerprint_status": "path_not_recorded",
        "empty_sha256_confirmed": False,
        "fingerprint_blocking_reason": "run artifact fingerprint is missing or malformed",
    }


def _raw_stream_log_filename(filename: str) -> bool:
    return filename.endswith((".stdout.txt", ".stderr.txt"))


def _artifact_role_from_stream_log(filename: str) -> str:
    if filename.endswith(".stdout.txt"):
        return "command_stdout"
    if filename.endswith(".stderr.txt"):
        return "command_stderr"
    return "command_log"


def _promoted_run_telemetry(vault: Path, owning_run: str) -> bool:
    payload = _read_json_object(vault / owning_run / "run-telemetry.json")
    return payload.get("decision") == "PROMOTE" and bool(payload.get("finalized", False))


def _summary_original_path_candidates(rel_path: str, owning_run: str, run_id: str) -> set[str]:
    candidates = {rel_path}
    if _is_archived_run(owning_run):
        candidates.add(f"runs/{run_id}/{Path(rel_path).name}")
    return candidates


def _relocated_summary_trace_path(
    vault: Path,
    *,
    owning_run: str,
    trace_rel: str,
) -> tuple[str, Path]:
    trace_path = vault / trace_rel
    if trace_path.is_file():
        return trace_rel, trace_path
    if _is_archived_run(owning_run):
        relocated_rel = f"{owning_run}/{Path(trace_rel).name}"
        relocated_path = vault / relocated_rel
        if relocated_path.is_file():
            return relocated_rel, relocated_path
    return trace_rel, trace_path


def _raw_command_log_summary_confirmation(
    vault: Path,
    *,
    rel_path: str,
    owning_run: str,
    run_id: str,
    size_bytes: int,
) -> dict[str, Any]:
    summary_rel_path = f"{owning_run}/{COMMAND_LOG_SUMMARY_FILENAME}"
    payload = _read_json_object(vault / summary_rel_path)
    streams = payload.get("streams")
    if not payload or not isinstance(streams, list):
        return {
            "summary_path": summary_rel_path,
            "summary_status": "missing_or_malformed",
            "summary_match_confirmed": False,
            "summary_blocking_reason": "command log summary is missing or malformed",
        }
    original_path_candidates = _summary_original_path_candidates(rel_path, owning_run, run_id)
    for item in streams:
        if not isinstance(item, dict) or item.get("original_path") not in original_path_candidates:
            continue
        raw_sha256 = _sha256_file(vault / rel_path)
        if item.get("original_size_bytes") != size_bytes or item.get("original_sha256") != raw_sha256:
            return {
                "summary_path": summary_rel_path,
                "summary_status": "original_fingerprint_mismatch",
                "summary_match_confirmed": False,
                "summary_blocking_reason": "command log summary original fingerprint mismatch",
            }
        trace_rel, trace_path = _relocated_summary_trace_path(
            vault,
            owning_run=owning_run,
            trace_rel=str(item.get("trace_path", "")).strip(),
        )
        if not trace_path.is_file() or item.get("trace_sha256") != _sha256_file(trace_path):
            return {
                "summary_path": summary_rel_path,
                "summary_status": "trace_fingerprint_mismatch",
                "summary_match_confirmed": False,
                "summary_blocking_reason": "command log summary trace fingerprint mismatch",
                "trace_path": trace_rel,
            }
        return {
            "summary_path": summary_rel_path,
            "summary_status": "path_recorded",
            "summary_match_confirmed": True,
            "trace_path": trace_rel,
            "trace_sha256": item.get("trace_sha256"),
            "original_sha256": raw_sha256,
        }
    return {
        "summary_path": summary_rel_path,
        "summary_status": "path_not_recorded",
        "summary_match_confirmed": False,
        "summary_blocking_reason": "command log summary does not record raw log path",
    }


def _run_command_log_symlink_retention_record(
    vault: Path, rel_path: str
) -> dict[str, Any]:
    owning_run = _owning_run_path(rel_path)
    return {
        **_path_record(vault, rel_path, category="historical_zero_byte_run_command_log"),
        "artifact_role": "run_log_placeholder",
        "size_bytes": 0,
        "owning_run": owning_run,
        "run_id": _run_id_from_owning_path(owning_run),
        "delete_allowed": False,
        "reason": "run command log path is a symlink",
    }


def _run_command_log_base_record(
    vault: Path,
    *,
    rel_path: str,
    owning_run: str,
    run_id: str,
    size_bytes: int,
) -> dict[str, Any]:
    return {
        **_path_record(vault, rel_path, category="historical_zero_byte_run_command_log"),
        "artifact_role": "run_log_placeholder",
        "size_bytes": size_bytes,
        "owning_run": owning_run,
        "run_id": run_id,
        "evidence_paths": [ARTIFACT_FRESHNESS_REPORT_PATH],
        **_run_artifact_fingerprint_confirmation(
            vault,
            owning_run=owning_run,
            rel_path=rel_path,
        ),
    }


def _raw_command_log_base_record(
    vault: Path,
    *,
    rel_path: str,
    owning_run: str,
    run_id: str,
    size_bytes: int,
) -> dict[str, Any]:
    return {
        **_path_record(vault, rel_path, category="raw_command_log_with_summary"),
        "artifact_role": _artifact_role_from_stream_log(Path(rel_path).name),
        "size_bytes": size_bytes,
        "owning_run": owning_run,
        "run_id": run_id,
        "evidence_paths": [f"{owning_run}/{COMMAND_LOG_SUMMARY_FILENAME}"],
    }


def _run_command_log_retained_record(
    record: dict[str, Any],
    reason: str,
    *,
    blocking_reference: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {**record, "delete_allowed": False, "reason": reason}
    if blocking_reference:
        result["blocking_reference"] = blocking_reference
    if extra:
        result.update(extra)
    return result


def _run_command_log_delete_record(
    record: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {**record, "delete_allowed": True, "reason": reason}


def _run_command_log_fingerprint_blocker(
    record: dict[str, Any],
) -> dict[str, Any] | None:
    reason = record.get("fingerprint_blocking_reason")
    if not reason:
        return None
    return _run_command_log_retained_record(
        record,
        str(reason),
        blocking_reference=str(record["fingerprint_path"]),
    )


def _raw_command_log_summary_blocker(record: dict[str, Any]) -> dict[str, Any] | None:
    reason = record.get("summary_blocking_reason")
    if not reason:
        return None
    return _run_command_log_retained_record(
        record,
        str(reason),
        blocking_reference=str(record["summary_path"]),
    )


def _classify_raw_command_log_record(
    vault: Path,
    record: dict[str, Any],
    *,
    rel_path: str,
    owning_run: str,
    run_id: str,
    closed_run_ids: set[str],
    lock_blocker: dict[str, str] | None,
    blocking_reference: str | None,
) -> dict[str, Any]:
    if not record["ignored"]:
        return _run_command_log_retained_record(
            record,
            "raw run command log is not ignored by git",
        )
    if lock_blocker is not None:
        return _run_command_log_retained_record(
            record,
            "goal runtime lock blocks run-log cleanup",
            blocking_reference=lock_blocker["path"],
            extra={"lock_blocking_reason": lock_blocker["reason"]},
        )
    if blocking_reference:
        return _run_command_log_retained_record(
            record,
            "current evidence references owning run",
            blocking_reference=blocking_reference,
        )
    if not (_is_archived_run(owning_run) or run_id in closed_run_ids):
        return _run_command_log_retained_record(
            record,
            "run is not archived or closed by rework-closures evidence",
        )
    if not _promoted_run_telemetry(vault, owning_run):
        return _run_command_log_retained_record(
            record,
            "run did not finish as promoted",
        )
    enriched = {
        **record,
        **_raw_command_log_summary_confirmation(
            vault,
            rel_path=rel_path,
            owning_run=owning_run,
            run_id=run_id,
            size_bytes=int(record["size_bytes"]),
        ),
    }
    summary_blocker = _raw_command_log_summary_blocker(enriched)
    if summary_blocker is not None:
        return summary_blocker
    return _run_command_log_delete_record(
        enriched,
        "promoted archived/closed raw command log covered by command-log-summary",
    )


def _classify_run_command_log_record(
    record: dict[str, Any],
    *,
    rel_path: str,
    owning_run: str,
    run_id: str,
    closed_run_ids: set[str],
    freshness_paths: set[str],
    freshness_reason: str,
    lock_blocker: dict[str, str] | None,
    blocking_reference: str | None,
) -> dict[str, Any]:
    if not record["ignored"]:
        return _run_command_log_retained_record(
            record,
            "zero-byte run command log is not ignored by git",
        )
    if lock_blocker is not None:
        return _run_command_log_retained_record(
            record,
            "goal runtime lock blocks run-log cleanup",
            blocking_reference=lock_blocker["path"],
            extra={"lock_blocking_reason": lock_blocker["reason"]},
        )
    if freshness_reason:
        return _run_command_log_retained_record(
            record,
            freshness_reason,
            blocking_reference=ARTIFACT_FRESHNESS_REPORT_PATH,
        )
    if rel_path not in freshness_paths:
        return _run_command_log_retained_record(
            record,
            "artifact freshness report does not list this zero-byte run log placeholder",
            blocking_reference=ARTIFACT_FRESHNESS_REPORT_PATH,
        )
    if blocking_reference:
        return _run_command_log_retained_record(
            record,
            "current evidence references owning run",
            blocking_reference=blocking_reference,
        )
    if _is_archived_run(owning_run):
        fingerprint_blocker = _run_command_log_fingerprint_blocker(record)
        if fingerprint_blocker is not None:
            return fingerprint_blocker
        return _run_command_log_delete_record(
            record,
            "archived run zero-byte command log placeholder",
        )
    if run_id in closed_run_ids:
        fingerprint_blocker = _run_command_log_fingerprint_blocker(record)
        if fingerprint_blocker is not None:
            return fingerprint_blocker
        return _run_command_log_delete_record(
            record,
            "closed rework run zero-byte command log placeholder",
        )
    return _run_command_log_retained_record(
        record,
        "run is not archived or closed by rework-closures evidence",
    )


def _template_run_residue_record(vault: Path, rel_path: str) -> dict[str, Any]:
    record = _path_record(vault, rel_path, category="template_run_residue")
    path = vault / rel_path
    if not path.exists():
        return {**record, "delete_allowed": True}
    if not path.is_dir():
        return {
            **record,
            "delete_allowed": False,
            "reason": "template placeholder run residue path is not a directory",
        }
    files = sorted(
        child.relative_to(path).as_posix()
        for child in path.rglob("*")
        if child.is_file()
    )
    delete_allowed = set(files).issubset(TEMPLATE_RUN_RESIDUE_ALLOWED_FILES)
    return {
        **record,
        "delete_allowed": delete_allowed,
        "files": files,
        "reason": (
            "template placeholder run directory contains only runtime event residue"
            if delete_allowed
            else "template placeholder run directory contains non-runtime-event artifacts"
        ),
    }


def _run_command_log_retention_records(vault: Path) -> list[dict[str, Any]]:
    runs_root = vault / "runs"
    if not runs_root.is_dir():
        return []
    closed_run_ids = _closed_rework_run_ids(vault)
    reference_evidence = _run_reference_evidence(vault)
    freshness_paths, freshness_reason = _freshness_placeholder_paths(vault)
    lock_blocker = _goal_runtime_lock_blocker(vault)
    records: list[dict[str, Any]] = []
    for path in sorted(runs_root.rglob("*")):
        is_zero_placeholder_name = path.name in RUN_COMMAND_LOG_FILENAMES
        is_raw_stream_log = _raw_stream_log_filename(path.name)
        if not (is_zero_placeholder_name or is_raw_stream_log):
            continue
        try:
            rel_path = path.relative_to(vault).as_posix()
        except ValueError:
            continue
        if path.is_symlink():
            records.append(_run_command_log_symlink_retention_record(vault, rel_path))
            continue
        if not path.is_file():
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue
        if size_bytes == 0 and not is_zero_placeholder_name:
            continue
        if size_bytes != 0 and not is_raw_stream_log:
            continue
        owning_run = _owning_run_path(rel_path)
        run_id = _run_id_from_owning_path(owning_run)
        blocking_reference = _blocking_run_reference(
            rel_path=rel_path,
            owning_run=owning_run,
            run_id=run_id,
            evidence=reference_evidence,
        )
        if size_bytes == 0:
            record = _run_command_log_base_record(
                vault,
                rel_path=rel_path,
                owning_run=owning_run,
                run_id=run_id,
                size_bytes=size_bytes,
            )
            records.append(
                _classify_run_command_log_record(
                    record,
                    rel_path=rel_path,
                    owning_run=owning_run,
                    run_id=run_id,
                    closed_run_ids=closed_run_ids,
                    freshness_paths=freshness_paths,
                    freshness_reason=freshness_reason,
                    lock_blocker=lock_blocker,
                    blocking_reference=blocking_reference,
                )
            )
            continue
        record = _raw_command_log_base_record(
            vault,
            rel_path=rel_path,
            owning_run=owning_run,
            run_id=run_id,
            size_bytes=size_bytes,
        )
        records.append(
            _classify_raw_command_log_record(
                vault,
                record,
                rel_path=rel_path,
                owning_run=owning_run,
                run_id=run_id,
                closed_run_ids=closed_run_ids,
                lock_blocker=lock_blocker,
                blocking_reference=blocking_reference,
            )
        )
    return records


def _empty_regular_run_log_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.stat().st_size == 0
    except OSError:
        return False


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _orphan_goal_state_records(vault: Path) -> list[dict[str, Any]]:
    runs_root = vault / "runs"
    if not runs_root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    global_status = vault / "ops/reports/goal-run-status.json"
    global_certificate = vault / "ops/reports/goal-runtime-certificate.json"
    global_lock = vault / "build/goal-runs/goal-runtime.lock.json"
    for state_dir in sorted(runs_root.glob("goal-*/state")):
        if not state_dir.is_dir():
            continue
        rel_path = state_dir.relative_to(vault).as_posix()
        records.append(
            {
                "path": rel_path,
                "category": "run_state_candidate",
                "exists": True,
                "ignored": _git_ignored(vault, rel_path),
                "delete_allowed": False,
                "reason": (
                    "run state is provenance evidence; classify/quarantine before deletion"
                    if global_status.exists()
                    or global_certificate.exists()
                    or global_lock.exists()
                    else "orphan-looking run state without global goal status, certificate, or lock"
                ),
            }
        )
    return records


def _delete_candidate_records(
    vault: Path, run_log_retention: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records = [
        _path_record(vault, rel_path, category="regenerated_residue")
        for rel_path in DELETE_CANDIDATE_PATHS
    ]
    records.extend(
        _path_record(vault, rel_path, category="disposable_diagnostic")
        for rel_path in DISPOSABLE_DIAGNOSTIC_PATHS
    )
    records.extend(
        _template_run_residue_record(vault, rel_path)
        for rel_path in TEMPLATE_RUN_RESIDUE_PATHS
    )
    records.extend(item for item in run_log_retention if item["delete_allowed"])
    return records


def _retained_records(
    vault: Path, run_log_retention: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records = [
        {
            **_path_record(vault, rel_path, category="protected_surface"),
            "delete_allowed": False,
        }
        for rel_path in PROTECTED_PATHS
    ]
    records.extend(_orphan_goal_state_records(vault))
    records.extend(item for item in run_log_retention if not item["delete_allowed"])
    return records


def _delete_candidate_blockers(
    delete_candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    blockers = [
        {
            "path": item["path"],
            "reason": "delete candidate exists but is not ignored by git",
        }
        for item in delete_candidates
        if item["exists"] and not item["ignored"]
    ]
    blockers.extend(
        {
            "path": item["path"],
            "reason": str(item.get("reason", "delete candidate is not safe to delete")),
        }
        for item in delete_candidates
        if item["exists"] and item["ignored"] and not item.get("delete_allowed", True)
    )
    return blockers


def _retention_blocker_records(
    run_log_retention: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "path": item["path"],
            "reason": str(item["reason"]),
            **(
                {"blocking_reference": str(item["blocking_reference"])}
                if item.get("blocking_reference")
                else {}
            ),
        }
        for item in run_log_retention
        if item["exists"] and item.get("reason") in RUN_LOG_BLOCKING_REASONS
    ]


def _run_log_apply_blockers(
    vault: Path, delete_candidates: list[dict[str, Any]]
) -> list[dict[str, str]]:
    changed_zero_byte_logs = [
        {
            "path": item["path"],
            "reason": "run command log changed before deletion",
        }
        for item in delete_candidates
        if item["category"] == "historical_zero_byte_run_command_log"
        and not _empty_regular_run_log_file(vault / item["path"])
    ]
    changed_raw_logs = [
        {
            "path": item["path"],
            "reason": "run command log summary changed before deletion",
        }
        for item in delete_candidates
        if item["category"] == "raw_command_log_with_summary"
        and not _raw_command_log_summary_confirmation(
            vault,
            rel_path=str(item["path"]),
            owning_run=str(item["owning_run"]),
            run_id=str(item["run_id"]),
            size_bytes=int(item["size_bytes"]),
        ).get("summary_match_confirmed")
    ]
    return changed_zero_byte_logs + changed_raw_logs


def _delete_allowed_candidates(
    vault: Path, delete_candidates: list[dict[str, Any]]
) -> list[str]:
    deleted_paths: list[str] = []
    for item in delete_candidates:
        if not item["exists"] or not item.get("delete_allowed", True):
            continue
        _delete_path(vault / item["path"])
        deleted_paths.append(item["path"])
    return deleted_paths


def _retention_summary(
    *,
    delete_candidates: list[dict[str, Any]],
    retained: list[dict[str, Any]],
    run_log_retention: list[dict[str, Any]],
    deleted_paths: list[str],
    blockers: list[dict[str, str]],
    retention_blockers: list[dict[str, str]],
) -> dict[str, int]:
    return {
        "delete_candidate_count": sum(1 for item in delete_candidates if item["exists"]),
        "deleted_count": len(deleted_paths),
        "retained_existing_count": sum(1 for item in retained if item["exists"]),
        "blocker_count": len(blockers),
        "retention_blocker_count": len(retention_blockers),
        "run_log_placeholder_count": len(run_log_retention),
        "run_log_delete_candidate_count": sum(
            1 for item in run_log_retention if item["delete_allowed"]
        ),
        "run_log_retained_count": sum(
            1 for item in run_log_retention if not item["delete_allowed"]
        ),
    }


def build_report(vault: Path, *, apply: bool = False) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    run_log_retention = _run_command_log_retention_records(resolved_vault)
    delete_candidates = _delete_candidate_records(resolved_vault, run_log_retention)
    retained = _retained_records(resolved_vault, run_log_retention)
    blockers = _delete_candidate_blockers(delete_candidates)
    active_lock_blocker = _goal_runtime_lock_blocker(resolved_vault)
    if apply and active_lock_blocker is not None:
        blockers.append(
            {
                "path": active_lock_blocker["path"],
                "reason": active_lock_blocker["reason"],
            }
        )
    retention_blockers = _retention_blocker_records(run_log_retention)
    deleted_paths: list[str] = []
    if apply and not blockers:
        blockers.extend(_run_log_apply_blockers(resolved_vault, delete_candidates))
    if apply and not blockers:
        deleted_paths = _delete_allowed_candidates(resolved_vault, delete_candidates)
    status = "fail" if blockers else "attention" if retention_blockers else "pass"
    cleanup_status = "blocked" if blockers else "applied" if apply else "dry_run"
    retention_status = "attention" if retention_blockers else "pass"
    gate_effect = (
        GATE_EFFECT_BLOCKS_EXECUTION
        if blockers
        else GATE_EFFECT_ADVISORY
        if retention_blockers
        else GATE_EFFECT_NONE
    )
    return {
        "artifact_kind": "generated_artifact_retention_clean",
        "status": status,
        "cleanup_status": cleanup_status,
        "retention_status": retention_status,
        "gate_effect": gate_effect,
        "apply": apply,
        "delete_candidates": delete_candidates,
        "retained": retained,
        "run_log_retention": run_log_retention,
        "deleted_paths": deleted_paths,
        "blockers": blockers,
        "retention_blockers": retention_blockers,
        "summary": _retention_summary(
            delete_candidates=delete_candidates,
            retained=retained,
            run_log_retention=run_log_retention,
            deleted_paths=deleted_paths,
            blockers=blockers,
            retention_blockers=retention_blockers,
        ),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = resolve_repo_output_path(
        vault, out_path, default_relative_path=DEFAULT_OUT
    )
    write_output_text(
        destination,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean safe generated residue with retention guards."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, apply=args.apply)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
