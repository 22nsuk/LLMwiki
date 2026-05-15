from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.command_runtime import FakeProcess, FakeProcessBackend, run_with_timeout


pytestmark = pytest.mark.public


class CommandRuntimeHeartbeatTests(unittest.TestCase):
    def test_completed_process_reports_heartbeat_fields(self) -> None:
        process = FakeProcess(communicate_side_effect=[("ok\n", "")])
        process.returncode = 0
        backend = FakeProcessBackend(process)

        with mock.patch(
            "ops.scripts.command_runtime.time.perf_counter",
            side_effect=[0.0, 0.01, 310.0],
        ):
            result = run_with_timeout(
                ["python", "-c", "print('ok')"],
                cwd=Path("."),
                timeout_seconds=600,
                backend=backend,
                heartbeat_interval_seconds=300,
            )

        self.assertEqual(result.heartbeat_interval_seconds, 300)
        self.assertEqual(result.heartbeat_emitted_count, 1)
        self.assertEqual(result.last_heartbeat_elapsed_seconds, 310.0)
        self.assertEqual(result.heartbeat_status, "completed")

    def test_default_heartbeat_is_disabled(self) -> None:
        process = FakeProcess(communicate_side_effect=[("ok\n", "")])
        process.returncode = 0
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('ok')"],
            cwd=Path("."),
            timeout_seconds=5,
            backend=backend,
        )

        self.assertEqual(result.heartbeat_interval_seconds, 0)
        self.assertEqual(result.heartbeat_emitted_count, 0)
        self.assertEqual(result.last_heartbeat_elapsed_seconds, 0.0)
        self.assertEqual(result.heartbeat_status, "disabled")

    def test_rejects_negative_heartbeat_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "heartbeat_interval_seconds must be >= 0"):
            run_with_timeout(
                ["python", "-c", "print('ok')"],
                cwd=Path("."),
                timeout_seconds=5,
                heartbeat_interval_seconds=-1,
            )


if __name__ == "__main__":
    unittest.main()
