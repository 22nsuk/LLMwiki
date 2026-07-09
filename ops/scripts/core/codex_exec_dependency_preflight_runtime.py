from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol, cast

from ops.scripts.core.codex_exec_execution_types_runtime import (
    ExecutionSummary,
    ExecutorDependencyCommandPayload,
    ExecutorDependencyModulePayload,
    ExecutorDependencyPreflightPayload,
)
from ops.scripts.core.codex_exec_sanitize_runtime import _sanitize_path_text
from ops.scripts.core.codex_exec_workspace_runtime import path_is_inside_workspace

NON_WORKER_PROJECT_CHECK_MODULES: tuple[tuple[str, str], ...] = (
    ("pytest", "pytest"),
    ("jsonschema", "jsonschema"),
    ("yaml", "PyYAML"),
)
DEPENDENCY_PREFLIGHT_PYTHON_FLAGS = ("-I", "-B")
PROJECT_CHECK_LANE = "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider <focused-selector>"


class DependencyPreflightTrustError(ValueError):
    """Raised when a dependency preflight interpreter cannot be trusted."""


class _DependencyPreflightRequest(Protocol):
    @property
    def artifact_root(self) -> Path: ...

    @property
    def workspace_root(self) -> Path: ...

    @property
    def role(self) -> str: ...

    @property
    def timeout_seconds(self) -> int: ...


def project_dependency_check_script(
    module_pairs: tuple[tuple[str, str], ...] = NON_WORKER_PROJECT_CHECK_MODULES,
) -> str:
    module_pairs_repr = repr(list(module_pairs))
    return (
        "import importlib, importlib.metadata, json, sys\n"
        f"module_pairs = {module_pairs_repr}\n"
        "payload = {\n"
        "    'python': {'executable': sys.executable, 'version': sys.version.split()[0]},\n"
        "    'modules': [],\n"
        "}\n"
        "failed = False\n"
        "for module, package in module_pairs:\n"
        "    item = {'import_name': module, 'package': package, 'status': 'available', 'version': '', 'detail': ''}\n"
        "    try:\n"
        "        importlib.import_module(module)\n"
        "    except Exception as exc:\n"
        "        failed = True\n"
        "        item['status'] = 'missing'\n"
        "        item['detail'] = f'{type(exc).__name__}: {exc}'\n"
        "    else:\n"
        "        try:\n"
        "            item['version'] = importlib.metadata.version(package)\n"
        "        except importlib.metadata.PackageNotFoundError:\n"
        "            item['version'] = 'unknown'\n"
        "    payload['modules'].append(item)\n"
        "print(json.dumps(payload, sort_keys=True))\n"
        "sys.exit(1 if failed else 0)\n"
    )


def dependency_preflight_module_payloads(
    *,
    probe: dict[str, Any],
    completed_returncode: int,
    stdout: str,
    stderr: str,
    roots: list[Path],
    module_pairs: tuple[tuple[str, str], ...] = NON_WORKER_PROJECT_CHECK_MODULES,
) -> list[dict[str, str]]:
    modules_by_name = (
        {
            str(item.get("import_name", "")).strip(): item
            for item in probe.get("modules", [])
            if isinstance(item, dict)
        }
        if isinstance(probe.get("modules"), list)
        else {}
    )
    unstructured_detail = ""
    if not probe and (stdout or stderr):
        unstructured_detail = _sanitize_path_text(
            "\n".join(item for item in (stdout, stderr) if item),
            roots=roots,
        )
    required_modules: list[dict[str, str]] = []
    for module, package in module_pairs:
        item = modules_by_name.get(module)
        if item is None:
            required_modules.append(
                {
                    "import_name": module,
                    "package": package,
                    "status": "unknown" if completed_returncode == 0 else "missing",
                    "version": "",
                    "detail": unstructured_detail,
                }
            )
            continue
        required_modules.append(
            {
                "import_name": module,
                "package": package,
                "status": str(item.get("status", "unknown")).strip() or "unknown",
                "version": str(item.get("version", "")).strip(),
                "detail": _sanitize_path_text(
                    str(item.get("detail", "")).strip(),
                    roots=roots,
                ),
            }
        )
    return required_modules


def parse_dependency_preflight_probe(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def dependency_module_payloads(
    status: str,
    *,
    detail: str = "",
) -> list[ExecutorDependencyModulePayload]:
    return [
        {
            "import_name": module,
            "package": package,
            "status": status,
            "version": "",
            "detail": detail,
        }
        for module, package in NON_WORKER_PROJECT_CHECK_MODULES
    ]


def dependency_preflight_command_payload(
    python_display: str,
) -> ExecutorDependencyCommandPayload:
    argv = (
        [
            python_display,
            *DEPENDENCY_PREFLIGHT_PYTHON_FLAGS,
            "-c",
            "<project-dependency-preflight>",
        ]
        if python_display
        else []
    )
    return {
        "argv": argv,
        "project_check_lane": PROJECT_CHECK_LANE,
    }


def dependency_preflight_payload(
    *,
    role_requires_project_check: bool,
    status: str,
    python_path: str,
    python_executable: str,
    python_version: str,
    python_exists: bool,
    required_modules: list[ExecutorDependencyModulePayload],
    returncode: int,
) -> ExecutorDependencyPreflightPayload:
    return {
        "role_requires_project_check": role_requires_project_check,
        "status": status,
        "command": dependency_preflight_command_payload(python_path),
        "python": {
            "path": python_path,
            "executable": python_executable,
            "version": python_version,
            "exists": python_exists,
        },
        "required_modules": required_modules,
        "returncode": returncode,
    }


def dependency_preflight_template(
    role: str,
    workspace_root: Path,
    roots: list[Path],
) -> ExecutorDependencyPreflightPayload:
    if role == "worker":
        return dependency_preflight_payload(
            role_requires_project_check=False,
            status="not_required",
            python_path="",
            python_executable="",
            python_version="",
            python_exists=False,
            required_modules=dependency_module_payloads("not_checked"),
            returncode=0,
        )
    python_path = workspace_root / ".venv" / "bin" / "python"
    python_display = _sanitize_path_text(str(python_path), roots=roots)
    return dependency_preflight_payload(
        role_requires_project_check=True,
        status="not_checked",
        python_path=python_display,
        python_executable="",
        python_version="",
        python_exists=python_path.exists(),
        required_modules=dependency_module_payloads("not_checked"),
        returncode=0,
    )


def trusted_dependency_preflight_python(
    artifact_root: Path,
    *,
    workspace_root: Path | None = None,
) -> Path:
    current_python = Path(sys.executable).absolute()
    current_resolved_python = current_python.resolve(strict=True)
    if workspace_root is not None and artifact_root.resolve() == workspace_root.resolve():
        workspace_python = (workspace_root / ".venv" / "bin" / "python").absolute()
        if not path_is_inside_workspace(current_python, workspace_root):
            return current_python
        if not path_is_inside_workspace(current_resolved_python, workspace_root):
            if current_python == workspace_python:
                return current_python
            return current_resolved_python
        raise DependencyPreflightTrustError(
            "same-root dependency preflight interpreter resolves inside the workspace"
        )
    repo_python = artifact_root / ".venv" / "bin" / "python"
    if repo_python.is_file():
        trusted_python = repo_python.resolve(strict=True)
        if workspace_root is not None and path_is_inside_workspace(trusted_python, workspace_root):
            raise DependencyPreflightTrustError(
                "artifact dependency preflight interpreter resolves inside the workspace"
            )
        return trusted_python
    if workspace_root is not None and path_is_inside_workspace(current_python, workspace_root):
        if not path_is_inside_workspace(current_resolved_python, workspace_root):
            return current_resolved_python
        raise DependencyPreflightTrustError(
            "dependency preflight interpreter resolves inside the workspace"
        )
    return current_python


def dependency_preflight_from_probe(
    request: _DependencyPreflightRequest,
    *,
    python_path: Path,
    completed: subprocess.CompletedProcess[str],
) -> ExecutorDependencyPreflightPayload:
    roots = [request.artifact_root, request.workspace_root]
    python_display = _sanitize_path_text(str(python_path), roots=roots)
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    probe = parse_dependency_preflight_probe(stdout)
    python_info = (
        probe.get("python", {}) if isinstance(probe.get("python"), dict) else {}
    )
    required_modules = cast(
        list[ExecutorDependencyModulePayload],
        dependency_preflight_module_payloads(
            probe=probe,
            completed_returncode=int(completed.returncode),
            stdout=stdout,
            stderr=stderr,
            roots=roots,
        ),
    )
    return dependency_preflight_payload(
        role_requires_project_check=True,
        status="pass" if completed.returncode == 0 else "fail",
        python_path=python_display,
        python_executable=_sanitize_path_text(
            str(python_info.get("executable", "")).strip(),
            roots=roots,
        ),
        python_version=str(python_info.get("version", "")).strip(),
        python_exists=True,
        required_modules=required_modules,
        returncode=int(completed.returncode),
    )


def dependency_preflight_failure_summary(
    request: _DependencyPreflightRequest,
    preflight: ExecutorDependencyPreflightPayload,
) -> ExecutionSummary | None:
    if preflight.get("status") != "fail":
        return None
    python_display = str(preflight.get("python", {}).get("path", "")).strip()
    required = ", ".join(
        package for _module, package in NON_WORKER_PROJECT_CHECK_MODULES
    )
    module_details = []
    for item in preflight.get("required_modules", []):
        if (
            not isinstance(item, dict)
            or str(item.get("status", "")).strip() == "available"
        ):
            continue
        package = str(item.get("package", "")).strip()
        module = str(item.get("import_name", "")).strip()
        detail = str(item.get("detail", "")).strip()
        if detail:
            module_details.append(f"{package} ({module}): {detail}")
    note = (
        f"executor dependency preflight blocked {request.role}: "
        f"{python_display} could not import required project check modules ({required})"
    )
    if module_details:
        note = f"{note}; {'; '.join(module_details)}"
    return ExecutionSummary(
        status="fail",
        decision="blocked",
        notes=[note],
        timed_out=False,
        timeout_seconds=request.timeout_seconds,
        termination_reason="completed",
    )


def workspace_python_failure(
    *,
    request: _DependencyPreflightRequest,
    workspace_python: Path,
    detail: str,
) -> tuple[ExecutorDependencyPreflightPayload, ExecutionSummary]:
    roots = [request.artifact_root, request.workspace_root]
    python_display = _sanitize_path_text(str(workspace_python), roots=roots)
    preflight = dependency_preflight_payload(
        role_requires_project_check=True,
        status="fail",
        python_path=python_display,
        python_executable="",
        python_version="",
        python_exists=True,
        required_modules=dependency_module_payloads("not_checked", detail=detail),
        returncode=126,
    )
    return (
        preflight,
        ExecutionSummary(
            status="fail",
            decision="blocked",
            notes=[
                (
                    f"executor dependency preflight blocked {request.role}: "
                    f"{python_display} failed workspace Python trust check; {detail}"
                )
            ],
            timed_out=False,
            timeout_seconds=request.timeout_seconds,
            termination_reason="completed",
        ),
    )
