from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from .command_runtime import TimedProcessResult, run_with_timeout

BWRAP = Path("/usr/bin/bwrap")
SANDBOX_TMP_BYTES = 64 * 1024 * 1024
SYSTEM_RUNTIME_PATHS = ("/usr", "/bin", "/sbin", "/lib", "/lib64")

# Capture the running controller's runtime before a candidate can change its
# interpreter links. Request paths are aliases, never authority for host mounts.
LAUNCHER_PYTHON = Path(sys.executable).absolute()
LAUNCHER_EXECUTABLE = LAUNCHER_PYTHON.resolve(strict=True)


def _launcher_runtime_mounts() -> tuple[tuple[Path, Path], ...]:
    prefixes = {
        Path(prefix).absolute()
        for prefix in (sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix)
    }
    # uv and other installers may use a lexical base-prefix alias in venv links.
    base_alias = Path(getattr(sys, "_base_executable", sys.executable)).absolute().parent.parent
    if base_alias.resolve() == Path(sys.base_prefix).resolve():
        prefixes.add(base_alias)
    paths = set(prefixes)
    if not any(LAUNCHER_PYTHON.is_relative_to(prefix) for prefix in prefixes):
        paths.add(LAUNCHER_PYTHON)
    return tuple((path.resolve(strict=True), path) for path in sorted(paths))


LAUNCHER_RUNTIME_MOUNTS = _launcher_runtime_mounts()


def candidate_environment(*, python: Path) -> dict[str, str]:
    """Start without credentials, user configuration, or executable search overrides."""
    return {
        "PATH": "/tools:/usr/bin:/bin",
        "HOME": "/tmp/home",
        "TMPDIR": "/tmp",
        "LANG": "C.UTF-8",
        "PYTHON": str(python),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "UV_OFFLINE": "1",
        "UV_CACHE_DIR": "/tmp/uv-cache",
    }


def _raise_walk_error(error: OSError) -> None:
    raise error


def validate_candidate_workspace(
    workspace: Path,
    *,
    interpreter_alias: tuple[Path, Path] | None = None,
) -> None:
    # A bind mount must not expose a host inode or service through an existing
    # hard link, socket, device or FIFO. Reject escaping symlinks as well: the
    # host later consumes candidate diagnostic files after the sandbox exits.
    workspace = workspace.resolve(strict=True)
    for directory, directories, files in os.walk(
        workspace, followlinks=False, onerror=_raise_walk_error
    ):
        for name in [*directories, *files]:
            path = Path(directory) / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                try:
                    target = path.resolve()
                except (OSError, RuntimeError) as exc:
                    raise ValueError(
                        "candidate sandbox cannot resolve workspace symlink"
                    ) from exc
                if interpreter_alias == (path, target):
                    continue
                runtime_alias = (
                    path.parent == workspace / ".venv" / "bin"
                    and path.name in {"python", "python3", LAUNCHER_EXECUTABLE.name}
                    and target == LAUNCHER_EXECUTABLE
                )
                if not target.is_relative_to(workspace) and not runtime_alias:
                    raise ValueError(
                        "candidate sandbox refuses symlinks outside its workspace"
                    )
                continue
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError(
                    "candidate sandbox refuses special files and multiply linked files"
                )


def candidate_sandbox_argv(
    argv: list[str],
    *,
    workspace_root: Path,
    cwd: Path,
    trusted_python: Path,
    interpreter_alias: tuple[Path, Path] | None = None,
) -> list[str]:
    """Build a mandatory Linux namespace boundary; never fall back to host execution."""
    if sys.platform != "linux" or not BWRAP.is_file():
        raise ValueError(
            "candidate validation requires Linux and /usr/bin/bwrap (Bubblewrap)"
        )
    workspace = workspace_root.resolve(strict=True)
    working_directory = cwd.resolve(strict=True)
    if not workspace.is_dir() or not working_directory.is_relative_to(workspace):
        raise ValueError("candidate working directory must be inside its workspace")
    if workspace == Path("/") or any(
        Path(path).is_relative_to(workspace) for path in SYSTEM_RUNTIME_PATHS
    ):
        raise ValueError(
            "candidate workspace must not contain a system runtime directory"
        )
    if trusted_python.resolve(strict=True) != LAUNCHER_EXECUTABLE:
        raise ValueError(
            "candidate Python must use the controller's captured runtime; "
            "start the controller with the required Python environment"
        )
    if LAUNCHER_PYTHON.resolve(strict=True) != LAUNCHER_EXECUTABLE:
        raise ValueError("controller Python executable changed before validation")
    for source, destination in LAUNCHER_RUNTIME_MOUNTS:
        if destination.resolve(strict=True) != source:
            raise ValueError("controller Python runtime path changed before validation")
    validate_candidate_workspace(
        workspace, interpreter_alias=interpreter_alias
    )
    command = [
        str(BWRAP),
        "--unshare-all",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-net",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(SANDBOX_TMP_BYTES),
        "--tmpfs",
        "/tmp",
        "--size",
        str(SANDBOX_TMP_BYTES),
        "--tmpfs",
        "/dev/shm",
        "--dir",
        "/tmp/home",
        "--dir",
        "/tools",
    ]
    for path in SYSTEM_RUNTIME_PATHS:
        if Path(path).exists():
            command.extend(["--ro-bind", path, path])
    loader_cache = Path("/etc/ld.so.cache")
    if loader_cache.is_file():
        command.extend(["--ro-bind", str(loader_cache), str(loader_cache)])
    command.extend(["--bind", str(workspace), str(workspace)])
    # Never add a mount from a request-selected or candidate-resolved path.
    # Mount both base and virtualenv prefixes; invoking the lexical launcher
    # below retains its installed dependencies instead of dropping to base Python.
    for source, destination in LAUNCHER_RUNTIME_MOUNTS:
        command.extend(["--ro-bind", str(source), str(destination)])
    uv = shutil.which("uv")
    if uv and not Path(uv).resolve().is_relative_to(workspace):
        command.extend(["--ro-bind", str(Path(uv).resolve()), "/tools/uv"])
    for key, value in candidate_environment(python=LAUNCHER_PYTHON).items():
        command.extend(["--setenv", key, value])
    python_aliases = {str(trusted_python), str(trusted_python.absolute()), str(LAUNCHER_EXECUTABLE)}
    sandbox_argv = [
        str(LAUNCHER_PYTHON) if token in python_aliases else
        f"PYTHON={LAUNCHER_PYTHON}" if token.removeprefix("PYTHON=") in python_aliases else
        token
        for token in argv
    ]
    command.extend(
        [
            "--remount-ro",
            "/dev",
            "--remount-ro",
            "/proc",
            "--remount-ro",
            "/",
            "--chdir",
            str(working_directory),
            "--",
            *sandbox_argv,
        ]
    )
    return command


def run_candidate_command(
    argv: list[str], *, cwd: Path, timeout_seconds: int
) -> TimedProcessResult:
    try:
        command = candidate_sandbox_argv(
            argv, workspace_root=cwd, cwd=cwd, trusted_python=LAUNCHER_PYTHON
        )
        return run_with_timeout(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text="",
            env=candidate_environment(python=LAUNCHER_PYTHON),
        )
    except (OSError, ValueError) as exc:
        return TimedProcessResult(
            args=argv,
            returncode=126,
            stdout="",
            stderr=f"candidate sandbox unavailable: {exc}\n",
            timed_out=False,
            timeout_seconds=timeout_seconds,
            termination_reason="sandbox_unavailable",
            launch_succeeded=False,
        )


def probe_candidate_sandbox(*, timeout_seconds: int = 30) -> TimedProcessResult:
    """Exercise the production namespace boundary and required runtime imports."""
    with tempfile.TemporaryDirectory(prefix="candidate-sandbox-smoke-") as workspace:
        return run_candidate_command(
            [str(LAUNCHER_PYTHON), "-c", "import jsonschema, pytest, yaml; print('candidate sandbox ready')"],
            cwd=Path(workspace), timeout_seconds=timeout_seconds,
        )
