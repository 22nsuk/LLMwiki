from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

from ops.scripts.core.command_runtime import run_with_timeout

pytestmark = pytest.mark.subprocess


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
