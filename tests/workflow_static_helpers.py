from __future__ import annotations

import re
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml

from ops.workflow_action_pin_catalog import (
    PINNED_ATTEST_BUILD_PROVENANCE_ACTION,
    PINNED_CHECKOUT_ACTION,
    PINNED_CI_CHECKOUT_ACTION,
    PINNED_CODEQL_ANALYZE_ACTION,
    PINNED_CODEQL_INIT_ACTION,
    PINNED_DEPENDENCY_REVIEW_ACTION,
    PINNED_DOWNLOAD_ARTIFACT_ACTION,
    PINNED_PYPI_PUBLISH_ACTION,
    PINNED_RELEASE_SECURITY_CHECKOUT_ACTION,
    PINNED_SETUP_PYTHON_ACTION,
    PINNED_SETUP_UV_ACTION,
    PINNED_UPLOAD_ARTIFACT_ACTION,
    WORKFLOW_ACTION_PIN_RULES,
)

PINNED_CODEQL_ACTION_PREFIX = "github/codeql-action/"
PINNED_ACTION_REF_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
__all__ = (
    "PINNED_ACTION_REF_RE",
    "PINNED_ATTEST_BUILD_PROVENANCE_ACTION",
    "PINNED_CHECKOUT_ACTION",
    "PINNED_CI_CHECKOUT_ACTION",
    "PINNED_CODEQL_ACTION_PREFIX",
    "PINNED_CODEQL_ANALYZE_ACTION",
    "PINNED_CODEQL_INIT_ACTION",
    "PINNED_DEPENDENCY_REVIEW_ACTION",
    "PINNED_DOWNLOAD_ARTIFACT_ACTION",
    "PINNED_PYPI_PUBLISH_ACTION",
    "PINNED_RELEASE_SECURITY_CHECKOUT_ACTION",
    "PINNED_SETUP_PYTHON_ACTION",
    "PINNED_SETUP_UV_ACTION",
    "PINNED_UPLOAD_ARTIFACT_ACTION",
    "WORKFLOW_ACTION_PIN_RULES",
)


def load_workflow(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"workflow must be a YAML mapping: {path}")
    return cast(dict[str, object], payload)


def workflow_mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(message)
    return cast(dict[str, object], value)


def workflow_on(workflow: dict[str, object]) -> dict[str, object]:
    # PyYAML's YAML 1.1 bool resolver loads the GitHub Actions `on` key as True.
    on_section = workflow.get("on")
    if on_section is None:
        on_section = cast(Mapping[object, object], workflow).get(True, {})
    return workflow_mapping(on_section, "workflow on section must be a mapping")


def workflow_jobs(workflow: dict[str, object]) -> dict[str, object]:
    return workflow_mapping(
        workflow.get("jobs", {}),
        "workflow jobs section must be a mapping",
    )


def workflow_job(workflow: dict[str, object], name: str) -> dict[str, object]:
    return workflow_mapping(
        workflow_jobs(workflow).get(name),
        f"missing workflow job: {name}",
    )


def workflow_matrix_values(job: dict[str, object], axis: str) -> tuple[str, ...]:
    matrix = workflow_matrix(job)
    values = matrix.get(axis, [])
    if not isinstance(values, list):
        raise AssertionError(f"workflow job matrix axis must be a list: {axis}")
    return tuple(str(value) for value in values)


def workflow_matrix(job: dict[str, object]) -> dict[str, object]:
    strategy = workflow_mapping(
        job.get("strategy", {}),
        "workflow job strategy must be a mapping",
    )
    return workflow_mapping(
        strategy.get("matrix", {}),
        "workflow job matrix must be a mapping",
    )


def workflow_matrix_include(job: dict[str, object]) -> tuple[dict[str, object], ...]:
    include = workflow_matrix(job).get("include", [])
    if not isinstance(include, list):
        raise AssertionError("workflow job matrix include must be a list")
    return tuple(
        workflow_mapping(item, "workflow job matrix include item must be a mapping")
        for item in include
    )


def workflow_steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        raise AssertionError("workflow job steps must be a list")
    return [cast(dict[str, object], step) for step in steps if isinstance(step, dict)]


def workflow_step(job: dict[str, object], name: str) -> dict[str, object]:
    for step in workflow_steps(job):
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing workflow step: {name}")


def workflow_run_text(step: dict[str, object]) -> str:
    run = step.get("run", "")
    if not isinstance(run, str):
        raise AssertionError("workflow step run must be a string")
    return run


def workflow_matrix_tier_run_text(job: dict[str, object], tier: str) -> str:
    expected_if = f"matrix.tier == '{tier}'"
    return "\n".join(
        workflow_run_text(step)
        for step in workflow_steps(job)
        if str(step.get("if", "")).strip() == expected_if and "run" in step
    )


def workflow_run_commands(job: dict[str, object]) -> str:
    return "\n".join(workflow_run_text(step) for step in workflow_steps(job) if "run" in step)


def workflow_path_entries(step: dict[str, object]) -> tuple[str, ...]:
    with_section = workflow_mapping(
        step.get("with", {}),
        "workflow step with section must be a mapping",
    )
    path = with_section.get("path", "")
    if not isinstance(path, str):
        raise AssertionError("workflow step path must be a string")
    return tuple(line.strip() for line in path.splitlines() if line.strip())


def assert_workflow_run_contains(
    case: unittest.TestCase, step: dict[str, object], tokens: tuple[str, ...]
) -> None:
    run = workflow_run_text(step)
    for token in tokens:
        case.assertIn(token, run)


def assert_locked_install_shape(
    case: unittest.TestCase, workflow: dict[str, object], expected_job_count: int
) -> None:
    jobs = workflow_jobs(workflow)
    case.assertEqual(len(jobs), expected_job_count)
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            raise AssertionError(f"workflow job must be a mapping: {job_name}")
        with case.subTest(job=job_name):
            setup = workflow_step(job, "Setup Python and uv")
            case.assertEqual(setup.get("uses"), "./.github/actions/setup-python-uv")
            install = next(
                (
                    step
                    for step in workflow_steps(job)
                    if str(step.get("name", "")).startswith("Install dependencies")
                ),
                None,
            )
            if install is not None:
                assert_workflow_run_contains(
                    case,
                    install,
                    (
                        "make uv-lock-check",
                        "uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt",
                        "python -m pip install -r tmp/locked-requirements.ci.txt",
                    ),
                )
                install_run = workflow_run_text(install)
                case.assertLess(
                    install_run.index("make uv-lock-check"),
                    install_run.index("uv export --frozen"),
                )


def assert_workflow_uses_are_sha_pinned(
    case: unittest.TestCase, workflow: dict[str, object]
) -> None:
    for job_name, job in workflow_jobs(workflow).items():
        if not isinstance(job, dict):
            raise AssertionError(f"workflow job must be a mapping: {job_name}")
        for step in workflow_steps(job):
            uses = step.get("uses")
            if not uses:
                continue
            with case.subTest(job=job_name, step=step.get("name", ""), uses=uses):
                case.assertIsInstance(uses, str)
                if str(uses).startswith("./"):
                    continue
                case.assertRegex(str(uses), PINNED_ACTION_REF_RE)
