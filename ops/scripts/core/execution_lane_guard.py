from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_POLICY = "ops/policies/execution-lanes.json"


def _load_policy(vault: Path, rel_path: str) -> dict[str, Any]:
    path = vault / rel_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"execution lane policy is unavailable: {rel_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"execution lane policy must be a JSON object: {rel_path}")
    return payload


def _path_exists(vault: Path, rel_path: str) -> bool:
    return (vault / rel_path).exists()


def detect_lane(vault: Path, policy: dict[str, Any]) -> str:
    lanes = policy.get("lanes")
    lane_payloads = lanes if isinstance(lanes, dict) else {}
    full_vault = lane_payloads.get("full_vault")
    source_package = lane_payloads.get("source_package_extract")
    full_sentinels = (
        full_vault.get("sentinels", []) if isinstance(full_vault, dict) else []
    )
    source_sentinels = (
        source_package.get("sentinels", []) if isinstance(source_package, dict) else []
    )
    if source_sentinels and any(_path_exists(vault, str(path)) for path in source_sentinels):
        return "source_package_extract"
    if full_sentinels and all(_path_exists(vault, str(path)) for path in full_sentinels):
        return "full_vault"
    return "public_or_partial_checkout"


def build_result(vault: Path, *, target: str, policy_path: str = DEFAULT_POLICY) -> dict[str, Any]:
    policy = _load_policy(vault, policy_path)
    targets = policy.get("targets")
    target_payloads = targets if isinstance(targets, dict) else {}
    target_policy = target_payloads.get(target)
    detected_lane = detect_lane(vault, policy)
    if not isinstance(target_policy, dict):
        return {
            "status": "pass",
            "target": target,
            "detected_lane": detected_lane,
            "required_lane": "",
            "blocked_lanes": [],
            "reason": "target has no execution lane restriction",
            "alternatives": [],
        }
    required_lane = str(target_policy.get("required_lane", "")).strip()
    blocked_lanes = [
        str(item).strip()
        for item in target_policy.get("blocked_lanes", [])
        if str(item).strip()
    ]
    if required_lane:
        status = "pass" if detected_lane == required_lane else "fail"
    elif blocked_lanes:
        status = "fail" if detected_lane in blocked_lanes else "pass"
    else:
        status = "pass"
    return {
        "status": status,
        "target": target,
        "detected_lane": detected_lane,
        "required_lane": required_lane,
        "blocked_lanes": blocked_lanes,
        "reason": str(target_policy.get("reason", "")).strip(),
        "alternatives": [str(item) for item in target_policy.get("alternatives", [])],
    }


def _failure_message(result: dict[str, Any]) -> str:
    alternatives = ", ".join(result["alternatives"]) or "none"
    if result.get("required_lane"):
        lane_clause = (
            f"requires {result['required_lane']} but detected {result['detected_lane']}"
        )
    else:
        blocked_lanes = ", ".join(result.get("blocked_lanes", [])) or "none"
        lane_clause = (
            f"is blocked in detected lane {result['detected_lane']} "
            f"(blocked lanes: {blocked_lanes})"
        )
    return (
        f"execution lane guard failed: target {result['target']} {lane_clause}. "
        f"{result['reason']} Alternatives: {alternatives}."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail fast when a Make target is run in the wrong execution lane.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default=DEFAULT_POLICY)
    parser.add_argument("--target", required=True)
    parser.add_argument("--json", action="store_true", help="Print the guard result as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    result = build_result(vault, target=args.target, policy_path=args.policy)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif result["status"] == "fail":
        print(_failure_message(result), file=sys.stderr)
    else:
        print(f"execution lane guard passed: {args.target} in {result['detected_lane']}")
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
