#!/usr/bin/env python3
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import TEST_EXECUTION_SUMMARY_SCHEMA_PATH
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.test.test_execution_command_runtime import (
    build_execution_environment,
    toolchain_fingerprint as _toolchain_fingerprint,
)
from ops.scripts.test.test_execution_evidence_runtime import (
    evidence_artifact_consistency as _evidence_artifact_consistency,
    nodeid_outcome_consistency as _nodeid_outcome_consistency,
    sha256_text as _sha256_text,
)
from ops.scripts.test.test_execution_selection_runtime import (
    FULL_SUITE_SCOPES,
    apply_toolchain_contract_to_coverage as _apply_toolchain_contract_to_coverage,
    suite_coverage as _suite_coverage,
)
from ops.scripts.test.test_execution_summary import (
    PRODUCER,
)


def load_test_execution_summary(vault: Path, path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = load_schema_with_vault_override(vault, TEST_EXECUTION_SUMMARY_SCHEMA_PATH)
    validate_or_raise(
        payload,
        schema,
        context=f"test execution summary shard validation failed for {report_path(vault, path)}",
    )
    return payload


def reusable_aggregate_summary_diagnostics(
    vault: Path,
    path_value: str | Path,
    *,
    suite: str,
) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    diagnostics: dict[str, Any] = {
        "reusable": False,
        "path": report_path(vault, path),
        "reason": "",
    }
    try:
        existing = load_test_execution_summary(vault, path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        diagnostics["reason"] = f"summary_unavailable:{type(exc).__name__}"
        return diagnostics

    current_source_revision = resolve_source_revision(vault).revision
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    checks = {
        "artifact_kind": existing.get("artifact_kind") == "test_execution_summary",
        "status": existing.get("status") == "pass",
        "suite": existing.get("suite") == suite,
        "summary_mode": existing.get("summary_mode") in {"aggregate", "reused"},
        "source_revision": existing.get("source_revision") == current_source_revision,
        "source_tree_fingerprint": existing.get("source_tree_fingerprint") == current_source_tree_fingerprint,
        "full_suite_evidence": (
            suite.strip().lower().replace("_", "-") not in FULL_SUITE_SCOPES
            or bool(existing.get("represents_full_suite"))
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        diagnostics["reason"] = f"not_current:{','.join(failed)}"
        diagnostics["result_reusable"] = failed == ["source_revision"]
        diagnostics["checks"] = checks
        diagnostics["current_source_revision"] = current_source_revision
        diagnostics["observed_source_revision"] = str(existing.get("source_revision", ""))
        diagnostics["current_source_tree_fingerprint"] = current_source_tree_fingerprint
        diagnostics["observed_source_tree_fingerprint"] = str(existing.get("source_tree_fingerprint", ""))
        return diagnostics
    diagnostics.update(
        {
            "reusable": True,
            "result_reusable": True,
            "reason": "current_passing_aggregate_summary",
            "generated_at": str(existing.get("generated_at", "")),
            "source_revision": str(existing.get("source_revision", "")),
            "source_tree_fingerprint": str(existing.get("source_tree_fingerprint", "")),
        }
    )
    return diagnostics


def aggregate_status(statuses: list[str]) -> str:
    if any(status in {"fail", "timeout", "interrupted"} for status in statuses):
        return "fail"
    if any(status == "partial-pass" for status in statuses):
        return "partial-pass"
    return "pass"


def aggregate_shard_source_tree_status(vault: Path, shards: list[dict[str, Any]]) -> str:
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    if not shards:
        return "fail"
    if all(
        str(shard.get("source_tree_fingerprint", "")).strip() == current_source_tree_fingerprint
        for shard in shards
    ):
        return "pass"
    return "fail"


def aggregate_counts(shards: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
        "subtests_passed": 0,
    }
    for shard in shards:
        shard_counts = shard.get("counts", {})
        if not isinstance(shard_counts, dict):
            continue
        for key in counts:
            counts[key] += int(shard_counts.get(key, 0) or 0)
    return counts


def summary_shard_paths(vault: Path, aggregate_from: list[str], aggregate_dir: str) -> list[str]:
    if aggregate_from:
        return sorted(str(item) for item in aggregate_from)
    directory = Path(aggregate_dir)
    if not directory.is_absolute():
        directory = vault / directory
    if not directory.is_dir():
        return []
    return sorted(report_path(vault, path) for path in directory.glob("*.json") if path.is_file())


def aggregate_deselection_lifecycle(
    shards: list[dict[str, Any]],
    *,
    deselected_tests: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    lifecycles = [
        lifecycle
        for shard in shards
        if isinstance((lifecycle := shard.get("deselection_lifecycle")), dict)
    ]
    blockers = [
        blocker
        for lifecycle in lifecycles
        for blocker in lifecycle.get("blockers", [])
        if isinstance(blocker, dict)
    ]
    if any(lifecycle.get("status") != "pass" for lifecycle in lifecycles):
        blockers.append(
            {
                "code": "shard_deselection_lifecycle_failed",
                "nodeid": "",
                "message": "One or more summary shards reported a failed deselection lifecycle.",
            }
        )
    max_allowed = sum(
        int(lifecycle.get("max_allowed_deselected_count", 0) or 0)
        for lifecycle in lifecycles
    )
    return {
        "status": "fail" if blockers else "pass",
        "checked_at": generated_at,
        "actual_deselected_count": len(deselected_tests),
        "max_allowed_deselected_count": max_allowed,
        "over_budget": any(bool(lifecycle.get("over_budget")) for lifecycle in lifecycles),
        "expired_count": sum(int(lifecycle.get("expired_count", 0) or 0) for lifecycle in lifecycles),
        "release_blocking_count": sum(
            int(lifecycle.get("release_blocking_count", 0) or 0)
            for lifecycle in lifecycles
        ),
        "missing_lifecycle_count": sum(
            int(lifecycle.get("missing_lifecycle_count", 0) or 0)
            for lifecycle in lifecycles
        ),
        "duplicate_policy_entry_count": sum(
            int(lifecycle.get("duplicate_policy_entry_count", 0) or 0)
            for lifecycle in lifecycles
        ),
        "unused_policy_entry_count": sum(
            int(lifecycle.get("unused_policy_entry_count", 0) or 0)
            for lifecycle in lifecycles
        ),
        "risk_owner": "aggregate",
        "expires_at": "",
        "count_increase_gate_effect": "fail",
        "expiry_gate_effect": "fail",
        "next_action": "none" if not blockers else "fix failing shard deselection lifecycle",
        "blockers": blockers,
    }


def aggregate_shard_refs(shard_paths: list[str], shards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path),
            "suite": str(shard.get("suite", "")),
            "status": str(shard.get("status", "")),
            "generated_at": str(shard.get("generated_at", "")),
            "duration_ms": int(shard.get("duration_ms", 0) or 0),
            "counts": shard.get("counts", {}),
            "represents_full_suite": bool(shard.get("represents_full_suite")),
        }
        for path, shard in zip(shard_paths, shards, strict=False)
    ]


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def aggregate_duration_telemetry(shards: list[dict[str, Any]]) -> dict[str, Any]:
    command_duration_ms = 0
    collect_only_duration_ms = 0
    for shard in shards:
        telemetry = shard.get("duration_telemetry")
        if isinstance(telemetry, dict):
            command_duration_ms += _nonnegative_int(telemetry.get("command_duration_ms"))
            collect_only_duration_ms += _nonnegative_int(telemetry.get("collect_only_duration_ms"))
            continue
        command_duration_ms += _nonnegative_int(shard.get("duration_ms"))
    return {
        "command_duration_ms": command_duration_ms,
        "collect_only_duration_ms": collect_only_duration_ms,
        "total_wall_time_ms": command_duration_ms + collect_only_duration_ms,
        "total_wall_time_source": "command_plus_collect_only",
    }


def aggregate_shard_dict_items(shards: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    return [
        item
        for shard in shards
        for item in shard.get(field, [])
        if isinstance(item, dict)
    ]


def aggregate_nodeid_digest(shards: list[dict[str, Any]]) -> dict[str, Any]:
    digests = [
        digest
        for shard in shards
        if isinstance(shard, dict)
        and isinstance((digest := shard.get("pytest_collect_nodeid_digest")), dict)
    ]
    if not digests:
        return {
            "status": "failed",
            "command": "",
            "nodeid_count": 0,
            "sha256": "",
            "reason": "aggregate report received no shard nodeid digests",
        }
    if any(digest.get("status") != "collected" for digest in digests):
        return {
            "status": "failed",
            "command": "",
            "nodeid_count": sum(int(digest.get("nodeid_count", 0) or 0) for digest in digests),
            "sha256": "",
            "reason": "one or more shard nodeid digests were not collected",
        }
    digest_input = "\n".join(
        f"{digest.get('sha256', '')}:{int(digest.get('nodeid_count', 0) or 0)}"
        for digest in digests
    )
    if digest_input:
        digest_input = f"{digest_input}\n"
    commands = [
        str(digest.get("command", "")).strip()
        for digest in digests
        if str(digest.get("command", "")).strip()
    ]
    return {
        "status": "collected",
        "command": " || ".join(commands),
        "nodeid_count": sum(int(digest.get("nodeid_count", 0) or 0) for digest in digests),
        "sha256": _sha256_text(digest_input),
        "reason": "aggregate report reuses shard nodeid digests",
        "duration_ms": sum(_nonnegative_int(digest.get("duration_ms")) for digest in digests),
    }


def aggregate_nodeid_consistency(
    shards: list[dict[str, Any]],
    counts: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    collect_digest = aggregate_nodeid_digest(shards)
    consistency = _nodeid_outcome_consistency(counts, collect_digest)
    if collect_digest.get("status") != "collected":
        consistency["reason"] = str(collect_digest.get("reason", "")) or consistency["reason"]
    return collect_digest, consistency


def aggregate_source_command(suite: str, shard_paths: list[str]) -> str:
    return (
        f"python -m ops.scripts.test_execution_summary --vault . --suite {suite} "
        f"--aggregate-from {' --aggregate-from '.join(shlex.quote(path) for path in shard_paths)}"
    )


def build_aggregate_report(
    vault: Path,
    *,
    shard_paths: list[str],
    suite: str,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    shards = [load_test_execution_summary(vault, path) for path in shard_paths]
    statuses = [str(shard.get("status", "fail")) for shard in shards]
    status = aggregate_status(statuses) if shards else "fail"
    if aggregate_shard_source_tree_status(vault, shards) != "pass":
        status = "fail"
    counts = aggregate_counts(shards)
    command = "aggregate test execution summary shards"
    shard_refs = aggregate_shard_refs(shard_paths, shards)
    deselected_tests = aggregate_shard_dict_items(shards, "deselected_tests")
    deselection_lifecycle = aggregate_deselection_lifecycle(
        shards,
        deselected_tests=deselected_tests,
        generated_at=generated_at,
    )
    execution_environment = build_execution_environment(vault, [sys.executable, "-m", "pytest"])
    coverage = _apply_toolchain_contract_to_coverage(
        _suite_coverage(
            suite=suite,
            command=[sys.executable, "-m", "pytest"],
            summary_mode="aggregate",
            shards=shards,
        ),
        execution_environment,
    )
    collect_nodeid_digest, nodeid_outcome_consistency = aggregate_nodeid_consistency(shards, counts)
    duration_telemetry = aggregate_duration_telemetry(shards)
    evidence_artifacts = aggregate_shard_dict_items(shards, "evidence_artifacts")
    evidence_artifact_consistency = _evidence_artifact_consistency(
        vault,
        counts=counts,
        evidence_artifacts=evidence_artifacts,
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="test_execution_summary",
            producer=PRODUCER,
            source_command=aggregate_source_command(suite, shard_paths),
            resolved_policy_path=resolved_policy_path,
            schema_path=TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/test/test_execution_summary.py",
                "ops/scripts/core/command_runtime.py",
            ],
            file_inputs={f"shard_{index}": path for index, path in enumerate(shard_paths, start=1)},
            text_inputs={
                "summary_mode": "aggregate",
                "suite": suite,
                "shard_statuses": json.dumps(statuses, sort_keys=True, separators=(",", ":")),
                "suite_coverage": json.dumps(coverage, sort_keys=True, separators=(",", ":")),
                "deselection_lifecycle": json.dumps(
                    deselection_lifecycle,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence_artifact_consistency": json.dumps(
                    evidence_artifact_consistency,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "suite": suite,
        **coverage,
        "status": status,
        "command": command,
        "semantic_command": command,
        "toolchain_fingerprint": _toolchain_fingerprint(execution_environment),
        "returncode": 0 if status == "pass" else 1,
        "timed_out": any(bool(shard.get("timed_out")) for shard in shards),
        "timeout_seconds": max([int(shard.get("timeout_seconds", 1) or 1) for shard in shards] or [1]),
        "termination_reason": "completed" if status == "pass" else "one_or_more_shards_not_current_or_pass",
        "duration_ms": sum(int(shard.get("duration_ms", 0) or 0) for shard in shards),
        "duration_telemetry": duration_telemetry,
        "counts": counts,
        "execution_environment": execution_environment,
        "test_target_fingerprints": [
            item
            for shard in shards
            for item in shard.get("test_target_fingerprints", [])
            if isinstance(item, dict)
        ],
        "deselected_tests": deselected_tests,
        "deselection_lifecycle": deselection_lifecycle,
        "pytest_collect_nodeid_digest": collect_nodeid_digest,
        "nodeid_outcome_consistency": nodeid_outcome_consistency,
        "evidence_artifacts": evidence_artifacts,
        "evidence_artifact_consistency": evidence_artifact_consistency,
        "stdout_tail": json.dumps(shard_refs, ensure_ascii=False, sort_keys=True),
        "stderr_tail": "",
        "summary_mode": "aggregate",
        "shards": shard_refs,
    }
