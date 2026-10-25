from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .public_surface_policy import is_public_excluded_path

SOURCE_HISTORY_REF_SCOPE = "all_refs_and_head"
SOURCE_HISTORY_SAMPLE_LIMIT = 20
GIT_NO_REPLACE_OBJECTS = "--no-replace-objects"
GIT_REPOSITORY_ENVIRONMENT_OVERRIDES = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


@dataclass(frozen=True)
class _GitResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _run_git(
    vault: Path,
    *args: str,
    input_text: str | None = None,
) -> _GitResult:
    environment = os.environ.copy()
    for variable in GIT_REPOSITORY_ENVIRONMENT_OVERRIDES:
        environment.pop(variable, None)
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        result = subprocess.run(
            ["git", GIT_NO_REPLACE_OBJECTS, *args],
            cwd=vault,
            env=environment,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return _GitResult(returncode=127, stderr=str(exc))
    return _GitResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _legacy_grafts_present(vault: Path) -> bool | None:
    """Detect active ``info/grafts`` entries that can rewrite commit ancestry."""
    graft_path_result = _run_git(vault, "rev-parse", "--git-path", "info/grafts")
    graft_path_text = graft_path_result.stdout.strip()
    if graft_path_result.returncode != 0 or not graft_path_text:
        return None
    graft_path = Path(graft_path_text)
    if not graft_path.is_absolute():
        graft_path = vault / graft_path
    try:
        if not graft_path.exists():
            return False
        content = graft_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    return any(
        line.strip() and not line.lstrip().startswith("#")
        for line in content.splitlines()
    )


def _ref_records(stdout: str) -> list[tuple[str, str]]:
    records: set[tuple[str, str]] = set()
    for line in stdout.splitlines():
        ref_name, separator, object_id = line.partition("\t")
        if separator and ref_name and object_id:
            records.add((ref_name, object_id))
    return sorted(records)


def _repository_state(vault: Path, *, requested: bool) -> dict[str, Any]:
    if not requested:
        state = {
            "requested": False,
            "repository_available": False,
            "inspection_complete": True,
            "ref_scope": "none",
            "ref_count": 0,
            "head_present": False,
            "shallow_repository": None,
            "legacy_grafts_present": None,
            "reason": "not_requested",
        }
        return {
            **state,
            "_ref_records": [],
            "ref_fingerprint": _fingerprint(state),
        }

    inside = _run_git(vault, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        state = {
            "requested": True,
            "repository_available": False,
            "inspection_complete": False,
            "ref_scope": SOURCE_HISTORY_REF_SCOPE,
            "ref_count": 0,
            "head_present": False,
            "shallow_repository": None,
            "legacy_grafts_present": None,
            "reason": "not_git_repository",
        }
        return {
            **state,
            "_ref_records": [],
            "ref_fingerprint": _fingerprint(state),
        }

    shallow_result = _run_git(vault, "rev-parse", "--is-shallow-repository")
    shallow_text = shallow_result.stdout.strip().lower()
    shallow_repository = (
        shallow_text == "true"
        if shallow_result.returncode == 0 and shallow_text in {"true", "false"}
        else None
    )
    legacy_grafts_present = _legacy_grafts_present(vault)
    refs_result = _run_git(
        vault,
        "for-each-ref",
        "--format=%(refname)%09%(objectname)",
    )
    refs = _ref_records(refs_result.stdout)
    head_result = _run_git(vault, "rev-parse", "--verify", "HEAD")
    head_oid = head_result.stdout.strip() if head_result.returncode == 0 else ""
    symbolic_head_result = _run_git(vault, "symbolic-ref", "-q", "HEAD")
    symbolic_head = (
        symbolic_head_result.stdout.strip()
        if symbolic_head_result.returncode == 0
        else ""
    )
    inspection_complete = (
        shallow_repository is not None
        and legacy_grafts_present is False
        and refs_result.returncode == 0
        and bool(refs or head_oid)
    )
    reason = "repository_state_complete"
    if legacy_grafts_present is True:
        reason = "legacy_grafts_present"
    elif legacy_grafts_present is None:
        reason = "legacy_graft_state_unknown"
    elif shallow_repository is None or refs_result.returncode != 0:
        reason = "repository_state_incomplete"
    elif not refs and not head_oid:
        reason = "no_reachable_refs"
    state = {
        "requested": True,
        "repository_available": True,
        "inspection_complete": inspection_complete,
        "ref_scope": SOURCE_HISTORY_REF_SCOPE,
        "ref_count": len(refs),
        "head_present": bool(head_oid),
        "shallow_repository": shallow_repository,
        "legacy_grafts_present": legacy_grafts_present,
        "reason": reason,
    }
    fingerprint_payload = {
        **state,
        "refs": ["\t".join(record) for record in refs],
        "head_oid": head_oid,
        "symbolic_head": symbolic_head,
    }
    return {
        **state,
        "_ref_records": refs,
        "ref_fingerprint": _fingerprint(fingerprint_payload),
    }


def _raw_history_object_path_records(stdout: str) -> list[tuple[str, str]]:
    """Return every distinct reachable leaf object/path pairing from raw diffs.

    `git rev-list --objects` emits a representative name for each object. That
    loses excluded aliases when the same blob is also reachable at an included
    path. NUL-delimited raw history records preserve every path occurrence; old
    and new object ids retain deleted and modified historical versions.
    """
    fields = stdout.split("\0")
    records: set[tuple[str, str]] = set()
    for index in range(0, len(fields) - 1, 2):
        metadata = fields[index].lstrip("\n")
        path = fields[index + 1]
        if not metadata.startswith(":") or not path:
            continue
        metadata_fields = metadata[1:].split()
        if len(metadata_fields) < 5:
            continue
        for object_id in metadata_fields[2:4]:
            if object_id and set(object_id) != {"0"}:
                records.add((object_id, path))
    return sorted(records, key=lambda record: (record[1], record[0]))


def _tree_listing_object_path_records(stdout: str) -> list[tuple[str, str]]:
    records: set[tuple[str, str]] = set()
    for entry in stdout.split("\0"):
        metadata, separator, path = entry.partition("\t")
        metadata_fields = metadata.split()
        if not separator or not path or len(metadata_fields) != 3:
            continue
        records.add((metadata_fields[2], path))
    return sorted(records, key=lambda record: (record[1], record[0]))


def _non_commit_ref_object_path_records(
    vault: Path,
    ref_records: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], bool, int]:
    records: set[tuple[str, str]] = set()
    complete = True
    tree_ref_count = 0
    for ref_name, _object_id in ref_records:
        object_type_result = _run_git(vault, "cat-file", "-t", f"{ref_name}^{{}}")
        object_type = object_type_result.stdout.strip()
        if object_type_result.returncode != 0:
            complete = False
            continue
        if object_type == "commit":
            continue
        if object_type == "blob":
            continue
        if object_type != "tree":
            complete = False
            continue
        tree_ref_count += 1
        tree_result = _run_git(
            vault,
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            f"{ref_name}^{{tree}}",
        )
        if tree_result.returncode != 0:
            complete = False
            continue
        records.update(_tree_listing_object_path_records(tree_result.stdout))
    return (
        sorted(records, key=lambda record: (record[1], record[0])),
        complete,
        tree_ref_count,
    )


def _object_sizes(vault: Path, object_ids: list[str]) -> tuple[dict[str, int], int]:
    if not object_ids:
        return {}, 0
    result = _run_git(
        vault,
        "cat-file",
        "--batch-check",
        input_text="\n".join(object_ids) + "\n",
    )
    sizes: dict[str, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        object_id, _object_type, size_text = fields
        try:
            sizes[object_id] = int(size_text)
        except ValueError:
            continue
    missing_count = len(set(object_ids) - set(sizes))
    if result.returncode != 0 and missing_count == 0:
        missing_count = len(set(object_ids))
        sizes = {}
    return sizes, missing_count


def scan_source_history(
    vault: Path,
    *,
    requested: bool = True,
    sample_limit: int = SOURCE_HISTORY_SAMPLE_LIMIT,
) -> dict[str, Any]:
    if sample_limit < 1:
        raise ValueError("source history sample_limit must be at least 1")
    state = _repository_state(vault, requested=requested)
    scan_command = ""
    records: list[tuple[str, str]] = []
    enumeration_complete = False
    tree_ref_count = 0
    if requested and state["repository_available"] and state["head_present"]:
        history_args = [
            "log",
            "--format=",
            "--raw",
            "--root",
            "--no-renames",
            "--ignore-submodules=none",
            "-m",
            "-r",
            "-z",
            "--no-abbrev",
            "--all",
            "HEAD",
        ]
        scan_command = f"git {GIT_NO_REPLACE_OBJECTS} " + " ".join(history_args)
        result = _run_git(vault, *history_args)
        records = _raw_history_object_path_records(result.stdout)
        enumeration_complete = result.returncode == 0
    elif requested and state["repository_available"] and state["ref_count"]:
        history_args = [
            "log",
            "--format=",
            "--raw",
            "--root",
            "--no-renames",
            "--ignore-submodules=none",
            "-m",
            "-r",
            "-z",
            "--no-abbrev",
            "--all",
        ]
        scan_command = f"git {GIT_NO_REPLACE_OBJECTS} " + " ".join(history_args)
        result = _run_git(vault, *history_args)
        records = _raw_history_object_path_records(result.stdout)
        enumeration_complete = result.returncode == 0

    if (
        requested
        and state["repository_available"]
        and (state["head_present"] or state["ref_count"])
    ):
        supplemental_records, supplemental_complete, tree_ref_count = (
            _non_commit_ref_object_path_records(vault, state["_ref_records"])
        )
        records = sorted(
            set(records).union(supplemental_records),
            key=lambda record: (record[1], record[0]),
        )
        enumeration_complete = enumeration_complete and supplemental_complete
        if tree_ref_count:
            scan_command += (
                " + git --no-replace-objects ls-tree -r -z --full-tree "
                "<non-commit-tree-ref>"
            )

    violations = [record for record in records if is_public_excluded_path(record[1])]
    violation_object_ids = sorted({object_id for object_id, _path in violations})
    sizes, missing_object_count = _object_sizes(vault, violation_object_ids)
    violation_bytes = sum(sizes.values())
    complete = (
        bool(state["inspection_complete"])
        and enumeration_complete
        and missing_object_count == 0
        and state["shallow_repository"] is False
    )
    if not requested:
        evaluation_status = "not_requested"
        reason = "not_requested"
    elif complete:
        evaluation_status = "evaluated"
        reason = "complete_full_ref_scan"
    else:
        evaluation_status = "insufficient_history"
        if state["shallow_repository"] is True:
            reason = "shallow_repository"
        elif not state["repository_available"] or not state["inspection_complete"]:
            reason = str(state["reason"])
        elif not enumeration_complete:
            reason = "object_enumeration_failed"
        else:
            reason = "object_size_resolution_incomplete"

    if violations:
        status = "fail"
    elif evaluation_status == "evaluated":
        status = "pass"
    else:
        status = "unknown"
    sample_paths = sorted({path for _object_id, path in violations})[:sample_limit]
    history_state_fingerprint = _fingerprint(
        {
            "repository_state_fingerprint": state["ref_fingerprint"],
            "evaluation_status": evaluation_status,
            "status": status,
            "reason": reason,
            "scan_command": scan_command,
            "object_enumeration_complete": enumeration_complete,
            "reachable_object_path_count": len(records),
            "object_path_records_fingerprint": _fingerprint(records),
            "non_commit_tree_ref_count": tree_ref_count,
            "violation_count": len(violations),
            "violation_bytes": violation_bytes,
            "missing_object_count": missing_object_count,
            "sample_limit": sample_limit,
            "sample_paths": sample_paths,
        }
    )
    return {
        "requested": requested,
        "evaluation_status": evaluation_status,
        "status": status,
        "reason": reason,
        "ref_scope": str(state["ref_scope"]),
        "ref_count": int(state["ref_count"]),
        "head_present": bool(state["head_present"]),
        "shallow_repository": state["shallow_repository"],
        "legacy_grafts_present": state["legacy_grafts_present"],
        "ref_fingerprint": str(state["ref_fingerprint"]),
        "history_state_fingerprint": history_state_fingerprint,
        "scan_command": scan_command,
        "object_enumeration_complete": enumeration_complete,
        "reachable_object_path_count": len(records),
        "violation_count": len(violations),
        "violation_bytes": violation_bytes,
        "missing_object_count": missing_object_count,
        "sample_limit": sample_limit,
        "sample_paths": sample_paths,
    }


def source_history_state_fingerprint(
    vault: Path,
    *,
    requested: bool = True,
) -> str:
    return str(
        scan_source_history(vault, requested=requested)["history_state_fingerprint"]
    )
