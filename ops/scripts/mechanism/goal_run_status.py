from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import read_json_object, write_schema_validated_json
from ops.scripts.output_runtime import write_output_text
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema

from .goal_worktree_guard import build_report as build_worktree_guard


GOAL_CONTRACT_SCHEMA = "ops/schemas/codex-goal-contract.schema.json"
GOAL_RUN_STATUS_SCHEMA = "ops/schemas/goal-run-status.schema.json"
GOAL_RESUME_METADATA_SCHEMA = "ops/schemas/goal-resume-metadata.schema.json"
DEFAULT_CONTRACT_PATH = "ops/reports/codex-goal-contract.json"
DEFAULT_STATUS_PATH = "ops/reports/goal-run-status.json"
DEFAULT_STATUS_MD_PATH = "ops/reports/goal-status.md"
DEFAULT_AUDIT_LOG_PATH = "ops/reports/goal-audit-log.jsonl"
DEFAULT_CHECKPOINTS_DIR = "ops/reports/goal-checkpoints"
DEFAULT_RESUME_METADATA_PATH = "ops/reports/goal-resume-metadata.json"
PRODUCER = "ops.scripts.goal_run_status"
POLICY_PATH = "ops/policies/wiki-maintainer-policy.yaml"


def _canonical_envelope(
    vault: Path,
    *,
    generated_at: str,
    artifact_kind: str,
    schema_path: str,
    source_command: str,
    source_paths: list[str],
    file_inputs: dict[str, str | Path] | None = None,
    text_inputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, POLICY_PATH)
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=artifact_kind,
        producer=PRODUCER,
        source_command=source_command,
        resolved_policy_path=resolved_policy_path,
        schema_path=schema_path,
        source_paths=source_paths,
        file_inputs=file_inputs,
        text_inputs=text_inputs,
    )


def _goal_contract_envelope(vault: Path, contract: dict[str, Any]) -> dict[str, Any]:
    return _canonical_envelope(
        vault,
        generated_at=str(contract["created_at"]),
        artifact_kind="codex_goal_contract",
        schema_path=GOAL_CONTRACT_SCHEMA,
        source_command="python -m ops.scripts.goal_run_status init",
        source_paths=[
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_worktree_guard.py",
            GOAL_CONTRACT_SCHEMA,
        ],
        text_inputs={
            "goal_id": str(contract["goal_id"]),
            "repo_url": str(contract["github"]["repo_url"]),
            "visibility": str(contract["github"]["visibility"]),
            "baseline_commit": str(contract["github"]["baseline_commit"]),
            "branch": str(contract["github"]["branch"]),
            "worktree_path": str(contract["github"]["worktree_path"]),
        },
    )


def _status_source_command(event: str) -> str:
    if event in {"heartbeat", "checkpoint"}:
        return f"python -m ops.scripts.goal_run_status {event}"
    return "python -m ops.scripts.goal_run_status init"


def _goal_status_envelope(vault: Path, status: dict[str, Any], *, event: str) -> dict[str, Any]:
    return _canonical_envelope(
        vault,
        generated_at=str(status["generated_at"]),
        artifact_kind="goal_run_status",
        schema_path=GOAL_RUN_STATUS_SCHEMA,
        source_command=_status_source_command(event),
        source_paths=[
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_worktree_guard.py",
            GOAL_RUN_STATUS_SCHEMA,
        ],
        file_inputs={"goal_contract": DEFAULT_CONTRACT_PATH},
        text_inputs={
            "event": event,
            "goal_id": str(status["goal_id"]),
            "active_profile": str(status["active_profile"]),
            "repo_url": str(status["repo"]["repo_url"]),
            "visibility": str(status["repo"]["visibility"]),
            "baseline_commit": str(status["repo"]["baseline_commit"]),
            "branch": str(status["repo"]["branch"]),
            "worktree_path": str(status["repo"]["worktree_path"]),
        },
    )


def _resume_metadata_envelope(
    vault: Path,
    metadata: dict[str, Any],
    *,
    generated_at: str,
    event: str,
) -> dict[str, Any]:
    return _canonical_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="goal_resume_metadata",
        schema_path=GOAL_RESUME_METADATA_SCHEMA,
        source_command=_status_source_command(event),
        source_paths=[
            "ops/scripts/mechanism/goal_run_status.py",
            GOAL_RESUME_METADATA_SCHEMA,
        ],
        file_inputs={"goal_status": str(metadata["status_json"])},
        text_inputs={
            "event": event,
            "goal_id": str(metadata["goal_id"]),
            "active_profile": str(metadata["active_profile"]),
            "last_checkpoint": str(metadata["last_checkpoint"]),
        },
    )


def default_goal_contract(
    *,
    context: RuntimeContext,
    repo_url: str,
    visibility: str,
    baseline_commit: str,
    branch: str,
    worktree_path: str,
) -> dict[str, Any]:
    return {
        "$schema": GOAL_CONTRACT_SCHEMA,
        "artifact_kind": "codex_goal_contract",
        "schema_version": 1,
        "goal_id": "goal-20260515-5day-auto-improve-runtime",
        "objective": (
            "Build and operate a five-day bounded auto-improve goal runtime with "
            "clean release evidence, private GitHub baseline, resumable audit trail, "
            "heartbeats, checkpoints, and no promotion until sealed authority is clean."
        ),
        "status": "running",
        "created_at": context.isoformat_z(),
        "duration": {
            "min_sustained_days": 5,
            "max_minutes": 7200,
        },
        "budgets": {
            "max_proposals": 60,
            "max_consecutive_failures": 1,
            "heartbeat_interval_minutes": 5,
            "checkpoint_interval_minutes": 30,
            "readiness_interval_hours": 6,
            "session_synopsis_interval_hours": 6,
        },
        "promotion_policy": {
            "can_promote_result": False,
            "requires_sealed_authority_clean_pass": True,
            "promotion_ban_reason": (
                "Promotion remains forbidden until can_promote_result=true and "
                "sealed authority clean pass are both current."
            ),
        },
        "github": {
            "repo_url": repo_url,
            "visibility": visibility,
            "baseline_commit": baseline_commit,
            "branch": branch,
            "worktree_path": worktree_path,
        },
        "artifacts": {
            "status_json": DEFAULT_STATUS_PATH,
            "status_markdown": DEFAULT_STATUS_MD_PATH,
            "audit_log": DEFAULT_AUDIT_LOG_PATH,
            "checkpoints_dir": DEFAULT_CHECKPOINTS_DIR,
            "resume_metadata": DEFAULT_RESUME_METADATA_PATH,
        },
        "execution_ladder": [
            {
                "profile": "30-minute-trial",
                "max_minutes": 30,
                "max_proposals": 1,
                "max_consecutive_failures": 1,
                "checkpoint_interval_minutes": 30,
            },
            {
                "profile": "6-hour-ramp",
                "max_minutes": 360,
                "max_proposals": 6,
                "checkpoint_interval_minutes": 30,
            },
            {
                "profile": "2-day-candidate",
                "max_minutes": 2880,
                "max_proposals": 24,
                "checkpoint_interval_minutes": 30,
                "readiness_interval_hours": 6,
                "session_synopsis_interval_hours": 6,
            },
            {
                "profile": "5-day-sustained",
                "max_minutes": 7200,
                "max_proposals": 60,
                "max_consecutive_failures": 1,
                "heartbeat_interval_minutes": 5,
                "checkpoint_interval_minutes": 30,
                "readiness_interval_hours": 6,
                "session_synopsis_interval_hours": 6,
            },
        ],
        "stop_conditions": [
            "allowed-root violation",
            "repeated blocker cannot be converted to remediation backlog",
            "status, audit, or heartbeat write failure",
            "sealed authority or readiness regression",
            "any need to bypass release, promotion, or learning-claim gates",
        ],
    }


def _profile_budget(contract: dict[str, Any], active_profile: str) -> dict[str, int]:
    for item in contract.get("execution_ladder", []):
        if isinstance(item, dict) and item.get("profile") == active_profile:
            return {
                "max_minutes": int(item.get("max_minutes", contract["duration"]["max_minutes"])),
                "max_proposals": int(item.get("max_proposals", contract["budgets"]["max_proposals"])),
                "max_consecutive_failures": int(
                    item.get(
                        "max_consecutive_failures",
                        contract["budgets"]["max_consecutive_failures"],
                    )
                ),
            }
    return {
        "max_minutes": int(contract["duration"]["max_minutes"]),
        "max_proposals": int(contract["budgets"]["max_proposals"]),
        "max_consecutive_failures": int(contract["budgets"]["max_consecutive_failures"]),
    }


def _heartbeat_status(contract: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
    interval = int(contract["budgets"]["heartbeat_interval_minutes"])
    return {
        "interval_minutes": interval,
        "last_heartbeat_at": context.isoformat_z(),
        "stale_after_minutes": interval * 2,
        "status": "fresh",
    }


def _worktree_guard_summary(vault: Path, contract: dict[str, Any]) -> dict[str, str]:
    report = build_worktree_guard(
        vault,
        expected_branch=str(contract["github"]["branch"]),
    )
    return {
        "status": str(report.get("status", "fail")),
        "mode": str(report.get("mode", "unknown")),
        "reason": str(report.get("reason", "")),
    }


def _build_status_from_contract(
    vault: Path,
    contract: dict[str, Any],
    *,
    context: RuntimeContext,
    active_profile: str = "5-day-sustained",
    status: str = "initialized",
    last_event: str = "initialized",
    reason: str = "goal runtime status initialized",
) -> dict[str, Any]:
    policy = contract["promotion_policy"]
    return {
        "$schema": GOAL_RUN_STATUS_SCHEMA,
        "artifact_kind": "goal_run_status",
        "schema_version": 1,
        "generated_at": context.isoformat_z(),
        "producer": PRODUCER,
        "goal_id": contract["goal_id"],
        "objective": contract["objective"],
        "status": status,
        "active_profile": active_profile,
        "repo": {
            **contract["github"],
            "worktree_guard": _worktree_guard_summary(vault, contract),
        },
        "budget": _profile_budget(contract, active_profile),
        "progress": {
            "iterations_completed": 0,
            "proposals_attempted": 0,
            "consecutive_failures": 0,
            "elapsed_minutes": 0,
        },
        "heartbeat": _heartbeat_status(contract, context),
        "promotion_policy": {
            "can_promote_result": bool(policy["can_promote_result"]),
            "requires_sealed_authority_clean_pass": bool(
                policy["requires_sealed_authority_clean_pass"]
            ),
            "promotion_ban_active": not bool(policy["can_promote_result"]),
            "promotion_ban_reason": str(policy["promotion_ban_reason"]),
        },
        "artifacts": contract["artifacts"],
        "checkpoints": [],
        "resume": {
            "resume_supported": True,
            "resume_metadata": contract["artifacts"]["resume_metadata"],
            "last_checkpoint": "",
        },
        "stop_conditions": list(contract["stop_conditions"]),
        "last_event": {
            "at": context.isoformat_z(),
            "event": last_event,
            "reason": reason,
        },
    }


def _write_status_markdown(vault: Path, status: dict[str, Any]) -> None:
    path = vault / status["artifacts"]["status_markdown"]
    repo = status["repo"]
    progress = status["progress"]
    text = "\n".join(
        [
            f"# {status['goal_id']}",
            "",
            f"- status: `{status['status']}`",
            f"- active_profile: `{status['active_profile']}`",
            f"- repo: `{repo['repo_url']}`",
            f"- visibility: `{repo['visibility']}`",
            f"- branch: `{repo['branch']}`",
            f"- baseline_commit: `{repo['baseline_commit']}`",
            f"- worktree_path: `{repo['worktree_path']}`",
            f"- worktree_guard: `{repo['worktree_guard']['status']}` / `{repo['worktree_guard']['mode']}`",
            f"- proposals_attempted: `{progress['proposals_attempted']}`",
            f"- consecutive_failures: `{progress['consecutive_failures']}`",
            f"- promotion_ban_active: `{status['promotion_policy']['promotion_ban_active']}`",
            "",
        ]
    )
    write_output_text(path, text)


def _append_audit_event(vault: Path, status: dict[str, Any], event: str, reason: str) -> None:
    audit_path = vault / status["artifacts"]["audit_log"]
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": status["generated_at"],
        "goal_id": status["goal_id"],
        "event": event,
        "reason": reason,
        "status": status["status"],
        "active_profile": status["active_profile"],
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_resume_metadata(vault: Path, status: dict[str, Any], *, event: str) -> None:
    path = vault / status["artifacts"]["resume_metadata"]
    metadata = {
        "goal_id": status["goal_id"],
        "resume_supported": True,
        "status_json": status["artifacts"]["status_json"],
        "last_checkpoint": status["resume"]["last_checkpoint"],
        "active_profile": status["active_profile"],
    }
    metadata.update(
        _resume_metadata_envelope(
            vault,
            metadata,
            generated_at=str(status["generated_at"]),
            event=event,
        )
    )
    write_schema_validated_json(
        path,
        metadata,
        load_schema(vault / GOAL_RESUME_METADATA_SCHEMA),
        context="goal resume metadata schema validation failed",
        trailing_newline=True,
    )


def write_goal_status(vault: Path, status: dict[str, Any], *, event: str, reason: str) -> Path:
    schema = load_schema(vault / GOAL_RUN_STATUS_SCHEMA)
    out = vault / status["artifacts"]["status_json"]
    status.update(_goal_status_envelope(vault, status, event=event))
    write_schema_validated_json(out, status, schema, context="goal run status schema validation failed")
    _write_status_markdown(vault, status)
    _append_audit_event(vault, status, event, reason)
    _write_resume_metadata(vault, status, event=event)
    return out


def write_checkpoint(vault: Path, status: dict[str, Any], *, reason: str) -> dict[str, Any]:
    checkpoint_dir = vault / status["artifacts"]["checkpoints_dir"]
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_name = f"checkpoint-{status['generated_at'].replace(':', '').replace('-', '')}.json"
    checkpoint_rel = f"{status['artifacts']['checkpoints_dir'].rstrip('/')}/{checkpoint_name}"
    status["checkpoints"].append(
        {
            "path": checkpoint_rel,
            "created_at": status["generated_at"],
            "reason": reason,
        }
    )
    status["resume"]["last_checkpoint"] = checkpoint_rel
    checkpoint = copy.deepcopy(status)
    checkpoint.update(_goal_status_envelope(vault, checkpoint, event="checkpoint"))
    checkpoint["last_event"] = {
        "at": status["generated_at"],
        "event": "checkpoint",
        "reason": reason,
    }
    write_schema_validated_json(
        vault / checkpoint_rel,
        checkpoint,
        load_schema(vault / GOAL_RUN_STATUS_SCHEMA),
        context="goal run checkpoint schema validation failed",
        trailing_newline=True,
    )
    return status


def initialize_goal_runtime(
    vault: Path,
    *,
    repo_url: str,
    visibility: str,
    baseline_commit: str,
    branch: str,
    worktree_path: str,
    context: RuntimeContext | None = None,
    active_profile: str = "5-day-sustained",
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    contract = default_goal_contract(
        context=runtime_context,
        repo_url=repo_url,
        visibility=visibility,
        baseline_commit=baseline_commit,
        branch=branch,
        worktree_path=worktree_path,
    )
    contract.update(_goal_contract_envelope(vault, contract))
    write_schema_validated_json(
        vault / DEFAULT_CONTRACT_PATH,
        contract,
        load_schema(vault / GOAL_CONTRACT_SCHEMA),
        context="codex goal contract schema validation failed",
        trailing_newline=True,
    )
    status = _build_status_from_contract(
        vault,
        contract,
        context=runtime_context,
        active_profile=active_profile,
        status="initialized",
    )
    status = write_checkpoint(vault, status, reason="initial GitHub worktree registration")
    write_goal_status(vault, status, event="initialized", reason="goal runtime initialized")
    return status


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize or update goal runtime status artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--vault", default=".")
    init.add_argument("--repo-url", required=True)
    init.add_argument("--visibility", required=True, choices=["PRIVATE", "PUBLIC", "UNKNOWN"])
    init.add_argument("--baseline-commit", required=True)
    init.add_argument("--branch", required=True)
    init.add_argument("--worktree-path", required=True)
    init.add_argument("--active-profile", default="5-day-sustained")

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--vault", default=".")
    heartbeat.add_argument("--status", default=DEFAULT_STATUS_PATH)
    heartbeat.add_argument("--reason", default="heartbeat")

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--vault", default=".")
    checkpoint.add_argument("--status", default=DEFAULT_STATUS_PATH)
    checkpoint.add_argument("--reason", default="checkpoint")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    context = RuntimeContext(display_timezone=dt.timezone.utc)
    if args.command == "init":
        status = initialize_goal_runtime(
            vault,
            repo_url=args.repo_url,
            visibility=args.visibility,
            baseline_commit=args.baseline_commit,
            branch=args.branch,
            worktree_path=args.worktree_path,
            context=context,
            active_profile=args.active_profile,
        )
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    status = read_json_object(vault / args.status)
    status["generated_at"] = context.isoformat_z()
    status["heartbeat"] = _heartbeat_status(
        {
            "budgets": {
                "heartbeat_interval_minutes": status["heartbeat"]["interval_minutes"],
            }
        },
        context,
    )
    if args.command == "checkpoint":
        status = write_checkpoint(vault, status, reason=args.reason)
    status["last_event"] = {
        "at": context.isoformat_z(),
        "event": args.command,
        "reason": args.reason,
    }
    write_goal_status(vault, status, event=args.command, reason=args.reason)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
