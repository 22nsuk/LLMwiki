from __future__ import annotations

import re
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml

PINNED_CHECKOUT_ACTION = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
PINNED_SETUP_PYTHON_ACTION = "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405"
PINNED_SETUP_UV_ACTION = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
PINNED_UPLOAD_ARTIFACT_ACTION = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
PINNED_DOWNLOAD_ARTIFACT_ACTION = "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
PINNED_ATTEST_BUILD_PROVENANCE_ACTION = (
    "actions/attest-build-provenance@a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32"
)
PINNED_PYPI_PUBLISH_ACTION = (
    "pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b"
)
PINNED_CODEQL_ACTION_PREFIX = "github/codeql-action/"
PINNED_DEPENDENCY_REVIEW_ACTION = (
    "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294"
)
PINNED_ACTION_REF_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


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
            setup_python = workflow_step(job, "Setup Python")
            case.assertEqual(setup_python.get("uses"), PINNED_SETUP_PYTHON_ACTION)
            setup_python_with = workflow_mapping(
                setup_python.get("with", {}),
                "workflow setup-python with section must be a mapping",
            )
            cache_paths = str(setup_python_with.get("cache-dependency-path", ""))
            case.assertIn("uv.lock", cache_paths.split())
            setup_uv = workflow_step(job, "Setup uv")
            case.assertEqual(setup_uv.get("uses"), PINNED_SETUP_UV_ACTION)
            install = next(
                step
                for step in workflow_steps(job)
                if str(step.get("name", "")).startswith("Install dependencies")
            )
            assert_workflow_run_contains(
                case,
                install,
                (
                    "uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt",
                    "python -m pip install -r tmp/locked-requirements.ci.txt",
                ),
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
