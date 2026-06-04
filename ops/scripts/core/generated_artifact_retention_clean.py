from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

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
        if path.name not in RUN_COMMAND_LOG_FILENAMES:
            continue
        if path.is_symlink():
            try:
                rel_path = path.relative_to(vault).as_posix()
            except ValueError:
                continue
            records.append(
                {
                    **_path_record(
                        vault, rel_path, category="historical_zero_byte_run_command_log"
                    ),
                    "artifact_role": "run_log_placeholder",
                    "size_bytes": 0,
                    "owning_run": _owning_run_path(rel_path),
                    "run_id": _run_id_from_owning_path(_owning_run_path(rel_path)),
                    "delete_allowed": False,
                    "reason": "run command log path is a symlink",
                }
            )
            continue
        if not path.is_file():
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue
        if size_bytes != 0:
            continue
        rel_path = path.relative_to(vault).as_posix()
        owning_run = _owning_run_path(rel_path)
        run_id = _run_id_from_owning_path(owning_run)
        blocking_reference = _blocking_run_reference(
            rel_path=rel_path,
            owning_run=owning_run,
            run_id=run_id,
            evidence=reference_evidence,
        )
        fingerprint = _run_artifact_fingerprint_confirmation(
            vault,
            owning_run=owning_run,
            rel_path=rel_path,
        )
        record = {
            **_path_record(
                vault, rel_path, category="historical_zero_byte_run_command_log"
            ),
            "artifact_role": "run_log_placeholder",
            "size_bytes": size_bytes,
            "owning_run": owning_run,
            "run_id": run_id,
            "evidence_paths": [ARTIFACT_FRESHNESS_REPORT_PATH],
            **fingerprint,
        }
        if not record["ignored"]:
            records.append(
                {
                    **record,
                    "delete_allowed": False,
                    "reason": "zero-byte run command log is not ignored by git",
                }
            )
        elif lock_blocker is not None:
            records.append(
                {
                    **record,
                    "delete_allowed": False,
                    "reason": "goal runtime lock blocks run-log cleanup",
                    "blocking_reference": lock_blocker["path"],
                    "lock_blocking_reason": lock_blocker["reason"],
                }
            )
        elif freshness_reason:
            records.append(
                {
                    **record,
                    "delete_allowed": False,
                    "reason": freshness_reason,
                    "blocking_reference": ARTIFACT_FRESHNESS_REPORT_PATH,
                }
            )
        elif rel_path not in freshness_paths:
            records.append(
                {
                    **record,
                    "delete_allowed": False,
                    "reason": "artifact freshness report does not list this zero-byte run log placeholder",
                    "blocking_reference": ARTIFACT_FRESHNESS_REPORT_PATH,
                }
            )
        elif blocking_reference:
            records.append(
                {
                    **record,
                    "delete_allowed": False,
                    "reason": "current evidence references owning run",
                    "blocking_reference": blocking_reference,
                }
            )
        elif _is_archived_run(owning_run):
            if record.get("fingerprint_blocking_reason"):
                records.append(
                    {
                        **record,
                        "delete_allowed": False,
                        "reason": str(record["fingerprint_blocking_reason"]),
                        "blocking_reference": str(record["fingerprint_path"]),
                    }
                )
            else:
                records.append(
                    {
                        **record,
                        "delete_allowed": True,
                        "reason": "archived run zero-byte command log placeholder",
                    }
                )
        elif run_id in closed_run_ids:
            if record.get("fingerprint_blocking_reason"):
                records.append(
                    {
                        **record,
                        "delete_allowed": False,
                        "reason": str(record["fingerprint_blocking_reason"]),
                        "blocking_reference": str(record["fingerprint_path"]),
                    }
                )
            else:
                records.append(
                    {
                        **record,
                        "delete_allowed": True,
                        "reason": "closed rework run zero-byte command log placeholder",
                    }
                )
        else:
            records.append(
                {
                    **record,
                    "delete_allowed": False,
                    "reason": "run is not archived or closed by rework-closures evidence",
                }
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


def build_report(vault: Path, *, apply: bool = False) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    delete_candidates = [
        _path_record(resolved_vault, rel_path, category="regenerated_residue")
        for rel_path in DELETE_CANDIDATE_PATHS
    ]
    delete_candidates.extend(
        _path_record(resolved_vault, rel_path, category="disposable_diagnostic")
        for rel_path in DISPOSABLE_DIAGNOSTIC_PATHS
    )
    delete_candidates.extend(
        _template_run_residue_record(resolved_vault, rel_path)
        for rel_path in TEMPLATE_RUN_RESIDUE_PATHS
    )
    run_log_retention = _run_command_log_retention_records(resolved_vault)
    delete_candidates.extend(
        item for item in run_log_retention if item["delete_allowed"]
    )
    retained = [
        {
            **_path_record(resolved_vault, rel_path, category="protected_surface"),
            "delete_allowed": False,
        }
        for rel_path in PROTECTED_PATHS
    ]
    retained.extend(_orphan_goal_state_records(resolved_vault))
    retained.extend(item for item in run_log_retention if not item["delete_allowed"])
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
    active_lock_blocker = _goal_runtime_lock_blocker(resolved_vault)
    if apply and active_lock_blocker is not None:
        blockers.append(
            {
                "path": active_lock_blocker["path"],
                "reason": active_lock_blocker["reason"],
            }
        )
    retention_blockers = [
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
    deleted_paths: list[str] = []
    apply_blockers = []
    if apply and not blockers:
        apply_blockers = [
            {
                "path": item["path"],
                "reason": "run command log changed before deletion",
            }
            for item in delete_candidates
            if item["category"] == "historical_zero_byte_run_command_log"
            and not _empty_regular_run_log_file(resolved_vault / item["path"])
        ]
    blockers.extend(apply_blockers)
    if apply and not blockers:
        for item in delete_candidates:
            if not item["exists"] or not item.get("delete_allowed", True):
                continue
            _delete_path(resolved_vault / item["path"])
            deleted_paths.append(item["path"])
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
        "summary": {
            "delete_candidate_count": sum(
                1 for item in delete_candidates if item["exists"]
            ),
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
        },
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
