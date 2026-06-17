from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.command_runtime import (
    CommandHeartbeat,
    FakeProcess,
    FakeProcessBackend,
    run_with_timeout,
)

pytestmark = pytest.mark.public


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
            cwd=Path("."),
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
                cwd=Path("."),
                timeout_seconds=5,
                backend=backend,
                heartbeat_interval_seconds=0,
                heartbeat_callback=lambda _event: None,
            )


if __name__ == "__main__":
    unittest.main()
