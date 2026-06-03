from __future__ import annotations

import hashlib
import json
from typing import Any

REUSE_MISMATCH_SOURCE_TREE = "source_tree_mismatch"
REUSE_MISMATCH_SOURCE_REVISION = "source_revision_mismatch"
REUSE_MISMATCH_COMMAND_IDENTITY = "command_identity_mismatch"
REUSE_MISMATCH_INTERPRETER_TOOLCHAIN = "interpreter_toolchain_mismatch"
REUSE_MISMATCH_MISSING_SUMMARY = "missing_summary"
REUSE_MISMATCH_CODES = {
    REUSE_MISMATCH_SOURCE_TREE,
    REUSE_MISMATCH_SOURCE_REVISION,
    REUSE_MISMATCH_COMMAND_IDENTITY,
    REUSE_MISMATCH_INTERPRETER_TOOLCHAIN,
    REUSE_MISMATCH_MISSING_SUMMARY,
}


def _toolchain_fingerprint(execution_environment: dict[str, Any]) -> str:
    python_version = str(execution_environment.get("python_version", "")).strip()
    pytest_version = str(execution_environment.get("pytest_version", "")).strip()
    plugin_policy = execution_environment.get("plugin_autoload_policy", {})
    plugin_policy = plugin_policy if isinstance(plugin_policy, dict) else {}
    autoload_disabled = bool(plugin_policy.get("autoload_disabled"))
    raw = f"python={python_version}|pytest={pytest_version}|plugin_autoload_disabled={autoload_disabled}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _test_target_fingerprints_match(left: object, right: object) -> bool:
    if not isinstance(left, list) or not isinstance(right, list):
        return False
    left_items = sorted(
        (str(item.get("path", "")), str(item.get("sha256", "")))
        for item in left
        if isinstance(item, dict)
    )
    right_items = sorted(
        (str(item.get("path", "")), str(item.get("sha256", "")))
        for item in right
        if isinstance(item, dict)
    )
    return left_items == right_items


def _deselected_tests_match(left: object, right: object) -> bool:
    if not isinstance(left, list) or not isinstance(right, list):
        return False
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right,
        sort_keys=True,
        separators=(",", ":"),
    )


def _collect_nodeid_digest_matches(
    existing: dict[str, Any],
    current: dict[str, Any] | None,
    *,
    collect_nodeids: bool,
) -> bool:
    if not collect_nodeids:
        return True
    if current is None or current.get("status") != "collected":
        return False
    existing_digest = existing.get("pytest_collect_nodeid_digest")
    if not isinstance(existing_digest, dict):
        return False
    return (
        existing_digest.get("status") == "collected"
        and existing_digest.get("nodeid_count") == current.get("nodeid_count")
        and existing_digest.get("sha256") == current.get("sha256")
    )


def _existing_toolchain_fingerprint(existing: dict[str, Any]) -> str:
    execution_environment = existing.get("execution_environment")
    if isinstance(execution_environment, dict):
        return _toolchain_fingerprint(execution_environment)
    return str(existing.get("toolchain_fingerprint", "")).strip()


def _existing_semantic_command(existing: dict[str, Any]) -> str:
    semantic = str(existing.get("semantic_command") or "").strip()
    if semantic:
        return semantic
    return str(existing.get("command") or "").strip()


def _reuse_failure(
    *,
    reason: str,
    current_source_revision: str,
    observed_source_revision: str,
    current_source_tree_fingerprint: str,
    observed_source_tree_fingerprint: str,
    checks: dict[str, bool],
) -> dict[str, Any]:
    if reason not in REUSE_MISMATCH_CODES:
        raise ValueError(f"unsupported reuse mismatch reason: {reason}")
    return {
        "reusable": False,
        "result_reusable": bool(checks.get("result_reusable", False)),
        "reason": reason,
        "current_source_revision": current_source_revision,
        "observed_source_revision": observed_source_revision,
        "current_source_tree_fingerprint": current_source_tree_fingerprint,
        "observed_source_tree_fingerprint": observed_source_tree_fingerprint,
        "executable_path_differs_only": False,
        "checks": checks,
    }


def reuse_currentness_diagnostics_from_state(
    existing: dict[str, Any],
    *,
    suite: str,
    current_source_revision: str,
    current_source_tree_fingerprint: str,
    current_semantic_command: str,
    current_toolchain_fingerprint: str,
    current_display_command: str,
    current_target_fingerprints: list[dict[str, Any]],
    current_deselected_tests: list[dict[str, Any]],
    current_deselection_lifecycle: dict[str, Any],
    collect_nodeids: bool,
    collect_nodeid_digest: dict[str, Any] | None,
) -> dict[str, Any]:
    observed_source_revision = str(existing.get("source_revision", "")).strip()
    observed_source_tree_fingerprint = str(existing.get("source_tree_fingerprint", "")).strip()
    checks = {
        "artifact_kind": existing.get("artifact_kind") == "test_execution_summary",
        "status": existing.get("status") == "pass",
    }
    if not existing or not all(checks.values()):
        return _reuse_failure(
            reason=REUSE_MISMATCH_MISSING_SUMMARY,
            current_source_revision=current_source_revision,
            observed_source_revision=observed_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            observed_source_tree_fingerprint=observed_source_tree_fingerprint,
            checks=checks,
        )

    checks["source_tree_fingerprint"] = (
        observed_source_tree_fingerprint == current_source_tree_fingerprint
    )
    if not checks["source_tree_fingerprint"]:
        return _reuse_failure(
            reason=REUSE_MISMATCH_SOURCE_TREE,
            current_source_revision=current_source_revision,
            observed_source_revision=observed_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            observed_source_tree_fingerprint=observed_source_tree_fingerprint,
            checks=checks,
        )

    checks["source_revision"] = observed_source_revision == current_source_revision

    existing_lifecycle = existing.get("deselection_lifecycle")
    if not isinstance(existing_lifecycle, dict):
        existing_lifecycle = {}
    existing_semantic_command = _existing_semantic_command(existing)
    command_checks = {
        "suite": existing.get("suite") == suite,
        "semantic_command": existing_semantic_command == current_semantic_command,
        "existing_deselection_lifecycle": existing_lifecycle.get("status") == "pass",
        "current_deselection_lifecycle": current_deselection_lifecycle.get("status") == "pass",
        "test_target_fingerprints": _test_target_fingerprints_match(
            existing.get("test_target_fingerprints"),
            current_target_fingerprints,
        ),
        "deselected_tests": _deselected_tests_match(
            existing.get("deselected_tests"),
            current_deselected_tests,
        ),
        "pytest_collect_nodeid_digest": _collect_nodeid_digest_matches(
            existing,
            collect_nodeid_digest,
            collect_nodeids=collect_nodeids,
        ),
        "nodeid_outcome_consistency": (
            not collect_nodeids
            or existing.get("nodeid_outcome_consistency", {}).get("status") == "pass"
        ),
    }
    checks.update(command_checks)
    if not all(command_checks.values()):
        return _reuse_failure(
            reason=REUSE_MISMATCH_COMMAND_IDENTITY,
            current_source_revision=current_source_revision,
            observed_source_revision=observed_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            observed_source_tree_fingerprint=observed_source_tree_fingerprint,
            checks=checks,
        )

    existing_toolchain_fingerprint = _existing_toolchain_fingerprint(existing)
    checks["toolchain_fingerprint"] = (
        existing_toolchain_fingerprint == current_toolchain_fingerprint
    )
    if not checks["toolchain_fingerprint"]:
        return _reuse_failure(
            reason=REUSE_MISMATCH_INTERPRETER_TOOLCHAIN,
            current_source_revision=current_source_revision,
            observed_source_revision=observed_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            observed_source_tree_fingerprint=observed_source_tree_fingerprint,
            checks=checks,
        )

    checks["result_reusable"] = True
    if not checks["source_revision"]:
        return _reuse_failure(
            reason=REUSE_MISMATCH_SOURCE_REVISION,
            current_source_revision=current_source_revision,
            observed_source_revision=observed_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            observed_source_tree_fingerprint=observed_source_tree_fingerprint,
            checks=checks,
        )

    existing_display_command = str(existing.get("command") or "").strip()
    executable_path_differs_only = (
        bool(existing_display_command)
        and existing_display_command != current_display_command
        and existing_semantic_command == current_semantic_command
    )
    return {
        "reusable": True,
        "result_reusable": True,
        "reason": None,
        "current_source_revision": current_source_revision,
        "observed_source_revision": observed_source_revision,
        "current_source_tree_fingerprint": current_source_tree_fingerprint,
        "observed_source_tree_fingerprint": observed_source_tree_fingerprint,
        "executable_path_differs_only": executable_path_differs_only,
        "checks": checks,
    }
