from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.core import candidate_sandbox_runtime as sandbox
from ops.scripts.core.executor_runtime_worker_preflight_runtime import (
    trusted_python_for_candidate_runs,
    write_worker_structural_complexity_preflight_report,
)
from ops.scripts.core.policy_runtime import load_policy, validate_policy_contract
from ops.scripts.core.trusted_candidate_runner import (
    TrustedCandidateRunRequest,
    run_trusted_candidate_command,
)
from ops.scripts.mechanism.mechanism_run_common_runtime import (
    RunMechanismExperimentUsageError,
)
from ops.scripts.mechanism.mechanism_run_repo_health_step_runtime import (
    write_structural_complexity_budget_artifact,
)
from ops.scripts.mechanism.mechanism_run_workspace_runtime import (
    _repo_health_step,
    _run_command,
)
from tests.runtime_test_context import frozen_context
from tests.test_mechanism_assess import seed_policy
from tests.test_mechanism_run_repo_health_step_runtime import _resolution

pytestmark = pytest.mark.subprocess


def test_shared_sandbox_probe_uses_production_launcher() -> None:
    result = sandbox.probe_candidate_sandbox(timeout_seconds=30)
    assert result.returncode == 0, result.stderr
    assert result.timed_out is False
    assert "candidate sandbox ready" in result.stdout


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    return workspace


def _check(candidate: Path, argv: list[str], *, timeout: int = 10) -> dict:
    return _run_command(
        shlex.join(argv),
        argv=argv,
        cwd=candidate,
        timeout_seconds=timeout,
        candidate=True,
    )


@pytest.mark.parametrize("entrypoint", ["python", "make", "pytest", "preflight"])
def test_candidate_entrypoints_cannot_use_host_authority(
    candidate: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    sentinel = candidate.parent / "synthetic-secret"
    sentinel.write_text("synthetic-only", encoding="utf-8")
    escaped = candidate.parent / "escaped"
    monkeypatch.setenv("CANDIDATE_TEST_SECRET", "synthetic-only")
    # Use a local listener only; no external network service is contacted.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        probe = f"""
import json, os, socket
from pathlib import Path
def denied(operation):
    try:
        operation()
    except OSError:
        return True
    return False
checks = {{
    "secret": denied(lambda: Path({str(sentinel)!r}).read_text()),
    "write": denied(lambda: Path("/host-write-must-fail").write_text("escape")),
    "network": denied(lambda: socket.create_connection(("127.0.0.1", {port}), timeout=1)),
    "proc_root": denied(lambda: Path("/proc/1/root" + {str(sentinel)!r}).read_text()),
    "environment": "CANDIDATE_TEST_SECRET" not in os.environ,
    "home": os.environ.get("HOME") == "/tmp/home",
}}
assert all(checks.values()), checks
# Host /tmp paths can have writable names in the private tmpfs; writing such a
# name must still leave the original host path unchanged (asserted by parent).
try:
    Path({str(escaped)!r}).write_text("sandbox-only")
except OSError:
    pass
Path("legitimate-output").write_text("ok")
Path("/tmp/scratch").write_text("ok")
Path("/tmp/home/config").write_text("ok")
print(json.dumps(checks))
"""
        (candidate / "probe.py").write_text(probe, encoding="utf-8")
        argv = [sys.executable, "probe.py"]
        if entrypoint == "make":
            (candidate / "Makefile").write_text(
                f"check:\n\t{shlex.quote(sys.executable)} probe.py\n",
                encoding="utf-8",
            )
            argv = ["/usr/bin/make", "check"]
        elif entrypoint == "pytest":
            (candidate / "conftest.py").write_text(probe, encoding="utf-8")
            (candidate / "test_ok.py").write_text(
                "def test_ok(): assert True\n", encoding="utf-8"
            )
            argv = [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "test_ok.py",
            ]
        if entrypoint == "preflight":
            outcome = run_trusted_candidate_command(
                TrustedCandidateRunRequest(
                    purpose="test",
                    argv=argv,
                    workspace_root=candidate,
                    trusted_vault_root=candidate.parent,
                    trusted_python=Path(sys.executable),
                    timeout_seconds=10,
                )
            )
            assert outcome.returncode == 0, outcome.stderr
            assert (
                outcome.audit_record["network_policy"] == "isolated_network_namespace"
            )
        else:
            result = _check(candidate, argv)
            assert result["returncode"] == 0, result["stderr"]
    assert sentinel.read_text(encoding="utf-8") == "synthetic-only"
    assert not escaped.exists()
    assert (candidate / "legitimate-output").read_text(encoding="utf-8") == "ok"


def test_missing_sandbox_never_falls_back_to_host(candidate: Path) -> None:
    with mock.patch.object(sandbox, "BWRAP", candidate / "missing-bwrap"):
        result = _check(
            candidate, [sys.executable, "-c", "open('executed', 'w').close()"]
        )
    assert result["returncode"] == 126
    assert not result["launch_succeeded"]
    assert "requires Linux" in result["stderr"]
    assert not (candidate / "executed").exists()


def test_unusable_sandbox_never_falls_back_to_host(candidate: Path) -> None:
    with mock.patch.object(sandbox, "BWRAP", Path("/usr/bin/false")):
        result = _check(
            candidate, [sys.executable, "-c", "open('executed', 'w').close()"]
        )
    assert result["returncode"] != 0
    assert not (candidate / "executed").exists()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_candidate_aliases_cannot_expose_host_files(candidate: Path, kind: str) -> None:
    sentinel = candidate.parent / "synthetic-secret"
    sentinel.write_text("synthetic-only", encoding="utf-8")
    alias = candidate / "alias"
    if kind == "symlink":
        alias.symlink_to(sentinel)
    elif kind == "hardlink":
        os.link(sentinel, alias)
    else:
        os.mkfifo(alias)
    with pytest.raises(RunMechanismExperimentUsageError, match="unsafe candidate"):
        _check(candidate, [sys.executable, "-c", "open('executed', 'w').close()"])
    assert not (candidate / "executed").exists()


def test_symlinked_diagnostic_parent_is_rejected_before_cleanup(
    candidate: Path,
) -> None:
    sentinel = candidate.parent / "artifact-freshness-report-check.json"
    sentinel.write_text("synthetic-only", encoding="utf-8")
    (candidate / "tmp").symlink_to(candidate.parent, target_is_directory=True)
    with pytest.raises(
        RunMechanismExperimentUsageError, match="unsafe candidate workspace"
    ):
        _repo_health_step(
            candidate.parent,
            candidate,
            run_id="unused",
            resolution=mock.Mock(),
            baseline_file_digests={},
        )
    assert sentinel.read_text(encoding="utf-8") == "synthetic-only"


def test_created_diagnostic_symlink_is_rejected_before_host_consumption(
    candidate: Path,
) -> None:
    sentinel = candidate.parent / "synthetic-secret"
    sentinel.write_text("synthetic-only", encoding="utf-8")
    code = (
        "from pathlib import Path; Path('tmp').mkdir(); "
        f"Path('tmp/artifact-freshness-report-check.json').symlink_to({str(sentinel)!r})"
    )
    with pytest.raises(
        RunMechanismExperimentUsageError, match="unsafe candidate validation output"
    ):
        _check(candidate, [sys.executable, "-c", code])


@pytest.mark.parametrize("timeout", [False, True])
@pytest.mark.parametrize("entrypoint", ["mechanism", "preflight"])
def test_candidate_descendants_are_reaped(candidate: Path, timeout: bool, entrypoint: str) -> None:
    child = (
        "import os,time; from pathlib import Path; os.setsid(); "
        "os.close(0); os.close(1); os.close(2); Path('ready').touch(); "
        "time.sleep(2); Path('survived').touch()"
    )
    parent = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "\nwhile not Path('ready').exists(): time.sleep(0.01)\n"
        + ("time.sleep(30)" if timeout else "")
    )
    if entrypoint == "preflight":
        outcome = run_trusted_candidate_command(
            TrustedCandidateRunRequest(
                purpose="test",
                argv=[sys.executable, "-c", parent],
                workspace_root=candidate,
                trusted_vault_root=candidate.parent,
                trusted_python=Path(sys.executable),
                timeout_seconds=1 if timeout else 10,
            )
        )
        timed_out = outcome.timed_out
    else:
        result = _check(
            candidate, [sys.executable, "-c", parent], timeout=1 if timeout else 10
        )
        timed_out = result["timed_out"]
    assert timed_out is timeout
    assert (candidate / "ready").exists()
    # A bounded observation interval covers the child's explicitly scheduled write.
    deadline = time.monotonic() + 2.2
    while time.monotonic() < deadline and not (candidate / "survived").exists():
        time.sleep(0.05)
    assert not (candidate / "survived").exists()


def test_repo_health_selects_sandbox_without_changing_mutation_runner(
    candidate: Path,
) -> None:
    with mock.patch(
        "ops.scripts.mechanism.mechanism_run_workspace_runtime.repo_health_step"
    ) as step:
        _repo_health_step(
            candidate.parent,
            candidate,
            run_id="unused",
            resolution=mock.Mock(),
            baseline_file_digests={},
        )
    runner = step.call_args.kwargs["dependencies"].run_command
    assert runner.keywords == {"candidate": True}


def test_internal_symlinks_and_nonzero_results_remain_supported(
    candidate: Path,
) -> None:
    (candidate / "source").write_text("ok", encoding="utf-8")
    (candidate / "alias").symlink_to("source")
    result = _check(
        candidate,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; print(Path('alias').read_text()); raise SystemExit(7)",
        ],
    )
    assert result["returncode"] == 7
    assert result["stdout"] == "ok\n"


def test_trusted_interpreter_alias_remains_usable(candidate: Path) -> None:
    alias = candidate / ".venv" / "bin" / "python"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(sys.executable)
    result = _check(candidate, [str(alias), "-c", "print('trusted interpreter')"])
    assert result["returncode"] == 0, result["stderr"]
    assert result["stdout"] == "trusted interpreter\n"


def test_same_root_preflight_preserves_but_does_not_expose_existing_alias(
    candidate: Path,
) -> None:
    secret = candidate.parent / "synthetic-secret"
    secret.write_text("synthetic-only", encoding="utf-8")
    alias = candidate / ".venv" / "bin" / "python"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(secret)
    code = "from pathlib import Path; assert not Path('.venv/bin/python').exists(); print('isolated')"
    outcome = run_trusted_candidate_command(
        TrustedCandidateRunRequest(
            purpose="test",
            argv=[sys.executable, "-c", code],
            workspace_root=candidate,
            trusted_vault_root=candidate,
            trusted_python=Path(sys.executable),
            timeout_seconds=10,
        )
    )
    assert outcome.returncode == 0, outcome.stderr
    assert outcome.stdout == "isolated\n"


def test_same_root_preflight_rejects_retargeted_alias(candidate: Path) -> None:
    original = candidate.parent / "original"
    original.touch()
    alias = candidate / ".venv" / "bin" / "python"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(original)
    code = "from pathlib import Path; p=Path('.venv/bin/python'); p.unlink(); p.symlink_to('/outside')"
    with pytest.raises(ValueError, match="unsafe candidate workspace"):
        run_trusted_candidate_command(
            TrustedCandidateRunRequest(
                purpose="test",
                argv=[sys.executable, "-c", code],
                workspace_root=candidate,
                trusted_vault_root=candidate,
                trusted_python=Path(sys.executable),
                timeout_seconds=10,
            )
        )


def test_worker_python_retarget_cannot_mount_host_secret(candidate: Path) -> None:
    secret = candidate.parent / "synthetic-secret"
    secret.write_text("synthetic-only", encoding="utf-8")
    alias = candidate / ".venv" / "bin" / "python"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(secret)
    (candidate / "Makefile").write_text(
        "check:\n\tcat $(PYTHON)\n", encoding="utf-8"
    )
    trusted_python = trusted_python_for_candidate_runs(candidate)
    outcome = run_trusted_candidate_command(
        TrustedCandidateRunRequest(
            purpose="worker_repo_health_preflight",
            argv=["/usr/bin/make", f"PYTHON={trusted_python}", "check"],
            workspace_root=candidate,
            trusted_vault_root=candidate,
            trusted_python=trusted_python,
            timeout_seconds=10,
        )
    )
    assert "synthetic-only" not in outcome.stdout
    assert outcome.returncode == 126


def test_resolved_python_keeps_launcher_virtualenv_dependencies(candidate: Path) -> None:
    outcome = run_trusted_candidate_command(
        TrustedCandidateRunRequest(
            purpose="worker_repo_health_preflight",
            argv=[str(Path(sys.executable).resolve()), "-c", "import pytest; print('deps-ok')"],
            workspace_root=candidate,
            trusted_vault_root=candidate.parent,
            trusted_python=Path(sys.executable).resolve(),
            timeout_seconds=10,
        )
    )
    assert outcome.returncode == 0, outcome.stderr
    assert outcome.stdout == "deps-ok\n"


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("parent_link", [False, True])
def test_unsafe_audit_output_never_writes_host_file(
    candidate: Path, existing: bool, parent_link: bool
) -> None:
    secret = candidate.parent / "synthetic-secret"
    secret.write_text("synthetic-only", encoding="utf-8")
    audit = "runs/check/audit.json"
    outside = candidate.parent / "outside"
    outside.mkdir()
    (outside / "audit.json").write_text("synthetic-only", encoding="utf-8")
    alias = "runs/check" if parent_link else audit
    target = outside if parent_link else secret
    code = (
        "from pathlib import Path; "
        f"p=Path({alias!r}); p.parent.mkdir(parents=True); "
        f"p.symlink_to({str(target)!r})"
    )
    if existing:
        (candidate / alias).parent.mkdir(parents=True)
        (candidate / alias).symlink_to(target)
        code = "pass"
    try:
        with pytest.raises(ValueError, match="unsafe candidate workspace"):
            run_trusted_candidate_command(
                TrustedCandidateRunRequest(
                    purpose="worker_repo_health_preflight",
                    argv=[sys.executable, "-c", code],
                    workspace_root=candidate,
                    trusted_vault_root=candidate,
                    trusted_python=Path(sys.executable),
                    timeout_seconds=10,
                    audit_rel_path=audit,
                )
            )
    finally:
        assert secret.read_text(encoding="utf-8") == "synthetic-only"
        assert (outside / "audit.json").read_text(encoding="utf-8") == "synthetic-only"


def test_diagnostics_cannot_borrow_mutable_interpreter_exception(
    candidate: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = candidate.parent / "synthetic-secret"
    secret.write_text("synthetic-only", encoding="utf-8")
    alias = candidate / ".venv" / "bin" / "python"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(secret)
    (candidate / "diagnostic.json").symlink_to(secret)
    monkeypatch.setattr(sys, "executable", str(alias))
    with pytest.raises(ValueError, match="symlinks outside"):
        sandbox.validate_candidate_workspace(candidate, interpreter_alias=(alias, secret))


def test_diagnostic_link_to_real_interpreter_is_not_an_executable_alias(candidate: Path) -> None:
    (candidate / "diagnostic.json").symlink_to(sandbox.LAUNCHER_EXECUTABLE)
    with pytest.raises(ValueError, match="symlinks outside"):
        sandbox.validate_candidate_workspace(candidate)


def test_unrelated_interpreter_is_rejected_without_execution(candidate: Path) -> None:
    unrelated = candidate.parent / "unrelated-python"
    unrelated.write_text("#!/bin/sh\ntouch executed\n", encoding="utf-8")
    unrelated.chmod(0o755)
    outcome = run_trusted_candidate_command(
        TrustedCandidateRunRequest(
            purpose="test",
            argv=[str(unrelated)],
            workspace_root=candidate,
            trusted_vault_root=candidate.parent,
            trusted_python=unrelated,
            timeout_seconds=10,
        )
    )
    assert outcome.returncode == 126
    assert "start the controller with the required Python environment" in outcome.stderr
    assert not (candidate / "executed").exists()


def test_system_python_controller_can_launch_its_own_runtime(candidate: Path) -> None:
    system_python = Path("/usr/bin/python3")
    assert system_python.is_file()
    code = (
        "import sys; from pathlib import Path; "
        "from ops.scripts.core.candidate_sandbox_runtime import run_candidate_command; "
        f"r=run_candidate_command([sys.executable, '-c', 'print(42)'], cwd=Path({str(candidate)!r}), timeout_seconds=10); "
        "assert r.returncode == 0, r.stderr; assert r.stdout == '42\\n'"
    )
    result = subprocess.run(
        [str(system_python), "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_unsupported_host_never_executes_candidate(candidate: Path, platform: str) -> None:
    with mock.patch.object(sys, "platform", platform):
        result = _check(candidate, [sys.executable, "-c", "open('executed', 'w').close()"])
    assert result["returncode"] == 126
    assert not result["launch_succeeded"]
    assert not (candidate / "executed").exists()


@pytest.mark.parametrize("prefix_kind", ["absolute", "traversal"])
@pytest.mark.parametrize("entrypoint", ["worker", "mechanism_pass", "mechanism_fail"])
def test_policy_prefix_cannot_read_host_during_diagnostics(
    candidate: Path, prefix_kind: str, entrypoint: str,
) -> None:
    seed_policy(candidate)
    authority = candidate.parent / "authority"
    authority.mkdir()
    secret = candidate.parent / "synthetic.py"
    secret.write_text("def synthetic_private_symbol(value):\n    return value\n", encoding="utf-8")
    prefix = str(secret) if prefix_kind == "absolute" else "../synthetic.py"
    policy, policy_path = load_policy(candidate)
    policy["system_refactor_policy"]["python_function_review"]["profiles"]["runtime"].update(
        include_prefixes=[prefix], lines=1, params=0, branches=0,
    )
    validate_policy_contract(policy, policy_path, candidate)
    policy_text = json.dumps(policy)
    if entrypoint == "worker":
        policy_path.write_text(policy_text, encoding="utf-8")
    else:
        returncode = 7 if entrypoint == "mechanism_fail" else 0
        code = (
            "from pathlib import Path; "
            f"Path('ops/policies/wiki-maintainer-policy.yaml').write_text({policy_text!r}); "
            f"raise SystemExit({returncode})"
        )
        result = _check(candidate, [sys.executable, "-c", code])
        assert result["returncode"] == returncode, result["stderr"]
    manifest_rel = "runs/diagnostic/changed-files-manifest.json"
    manifest = authority / manifest_rel
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"files": []}), encoding="utf-8")
    read_text = Path.read_text
    host_reads = []

    def record_read(path: Path, *args: object, **kwargs: object) -> str:
        if path.resolve() == secret:
            host_reads.append(path)
        return read_text(path, *args, **kwargs)

    try:
        with mock.patch.object(Path, "read_text", record_read), pytest.raises(ValueError, match="stay under vault"):
            if entrypoint == "worker":
                write_worker_structural_complexity_preflight_report(
                    authority, workspace_root=candidate, run_id="diagnostic",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    changed_targets=[], context=frozen_context(),
                )
            else:
                write_structural_complexity_budget_artifact(
                    authority, candidate, run_id="diagnostic", resolution=_resolution(),
                    changed_files_manifest=manifest_rel,
                )
    finally:
        assert host_reads == [], "diagnostics read the synthetic host file"
