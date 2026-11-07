#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from ops.scripts.test.test_execution_command_runtime import (
    PYTEST_BOOLEAN_FLAGS,
    PYTEST_CACHE_SELECTION_FLAGS,
    PYTEST_COLLECTION_FILTER_FLAGS,
    PYTEST_JUNIT_OUTPUT_FLAGS,
    PYTEST_OPTION_VALUE_FLAGS,
    RELEASE_BUILDER_ENVIRONMENT,
    is_pytest_command,
    parsed_pytest_args,
    pytest_args as pytest_args,
)

REPORT_CONTRACT_SUMMARY_SUITE = "report-contract-summary"
RAW_FULL_SUITE_PYTEST_COMMAND = "python -m pytest"
FULL_SUITE_COMMAND = "make test-execution-summary-full-current-or-refresh"
DEVELOPER_FULL_REGRESSION_COMMAND = "make test-all"
FULL_SUITE_SCOPES = {"full", "full-suite", "pytest"}
RELEASE_BUILDER_FULL_SCOPES = {"release-builder-full", "release_builder_full"}
FULL_SUITE_SHARD_PREFIX = "full-shard-"


def pytest_selector_args(command: list[str]) -> list[str]:
    return [str(arg.value) for arg in parsed_pytest_args(command) if arg.option is None]


def pytest_collection_filter_args(command: list[str]) -> list[str]:
    return [str(arg.option) for arg in parsed_pytest_args(command)
            if arg.option in PYTEST_COLLECTION_FILTER_FLAGS]


def _unknown_or_nonexecuting_options(command: list[str]) -> bool:
    if not is_pytest_command(command):
        return True
    for arg in parsed_pytest_args(command):
        if arg.option is None or arg.option == "--":
            continue
        if arg.option in {"--collect-only", "--co"}:
            return True
        if arg.option not in PYTEST_OPTION_VALUE_FLAGS | PYTEST_BOOLEAN_FLAGS:
            return True
        if (
            arg.option in {"-o", "--override-ini"}
            and str(arg.value).startswith("addopts=")
            and str(arg.value).removeprefix("addopts=").strip()
        ):
            return True
    return False


def suite_coverage(
    *,
    suite: str,
    command: list[str],
    summary_mode: str = "single",
    shards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selectors = pytest_selector_args(command)
    collection_filters = pytest_collection_filter_args(command)
    collection_limited = bool(selectors or collection_filters) or _unknown_or_nonexecuting_options(command)
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
    reason = (
        "unsupported toolchain blocks full-suite evidence promotion: "
        f"{toolchain.get('reason', 'unknown toolchain contract failure')}"
    )
    return without_full_suite_coverage(coverage, reason)


def without_full_suite_coverage(coverage: dict[str, Any], reason: str) -> dict[str, Any]:
    adjusted = dict(coverage)
    full_suite_evidence = dict(adjusted.get("full_suite_evidence", {}))
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
    return [token for arg in parsed_pytest_args(command)
            if arg.option in PYTEST_COLLECTION_FILTER_FLAGS
            for token in ([str(arg.option), arg.value] if arg.value is not None else [str(arg.option)])]


def pytest_uses_selection_cache(command: list[str]) -> bool:
    return bool(set(pytest_collection_filter_args(command)) & PYTEST_CACHE_SELECTION_FLAGS)


def pytest_collection_args(command: list[str]) -> list[str]:
    # Collection must retain config, plugins and selectors, but must not write
    # execution evidence or change nodeid output formatting/start xdist workers.
    omitted = PYTEST_JUNIT_OUTPUT_FLAGS | {
        "-n", "--dist", "--maxprocesses", "--max-worker-restart",
        "-q", "--quiet", "-v", "--verbose", "--verbosity", "-r",
        "--collect-only", "--co", "--log-file",
        "--ff", "--failed-first", "--nf", "--new-first",
    }
    if not pytest_uses_selection_cache(command):
        omitted.update({"--cache-clear", "--lfnf", "--last-failed-no-failures"})
    # The digest reader needs one nodeid per line, even when addopts or ini
    # settings override global verbosity. Apply this after user overrides and
    # before the delimiter, without changing the original execution command.
    output_format = ["-o", "verbosity_test_cases=-1"]
    parsed = parsed_pytest_args(command)
    collected: list[str] = []
    for index, arg in enumerate(parsed):
        if arg.option == "--":
            return [*collected, *output_format, *(token for item in parsed[index:] for token in item.tokens)]
        if arg.option not in omitted:
            collected.extend(arg.tokens)
    return [*collected, *output_format]


def pytest_deselected_nodeids(command: list[str]) -> list[str]:
    return [arg.value for arg in parsed_pytest_args(command) if arg.option == "--deselect" and arg.value]
