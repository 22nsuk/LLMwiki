from __future__ import annotations

import unittest
from pathlib import Path

import yaml


def load_workflow(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"workflow must be a YAML mapping: {path}")
    return payload


def workflow_on(workflow: dict[str, object]) -> dict[str, object]:
    # PyYAML's YAML 1.1 bool resolver loads the GitHub Actions `on` key as True.
    on_section = workflow.get("on", workflow.get(True, {}))
    if not isinstance(on_section, dict):
        raise AssertionError("workflow on section must be a mapping")
    return on_section


def workflow_jobs(workflow: dict[str, object]) -> dict[str, object]:
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict):
        raise AssertionError("workflow jobs section must be a mapping")
    return jobs


def workflow_job(workflow: dict[str, object], name: str) -> dict[str, object]:
    item = workflow_jobs(workflow).get(name)
    if not isinstance(item, dict):
        raise AssertionError(f"missing workflow job: {name}")
    return item


def workflow_steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        raise AssertionError("workflow job steps must be a list")
    return [step for step in steps if isinstance(step, dict)]


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
    with_section = step.get("with", {})
    if not isinstance(with_section, dict):
        raise AssertionError("workflow step with section must be a mapping")
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
    setup_uv_action = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
    jobs = workflow_jobs(workflow)
    case.assertEqual(len(jobs), expected_job_count)
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            raise AssertionError(f"workflow job must be a mapping: {job_name}")
        with case.subTest(job=job_name):
            setup_python = workflow_step(job, "Setup Python")
            setup_python_with = setup_python.get("with", {})
            case.assertIsInstance(setup_python_with, dict)
            cache_paths = str(setup_python_with.get("cache-dependency-path", ""))
            case.assertIn("uv.lock", cache_paths.split())
            setup_uv = workflow_step(job, "Setup uv")
            case.assertEqual(setup_uv.get("uses"), setup_uv_action)
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
