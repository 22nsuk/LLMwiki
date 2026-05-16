#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shlex
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.command_runtime import TimedProcessResult, run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        TEST_DESELECTION_POLICY_SCHEMA_PATH,
        TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
    )
    from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_or_raise
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.command_runtime import TimedProcessResult, run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        TEST_DESELECTION_POLICY_SCHEMA_PATH,
        TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
    )
    from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_or_raise


DEFAULT_OUT = "ops/reports/test-execution-summary.json"
PRODUCER = "ops.scripts.test_execution_summary"
DEFAULT_TIMEOUT_SECONDS = 5400
TAIL_LINE_COUNT = 80
DEFAULT_SHARD_DIR = "ops/reports/test-execution-summary-shards"
DEFAULT_FULL_SUITE_SHARD_DIR = "ops/reports/test-execution-summary-full-shards"
REPORT_CONTRACT_SUMMARY_SUITE = "report-contract-summary"
FULL_SUITE_COMMAND = "python -m pytest"
RELEASE_BUILDER_ENVIRONMENT = ".venv clean release-builder"
SUPPORTED_PYTHON_MAJOR_MINOR = ("3.11", "3.12", "3.13", "3.14")
MINIMUM_PYTEST_MAJOR = 8
FULL_SUITE_SCOPES = {"full", "full-suite", "pytest"}
RELEASE_BUILDER_FULL_SCOPES = {"release-builder-full", "release_builder_full"}
FULL_SUITE_SHARD_PREFIX = "full-shard-"
PYTEST_COUNT_RE = re.compile(
    r"(?P<count>\d+)\s+"
    r"(?P<label>passed|failed|error|errors|skipped|xfailed|xpassed|warning|warnings)"
)
PYTEST_DESELECTED_RE = re.compile(r"(?P<count>\d+)\s+deselected")
PYTEST_OPTION_VALUE_FLAGS = {
    "-c",
    "-k",
    "-m",
    "-n",
    "-p",
    "--basetemp",
    "--cache-clear",
    "--capture",
    "--confcutdir",
    "--deselect",
    "--dist",
    "--junit-xml",
    "--log-cli-level",
    "--maxfail",
    "--override-ini",
    "--rootdir",
    "--tb",
}
PYTEST_COLLECTION_FILTER_FLAGS = {"-k", "-m", "--deselect"}
PYTEST_PLUGIN_AUTOLOAD_ENV = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"


@dataclass(frozen=True)
class TestExecutionReportRequest:
    command: list[str]
    result: TimedProcessResult
    duration_ms: int
    suite: str
    policy_path: str | None = None
    context: RuntimeContext | None = None
    collect_nodeids: bool = False
    collect_nodeid_digest: dict[str, Any] | None = None
    evidence_artifacts: list[dict[str, Any]] | None = None
    deselection_policy_path: str | None = None


@dataclass(frozen=True)
class TestExecutionObservations:
    counts: dict[str, int]
    target_paths: list[str]
    test_target_fingerprints: list[dict[str, str]]
    deselected_tests: list[dict[str, Any]]
    deselection_lifecycle: dict[str, Any]
    pytest_marker_deselected_count: int
    policy_deselected_count: int
    collect_nodeid_digest: dict[str, Any]
    nodeid_outcome_consistency: dict[str, Any]
    evidence_artifacts: list[dict[str, Any]]
    evidence_artifact_consistency: dict[str, Any]
    execution_environment: dict[str, Any]
    coverage: dict[str, Any]
    status: str


@dataclass(frozen=True)
class TestExecutionRenderInputs:
    vault: Path
    request: TestExecutionReportRequest
    policy: dict[str, Any]
    resolved_policy_path: Path
    generated_at: str
    observations: TestExecutionObservations


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def classify_interpreter_path(vault: Path, executable: str) -> str:
    value = str(executable).strip()
    if not value:
        return "unknown"
    if value in {"python", "python3", "py"}:
        return "path_lookup"
    path = Path(value)
    if not path.is_absolute():
        if ".venv" in path.parts:
            return "repo_virtualenv"
        resolved = (vault / path).resolve()
        if _is_relative_to(resolved, vault.resolve()):
            return "repo_relative"
        return "relative_external"
    resolved = path.resolve()
    if _is_relative_to(resolved, vault.resolve()):
        return "repo_virtualenv" if ".venv" in resolved.parts else "repo_absolute"
    if ".venv" in resolved.parts or "venv" in resolved.parts:
        return "external_virtualenv"
    return "external_absolute"


def _pytest_version() -> str:
    try:
        return importlib.metadata.version("pytest")
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _major_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2:
        return version
    return f"{parts[0]}.{parts[1]}"


def _major_version(value: str) -> int | None:
    try:
        return int(value.split(".", 1)[0])
    except ValueError:
        return None


def _toolchain_contract(python_version: str, pytest_version: str) -> dict[str, Any]:
    python_supported = _major_minor(python_version) in SUPPORTED_PYTHON_MAJOR_MINOR
    pytest_major = _major_version(pytest_version)
    pytest_supported = pytest_major is not None and pytest_major >= MINIMUM_PYTEST_MAJOR
    status = "pass" if python_supported and pytest_supported else "unsupported"
    reason_parts: list[str] = []
    if not python_supported:
        reason_parts.append(
            f"python {_major_minor(python_version)} is outside supported set "
            f"{', '.join(SUPPORTED_PYTHON_MAJOR_MINOR)}"
        )
    if not pytest_supported:
        reason_parts.append(f"pytest {pytest_version} is below required major {MINIMUM_PYTEST_MAJOR}")
    return {
        "status": status,
        "python_supported": python_supported,
        "pytest_supported": pytest_supported,
        "supported_python_major_minor": list(SUPPORTED_PYTHON_MAJOR_MINOR),
        "minimum_pytest_major": MINIMUM_PYTEST_MAJOR,
        "release_evidence_effect": "eligible" if status == "pass" else "blocked_unsupported_toolchain",
        "reason": "; ".join(reason_parts) if reason_parts else "toolchain is eligible for release evidence",
    }


def build_execution_environment(vault: Path, command: list[str]) -> dict[str, Any]:
    env_value = os.environ.get(PYTEST_PLUGIN_AUTOLOAD_ENV, "")
    command_executable = str(command[0]) if command else ""
    python_version = platform.python_version()
    pytest_version = _pytest_version()
    return {
        "python_version": python_version,
        "pytest_version": pytest_version,
        "plugin_autoload_policy": {
            "env_var": PYTEST_PLUGIN_AUTOLOAD_ENV,
            "value": env_value,
            "autoload_disabled": env_value == "1",
            "policy": "disabled" if env_value == "1" else "not_set" if not env_value else "custom",
        },
        "interpreter_path_class": classify_interpreter_path(vault, command_executable),
        "toolchain_contract": _toolchain_contract(python_version, pytest_version),
    }


def _tail_text(text: str, max_lines: int = TAIL_LINE_COUNT) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def _display_command(vault: Path, command: list[str]) -> str:
    return shlex.join([sanitize_report_text(vault, item) for item in command])


def parse_pytest_counts(*streams: str) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
    }
    text = "\n".join(streams)
    for match in PYTEST_COUNT_RE.finditer(text):
        label = match.group("label")
        normalized = {
            "error": "errors",
            "warning": "warnings",
        }.get(label, label)
        counts[normalized] = max(counts[normalized], int(match.group("count")))
    return counts


def classify_status(result: TimedProcessResult, counts: dict[str, int]) -> str:
    if result.timed_out:
        return "timeout"
    if result.returncode in {130, -2}:
        return "interrupted"
    if result.returncode == 0:
        return "pass"
    if counts["passed"] > 0 and (counts["failed"] > 0 or counts["errors"] > 0):
        return "partial-pass"
    return "fail"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pytest_args(command: list[str]) -> list[str]:
    for index, item in enumerate(command):
        value = str(item)
        name = Path(value).name
        if value == "pytest" or name.startswith("pytest"):
            return [str(arg) for arg in command[index + 1 :]]
        if value == "-m" and index + 1 < len(command) and str(command[index + 1]) == "pytest":
            return [str(arg) for arg in command[index + 2 :]]
    return []


def _pytest_selector_args(command: list[str]) -> list[str]:
    selectors: list[str] = []
    args = _pytest_args(command)
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg == "--":
            continue
        if arg in PYTEST_OPTION_VALUE_FLAGS:
            skip_next = True
            continue
        if any(arg.startswith(f"{flag}=") for flag in PYTEST_OPTION_VALUE_FLAGS if flag.startswith("--")):
            continue
        if arg.startswith("-"):
            continue
        selectors.append(arg)
    return selectors


def _pytest_collection_filter_args(command: list[str]) -> list[str]:
    filters: list[str] = []
    args = _pytest_args(command)
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in PYTEST_COLLECTION_FILTER_FLAGS:
            filters.append(arg)
            skip_next = True
            continue
        for flag in PYTEST_COLLECTION_FILTER_FLAGS:
            if flag.startswith("--") and arg.startswith(f"{flag}="):
                filters.append(flag)
                break
    return filters


def _suite_coverage(
    *,
    suite: str,
    command: list[str],
    summary_mode: str = "single",
    shards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selectors = _pytest_selector_args(command)
    collection_filters = _pytest_collection_filter_args(command)
    collection_limited = bool(selectors or collection_filters)
    suite_key = suite.strip().lower().replace("_", "-")
    if suite_key == REPORT_CONTRACT_SUMMARY_SUITE:
        suite_scope = "report_contract_summary"
        represents_full_suite = False
        not_full_suite_reason = (
            "report-contract-summary is a targeted report-contract subset; use full release-builder evidence "
            "before treating this as full-suite proof."
        )
    elif summary_mode == "aggregate":
        shard_values = [
            bool(shard.get("represents_full_suite"))
            for shard in shards or []
            if isinstance(shard, dict)
        ]
        represents_full_suite = bool(shard_values) and all(shard_values)
        suite_scope = "full_suite" if represents_full_suite else _suite_scope_for_key(suite_key)
        not_full_suite_reason = (
            ""
            if represents_full_suite
            else "aggregate summary does not represent the full suite unless every shard does"
        )
    elif collection_limited:
        suite_scope = _suite_scope_for_key(suite_key)
        represents_full_suite = False
        not_full_suite_reason = "pytest selectors limit this execution to a targeted suite subset"
    else:
        suite_scope = _suite_scope_for_key(suite_key)
        represents_full_suite = suite_scope in {"full_suite", "release_builder_full"}
        not_full_suite_reason = "" if represents_full_suite else f"{suite_scope} is not full-suite evidence"

    return {
        "suite_scope": suite_scope,
        "represents_full_suite": represents_full_suite,
        "not_full_suite_reason": not_full_suite_reason,
        "full_suite_evidence": {
            "status": "represented" if represents_full_suite else "not_represented",
            "required_command": FULL_SUITE_COMMAND,
            "release_builder_environment": RELEASE_BUILDER_ENVIRONMENT,
            "reason": (
                "this execution has no pytest selectors and is treated as full-suite evidence"
                if represents_full_suite
                else not_full_suite_reason
            ),
        },
    }


def _apply_toolchain_contract_to_coverage(
    coverage: dict[str, Any],
    execution_environment: dict[str, Any],
) -> dict[str, Any]:
    toolchain = execution_environment.get("toolchain_contract", {})
    if not isinstance(toolchain, dict) or toolchain.get("status") == "pass":
        return coverage
    adjusted = dict(coverage)
    full_suite_evidence = dict(adjusted.get("full_suite_evidence", {}))
    reason = (
        "unsupported toolchain blocks full-suite evidence promotion: "
        f"{toolchain.get('reason', 'unknown toolchain contract failure')}"
    )
    adjusted["represents_full_suite"] = False
    adjusted["not_full_suite_reason"] = reason
    full_suite_evidence["status"] = "not_represented"
    full_suite_evidence["reason"] = reason
    adjusted["full_suite_evidence"] = full_suite_evidence
    return adjusted


def _suite_scope_for_key(suite_key: str) -> str:
    if suite_key in FULL_SUITE_SCOPES:
        return "full_suite"
    if suite_key.startswith(FULL_SUITE_SHARD_PREFIX):
        return "full_suite"
    if suite_key in RELEASE_BUILDER_FULL_SCOPES:
        return "release_builder_full"
    if suite_key in {"fast", "unit", "unit-tests", "test-fast"}:
        return "fast_unit"
    if suite_key in {"public", "public-contract", "test-public", "public-check"}:
        return "public_contract"
    if suite_key in {"artifact-finalization", "artifact-finalisation", "report-contract-finalization"}:
        return "artifact_finalization"
    if suite_key in {"release-sealing", "release_sealing"}:
        return "release_sealing"
    if suite_key in {"subprocess", "subprocess-integration"}:
        return "subprocess_integration"
    return "fast_unit"


def _pytest_file_candidates(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    candidates = [*path.rglob("test_*.py"), *path.rglob("*_test.py")]
    return sorted({candidate.resolve() for candidate in candidates if candidate.is_file()})


def resolve_pytest_target_paths(vault: Path, command: list[str]) -> list[str]:
    target_paths: list[str] = []
    seen: set[str] = set()
    for selector in _pytest_selector_args(command):
        path_selector = selector.split("::", 1)[0]
        if not path_selector:
            continue
        candidate = Path(path_selector)
        if not candidate.is_absolute():
            candidate = vault / candidate
        for path in _pytest_file_candidates(candidate.resolve()):
            rel_path = report_path(vault, path)
            if rel_path not in seen:
                seen.add(rel_path)
                target_paths.append(rel_path)
    return sorted(target_paths)


def _pytest_collect_modifiers(command: list[str]) -> list[str]:
    modifiers: list[str] = []
    args = _pytest_args(command)
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("--deselect="):
            modifiers.append(arg)
            continue
        if arg == "--deselect" and index + 1 < len(args):
            modifiers.extend([arg, args[index + 1]])
            skip_next = True
            continue
        if arg in {"-m", "-k"} and index + 1 < len(args):
            modifiers.extend([arg, args[index + 1]])
            skip_next = True
            continue
        if arg.startswith(("--deselect=", "-m=", "-k=")):
            modifiers.append(arg)
            continue
    return modifiers


def _pytest_deselected_nodeids(command: list[str]) -> list[str]:
    nodeids: list[str] = []
    args = _pytest_args(command)
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("--deselect="):
            nodeids.append(arg.split("=", 1)[1])
            continue
        if arg == "--deselect" and index + 1 < len(args):
            nodeids.append(args[index + 1])
            skip_next = True
    return [nodeid for nodeid in nodeids if nodeid]


def _load_deselection_policy_payload(vault: Path, policy_path: str | None) -> dict[str, Any]:
    if not policy_path:
        return {}
    resolved = Path(policy_path)
    if not resolved.is_absolute():
        resolved = vault / resolved
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    schema = load_schema_with_vault_override(vault, TEST_DESELECTION_POLICY_SCHEMA_PATH)
    validate_or_raise(
        payload,
        schema,
        context=f"test deselection policy validation failed for {report_path(vault, resolved)}",
    )
    return payload


def _load_deselection_policy(vault: Path, policy_path: str | None) -> dict[str, dict[str, Any]]:
    payload = _load_deselection_policy_payload(vault, policy_path)
    if not payload:
        return {}
    return {str(item["nodeid"]): item for item in payload["deselected_tests"]}


def _parse_utc_timestamp(value: str, *, context: str) -> dt.datetime:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{context} is missing a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context} has an invalid timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{context} must include timezone information: {text!r}")
    return parsed.astimezone(dt.timezone.utc)


def _deselection_lifecycle(
    deselected_tests: list[dict[str, Any]],
    *,
    generated_at: str,
    policy_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    policy_payload = policy_payload or {}
    budget = policy_payload.get("deselection_budget")
    budget = budget if isinstance(budget, dict) else {}
    checked_at = _parse_utc_timestamp(generated_at, context="test deselection lifecycle generated_at")
    policy_entries = policy_payload.get("deselected_tests", [])
    policy_entries = policy_entries if isinstance(policy_entries, list) else []
    policy_nodeids = [str(item.get("nodeid", "")) for item in policy_entries if isinstance(item, dict)]
    actual_nodeids = [str(item.get("nodeid", "")) for item in deselected_tests if isinstance(item, dict)]
    duplicate_count = len(policy_nodeids) - len(set(policy_nodeids))
    max_count = int(budget.get("max_count", len(policy_nodeids) or len(actual_nodeids)) or 0)
    release_blocking_count = sum(1 for item in deselected_tests if bool(item.get("release_blocking")))

    blockers: list[dict[str, str]] = []
    expired_count = 0
    missing_lifecycle_count = 0
    for item in deselected_tests:
        nodeid = str(item.get("nodeid", ""))
        owner = str(item.get("risk_owner", "")).strip()
        expires_at = str(item.get("expires_at", "")).strip()
        if not owner or not expires_at:
            missing_lifecycle_count += 1
            blockers.append(
                {
                    "code": "missing_deselection_lifecycle",
                    "nodeid": nodeid,
                    "message": "Deselected test is missing risk_owner or expires_at.",
                }
            )
            continue
        if _parse_utc_timestamp(expires_at, context=f"{nodeid}:expires_at") <= checked_at:
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
    if budget_expires_at and _parse_utc_timestamp(
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
    policy = _load_deselection_policy(vault, deselection_policy_path)
    entries: list[dict[str, Any]] = []
    for nodeid in _pytest_deselected_nodeids(command):
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


def build_test_target_fingerprints(vault: Path, target_paths: list[str]) -> list[dict[str, str]]:
    fingerprints: list[dict[str, str]] = []
    for rel_path in target_paths:
        path = (vault / rel_path).resolve()
        if path.is_file():
            fingerprints.append({"path": rel_path, "sha256": _sha256_file(path)})
    return fingerprints


def _collect_nodeids(stdout: str) -> list[str]:
    return sorted(
        line.strip()
        for line in stdout.splitlines()
        if line.strip() and ".py::" in line and not line.lstrip().startswith("=")
    )


def collect_pytest_nodeid_digest(
    vault: Path,
    command: list[str],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    selectors = _pytest_selector_args(command)
    collect_command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "--collect-only",
        "-q",
        "--capture=no",
        *selectors,
        *_pytest_collect_modifiers(command),
    ]
    result = run_with_timeout(collect_command, cwd=vault, timeout_seconds=timeout_seconds)
    command_text = _display_command(vault, collect_command)
    if result.returncode != 0 or result.timed_out:
        return {
            "status": "failed",
            "command": command_text,
            "nodeid_count": 0,
            "sha256": "",
            "reason": result.termination_reason,
        }
    nodeids = _collect_nodeids(result.stdout)
    digest_input = "\n".join(nodeids)
    if digest_input:
        digest_input = f"{digest_input}\n"
    return {
        "status": "collected",
        "command": command_text,
        "nodeid_count": len(nodeids),
        "sha256": _sha256_text(digest_input),
        "reason": "",
    }


def _nodeid_outcome_consistency(
    counts: dict[str, int],
    collect_nodeid_digest: dict[str, Any],
) -> dict[str, Any]:
    counted_outcomes = {
        "passed": int(counts.get("passed", 0) or 0),
        "skipped": int(counts.get("skipped", 0) or 0),
        "xfailed": int(counts.get("xfailed", 0) or 0),
        "xpassed": int(counts.get("xpassed", 0) or 0),
    }
    nodeid_count = int(collect_nodeid_digest.get("nodeid_count", 0) or 0)
    outcome_count = sum(counted_outcomes.values())
    if collect_nodeid_digest.get("status") != "collected":
        status = "skipped"
        reason = str(collect_nodeid_digest.get("reason", "")) or "pytest nodeids were not collected"
    elif int(counts.get("failed", 0) or 0) or int(counts.get("errors", 0) or 0):
        status = "skipped"
        reason = "failed/error outcomes are excluded from the release non-failing nodeid consistency gate"
    elif nodeid_count == outcome_count:
        status = "pass"
        reason = "collected nodeid count matches passed + skipped + xfailed/xpassed outcomes"
    else:
        status = "fail"
        reason = "collected nodeid count does not match passed + skipped + xfailed/xpassed outcomes"
    return {
        "status": status,
        "nodeid_count": nodeid_count,
        "outcome_count": outcome_count,
        "counted_outcomes": counted_outcomes,
        "delta": nodeid_count - outcome_count,
        "reason": reason,
    }


def _artifact_identity(vault: Path, path_value: str | Path, *, kind: str, source: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    exists = path.is_file()
    return {
        "kind": kind,
        "path": report_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
        "source": source,
    }


def _failed_nodeids(stdout: str) -> list[str]:
    failed: set[str] = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("FAILED "):
            continue
        nodeid = stripped.removeprefix("FAILED ").split(" - ", 1)[0].strip()
        if nodeid:
            failed.add(nodeid)
    return sorted(failed)


def _execution_log_text(result: TimedProcessResult) -> str:
    return "\n".join(["## stdout", result.stdout, "## stderr", result.stderr])


def write_execution_log(vault: Path, out_path: str | Path, result: TimedProcessResult) -> dict[str, Any]:
    path = Path(out_path)
    if not path.is_absolute():
        path = vault / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_execution_log_text(result), encoding="utf-8")
    return _artifact_identity(vault, path, kind="execution_log", source="captured_pytest_stdout_stderr")


def write_failed_nodeids_artifact(
    vault: Path,
    out_path: str | Path,
    *,
    failed_nodeids: list[str],
) -> dict[str, Any]:
    path = Path(out_path)
    if not path.is_absolute():
        path = vault / path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(failed_nodeids)
    if payload:
        payload = f"{payload}\n"
    path.write_text(payload, encoding="utf-8")
    return _artifact_identity(vault, path, kind="failed_nodeids", source="pytest_failure_nodeids")


def _artifact_path(vault: Path, artifact: dict[str, Any]) -> Path:
    path = Path(str(artifact.get("path", "")))
    if not path.is_absolute():
        path = vault / path
    return path


def _non_empty_line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _junit_testcase_count(path: Path) -> int | None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None

    suite_counts: list[int] = []
    for element in root.iter():
        if _xml_local_name(str(element.tag)) != "testsuite":
            continue
        value = element.attrib.get("tests")
        if value is None:
            continue
        try:
            suite_counts.append(int(value))
        except ValueError:
            return None
    if suite_counts:
        return sum(suite_counts)
    return sum(1 for element in root.iter() if _xml_local_name(str(element.tag)) == "testcase")


def _counted_outcome_total(counts: dict[str, int]) -> int:
    return sum(
        int(counts.get(key, 0) or 0)
        for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")
    )


def _evidence_artifact_consistency(
    vault: Path,
    *,
    counts: dict[str, int],
    evidence_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    expected_failed_nodeids = int(counts.get("failed", 0) or 0) + int(counts.get("errors", 0) or 0)
    expected_junit_tests = _counted_outcome_total(counts)

    for artifact in evidence_artifacts:
        kind = str(artifact.get("kind", ""))
        if kind not in {"failed_nodeids", "junit_xml"}:
            continue
        path = _artifact_path(vault, artifact)
        rel_path = report_path(vault, path)
        if not path.is_file():
            check = {
                "kind": kind,
                "path": rel_path,
                "status": "fail",
                "expected_count": 0,
                "observed_count": 0,
            }
            checks.append(check)
            blockers.append(
                {
                    "code": "evidence_artifact_missing",
                    "path": rel_path,
                    "expected_count": 1,
                    "observed_count": 0,
                    "message": f"{kind} evidence artifact is referenced but missing.",
                }
            )
            continue

        if kind == "failed_nodeids":
            observed = _non_empty_line_count(path)
            expected = expected_failed_nodeids
            code = "failed_nodeids_count_mismatch"
            message = "failed-nodeids artifact line count does not match failed + error pytest outcomes."
        else:
            observed_count = _junit_testcase_count(path)
            if observed_count is None:
                check = {
                    "kind": kind,
                    "path": rel_path,
                    "status": "fail",
                    "expected_count": expected_junit_tests,
                    "observed_count": 0,
                }
                checks.append(check)
                blockers.append(
                    {
                        "code": "junit_xml_unreadable",
                        "path": rel_path,
                        "expected_count": expected_junit_tests,
                        "observed_count": 0,
                        "message": "JUnit XML evidence artifact could not be parsed.",
                    }
                )
                continue
            observed = observed_count
            expected = expected_junit_tests
            code = "junit_testcase_count_mismatch"
            message = "JUnit testcase count does not match counted pytest outcomes."

        status = "pass" if observed == expected else "fail"
        checks.append(
            {
                "kind": kind,
                "path": rel_path,
                "status": status,
                "expected_count": expected,
                "observed_count": observed,
            }
        )
        if status != "pass":
            blockers.append(
                {
                    "code": code,
                    "path": rel_path,
                    "expected_count": expected,
                    "observed_count": observed,
                    "message": message,
                }
            )

    return {
        "status": "fail" if blockers else "pass" if checks else "skipped",
        "checked_artifact_count": len(checks),
        "checks": checks,
        "blockers": blockers,
    }


_BUILD_REPORT_KWARGS = {
    "command",
    "result",
    "duration_ms",
    "suite",
    "policy_path",
    "context",
    "collect_nodeids",
    "collect_nodeid_digest",
    "evidence_artifacts",
    "deselection_policy_path",
}


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _test_execution_report_request(
    request: TestExecutionReportRequest | None,
    legacy_kwargs: dict[str, Any],
) -> TestExecutionReportRequest:
    if request is not None:
        if legacy_kwargs:
            names = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"build_report request cannot be combined with legacy keyword arguments: {names}")
        if not isinstance(request, TestExecutionReportRequest):
            raise TypeError("build_report request must be a TestExecutionReportRequest")
        return request

    missing = {"command", "result", "duration_ms", "suite"} - set(legacy_kwargs)
    extra = set(legacy_kwargs) - _BUILD_REPORT_KWARGS
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing required keyword arguments: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"unexpected keyword arguments: {', '.join(sorted(extra))}")
        raise TypeError("; ".join(parts))

    result = legacy_kwargs["result"]
    context = legacy_kwargs.get("context")
    if not isinstance(result, TimedProcessResult):
        raise TypeError("build_report result must be a TimedProcessResult")
    if context is not None and not isinstance(context, RuntimeContext):
        raise TypeError("build_report context must be a RuntimeContext")

    return TestExecutionReportRequest(
        command=[str(item) for item in legacy_kwargs["command"]],
        result=result,
        duration_ms=int(legacy_kwargs["duration_ms"]),
        suite=str(legacy_kwargs["suite"]),
        policy_path=_optional_text(legacy_kwargs.get("policy_path")),
        context=context,
        collect_nodeids=bool(legacy_kwargs.get("collect_nodeids", False)),
        collect_nodeid_digest=legacy_kwargs.get("collect_nodeid_digest"),
        evidence_artifacts=legacy_kwargs.get("evidence_artifacts"),
        deselection_policy_path=_optional_text(legacy_kwargs.get("deselection_policy_path")),
    )


def _default_collect_nodeid_digest() -> dict[str, Any]:
    return {
        "status": "skipped",
        "command": "",
        "nodeid_count": 0,
        "sha256": "",
        "reason": "collect-nodeids was not requested",
    }


def _pytest_stdout_deselected_count(stdout: str) -> int:
    total = 0
    for match in PYTEST_DESELECTED_RE.finditer(stdout):
        total = max(total, int(match.group("count")))
    return total


def _test_execution_observations(
    vault: Path,
    request: TestExecutionReportRequest,
    *,
    generated_at: str,
) -> TestExecutionObservations:
    counts = parse_pytest_counts(request.result.stdout, request.result.stderr)
    target_paths = resolve_pytest_target_paths(vault, request.command)
    test_target_fingerprints = build_test_target_fingerprints(vault, target_paths)
    deselected_tests = structured_deselected_tests(
        request.command,
        vault=vault,
        deselection_policy_path=request.deselection_policy_path,
    )
    deselection_lifecycle = _deselection_lifecycle(
        deselected_tests,
        generated_at=generated_at,
        policy_payload=_load_deselection_policy_payload(vault, request.deselection_policy_path),
    )
    policy_deselected_count = len(deselected_tests)
    pytest_marker_deselected_count = max(
        0,
        _pytest_stdout_deselected_count(request.result.stdout) - policy_deselected_count,
    )
    collect_nodeid_digest = request.collect_nodeid_digest
    if collect_nodeid_digest is None:
        collect_nodeid_digest = _default_collect_nodeid_digest()
    nodeid_outcome_consistency = _nodeid_outcome_consistency(counts, collect_nodeid_digest)
    evidence_artifacts = list(request.evidence_artifacts or [])
    evidence_artifact_consistency = _evidence_artifact_consistency(
        vault,
        counts=counts,
        evidence_artifacts=evidence_artifacts,
    )
    execution_environment = build_execution_environment(vault, request.command)
    coverage = _apply_toolchain_contract_to_coverage(
        _suite_coverage(suite=request.suite, command=request.command),
        execution_environment,
    )
    return TestExecutionObservations(
        counts=counts,
        target_paths=target_paths,
        test_target_fingerprints=test_target_fingerprints,
        deselected_tests=deselected_tests,
        deselection_lifecycle=deselection_lifecycle,
        pytest_marker_deselected_count=pytest_marker_deselected_count,
        policy_deselected_count=policy_deselected_count,
        collect_nodeid_digest=collect_nodeid_digest,
        nodeid_outcome_consistency=nodeid_outcome_consistency,
        evidence_artifacts=evidence_artifacts,
        evidence_artifact_consistency=evidence_artifact_consistency,
        execution_environment=execution_environment,
        coverage=coverage,
        status=classify_status(request.result, counts),
    )


def _test_execution_source_command(vault: Path, request: TestExecutionReportRequest) -> str:
    collect_option = " --collect-nodeids" if request.collect_nodeids else ""
    base = f"python -m ops.scripts.test_execution_summary --vault . --suite {request.suite}{collect_option}"
    if request.deselection_policy_path:
        return (
            f"{base} --deselection-policy {shlex.quote(request.deselection_policy_path)} -- "
            f"{_display_command(vault, request.command)}"
        )
    return f"{base} -- {_display_command(vault, request.command)}"


def _test_execution_file_inputs(request: TestExecutionReportRequest) -> dict[str, str] | None:
    if not request.deselection_policy_path:
        return None
    return {"deselection_policy": request.deselection_policy_path}


def _test_execution_text_inputs(
    vault: Path,
    request: TestExecutionReportRequest,
    observations: TestExecutionObservations,
) -> dict[str, str]:
    return {
        "wrapped_command": _display_command(vault, request.command),
        "suite": request.suite,
        "suite_coverage": json.dumps(observations.coverage, sort_keys=True, separators=(",", ":")),
        "deselected_tests": json.dumps(
            observations.deselected_tests,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "deselection_lifecycle": json.dumps(
            observations.deselection_lifecycle,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "nodeid_outcome_consistency": json.dumps(
            observations.nodeid_outcome_consistency,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "evidence_artifacts": json.dumps(
            observations.evidence_artifacts,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "evidence_artifact_consistency": json.dumps(
            observations.evidence_artifact_consistency,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _render_test_execution_summary(inputs: TestExecutionRenderInputs) -> dict[str, Any]:
    vault = inputs.vault
    request = inputs.request
    observations = inputs.observations
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=inputs.generated_at,
            artifact_kind="test_execution_summary",
            producer=PRODUCER,
            source_command=_test_execution_source_command(vault, request),
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/test_execution_summary.py",
                "ops/scripts/command_runtime.py",
            ],
            text_inputs=_test_execution_text_inputs(vault, request, observations),
            file_inputs=_test_execution_file_inputs(request),
            path_group_inputs={"test_targets": observations.target_paths} if observations.target_paths else None,
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "suite": request.suite,
        **observations.coverage,
        "status": observations.status,
        "command": _display_command(vault, request.command),
        "returncode": request.result.returncode,
        "timed_out": request.result.timed_out,
        "timeout_seconds": request.result.timeout_seconds,
        "termination_reason": request.result.termination_reason,
        "duration_ms": request.duration_ms,
        "counts": observations.counts,
        "execution_environment": observations.execution_environment,
        "test_target_fingerprints": observations.test_target_fingerprints,
        "deselected_tests": observations.deselected_tests,
        "deselection_lifecycle": observations.deselection_lifecycle,
        "pytest_marker_deselected_count": observations.pytest_marker_deselected_count,
        "policy_deselected_count": observations.policy_deselected_count,
        "pytest_collect_nodeid_digest": observations.collect_nodeid_digest,
        "nodeid_outcome_consistency": observations.nodeid_outcome_consistency,
        "evidence_artifacts": observations.evidence_artifacts,
        "evidence_artifact_consistency": observations.evidence_artifact_consistency,
        "stdout_tail": sanitize_report_text(vault, _tail_text(request.result.stdout)),
        "stderr_tail": sanitize_report_text(vault, _tail_text(request.result.stderr)),
        "release_contract_diagnosis": _build_release_contract_diagnosis(
            suite=request.suite,
            status=observations.status,
            command=_display_command(vault, request.command),
            duration_ms=request.duration_ms,
            generated_at=inputs.generated_at,
            deselection_lifecycle=observations.deselection_lifecycle,
        ),
    }


def build_report(
    vault: Path,
    request: TestExecutionReportRequest | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    request = _test_execution_report_request(request, legacy_kwargs)
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    observations = _test_execution_observations(
        vault,
        request,
        generated_at=generated_at,
    )
    return _render_test_execution_summary(
        TestExecutionRenderInputs(
            vault=vault,
            request=request,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            generated_at=generated_at,
            observations=observations,
        )
    )


def _build_release_contract_diagnosis(
    *,
    suite: str,
    status: str,
    command: str,
    duration_ms: int,
    generated_at: str,
    deselection_lifecycle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build release contract diagnosis entries for this test execution."""
    diagnosis: list[dict[str, Any]] = []

    # Pytest contract summary (the actual executed suite)
    lane = "clean" if status == "pass" else "blocked"
    blocker_conditions: list[str] = []
    if status == "fail":
        blocker_conditions.append("pytest_suite_failed")
    if deselection_lifecycle.get("status") != "pass":
        blocker_conditions.append("deselection_lifecycle_not_pass")

    diagnosis.append(
        {
            "name": "pytest_contract_summary",
            "status": "clean_pass" if status == "pass" else "blocked",
            "lane": lane,
            "command": command,
            "duration_seconds": round(duration_ms / 1000, 2),
            "checked_at": generated_at,
            "blocker_conditions": blocker_conditions,
            "accepted_risk_family": None,
            "risk_acceptance_ref": None,
            "reason": "",
        }
    )

    # Static checks (ruff, mypy) are executed via `make static` in the
    # release-evidence-closeout recipe. They do not run inside this pytest
    # wrapper, so they are recorded as externally executed.
    diagnosis.append(
        {
            "name": "static_checks",
            "status": "not_run",
            "lane": "blocked",
            "command": "make static",
            "duration_seconds": None,
            "checked_at": None,
            "blocker_conditions": ["external_static_evidence_not_captured_by_summary"],
            "accepted_risk_family": None,
            "risk_acceptance_ref": None,
            "reason": "not executed inside this pytest summary; use release-builder evidence before treating static checks as covered",
        }
    )

    return diagnosis


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


def reusable_summary_is_current(
    existing: dict[str, Any],
    *,
    vault: Path,
    command: list[str],
    suite: str,
    collect_nodeids: bool,
    collect_nodeid_digest: dict[str, Any] | None,
    deselection_policy_path: str | None = None,
) -> bool:
    target_paths = resolve_pytest_target_paths(vault, command)
    current_target_fingerprints = build_test_target_fingerprints(vault, target_paths)
    current_deselected_tests = structured_deselected_tests(
        command,
        vault=vault,
        deselection_policy_path=deselection_policy_path,
    )
    policy, _ = load_policy(vault)
    generated_at = RuntimeContext.from_policy(policy).isoformat_z()
    current_lifecycle = _deselection_lifecycle(
        current_deselected_tests,
        generated_at=generated_at,
        policy_payload=_load_deselection_policy_payload(vault, deselection_policy_path),
    )
    existing_lifecycle = existing.get("deselection_lifecycle")
    if not isinstance(existing_lifecycle, dict):
        existing_lifecycle = {}
    return (
        existing.get("artifact_kind") == "test_execution_summary"
        and existing.get("status") == "pass"
        and existing_lifecycle.get("status") == "pass"
        and current_lifecycle.get("status") == "pass"
        and existing.get("suite") == suite
        and existing.get("command") == _display_command(vault, command)
        and _test_target_fingerprints_match(
            existing.get("test_target_fingerprints"),
            current_target_fingerprints,
        )
        and _deselected_tests_match(existing.get("deselected_tests"), current_deselected_tests)
        and _collect_nodeid_digest_matches(
            existing,
            collect_nodeid_digest,
            collect_nodeids=collect_nodeids,
        )
        and (
            not collect_nodeids
            or existing.get("nodeid_outcome_consistency", {}).get("status") == "pass"
        )
    )


def build_reused_report(
    vault: Path,
    *,
    existing: dict[str, Any],
    command: list[str],
    suite: str,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    collect_nodeids: bool = False,
    collect_nodeid_digest: dict[str, Any] | None = None,
    deselection_policy_path: str | None = None,
) -> dict[str, Any]:
    result = TimedProcessResult(
        args=[str(item) for item in command],
        returncode=0,
        stdout=str(existing.get("stdout_tail", "")),
        stderr=str(existing.get("stderr_tail", "")),
        timed_out=False,
        timeout_seconds=int(existing.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS) or DEFAULT_TIMEOUT_SECONDS),
        termination_reason="reused_current_summary",
    )
    report = build_report(
        vault,
        command=command,
        result=result,
        duration_ms=int(existing.get("duration_ms", 0) or 0),
        suite=suite,
        policy_path=policy_path,
        context=context,
        collect_nodeids=collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        evidence_artifacts=[
            item for item in existing.get("evidence_artifacts", []) if isinstance(item, dict)
        ],
        deselection_policy_path=deselection_policy_path,
    )
    report["counts"] = dict(existing.get("counts", {}))
    report["nodeid_outcome_consistency"] = _nodeid_outcome_consistency(
        report["counts"],
        collect_nodeid_digest or dict(existing.get("pytest_collect_nodeid_digest", {})),
    )
    report["evidence_artifact_consistency"] = _evidence_artifact_consistency(
        vault,
        counts=report["counts"],
        evidence_artifacts=[
            item for item in existing.get("evidence_artifacts", []) if isinstance(item, dict)
        ],
    )
    report["termination_reason"] = "reused_current_summary"
    report["stdout_tail"] = str(existing.get("stdout_tail", ""))
    report["stderr_tail"] = str(existing.get("stderr_tail", ""))
    report["summary_mode"] = "reused"
    report["reused_from"] = str(existing.get("generated_at", ""))
    return report


def _load_summary(vault: Path, path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = load_schema_with_vault_override(vault, TEST_EXECUTION_SUMMARY_SCHEMA_PATH)
    validate_or_raise(payload, schema, context=f"test execution summary shard validation failed for {report_path(vault, path)}")
    return payload


def _aggregate_status(statuses: list[str]) -> str:
    if any(status in {"fail", "timeout", "interrupted"} for status in statuses):
        return "fail"
    if any(status == "partial-pass" for status in statuses):
        return "partial-pass"
    return "pass"


def _aggregate_counts(shards: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 0,
    }
    for shard in shards:
        shard_counts = shard.get("counts", {})
        if not isinstance(shard_counts, dict):
            continue
        for key in counts:
            counts[key] += int(shard_counts.get(key, 0) or 0)
    return counts


def _summary_shard_paths(vault: Path, aggregate_from: list[str], aggregate_dir: str) -> list[str]:
    if aggregate_from:
        return sorted(str(item) for item in aggregate_from)
    directory = Path(aggregate_dir)
    if not directory.is_absolute():
        directory = vault / directory
    if not directory.is_dir():
        return []
    return sorted(report_path(vault, path) for path in directory.glob("*.json") if path.is_file())


def _aggregate_deselection_lifecycle(
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


def _aggregate_shard_refs(shard_paths: list[str], shards: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _aggregate_shard_dict_items(shards: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    return [
        item
        for shard in shards
        for item in shard.get(field, [])
        if isinstance(item, dict)
    ]


def _aggregate_nested_int(shards: list[dict[str, Any]], field: str, key: str) -> int:
    return sum(
        int(shard.get(field, {}).get(key, 0) or 0)
        for shard in shards
        if isinstance(shard.get(field), dict)
    )


def _aggregate_nodeid_digest(shards: list[dict[str, Any]]) -> dict[str, Any]:
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
    }


def _aggregate_nodeid_consistency(
    shards: list[dict[str, Any]],
    counts: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    collect_digest = _aggregate_nodeid_digest(shards)
    consistency = _nodeid_outcome_consistency(counts, collect_digest)
    if collect_digest.get("status") != "collected":
        consistency["reason"] = str(collect_digest.get("reason", "")) or consistency["reason"]
    return collect_digest, consistency


def _aggregate_source_command(suite: str, shard_paths: list[str]) -> str:
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
    shards = [_load_summary(vault, path) for path in shard_paths]
    statuses = [str(shard.get("status", "fail")) for shard in shards]
    status = _aggregate_status(statuses) if shards else "fail"
    counts = _aggregate_counts(shards)
    command = "aggregate test execution summary shards"
    shard_refs = _aggregate_shard_refs(shard_paths, shards)
    deselected_tests = _aggregate_shard_dict_items(shards, "deselected_tests")
    deselection_lifecycle = _aggregate_deselection_lifecycle(
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
    collect_nodeid_digest, nodeid_outcome_consistency = _aggregate_nodeid_consistency(shards, counts)
    evidence_artifacts = _aggregate_shard_dict_items(shards, "evidence_artifacts")
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
            source_command=_aggregate_source_command(suite, shard_paths),
            resolved_policy_path=resolved_policy_path,
            schema_path=TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/test_execution_summary.py",
                "ops/scripts/command_runtime.py",
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
        "returncode": 0 if status == "pass" else 1,
        "timed_out": any(bool(shard.get("timed_out")) for shard in shards),
        "timeout_seconds": max([int(shard.get("timeout_seconds", 1) or 1) for shard in shards] or [1]),
        "termination_reason": "completed" if status == "pass" else "one_or_more_shards_not_pass",
        "duration_ms": sum(int(shard.get("duration_ms", 0) or 0) for shard in shards),
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


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=TEST_EXECUTION_SUMMARY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="test execution summary schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a test command and write a schema-backed execution summary")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--suite", default="pytest")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--collect-nodeids", action="store_true")
    parser.add_argument("--collect-timeout-seconds", type=int, default=300)
    parser.add_argument("--junit-xml-path")
    parser.add_argument("--execution-log-out")
    parser.add_argument("--failed-nodeids-out")
    parser.add_argument("--deselection-policy")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--aggregate-dir", default=DEFAULT_SHARD_DIR)
    parser.add_argument("--aggregate-from", action="append", default=[])
    parser.add_argument("--reuse-if-current", action="store_true")
    parser.add_argument("--reuse-from")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        args.command = [sys.executable, "-m", "pytest"]
    return args


def _write_and_print_report(vault: Path, report: dict[str, Any], out_path: str | None) -> None:
    destination = write_report(vault, report, out_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten_to={display_path(vault, destination)}")


def _run_aggregate_cli(vault: Path, args: argparse.Namespace) -> int:
    shard_paths = _summary_shard_paths(vault, list(args.aggregate_from), args.aggregate_dir)
    if not shard_paths:
        print(f"no test execution summary shards found under {args.aggregate_dir}", file=sys.stderr)
        return 1
    report = build_aggregate_report(
        vault,
        shard_paths=shard_paths,
        suite=args.suite,
        policy_path=args.policy,
    )
    _write_and_print_report(vault, report, args.out)
    return 0 if report["status"] == "pass" else 1


def _collect_nodeid_digest_for_args(vault: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    if args.collect_nodeids:
        return collect_pytest_nodeid_digest(
            vault,
            args.command,
            timeout_seconds=args.collect_timeout_seconds,
        )
    return None


def _reused_report_for_args(
    vault: Path,
    args: argparse.Namespace,
    *,
    collect_nodeid_digest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if args.reuse_if_current:
        reuse_path = args.reuse_from or args.out
        try:
            existing = _load_summary(vault, reuse_path)
        except (OSError, json.JSONDecodeError, ValueError):
            existing = {}
        if existing and reusable_summary_is_current(
            existing,
            vault=vault,
            command=args.command,
            suite=args.suite,
            collect_nodeids=args.collect_nodeids,
            collect_nodeid_digest=collect_nodeid_digest,
            deselection_policy_path=args.deselection_policy,
        ):
            report = build_reused_report(
                vault,
                existing=existing,
                command=args.command,
                suite=args.suite,
                policy_path=args.policy,
                collect_nodeids=args.collect_nodeids,
                collect_nodeid_digest=collect_nodeid_digest,
                deselection_policy_path=args.deselection_policy,
            )
            return report
    return None


def _interrupted_report(
    vault: Path,
    args: argparse.Namespace,
    *,
    started_at: float,
    collect_nodeid_digest: dict[str, Any] | None,
) -> dict[str, Any]:
    elapsed_ms = max(0, int(round((time.monotonic() - started_at) * 1000)))
    result = TimedProcessResult(
        args=[str(item) for item in args.command],
        returncode=130,
        stdout="",
        stderr="KeyboardInterrupt",
        timed_out=False,
        timeout_seconds=args.timeout_seconds,
        termination_reason="interrupted",
    )
    return build_report(
        vault,
        command=args.command,
        result=result,
        duration_ms=elapsed_ms,
        suite=args.suite,
        policy_path=args.policy,
        collect_nodeids=args.collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        evidence_artifacts=[],
        deselection_policy_path=args.deselection_policy,
    )


def _evidence_artifacts_for_args(
    vault: Path,
    args: argparse.Namespace,
    result: TimedProcessResult,
) -> list[dict[str, Any]]:
    evidence_artifacts: list[dict[str, Any]] = []
    if args.execution_log_out:
        evidence_artifacts.append(write_execution_log(vault, args.execution_log_out, result))
    if args.junit_xml_path:
        evidence_artifacts.append(
            _artifact_identity(
                vault,
                args.junit_xml_path,
                kind="junit_xml",
                source="pytest_junit_xml",
            )
        )
    if args.failed_nodeids_out:
        evidence_artifacts.append(
            write_failed_nodeids_artifact(
                vault,
                args.failed_nodeids_out,
                failed_nodeids=_failed_nodeids(result.stdout),
            )
        )
    return evidence_artifacts


def _executed_report_for_args(
    vault: Path,
    args: argparse.Namespace,
    *,
    collect_nodeid_digest: dict[str, Any] | None,
) -> tuple[dict[str, Any], int]:
    started_at = time.monotonic()
    try:
        result = run_with_timeout(
            args.command,
            cwd=vault,
            timeout_seconds=args.timeout_seconds,
        )
    except KeyboardInterrupt:
        return (
            _interrupted_report(
                vault,
                args,
                started_at=started_at,
                collect_nodeid_digest=collect_nodeid_digest,
            ),
            130,
        )

    elapsed_ms = max(0, int(round((time.monotonic() - started_at) * 1000)))
    report = build_report(
        vault,
        command=args.command,
        result=result,
        duration_ms=elapsed_ms,
        suite=args.suite,
        policy_path=args.policy,
        collect_nodeids=args.collect_nodeids,
        collect_nodeid_digest=collect_nodeid_digest,
        evidence_artifacts=_evidence_artifacts_for_args(vault, args, result),
        deselection_policy_path=args.deselection_policy,
    )
    return report, 0 if report["status"] == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.aggregate or args.aggregate_from:
        return _run_aggregate_cli(vault, args)

    collect_nodeid_digest = _collect_nodeid_digest_for_args(vault, args)
    report = _reused_report_for_args(
        vault,
        args,
        collect_nodeid_digest=collect_nodeid_digest,
    )
    if report is not None:
        _write_and_print_report(vault, report, args.out)
        return 0

    report, returncode = _executed_report_for_args(
        vault,
        args,
        collect_nodeid_digest=collect_nodeid_digest,
    )
    _write_and_print_report(vault, report, args.out)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
