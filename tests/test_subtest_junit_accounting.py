from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

import pytest
from _pytest.reports import TestReport
from _pytest.unittest import SubtestReport

from ops.scripts.test.test_execution_derivation_runtime import (
    JUNIT_SUBTESTS_PASSED_PROPERTY,
    parse_junit_testcases,
)

pytestmark = pytest.mark.subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTION_MODES = [
    pytest.param("direct", (), id="direct"),
    pytest.param("xdist", ("-p", "xdist.plugin", "-n", "2"), id="xdist"),
]


def _run_junit_subprocess(
    fixture_source: str,
    *,
    mode_args: tuple[str, ...],
) -> tuple[subprocess.CompletedProcess[str], bytes]:
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_path = temp_path / "test_sample.py"
        junit_path = temp_path / "junit.xml"
        test_path.write_text(fixture_source, encoding="utf-8")
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-p",
                "tests.conftest",
                *mode_args,
                "--junitxml",
                str(junit_path),
                str(test_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        return completed, junit_path.read_bytes()


def _subtest_properties(junit_xml: bytes) -> dict[str, list[str | None]]:
    return {
        testcase.attrib["name"]: [
            prop.attrib.get("value")
            for prop in testcase.findall("./properties/property")
            if prop.attrib.get("name") == JUNIT_SUBTESTS_PASSED_PROPERTY
        ]
        for testcase in ET.fromstring(junit_xml).iter("testcase")
    }


def _load_repo_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "subtest_junit_conftest_under_test",
        REPO_ROOT / "tests" / "conftest.py",
    )
    if spec is None or spec.loader is None:
        raise unittest.SkipTest("tests/conftest.py is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _teardown_report(
    *, nodeid: str = "test_sample.py::SampleTests::test_parent"
) -> TestReport:
    return TestReport(
        nodeid=nodeid,
        location=("test_sample.py", 1, "SampleTests.test_parent"),
        keywords={},
        outcome="passed",
        longrepr=None,
        when="teardown",
    )


def _passed_subtest_report(
    *, nodeid: str = "test_sample.py::SampleTests::test_parent"
) -> SubtestReport:
    return SubtestReport(
        nodeid=nodeid,
        location=("test_sample.py", 1, "SampleTests.test_parent"),
        keywords={},
        outcome="passed",
        longrepr=None,
        when="call",
        context=None,
    )


@pytest.mark.parametrize(("mode", "mode_args"), EXECUTION_MODES)
def test_junit_records_reconcilable_subtests_per_parent(
    mode: str, mode_args: tuple[str, ...]
) -> None:
    fixture_source = """\
import unittest


class SampleTests(unittest.TestCase):
    def test_with_subtests(self):
        for value in range(3):
            with self.subTest(value=value):
                self.assertLess(value, 3)

    def test_without_subtests(self):
        self.assertTrue(True)

    @unittest.expectedFailure
    def test_expected_failure(self):
        self.assertEqual(1, 2)
"""

    completed, junit_xml = _run_junit_subprocess(
        fixture_source, mode_args=mode_args
    )

    assert completed.returncode == 0, (
        f"mode={mode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert _subtest_properties(junit_xml) == {
        "test_expected_failure": ["0"],
        "test_with_subtests": ["3"],
        "test_without_subtests": ["0"],
    }
    nodeids = [
        f"test_sample.py::SampleTests::{name}"
        for name in (
            "test_expected_failure",
            "test_with_subtests",
            "test_without_subtests",
        )
    ]
    evidence = parse_junit_testcases(junit_xml, expected_nodeids=nodeids)
    assert evidence["outcomes"][nodeids[0]] == "xfailed"
    assert evidence["subtests_passed_by_nodeid"] == {
        nodeids[0]: 0,
        nodeids[1]: 3,
        nodeids[2]: 0,
    }


@pytest.mark.parametrize(("mode", "mode_args"), EXECUTION_MODES)
def test_failed_subtest_junit_is_rejected_fail_closed(
    mode: str, mode_args: tuple[str, ...]
) -> None:
    fixture_source = """\
import unittest


class SampleTests(unittest.TestCase):
    def test_with_failed_subtest(self):
        for value in range(2):
            with self.subTest(value=value):
                self.assertEqual(value, 0)
"""
    completed, junit_xml = _run_junit_subprocess(
        fixture_source, mode_args=mode_args
    )

    assert completed.returncode == 1, (
        f"mode={mode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert _subtest_properties(junit_xml) == {"test_with_failed_subtest": ["1"]}
    nodeid = "test_sample.py::SampleTests::test_with_failed_subtest"
    with pytest.raises(
        ValueError,
        match="testcase subtest properties do not match testsuite aggregate",
    ):
        parse_junit_testcases(junit_xml, expected_nodeids=[nodeid])


class SubtestJunitAccountingTests(unittest.TestCase):

    def test_teardown_property_is_idempotent_and_fails_closed_on_bad_input(
        self,
    ) -> None:
        conftest = _load_repo_conftest()

        conftest.pytest_runtest_logreport(_passed_subtest_report())
        conftest.pytest_runtest_logreport(_passed_subtest_report())
        replay = _teardown_report()
        replay.user_properties.append((JUNIT_SUBTESTS_PASSED_PROPERTY, 2))
        conftest.pytest_runtest_logreport(replay)
        self.assertEqual(
            replay.user_properties,
            [(JUNIT_SUBTESTS_PASSED_PROPERTY, 2)],
        )

        following_run = _teardown_report()
        conftest.pytest_runtest_logreport(following_run)
        self.assertEqual(
            following_run.user_properties,
            [(JUNIT_SUBTESTS_PASSED_PROPERTY, 0)],
        )

        for value, error in [
            ("0", "malformed"),
            (-1, "malformed"),
            (1, "conflicting"),
        ]:
            with self.subTest(value=value):
                report = _teardown_report()
                report.user_properties.append((JUNIT_SUBTESTS_PASSED_PROPERTY, value))
                with self.assertRaisesRegex(pytest.UsageError, error):
                    conftest.pytest_runtest_logreport(report)

        duplicate = _teardown_report()
        duplicate.user_properties.extend(
            [
                (JUNIT_SUBTESTS_PASSED_PROPERTY, 0),
                (JUNIT_SUBTESTS_PASSED_PROPERTY, 0),
            ]
        )
        with self.assertRaisesRegex(pytest.UsageError, "duplicate"):
            conftest.pytest_runtest_logreport(duplicate)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
