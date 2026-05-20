from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/goal-runtime-clean-transient.json"
DEFAULT_STATUS_REPORT = "ops/reports/goal-run-status.json"
PRODUCER = "ops.scripts.goal_runtime_clean_transient"
SCHEMA_PATH = "ops/schemas/goal-runtime-clean-transient.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_clean_transient --vault ."
OBSOLETE_TRACKED_GOAL_SURFACES = {
    "ops/reports/goal-status.md": "legacy markdown status predates run-local goal state",
    "ops/reports/goal-resume-metadata.json": "legacy resume metadata points at old checkpoints",
    "ops/reports/goal-prompt.md": "legacy markdown prompt duplicates the JSON prompt surface",
    "ops/reports/goal-audit-log.jsonl": "legacy audit log is superseded by run-local audit-log.jsonl",
}
STALE_TMP_TREES = (
    "tmp/source-package-check",
    "tmp/source-package-clean-extract",
    "tmp/release-source-package-check",
    "tmp/release-closeout-sealed-dry-run",
)
PROTECTED_REPORT_SURFACES = (
    "ops/reports/codex-goal-contract.json",
    "ops/reports/codex-goal-prompt.json",
    "ops/reports/goal-run-status.json",
    "ops/reports/goal-profile-verification.json",
)
GOAL_SESSION_RESULT_FILENAME = "auto-improve-goal-session-result.json"
GOAL_SESSION_RESULT_CATEGORY = "stale_goal_session_result"


@dataclass(frozen=True)
class GoalRuntimeCleanTransientRequest:
    vault: Path
    apply: bool = False
    out_path: str | None = None
    status_report_path: str = DEFAULT_STATUS_REPORT
    policy_path: str | None = None
    context: RuntimeContext | None = None


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _repo_path(vault: Path, rel_path: str) -> Path:
    path = vault / rel_path
    resolved = path.resolve(strict=False)
    resolved.relative_to(vault.resolve())
    return resolved


def _repo_path_or_none(vault: Path, rel_path: str) -> Path | None:
    try:
        return _repo_path(vault, rel_path)
    except ValueError:
        return None


def _relative_path(vault: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(vault.resolve()).as_posix()
    except ValueError:
        return "<outside-vault>"


def _safe_relative_path(vault: Path, rel_path: str) -> str | None:
    path = _repo_path_or_none(vault, rel_path)
    if path is None:
        return None
    normalized = _relative_path(vault, path)
    return normalized if normalized != "<outside-vault>" else None


def _path_kind(path: Path) -> str:
    if path.is_dir() and not path.is_symlink():
        return "directory"
    if path.exists():
        return "file"
    return "missing"


def _status_report(vault: Path, rel_path: str) -> dict[str, Any]:
    path = _repo_path_or_none(vault, rel_path)
    return _load_json_object(path) if path is not None else {}


def _string_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in payload.values():
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _protected_paths(vault: Path, status_report_path: str, status: dict[str, Any]) -> list[str]:
    protected = {status_report_path, *PROTECTED_REPORT_SURFACES}
    goal = status.get("goal")
    if isinstance(goal, dict):
        contract_path = goal.get("contract_path")
        if isinstance(contract_path, str) and contract_path:
            protected.add(contract_path)
    artifacts = status.get("artifacts")
    if isinstance(artifacts, dict):
        protected.update(_string_values(artifacts))
    run = status.get("run")
    run_id = run.get("run_id") if isinstance(run, dict) else ""
    if isinstance(run_id, str) and run_id:
        protected.add(f"runs/goal-{run_id}")
    for rel_path in list(protected):
        if rel_path.startswith("runs/") and "/state/" in rel_path:
            protected.add(rel_path.split("/state/", maxsplit=1)[0])
    return sorted({path for rel_path in protected if (path := _safe_relative_path(vault, rel_path))})


def _is_protected(rel_path: str, protected_paths: list[str]) -> bool:
    rel = rel_path.rstrip("/")
    for protected in protected_paths:
        item = protected.rstrip("/")
        if rel == item or rel.startswith(f"{item}/") or item.startswith(f"{rel}/"):
            return True
    return False


def _candidate(
    *,
    vault: Path,
    rel_path: str,
    category: str,
    reason: str,
    protected_paths: list[str],
) -> dict[str, Any] | None:
    path = _repo_path_or_none(vault, rel_path)
    if path is None:
        return None
    if not path.exists():
        return None
    normalized = _relative_path(vault, path)
    protected = (
        False
        if category == GOAL_SESSION_RESULT_CATEGORY
        else _is_protected(normalized, protected_paths)
    )
    return {
        "path": normalized,
        "category": category,
        "reason": reason,
        "path_type": _path_kind(path),
        "protected": protected,
        "existed_before": True,
        "exists_after": True,
        "action": "skipped_protected" if protected else "would_remove",
        "error": "",
    }


def _runtime_event_log_candidates(status: dict[str, Any]) -> list[tuple[str, str, str]]:
    run_id = _active_run_id(status)
    if not run_id:
        return []
    return [
        (
            f"ops/reports/runtime-events/auto-improve-session/{run_id}.jsonl",
            "legacy_runtime_event_log",
            "run-local goal state supersedes legacy auto-improve session event logs for this run id",
        ),
        (
            f"ops/reports/runtime-events/observability-artifacts/{run_id}.jsonl",
            "legacy_runtime_event_log",
            "run-local goal state supersedes legacy observability event logs for this run id",
        ),
    ]


def _active_run_id(status: dict[str, Any]) -> str:
    run = status.get("run")
    run_id = run.get("run_id") if isinstance(run, dict) else ""
    return run_id if isinstance(run_id, str) and run_id else ""


def _active_run_status(status: dict[str, Any]) -> str:
    run = status.get("run")
    run_status = run.get("status") if isinstance(run, dict) else ""
    return run_status if isinstance(run_status, str) else ""


def _goal_session_result_candidates(status: dict[str, Any]) -> list[tuple[str, str, str]]:
    if _active_run_status(status) == "running":
        return []
    state_dirs = _goal_state_dirs(status)
    if not state_dirs:
        return []
    return [
        (
            f"{state_dir}/{GOAL_SESSION_RESULT_FILENAME}",
            GOAL_SESSION_RESULT_CATEGORY,
            (
                "goal runner result-out is a transient child stdout copy; "
                "canonical session evidence lives in schema-backed auto-improve session reports"
            ),
        )
        for state_dir in state_dirs
    ]


def _goal_state_dirs(status: dict[str, Any]) -> list[str]:
    state_dirs: set[str] = set()
    goal = status.get("goal")
    if isinstance(goal, dict):
        contract_path = goal.get("contract_path")
        if isinstance(contract_path, str) and contract_path:
            state_dirs.add(str(Path(contract_path).parent).strip("."))
    artifacts = status.get("artifacts")
    if isinstance(artifacts, dict):
        status_report_path = artifacts.get("status_report_path")
        if isinstance(status_report_path, str) and status_report_path:
            state_dirs.add(str(Path(status_report_path).parent).strip("."))
    run_id = _active_run_id(status)
    if run_id:
        state_dirs.add(f"runs/goal-{run_id}/state")
    return sorted(path.strip("/") for path in state_dirs if path.strip("/"))


def _goal_tree_candidates(
    vault: Path, status: dict[str, Any], protected_paths: list[str]
) -> list[tuple[str, str, str]]:
    if not _active_run_id(status):
        return []
    runs_root = vault / "runs"
    if not runs_root.exists():
        return []
    candidates: list[tuple[str, str, str]] = []
    for path in sorted(runs_root.glob("goal-*")):
        if not path.is_dir():
            continue
        rel_path = _relative_path(vault, path)
        if _is_protected(rel_path, protected_paths):
            continue
        candidates.append(
            (
                rel_path,
                "stale_goal_run_local_tree",
                "goal run-local tree is not referenced by the current goal status report",
            )
        )
    return candidates


def _cleanup_specs(
    vault: Path,
    status: dict[str, Any],
    protected_paths: list[str],
) -> list[tuple[str, str, str]]:
    specs = [
        (path, "obsolete_tracked_goal_surface", reason)
        for path, reason in OBSOLETE_TRACKED_GOAL_SURFACES.items()
    ]
    specs.extend(_runtime_event_log_candidates(status))
    specs.extend(_goal_session_result_candidates(status))
    specs.extend(_goal_tree_candidates(vault, status, protected_paths))
    specs.extend(
        (
            path,
            "stale_tmp_tree",
            "temporary extraction or dry-run tree should not feed long-run currentness",
        )
        for path in STALE_TMP_TREES
    )
    return specs


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink()


def _apply_cleanup(vault: Path, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        if item["protected"]:
            applied.append(item)
            continue
        path = _repo_path_or_none(vault, str(item["path"]))
        if path is None:
            item["action"] = "failed"
            item["error"] = "candidate path is outside the vault"
            item["exists_after"] = False
            applied.append(item)
            continue
        try:
            _remove_path(path)
        except OSError as exc:
            item["action"] = "failed"
            item["error"] = str(exc)
        else:
            item["action"] = "removed"
            item["error"] = ""
        item["exists_after"] = path.exists()
        applied.append(item)
    return applied


def _status(candidates: list[dict[str, Any]], *, apply: bool) -> str:
    if any(item["action"] == "failed" for item in candidates):
        return "fail"
    if not apply and any(not item["protected"] for item in candidates):
        return "attention"
    return "pass"


def _summary(candidates: list[dict[str, Any]], *, apply: bool) -> dict[str, int | bool]:
    return {
        "apply": apply,
        "candidate_count": len(candidates),
        "removable_count": sum(1 for item in candidates if not item["protected"]),
        "removed_count": sum(1 for item in candidates if item["action"] == "removed"),
        "would_remove_count": sum(1 for item in candidates if item["action"] == "would_remove"),
        "skipped_protected_count": sum(1 for item in candidates if item["action"] == "skipped_protected"),
        "failed_count": sum(1 for item in candidates if item["action"] == "failed"),
    }


def build_report(
    request: GoalRuntimeCleanTransientRequest | Path,
    **legacy_fields: Any,
) -> dict[str, Any]:
    if isinstance(request, GoalRuntimeCleanTransientRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        active_request = request
    else:
        active_request = GoalRuntimeCleanTransientRequest(vault=Path(request), **legacy_fields)
    vault = active_request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, active_request.policy_path)
    context = active_request.context or RuntimeContext.from_policy(policy)
    status_report_path = (
        _safe_relative_path(vault, active_request.status_report_path) or "<outside-vault>"
    )
    status = _status_report(vault, active_request.status_report_path)
    protected_paths = _protected_paths(vault, status_report_path, status)
    candidates = [
        item
        for rel_path, category, reason in _cleanup_specs(vault, status, protected_paths)
        for item in [
            _candidate(
                vault=vault,
                rel_path=rel_path,
                category=category,
                reason=reason,
                protected_paths=protected_paths,
            )
        ]
        if item is not None
    ]
    if active_request.apply:
        candidates = _apply_cleanup(vault, candidates)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="goal_runtime_clean_transient",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_clean_transient.py",
                "ops/schemas/goal-runtime-clean-transient.schema.json",
                "mk/mechanism.mk",
            ],
            text_inputs={
                "obsolete_tracked_goal_surfaces": json.dumps(
                    OBSOLETE_TRACKED_GOAL_SURFACES,
                    sort_keys=True,
                ),
                "stale_tmp_trees": json.dumps(STALE_TMP_TREES),
                "status_report_path": status_report_path,
            },
            source_tree_excluded_files=(active_request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": _status(candidates, apply=active_request.apply),
        "status_report_path": status_report_path,
        "protected_paths": protected_paths,
        "summary": _summary(candidates, apply=active_request.apply),
        "cleanup_candidates": candidates,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal runtime transient cleanup schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output report path.")
    parser.add_argument("--status-report", default=DEFAULT_STATUS_REPORT, help="Current goal status report path.")
    parser.add_argument("--policy-path", default=None, help="Policy path relative to the vault.")
    parser.add_argument("--apply", action="store_true", help="Remove non-protected transient candidates.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeCleanTransientRequest(
            vault=vault,
            apply=args.apply,
            out_path=args.out,
            status_report_path=args.status_report,
            policy_path=args.policy_path,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
