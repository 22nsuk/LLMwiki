from __future__ import annotations

import subprocess
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.command_runtime import (
    CommandHeartbeat,
    FakeProcess,
    FakeProcessBackend,
    ProcessCleanupError,
    run_with_timeout,
)

pytestmark = pytest.mark.public


@pytest.mark.parametrize("failure_site", ["communicate", "after_launch", "signal_install"])
def test_post_launch_errors_abort_before_propagating(failure_site: str) -> None:
    error = OSError("controller failed")
    process = FakeProcess(communicate_side_effect=[error] if failure_site == "communicate" else [])
    backend = FakeProcessBackend(process)
    clock_values = iter([0.0, error] if failure_site == "after_launch" else [0.0] * 10)

    def clock() -> float:
        value = next(clock_values)
        if isinstance(value, BaseException):
            raise value
        return value

    failure_context = (
        patch("ops.scripts.core.command_runtime._install_parent_signal_cleanup", side_effect=error)
        if failure_site == "signal_install" else nullcontext()
    )
    with failure_context, pytest.raises(OSError) as raised:
        run_with_timeout(["python"], cwd=Path(), timeout_seconds=5, backend=backend, monotonic_clock=clock)
    assert raised.value is error
    assert backend.signal_calls == [(process.pid, int(backend.kill_signal()))]
    assert process.communicate_calls[-1]["timeout"] == 2.0


def test_cleanup_failure_preserves_original_exception_and_stays_bounded() -> None:
    original = OSError("heartbeat status write failed")
    process = FakeProcess(communicate_side_effect=[original, subprocess.TimeoutExpired(cmd=["python"], timeout=.1)])
    backend = FakeProcessBackend(process)
    with pytest.raises(ProcessCleanupError) as raised:
        run_with_timeout(["python"], cwd=Path(), timeout_seconds=5, grace_seconds=.1, backend=backend)
    assert raised.value.__cause__ is original
    assert "cleanup incomplete" in str(raised.value)
    assert process.communicate_calls[-1]["timeout"] == .1


class SteppedClock:
    def __init__(self, values: list[float]) -> None:
        self.values = list(values)
        self.last = self.values[-1] if self.values else 0.0

    def __call__(self) -> float:
        if self.values:
            self.last = self.values.pop(0)
        return self.last


class CommandRuntimeHeartbeatTests(unittest.TestCase):
    def test_run_with_timeout_emits_process_heartbeat_before_completion(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                ("done\n", ""),
            ]
        )
        process.returncode = 0
        backend = FakeProcessBackend(process)
        heartbeats: list[CommandHeartbeat] = []

        result = run_with_timeout(
            ["python", "-c", "print('done')"],
            cwd=Path(),
            timeout_seconds=5,
            backend=backend,
            heartbeat_interval_seconds=1,
            heartbeat_callback=heartbeats.append,
            monotonic_clock=SteppedClock([0.0, 0.0, 0.0, 0.0, 1.0, 1.0]),
        )

        self.assertEqual(result.stdout, "done\n")
        self.assertFalse(result.timed_out)
        self.assertEqual(result.observation_mode, "process_heartbeat")
        self.assertEqual(result.heartbeat_count, 1)
        self.assertEqual(result.heartbeat_interval_seconds, 1)
        self.assertEqual(result.quiet_seconds, 1)
        self.assertEqual(len(heartbeats), 1)
        self.assertEqual(heartbeats[0].heartbeat_index, 1)
        self.assertEqual(heartbeats[0].quiet_seconds, 1)
        self.assertEqual(heartbeats[0].observation_mode, "process_poll")
        self.assertEqual(
            [call["timeout"] for call in process.communicate_calls],
            [1.0, 1.0],
        )

    def test_run_with_timeout_rejects_nonpositive_heartbeat_interval(self) -> None:
        process = FakeProcess(communicate_side_effect=[("ok\n", "")])
        backend = FakeProcessBackend(process)

        with self.assertRaisesRegex(ValueError, "heartbeat_interval_seconds must be >= 1"):
            run_with_timeout(
                ["python", "-c", "print('ok')"],
                cwd=Path(),
                timeout_seconds=5,
                backend=backend,
                heartbeat_interval_seconds=0,
                heartbeat_callback=lambda _event: None,
            )


if __name__ == "__main__":
    unittest.main()
