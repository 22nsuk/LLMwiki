from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

import pytest

from ops.scripts.core.command_runtime import PosixProcessBackend, run_with_timeout

pytestmark = pytest.mark.subprocess


@pytest.mark.skipif(not Path("/proc/self/stat").is_file(), reason="Linux procfs verifies descendant exit")
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_parent_signal_kills_descendant_even_after_output_eof(tmp_path: Path, signum: signal.Signals) -> None:
    class RecordingBackend(PosixProcessBackend):
        def start(self, *args, **kwargs):
            self.process = super().start(*args, **kwargs)
            return self.process

    backend = RecordingBackend()
    ready = tmp_path / "descendant.pid"
    child_pid = None
    child = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "signal.signal(signal.SIGINT, signal.SIG_IGN); "
        "os.close(1); os.close(2); "
        "Path('pid.tmp').write_text(str(os.getpid())); "
        "Path('pid.tmp').rename('descendant.pid'); time.sleep(30)"
    )
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"

    def heartbeat(_event):
        nonlocal child_pid
        if ready.exists():
            child_pid = int(ready.read_text(encoding="utf-8"))
            signal.raise_signal(signum)

    previous = signal.signal(signum, signal.SIG_DFL)
    try:
        with pytest.raises(KeyboardInterrupt if signum == signal.SIGINT else SystemExit):
            run_with_timeout(
                [sys.executable, "-c", parent], cwd=tmp_path, timeout_seconds=10,
                grace_seconds=0.2, heartbeat_interval_seconds=1, heartbeat_callback=heartbeat, backend=backend,
            )
        assert backend.process.poll() is not None
        assert child_pid is not None
        deadline = time.monotonic() + 2
        while True:
            try:
                state = Path(f"/proc/{child_pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
            except (FileNotFoundError, ProcessLookupError):
                break
            if state == "Z":
                break
            assert time.monotonic() < deadline, "descendant survived parent signal cleanup"
            time.sleep(0.01)
    finally:
        signal.signal(signum, previous)
        with suppress(ProcessLookupError):
            os.killpg(backend.process.pid, signal.SIGKILL)
        backend.process.communicate(timeout=3)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group cleanup")
@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_heartbeat_error_reaps_process_before_returning(tmp_path: Path, failure: type[BaseException]) -> None:
    class RecordingBackend(PosixProcessBackend):
        def start(self, *args, **kwargs):
            self.process = super().start(*args, **kwargs)
            return self.process

    backend = RecordingBackend()
    ready = tmp_path / "ready"
    error = failure("heartbeat failed")

    def heartbeat(_event):
        if ready.exists():
            raise error

    try:
        with pytest.raises(failure) as raised:
            run_with_timeout(
                [sys.executable, "-c", "from pathlib import Path; import time; Path('ready').touch(); time.sleep(30)"],
                cwd=tmp_path, timeout_seconds=10, grace_seconds=0.2,
                heartbeat_interval_seconds=1, heartbeat_callback=heartbeat, backend=backend,
            )
        assert raised.value is error
        assert backend.process.poll() is not None
    finally:
        if backend.process.poll() is None:
            os.killpg(backend.process.pid, signal.SIGKILL)
        backend.process.communicate(timeout=3)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group descendant cleanup")
@pytest.mark.parametrize("ignore_term", [False, True])
def test_exited_parent_does_not_hide_output_owning_descendant_timeout(tmp_path: Path, ignore_term: bool) -> None:
    child = "import signal,time; "
    if ignore_term:
        child += "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    child += "print('child output', flush=True); time.sleep(4)"
    parent = f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child!r}])"
    started = time.monotonic()
    result = run_with_timeout(
        [sys.executable, "-c", parent], cwd=tmp_path,
        timeout_seconds=1, grace_seconds=0.2,
    )
    assert result.timed_out is True
    assert result.returncode != 0
    assert result.termination_reason == "timeout_after_output"
    assert "child output" in result.stdout
    assert result.signal_sent == ("sigkill" if ignore_term else "sigterm")
    assert time.monotonic() - started < 3


def test_run_with_timeout_executes_real_subprocess() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        result = run_with_timeout(
            [sys.executable, "-c", "print('ok')"],
            cwd=Path(temp_dir),
            timeout_seconds=5,
        )

    assert result.returncode == 0
    assert result.stdout == "ok\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.termination_reason == "completed"
    assert result.signal_sent == "none"
    assert result.final_state_observed == "communicate"


def test_hermetic_mode_cleans_environment_and_runs_python_without_site() -> None:
    code = (
        "import json, os, sys; "
        "print(json.dumps({"
        "'no_site': sys.flags.no_site, "
        "'pythonpath': os.environ.get('PYTHONPATH'), "
        "'custom': os.environ.get('CUSTOM_LEAK'), "
        "'pythonutf8': os.environ.get('PYTHONUTF8')"
        "}, sort_keys=True))"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        result = run_with_timeout(
            [sys.executable, "-c", code],
            cwd=Path(temp_dir),
            timeout_seconds=5,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "/leak", "CUSTOM_LEAK": "yes"},
            hermetic=True,
        )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.args[:3] == [sys.executable, "-S", "-c"]
    assert payload == {
        "custom": None,
        "no_site": 1,
        "pythonpath": None,
        "pythonutf8": "1",
    }
