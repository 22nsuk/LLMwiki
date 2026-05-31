from __future__ import annotations

from ops.scripts.test.test_execution_selection_runtime import (
    apply_toolchain_contract_to_coverage,
    pytest_deselected_nodeids,
    pytest_selector_args,
    suite_coverage,
)


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
