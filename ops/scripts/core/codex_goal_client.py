from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Protocol, cast

from .artifact_freshness_runtime import (
    build_canonical_report_envelope,
    embed_artifact_envelope_metadata,
)
from .artifact_io_runtime import load_optional_json_object, read_json_object, write_json_object
from .output_runtime import display_path, resolve_repo_output_path
from .policy_runtime import load_policy
from .schema_runtime import load_schema_with_vault_override, validate_with_schema


DEFAULT_CONTRACT_PATH = "ops/reports/codex-goal-contract.json"
SCHEMA_PATH = "ops/schemas/codex-goal-contract.schema.json"
DEFAULT_CONTRACT_ID = "auto-improve-goal"
PRODUCER = "ops.scripts.codex_goal_client"
SOURCE_COMMAND = "python -m ops.scripts.codex_goal_client --vault ."
DEFAULT_RUNTIME_MODE = "self_improvement_loop"
RUNTIME_MODES = (DEFAULT_RUNTIME_MODE,)
DEFAULT_RUNTIME_SECONDS = 21600
DEFAULT_READINESS_REPORT_PATH = "ops/reports/auto-improve-readiness.json"
SEALED_PREFLIGHT_REPORT_PATH = "ops/reports/release-closeout-sealed-rehearsal-check.json"
DEFAULT_WORKTREE_GUARD_REPORT_PATH = "tmp/goal-worktree-guard.json"
DEFAULT_GOAL_STATUS_PATH = "ops/reports/goal-run-status.json"
GOAL_BACKEND_TYPES = ("file", "run_local_file", "app_server")
TERMINAL_QUEUE_BLOCKERS = {
    "execution_blocked_by_no_runnable_proposal",
    "learning_blocked_by_execution_not_runnable",
}
TERMINAL_QUEUE_STOP_REASONS = {"queue_exhausted", "proposal_budget_exhausted"}


class GoalBackendError(RuntimeError):
    """Base error for local Codex goal backend operations."""


class GoalBackendUnavailableError(GoalBackendError):
    """Raised when no allowed goal backend can be selected."""


class GoalContractValidationError(GoalBackendError):
    """Raised when a goal contract does not satisfy the schema."""


class GoalBackend(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def process_persistent(self) -> bool:
        ...

    def get_goal(self) -> dict[str, Any]:
        ...

    def set_goal(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def update_goal(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        ...


def _copy_json_object(payload: Mapping[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], deepcopy(dict(payload)))


def _validate_contract(vault: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    contract = _copy_json_object(payload)
    schema = load_schema_with_vault_override(vault, SCHEMA_PATH)
    issues = validate_with_schema(contract, schema)
    if issues:
        raise GoalContractValidationError(
            "codex goal contract validation failed: " + "; ".join(issues)
        )
    return contract


def _merge_json_objects(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = _copy_json_object(base)
    for key, value in patch.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            merged[key] = _merge_json_objects(existing, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _utc_now() -> str:
    injected = os.environ.get("LLMWIKI_RUNTIME_UTC_NOW", "").strip()
    if injected:
        try:
            parsed = dt.datetime.fromisoformat(injected.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return (
                parsed.astimezone(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _existing_created_at(vault: Path, contract_path: str | Path, contract_id: str) -> str:
    destination = resolve_repo_output_path(
        vault,
        contract_path,
        default_relative_path=DEFAULT_CONTRACT_PATH,
    )
    existing = load_optional_json_object(destination)
    if existing.get("contract_id") != contract_id:
        return ""
    created_at = existing.get("created_at")
    return created_at if isinstance(created_at, str) and created_at.strip() else ""


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        unique.append(normalized)
        seen.add(normalized)
    return unique


def _existing_contract_for_same_id(
    vault: Path,
    contract_path: str | Path,
    contract_id: str,
) -> Mapping[str, Any]:
    destination = resolve_repo_output_path(
        vault,
        contract_path,
        default_relative_path=DEFAULT_CONTRACT_PATH,
    )
    existing = load_optional_json_object(destination)
    if existing.get("contract_id") != contract_id:
        return {}
    return existing


def _runtime_certificate_status(value: object) -> str:
    status = str(value or "").strip()
    return status if status in {"unverified", "verified"} else "unverified"


def _preserve_existing_runtime_state(
    contract: Mapping[str, Any],
    existing_contract: Mapping[str, Any],
) -> dict[str, Any]:
    merged = _copy_json_object(contract)
    if not existing_contract:
        return merged
    existing_objective = existing_contract.get("objective")
    if isinstance(existing_objective, str) and existing_objective.strip():
        merged["objective"] = existing_objective
    existing_metadata = existing_contract.get("metadata")
    if isinstance(existing_metadata, Mapping):
        merged["metadata"] = _copy_json_object(existing_metadata)
    existing_runtime = _mapping_value(existing_contract, "runtime")
    runtime = dict(_mapping_value(merged, "runtime"))
    runtime["certificate_status"] = _runtime_certificate_status(
        existing_runtime.get("certificate_status")
    )
    existing_verified_at = str(existing_runtime.get("verified_at", "")).strip()
    if existing_verified_at and runtime["certificate_status"] == "verified":
        runtime["verified_at"] = existing_verified_at
    merged["runtime"] = runtime

    existing_guard = _mapping_value(existing_contract, "promotion_guard")
    promotion_guard = dict(_mapping_value(merged, "promotion_guard"))
    promotion_guard["runtime_certificate_verified"] = (
        runtime["certificate_status"] == "verified"
    )
    promotion_guard["sustained_runtime_claimed"] = (
        bool(existing_guard.get("sustained_runtime_claimed", False))
        and runtime["certificate_status"] == "verified"
        and bool(promotion_guard.get("can_promote_result", False))
        and bool(promotion_guard.get("sealed_authority_clean", False))
    )
    merged["promotion_guard"] = promotion_guard
    return merged


def _promotion_blocker_ids(readiness: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for item in readiness.get("promotion_blockers", []):
        if not isinstance(item, Mapping):
            continue
        blocker_id = str(item.get("id", "")).strip()
        if blocker_id:
            blockers.append(blocker_id)
    return blockers


def _successful_session_iteration(iteration: Mapping[str, Any]) -> bool:
    return (
        str(iteration.get("decision", "")).strip() == "PROMOTE"
        or str(iteration.get("outcome", "")).strip() == "promoted"
        or str(iteration.get("status", "")).strip() == "promoted"
    )


def _session_report_path_from_status(status_report: Mapping[str, Any]) -> str:
    run_id = str(_mapping_value(status_report, "run").get("run_id", "")).strip()
    return f"ops/reports/auto-improve-sessions/{run_id}.json" if run_id else ""


def _completed_self_improvement_terminal_queue(
    vault: Path,
    *,
    goal_status_path: str,
) -> bool:
    status_report = load_optional_json_object(vault / goal_status_path)
    run = _mapping_value(status_report, "run")
    if str(run.get("status", "")).strip() != "completed":
        return False
    if str(run.get("runtime_mode", "")).strip() != DEFAULT_RUNTIME_MODE:
        return False
    session_report_path = _session_report_path_from_status(status_report)
    if not session_report_path:
        return False
    session = load_optional_json_object(vault / session_report_path)
    if str(session.get("status", "")).strip() != "complete":
        return False
    if str(session.get("stop_reason", "")).strip() not in TERMINAL_QUEUE_STOP_REASONS:
        return False
    iterations = session.get("iterations")
    if not isinstance(iterations, list):
        return False
    return any(
        _successful_session_iteration(iteration)
        for iteration in iterations
        if isinstance(iteration, Mapping)
    )


def _worktree_guard_promotion_blockers(
    vault: Path,
    worktree_guard_report_path: str,
) -> list[str]:
    if not worktree_guard_report_path.strip():
        return []
    guard_path = resolve_repo_output_path(
        vault,
        worktree_guard_report_path,
        default_relative_path=DEFAULT_WORKTREE_GUARD_REPORT_PATH,
    )
    guard = load_optional_json_object(guard_path)
    if not guard:
        return ["goal_worktree_guard_missing"]
    if guard.get("artifact_kind") != "goal_worktree_guard":
        return ["goal_worktree_guard_invalid"]
    decisions = _mapping_value(guard, "decisions")
    if bool(decisions.get("can_promote_result", False)):
        return []
    blockers = _list_text(decisions.get("promotion_blockers"))
    blockers.extend(_list_text(decisions.get("fatal_blockers")))
    if not blockers:
        blockers.append("goal_worktree_guard_not_promotable")
    return _unique_text(blockers)


def _preflight_is_clean(preflight: Mapping[str, Any]) -> bool:
    return (
        preflight.get("artifact_kind") == "release_closeout_sealed_rehearsal_check"
        and preflight.get("status") == "pass"
        and preflight.get("preflight_status") == "sealed_clean_pass"
        and preflight.get("distribution_binding_status") == "pass"
        and preflight.get("authority_preflight_status") == "clean"
    )


def promotion_guard_from_readiness(
    vault: Path,
    *,
    readiness_report_path: str = DEFAULT_READINESS_REPORT_PATH,
    worktree_guard_report_path: str = "",
    goal_status_path: str = DEFAULT_GOAL_STATUS_PATH,
) -> dict[str, Any] | None:
    readiness = load_optional_json_object(vault / readiness_report_path)
    if not readiness:
        return None
    diagnostics = _mapping_value(readiness, "diagnostics")
    preflight = _mapping_value(diagnostics, "release_authority_preflight_summary")
    if not preflight:
        preflight = load_optional_json_object(vault / SEALED_PREFLIGHT_REPORT_PATH)
    sealed_clean = _preflight_is_clean(preflight)
    readiness_promotes = bool(readiness.get("can_promote_result", False))
    blockers = [] if readiness_promotes else _promotion_blocker_ids(readiness)
    terminal_queue_completed = _completed_self_improvement_terminal_queue(
        vault,
        goal_status_path=goal_status_path,
    )
    if terminal_queue_completed:
        blockers = [
            blocker for blocker in blockers if blocker not in TERMINAL_QUEUE_BLOCKERS
        ]
    terminal_queue_promotes = terminal_queue_completed and not blockers
    can_promote = (readiness_promotes or terminal_queue_promotes) and sealed_clean
    worktree_guard_blockers = _worktree_guard_promotion_blockers(
        vault,
        worktree_guard_report_path,
    )
    if worktree_guard_blockers:
        can_promote = False
        blockers.extend(worktree_guard_blockers)
    if not can_promote and not blockers:
        blockers = [
            "sealed authority clean pass not verified"
            if not sealed_clean
            else "can_promote_result not verified"
        ]
    blockers = _unique_text(blockers)
    return {
        "can_promote_result": can_promote,
        "promotion_blockers": blockers,
        "sealed_authority_clean": sealed_clean,
        "runtime_certificate_verified": False,
        "sustained_runtime_claimed": False,
        "no_sustained_claim_before_certificate_verified": True,
    }


def build_auto_improve_goal_contract(
    *,
    contract_id: str = DEFAULT_CONTRACT_ID,
    created_at: str | None = None,
    created_by: str = "codex",
    storage_path: str = DEFAULT_CONTRACT_PATH,
    backend_type: str = "file",
    runtime_mode: str = DEFAULT_RUNTIME_MODE,
    max_unattended_seconds: int = DEFAULT_RUNTIME_SECONDS,
    max_proposals: int = 1,
    max_consecutive_failures: int = 1,
    heartbeat_interval_seconds: int = 300,
    checkpoint_interval_seconds: int = 1800,
    goal_status_path: str = DEFAULT_GOAL_STATUS_PATH,
    promotion_guard: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if runtime_mode not in RUNTIME_MODES:
        raise GoalBackendError(f"unsupported goal runtime mode: {runtime_mode}")
    if backend_type not in GOAL_BACKEND_TYPES:
        raise GoalBackendError(f"unsupported goal backend type: {backend_type}")
    default_promotion_guard = {
        "can_promote_result": False,
        "promotion_blockers": [
            "self-improvement loop certificate incomplete",
            "sealed authority clean pass not verified",
        ],
        "sealed_authority_clean": False,
        "runtime_certificate_verified": False,
        "sustained_runtime_claimed": False,
        "no_sustained_claim_before_certificate_verified": True,
    }
    if promotion_guard is not None:
        default_promotion_guard.update(dict(promotion_guard))
    return {
        "$schema": SCHEMA_PATH,
        "schema_version": 1,
        "contract_id": contract_id,
        "objective": (
            "Run a bounded self-improvement loop whose result is certified by current "
            "readiness, release, source-package, public-check, status, and session evidence."
        ),
        "non_goals": [
            "Do not treat wall-clock duration as proof without the self-improvement loop certificate.",
            "Do not treat native Codex goal state as durable proof without file-backed goal, status, checkpoint, and certificate evidence.",
            "Do not promote release, learning, or improvement claims while promotion blockers remain.",
            "Do not mutate private corpus surfaces from a public/runtime maintenance goal.",
        ],
        "allowed_roots": [
            {"path": "ops/", "purpose": "runtime, schemas, policies, reports, and scripts"},
            {"path": "tests/", "purpose": "deterministic regression coverage"},
            {"path": "mk/", "purpose": "Make target orchestration"},
            {"path": ".github/", "purpose": "CI workflow contract"},
            {"path": ".codex/agents/", "purpose": "shared subagent profile surface"},
            {"path": "README.md", "purpose": "operator-facing runtime contract"},
            {"path": "ops/README.md", "purpose": "ops-layer runtime contract"},
        ],
        "budgets": {
            "max_wall_clock_seconds": max_unattended_seconds,
            "max_proposals": max_proposals,
            "max_consecutive_failures": max_consecutive_failures,
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
            "checkpoint_interval_seconds": checkpoint_interval_seconds,
        },
        "created_at": created_at or _utc_now(),
        "created_by": created_by,
        "status": "active",
        "runtime": {
            "mode": runtime_mode,
            "duration_seconds": max_unattended_seconds,
            "max_unattended_seconds": max_unattended_seconds,
            "certificate_status": "unverified",
            "verified_at": "",
        },
        "goal_backend": {
            "backend_type": backend_type,
            "process_persistent": True,
            "storage_path": storage_path,
        },
        "stop_conditions": [
            {
                "condition_id": "promotion_guard_blocked",
                "description": "Stop before any promotion or learning claim while blockers remain.",
                "severity": "stop",
            },
            {
                "condition_id": "runtime_budget_exhausted",
                "description": "Pause when the runtime wall-clock or proposal budget is exhausted.",
                "severity": "pause",
            },
            {
                "condition_id": "sealed_authority_not_clean",
                "description": "Require review when sealed authority or can_promote_result is not clean.",
                "severity": "require_review",
            },
        ],
        "required_evidence": [
            {
                "evidence_id": "auto_improve_readiness",
                "path": "ops/reports/auto-improve-readiness.json",
                "description": "Readiness separates trial execution from result promotion.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "goal_run_status",
                "path": goal_status_path,
                "description": "Goal status records heartbeat, checkpoint, resume, and promotion blockers.",
                "freshness": "current_run",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "session_synopsis",
                "path": "ops/reports/session-synopsis.json",
                "description": "Session synopsis confirms the loop state, blockers, and next action.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "remediation_backlog",
                "path": "ops/reports/remediation-backlog.json",
                "description": "Remediation backlog must agree with readiness and session state.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "source_package_clean_extract",
                "path": "ops/reports/source-package-clean-extract.json",
                "description": "Source package replay proves packaged-copy parity for the loop output.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "public_check_summary",
                "path": "ops/reports/public-check-summary.json",
                "description": "Public mirror checks must pass for the loop output.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "release_authority",
                "path": "ops/reports/release-closeout-summary.json",
                "description": "Release authority blocks promotion until machine release is allowed.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
            {
                "evidence_id": "goal_worktree_guard",
                "path": DEFAULT_WORKTREE_GUARD_REPORT_PATH,
                "description": "Git/ZIP preflight blocks promotion from dirty, non-Git, or replay-only trees.",
                "freshness": "current_source_tree",
                "required_for_promotion": True,
            },
        ],
        "promotion_guard": default_promotion_guard,
        "metadata": {
            "contract_family": "bounded_auto_improve",
            "claim_policy": "loop_certificate_and_release_authority_required_for_claims",
        },
    }


@dataclass
class FakeGoalBackend:
    vault: Path = Path(".")
    name: str = "fake"
    process_persistent: bool = False
    _payload: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def get_goal(self) -> dict[str, Any]:
        if self._payload is None:
            raise GoalBackendUnavailableError("fake goal backend has no contract")
        return _copy_json_object(self._payload)

    def set_goal(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        payload = _validate_contract(self.vault, contract)
        self._payload = payload
        return _copy_json_object(payload)

    def update_goal(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        return self.set_goal(_merge_json_objects(self.get_goal(), patch))


@dataclass(frozen=True)
class FileGoalBackend:
    vault: Path
    contract_path: str | Path = DEFAULT_CONTRACT_PATH
    name: str = "file"
    process_persistent: bool = True

    @property
    def destination(self) -> Path:
        return resolve_repo_output_path(
            self.vault,
            self.contract_path,
            default_relative_path=DEFAULT_CONTRACT_PATH,
        )

    def get_goal(self) -> dict[str, Any]:
        path = self.destination
        if not path.is_file():
            raise GoalBackendUnavailableError(
                f"goal contract does not exist: {path.as_posix()}"
            )
        try:
            payload = read_json_object(path, context="codex goal contract")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GoalBackendError(f"failed to read goal contract: {exc}") from exc
        return _validate_contract(self.vault, payload)

    def set_goal(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        payload = _validate_contract(self.vault, contract)
        write_json_object(self.destination, payload, trailing_newline=True)
        return _copy_json_object(payload)

    def update_goal(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        return self.set_goal(_merge_json_objects(self.get_goal(), patch))


@dataclass(frozen=True)
class RunLocalFileGoalBackend(FileGoalBackend):
    name: str = "run_local_file"


def detect_goal_backend(
    *,
    backend: GoalBackend | None = None,
    vault: Path | str | None = None,
    contract_path: str | Path | None = None,
    allow_fake: bool = False,
) -> GoalBackend:
    if backend is not None:
        if not backend.process_persistent and not allow_fake:
            raise GoalBackendUnavailableError(
                "non-persistent goal backend requires allow_fake=True"
            )
        return backend
    if vault is not None:
        return FileGoalBackend(
            vault=Path(vault),
            contract_path=contract_path or DEFAULT_CONTRACT_PATH,
        )
    if contract_path is not None:
        raise GoalBackendUnavailableError(
            "contract_path requires an explicit vault for a process-persistent backend"
        )
    if allow_fake:
        return FakeGoalBackend()
    raise GoalBackendUnavailableError(
        "no process-persistent goal backend configured; pass vault or backend"
    )


def require_persistent_goal_backend(
    *,
    backend: GoalBackend | None = None,
    vault: Path | str | None = None,
    contract_path: str | Path | None = None,
) -> GoalBackend:
    selected = detect_goal_backend(
        backend=backend,
        vault=vault,
        contract_path=contract_path,
        allow_fake=False,
    )
    if not selected.process_persistent:
        raise GoalBackendUnavailableError("goal backend is not process-persistent")
    return selected


def set_goal(
    contract: Mapping[str, Any],
    *,
    backend: GoalBackend | None = None,
    vault: Path | str | None = None,
    contract_path: str | Path | None = None,
    allow_fake: bool = False,
) -> dict[str, Any]:
    selected = detect_goal_backend(
        backend=backend,
        vault=vault,
        contract_path=contract_path,
        allow_fake=allow_fake,
    )
    return selected.set_goal(contract)


def get_goal(
    *,
    backend: GoalBackend | None = None,
    vault: Path | str | None = None,
    contract_path: str | Path | None = None,
    allow_fake: bool = False,
) -> dict[str, Any]:
    selected = detect_goal_backend(
        backend=backend,
        vault=vault,
        contract_path=contract_path,
        allow_fake=allow_fake,
    )
    return selected.get_goal()


def update_goal(
    patch: Mapping[str, Any],
    *,
    backend: GoalBackend | None = None,
    vault: Path | str | None = None,
    contract_path: str | Path | None = None,
    allow_fake: bool = False,
) -> dict[str, Any]:
    selected = detect_goal_backend(
        backend=backend,
        vault=vault,
        contract_path=contract_path,
        allow_fake=allow_fake,
    )
    return selected.update_goal(patch)


def _embed_contract_artifact_envelope(
    vault: Path,
    contract: Mapping[str, Any],
    *,
    out_path: str,
    generated_at: str,
    readiness_report_path: str = DEFAULT_READINESS_REPORT_PATH,
    worktree_guard_report_path: str = "",
    goal_status_path: str = DEFAULT_GOAL_STATUS_PATH,
    readiness_sync_enabled: bool = True,
) -> dict[str, Any]:
    try:
        _policy, resolved_policy_path = load_policy(vault)
        file_inputs: dict[str, str] = {}
        if readiness_sync_enabled:
            file_inputs["auto_improve_readiness"] = readiness_report_path
            file_inputs["goal_run_status"] = goal_status_path
            status_report = load_optional_json_object(vault / goal_status_path)
            session_report_path = _session_report_path_from_status(status_report)
            if session_report_path:
                file_inputs["auto_improve_session"] = session_report_path
        if worktree_guard_report_path.strip():
            file_inputs["goal_worktree_guard_report"] = worktree_guard_report_path
        envelope = build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="codex_goal_contract",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/core/codex_goal_client.py",
                "ops/schemas/codex-goal-contract.schema.json",
            ],
            file_inputs=file_inputs,
            text_inputs={"contract_id": str(contract.get("contract_id", ""))},
            source_tree_excluded_files=(out_path,),
        )
    except (OSError, ValueError, json.JSONDecodeError, ModuleNotFoundError):
        return _copy_json_object(contract)
    return embed_artifact_envelope_metadata(_copy_json_object(contract), envelope)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_CONTRACT_PATH, help="Goal contract output path.")
    parser.add_argument("--contract-id", default=DEFAULT_CONTRACT_ID)
    parser.add_argument("--created-at", default="")
    parser.add_argument("--created-by", default="codex")
    parser.add_argument("--backend-type", choices=GOAL_BACKEND_TYPES, default="file")
    parser.add_argument("--runtime-mode", default=DEFAULT_RUNTIME_MODE)
    parser.add_argument("--current-profile", dest="runtime_mode", default=argparse.SUPPRESS)
    parser.add_argument("--max-unattended-seconds", type=int, default=DEFAULT_RUNTIME_SECONDS)
    parser.add_argument("--max-proposals", type=int, default=1)
    parser.add_argument("--max-consecutive-failures", type=int, default=1)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=300)
    parser.add_argument("--checkpoint-interval-seconds", type=int, default=1800)
    parser.add_argument("--goal-status-path", default=DEFAULT_GOAL_STATUS_PATH)
    parser.add_argument("--readiness-report", default=DEFAULT_READINESS_REPORT_PATH)
    parser.add_argument("--worktree-guard-report", default="")
    parser.add_argument("--no-readiness-sync", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    existing_contract = _existing_contract_for_same_id(vault, args.out, args.contract_id)
    promotion_guard = None
    if not args.no_readiness_sync:
        promotion_guard = promotion_guard_from_readiness(
            vault,
            readiness_report_path=args.readiness_report,
            worktree_guard_report_path=args.worktree_guard_report,
            goal_status_path=args.goal_status_path,
        )
    contract = build_auto_improve_goal_contract(
        contract_id=args.contract_id,
        created_at=args.created_at
        or _existing_created_at(vault, args.out, args.contract_id)
        or None,
        created_by=args.created_by,
        storage_path=args.out,
        backend_type=args.backend_type,
        runtime_mode=args.runtime_mode,
        max_unattended_seconds=args.max_unattended_seconds,
        max_proposals=args.max_proposals,
        max_consecutive_failures=args.max_consecutive_failures,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        checkpoint_interval_seconds=args.checkpoint_interval_seconds,
        goal_status_path=args.goal_status_path,
        promotion_guard=promotion_guard,
    )
    contract = _preserve_existing_runtime_state(contract, existing_contract)
    contract = _embed_contract_artifact_envelope(
        vault,
        contract,
        out_path=args.out,
        generated_at=_utc_now(),
        readiness_report_path=args.readiness_report,
        worktree_guard_report_path=args.worktree_guard_report,
        goal_status_path=args.goal_status_path,
        readiness_sync_enabled=not args.no_readiness_sync,
    )
    backend = FileGoalBackend(vault=vault, contract_path=args.out)
    backend.set_goal(contract)
    print(display_path(vault, backend.destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
