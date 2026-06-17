#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.policy_runtime import report_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def nodeid_outcome_consistency(
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


def artifact_identity(vault: Path, path_value: str | Path, *, kind: str, source: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    exists = path.is_file()
    return {
        "kind": kind,
        "path": report_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": sha256_file(path) if exists else "",
        "source": source,
    }


def _pytest_outcome_total(counts: dict[str, int]) -> int:
    return sum(
        int(counts.get(label, 0) or 0)
        for label in (
            "passed",
            "failed",
            "errors",
            "skipped",
            "xfailed",
            "xpassed",
            "subtests_passed",
        )
    )


def _count_consistency(
    *,
    expected_count: int,
    observed_count: int | None,
    subject: str,
) -> dict[str, Any]:
    if observed_count is None:
        return {
            "consistency_status": "attention",
            "observed_count": 0,
            "expected_count": expected_count,
            "consistency_reason": f"{subject} count could not be read",
        }
    if observed_count == expected_count:
        return {
            "consistency_status": "pass",
            "observed_count": observed_count,
            "expected_count": expected_count,
            "consistency_reason": f"{subject} count matches pytest summary",
        }
    return {
        "consistency_status": "attention",
        "observed_count": observed_count,
        "expected_count": expected_count,
        "consistency_reason": f"{subject} count does not match pytest summary",
    }


def failed_nodeids(stdout: str) -> list[str]:
    failed: set[str] = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        for prefix in ("FAILED ", "ERROR "):
            if not stripped.startswith(prefix):
                continue
            nodeid = stripped.removeprefix(prefix).split(" - ", 1)[0].strip()
            if nodeid:
                failed.add(nodeid)
            break
    return sorted(failed)


def execution_log_text(result: TimedProcessResult) -> str:
    return "\n".join(["## stdout", result.stdout, "## stderr", result.stderr])


def write_execution_log(vault: Path, out_path: str | Path, result: TimedProcessResult) -> dict[str, Any]:
    path = Path(out_path)
    if not path.is_absolute():
        path = vault / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(execution_log_text(result), encoding="utf-8")
    return artifact_identity(vault, path, kind="execution_log", source="captured_pytest_stdout_stderr")


def junit_artifact_identity(
    vault: Path,
    path_value: str | Path,
    *,
    counts: dict[str, int],
) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    artifact = artifact_identity(vault, path, kind="junit_xml", source="pytest_junit_xml")
    if not artifact["exists"]:
        artifact.update(
            {
                "consistency_status": "skipped",
                "observed_count": 0,
                "expected_count": _pytest_outcome_total(counts),
                "consistency_reason": "junit_xml artifact was not written",
            }
        )
        return artifact
    artifact.update(
        _count_consistency(
            expected_count=_pytest_outcome_total(counts),
            observed_count=_junit_testcase_count(path),
            subject="junit testcase",
        )
    )
    return artifact


def write_failed_nodeids_artifact(
    vault: Path,
    out_path: str | Path,
    *,
    failed_nodeids: list[str],
    expected_count: int | None = None,
) -> dict[str, Any]:
    path = Path(out_path)
    if not path.is_absolute():
        path = vault / path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(failed_nodeids)
    if payload:
        payload = f"{payload}\n"
    path.write_text(payload, encoding="utf-8")
    artifact = artifact_identity(vault, path, kind="failed_nodeids", source="pytest_failed_and_error_nodeids")
    if expected_count is not None:
        artifact.update(
            _count_consistency(
                expected_count=expected_count,
                observed_count=len(failed_nodeids),
                subject="failed/error nodeid artifact",
            )
        )
    return artifact


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
        for key in (
            "passed",
            "failed",
            "errors",
            "skipped",
            "xfailed",
            "xpassed",
            "subtests_passed",
        )
    )


def evidence_artifact_consistency(
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
