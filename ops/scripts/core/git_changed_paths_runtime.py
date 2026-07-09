from __future__ import annotations

import re
import stat as stat_module
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .command_runtime import RunWithTimeoutRequest, run_with_timeout
from .git_runtime import resolve_trusted_git_executable, trusted_git_subprocess_env

_GitFailure = dict[str, Any]

GIT_LS_FILES_DEBUG_RE = re.compile(
    r"^  ctime: (?P<ctime_s>\d+):(?P<ctime_ns>\d+)\n"
    r"  mtime: (?P<mtime_s>\d+):(?P<mtime_ns>\d+)\n"
    r"  dev: (?P<dev>\d+)\tino: (?P<ino>\d+)\n"
    r"  uid: (?P<uid>\d+)\tgid: (?P<gid>\d+)\n"
    r"  size: (?P<size>\d+)\tflags: (?P<flags>[0-9a-fA-F]+)\n"
)
GIT_OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
GIT_INDEX_INTENT_TO_ADD_FLAG = 0x20000000
GIT_CHANGED_PATHS_TIMEOUT_SECONDS = 30
GIT_SYMBOLIC_REF_MAX_DEPTH = 8
SUBMODULE_IGNORE_MODES = {"all", "dirty", "untracked", "none"}
GIT_BASE_CONFIG_ARGS = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
)


@dataclass(frozen=True)
class _GitCommandObservation:
    command_id: str
    status: str
    returncode: int
    timed_out: bool
    path_count: int = 0
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.command_id,
            "status": self.status,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "path_count": self.path_count,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class _GitChangedPathsResult:
    paths: list[str]
    diagnostics: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.diagnostics.get("status") in {
            "failed",
            "timed_out",
            "unavailable",
        }


@dataclass(frozen=True)
class _GitIndexEntry:
    mode: str
    object_id: str
    rel_path: str


@dataclass(frozen=True)
class _TrackedFilterContext:
    config_env: dict[str, str]
    filtered_paths: set[str]
    gitlink_paths: set[str]
    index_debug_stdout: str


@dataclass(frozen=True)
class _GitlinkScanResult:
    paths: list[str]
    commands: list[_GitCommandObservation]
    failures: list[_GitFailure]
    ignored_all_paths: set[str]


@dataclass(frozen=True)
class _GitChangedPathsScanResult:
    paths: list[str]
    commands: list[_GitCommandObservation]
    failures: list[_GitFailure]
    skip_reason: str = ""


def _git_changed_paths_diagnostics(
    *,
    status: str,
    source: str,
    path_count: int = 0,
    reason: str = "",
    commands: list[_GitCommandObservation] | None = None,
    failures: list[_GitFailure] | None = None,
    ignored_path_entry_count: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "source": source,
        "path_count": path_count,
        "commands": [command.to_payload() for command in commands or []],
        "failures": failures or [],
        "ignored_path_entry_count": ignored_path_entry_count,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _skipped_git_changed_paths(
    reason: str,
    *,
    source: str = "none",
    commands: list[_GitCommandObservation] | None = None,
    ignored_path_entry_count: int = 0,
) -> _GitChangedPathsResult:
    return _GitChangedPathsResult(
        paths=[],
        diagnostics=_git_changed_paths_diagnostics(
            status="skipped",
            source=source,
            reason=reason,
            commands=commands,
            ignored_path_entry_count=ignored_path_entry_count,
        ),
    )


def _split_nul_paths(stdout: str) -> list[str]:
    return [item for item in stdout.split("\0") if item]


def _hidden_index_paths_from_ls_files_verbose(stdout: str) -> set[str]:
    paths: set[str] = set()
    for record in _split_nul_paths(stdout):
        flag = record[:1]
        _flag, separator, rel_path = record.partition(" ")
        if separator and (flag.islower() or flag == "S"):
            paths.add(rel_path)
    return paths


def _run_git_raw_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    command_id: str,
    args: list[str],
    input_text: str | None = None,
) -> tuple[str, _GitCommandObservation, _GitFailure | None]:
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[git_executable, *GIT_BASE_CONFIG_ARGS, *args],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
            input_text=input_text,
        )
    )
    if result.timed_out:
        observation = _GitCommandObservation(
            command_id=command_id,
            status="timed_out",
            returncode=result.returncode,
            timed_out=True,
            reason="git_probe_timed_out",
        )
        return "", observation, {
            "command_id": command_id,
            "code": "git_probe_timed_out",
        }
    if result.returncode != 0:
        observation = _GitCommandObservation(
            command_id=command_id,
            status="failed",
            returncode=result.returncode,
            timed_out=False,
            reason="git_probe_failed",
        )
        return "", observation, {
            "command_id": command_id,
            "code": "git_probe_failed",
        }
    return (
        result.stdout,
        _GitCommandObservation(
            command_id=command_id,
            status="pass",
            returncode=result.returncode,
            timed_out=False,
        ),
        None,
    )


def _run_git_changed_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    command_id: str,
    args: list[str],
) -> tuple[list[str], _GitCommandObservation, _GitFailure | None]:
    stdout, observation, failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id=command_id,
        args=args,
    )
    if failure is not None:
        return [], observation, failure
    paths = _split_nul_paths(stdout)
    return (
        paths,
        _GitCommandObservation(
            command_id=observation.command_id,
            status=observation.status,
            returncode=observation.returncode,
            timed_out=observation.timed_out,
            path_count=len(paths),
            reason=observation.reason,
        ),
        None,
    )


def _run_git_hidden_index_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[set[str], _GitCommandObservation, _GitFailure | None]:
    stdout, observation, failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="ls-files-index-flags",
        args=["ls-files", "-z", "-v"],
    )
    if failure is not None:
        return set(), observation, failure
    paths = _hidden_index_paths_from_ls_files_verbose(stdout)
    return (
        paths,
        _GitCommandObservation(
            command_id=observation.command_id,
            status=observation.status,
            returncode=observation.returncode,
            timed_out=observation.timed_out,
            path_count=len(paths),
            reason=observation.reason,
        ),
        None,
    )


def _run_git_optional_config_raw(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    args: list[str],
) -> str:
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[git_executable, *GIT_BASE_CONFIG_ARGS, "config", *args],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
        )
    )
    if result.timed_out or result.returncode not in {0, 1}:
        return ""
    return result.stdout


def _run_git_optional_config(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    args: list[str],
) -> str:
    return _run_git_optional_config_raw(
        vault=vault,
        git_executable=git_executable,
        env=env,
        args=args,
    ).strip()


def _submodule_names_by_path_from_config_stdout(stdout: str) -> dict[str, str]:
    names_by_path: dict[str, str] = {}
    for record in _split_nul_paths(stdout):
        key, separator, rel_path = record.partition("\n")
        if not separator:
            continue
        prefix = "submodule."
        suffix = ".path"
        if key.startswith(prefix) and key.endswith(suffix):
            names_by_path[rel_path] = key[len(prefix) : -len(suffix)]
    return names_by_path


def _stderr_indicates_missing_worktree(stderr: str) -> bool:
    normalized = stderr.lower()
    return "not a git repository" in normalized or "not a git repo" in normalized


def _git_worktree_exists(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, _GitCommandObservation, _GitFailure | None]:
    command_id = "rev-parse-worktree"
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[
                git_executable,
                *GIT_BASE_CONFIG_ARGS,
                "rev-parse",
                "--is-inside-work-tree",
            ],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
        )
    )
    if result.timed_out:
        return (
            False,
            _GitCommandObservation(
                command_id=command_id,
                status="timed_out",
                returncode=result.returncode,
                timed_out=True,
                reason="git_probe_timed_out",
            ),
            {"command_id": command_id, "code": "git_probe_timed_out"},
        )
    if result.returncode == 0 and result.stdout.strip() == "true":
        return (
            True,
            _GitCommandObservation(
                command_id=command_id,
                status="pass",
                returncode=result.returncode,
                timed_out=False,
            ),
            None,
        )
    if result.returncode == 0 or _stderr_indicates_missing_worktree(result.stderr):
        return (
            False,
            _GitCommandObservation(
                command_id=command_id,
                status="not_worktree",
                returncode=result.returncode,
                timed_out=False,
                reason="git_worktree_missing",
            ),
            None,
        )
    return (
        False,
        _GitCommandObservation(
            command_id=command_id,
            status="failed",
            returncode=result.returncode,
            timed_out=False,
            reason="git_probe_failed",
        ),
        {"command_id": command_id, "code": "git_probe_failed"},
    )


def _git_index_entry(record: str) -> _GitIndexEntry | None:
    header, separator, rel_path = record.partition("\t")
    if not separator:
        return None
    parts = header.split()
    if len(parts) != 3:
        return None
    mode, object_id, stage = parts
    if not re.fullmatch(r"\d{6}", mode):
        return None
    if not GIT_OBJECT_ID_RE.fullmatch(object_id):
        return None
    if not stage.isdigit():
        return None
    return _GitIndexEntry(
        mode=mode,
        object_id=object_id.lower(),
        rel_path=rel_path,
    )


def _ls_files_stage_debug_records(
    stdout: str,
) -> list[tuple[_GitIndexEntry, re.Match[str]]]:
    segments = stdout.split("\0")
    if not segments:
        return []
    stage_record = segments[0]
    records: list[tuple[_GitIndexEntry, re.Match[str]]] = []
    for segment in segments[1:]:
        if not stage_record:
            break
        entry = _git_index_entry(stage_record)
        if entry is None:
            break
        match = GIT_LS_FILES_DEBUG_RE.match(segment)
        if match is None:
            break
        records.append((entry, match))
        stage_record = segment[match.end() :]
    return records


def _gitlink_entries_from_ls_files_stage(stdout: str) -> dict[str, _GitIndexEntry]:
    entries: dict[str, _GitIndexEntry] = {}
    for record in _split_nul_paths(stdout):
        entry = _git_index_entry(record)
        if entry is None or entry.mode != "160000":
            continue
        entries[entry.rel_path] = entry
    return entries


def _filter_driver_paths_from_check_attr(stdout: str) -> dict[str, str]:
    fields = stdout.split("\0")
    drivers_by_path: dict[str, str] = {}
    for index in range(0, len(fields) - 2, 3):
        path = fields[index]
        attr = fields[index + 1]
        value = fields[index + 2]
        if attr != "filter" or value in {"", "unspecified", "unset", "set"}:
            continue
        drivers_by_path[path] = value
    return drivers_by_path


def _safe_filter_driver_config_env(filter_names: set[str]) -> dict[str, str] | None:
    config_env: dict[str, str] = {}
    config_index = 0
    for name in sorted(filter_names):
        if not name or any(char in name for char in "\0\r\n"):
            return None
        for suffix, value in (
            ("clean", ""),
            ("process", ""),
            ("required", "false"),
        ):
            config_env[f"GIT_CONFIG_KEY_{config_index}"] = f"filter.{name}.{suffix}"
            config_env[f"GIT_CONFIG_VALUE_{config_index}"] = value
            config_index += 1
    if config_index:
        config_env["GIT_CONFIG_COUNT"] = str(config_index)
    return config_env


def _index_time_ns(match: re.Match[str], prefix: str) -> int:
    return int(match.group(f"{prefix}_s")) * 1_000_000_000 + int(
        match.group(f"{prefix}_ns")
    )


def _git_mode_from_lstat_mode(mode: int) -> str | None:
    if stat_module.S_ISLNK(mode):
        return "120000"
    if stat_module.S_ISREG(mode):
        return "100755" if mode & 0o111 else "100644"
    return None


def _git_core_filemode(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> bool:
    value = _run_git_optional_config(
        vault=vault,
        git_executable=git_executable,
        env=env,
        args=["--bool", "core.fileMode"],
    ).lower()
    return value != "false"


def _index_entry_stat_changed(
    *,
    vault: Path,
    entry: _GitIndexEntry,
    match: re.Match[str],
    core_filemode: bool,
) -> bool:
    try:
        stat_result = (vault / entry.rel_path).lstat()
    except OSError:
        return False
    if core_filemode:
        worktree_mode = _git_mode_from_lstat_mode(stat_result.st_mode)
        if entry.mode not in {"160000", worktree_mode}:
            return True
    return any(
        (
            stat_result.st_size != int(match.group("size")),
            stat_result.st_mtime_ns != _index_time_ns(match, "mtime"),
            stat_result.st_ctime_ns != _index_time_ns(match, "ctime"),
            stat_result.st_dev != int(match.group("dev")),
            stat_result.st_ino != int(match.group("ino")),
        )
    )


def _filtered_paths_requiring_filter_driver(
    *,
    vault: Path,
    stdout: str,
    filtered_paths: set[str],
    core_filemode: bool,
) -> list[str]:
    paths: list[str] = []
    for entry, match in _ls_files_stage_debug_records(stdout):
        if entry.rel_path not in filtered_paths:
            continue
        flags = int(match.group("flags"), 16)
        if flags != 0:
            continue
        if _index_entry_stat_changed(
            vault=vault,
            entry=entry,
            match=match,
            core_filemode=core_filemode,
        ):
            paths.append(entry.rel_path)
    return paths


def _filtered_intent_to_add_paths(
    *,
    stdout: str,
    filtered_paths: set[str],
) -> list[str]:
    paths: list[str] = []
    for entry, match in _ls_files_stage_debug_records(stdout):
        if entry.rel_path not in filtered_paths:
            continue
        flags = int(match.group("flags"), 16)
        if flags & GIT_INDEX_INTENT_TO_ADD_FLAG:
            paths.append(entry.rel_path)
    return paths


def _tracked_filter_context(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[_TrackedFilterContext, _GitFailure | None]:
    paths_stdout, _paths_observation, paths_failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="ls-files-filter-paths",
        args=["ls-files", "-z", "-s", "--debug"],
    )
    if paths_failure is not None:
        return _TrackedFilterContext({}, set(), set(), ""), paths_failure
    entries = [entry for entry, _match in _ls_files_stage_debug_records(paths_stdout)]
    paths = [entry.rel_path for entry in entries]
    if not paths:
        return _TrackedFilterContext({}, set(), set(), paths_stdout), None
    attr_stdout, _attr_observation, attr_failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="check-attr-filter",
        args=["check-attr", "-z", "--stdin", "filter"],
        input_text="\0".join(paths) + "\0",
    )
    if attr_failure is not None:
        return _TrackedFilterContext({}, set(), set(), paths_stdout), attr_failure
    drivers_by_path = _filter_driver_paths_from_check_attr(attr_stdout)
    config_env = _safe_filter_driver_config_env(set(drivers_by_path.values()))
    if config_env is None:
        return _TrackedFilterContext({}, set(), set(), paths_stdout), {
            "command_id": "check-attr-filter",
            "code": "git_probe_failed",
        }
    gitlink_paths = {entry.rel_path for entry in entries if entry.mode == "160000"}
    return (
        _TrackedFilterContext(
            config_env=config_env,
            filtered_paths=set(drivers_by_path),
            gitlink_paths=gitlink_paths,
            index_debug_stdout=paths_stdout,
        ),
        None,
    )


def _git_dir_from_marker(marker: Path) -> Path | None:
    try:
        if marker.is_symlink():
            return None
        if marker.is_dir():
            return marker.resolve()
        if not marker.is_file():
            return None
        first_line = marker.read_text(encoding="utf-8", errors="replace").splitlines()[
            0:1
        ]
    except OSError:
        return None
    if not first_line:
        return None
    prefix, separator, raw_git_dir = first_line[0].partition(":")
    if prefix.strip().lower() != "gitdir" or not separator:
        return None
    try:
        return (marker.parent / raw_git_dir.strip()).resolve()
    except OSError:
        return None


def _submodule_git_dir_is_allowed(vault: Path, rel_path: str, git_dir: Path) -> bool:
    submodule_root = vault / rel_path
    storage_root = _git_dir_from_marker(vault / ".git")
    if storage_root is not None:
        try:
            git_dir.relative_to(storage_root)
            return True
        except ValueError:
            pass
    try:
        git_dir.relative_to(submodule_root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _submodule_git_dir(vault: Path, rel_path: str) -> Path | None:
    git_dir = _git_dir_from_marker(vault / rel_path / ".git")
    if git_dir is None:
        return None
    if not _submodule_git_dir_is_allowed(vault, rel_path, git_dir):
        return None
    return git_dir


def _submodule_external_git_dir(vault: Path, rel_path: str) -> Path | None:
    git_dir = _git_dir_from_marker(vault / rel_path / ".git")
    if git_dir is None:
        return None
    if _submodule_git_dir_is_allowed(vault, rel_path, git_dir):
        return None
    return git_dir


def _external_git_dir_points_to_worktree_marker(
    *,
    vault: Path,
    rel_path: str,
    git_dir: Path,
) -> bool:
    try:
        marker_path = (vault / rel_path / ".git").resolve()
        backlink = (git_dir / "gitdir").read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()
        backlink_path = (git_dir / backlink).resolve()
    except OSError:
        return False
    return backlink_path == marker_path


def _read_packed_git_ref(git_dir: Path, ref_name: str) -> str | None:
    try:
        git_dir_root = git_dir.resolve()
        packed_refs_path = (git_dir_root / "packed-refs").resolve()
        packed_refs_path.relative_to(git_dir_root)
        lines = packed_refs_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        if not line or line.startswith(("#", "^")):
            continue
        object_id, separator, name = line.partition(" ")
        if separator and name == ref_name and GIT_OBJECT_ID_RE.fullmatch(object_id):
            return object_id.lower()
    return None


def _git_common_dir(git_dir_root: Path) -> Path:
    try:
        commondir_path = (git_dir_root / "commondir").resolve()
        commondir_path.relative_to(git_dir_root)
        raw_common_dir = commondir_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()
    except (OSError, ValueError):
        return git_dir_root
    if not raw_common_dir:
        return git_dir_root
    try:
        return (git_dir_root / raw_common_dir).resolve()
    except OSError:
        return git_dir_root


def _git_ref_roots(git_dir_root: Path) -> list[Path]:
    common_dir = _git_common_dir(git_dir_root)
    if common_dir == git_dir_root:
        return [git_dir_root]
    return [git_dir_root, common_dir]


def _read_loose_git_ref_value(git_dir: Path, ref_name: str) -> str | None:
    try:
        git_dir_root = git_dir.resolve()
        ref_path = (git_dir_root / ref_name).resolve()
        ref_path.relative_to(git_dir_root)
        return ref_path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, ValueError):
        return None


def _resolve_git_ref(
    ref_roots: list[Path],
    ref_name: str,
    *,
    seen: frozenset[str] = frozenset(),
) -> str | None:
    if ref_name in seen or len(seen) >= GIT_SYMBOLIC_REF_MAX_DEPTH:
        return None
    next_seen = frozenset({*seen, ref_name})
    for ref_root in ref_roots:
        ref_value = _read_loose_git_ref_value(ref_root, ref_name)
        if ref_value is None:
            continue
        if GIT_OBJECT_ID_RE.fullmatch(ref_value):
            return ref_value.lower()
        prefix, separator, next_ref_name = ref_value.partition(":")
        if prefix == "ref" and separator:
            return _resolve_git_ref(
                ref_roots,
                next_ref_name.strip(),
                seen=next_seen,
            )
        return None
    for ref_root in ref_roots:
        ref_value = _read_packed_git_ref(ref_root, ref_name)
        if ref_value is not None:
            return ref_value
    return None


def _read_git_dir_head(git_dir: Path) -> str | None:
    try:
        git_dir_root = git_dir.resolve()
        head_path = (git_dir_root / "HEAD").resolve()
        head_path.relative_to(git_dir_root)
        head = head_path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, ValueError):
        return None
    if GIT_OBJECT_ID_RE.fullmatch(head):
        return head.lower()
    prefix, separator, ref_name = head.partition(":")
    if prefix != "ref" or not separator:
        return None
    ref_name = ref_name.strip()
    return _resolve_git_ref(_git_ref_roots(git_dir_root), ref_name)


def _submodule_command_id(rel_path: str, command_id: str) -> str:
    return f"submodule:{rel_path}:{command_id}"


def _submodule_observation(
    rel_path: str,
    observation: _GitCommandObservation,
) -> _GitCommandObservation:
    return _GitCommandObservation(
        command_id=_submodule_command_id(rel_path, observation.command_id),
        status=observation.status,
        returncode=observation.returncode,
        timed_out=observation.timed_out,
        path_count=observation.path_count,
        reason=observation.reason,
    )


def _submodule_failure(rel_path: str, failure: _GitFailure) -> _GitFailure:
    payload = dict(failure)
    payload["command_id"] = _submodule_command_id(
        rel_path,
        str(failure.get("command_id", "git-probe")),
    )
    return payload


def _submodule_names_by_path(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> dict[str, str]:
    gitmodules_stdout = _run_git_optional_config_raw(
        vault=vault,
        git_executable=git_executable,
        env=env,
        args=["-z", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"],
    )
    names_by_path = _submodule_names_by_path_from_config_stdout(gitmodules_stdout)
    local_stdout = _run_git_optional_config_raw(
        vault=vault,
        git_executable=git_executable,
        env=env,
        args=["-z", "--get-regexp", r"^submodule\..*\.path$"],
    )
    for rel_path, name in _submodule_names_by_path_from_config_stdout(local_stdout).items():
        names_by_path.setdefault(rel_path, name)
    return names_by_path


def _submodule_ignore_mode(
    *,
    vault: Path,
    entry: _GitIndexEntry,
    git_executable: str,
    env: dict[str, str],
) -> str:
    name = _submodule_names_by_path(
        vault=vault,
        git_executable=git_executable,
        env=env,
    ).get(entry.rel_path, entry.rel_path)
    config_key = f"submodule.{name}.ignore"
    for args in (
        ["--get", config_key],
        ["--file", ".gitmodules", "--get", config_key],
    ):
        value = _run_git_optional_config(
            vault=vault,
            git_executable=git_executable,
            env=env,
            args=args,
        ).lower()
        if value in SUBMODULE_IGNORE_MODES:
            return value
    diff_ignore = _run_git_optional_config(
        vault=vault,
        git_executable=git_executable,
        env=env,
        args=["--get", "diff.ignoreSubmodules"],
    ).lower()
    if diff_ignore in SUBMODULE_IGNORE_MODES:
        return diff_ignore
    return "untracked"


def _submodule_worktree_dirty(
    *,
    vault: Path,
    entry: _GitIndexEntry,
    git_executable: str,
    env: dict[str, str],
    ignore_untracked: bool,
) -> tuple[bool, list[_GitCommandObservation], list[_GitFailure]]:
    submodule_root = vault / entry.rel_path
    if not submodule_root.is_dir():
        return False, [], []
    commands: list[_GitCommandObservation] = []
    failures: list[_GitFailure] = []
    hidden_index_paths, hidden_observation, hidden_failure = _run_git_hidden_index_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
    )
    commands.append(_submodule_observation(entry.rel_path, hidden_observation))
    if hidden_failure is not None:
        failures.append(_submodule_failure(entry.rel_path, hidden_failure))
        return False, commands, failures
    worktree_args = ["ls-files", "-z", "-d"]
    if not ignore_untracked:
        worktree_args.extend(["-o", "--exclude-standard"])
    worktree_paths, worktree_observation, worktree_failure = _run_git_changed_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        command_id=_submodule_command_id(entry.rel_path, "ls-files-worktree"),
        args=worktree_args,
    )
    commands.append(worktree_observation)
    if worktree_failure is not None:
        failures.append(worktree_failure)
        return False, commands, failures
    worktree_paths = [
        path for path in worktree_paths if path not in hidden_index_paths
    ]
    modified_paths, modified_observation, modified_failure = _run_git_modified_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        command_id=_submodule_command_id(entry.rel_path, "ls-files-modified"),
    )
    commands.append(modified_observation)
    filtered_driver_dirty = False
    if modified_failure is not None:
        if modified_failure.get("code") == "filtered_path_requires_filter_driver":
            filtered_driver_dirty = True
        else:
            failures.append(modified_failure)
            return False, commands, failures
    modified_paths = [
        path for path in modified_paths if path not in hidden_index_paths
    ]
    nested_result = _run_git_submodule_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        hidden_index_paths=hidden_index_paths,
    )
    commands.extend(
        _submodule_observation(entry.rel_path, command)
        for command in nested_result.commands
    )
    failures.extend(
        _submodule_failure(entry.rel_path, failure)
        for failure in nested_result.failures
    )
    if failures:
        return False, commands, failures
    has_head, head_observation, head_failure = _git_head_exists(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
    )
    commands.append(_submodule_observation(entry.rel_path, head_observation))
    if head_failure is not None:
        failures.append(_submodule_failure(entry.rel_path, head_failure))
        return False, commands, failures
    if has_head:
        staged_args = ["diff", "--cached", "-z", "--name-only", "HEAD", "--"]
        staged_command_id = "diff-cached"
    elif ignore_untracked:
        staged_args = ["ls-files", "-z", "--cached"]
        staged_command_id = "ls-files-no-head"
    else:
        staged_args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        staged_command_id = "ls-files-no-head"
    staged_paths, staged_observation, staged_failure = _run_git_changed_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        command_id=_submodule_command_id(entry.rel_path, staged_command_id),
        args=staged_args,
    )
    commands.append(staged_observation)
    if staged_failure is not None:
        failures.append(staged_failure)
        return False, commands, failures
    return (
        bool(
            worktree_paths
            or modified_paths
            or filtered_driver_dirty
            or nested_result.paths
            or staged_paths
        ),
        commands,
        failures,
    )


def _submodule_worktree_type_changed(vault: Path, rel_path: str) -> bool:
    try:
        worktree_mode = (vault / rel_path).lstat().st_mode
    except OSError:
        return False
    return stat_module.S_ISLNK(worktree_mode) or not stat_module.S_ISDIR(worktree_mode)


def _submodule_changed(
    *,
    vault: Path,
    entry: _GitIndexEntry,
    ignore_mode: str,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, list[_GitCommandObservation], list[_GitFailure]]:
    if ignore_mode == "all":
        return False, [], []
    if _submodule_worktree_type_changed(vault, entry.rel_path):
        return True, [], []
    git_dir = _submodule_git_dir(vault, entry.rel_path)
    if git_dir is None:
        external_git_dir = _submodule_external_git_dir(vault, entry.rel_path)
        if external_git_dir is None:
            return False, [], []
        if not _external_git_dir_points_to_worktree_marker(
            vault=vault,
            rel_path=entry.rel_path,
            git_dir=external_git_dir,
        ):
            return True, [], []
        current_external_head = _read_git_dir_head(external_git_dir)
        head_changed = (
            current_external_head is None or current_external_head != entry.object_id
        )
        if ignore_mode == "dirty":
            return head_changed, [], []
        dirty, commands, failures = _submodule_worktree_dirty(
            vault=vault,
            entry=entry,
            git_executable=git_executable,
            env=env,
            ignore_untracked=ignore_mode == "untracked",
        )
        return head_changed or dirty, commands, failures
    current_head = _read_git_dir_head(git_dir)
    head_changed = current_head is None or current_head != entry.object_id
    if ignore_mode == "dirty":
        return head_changed, [], []
    dirty, commands, failures = _submodule_worktree_dirty(
        vault=vault,
        entry=entry,
        git_executable=git_executable,
        env=env,
        ignore_untracked=ignore_mode == "untracked",
    )
    return head_changed or dirty, commands, failures


def _submodule_changed_paths(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    stdout: str,
    hidden_index_paths: set[str],
) -> tuple[list[str], list[_GitCommandObservation], list[_GitFailure], set[str]]:
    paths: list[str] = []
    commands: list[_GitCommandObservation] = []
    failures: list[_GitFailure] = []
    ignored_all_paths: set[str] = set()
    for entry in _gitlink_entries_from_ls_files_stage(stdout).values():
        if entry.rel_path in hidden_index_paths:
            continue
        ignore_mode = _submodule_ignore_mode(
            vault=vault,
            entry=entry,
            git_executable=git_executable,
            env=env,
        )
        if ignore_mode == "all":
            ignored_all_paths.add(entry.rel_path)
        changed, submodule_commands, submodule_failures = _submodule_changed(
            vault=vault,
            entry=entry,
            ignore_mode=ignore_mode,
            git_executable=git_executable,
            env=env,
        )
        commands.extend(submodule_commands)
        failures.extend(submodule_failures)
        if changed:
            paths.append(entry.rel_path)
    return paths, commands, failures, ignored_all_paths


def _run_git_submodule_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    hidden_index_paths: set[str] | None = None,
) -> _GitlinkScanResult:
    stdout, observation, failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="ls-files-gitlinks",
        args=["ls-files", "-z", "-s"],
    )
    if failure is not None:
        return _GitlinkScanResult([], [observation], [failure], set())
    paths, commands, failures, ignored_all_paths = _submodule_changed_paths(
        vault=vault,
        git_executable=git_executable,
        env=env,
        stdout=stdout,
        hidden_index_paths=hidden_index_paths or set(),
    )
    return _GitlinkScanResult(
        paths=paths,
        commands=[
            _GitCommandObservation(
                command_id=observation.command_id,
                status=observation.status,
                returncode=observation.returncode,
                timed_out=observation.timed_out,
                path_count=len(paths),
                reason=observation.reason,
            ),
            *commands,
        ],
        failures=failures,
        ignored_all_paths=ignored_all_paths,
    )


def _run_git_modified_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    command_id: str = "ls-files-modified",
) -> tuple[list[str], _GitCommandObservation, _GitFailure | None]:
    filter_context, filter_failure = _tracked_filter_context(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    if filter_failure is not None:
        return (
            [],
            _GitCommandObservation(
                command_id=command_id,
                status="failed",
                returncode=1,
                timed_out=False,
                reason="git_probe_failed",
            ),
            {"command_id": command_id, "code": str(filter_failure["code"])},
        )
    paths, observation, failure = _run_git_changed_paths_command(
        vault=vault,
        git_executable=git_executable,
        env={**env, **filter_context.config_env},
        command_id=command_id,
        args=["ls-files", "-z", "-m"],
    )
    if failure is not None:
        return paths, observation, failure
    excluded_paths = filter_context.gitlink_paths | filter_context.filtered_paths
    intent_to_add_paths = _filtered_intent_to_add_paths(
        stdout=filter_context.index_debug_stdout,
        filtered_paths=filter_context.filtered_paths - filter_context.gitlink_paths,
    )
    filter_driver_required_paths = _filtered_paths_requiring_filter_driver(
        vault=vault,
        stdout=filter_context.index_debug_stdout,
        filtered_paths=filter_context.filtered_paths - filter_context.gitlink_paths,
        core_filemode=_git_core_filemode(
            vault=vault,
            git_executable=git_executable,
            env=env,
        ),
    )
    detected_paths = sorted(
        {
            path
            for path in paths
            if path not in excluded_paths
        }
        | set(intent_to_add_paths)
    )
    if filter_driver_required_paths:
        return (
            detected_paths,
            _GitCommandObservation(
                command_id=observation.command_id,
                status=observation.status,
                returncode=observation.returncode,
                timed_out=observation.timed_out,
                path_count=len(detected_paths),
                reason=observation.reason,
            ),
            {
                "command_id": command_id,
                "code": "filtered_path_requires_filter_driver",
                "paths": filter_driver_required_paths,
            },
        )
    return (
        detected_paths,
        _GitCommandObservation(
            command_id=observation.command_id,
            status=observation.status,
            returncode=observation.returncode,
            timed_out=observation.timed_out,
            path_count=len(detected_paths),
            reason=observation.reason,
        ),
        None,
    )


def _git_head_exists(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, _GitCommandObservation, _GitFailure | None]:
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[
                git_executable,
                *GIT_BASE_CONFIG_ARGS,
                "rev-parse",
                "--verify",
                "--quiet",
                "HEAD",
            ],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
        )
    )
    if result.timed_out:
        observation = _GitCommandObservation(
            command_id="rev-parse-head",
            status="timed_out",
            returncode=result.returncode,
            timed_out=True,
            reason="git_probe_timed_out",
        )
        return False, observation, {
            "command_id": "rev-parse-head",
            "code": "git_probe_timed_out",
        }
    if result.returncode == 0:
        return (
            True,
            _GitCommandObservation(
                command_id="rev-parse-head",
                status="pass",
                returncode=result.returncode,
                timed_out=False,
            ),
            None,
        )
    if result.returncode == 1:
        return (
            False,
            _GitCommandObservation(
                command_id="rev-parse-head",
                status="no_head",
                returncode=result.returncode,
                timed_out=False,
                reason="git_head_missing",
            ),
            None,
        )
    observation = _GitCommandObservation(
        command_id="rev-parse-head",
        status="failed",
        returncode=result.returncode,
        timed_out=False,
        reason="git_probe_failed",
    )
    return False, observation, {
        "command_id": "rev-parse-head",
        "code": "git_probe_failed",
    }


def _failed_git_changed_paths_result(
    *,
    paths: list[str],
    commands: list[_GitCommandObservation],
    failures: list[_GitFailure],
    ignored_path_entry_count: int,
) -> _GitChangedPathsResult:
    unique_paths = sorted(set(paths))
    failed_statuses = {command.status for command in commands if command.status != "pass"}
    status = "timed_out" if "timed_out" in failed_statuses else "failed"
    failure_codes = {failure["code"] for failure in failures}
    reason = (
        next(iter(failure_codes))
        if len(failure_codes) == 1
        else "git_probe_failed"
    )
    return _GitChangedPathsResult(
        paths=unique_paths,
        diagnostics=_git_changed_paths_diagnostics(
            status=status,
            source="git",
            path_count=len(unique_paths),
            reason=reason,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        ),
    )


def _read_unstaged_root_paths(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    hidden_index_paths: set[str],
) -> _GitChangedPathsScanResult:
    commands: list[_GitCommandObservation] = []
    failures: list[_GitFailure] = []
    paths: list[str] = []
    worktree_paths, worktree_observation, worktree_failure = _run_git_changed_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="ls-files-worktree",
        args=["ls-files", "-z", "-d", "-o", "--exclude-standard"],
    )
    commands.append(worktree_observation)
    if worktree_failure is not None:
        failures.append(worktree_failure)
    paths.extend(path for path in worktree_paths if path not in hidden_index_paths)
    if failures:
        return _GitChangedPathsScanResult(
            paths=paths,
            commands=commands,
            failures=failures,
        )

    modified_paths, modified_observation, modified_failure = _run_git_modified_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.append(modified_observation)
    if modified_failure is not None:
        failures.append(modified_failure)
    paths.extend(path for path in modified_paths if path not in hidden_index_paths)
    return _GitChangedPathsScanResult(
        paths=paths,
        commands=commands,
        failures=failures,
    )


def _read_staged_root_paths(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> _GitChangedPathsScanResult:
    commands: list[_GitCommandObservation] = []
    failures: list[_GitFailure] = []
    has_head, head_observation, head_failure = _git_head_exists(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.append(head_observation)
    if head_failure is not None:
        failures.append(head_failure)
        return _GitChangedPathsScanResult(
            paths=[],
            commands=commands,
            failures=failures,
        )
    if has_head:
        staged_args = ["diff", "--cached", "-z", "--name-only", "HEAD", "--"]
        command_id = "diff-cached"
    else:
        staged_args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        command_id = "ls-files-no-head"
    staged_paths, staged_observation, staged_failure = _run_git_changed_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id=command_id,
        args=staged_args,
    )
    commands.append(staged_observation)
    if staged_failure is not None:
        failures.append(staged_failure)
    return _GitChangedPathsScanResult(
        paths=staged_paths,
        commands=commands,
        failures=failures,
    )


def _scan_root_git_changed_paths(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> _GitChangedPathsScanResult:
    commands: list[_GitCommandObservation] = []
    failures: list[_GitFailure] = []
    paths: list[str] = []
    has_worktree, worktree_probe, worktree_probe_failure = _git_worktree_exists(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.append(worktree_probe)
    if worktree_probe_failure is not None:
        failures.append(worktree_probe_failure)
        return _GitChangedPathsScanResult(
            paths=paths,
            commands=commands,
            failures=failures,
        )
    if not has_worktree:
        return _GitChangedPathsScanResult(
            paths=paths,
            commands=commands,
            failures=failures,
            skip_reason="git_worktree_missing",
        )

    hidden_index_paths, hidden_index_observation, hidden_index_failure = (
        _run_git_hidden_index_paths_command(
            vault=vault,
            git_executable=git_executable,
            env=env,
        )
    )
    commands.append(hidden_index_observation)
    if hidden_index_failure is not None:
        failures.append(hidden_index_failure)
        return _GitChangedPathsScanResult(
            paths=paths,
            commands=commands,
            failures=failures,
        )

    unstaged_result = _read_unstaged_root_paths(
        vault=vault,
        git_executable=git_executable,
        env=env,
        hidden_index_paths=hidden_index_paths,
    )
    commands.extend(unstaged_result.commands)
    failures.extend(unstaged_result.failures)
    paths.extend(unstaged_result.paths)
    if failures:
        return _GitChangedPathsScanResult(
            paths=paths,
            commands=commands,
            failures=failures,
        )

    submodule_result = _run_git_submodule_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        hidden_index_paths=hidden_index_paths,
    )
    commands.extend(submodule_result.commands)
    failures.extend(submodule_result.failures)
    paths = [
        path for path in paths if path not in submodule_result.ignored_all_paths
    ]
    paths.extend(submodule_result.paths)
    if failures:
        return _GitChangedPathsScanResult(
            paths=paths,
            commands=commands,
            failures=failures,
        )

    staged_result = _read_staged_root_paths(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.extend(staged_result.commands)
    failures.extend(staged_result.failures)
    paths.extend(staged_result.paths)
    return _GitChangedPathsScanResult(
        paths=paths,
        commands=commands,
        failures=failures,
    )


def _read_git_changed_paths(vault: Path) -> _GitChangedPathsResult:
    if not (vault / ".git").exists():
        return _skipped_git_changed_paths("source_package_without_git")
    git_executable, path_text, ignored_path_entry_count = resolve_trusted_git_executable(
        vault
    )
    if git_executable is None:
        return _GitChangedPathsResult(
            paths=[],
            diagnostics=_git_changed_paths_diagnostics(
                status="unavailable",
                source="git",
                reason="git_executable_unavailable",
                failures=[{"code": "git_executable_unavailable"}],
                ignored_path_entry_count=ignored_path_entry_count,
            ),
        )
    env = trusted_git_subprocess_env(path_text)
    scan_result = _scan_root_git_changed_paths(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    if scan_result.skip_reason:
        return _skipped_git_changed_paths(
            scan_result.skip_reason,
            source="git",
            commands=scan_result.commands,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    if scan_result.failures:
        return _failed_git_changed_paths_result(
            paths=scan_result.paths,
            commands=scan_result.commands,
            failures=scan_result.failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    unique_paths = sorted(set(scan_result.paths))
    return _GitChangedPathsResult(
        paths=unique_paths,
        diagnostics=_git_changed_paths_diagnostics(
            status="pass",
            source="git",
            path_count=len(unique_paths),
            commands=scan_result.commands,
            ignored_path_entry_count=ignored_path_entry_count,
        ),
    )




GitChangedPathsResult = _GitChangedPathsResult


def skipped_git_changed_paths(
    reason: str,
    *,
    source: str = "none",
    ignored_path_entry_count: int = 0,
) -> GitChangedPathsResult:
    return _skipped_git_changed_paths(
        reason,
        source=source,
        ignored_path_entry_count=ignored_path_entry_count,
    )


def read_git_changed_paths(vault: Path) -> GitChangedPathsResult:
    return _read_git_changed_paths(vault)
