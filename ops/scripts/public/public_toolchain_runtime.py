from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from ops.scripts.core.command_runtime import run_with_timeout

# Run with the requested interpreter, using only its standard library. Persist
# the digest, never local executable, package, or installation paths.
_PROBE = """
import hashlib, importlib.metadata, importlib.util, json, os, platform, sys
from pathlib import Path

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

packages = []
for distribution in importlib.metadata.distributions():
    packages.append((
        distribution.metadata['Name'], distribution.version,
        str(distribution.locate_file('').resolve()),
        tuple(digest(distribution.read_text(name) or '') for name in
              ('METADATA', 'RECORD', 'direct_url.json')),
    ))
tools = {}
for name in ('pytest', 'ruff', 'mypy'):
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise RuntimeError('required validation module is unavailable')
    tools[name] = (importlib.metadata.version(name), spec.origin)
executable = Path(sys.executable).resolve(strict=True)
with executable.open('rb') as handle:
    executable_digest = hashlib.file_digest(handle, 'sha256').hexdigest()
payload = {
    'version': 1, 'python': sys.version, 'implementation': sys.implementation.name,
    'platform': platform.platform(), 'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
    'executable': str(executable), 'executable_sha256': executable_digest,
    'packages': sorted(packages), 'tools': tools,
    'search_path': sys.path[1:],
    'environment': {name: os.environ.get(name, '') for name in (
        'PYTHONPATH', 'PYTHONHOME', 'PYTHONNOUSERSITE', 'PYTHONSAFEPATH',
        'PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'MYPYPATH',
    )},
    'plugin_autoload_disabled': os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1'),
}
print(digest(json.dumps(payload, sort_keys=True, separators=(',', ':'))))
"""
PROBE_TIMEOUT_SECONDS = 15


def public_toolchain_fingerprint(public_python: str) -> str:
    """Fail closed if the selected launcher or its validation environment is unavailable."""
    try:
        launcher = shutil.which(public_python)
        if launcher is None:
            raise ValueError("public Python launcher is unavailable")
        path = Path(launcher).resolve(strict=True)
        before = path.stat()
        with path.open("rb") as handle:
            launcher_digest = hashlib.file_digest(handle, "sha256").hexdigest()
        with tempfile.TemporaryDirectory(prefix="public-toolchain-probe-") as directory:
            result = run_with_timeout(
                [launcher, "-c", _PROBE], cwd=Path(directory),
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
    identity = (
        launcher, str(path), before.st_dev, before.st_ino, before.st_mtime_ns,
        before.st_size, before.st_mode, launcher_digest, digest,
    )
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()
