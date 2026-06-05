#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
else:
    from .output_runtime import display_path
    from .policy_runtime import load_policy
    from .runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/subagent-profile-schema.json"
DEFAULT_POLICY = "ops/policies/wiki-maintainer-policy.yaml"
PRODUCER = "ops.scripts.subagent_profile_schema"
SCHEMA_PATH = "ops/schemas/subagent-profile.schema.json"


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _profile_entry(vault: Path, path: Path, policy_roles: dict[str, Any]) -> dict[str, Any]:
    payload = _load_toml(path)
    rel_path = path.relative_to(vault).as_posix()
    name = str(payload.get("name", "")).strip()
    role_policy = policy_roles.get(name, {}) if name else {}
    return {
        "path": rel_path,
        "name": name,
        "description_present": bool(str(payload.get("description", "")).strip()),
        "model": str(payload.get("model", "")).strip(),
        "model_reasoning_effort": str(payload.get("model_reasoning_effort", "")).strip(),
        "sandbox_mode": str(payload.get("sandbox_mode", "")).strip(),
        "developer_instructions_present": bool(str(payload.get("developer_instructions", "")).strip()),
        "policy_role_declared": bool(role_policy),
        "default_rung": int(role_policy.get("default_rung", 0)) if role_policy else 0,
        "allowed_rungs": list(role_policy.get("allowed_rungs", [])) if role_policy else [],
    }


def build_report(
    vault: Path,
    *,
    policy_path: str = DEFAULT_POLICY,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    policy, _resolved_policy = load_policy(resolved_vault, policy_path)
    policy_roles = policy["subagent_routing_policy"]["roles"]
    profiles = [
        _profile_entry(resolved_vault, path, policy_roles)
        for path in sorted((resolved_vault / ".codex" / "agents").glob("*.toml"))
    ]
    profile_roles = {entry["name"] for entry in profiles if entry["name"]}
    policy_role_names = set(policy_roles)
    missing_profiles = sorted(policy_role_names - profile_roles)
    extra_profiles = sorted(profile_roles - policy_role_names)
    incomplete_profiles = [
        entry["path"]
        for entry in profiles
        if not entry["description_present"] or not entry["developer_instructions_present"]
    ]
    status = "pass" if not missing_profiles and not extra_profiles and not incomplete_profiles else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "subagent_profile_schema",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": status,
        "summary": {
            "profile_count": len(profiles),
            "policy_role_count": len(policy_role_names),
            "missing_profile_count": len(missing_profiles),
            "extra_profile_count": len(extra_profiles),
            "incomplete_profile_count": len(incomplete_profiles),
        },
        "profiles": profiles,
        "missing_profiles": missing_profiles,
        "extra_profiles": extra_profiles,
        "incomplete_profiles": incomplete_profiles,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate subagent TOML profiles against routing policy roles.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default=DEFAULT_POLICY)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
