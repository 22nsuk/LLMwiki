from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.codex_goal_client import DEFAULT_CONTRACT_PATH, FileGoalBackend
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "ops/reports/codex-goal-prompt.json"
PRODUCER = "ops.scripts.codex_goal_prompt"
SCHEMA_PATH = "ops/schemas/codex-goal-prompt.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.codex_goal_prompt --vault ."


def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _goal_path_items(items: object, *, path_key: str = "path") -> list[str]:
    if not isinstance(items, list):
        return []
    paths: list[str] = []
    for item in items:
        if isinstance(item, Mapping):
            path = str(item.get(path_key, "")).strip()
            if path:
                paths.append(path)
    return paths


def _budget_value(budgets: Mapping[str, Any], key: str) -> int:
    value = budgets.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else 1


def build_prompt_text(contract: Mapping[str, Any]) -> str:
    budgets = _mapping_value(contract, "budgets")
    runtime_profile = _mapping_value(contract, "runtime_profile")
    promotion_guard = _mapping_value(contract, "promotion_guard")
    goal_backend = _mapping_value(contract, "goal_backend")
    allowed_roots = _goal_path_items(contract.get("allowed_roots"))
    required_evidence = _goal_path_items(contract.get("required_evidence"))
    promotion_blockers = _list_text(promotion_guard.get("promotion_blockers"))
    can_promote_result = bool(promotion_guard.get("can_promote_result", False))
    profile_verified = str(promotion_guard.get("profile_verified", "")).strip()

    lines = [
        "You are Codex continuing a bounded auto-improve goal for this repository.",
        "",
        "Goal contract:",
        f"- contract_id: {str(contract.get('contract_id', '')).strip()}",
        f"- status: {str(contract.get('status', '')).strip()}",
        f"- profile: {str(runtime_profile.get('current_profile', '')).strip()}",
        f"- backend_storage: {str(goal_backend.get('storage_path', '')).strip()}",
        "",
        "Objective:",
        str(contract.get("objective", "")).strip(),
        "",
        "Budget limits:",
        f"- max_wall_clock_seconds: {_budget_value(budgets, 'max_wall_clock_seconds')}",
        f"- max_unattended_seconds: {_budget_value(runtime_profile, 'max_unattended_seconds')}",
        f"- max_proposals: {_budget_value(budgets, 'max_proposals')}",
        f"- max_consecutive_failures: {_budget_value(budgets, 'max_consecutive_failures')}",
        f"- heartbeat_interval_seconds: {_budget_value(budgets, 'heartbeat_interval_seconds')}",
        f"- checkpoint_interval_seconds: {_budget_value(budgets, 'checkpoint_interval_seconds')}",
        "",
        "Allowed roots:",
        *[f"- {path}" for path in allowed_roots],
        "",
        "Required evidence:",
        *[f"- {path}" for path in required_evidence],
        "",
        "Promotion guard:",
        f"- can_promote_result: {str(can_promote_result).lower()}",
        f"- sealed_authority_clean: {str(bool(promotion_guard.get('sealed_authority_clean', False))).lower()}",
        f"- profile_verified: {profile_verified}",
    ]
    if can_promote_result:
        lines.extend(
            [
                "- promotion_allowed: true only for claims backed by current required evidence.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "PROMOTION BAN: can_promote_result=false.",
                "Do not promote release, learning, or improvement claims.",
                "Do not claim 5-day sustained operation.",
                "Do not call update_goal complete until blockers are cleared by evidence.",
                "",
                "Promotion blockers:",
                *[f"- {blocker}" for blocker in promotion_blockers],
            ]
        )
    if profile_verified != "5d_sustained":
        lines.extend(
            [
                "",
                "SUSTAINED CLAIM BAN: profile_verified is not 5d_sustained.",
                "Do not claim 5-day sustained operation until the full profile ladder is verified.",
            ]
        )
    lines.extend(
        [
            "",
            "Resume discipline:",
            "- Keep the same contract digest across resume.",
            "- Stop with time_budget_exhausted only when the wall-clock budget is reached.",
            "- Stop with proposal_budget_exhausted or failure_budget_exhausted when those separate caps are reached.",
            "- Write heartbeat, checkpoint, and status evidence before widening the run profile.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_report(
    vault: Path,
    *,
    goal_contract_path: str = DEFAULT_CONTRACT_PATH,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    backend = FileGoalBackend(vault=resolved_vault, contract_path=goal_contract_path)
    contract = backend.get_goal()
    budgets = _mapping_value(contract, "budgets")
    runtime_profile = _mapping_value(contract, "runtime_profile")
    promotion_guard = _mapping_value(contract, "promotion_guard")
    goal_backend = _mapping_value(contract, "goal_backend")
    prompt_text = build_prompt_text(contract)
    promotion_ban_required = not bool(promotion_guard.get("can_promote_result", False))
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="codex_goal_prompt",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/codex_goal_prompt.py",
                "ops/scripts/core/codex_goal_client.py",
                "ops/schemas/codex-goal-prompt.schema.json",
                "ops/schemas/codex-goal-contract.schema.json",
            ],
            file_inputs={"goal_contract": goal_contract_path},
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "goal_contract": {
            "path": report_path(resolved_vault, backend.destination),
            "contract_sha256": _canonical_json_digest(contract),
            "contract_id": str(contract.get("contract_id", "")).strip(),
            "status": str(contract.get("status", "")).strip(),
            "objective": str(contract.get("objective", "")).strip(),
            "current_profile": str(runtime_profile.get("current_profile", "")).strip(),
            "process_persistent_backend": bool(goal_backend.get("process_persistent", False)),
        },
        "budget": {
            "max_wall_clock_seconds": _budget_value(budgets, "max_wall_clock_seconds"),
            "max_unattended_seconds": _budget_value(runtime_profile, "max_unattended_seconds"),
            "max_proposals": _budget_value(budgets, "max_proposals"),
            "max_consecutive_failures": _budget_value(budgets, "max_consecutive_failures"),
            "heartbeat_interval_seconds": _budget_value(budgets, "heartbeat_interval_seconds"),
            "checkpoint_interval_seconds": _budget_value(budgets, "checkpoint_interval_seconds"),
        },
        "promotion_guard": {
            "can_promote_result": bool(promotion_guard.get("can_promote_result", False)),
            "promotion_ban_required": promotion_ban_required,
            "promotion_blockers": _list_text(promotion_guard.get("promotion_blockers")),
            "sealed_authority_clean": bool(promotion_guard.get("sealed_authority_clean", False)),
            "profile_verified": str(promotion_guard.get("profile_verified", "")).strip(),
            "sustained_runtime_claimed": bool(
                promotion_guard.get("sustained_runtime_claimed", False)
            ),
        },
        "prompt": {
            "text": prompt_text,
            "line_count": len(prompt_text.splitlines()),
            "includes_promotion_ban": "PROMOTION BAN: can_promote_result=false." in prompt_text,
            "includes_sustained_claim_ban": "SUSTAINED CLAIM BAN:" in prompt_text,
            "includes_budget_limits": "Budget limits:" in prompt_text,
            "includes_allowed_roots": "Allowed roots:" in prompt_text,
        },
        "status": "attention" if promotion_ban_required else "pass",
    }


def write_report(vault: Path, report: Mapping[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="codex goal prompt schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--goal-contract", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--policy", default=None, help="Policy path relative to the vault.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output path for the prompt report.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        goal_contract_path=args.goal_contract,
        policy_path=args.policy,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
