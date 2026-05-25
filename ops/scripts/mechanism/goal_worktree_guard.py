from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext

DEFAULT_OUT = "ops/reports/goal-worktree-guard.json"
PRODUCER = "ops.scripts.goal_worktree_guard"
SCHEMA_PATH = "ops/schemas/goal-worktree-guard.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_worktree_guard --vault ."
PUBLIC_SOURCE_LAYOUT_PATHS = ("ops", "tests", "mk", "docs", "README.md", "Makefile")
REQUESTED_MODES = ("auto", "git", "zip")
DURABLE_PRIVATE_IGNORED_PREFIXES = (
    "AGENTS.local.md",
    "external-reports/",
    "ops/manifest.json",
    "ops/operator/",
    "ops/raw-registry.json",
    "ops/reports/",
    "raw/",
    "runs/",
    "system/",
    "wiki/",
)
LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_PATHS = (
    "AGENTS.local.md",
    "external-reports/report-reference-manifest.json",
    "ops/manifest.json",
    "ops/raw-registry.json",
)
LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_PREFIXES = (
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "raw/",
    "runs/",
    "system/",
    "wiki/",
)


@dataclass(frozen=True)
class GitCommandResult:
    returncode: int
    stdout: str
    stderr: str


GitRunner = Callable[[Sequence[str]], GitCommandResult]


@dataclass(frozen=True)
class GoalWorktreeGuardRequest:
    vault: Path
    requested_mode: str = "git"
    out_path: str | None = None
    policy_path: str | None = None
    context: RuntimeContext | None = None
    git_runner: GitRunner | None = None


@dataclass(frozen=True)
class GitInspection:
    available: bool
    inside_worktree: bool
    worktree_root: str
    head_sha: str
    branch: str
    dirty_entry_count: int
    status_porcelain_sha256: str
    status_codes: dict[str, int]
    self_output_dirty_entry_count: int
    self_output_dirty_status_porcelain_sha256: str
    self_output_dirty_status_codes: dict[str, int]
    durable_private_ignored_entry_count: int
    durable_private_ignored_status_porcelain_sha256: str
    durable_private_ignored_status_codes: dict[str, int]
    durable_private_ignored_error: str
    error: str


@dataclass(frozen=True)
class WorktreeBlocker:
    blocker_id: str
    severity: str
    summary: str
    next_action: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _subprocess_git_runner(cwd: Path) -> GitRunner:
    def run(args: Sequence[str]) -> GitCommandResult:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=False,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError:
            return GitCommandResult(returncode=127, stdout="", stderr="git executable not found")
        return GitCommandResult(
            returncode=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )

    return run


def _relative_or_marker(vault: Path, raw_path: str) -> str:
    if not raw_path.strip():
        return ""
    path = Path(raw_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        rendered = report_path(vault, path)
    except OSError:
        return "<outside-vault>"
    if rendered.startswith("/") or rendered == ".." or rendered.startswith("../"):
        return "<outside-vault>"
    return rendered


def _porcelain_status_codes(porcelain: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in porcelain.splitlines():
        code = line[:2].strip() or "??"
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _normalize_repo_path(value: str) -> str:
    normalized = Path(value).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in ("", ".") or normalized.startswith("/") or ".." in normalized.split("/"):
        return ""
    return normalized


def _porcelain_line_path(line: str) -> str:
    if len(line) < 3:
        return ""
    # _subprocess_git_runner strips stdout, so an unstaged-only porcelain
    # line like " M path" can arrive as "M path".
    path = line[2:] if line[1:2] == " " and line[2:3] != " " else line[3:]
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[1]
    return _normalize_repo_path(path)


def _split_self_output_status(
    porcelain: str,
    *,
    self_output_path: str,
) -> tuple[str, str]:
    normalized_self_output_path = _normalize_repo_path(self_output_path)
    if not normalized_self_output_path:
        return porcelain, ""
    kept: list[str] = []
    self_output: list[str] = []
    for line in porcelain.splitlines():
        if _porcelain_line_path(line) == normalized_self_output_path:
            self_output.append(line)
        else:
            kept.append(line)
    return "\n".join(kept), "\n".join(self_output)


def _is_local_only_retained_private_ignored_path(rel_path: str) -> bool:
    if rel_path in LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_PATHS:
        return True
    return any(
        rel_path == prefix.rstrip("/") or rel_path.startswith(prefix)
        for prefix in LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_PREFIXES
    )


def _ignored_directory_contains_only_local_retained_files(vault: Path, rel_path: str) -> bool:
    path = vault / rel_path
    if not path.is_dir():
        return False
    files = [item for item in path.rglob("*") if item.is_file()]
    return bool(files) and all(
        _is_local_only_retained_private_ignored_path(_normalize_repo_path(report_path(vault, item)))
        for item in files
    )


def _is_local_only_retained_private_ignored_entry(vault: Path, rel_path: str) -> bool:
    if _is_local_only_retained_private_ignored_path(rel_path):
        return True
    return _ignored_directory_contains_only_local_retained_files(vault, rel_path)


def _durable_private_ignored_porcelain_lines(vault: Path, porcelain: str) -> str:
    lines: list[str] = []
    for line in porcelain.splitlines():
        if not line.startswith("!! "):
            continue
        if _is_local_only_retained_private_ignored_entry(vault, _porcelain_line_path(line)):
            continue
        lines.append(line)
    return "\n".join(lines)


def inspect_git_worktree(
    vault: Path,
    git_runner: GitRunner | None = None,
    *,
    self_output_path: str = DEFAULT_OUT,
) -> GitInspection:
    runner = git_runner or _subprocess_git_runner(vault)
    version = runner(["--version"])
    if version.returncode != 0:
        return GitInspection(
            available=False,
            inside_worktree=False,
            worktree_root="",
            head_sha="",
            branch="",
            dirty_entry_count=0,
            status_porcelain_sha256=_sha256_text(""),
            status_codes={},
            self_output_dirty_entry_count=0,
            self_output_dirty_status_porcelain_sha256=_sha256_text(""),
            self_output_dirty_status_codes={},
            durable_private_ignored_entry_count=0,
            durable_private_ignored_status_porcelain_sha256=_sha256_text(""),
            durable_private_ignored_status_codes={},
            durable_private_ignored_error="",
            error=version.stderr or "git executable unavailable",
        )

    inside = runner(["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return GitInspection(
            available=True,
            inside_worktree=False,
            worktree_root="",
            head_sha="",
            branch="",
            dirty_entry_count=0,
            status_porcelain_sha256=_sha256_text(""),
            status_codes={},
            self_output_dirty_entry_count=0,
            self_output_dirty_status_porcelain_sha256=_sha256_text(""),
            self_output_dirty_status_codes={},
            durable_private_ignored_entry_count=0,
            durable_private_ignored_status_porcelain_sha256=_sha256_text(""),
            durable_private_ignored_status_codes={},
            durable_private_ignored_error="",
            error=inside.stderr,
        )

    root = runner(["rev-parse", "--show-toplevel"])
    head = runner(["rev-parse", "--verify", "HEAD"])
    branch = runner(["branch", "--show-current"])
    status = runner(["status", "--porcelain=v1", "--untracked-files=normal"])
    raw_porcelain = status.stdout if status.returncode == 0 else ""
    porcelain, self_output_porcelain = _split_self_output_status(
        raw_porcelain,
        self_output_path=self_output_path,
    )
    ignored_status = runner(
        [
            "status",
            "--porcelain=v1",
            "--ignored=matching",
            "--untracked-files=all",
            "--",
            *[prefix.rstrip("/") for prefix in DURABLE_PRIVATE_IGNORED_PREFIXES],
        ]
    )
    ignored_porcelain = (
        _durable_private_ignored_porcelain_lines(vault, ignored_status.stdout)
        if ignored_status.returncode == 0
        else ""
    )
    return GitInspection(
        available=True,
        inside_worktree=True,
        worktree_root=_relative_or_marker(vault, root.stdout),
        head_sha=head.stdout if head.returncode == 0 else "",
        branch=branch.stdout if branch.returncode == 0 else "",
        dirty_entry_count=len([line for line in porcelain.splitlines() if line.strip()]),
        status_porcelain_sha256=_sha256_text(porcelain),
        status_codes=_porcelain_status_codes(porcelain),
        self_output_dirty_entry_count=len(
            [line for line in self_output_porcelain.splitlines() if line.strip()]
        ),
        self_output_dirty_status_porcelain_sha256=_sha256_text(self_output_porcelain),
        self_output_dirty_status_codes=_porcelain_status_codes(self_output_porcelain),
        durable_private_ignored_entry_count=len(
            [line for line in ignored_porcelain.splitlines() if line.strip()]
        ),
        durable_private_ignored_status_porcelain_sha256=_sha256_text(ignored_porcelain),
        durable_private_ignored_status_codes=_porcelain_status_codes(ignored_porcelain),
        durable_private_ignored_error=(
            ignored_status.stderr if ignored_status.returncode != 0 else ""
        ),
        error=status.stderr if status.returncode != 0 else "",
    )


def detect_execution_mode(vault: Path, git: GitInspection) -> str:
    if git.inside_worktree:
        return "git_worktree"
    if all((vault / rel_path).exists() for rel_path in PUBLIC_SOURCE_LAYOUT_PATHS):
        return "zip_extract"
    return "unknown"


def _blocker(blocker_id: str, severity: str, summary: str, next_action: str) -> WorktreeBlocker:
    return WorktreeBlocker(
        blocker_id=blocker_id,
        severity=severity,
        summary=summary,
        next_action=next_action,
    )


def evaluate_blockers(
    *,
    requested_mode: str,
    detected_mode: str,
    git: GitInspection,
) -> list[WorktreeBlocker]:
    blockers: list[WorktreeBlocker] = []
    if requested_mode not in REQUESTED_MODES:
        blockers.append(
            _blocker(
                "invalid_requested_mode",
                "fatal",
                f"requested_mode={requested_mode!r} is not supported",
                "Use requested mode auto, git, or zip.",
            )
        )
    if not git.available:
        blockers.append(
            _blocker(
                "git_unavailable",
                "fatal",
                "git is unavailable, so the preflight cannot prove worktree state",
                "Run from an environment with git installed before starting a long goal runtime.",
            )
        )
    if requested_mode == "git" and detected_mode != "git_worktree":
        blockers.append(
            _blocker(
                "git_worktree_required",
                "fatal",
                f"requested git mode but detected {detected_mode}",
                "Start the unattended goal runtime from a Git checkout, not an extracted ZIP tree.",
            )
        )
    if requested_mode == "zip" and detected_mode == "git_worktree":
        blockers.append(
            _blocker(
                "zip_mode_requested_in_git_worktree",
                "fatal",
                "requested ZIP mode but detected a Git worktree",
                "Run the ZIP replay guard inside the extracted source package, or request git mode.",
            )
        )
    if detected_mode == "unknown":
        blockers.append(
            _blocker(
                "repository_layout_unknown",
                "fatal",
                "the vault root is neither a Git worktree nor a recognizable source extract",
                "Run preflight from the repository root or from the root of an extracted source package.",
            )
        )
    if detected_mode == "zip_extract":
        blockers.append(
            _blocker(
                "zip_mode_non_promotable",
                "blocking",
                "ZIP/source extract mode is replay-only for long goal runs",
                "Use ZIP mode for package replay checks only; use a Git checkout for unattended mutation and promotion.",
            )
        )
    if git.dirty_entry_count:
        blockers.append(
            _blocker(
                "git_worktree_dirty",
                "blocking",
                f"Git worktree has {git.dirty_entry_count} dirty status entries",
                "Commit, stash, or remove dirty entries before treating goal output as promotable.",
            )
        )
    if git.durable_private_ignored_entry_count:
        blockers.append(
            _blocker(
                "git_durable_private_ignored_dirty",
                "blocking",
                (
                    "Git worktree has "
                    f"{git.durable_private_ignored_entry_count} ignored durable private evidence "
                    "entrie(s)"
                ),
                (
                    "Track, archive, or remove ignored durable private evidence before treating "
                    "goal output as promotable."
                ),
            )
        )
    return blockers


def _status_from_blockers(blockers: Sequence[WorktreeBlocker]) -> str:
    if any(item.severity == "fatal" for item in blockers):
        return "fail"
    if blockers:
        return "attention"
    return "pass"


def _can_execute_goal_runtime(detected_mode: str, blockers: Sequence[WorktreeBlocker]) -> bool:
    if detected_mode != "git_worktree":
        return False
    return not any(item.severity == "fatal" for item in blockers)


def _blockers_as_dicts(blockers: Sequence[WorktreeBlocker]) -> list[dict[str, str]]:
    return [
        {
            "blocker_id": blocker.blocker_id,
            "severity": blocker.severity,
            "summary": blocker.summary,
            "next_action": blocker.next_action,
        }
        for blocker in blockers
    ]


def _request_from_legacy(
    vault_or_request: Path | GoalWorktreeGuardRequest,
    legacy_fields: dict[str, Any],
) -> GoalWorktreeGuardRequest:
    if isinstance(vault_or_request, GoalWorktreeGuardRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        return vault_or_request
    return GoalWorktreeGuardRequest(vault=Path(vault_or_request), **legacy_fields)


def build_report(
    vault_or_request: Path | GoalWorktreeGuardRequest,
    **legacy_fields: Any,
) -> dict[str, Any]:
    request = _request_from_legacy(vault_or_request, legacy_fields)
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    out_path = request.out_path or DEFAULT_OUT
    git = inspect_git_worktree(vault, request.git_runner, self_output_path=out_path)
    detected_mode = detect_execution_mode(vault, git)
    blockers = evaluate_blockers(
        requested_mode=request.requested_mode,
        detected_mode=detected_mode,
        git=git,
    )
    fatal_blockers = [item.blocker_id for item in blockers if item.severity == "fatal"]
    blocking_blockers = [item.blocker_id for item in blockers if item.severity != "fatal"]
    can_execute = _can_execute_goal_runtime(detected_mode, blockers)
    can_promote = can_execute and not blockers
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="goal_worktree_guard",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_worktree_guard.py",
                "ops/schemas/goal-worktree-guard.schema.json",
                "mk/mechanism.mk",
                "mk/release.mk",
            ],
            text_inputs={
                "public_source_layout_paths": json.dumps(PUBLIC_SOURCE_LAYOUT_PATHS),
                "durable_private_ignored_prefixes": json.dumps(
                    DURABLE_PRIVATE_IGNORED_PREFIXES
                ),
                "local_only_retained_private_ignored_paths": json.dumps(
                    LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_PATHS
                ),
                "local_only_retained_private_ignored_prefixes": json.dumps(
                    LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_PREFIXES
                ),
            },
            source_tree_excluded_files=(request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "requested_mode": request.requested_mode,
        "detected_mode": detected_mode,
        "public_source_layout": {
            "required_paths": list(PUBLIC_SOURCE_LAYOUT_PATHS),
            "present": all((vault / rel_path).exists() for rel_path in PUBLIC_SOURCE_LAYOUT_PATHS),
            "missing_paths": [
                rel_path for rel_path in PUBLIC_SOURCE_LAYOUT_PATHS if not (vault / rel_path).exists()
            ],
        },
        "git": {
            "available": git.available,
            "inside_worktree": git.inside_worktree,
            "worktree_root": git.worktree_root,
            "head_sha": git.head_sha,
            "branch": git.branch,
            "dirty_entry_count": git.dirty_entry_count,
            "status_porcelain_sha256": git.status_porcelain_sha256,
            "status_codes": git.status_codes,
            "self_output_dirty_entry_count": git.self_output_dirty_entry_count,
            "self_output_dirty_status_porcelain_sha256": (
                git.self_output_dirty_status_porcelain_sha256
            ),
            "self_output_dirty_status_codes": git.self_output_dirty_status_codes,
            "durable_private_ignored_entry_count": git.durable_private_ignored_entry_count,
            "durable_private_ignored_status_porcelain_sha256": (
                git.durable_private_ignored_status_porcelain_sha256
            ),
            "durable_private_ignored_status_codes": (
                git.durable_private_ignored_status_codes
            ),
            "durable_private_ignored_error": git.durable_private_ignored_error,
            "error": git.error,
        },
        "decisions": {
            "can_execute_goal_runtime": can_execute,
            "can_promote_result": can_promote,
            "zip_mode_replay_only": detected_mode == "zip_extract",
            "fatal_blockers": fatal_blockers,
            "promotion_blockers": blocking_blockers,
        },
        "blockers": _blockers_as_dicts(blockers),
        "status": _status_from_blockers(blockers),
    }


def write_report(vault: Path, report: Mapping[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal worktree guard schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify Git vs ZIP mode before long goal runs.")
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--requested-mode", choices=REQUESTED_MODES, default="git")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero for attention as well as fail.")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalWorktreeGuardRequest(
            vault=vault,
            requested_mode=args.requested_mode,
            out_path=args.out,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if report["status"] == "fail" or (args.strict and report["status"] != "pass"):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
