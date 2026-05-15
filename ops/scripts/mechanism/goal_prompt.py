from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ops.scripts.output_runtime import write_output_text


PROMOTION_BAN_HEADER = "PROMOTION BAN"


def promotion_ban_lines(contract: dict[str, Any]) -> list[str]:
    policy = contract.get("promotion_policy")
    policy = policy if isinstance(policy, dict) else {}
    can_promote = bool(policy.get("can_promote_result", False))
    requires_clean = bool(policy.get("requires_sealed_authority_clean_pass", True))
    reason = str(policy.get("promotion_ban_reason", "")).strip()
    if can_promote and not requires_clean:
        return []
    return [
        f"{PROMOTION_BAN_HEADER}: do not promote, release, or claim a learning improvement.",
        "Promotion remains forbidden until can_promote_result=true and sealed authority clean pass are both current.",
        f"Reason: {reason or 'promotion gate is not explicitly open'}.",
    ]


def build_goal_prompt(contract: dict[str, Any]) -> str:
    objective = str(contract.get("objective", "")).strip()
    goal_id = str(contract.get("goal_id", "")).strip()
    ladder = contract.get("execution_ladder")
    ladder = ladder if isinstance(ladder, list) else []
    stop_conditions = contract.get("stop_conditions")
    stop_conditions = stop_conditions if isinstance(stop_conditions, list) else []
    lines = [
        f"Goal: {goal_id}",
        "",
        objective,
        "",
        *promotion_ban_lines(contract),
        "",
        "Execution ladder:",
    ]
    for item in ladder:
        if isinstance(item, dict):
            lines.append(
                "- {profile}: max_minutes={max_minutes}, max_proposals={max_proposals}".format(
                    profile=item.get("profile", ""),
                    max_minutes=item.get("max_minutes", ""),
                    max_proposals=item.get("max_proposals", ""),
                )
            )
    lines.append("")
    lines.append("Stop immediately on:")
    for condition in stop_conditions:
        lines.append(f"- {condition}")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a goal runtime prompt.")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    prompt = build_goal_prompt(contract)
    if args.out:
        write_output_text(Path(args.out), prompt)
    else:
        print(prompt, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
