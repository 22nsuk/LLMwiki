from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_OUT = "tmp/release-ready-commit.json"
DEFAULT_MESSAGE = "release: converge all surfaces"

GENERATED_FILES = {
    ".gitignore",
    "ops/manifest.json",
    "ops/raw-registry.json",
    "ops/script-output-surfaces.json",
    "ops/operator/artifact-relocation-audit.json",
}
GENERATED_PREFIXES = ("ops/reports/",)
PUBLIC_SOURCE_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "LICENSE",
    "Makefile",
    "README.md",
    "mypy.ini",
    "pyproject.toml",
    "pytest.ini",
    "requirements-dev.txt",
    "requirements.txt",
    "uv.lock",
}
PUBLIC_SOURCE_PREFIXES = (
    ".codex/agents/",
    ".github/",
    "mk/",
    "ops/",
    "tests/",
    "tools/",
)
PRIVATE_OR_TRANSIENT_PREFIXES = (
    ".git/",
    ".venv/",
    "build/",
    "dist/",
    "external-reports/",
    "raw/",
    "review/",
    "runs/",
    "system/",
    "tmp/",
    "wiki/",
)


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class StatusEntry:
    xy: str
    path: str
    original_path: str = ""

    @property
    def staged(self) -> bool:
        return self.xy[:1] not in (" ", "?")


def _run_git(vault: Path, args: list[str]) -> GitResult:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=vault,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return GitResult(127, "", "git executable not found")
    return GitResult(result.returncode, result.stdout, result.stderr)


def _require_git_worktree(vault: Path) -> tuple[bool, str]:
    inside = _run_git(vault, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False, inside.stderr.strip() or "not inside a Git worktree"
    return True, ""


def _head(vault: Path) -> str:
    result = _run_git(vault, ["rev-parse", "--verify", "HEAD"])
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def parse_status_porcelain_z(raw: str) -> list[StatusEntry]:
    entries: list[StatusEntry] = []
    parts = raw.split("\0")
    index = 0
    while index < len(parts):
        item = parts[index]
        index += 1
        if not item:
            continue
        xy = item[:2]
        path = item[3:] if len(item) >= 4 else ""
        original_path = ""
        if "R" in xy or "C" in xy:
            if index < len(parts):
                original_path = parts[index]
                index += 1
        entries.append(StatusEntry(xy=xy, path=path, original_path=original_path))
    return entries


def git_status_entries(vault: Path) -> list[StatusEntry]:
    status = _run_git(vault, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "git status failed")
    return parse_status_porcelain_z(status.stdout)


def _normalize_repo_path(path: str) -> str:
    normalized = Path(path).as_posix().lstrip("./")
    if normalized in ("", "."):
        return ""
    parts = normalized.split("/")
    if normalized.startswith("/") or ".." in parts:
        return "<outside-repo>"
    return normalized


def classify_path(path: str) -> str:
    normalized = _normalize_repo_path(path)
    if not normalized or normalized == "<outside-repo>":
        return "unexpected"
    if normalized in GENERATED_FILES or normalized.startswith(GENERATED_PREFIXES):
        return "generated_canonical"
    if normalized.startswith(PRIVATE_OR_TRANSIENT_PREFIXES):
        return "unexpected"
    if normalized in PUBLIC_SOURCE_FILES or normalized.startswith(PUBLIC_SOURCE_PREFIXES):
        return "public_source"
    return "unexpected"


def _load_preexisting_paths(pre_status_path: Path | None) -> set[str]:
    if pre_status_path is None or not pre_status_path.exists():
        return set()
    payload = json.loads(pre_status_path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return set()
    paths: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path:
            paths.add(path)
    return paths


def _entry_payload(entry: StatusEntry, *, preexisting_paths: set[str]) -> dict[str, Any]:
    path = _normalize_repo_path(entry.path)
    return {
        "xy": entry.xy,
        "path": path,
        "original_path": _normalize_repo_path(entry.original_path) if entry.original_path else "",
        "category": classify_path(path),
        "phase": "preexisting" if path in preexisting_paths else "converge_or_post_snapshot",
        "staged": entry.staged,
    }


def _write_report(out_path: Path, payload: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _display_path(vault: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(vault).as_posix()
    except ValueError:
        return path.as_posix()


def _base_report(vault: Path, entries: list[StatusEntry], preexisting_paths: set[str]) -> dict[str, Any]:
    entry_payloads = [_entry_payload(entry, preexisting_paths=preexisting_paths) for entry in entries]
    counts: dict[str, int] = {}
    for item in entry_payloads:
        category = str(item["category"])
        counts[category] = counts.get(category, 0) + 1
    return {
        "artifact_kind": "release_ready_commit_report",
        "producer": "ops.scripts.release_ready_commit",
        "vault": ".",
        "head_before": _head(vault),
        "entries": entry_payloads,
        "counts": dict(sorted(counts.items())),
    }


def _stage_entries(vault: Path, entries: list[dict[str, Any]]) -> GitResult:
    tracked_paths = [
        str(item["path"])
        for item in entries
        if item.get("path") and item.get("xy") != "??"
    ]
    untracked_paths = [
        str(item["path"])
        for item in entries
        if item.get("path") and item.get("xy") == "??"
    ]
    if tracked_paths:
        tracked_result = _run_git(vault, ["add", "-u", "--", *tracked_paths])
        if tracked_result.returncode != 0:
            return tracked_result
    if untracked_paths:
        return _run_git(vault, ["add", "-f", "--", *untracked_paths])
    return GitResult(0, "", "")


def _commit(vault: Path, message: str) -> GitResult:
    return _run_git(vault, ["commit", "-m", message])


def _commit_amend(vault: Path) -> GitResult:
    return _run_git(vault, ["commit", "--amend", "--no-edit"])


def _load_amend_base(amend_of_path: Path | None) -> dict[str, Any]:
    if amend_of_path is None or not amend_of_path.exists():
        return {}
    payload = json.loads(amend_of_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_snapshot(vault: Path, out_path: Path) -> int:
    ok, reason = _require_git_worktree(vault)
    if not ok:
        _write_report(out_path, {"status": "blocked", "reason": reason, "entries": []})
        return 1
    entries = git_status_entries(vault)
    report = _base_report(vault, entries, preexisting_paths=set())
    report["status"] = "snapshot"
    report["dirty_entry_count"] = len(entries)
    _write_report(out_path, report)
    print(out_path.as_posix())
    return 0


def run_commit(
    *,
    vault: Path,
    out_path: Path,
    message: str,
    pre_status_path: Path | None,
    amend: bool,
    amend_of_path: Path | None,
    dry_run: bool,
    allow_staged: bool,
) -> int:
    ok, reason = _require_git_worktree(vault)
    if not ok:
        _write_report(out_path, {"status": "blocked", "reason": reason, "entries": []})
        return 1

    entries = git_status_entries(vault)
    preexisting_paths = _load_preexisting_paths(pre_status_path)
    report = _base_report(vault, entries, preexisting_paths=preexisting_paths)
    report["message"] = message
    report["dry_run"] = dry_run
    report["amend"] = amend

    amend_base = _load_amend_base(amend_of_path) if amend else {}
    if amend:
        report["amend_of"] = _display_path(vault, amend_of_path)
        expected_head = str(amend_base.get("head_after", "")).strip()
        current_head = _head(vault)
        report["expected_head_before_amend"] = expected_head
        report["actual_head_before_amend"] = current_head
        if not expected_head:
            report["status"] = "blocked"
            report["reason"] = "amend_base_missing_head"
            _write_report(out_path, report)
            print("release-ready-amend refused: amend base has no head_after", file=sys.stderr)
            return 1
        if current_head != expected_head:
            report["status"] = "blocked"
            report["reason"] = "amend_base_head_mismatch"
            _write_report(out_path, report)
            print("release-ready-amend refused: current HEAD does not match amend base", file=sys.stderr)
            return 1

    unexpected = [item for item in report["entries"] if item["category"] == "unexpected"]
    late_public_source = [
        item for item in report["entries"] if amend and item["category"] == "public_source"
    ]
    staged = [item for item in report["entries"] if item["staged"]]
    if unexpected:
        report["status"] = "blocked"
        report["reason"] = "unexpected_dirty_paths"
        report["unexpected_paths"] = [item["path"] for item in unexpected]
        _write_report(out_path, report)
        print("release-ready-commit refused: unexpected dirty paths are present", file=sys.stderr)
        for item in unexpected:
            print(item["path"], file=sys.stderr)
        return 1
    if late_public_source:
        report["status"] = "blocked"
        report["reason"] = "amend_contains_public_source_changes"
        report["late_public_source_paths"] = [item["path"] for item in late_public_source]
        _write_report(out_path, report)
        print(
            "release-ready-amend refused: public source changed after release-ready commit",
            file=sys.stderr,
        )
        return 1
    if staged and not allow_staged:
        report["status"] = "blocked"
        report["reason"] = "preexisting_staged_changes"
        report["staged_paths"] = [item["path"] for item in staged]
        _write_report(out_path, report)
        print("release-ready-commit refused: staged changes are present", file=sys.stderr)
        return 1

    paths = [str(item["path"]) for item in report["entries"] if item["path"]]
    if not paths:
        report["status"] = "no_changes"
        report["head_after"] = _head(vault)
        _write_report(out_path, report)
        action = "release-ready-amend" if amend else "release-ready-commit"
        print(f"{action}: no dirty release-ready changes")
        return 0

    report["paths_to_commit"] = paths
    if dry_run:
        report["status"] = "dry_run"
        report["head_after"] = _head(vault)
        _write_report(out_path, report)
        print(out_path.as_posix())
        return 0

    stage = _stage_entries(vault, report["entries"])
    if stage.returncode != 0:
        report["status"] = "blocked"
        report["reason"] = "git_add_failed"
        report["stderr"] = stage.stderr.strip()
        _write_report(out_path, report)
        print(stage.stderr, file=sys.stderr)
        return stage.returncode or 1

    commit = _commit_amend(vault) if amend else _commit(vault, message)
    if commit.returncode != 0:
        report["status"] = "blocked"
        report["reason"] = "git_amend_failed" if amend else "git_commit_failed"
        report["stdout"] = commit.stdout.strip()
        report["stderr"] = commit.stderr.strip()
        _write_report(out_path, report)
        print(commit.stdout, file=sys.stderr)
        print(commit.stderr, file=sys.stderr)
        return commit.returncode or 1

    report["status"] = "amended" if amend else "committed"
    report["stdout"] = commit.stdout.strip()
    report["head_after"] = _head(vault)
    _write_report(out_path, report)
    print(out_path.as_posix())
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Commit release-ready public source changes together with converged canonical artifacts."
    )
    parser.add_argument("--vault", default=".", help="Repository root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Report path.")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Commit message.")
    parser.add_argument("--pre-status", default="", help="Optional snapshot report captured before converge.")
    parser.add_argument(
        "--amend",
        action="store_true",
        help="Amend the release-ready commit instead of creating a second stabilization commit.",
    )
    parser.add_argument(
        "--amend-of",
        default="",
        help="Report path from the release-ready commit whose head_after must match current HEAD.",
    )
    parser.add_argument("--snapshot-only", action="store_true", help="Only write the current dirty snapshot.")
    parser.add_argument("--dry-run", action="store_true", help="Classify and report without staging or committing.")
    parser.add_argument(
        "--allow-staged",
        action="store_true",
        help="Allow pre-staged changes to be included in the release-ready commit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault)
    out_path = vault / args.out
    if args.snapshot_only:
        return build_snapshot(vault, out_path)
    pre_status_path = vault / args.pre_status if args.pre_status else None
    amend_of_path = vault / args.amend_of if args.amend_of else None
    return run_commit(
        vault=vault,
        out_path=out_path,
        message=args.message,
        pre_status_path=pre_status_path,
        amend=bool(args.amend),
        amend_of_path=amend_of_path,
        dry_run=bool(args.dry_run),
        allow_staged=bool(args.allow_staged),
    )


if __name__ == "__main__":
    raise SystemExit(main())
