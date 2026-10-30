from __future__ import annotations

import pytest

from ops.scripts.test.test_execution_command_runtime import collection_semantic_command
from ops.scripts.test.test_execution_selection_runtime import (
    apply_toolchain_contract_to_coverage,
    pytest_deselected_nodeids,
    pytest_selector_args,
    suite_coverage,
)


@pytest.mark.parametrize("option", ["--junit-xml", "--junitxml"])
@pytest.mark.parametrize("joined", [False, True], ids=["separate", "equals"])
@pytest.mark.parametrize(
    ("scope", "selectors"),
    [([], []), (["tests/test_sample.py"], ["tests/test_sample.py"]),
     (["tests/test_sample.py::test_one"], ["tests/test_sample.py::test_one"]),
     (["-m", "smoke"], [])],
    ids=["full", "file", "nodeid", "marker"],
)
def test_junit_output_option_preserves_pytest_selection(
    option: str, joined: bool, scope: list[str], selectors: list[str],
) -> None:
    output = "tmp/junit results.xml"
    output_args = [f"{option}={output}"] if joined else [option, output]
    command = ["python", "-m", "pytest", *output_args, *scope, "-q"]

    assert pytest_selector_args(command) == selectors
    assert collection_semantic_command(command) == ["-m", "pytest", *scope, "-q"]
    assert suite_coverage(suite="full", command=command)["represents_full_suite"] is (not scope)


def test_pytest_selector_args_ignore_option_values() -> None:
    selectors = pytest_selector_args(
        [
            "python",
            "-m",
            "pytest",
            "-k",
            "smoke",
            "--maxfail=1",
            "tests/test_sample.py",
        ]
    )

    assert selectors == ["tests/test_sample.py"]


def test_suite_coverage_distinguishes_report_contract_and_full_aggregate() -> None:
    targeted = suite_coverage(
        suite="report-contract-summary",
        command=["python", "-m", "pytest"],
    )
    aggregate_full = suite_coverage(
        suite="full",
        command=["python", "-m", "pytest"],
        summary_mode="aggregate",
        shards=[{"represents_full_suite": True}, {"represents_full_suite": True}],
    )

    assert targeted["suite_scope"] == "report_contract_summary"
    assert targeted["represents_full_suite"] is False
    assert aggregate_full["suite_scope"] == "full_suite"
    assert aggregate_full["represents_full_suite"] is True
    assert (
        aggregate_full["full_suite_evidence"]["required_command"]
        == "make test-execution-summary-full-current-or-refresh"
    )
    assert aggregate_full["full_suite_evidence"]["raw_pytest_command"] == "python -m pytest"
    assert aggregate_full["full_suite_evidence"]["developer_regression_command"] == "make test-all"


def test_toolchain_failure_demotes_full_suite_coverage() -> None:
    demoted = apply_toolchain_contract_to_coverage(
        suite_coverage(suite="full", command=["python", "-m", "pytest"]),
        {"toolchain_contract": {"status": "fail", "reason": "unsupported pytest"}},
    )

    assert demoted["represents_full_suite"] is False
    assert demoted["full_suite_evidence"]["status"] == "not_represented"


def test_pytest_deselected_nodeids_preserves_cli_entries() -> None:
    assert pytest_deselected_nodeids(
        [
            "python",
            "-m",
            "pytest",
            "--deselect=tests/test_sample.py::test_one",
            "--deselect",
            "tests/test_sample.py::test_one",
        ]
    ) == ["tests/test_sample.py::test_one", "tests/test_sample.py::test_one"]
