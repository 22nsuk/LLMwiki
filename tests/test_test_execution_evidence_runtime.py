from __future__ import annotations

from pathlib import Path

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.test.test_execution_evidence_runtime import (
    evidence_artifact_consistency,
    failed_nodeids,
    nodeid_outcome_consistency,
    write_execution_log,
    write_failed_nodeids_artifact,
)


def test_nodeid_outcome_consistency_matches_non_failing_counts() -> None:
    consistency = nodeid_outcome_consistency(
        {"passed": 2, "skipped": 1, "xfailed": 0, "xpassed": 0, "failed": 0, "errors": 0},
        {"status": "collected", "nodeid_count": 3},
    )

    assert consistency["status"] == "pass"
    assert consistency["delta"] == 0


def test_failed_nodeid_artifact_consistency_is_count_checked(tmp_path: Path) -> None:
    stdout = "FAILED tests/test_sample.py::test_one - AssertionError\n"
    artifact = write_failed_nodeids_artifact(
        tmp_path,
        "tmp/failed-nodeids.txt",
        failed_nodeids=failed_nodeids(stdout),
        expected_count=1,
    )

    consistency = evidence_artifact_consistency(
        tmp_path,
        counts={"passed": 0, "failed": 1, "errors": 0, "skipped": 0, "xfailed": 0, "xpassed": 0},
        evidence_artifacts=[artifact],
    )

    assert consistency["status"] == "pass"
    assert consistency["checked_artifact_count"] == 1


def test_execution_log_identity_uses_vault_relative_path(tmp_path: Path) -> None:
    artifact = write_execution_log(
        tmp_path,
        "tmp/execution.log",
        TimedProcessResult(
            args=["python", "-m", "pytest"],
            returncode=0,
            stdout="1 passed",
            stderr="",
            timed_out=False,
            timeout_seconds=30,
            termination_reason="completed",
        ),
    )

    assert artifact["path"] == "tmp/execution.log"
    assert artifact["exists"] is True
    assert artifact["sha256"]
