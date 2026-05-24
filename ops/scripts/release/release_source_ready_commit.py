from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from ops.scripts.release_authority_vocabulary import REASON_MACHINE_RELEASE_NOT_ALLOWED
from ops.scripts.release.release_status_v2 import release_status_v2_view_with_readiness_fallback

DEFAULT_OUT = "tmp/release-source-ready-commit.json"
DEFAULT_MESSAGE = "release: converge source-ready surfaces"
GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH = "tmp/goal-runtime-local-evidence-refresh.json"
RELEASE_CLOSEOUT_SUMMARY = "ops/reports/release-closeout-summary.json"
ARTIFACT_FRESHNESS_REPORT = "ops/reports/artifact-freshness-report.json"

GENERATED_FILES = {
    ".gitignore",
    "ops/script-output-surfaces.json",
}
GENERATED_PREFIXES: tuple[str, ...] = ()
PUBLIC_SOURCE_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "mypy.ini",
    "pyproject.toml",
    "pytest.ini",
    "requirements-dev.txt",
    "requirements.txt",
    "uv.lock",
}
LOCAL_SOURCE_CONTRACT_FILES = {
    "AGENTS.local.md",
}
PUBLIC_SOURCE_PREFIXES = (
    ".codex/agents/",
    ".github/",
    "docs/",
    "mk/",
    "ops/",
    "tests/",
    "tools/",
)
SOURCE_CONTRACT_CATEGORIES = {"public_source", "local_source_contract"}
PRIVATE_OR_TRANSIENT_PREFIXES = (
    ".git/",
    ".venv/",
    "build/",
    "dist/",
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "raw/",
    "review/",
    "runs/",
    "system/",
    "tmp/",
    "wiki/",
)
DURABLE_PRIVATE_IGNORED_STATUS_PREFIXES = (
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
LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_STATUS_PATHS = (
    "AGENTS.local.md",
    "external-reports/report-reference-manifest.json",
    "ops/manifest.json",
    "ops/raw-registry.json",
)
LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_STATUS_PREFIXES = (
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "raw/",
    "runs/",
    "system/",
    "wiki/",
)
LOCAL_ONLY_PRIVATE_DEINDEX_PATHS = (
    "AGENTS.local.md",
    "ops/manifest.json",
    "ops/raw-registry.json",
)
LOCAL_ONLY_PRIVATE_DEINDEX_PREFIXES = (
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "raw/",
    "runs/",
    "system/",
    "wiki/",
)
LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY = "local_only_private_deindex"


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


def _is_local_only_retained_private_ignored_path(rel_path: str) -> bool:
    if rel_path in LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_STATUS_PATHS:
        return True
    return any(
        rel_path == prefix.rstrip("/") or rel_path.startswith(prefix)
        for prefix in LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_STATUS_PREFIXES
    )


def _ignored_directory_contains_only_local_retained_files(vault: Path, rel_path: str) -> bool:
    path = vault / rel_path
    if not path.is_dir():
        return False
    files = [item for item in path.rglob("*") if item.is_file()]
    return bool(files) and all(
        _is_local_only_retained_private_ignored_path(
            _normalize_repo_path(item.relative_to(vault).as_posix())
        )
        for item in files
    )


def _is_local_only_retained_private_ignored_entry(vault: Path, entry: StatusEntry) -> bool:
    path = _normalize_repo_path(entry.path)
    if _is_local_only_retained_private_ignored_path(path):
        return True
    return _ignored_directory_contains_only_local_retained_files(vault, path)


def git_status_entries(vault: Path) -> list[StatusEntry]:
    status = _run_git(vault, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "git status failed")
    ignored_status = _run_git(
        vault,
        [
            "status",
            "--porcelain=v1",
            "-z",
            "--ignored=matching",
            "--untracked-files=all",
            "--",
            *[prefix.rstrip("/") for prefix in DURABLE_PRIVATE_IGNORED_STATUS_PREFIXES],
        ],
    )
    if ignored_status.returncode != 0:
        raise RuntimeError(
            ignored_status.stderr.strip() or "git ignored durable private status failed"
        )
    ignored_entries = [
        entry
        for entry in parse_status_porcelain_z(ignored_status.stdout)
        if entry.xy == "!!"
        and not _is_local_only_retained_private_ignored_entry(vault, entry)
    ]
    entries = [*parse_status_porcelain_z(status.stdout), *ignored_entries]
    deduped: dict[tuple[str, str, str], StatusEntry] = {}
    for entry in entries:
        deduped[(entry.xy, entry.path, entry.original_path)] = entry
    return list(deduped.values())


def _normalize_repo_path(path: str) -> str:
    normalized = Path(path).as_posix()
    if normalized in ("", "."):
        return ""
    if normalized.startswith("/"):
        return "<outside-repo>"
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if ".." in parts:
        return "<outside-repo>"
    return normalized


def _matches_prefix_or_root(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def classify_path(path: str) -> str:
    normalized = _normalize_repo_path(path)
    if not normalized or normalized == "<outside-repo>":
        return "unexpected"
    if normalized in GENERATED_FILES or _matches_prefix_or_root(normalized, GENERATED_PREFIXES):
        return "generated_canonical"
    if normalized in LOCAL_SOURCE_CONTRACT_FILES:
        return "local_source_contract"
    if _matches_prefix_or_root(normalized, PRIVATE_OR_TRANSIENT_PREFIXES):
        return "unexpected"
    if normalized in PUBLIC_SOURCE_FILES or _matches_prefix_or_root(normalized, PUBLIC_SOURCE_PREFIXES):
        return "public_source"
    return "unexpected"


def _is_local_only_private_deindex(vault: Path, entry: StatusEntry, path: str) -> bool:
    if "D" not in entry.xy:
        return False
    if path not in LOCAL_ONLY_PRIVATE_DEINDEX_PATHS and not any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in LOCAL_ONLY_PRIVATE_DEINDEX_PREFIXES
    ):
        return False
    return (vault / path).exists()


def _classify_entry(vault: Path, entry: StatusEntry, path: str) -> str:
    if _is_local_only_private_deindex(vault, entry, path):
        return LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY
    return classify_path(path)


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


def _load_report(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_repo_report(vault: Path, rel_path: str) -> dict[str, Any]:
    return _load_report(vault / rel_path)


def _text_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _bool_field(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is True


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _goal_runtime_refresh_diagnostics(vault: Path) -> dict[str, Any]:
    payload = _load_repo_report(vault, GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH)
    if not payload:
        return {"path": GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH, "present": False}
    iterations = []
    for item in payload.get("iterations", []):
        if not isinstance(item, dict):
            continue
        changed_paths = [
            str(path)
            for path in item.get("changed_paths", [])
            if isinstance(path, str)
        ]
        iterations.append(
            {
                "iteration_index": item.get("iteration_index", 0),
                "status": _text_field(item, "status"),
                "changed_path_count": len(changed_paths),
                "changed_paths": changed_paths[:20],
            }
        )
    return {
        "path": GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH,
        "present": True,
        "status": _text_field(payload, "status"),
        "reason": _text_field(payload, "reason"),
        "digest_mode": _text_field(payload, "digest_mode"),
        "summary": _dict_field(payload, "summary"),
        "iterations": iterations,
    }


def _release_closeout_summary_diagnostics(vault: Path) -> dict[str, Any]:
    payload = _load_repo_report(vault, RELEASE_CLOSEOUT_SUMMARY)
    if not payload:
        return {"path": RELEASE_CLOSEOUT_SUMMARY, "present": False}
    status_view = release_status_v2_view_with_readiness_fallback(payload)
    compatibility_status = str(status_view["compatibility_status_value"])
    release_authority_status = str(status_view["release_authority_status"])
    sealed_release_status = str(status_view["sealed_release_status"])
    blocker_reason_ids = [str(reason) for reason in status_view["blocker_reason_ids"]]
    clean_release_ready = _bool_field(payload, "clean_release_ready")
    machine_release_allowed = (
        release_authority_status == "clean_pass"
        and REASON_MACHINE_RELEASE_NOT_ALLOWED not in blocker_reason_ids
    )
    source_ready = release_authority_status in {"clean_pass", "conditional_pass"} or bool(
        payload.get("checked_in_release_ready")
    )
    if machine_release_allowed:
        classification = "machine_release_allowed"
        note = "release closeout allows machine release."
    elif source_ready and sealed_release_status == "unsealed_distribution_not_provided":
        classification = "source_release_checks_pass_distribution_unsealed"
        note = (
            "release-source-ready/check may pass, but this is not a sealed machine release "
            "until a distribution package is provided and release-evidence-closeout-sealed-check passes."
        )
    else:
        classification = "release_not_machine_allowed"
        note = (
            "release closeout does not currently allow machine release; inspect "
            "status_v2.status_axes.release_authority_status, "
            "status_v2.status_axes.sealed_release_status, and "
            "release_authority_vocabulary.blocker_reason_ids before treating this as distributable."
        )
    return {
        "path": RELEASE_CLOSEOUT_SUMMARY,
        "present": True,
        "compatibility_status_value": compatibility_status,
        "clean_release_ready": clean_release_ready,
        "source_ready": source_ready,
        "machine_release_allowed": machine_release_allowed,
        "release_authority_status": release_authority_status,
        "sealed_release_status": sealed_release_status,
        "blocker_reason_ids": blocker_reason_ids,
        "status_v2_used_legacy_fallback_fields": status_view["used_legacy_fallback_fields"],
        "authoritative_machine_release_target": "release-evidence-closeout-sealed-check",
        "classification": classification,
        "operator_note": note,
    }


def _artifact_freshness_diagnostics(vault: Path) -> dict[str, Any]:
    payload = _load_repo_report(vault, ARTIFACT_FRESHNESS_REPORT)
    if not payload:
        return {"path": ARTIFACT_FRESHNESS_REPORT, "present": False}
    currentness = _dict_field(payload, "currentness")
    return {
        "path": ARTIFACT_FRESHNESS_REPORT,
        "present": True,
        "status": _text_field(payload, "status"),
        "currentness_status": _text_field(currentness, "status"),
        "source_tree_fingerprint": _text_field(payload, "source_tree_fingerprint"),
    }


def _release_source_ready_diagnostics(vault: Path) -> dict[str, Any]:
    return {
        "goal_runtime_local_evidence_refresh": _goal_runtime_refresh_diagnostics(vault),
        "release_closeout_summary": _release_closeout_summary_diagnostics(vault),
        "artifact_freshness": _artifact_freshness_diagnostics(vault),
    }


def _entry_payload(
    vault: Path,
    entry: StatusEntry,
    *,
    preexisting_paths: set[str],
) -> dict[str, Any]:
    path = _normalize_repo_path(entry.path)
    return {
        "xy": entry.xy,
        "path": path,
        "original_path": _normalize_repo_path(entry.original_path) if entry.original_path else "",
        "category": _classify_entry(vault, entry, path),
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
    entry_payloads = [
        _entry_payload(vault, entry, preexisting_paths=preexisting_paths)
        for entry in entries
    ]
    counts: dict[str, int] = {}
    for item in entry_payloads:
        category = str(item["category"])
        counts[category] = counts.get(category, 0) + 1
    return {
        "artifact_kind": "release_source_ready_commit_report",
        "producer": "ops.scripts.release_source_ready_commit",
        "vault": ".",
        "head_before": _head(vault),
        "entries": entry_payloads,
        "counts": dict(sorted(counts.items())),
        "diagnostics": _release_source_ready_diagnostics(vault),
        "durable_private_ignored_status_prefixes": list(
            DURABLE_PRIVATE_IGNORED_STATUS_PREFIXES
        ),
        "local_only_retained_private_ignored_status_paths": list(
            LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_STATUS_PATHS
        ),
        "local_only_retained_private_ignored_status_prefixes": list(
            LOCAL_ONLY_RETAINED_PRIVATE_IGNORED_STATUS_PREFIXES
        ),
        "local_only_private_deindex_paths": list(LOCAL_ONLY_PRIVATE_DEINDEX_PATHS),
        "local_only_private_deindex_prefixes": list(LOCAL_ONLY_PRIVATE_DEINDEX_PREFIXES),
    }


def _stage_entries(vault: Path, entries: list[dict[str, Any]]) -> GitResult:
    local_only_deindex_paths = [
        str(item["path"])
        for item in entries
        if item.get("path")
        and item.get("category") == LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY
        and not item.get("staged")
    ]
    tracked_paths = [
        str(item["path"])
        for item in entries
        if item.get("path")
        and item.get("xy") != "??"
        and item.get("category") != LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY
    ]
    untracked_paths = [
        str(item["path"])
        for item in entries
        if item.get("path")
        and item.get("xy") == "??"
        and item.get("category") != LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY
    ]
    if local_only_deindex_paths:
        deindex_result = _run_git(
            vault,
            ["rm", "--cached", "--ignore-unmatch", "--", *local_only_deindex_paths],
        )
        if deindex_result.returncode != 0:
            return deindex_result
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
    return _load_report(amend_of_path)


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
    only_generated_canonical: bool,
) -> int:
    ok, reason = _require_git_worktree(vault)
    if not ok:
        _write_report(out_path, {"status": "blocked", "reason": reason, "entries": []})
        return 1

    entries = git_status_entries(vault)
    pre_status = _load_report(pre_status_path)
    preexisting_paths = _load_preexisting_paths(pre_status_path)
    report = _base_report(vault, entries, preexisting_paths=preexisting_paths)
    report["message"] = message
    report["dry_run"] = dry_run
    report["amend"] = amend

    if pre_status and not amend:
        expected_head = str(pre_status.get("head_before", "")).strip()
        current_head = _head(vault)
        report["snapshot"] = _display_path(vault, pre_status_path)
        report["expected_head_from_snapshot"] = expected_head
        report["actual_head_before_commit"] = current_head
        if expected_head and current_head != expected_head:
            report["status"] = "blocked"
            report["reason"] = "snapshot_head_mismatch"
            _write_report(out_path, report)
            print(
                "release-source-ready-commit refused: current HEAD does not match release-source-ready snapshot",
                file=sys.stderr,
            )
            return 1

    amend_base = _load_amend_base(amend_of_path) if amend else {}
    if amend:
        report["amend_of"] = _display_path(vault, amend_of_path)
        report["amend_of_status"] = str(amend_base.get("status", "")).strip()
        expected_head = str(amend_base.get("head_after", "")).strip()
        current_head = _head(vault)
        report["expected_head_before_amend"] = expected_head
        report["actual_head_before_amend"] = current_head
        if not expected_head:
            report["status"] = "blocked"
            report["reason"] = "amend_base_missing_head"
            _write_report(out_path, report)
            print("release-source-ready-amend refused: amend base has no head_after", file=sys.stderr)
            return 1
        if current_head != expected_head:
            report["status"] = "blocked"
            report["reason"] = "amend_base_head_mismatch"
            _write_report(out_path, report)
            print("release-source-ready-amend refused: current HEAD does not match amend base", file=sys.stderr)
            return 1

    unexpected = [item for item in report["entries"] if item["category"] == "unexpected"]
    late_source_contract = [
        item
        for item in report["entries"]
        if amend and item["category"] in SOURCE_CONTRACT_CATEGORIES
    ]
    staged = [
        item
        for item in report["entries"]
        if item["staged"] and item["category"] != LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY
    ]
    non_generated = [
        item
        for item in report["entries"]
        if item["category"] != "generated_canonical"
    ]
    paths = [str(item["path"]) for item in report["entries"] if item["path"]]
    if unexpected:
        report["status"] = "blocked"
        report["reason"] = "unexpected_dirty_paths"
        report["unexpected_paths"] = [item["path"] for item in unexpected]
        _write_report(out_path, report)
        print("release-source-ready-commit refused: unexpected dirty paths are present", file=sys.stderr)
        for item in unexpected:
            print(item["path"], file=sys.stderr)
        return 1
    if late_source_contract:
        report["status"] = "blocked"
        if all(item["category"] == "public_source" for item in late_source_contract):
            report["reason"] = "amend_contains_public_source_changes"
            report["late_public_source_paths"] = [
                item["path"] for item in late_source_contract
            ]
        else:
            report["reason"] = "amend_contains_source_contract_changes"
            report["late_source_contract_paths"] = [
                item["path"] for item in late_source_contract
            ]
        _write_report(out_path, report)
        print(
            "release-source-ready-amend refused: source contract changed after release-source-ready commit",
            file=sys.stderr,
        )
        return 1
    if staged and not allow_staged:
        report["status"] = "blocked"
        report["reason"] = "preexisting_staged_changes"
        report["staged_paths"] = [item["path"] for item in staged]
        _write_report(out_path, report)
        print("release-source-ready-commit refused: staged changes are present", file=sys.stderr)
        return 1
    if only_generated_canonical and non_generated:
        report["status"] = "blocked"
        report["reason"] = "non_generated_dirty_paths"
        report["non_generated_paths"] = [item["path"] for item in non_generated]
        _write_report(out_path, report)
        print(
            "release-source-ready-commit refused: non-generated dirty paths are present",
            file=sys.stderr,
        )
        for item in non_generated:
            print(item["path"], file=sys.stderr)
        return 1

    if amend and paths and report["amend_of_status"] not in {"committed", "amended"}:
        report["status"] = "blocked"
        report["reason"] = "amend_base_not_committed"
        report["paths_after_uncommitted_base"] = paths
        _write_report(out_path, report)
        print(
            "release-source-ready-amend refused: release-source-ready commit did not create a commit",
            file=sys.stderr,
        )
        return 1

    if not paths:
        report["status"] = "no_changes"
        report["head_after"] = _head(vault)
        _write_report(out_path, report)
        action = "release-source-ready-amend" if amend else "release-source-ready-commit"
        print(f"{action}: no dirty release-source-ready changes")
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
        description="Commit release-source-ready public source changes together with converged canonical artifacts."
    )
    parser.add_argument("--vault", default=".", help="Repository root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Report path.")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Commit message.")
    parser.add_argument("--pre-status", default="", help="Optional snapshot report captured before converge.")
    parser.add_argument(
        "--amend",
        action="store_true",
        help="Amend the release-source-ready commit instead of creating a second stabilization commit.",
    )
    parser.add_argument(
        "--amend-of",
        default="",
        help="Report path from the release-source-ready commit whose head_after must match current HEAD.",
    )
    parser.add_argument("--snapshot-only", action="store_true", help="Only write the current dirty snapshot.")
    parser.add_argument("--dry-run", action="store_true", help="Classify and report without staging or committing.")
    parser.add_argument(
        "--allow-staged",
        action="store_true",
        help="Allow pre-staged changes to be included in the release-source-ready commit.",
    )
    parser.add_argument(
        "--only-generated-canonical",
        action="store_true",
        help="Refuse to commit anything except tracked generated source contracts.",
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
        only_generated_canonical=bool(args.only_generated_canonical),
    )


if __name__ == "__main__":
    raise SystemExit(main())
