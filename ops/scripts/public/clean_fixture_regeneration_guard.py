from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/clean-fixture-regeneration-guard.json"
PRODUCER = "ops.scripts.clean_fixture_regeneration_guard"
SCHEMA_PATH = "ops/schemas/clean-fixture-regeneration-guard.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.clean_fixture_regeneration_guard --vault ."
DIRTY_REPORT_PREFIX = "ops/reports/"
PUBLIC_GENERATED_SURFACES = (
    "tests/fixtures/report_schema_samples.json",
    "ops/script-output-surfaces.json",
)


@dataclass(frozen=True)
class CleanFixtureRegenerationGuardRequest:
    vault: Path
    out_path: str | None = None
    policy_path: str | None = None
    allow_dirty_ops_reports: bool = False
    context: RuntimeContext | None = None
    git_status_lines: tuple[str, ...] | None = None
    git_status_error: str = ""


def _run_git_status(vault: Path) -> tuple[tuple[str, ...], str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(vault),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            DIRTY_REPORT_PREFIX.rstrip("/"),
            *PUBLIC_GENERATED_SURFACES,
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
    if completed.returncode != 0:
        return lines, completed.stderr.strip() or f"git status exited with {completed.returncode}"
    return lines, ""


def _porcelain_paths(line: str) -> list[str]:
    text = line[3:].strip() if len(line) > 3 else ""
    if " -> " in text:
        return [part.strip().strip('"') for part in text.split(" -> ", maxsplit=1) if part.strip()]
    return [text.strip('"')] if text else []


def _dirty_entries(lines: tuple[str, ...]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in lines:
        status = line[:2].strip() or "?"
        for path in _porcelain_paths(line):
            entries.append({"status": status, "path": path})
    return entries


def _path_set(entries: list[dict[str, str]], predicate: Callable[[str], bool]) -> list[str]:
    return sorted({entry["path"] for entry in entries if predicate(entry["path"])})


def _status(*, git_status_error: str, dirty_ops_reports: list[str], allow_dirty: bool) -> str:
    if git_status_error:
        return "fail"
    if dirty_ops_reports and not allow_dirty:
        return "fail"
    return "pass"


def _summary(
    *,
    dirty_ops_reports: list[str],
    dirty_public_surfaces: list[str],
    allow_dirty: bool,
) -> dict[str, Any]:
    return {
        "dirty_ops_report_count": len(dirty_ops_reports),
        "dirty_public_surface_count": len(dirty_public_surfaces),
        "allow_dirty_ops_reports": allow_dirty,
        "next_action": (
            "Use a clean checkout/worktree before regenerating public fixtures."
            if dirty_ops_reports and not allow_dirty
            else "Public fixture regeneration guard is clear."
        ),
    }


def build_report(request: CleanFixtureRegenerationGuardRequest) -> dict[str, Any]:
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    context = request.context or RuntimeContext.from_policy(policy)
    if request.git_status_lines is None:
        status_lines, git_status_error = _run_git_status(vault)
    else:
        status_lines = request.git_status_lines
        git_status_error = request.git_status_error
    dirty_entries = _dirty_entries(status_lines)
    dirty_ops_reports = _path_set(
        dirty_entries,
        lambda path: path == DIRTY_REPORT_PREFIX.rstrip("/") or path.startswith(DIRTY_REPORT_PREFIX),
    )
    dirty_public_surfaces = _path_set(
        dirty_entries,
        lambda path: path in set(PUBLIC_GENERATED_SURFACES),
    )
    status = _status(
        git_status_error=git_status_error,
        dirty_ops_reports=dirty_ops_reports,
        allow_dirty=request.allow_dirty_ops_reports,
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="clean_fixture_regeneration_guard",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/public/clean_fixture_regeneration_guard.py",
                "ops/schemas/clean-fixture-regeneration-guard.schema.json",
                "mk/artifact.mk",
                "mk/test.mk",
            ],
            text_inputs={
                "dirty_report_prefix": DIRTY_REPORT_PREFIX,
                "public_generated_surfaces": json.dumps(PUBLIC_GENERATED_SURFACES),
            },
            source_tree_excluded_files=(request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": status,
        "allow_dirty_ops_reports": request.allow_dirty_ops_reports,
        "git_status_error": git_status_error,
        "dirty_entries": dirty_entries,
        "dirty_ops_report_paths": dirty_ops_reports,
        "dirty_public_surface_paths": dirty_public_surfaces,
        "summary": _summary(
            dirty_ops_reports=dirty_ops_reports,
            dirty_public_surfaces=dirty_public_surfaces,
            allow_dirty=request.allow_dirty_ops_reports,
        ),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="clean fixture regeneration guard schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output report path.")
    parser.add_argument("--policy-path", default=None, help="Policy path relative to the vault.")
    parser.add_argument(
        "--allow-dirty-ops-reports",
        action="store_true",
        help="Record but do not fail when ops/reports is dirty.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        CleanFixtureRegenerationGuardRequest(
            vault=vault,
            out_path=args.out,
            policy_path=args.policy_path,
            allow_dirty_ops_reports=args.allow_dirty_ops_reports,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
