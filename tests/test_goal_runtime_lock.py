from __future__ import annotations

import datetime as dt
import json
import os
import signal
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.goal_runtime_lock import (
    GoalRuntimeWorkspaceLockActive,
    acquire_workspace_lock,
    inspect_workspace_lock,
    release_workspace_lock,
    stop_workspace_lock,
    update_workspace_lock_child,
)

pytestmark = pytest.mark.public


class GoalRuntimeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        self.lock_path = "build/goal-runs/goal-runtime.lock.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_active_workspace_lock_blocks_second_goal_runtime(self) -> None:
        lock_file = self.vault / self.lock_path
        lock_file.parent.mkdir(parents=True)
        lock_file.write_text(
            json.dumps(
                {
                    "artifact_kind": "goal_runtime_workspace_lock",
                    "producer": "ops.scripts.goal_runtime_lock",
                    "run_id": "active-run",
                    "pid": os.getpid(),
                    "pgid": 0,
                    "child_pid": 0,
                    "child_pgid": 0,
                    "token": "active",
                }
            ),
            encoding="utf-8",
        )

        status = inspect_workspace_lock(self.vault, lock_path=self.lock_path)

        self.assertEqual(status["status"], "active")
        self.assertTrue(status["active"])
        with self.assertRaises(GoalRuntimeWorkspaceLockActive):
            acquire_workspace_lock(
                self.vault,
                lock_path=self.lock_path,
                run_id="next-run",
                runtime_mode="self_improvement_loop",
                started_at="2026-05-21T00:00:00Z",
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
            )

    def test_stale_workspace_lock_is_replaced_and_released(self) -> None:
        lock_file = self.vault / self.lock_path
        lock_file.parent.mkdir(parents=True)
        lock_file.write_text(
            json.dumps({"run_id": "old-run", "pid": -1, "pgid": 0, "token": "stale"}),
            encoding="utf-8",
        )

        lock = acquire_workspace_lock(
            self.vault,
            lock_path=self.lock_path,
            run_id="fresh-run",
            runtime_mode="self_improvement_loop",
            started_at="2026-05-21T00:00:00Z",
            command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
        )
        payload = json.loads(lock_file.read_text(encoding="utf-8"))

        self.assertEqual(payload["run_id"], "fresh-run")
        self.assertEqual(payload["artifact_kind"], "goal_runtime_workspace_lock")
        release_workspace_lock(lock)
        self.assertFalse(lock_file.exists())

    def test_stop_prefers_recorded_child_process_group(self) -> None:
        lock = acquire_workspace_lock(
            self.vault,
            lock_path=self.lock_path,
            run_id="active-run",
            runtime_mode="self_improvement_loop",
            started_at=dt.datetime(2026, 5, 21, tzinfo=dt.UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
        )
        update_workspace_lock_child(lock, child_pid=4321, child_pgid=9876)
        signals: list[tuple[int, int]] = []

        result = stop_workspace_lock(
            self.vault,
            lock_path=self.lock_path,
            process_is_running=lambda pid: False,
            process_group_is_running=lambda pgid: pgid == 9876,
            signal_pid=lambda pid, sig: signals.append((pid, sig)),
            signal_pgid=lambda pgid, sig: signals.append((pgid, sig)),
        )

        self.assertEqual(result["status"], "stop_requested")
        self.assertEqual(
            result["target"],
            {"type": "child_process_group", "field": "child_pgid", "id": 9876},
        )
        self.assertEqual(signals, [(9876, int(signal.SIGTERM))])
        release_workspace_lock(lock)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
