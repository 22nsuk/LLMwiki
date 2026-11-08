from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from ops.scripts.core.command_runtime import run_with_timeout

# Run with the requested interpreter, using only its standard library. Persist
# the digest, never local executable, package, or installation paths.
_PROBE = """
import hashlib, importlib.metadata, importlib.util, json, os, platform, sys
from pathlib import Path

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

export_root = Path.cwd()
workspace_root = export_root.parent if sys.argv[1] == 'private' else export_root

def path_identity(value):
    if value is None:
        return None
    path = Path(value).resolve()
    if path.is_relative_to(export_root):
        return '<export>/' + path.relative_to(export_root).as_posix()
    if path.is_relative_to(workspace_root):
        return '<workspace>/' + path.relative_to(workspace_root).as_posix()
    return str(path)

packages = []
for distribution in importlib.metadata.distributions():
    packages.append((
        distribution.metadata['Name'], distribution.version,
        path_identity(distribution.locate_file('')),
        tuple(digest(distribution.read_text(name) or '') for name in
              ('METADATA', 'RECORD', 'direct_url.json')),
    ))
tools = {}
for name in ('pytest', 'ruff', 'mypy'):
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise RuntimeError('required validation module is unavailable')
    tools[name] = (importlib.metadata.version(name), path_identity(spec.origin))
executable = Path(sys.executable).resolve(strict=True)
with executable.open('rb') as handle:
    executable_digest = hashlib.file_digest(handle, 'sha256').hexdigest()
payload = {
    'version': 3, 'python': sys.version, 'implementation': sys.implementation.name,
    'platform': platform.platform(), 'prefix': path_identity(sys.prefix),
    'base_prefix': path_identity(sys.base_prefix),
    'executable': path_identity(executable), 'executable_sha256': executable_digest,
    'packages': sorted(packages), 'tools': tools,
    # Keep every entry: safe-path mode does not prepend the usual empty entry.
    # Export contents are bound separately; invocation-private roots are disposable.
    'search_path': [path_identity(path) for path in sys.path],
    'environment': {name: os.environ.get(name, '') for name in (
        'PYTHONPATH', 'PYTHONHOME', 'PYTHONNOUSERSITE', 'PYTHONSAFEPATH',
        'PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'MYPYPATH',
    )},
    'plugin_autoload_disabled': os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1'),
}
print(digest(json.dumps(payload, sort_keys=True, separators=(',', ':'))))
"""
PROBE_TIMEOUT_SECONDS = 15


def public_check_environment(public_python: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHON"] = public_python
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return env


def public_python_launcher(public_python: str, *, cwd: Path) -> str:
    """Resolve the command in the export's PATH without bypassing venv aliases."""
    if os.path.dirname(public_python):
        return str((cwd / public_python).absolute())
    search_path = os.pathsep.join(
        str((cwd / entry).absolute()) for entry in os.get_exec_path()
    )
    launcher = shutil.which(public_python, path=search_path)
    if launcher is None:
        raise ValueError("public Python launcher is unavailable")
    return str(Path(launcher).absolute())


def public_toolchain_fingerprint(
    public_python: str, *, cwd: Path, private_workspace: bool = False,
) -> str:
    """Fail closed if the selected launcher or its validation environment is unavailable."""
    try:
        launcher = public_python_launcher(public_python, cwd=cwd)
        path = Path(launcher).resolve(strict=True)
        before = path.stat()
        with path.open("rb") as handle:
            launcher_digest = hashlib.file_digest(handle, "sha256").hexdigest()
        result = run_with_timeout(
            [launcher, "-c", _PROBE, "private" if private_workspace else "retained"],
            cwd=cwd, env=public_check_environment(launcher),
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0 or result.timed_out:
            raise ValueError("public Python toolchain probe failed")
        digest = result.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("public Python toolchain probe returned invalid evidence")
        after = path.stat()
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode)
            or Path(launcher).resolve(strict=True) != path
        ):
            raise ValueError("public Python launcher changed during probe")
    except OSError as exc:
        raise ValueError("public Python toolchain is unavailable") from exc
    launcher_identity: tuple[str | int, ...]
    if path.is_relative_to(cwd.resolve()):
        # Export copies have new inodes. Their bytes and mode, plus the export's
        # source binding, establish identity; the before/after stat guard still runs.
        launcher_identity = ("<export>/" + path.relative_to(cwd.resolve()).as_posix(), before.st_mode)
    else:
        launcher_identity = (str(path), before.st_dev, before.st_ino, before.st_mtime_ns, before.st_mode)
    identity = (
        # Equivalent aliases share the target identity; the probe still binds the
        # effective prefix, imports and metadata, so distinct venvs stay distinct.
        launcher_identity, before.st_size, launcher_digest, digest,
    )
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()
