"""Verify the built wheel in a clean interpreter outside the source checkout."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops.scripts.public.public_surface_policy import is_public_excluded_path

RESOURCE_PROBE = """
import json, sys
from pathlib import Path
import ops
from ops.scripts.core.policy_runtime import load_policy, write_local_corpus_policy
from ops.scripts.core.schema_runtime import load_schema_with_vault_override
from importlib.resources import files

installed = Path(sys.prefix).resolve()
assert Path(ops.__file__).resolve().is_relative_to(installed), 'ops imported outside installed environment'
vault = Path.cwd() / 'synthetic-vault'
policy_path = vault / 'ops/policies/wiki-maintainer-policy.yaml'
policy_path.parent.mkdir(parents=True)
policy_path.write_text(files('ops').joinpath('policies/wiki-maintainer-policy.yaml').read_text(encoding='utf-8'), encoding='utf-8')
schema = load_schema_with_vault_override(vault, 'ops/schemas/wiki-maintainer-policy.schema.json')
assert schema['type'] == 'object'
policy, _ = load_policy(vault)
policy['page_shape']['special_page_required_sections']['system/synthetic-wheel-page.md'] = ['Summary']
write_local_corpus_policy(vault, policy)
assert load_policy(vault)[0] == policy
assert not (vault / 'ops/schemas').exists(), 'resource fallback was not exercised'
for name, module in tuple(sys.modules.items()):
    location = getattr(module, '__file__', None)
    if (name == 'ops' or name.startswith('ops.')) and location:
        assert Path(location).resolve().is_relative_to(installed), name
print(json.dumps({'installed_imports': 'pass', 'bundled_schema': 'pass', 'local_policy': 'pass'}))
"""


def _run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=300, check=False)
    if result.returncode:
        raise RuntimeError(f"installed-wheel check failed: {result.stderr[-4000:]}")
    return result.stdout


def verify_wheel(wheel: Path, root: Path) -> dict[str, object]:
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    with zipfile.ZipFile(wheel) as archive:
        if any(is_public_excluded_path(name) for name in archive.namelist()):
            raise ValueError("wheel contains policy-excluded local artifacts; rebuild from a clean public source tree")
        entry_files = [name for name in archive.namelist() if name.endswith('.dist-info/entry_points.txt')]
        if len(entry_files) != 1:
            raise ValueError("expected one wheel entry-point manifest")
        entries = configparser.ConfigParser()
        entries.optionxform = str
        entries.read_string(archive.read(entry_files[0]).decode('utf-8'))
        scripts = sorted(entries['console_scripts'])
        if not scripts:
            raise ValueError("wheel has no console scripts")
    environment = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME'):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='installed-wheel-check-') as temp:
        work = Path(temp)
        requirements = work / 'requirements.txt'
        _run(['uv', 'export', '--frozen', '--no-emit-project', '--no-dev', '--format', 'requirements-txt', '--output-file', str(requirements)], cwd=root, env=environment)
        target = work / 'venv'
        venv.EnvBuilder(with_pip=True).create(target)
        scripts_dir = target / ('Scripts' if os.name == 'nt' else 'bin')
        python = scripts_dir / ('python.exe' if os.name == 'nt' else 'python')
        _run([str(python), '-I', '-m', 'pip', 'install', '--require-hashes', '-r', str(requirements)], cwd=work, env=environment)
        _run([str(python), '-I', '-m', 'pip', 'install', '--no-deps', str(wheel)], cwd=work, env=environment)
        for script in scripts:
            command = scripts_dir / (script + '.exe' if os.name == 'nt' else script)
            _run([str(command), '--help'], cwd=work, env=environment)
        resources = json.loads(_run([str(python), '-I', '-c', RESOURCE_PROBE], cwd=work, env=environment))
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != digest:
        raise ValueError('wheel changed during installed validation')
    return {'status': 'pass', 'wheel': wheel.name, 'wheel_sha256': digest, 'console_scripts': scripts, 'resources': resources}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--out', type=Path, default=Path('tmp/installed-wheel-smoke.json'))
    args = parser.parse_args()
    try:
        wheels = list(args.dist.resolve().glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('expected exactly one built wheel')
        result = verify_wheel(wheels[0], Path.cwd())
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        result = {'status': 'fail', 'error': str(exc)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
