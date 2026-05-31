#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from ops.scripts.schema_constants_runtime import TEST_DESELECTION_POLICY_SCHEMA_PATH
from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_or_raise
from ops.scripts.test.test_execution_command_runtime import PYTEST_DESELECTED_RE
from ops.scripts.test.test_execution_selection_runtime import pytest_deselected_nodeids


def load_deselection_policy_payload(vault: Path, policy_path: str | None) -> dict[str, Any]:
    if not policy_path:
        return {}
    path = vault / policy_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = load_schema_with_vault_override(vault, TEST_DESELECTION_POLICY_SCHEMA_PATH)
    validate_or_raise(
        payload,
        schema,
        context=f"test deselection policy schema validation failed for {policy_path}",
    )
    return payload


def load_deselection_policy(vault: Path, policy_path: str | None) -> dict[str, dict[str, Any]]:
    payload = load_deselection_policy_payload(vault, policy_path)
    entries: dict[str, dict[str, Any]] = {}
    for item in payload.get("deselected_tests", []) if isinstance(payload.get("deselected_tests"), list) else []:
        if not isinstance(item, dict):
            continue
        nodeid = str(item.get("nodeid", "")).strip()
        if not nodeid:
            continue
        entries[nodeid] = item
    return entries


def parse_utc_timestamp(value: str, *, context: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context}: invalid ISO timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{context}: timestamp must include timezone")
    return parsed.astimezone(dt.UTC)


def deselection_lifecycle(
    deselected_tests: list[dict[str, Any]],
    *,
    generated_at: str,
    policy_payload: dict[str, Any],
) -> dict[str, Any]:
    checked_at = parse_utc_timestamp(generated_at, context="generated_at")
    budget = policy_payload.get("deselection_budget", {})
    if not isinstance(budget, dict):
        budget = {}
    max_count = int(budget.get("max_count", 0) or 0)
    policy_items = policy_payload.get("deselected_tests", [])
    policy_nodeids = [
        str(item.get("nodeid", "")).strip()
        for item in policy_items
        if isinstance(item, dict) and str(item.get("nodeid", "")).strip()
    ] if isinstance(policy_items, list) else []
    duplicate_count = len(policy_nodeids) - len(set(policy_nodeids))
    actual_nodeids = [str(item.get("nodeid", "")).strip() for item in deselected_tests if str(item.get("nodeid", "")).strip()]
    blockers: list[dict[str, Any]] = []
    expired_count = 0
    release_blocking_count = 0
    missing_lifecycle_count = 0
    for item in deselected_tests:
        nodeid = str(item.get("nodeid", "")).strip()
        risk_owner = str(item.get("risk_owner", "")).strip()
        expires_at = str(item.get("expires_at", "")).strip()
        if bool(item.get("release_blocking")):
            release_blocking_count += 1
        if not risk_owner or not expires_at:
            missing_lifecycle_count += 1
            blockers.append(
                {
                    "code": "missing_deselection_lifecycle",
                    "nodeid": nodeid,
                    "message": "Deselected test is missing risk_owner or expires_at.",
                }
            )
            continue
        if parse_utc_timestamp(expires_at, context=f"{nodeid}:expires_at") <= checked_at:
            expired_count += 1
            blockers.append(
                {
                    "code": "expired_deselection",
                    "nodeid": nodeid,
                    "message": f"Deselection expired at {expires_at}.",
                }
            )
        if bool(item.get("release_blocking")):
            blockers.append(
                {
                    "code": "release_blocking_deselection",
                    "nodeid": nodeid,
                    "message": "Deselected test is marked release blocking.",
                }
            )

    budget_expires_at = str(budget.get("expires_at", "")).strip()
    if budget_expires_at and parse_utc_timestamp(
        budget_expires_at,
        context="deselection_budget.expires_at",
    ) <= checked_at:
        blockers.append(
            {
                "code": "expired_deselection_budget",
                "nodeid": "",
                "message": f"Deselection budget expired at {budget_expires_at}.",
            }
        )
    if len(actual_nodeids) > max_count:
        blockers.append(
            {
                "code": "deselection_budget_exceeded",
                "nodeid": "",
                "message": f"Deselected test count {len(actual_nodeids)} exceeds max_count {max_count}.",
            }
        )
    if duplicate_count:
        blockers.append(
            {
                "code": "duplicate_deselection_policy_entry",
                "nodeid": "",
                "message": f"Deselection policy contains {duplicate_count} duplicate nodeid entries.",
            }
        )
    if actual_nodeids and not policy_payload:
        blockers.append(
            {
                "code": "missing_deselection_policy",
                "nodeid": "",
                "message": "Pytest command deselects tests without a structured deselection policy.",
            }
        )

    return {
        "status": "fail" if blockers else "pass",
        "checked_at": generated_at,
        "actual_deselected_count": len(actual_nodeids),
        "max_allowed_deselected_count": max_count,
        "over_budget": len(actual_nodeids) > max_count,
        "expired_count": expired_count,
        "release_blocking_count": release_blocking_count,
        "missing_lifecycle_count": missing_lifecycle_count,
        "duplicate_policy_entry_count": duplicate_count,
        "unused_policy_entry_count": len(set(policy_nodeids) - set(actual_nodeids)),
        "risk_owner": str(budget.get("risk_owner", "")).strip(),
        "expires_at": budget_expires_at,
        "count_increase_gate_effect": str(budget.get("count_increase_gate_effect", "")).strip(),
        "expiry_gate_effect": str(budget.get("expiry_gate_effect", "")).strip(),
        "next_action": "none" if not blockers else "refresh tests or renew/remove deselection policy entries",
        "blockers": blockers,
    }


def structured_deselected_tests(
    command: list[str],
    *,
    vault: Path,
    deselection_policy_path: str | None = None,
) -> list[dict[str, Any]]:
    policy = load_deselection_policy(vault, deselection_policy_path)
    entries: list[dict[str, Any]] = []
    for nodeid in pytest_deselected_nodeids(command):
        if nodeid in policy:
            item = policy[nodeid]
            entries.append(
                {
                    "nodeid": nodeid,
                    "reason": str(item["reason"]),
                    "policy_ref": str(item["policy_ref"]),
                    "risk_owner": str(item["risk_owner"]),
                    "expires_at": str(item["expires_at"]),
                    "release_blocking": bool(item["release_blocking"]),
                    "expected_to_pass_after_refresh": bool(item["expected_to_pass_after_refresh"]),
                }
            )
            continue
        if deselection_policy_path:
            raise ValueError(f"{nodeid}: missing structured test deselection policy entry")
        entries.append(
            {
                "nodeid": nodeid,
                "reason": "pytest command deselected this test without a structured policy entry",
                "policy_ref": "",
                "risk_owner": "",
                "expires_at": "",
                "release_blocking": True,
                "expected_to_pass_after_refresh": False,
            }
        )
    return entries


def pytest_stdout_deselected_count(stdout: str) -> int:
    total = 0
    for match in PYTEST_DESELECTED_RE.finditer(stdout):
        total = max(total, int(match.group("count")))
    return total
