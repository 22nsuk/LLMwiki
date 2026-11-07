from __future__ import annotations

import datetime as dt
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.codex_goal_client import set_goal
from ops.scripts.core.command_runtime import (
    FakeProcess,
    FakeProcessBackend,
    ProcessCleanupError,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism.goal_run_status import (
    GoalRunStatusRequest,
    build_report as build_goal_run_status_report,
    write_report as write_goal_run_status_report,
)
from ops.scripts.mechanism.goal_runtime_lock import (
    cleanup_stale_workspace_lock,
    inspect_workspace_lock,
    main as workspace_lock_main,
    stop_workspace_lock,
)
from ops.scripts.mechanism.goal_runtime_runner import (
    CheckpointCommandExecution,
    GoalRuntimeRunnerRequest,
    run_goal_runtime_command,
)
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_codex_goal_contract import sample_goal_contract

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]


class SteppedClock:
    def __init__(self, values: list[float]) -> None:
        self.values = list(values)
        self.last = self.values[-1] if self.values else 0.0

    def __call__(self) -> float:
        if self.values:
            self.last = self.values.pop(0)
        return self.last


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC),
    )


def context_at(hour: int, minute: int) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 17, hour, minute, tzinfo=dt.UTC),
    )


class GoalRuntimeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        for rel_path in (
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/core/codex_goal_client.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_backoff.py",
            "ops/scripts/mechanism/goal_runtime_maintenance.py",
            "ops/scripts/mechanism/goal_runtime_certificate.py",
            "ops/scripts/mechanism/goal_runtime_lock.py",
            "ops/scripts/mechanism/goal_runtime_resume.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
        ):
            self._copy_support_file(rel_path)
        set_goal(sample_goal_contract(), vault=self.vault)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def test_status_or_registration_error_cleans_child_before_unlocking(self) -> None:
        for stage in ("registration", "heartbeat"):
            with self.subTest(stage=stage):
                error = OSError("cannot write child status")
                events = [subprocess.TimeoutExpired(cmd=["python"], timeout=1)] if stage == "heartbeat" else []
                process = FakeProcess(communicate_side_effect=[*events, ("", "")])
                backend = FakeProcessBackend(process)
                target = "update_workspace_lock_child" if stage == "registration" else "_write_status_snapshot"
                effects = error if stage == "registration" else [None, error]
                with patch(f"ops.scripts.mechanism.goal_runtime_runner.{target}", side_effect=effects), self.assertRaises(OSError) as raised:
                    run_goal_runtime_command(GoalRuntimeRunnerRequest(
                        vault=self.vault, command_argv=["python"], run_id=f"error-{stage}",
                        goal_contract_path="ops/reports/codex-goal-contract.json", context=fixed_context(),
                        backend=backend, heartbeat_interval_seconds=1, timeout_seconds=5,
                        monotonic_clock=SteppedClock([0, 0, 0, 0, 1]),
                    ))
                self.assertIs(raised.exception, error)
                self.assertEqual(backend.signal_calls, [(process.pid, int(backend.kill_signal()))])
                self.assertEqual(process.communicate_calls[-1]["timeout"], 2.0)
                self.assertFalse((self.vault / "build/goal-runs/goal-runtime.lock.json").exists())
                self.assertFalse(list((self.vault / "runs").glob("*/runner.lock.json")))

    def test_cleanup_failure_retains_workspace_and_runner_locks(self) -> None:
        error = OSError("heartbeat status write failed")
        process = FakeProcess(communicate_side_effect=[
            subprocess.TimeoutExpired(cmd=["python"], timeout=1),
            subprocess.TimeoutExpired(cmd=["python"], timeout=2),
        ])
        with (
            patch("ops.scripts.mechanism.goal_runtime_runner._write_status_snapshot", side_effect=[None, error]),
            self.assertRaises(ProcessCleanupError) as raised,
        ):
            run_goal_runtime_command(GoalRuntimeRunnerRequest(
                vault=self.vault, command_argv=["python"], run_id="cleanup-error",
                goal_contract_path="ops/reports/codex-goal-contract.json", context=fixed_context(),
                backend=FakeProcessBackend(process), heartbeat_interval_seconds=1, timeout_seconds=5,
                monotonic_clock=SteppedClock([0, 0, 0, 0, 1]),
            ))
        self.assertIs(raised.exception.__cause__, error)
        self.assertTrue((self.vault / "build/goal-runs/goal-runtime.lock.json").exists())
        self.assertEqual(len(list((self.vault / "runs").glob("*/runner.lock.json"))), 1)

    def test_registration_marker_write_failure_prevents_launch(self) -> None:
        backend = FakeProcessBackend(FakeProcess())
        write_text = Path.write_text

        def fail_marker(path, data, *args, **kwargs):
            if path.name == "goal-runtime.lock.json" and json.loads(data).get("child_registration_pending"):
                raise OSError("cannot persist child registration intent")
            return write_text(path, data, *args, **kwargs)

        with patch.object(Path, "write_text", fail_marker), self.assertRaisesRegex(OSError, "registration intent"):
            run_goal_runtime_command(GoalRuntimeRunnerRequest(
                vault=self.vault, command_argv=["python"], run_id="marker-write-failure",
                goal_contract_path="ops/reports/codex-goal-contract.json", context=fixed_context(),
                backend=backend,
            ))
        self.assertEqual(backend.start_calls, [])
        self.assertFalse((self.vault / "build/goal-runs/goal-runtime.lock.json").exists())
        self.assertFalse(list((self.vault / "runs").glob("*/runner.lock.json")))

    @unittest.skipUnless(Path("/proc/self/stat").is_file(), "Linux procfs verifies orphan cleanup")
    def test_unregistered_child_blocks_restart_after_runner_exits(self) -> None:
        child = None
        script = textwrap.dedent("""
            import sys
            from pathlib import Path
            from unittest.mock import patch
            from ops.scripts.core.command_runtime import PosixProcessBackend
            from ops.scripts.mechanism.goal_runtime_runner import GoalRuntimeRunnerRequest, run_goal_runtime_command

            vault = Path(sys.argv[1])
            class UnkillableBackend(PosixProcessBackend):
                def start(self, *args, **kwargs):
                    process = super().start(*args, **kwargs)
                    (vault / "child.pid").write_text(str(process.pid))
                    return process

                def send_signal(self, process, sig):
                    raise PermissionError("injected termination failure")

            with patch("ops.scripts.mechanism.goal_runtime_runner.update_workspace_lock_child",
                       side_effect=OSError("injected registration failure")):
                run_goal_runtime_command(GoalRuntimeRunnerRequest(
                    vault=vault, command_argv=[sys.executable, "-c", "import time; time.sleep(60)"],
                    run_id="registration-failure", goal_contract_path="ops/reports/codex-goal-contract.json",
                    backend=UnkillableBackend(), timeout_seconds=5,
                ))
        """)
        try:
            result = subprocess.run(
                [sys.executable, "-c", script, str(self.vault)],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
            )
            child = int((self.vault / "child.pid").read_text())
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ProcessCleanupError", result.stderr)
            os.kill(child, 0)  # The child outlives the failed runner.
            lock_path = self.vault / "build/goal-runs/goal-runtime.lock.json"
            original_lock = lock_path.read_bytes()
            self.assertEqual(json.loads(original_lock)["child_pid"], 0)
            self.assertTrue(inspect_workspace_lock(self.vault)["active"])
            self.assertFalse(cleanup_stale_workspace_lock(self.vault))
            self.assertEqual(workspace_lock_main(["check", "--vault", str(self.vault), "--cleanup-stale"]), 75)
            self.assertEqual(stop_workspace_lock(self.vault)["status"], "blocked")
            for run_id in ("registration-failure", "different-run"):
                with self.subTest(run_id=run_id):
                    backend = FakeProcessBackend(FakeProcess())
                    self.assertEqual(run_goal_runtime_command(GoalRuntimeRunnerRequest(
                        vault=self.vault, command_argv=["python"], run_id=run_id,
                        goal_contract_path="ops/reports/codex-goal-contract.json",
                        context=fixed_context(), backend=backend,
                    )), 75)
                    self.assertEqual(backend.start_calls, [])
            self.assertEqual(lock_path.read_bytes(), original_lock)
        finally:
            pid_path = self.vault / "child.pid"
            if child is None and pid_path.exists():
                child = int(pid_path.read_text())
            if child is not None:
                with suppress(ProcessLookupError):
                    os.killpg(child, signal.SIGKILL)
                deadline = time.monotonic() + 3
                while True:
                    try:
                        state = Path(f"/proc/{child}/stat").read_text().rsplit(")", 1)[1].split()[0]
                    except (FileNotFoundError, ProcessLookupError):
                        break
                    if state == "Z":
                        break
                    self.assertLess(time.monotonic(), deadline, "orphan survived test cleanup")
                    time.sleep(0.01)

    def test_signal_cleanup_failure_retains_workspace_and_runner_locks(self) -> None:
        installed = {}

        def install(signum, handler):
            if callable(handler):
                installed[signum] = handler
            return signal.SIG_DFL

        def interrupt(_event):
            installed[signal.SIGTERM](int(signal.SIGTERM), None)

        process = FakeProcess(communicate_side_effect=[
            subprocess.TimeoutExpired(cmd=["python"], timeout=2),
        ])
        backend = FakeProcessBackend(process)
        with (
            patch("ops.scripts.core.command_runtime.signal.signal", side_effect=install),
            patch("ops.scripts.core.command_runtime._communicate_with_optional_heartbeats", side_effect=lambda **_: interrupt(None)),
            self.assertRaises(ProcessCleanupError) as raised,
        ):
            run_goal_runtime_command(GoalRuntimeRunnerRequest(
                vault=self.vault, command_argv=["python"], run_id="signal-cleanup-error",
                goal_contract_path="ops/reports/codex-goal-contract.json", context=fixed_context(),
                backend=backend, heartbeat_interval_seconds=1, timeout_seconds=5,
            ))
        self.assertIsInstance(raised.exception.__cause__, SystemExit)
        self.assertEqual(raised.exception.__cause__.code, 128 + int(signal.SIGTERM))
        self.assertEqual(backend.signal_calls, [(process.pid, int(backend.kill_signal()))])
        self.assertTrue((self.vault / "build/goal-runs/goal-runtime.lock.json").exists())
        self.assertEqual(len(list((self.vault / "runs").glob("*/runner.lock.json"))), 1)

    def test_runner_writes_status_heartbeat_audit_and_final_result(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                ('{"ok": true}\n', ""),
            ]
        )
        process.returncode = 0
        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=FakeProcessBackend(process),
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 2.0]),
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            (self.vault / "tmp" / "session-result.json").read_text(encoding="utf-8"),
            '{"ok": true}\n',
        )
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["run"]["status"], "completed")
        self.assertEqual(status["run"]["started_at"], "2026-05-17T12:00:00Z")
        self.assertEqual(status["run"]["completed_at"], "2026-05-17T12:00:02Z")
        self.assertEqual(status["observability"]["last_command_heartbeat_at"], "2026-05-17T12:00:02Z")
        self.assertEqual(status["observability"]["command_observation_mode"], "process_heartbeat")
        self.assertEqual(status["observability"]["command_heartbeat_count"], 2)
        self.assertEqual(status["observability"]["command_timeout_seconds"], 5)
        self.assertEqual(status["observability"]["last_command_returncode"], 0)
        self.assertFalse(status["observability"]["last_command_timed_out"])
        self.assertEqual(status["observability"]["last_command_termination_reason"], "completed")
        audit_events = [
            json.loads(line)
            for line in (
                self.vault / "runs" / "goal-20260517-trial" / "audit-log.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(audit_events), 4)
        self.assertEqual(
            [event["run_status"] for event in audit_events],
            ["running", "running", "running", "completed"],
        )
        self.assertEqual(audit_events[-1]["command_heartbeat_count"], 2)
        self.assertEqual(audit_events[-1]["command_observation_mode"], "process_heartbeat")
        self.assertEqual(audit_events[-1]["last_command_termination_reason"], "completed")
        self.assertEqual(audit_events[-1]["writer"], "ops.scripts.goal_runtime_runner")
        self.assertEqual(
            sorted({event["generated_at"] for event in audit_events}),
            [
                "2026-05-17T12:00:00Z",
                "2026-05-17T12:00:01Z",
                "2026-05-17T12:00:02Z",
            ],
        )

    def test_runner_final_status_clears_prior_falsey_observability(self) -> None:
        prior = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="running",
                started_at="2026-05-17T11:50:00Z",
                last_heartbeat_at="2026-05-17T11:50:00Z",
                last_checkpoint_at="2026-05-17T11:50:00Z",
                last_command_heartbeat_at="2026-05-17T11:50:00Z",
                command_observation_mode="process_heartbeat",
                command_heartbeat_count=4,
                command_timeout_seconds=99,
                last_command_returncode=7,
                last_command_timed_out=True,
                resume_from_checkpoint=True,
                resume_command="python stale-resume.py",
                context=context_at(11, 50),
            )
        )
        write_goal_run_status_report(self.vault, prior)
        process = FakeProcess(communicate_side_effect=[('{"ok": true}\n', "")])
        process.returncode = 0

        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=FakeProcessBackend(process),
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0]),
            )
        )

        self.assertEqual(exit_code, 0)
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        observability = status["observability"]
        self.assertEqual(status["run"]["status"], "completed")
        self.assertEqual(observability["command_heartbeat_count"], 0)
        self.assertEqual(observability["command_timeout_seconds"], 5)
        self.assertEqual(observability["last_command_returncode"], 0)
        self.assertFalse(observability["last_command_timed_out"])
        self.assertEqual(observability["last_command_termination_reason"], "completed")
        self.assertFalse(observability["resume_from_checkpoint"])
        self.assertEqual(
            observability["resume_command"],
            "python -m ops.scripts.auto_improve_loop",
        )

    def test_runner_finalizes_failed_command_status_and_exit_code(self) -> None:
        process = FakeProcess(communicate_side_effect=[("", "boom\n")])
        process.returncode = 9
        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                resume_from_checkpoint=True,
                context=fixed_context(),
                backend=FakeProcessBackend(process),
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0]),
            )
        )

        self.assertEqual(exit_code, 9)
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["run"]["status"], "failed")
        self.assertEqual(status["observability"]["resume_from_checkpoint"], True)
        self.assertEqual(status["observability"]["command_observation_mode"], "process_heartbeat")
        self.assertEqual(status["observability"]["command_heartbeat_count"], 0)
        self.assertEqual(status["observability"]["last_command_returncode"], 9)
        self.assertEqual(status["observability"]["last_command_termination_reason"], "completed")
        self.assertEqual(
            status["observability"]["resume_command"],
            "python -m ops.scripts.auto_improve_loop",
        )
        audit_events = [
            json.loads(line)
            for line in (
                self.vault / "runs" / "goal-20260517-trial" / "audit-log.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["run_status"] for event in audit_events], ["running", "failed"])
        self.assertEqual(audit_events[-1]["writer"], "ops.scripts.goal_runtime_runner")

    def test_runner_rejects_duplicate_run_id_before_status_overwrite(self) -> None:
        lock_path = self.vault / "runs" / "goal-20260517-trial" / "runner.lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps({"pid": os.getpid(), "run_id": "20260517-trial", "token": "active"}),
            encoding="utf-8",
        )
        process = FakeProcess(communicate_side_effect=[('{"ok": true}\n', "")])
        backend = FakeProcessBackend(process)

        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=backend,
                monotonic_clock=SteppedClock([0.0]),
            )
        )

        self.assertEqual(exit_code, 75)
        self.assertEqual(backend.start_calls, [])
        self.assertFalse((self.vault / "ops" / "reports" / "goal-run-status.json").exists())
        self.assertEqual(
            json.loads(lock_path.read_text(encoding="utf-8")),
            {"pid": os.getpid(), "run_id": "20260517-trial", "token": "active"},
        )

    def test_runner_rejects_active_workspace_lock_before_status_overwrite(self) -> None:
        lock_path = self.vault / "build" / "goal-runs" / "goal-runtime.lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps(
                {
                    "artifact_kind": "goal_runtime_workspace_lock",
                    "producer": "ops.scripts.goal_runtime_lock",
                    "pid": os.getpid(),
                    "pgid": 0,
                    "child_pid": 0,
                    "child_pgid": 0,
                    "run_id": "other-run",
                    "token": "active",
                }
            ),
            encoding="utf-8",
        )
        process = FakeProcess(communicate_side_effect=[('{"ok": true}\n', "")])
        backend = FakeProcessBackend(process)

        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=backend,
                monotonic_clock=SteppedClock([0.0]),
            )
        )

        self.assertEqual(exit_code, 75)
        self.assertEqual(backend.start_calls, [])
        self.assertFalse((self.vault / "ops" / "reports" / "goal-run-status.json").exists())

    def test_runner_replaces_stale_run_id_lock(self) -> None:
        lock_path = self.vault / "runs" / "goal-20260517-trial" / "runner.lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps({"pid": -1, "run_id": "20260517-trial", "token": "stale"}),
            encoding="utf-8",
        )
        process = FakeProcess(communicate_side_effect=[('{"ok": true}\n', "")])
        process.returncode = 0

        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=FakeProcessBackend(process),
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0]),
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertFalse(lock_path.exists())
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["run"]["status"], "completed")

    def test_runner_records_signal_returncode_without_schema_failure(self) -> None:
        process = FakeProcess(communicate_side_effect=[("", "terminated\n")])
        process.returncode = -15
        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=FakeProcessBackend(process),
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0]),
            )
        )

        self.assertEqual(exit_code, -15)
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["run"]["status"], "failed")
        self.assertEqual(status["observability"]["last_command_returncode"], -15)
        self.assertFalse(status["observability"]["last_command_timed_out"])
        self.assertEqual(status["observability"]["last_command_termination_reason"], "completed")
        audit_events = [
            json.loads(line)
            for line in (
                self.vault / "runs" / "goal-20260517-trial" / "audit-log.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["run_status"] for event in audit_events], ["running", "failed"])
        self.assertEqual(audit_events[-1]["last_command_returncode"], -15)

    def test_runner_preserves_usage_limit_retry_after_in_goal_status(self) -> None:
        run_id = "run-usage-limited"
        run_dir = self.vault / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "worker.stderr.txt").write_text(
            "ERROR: You've hit your usage limit. Try again at May 17th, 2026 12:29 PM.\n",
            encoding="utf-8",
        )
        (run_dir / "worker-executor-report.json").write_text(
            json.dumps(
                {
                    "role": "worker",
                    "status": "fail",
                    "artifacts": {"stderr": f"runs/{run_id}/worker.stderr.txt"},
                    "diagnostics": {
                        "notes": [
                            "codex exec blocked by usage limit; "
                            "retry_after=May 17th, 2026 12:29 PM"
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        process = FakeProcess(
            communicate_side_effect=[
                (
                    json.dumps(
                        {
                            "stop_reason": "executor_usage_limited",
                            "run_ids": [run_id],
                        }
                    )
                    + "\n",
                    "",
                )
            ]
        )
        process.returncode = 0

        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-trial",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=1,
                checkpoint_interval_seconds=2,
                timeout_seconds=5,
                context=fixed_context(),
                backend=FakeProcessBackend(process),
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0]),
            )
        )

        self.assertEqual(exit_code, 0)
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["observability"]["last_backoff_until"], "2026-05-17T12:29:00Z")
        self.assertEqual(status["health"]["backoff_status"], "active")
        self.assertEqual(
            status["observability"]["backoff_reason"],
            "executor_usage_limited; retry_after_source=May 17th, 2026 12:29 PM",
        )

    def test_runner_executes_due_periodic_checkpoint_commands_before_status_write(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                ('{"ok": true}\n', ""),
            ]
        )
        process.returncode = 0
        executed_commands: list[str] = []

        def checkpoint_executor(command: str, observed_at: dt.datetime) -> CheckpointCommandExecution:
            executed_commands.append(command)
            reports = self.vault / "ops" / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            if command == "make auto-improve-readiness-report-body":
                (reports / "auto-improve-readiness.json").write_text(
                    json.dumps({"generated_at": observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")}),
                    encoding="utf-8",
                )
            if command == "make session-synopsis":
                (reports / "session-synopsis.json").write_text(
                    json.dumps({"generated_at": observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")}),
                    encoding="utf-8",
                )
            return CheckpointCommandExecution(
                command=command,
                status="pass",
                returncode=0,
                timed_out=False,
                timeout_seconds=900,
            )

        exit_code = run_goal_runtime_command(
            GoalRuntimeRunnerRequest(
                vault=self.vault,
                command_argv=["python", "-m", "ops.scripts.auto_improve_loop"],
                run_id="20260517-ramp",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                result_out="tmp/session-result.json",
                heartbeat_interval_seconds=21600,
                checkpoint_interval_seconds=21600,
                timeout_seconds=21610,
                context=context_at(5, 0),
                backend=FakeProcessBackend(process),
                checkpoint_command_executor=checkpoint_executor,
                monotonic_clock=SteppedClock([0.0, 0.0, 0.0, 21600.0, 21600.0, 21601.0]),
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            executed_commands,
            [
                "make auto-improve-readiness-report-body",
                "make session-synopsis",
                "make static",
            ],
        )
        status = json.loads(
            (self.vault / "ops" / "reports" / "goal-run-status.json").read_text(encoding="utf-8")
        )
        checkpoint_6h = status["periodic_evidence"]["checkpoints"][0]
        self.assertEqual(checkpoint_6h["status"], "observed")
        self.assertEqual(checkpoint_6h["command_run"]["status"], "pass")
        command_events = [
            json.loads(line)
            for line in (
                self.vault
                / "runs"
                / "goal-20260517-ramp"
                / "checkpoint-command-events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(command_events), 1)
        self.assertEqual(command_events[0]["checkpoint_id"], "checkpoint_6h")
        self.assertEqual(command_events[0]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
