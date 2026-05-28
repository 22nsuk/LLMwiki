from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .output_runtime import display_path, resolve_repo_output_path, write_output_text

DEFAULT_OUT = "tmp/generated-artifact-retention-clean.json"

DELETE_CANDIDATE_PATHS = (
    "build/source-package-smoke",
    "build/review",
    "tmp/source-package-clean-extract",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "llm_wiki_vnext.egg-info",
)
DISPOSABLE_DIAGNOSTIC_PATHS = (
    "build/release/release-closeout-sealed-dry-run",
)
PROTECTED_PATHS = (
    "build/release",
    "ops/reports",
    "ops/operator",
    "runs",
    "raw",
    "wiki",
    "system",
    "external-reports",
    "AGENTS.local.md",
    "ops/manifest.json",
    "ops/raw-registry.json",
    "ops/script-output-surfaces.json",
)


def _git_ignored(vault: Path, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel_path],
        cwd=vault,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _path_record(vault: Path, rel_path: str, *, category: str) -> dict[str, Any]:
    path = vault / rel_path
    exists = path.exists()
    return {
        "path": rel_path,
        "category": category,
        "exists": exists,
        "ignored": _git_ignored(vault, rel_path) if exists else False,
        "kind": "directory" if path.is_dir() else "file" if path.is_file() else "missing",
    }


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _orphan_goal_state_records(vault: Path) -> list[dict[str, Any]]:
    runs_root = vault / "runs"
    if not runs_root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    global_status = vault / "ops/reports/goal-run-status.json"
    global_certificate = vault / "ops/reports/goal-runtime-certificate.json"
    global_lock = vault / "build/goal-runs/goal-runtime.lock.json"
    for state_dir in sorted(runs_root.glob("goal-*/state")):
        if not state_dir.is_dir():
            continue
        rel_path = state_dir.relative_to(vault).as_posix()
        records.append(
            {
                "path": rel_path,
                "category": "run_state_candidate",
                "exists": True,
                "ignored": _git_ignored(vault, rel_path),
                "delete_allowed": False,
                "reason": (
                    "run state is provenance evidence; classify/quarantine before deletion"
                    if global_status.exists() or global_certificate.exists() or global_lock.exists()
                    else "orphan-looking run state without global goal status, certificate, or lock"
                ),
            }
        )
    return records


def build_report(vault: Path, *, apply: bool = False) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    delete_candidates = [
        _path_record(resolved_vault, rel_path, category="regenerated_residue")
        for rel_path in DELETE_CANDIDATE_PATHS
    ]
    delete_candidates.extend(
        _path_record(resolved_vault, rel_path, category="disposable_diagnostic")
        for rel_path in DISPOSABLE_DIAGNOSTIC_PATHS
    )
    retained = [
        {
            **_path_record(resolved_vault, rel_path, category="protected_surface"),
            "delete_allowed": False,
        }
        for rel_path in PROTECTED_PATHS
    ]
    retained.extend(_orphan_goal_state_records(resolved_vault))
    blockers = [
        {
            "path": item["path"],
            "reason": "delete candidate exists but is not ignored by git",
        }
        for item in delete_candidates
        if item["exists"] and not item["ignored"]
    ]
    deleted_paths: list[str] = []
    if apply and not blockers:
        for item in delete_candidates:
            if not item["exists"]:
                continue
            _delete_path(resolved_vault / item["path"])
            deleted_paths.append(item["path"])
    status = "pass" if not blockers else "fail"
    return {
        "artifact_kind": "generated_artifact_retention_clean",
        "status": status,
        "apply": apply,
        "delete_candidates": delete_candidates,
        "retained": retained,
        "deleted_paths": deleted_paths,
        "blockers": blockers,
        "summary": {
            "delete_candidate_count": sum(1 for item in delete_candidates if item["exists"]),
            "deleted_count": len(deleted_paths),
            "retained_existing_count": sum(1 for item in retained if item["exists"]),
            "blocker_count": len(blockers),
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = resolve_repo_output_path(vault, out_path, default_relative_path=DEFAULT_OUT)
    write_output_text(destination, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean safe generated residue with retention guards.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, apply=args.apply)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
