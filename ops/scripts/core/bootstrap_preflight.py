from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
else:
    from .output_runtime import display_path, sanitize_report_text
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


ModuleAvailable = Callable[[str], bool]


def _default_module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _python_version_label(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def _isoformat_z(clock: Callable[[], Any] | None = None) -> str:
    current = clock() if clock else dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        "ops/scripts/bootstrap_preflight.py",
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
    status = "pass" if python_ok and not missing else "fail"
    return {
        "$schema": schema_path,
        "artifact_kind": ARTIFACT_KIND,
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": "unknown",
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
        },
        "dependencies": dependency_rows,
        "summary": {
            "dependency_count": len(dependency_rows),
            "missing_dependency_count": len(missing),
            "missing_packages": [str(row["package"]) for row in missing],
        },
        "guidance": (
            "Run make dev-install, then rerun make bootstrap-preflight."
            if include_dev
            else "Install requirements.txt, or run make dev-install for a complete local environment."
        ),
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
        f"python: {report['python']['version']} (minimum {report['python']['minimum']}) "
        f"[{report['python']['status']}]",
    ]
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
    parser.add_argument("--dev", action="store_true", help="Also check dev/test tools from requirements-dev.txt.")
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
