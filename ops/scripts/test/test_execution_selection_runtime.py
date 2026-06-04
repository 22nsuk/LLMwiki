#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.test.test_execution_command_runtime import (
    PYTEST_COLLECTION_FILTER_FLAGS,
    PYTEST_OPTION_VALUE_FLAGS,
    RELEASE_BUILDER_ENVIRONMENT,
)

REPORT_CONTRACT_SUMMARY_SUITE = "report-contract-summary"
RAW_FULL_SUITE_PYTEST_COMMAND = "python -m pytest"
FULL_SUITE_COMMAND = "make test-execution-summary-full-current-or-refresh"
DEVELOPER_FULL_REGRESSION_COMMAND = "make test-all"
FULL_SUITE_SCOPES = {"full", "full-suite", "pytest"}
RELEASE_BUILDER_FULL_SCOPES = {"release-builder-full", "release_builder_full"}
FULL_SUITE_SHARD_PREFIX = "full-shard-"


def pytest_args(command: list[str]) -> list[str]:
    for index, item in enumerate(command):
        value = str(item)
        name = Path(value).name
        if value == "pytest" or name.startswith("pytest"):
            return [str(arg) for arg in command[index + 1 :]]
        if value == "-m" and index + 1 < len(command) and str(command[index + 1]) == "pytest":
            return [str(arg) for arg in command[index + 2 :]]
    return []


def pytest_selector_args(command: list[str]) -> list[str]:
    selectors: list[str] = []
    args = pytest_args(command)
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


def pytest_collection_filter_args(command: list[str]) -> list[str]:
    filters: list[str] = []
    args = pytest_args(command)
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


def suite_coverage(
    *,
    suite: str,
    command: list[str],
    summary_mode: str = "single",
    shards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selectors = pytest_selector_args(command)
    collection_filters = pytest_collection_filter_args(command)
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
        suite_scope = "full_suite" if represents_full_suite else suite_scope_for_key(suite_key)
        not_full_suite_reason = (
            ""
            if represents_full_suite
            else "aggregate summary does not represent the full suite unless every shard does"
        )
    elif collection_limited:
        suite_scope = suite_scope_for_key(suite_key)
        represents_full_suite = False
        not_full_suite_reason = "pytest selectors limit this execution to a targeted suite subset"
    else:
        suite_scope = suite_scope_for_key(suite_key)
        represents_full_suite = suite_scope in {"full_suite", "release_builder_full"}
        not_full_suite_reason = "" if represents_full_suite else f"{suite_scope} is not full-suite evidence"

    return {
        "suite_scope": suite_scope,
        "represents_full_suite": represents_full_suite,
        "not_full_suite_reason": not_full_suite_reason,
        "full_suite_evidence": {
            "status": "represented" if represents_full_suite else "not_represented",
            "required_command": FULL_SUITE_COMMAND,
            "raw_pytest_command": RAW_FULL_SUITE_PYTEST_COMMAND,
            "developer_regression_command": DEVELOPER_FULL_REGRESSION_COMMAND,
            "release_builder_environment": RELEASE_BUILDER_ENVIRONMENT,
            "reason": (
                "this execution has no pytest selectors and is treated as full-suite evidence"
                if represents_full_suite
                else not_full_suite_reason
            ),
        },
    }


def apply_toolchain_contract_to_coverage(
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


def suite_scope_for_key(suite_key: str) -> str:
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
    if suite_key in {"release-sealing", "release_sealing"}:
        return "release_sealing"
    if suite_key in {"subprocess", "subprocess-integration"}:
        return "subprocess_integration"
    return "fast_unit"


def pytest_collect_modifiers(command: list[str]) -> list[str]:
    modifiers: list[str] = []
    args = pytest_args(command)
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


def pytest_deselected_nodeids(command: list[str]) -> list[str]:
    nodeids: list[str] = []
    args = pytest_args(command)
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
