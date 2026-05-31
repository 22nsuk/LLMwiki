from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.source_revision_runtime import resolve_source_revision
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from .output_runtime import display_path, sanitize_report_text
    from .source_revision_runtime import resolve_source_revision
    from .source_tree_fingerprint_runtime import release_source_tree_fingerprint


MIN_PYTHON = (3, 12)
DEFAULT_OUT = "ops/reports/bootstrap-preflight-report.json"
ARTIFACT_KIND = "bootstrap_preflight_report"
PRODUCER = "ops.scripts.bootstrap_preflight"
SOURCE_COMMAND = "python -m ops.scripts.bootstrap_preflight --dev --out ops/reports/bootstrap-preflight-report.json"
RUNTIME_DEPENDENCIES = {
    "yaml": "PyYAML",
    "jsonschema": "jsonschema",
}
DEV_DEPENDENCIES = {
    "pytest": "pytest",
    "ruff": "ruff",
    "mypy": "mypy",
}
CODEX_EXECUTABLE_NAMES = ("codex", "codex.exe", "codex.cmd", "codex.ps1", "codex.js")


ModuleAvailable = Callable[[str], bool]


def _default_module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _python_version_label(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def _isoformat_z(clock: Callable[[], Any] | None = None) -> str:
    current = clock() if clock else dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.UTC)
    return current.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_rel_path(vault: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(vault.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_fingerprints(vault: Path, paths: list[str]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for rel_path in paths:
        path = vault / rel_path
        if path.is_file():
            fingerprints[rel_path] = _sha256_file(path)
    return fingerprints


def _policy_version(vault: Path, policy_path: str) -> int | str:
    path = vault / policy_path
    if not path.is_file():
        return "unknown"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("version:"):
            continue
        raw_value = line.split(":", 1)[1].strip().strip('"')
        try:
            return int(raw_value)
        except ValueError:
            return raw_value or "unknown"
    return "unknown"


def _resolve_repo_output_path(vault: Path, out_path: str) -> Path:
    vault_root = vault.resolve()
    path = Path(out_path)
    resolved = path.resolve() if path.is_absolute() else (vault_root / path).resolve()
    if not resolved.is_relative_to(vault_root):
        raise ValueError(f"repo output path must stay under vault: {resolved.as_posix()}")
    return resolved


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def _workspace_virtualenv_bin(vault: Path) -> Path | None:
    venv_root = vault / ".venv"
    for rel_path in ("bin/python", "Scripts/python.exe", "Scripts/python"):
        python_path = venv_root / rel_path
        if python_path.exists():
            return python_path.parent
    return None


def _path_without_workspace_virtualenv(vault: Path) -> str:
    path_text = os.environ.get("PATH", "")
    venv_bin = _workspace_virtualenv_bin(vault)
    if venv_bin is None or not path_text:
        return path_text
    entries: list[str] = []
    for entry in path_text.split(os.pathsep):
        if entry and _same_path(Path(entry), venv_bin):
            continue
        entries.append(entry)
    return os.pathsep.join(entries)


def _safe_tool_path(vault: Path, path_text: str | None) -> str:
    if not path_text:
        return ""
    return sanitize_report_text(vault, display_path(vault, Path(path_text)))


def _workspace_codex_paths(venv_bin: Path | None) -> list[Path]:
    if venv_bin is None:
        return []
    return [venv_bin / name for name in CODEX_EXECUTABLE_NAMES if (venv_bin / name).exists()]


def _path_matches_any(path_text: str | None, candidates: list[Path]) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    return any(_same_path(path, candidate) for candidate in candidates)


def _executor_tooling(vault: Path, *, environment_class: str) -> dict[str, Any]:
    venv_bin = _workspace_virtualenv_bin(vault)
    workspace_codex_paths = _workspace_codex_paths(venv_bin)
    codex_on_path = shutil.which("codex")
    codex_outside_workspace_virtualenv = shutil.which(
        "codex",
        path=_path_without_workspace_virtualenv(vault),
    )
    workspace_shadowing = _path_matches_any(codex_on_path, workspace_codex_paths)
    failures: list[str] = []
    if environment_class == "goal-runtime":
        if venv_bin is None:
            failures.append("workspace_virtualenv_python_missing")
        if not codex_outside_workspace_virtualenv and workspace_codex_paths:
            failures.append("workspace_virtualenv_codex_shadow")
        elif not codex_outside_workspace_virtualenv:
            failures.append("codex_not_resolved_outside_workspace_virtualenv")
    return {
        "status": "fail" if failures else "pass",
        "environment_class": environment_class,
        "workspace_virtualenv_bin": _safe_tool_path(vault, str(venv_bin)) if venv_bin else "",
        "workspace_virtualenv_present": venv_bin is not None,
        "workspace_virtualenv_codex_present": bool(workspace_codex_paths),
        "codex_on_path": _safe_tool_path(vault, codex_on_path),
        "codex_outside_workspace_virtualenv": _safe_tool_path(
            vault,
            codex_outside_workspace_virtualenv,
        ),
        "workspace_virtualenv_codex_shadowing_path": workspace_shadowing,
        "failures": failures,
    }


def _dependency_rows(
    dependencies: dict[str, str],
    *,
    module_available: ModuleAvailable,
    category: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module, package in sorted(dependencies.items()):
        installed = module_available(module)
        rows.append(
            {
                "category": category,
                "module": module,
                "package": package,
                "installed": installed,
                "status": "pass" if installed else "fail",
            }
        )
    return rows


def build_report(
    *,
    vault: Path | None = None,
    include_dev: bool = False,
    python_version: tuple[int, int, int] | None = None,
    module_available: ModuleAvailable = _default_module_available,
    clock: Callable[[], Any] | None = None,
    policy_path: str | None = None,
    environment_class: str = "developer",
) -> dict[str, Any]:
    resolved_vault = (vault or Path(".")).resolve()
    resolved_policy_path = policy_path or "ops/policies/wiki-maintainer-policy.yaml"
    generated_at = _isoformat_z(clock)
    schema_path = "ops/schemas/bootstrap-preflight-report.schema.json"
    source_paths = [
        "ops/scripts/core/bootstrap_preflight.py",
        schema_path,
        resolved_policy_path,
    ]
    input_fingerprints = _input_fingerprints(resolved_vault, source_paths)
    version = python_version or sys.version_info[:3]
    python_ok = version >= MIN_PYTHON
    dependency_rows = _dependency_rows(
        RUNTIME_DEPENDENCIES,
        module_available=module_available,
        category="runtime",
    )
    if include_dev:
        dependency_rows.extend(
            _dependency_rows(DEV_DEPENDENCIES, module_available=module_available, category="dev")
        )
    missing = [row for row in dependency_rows if not bool(row["installed"])]
    executor_tooling = _executor_tooling(resolved_vault, environment_class=environment_class)
    executor_tooling_failures = [
        str(item) for item in executor_tooling.get("failures", []) if str(item).strip()
    ]
    status = "pass" if python_ok and not missing and not executor_tooling_failures else "fail"
    if "workspace_virtualenv_python_missing" in executor_tooling_failures:
        guidance = (
            "Run make dev-install, then rerun make goal-runtime-python-preflight "
            "before goal-runtime execution."
        )
    elif executor_tooling_failures:
        guidance = (
            "Expose the operator Codex CLI outside the repository virtualenv and remove "
            "repo-local .venv/bin/codex shims before running goal-runtime execution."
        )
    elif include_dev:
        guidance = "Run make dev-install, then rerun make bootstrap-preflight."
    else:
        guidance = "Install the project from pyproject.toml, or run make dev-install for a complete local environment."
    source_revision = resolve_source_revision(resolved_vault)
    return {
        "$schema": schema_path,
        "artifact_kind": ARTIFACT_KIND,
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": source_revision.revision,
        "source_tree_fingerprint": release_source_tree_fingerprint(resolved_vault),
        "input_fingerprints": input_fingerprints,
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": generated_at,
        },
        "vault": _safe_rel_path(resolved_vault, resolved_vault),
        "policy": {
            "path": resolved_policy_path,
            "version": _policy_version(resolved_vault, resolved_policy_path),
        },
        "status": status,
        "python": {
            "version": _python_version_label(version),
            "minimum": _python_version_label((*MIN_PYTHON, 0)),
            "status": "pass" if python_ok else "fail",
        },
        "include_dev": include_dev,
        "environment": {
            "environment_class": environment_class,
            "dependency_source": "current_python_environment",
            "install_attempted": False,
            "interpreter": sanitize_report_text(
                resolved_vault,
                display_path(resolved_vault, Path(sys.executable)),
            ),
            "interpreter_selection": "active interpreter",
            "include_dev": include_dev,
            "executor_tooling": executor_tooling,
        },
        "dependencies": dependency_rows,
        "summary": {
            "dependency_count": len(dependency_rows),
            "missing_dependency_count": len(missing),
            "missing_packages": [str(row["package"]) for row in missing],
            "executor_tooling_failure_count": len(executor_tooling_failures),
            "executor_tooling_failures": executor_tooling_failures,
        },
        "guidance": guidance,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    destination = _resolve_repo_output_path(vault, out_path or DEFAULT_OUT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generated_at = str(report.get("generated_at", "")).strip()
    try:
        generated_dt = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        generated_dt = None
    if generated_dt is not None:
        os.utime(destination, (generated_dt.timestamp(), generated_dt.timestamp()))
    return destination


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"bootstrap preflight: {report['status']}",
        f"interpreter: {report['environment']['interpreter']}",
        f"python: {report['python']['version']} (minimum {report['python']['minimum']}) "
        f"[{report['python']['status']}]",
    ]
    executor_tooling = report["environment"].get("executor_tooling", {})
    if isinstance(executor_tooling, dict):
        resolved_codex = executor_tooling.get("codex_outside_workspace_virtualenv") or "unresolved"
        lines.append(f"codex executor: {resolved_codex} [{executor_tooling.get('status', 'unknown')}]")
    for row in report["dependencies"]:
        marker = "ok" if row["installed"] else "missing"
        lines.append(f"{row['category']}: {row['package']} ({row['module']}) [{marker}]")
    if report["status"] != "pass":
        lines.append(str(report["guidance"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local bootstrap dependencies before running repo gates.")
    parser.add_argument("--vault", default=".", help="Vault/repo root")
    parser.add_argument("--policy-path")
    parser.add_argument("--environment-class", default="developer")
    parser.add_argument("--out", help="Write a schema-backed report to this path under the vault.")
    parser.add_argument("--dev", action="store_true", help="Also check dev/test tools from pyproject.toml [project.optional-dependencies].dev.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    report = build_report(
        vault=vault,
        include_dev=args.dev,
        policy_path=args.policy_path,
        environment_class=args.environment_class,
    )
    if args.out:
        destination = write_report(vault, report, args.out)
        if not args.json:
            print(_safe_rel_path(vault, destination))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text(report))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
