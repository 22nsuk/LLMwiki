from __future__ import annotations

import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.command_runtime import (
    FakeProcess,
    FakeProcessBackend,
    run_with_timeout,
)

from ops.scripts import command_runtime


class CompletingOnDrainFakeProcess(FakeProcess):
    def communicate(
        self,
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        stdout, stderr = super().communicate(input=input, timeout=timeout)
        if timeout == 0:
            self.returncode = 0
        return stdout, stderr


class CommandRuntimeTests(unittest.TestCase):
    def test_run_with_timeout_returns_completed_process_result(self) -> None:
        process = FakeProcess(communicate_side_effect=[("ok\n", "")])
        process.returncode = 0
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('ok')"],
            cwd=Path("."),
            timeout_seconds=5,
            backend=backend,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok\n")
        self.assertFalse(result.timed_out)
        self.assertEqual(result.timeout_seconds, 5)
        self.assertEqual(result.termination_reason, "completed")
        self.assertTrue(result.launch_succeeded)
        self.assertEqual(result.signal_sent, "none")
        self.assertEqual(result.final_state_observed, "communicate")
        self.assertTrue(result.stdout_received)
        self.assertTrue(result.stderr_received)
        self.assertGreaterEqual(result.launch_latency_seconds, 0.0)

    def test_run_with_timeout_terminates_timed_out_process(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                subprocess.TimeoutExpired(cmd=["python"], timeout=0),
                ("", ""),
            ],
            poll_side_effect=[None],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "import time; time.sleep(5)"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.timeout_seconds, 1)
        self.assertEqual(result.termination_reason, "execution_timeout")
        self.assertNotEqual(result.signal_sent, "none")

    def test_run_with_timeout_rejects_nonpositive_timeout(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            self.assertRaisesRegex(ValueError, "timeout_seconds must be >= 1"),
        ):
            run_with_timeout(
                ["python", "-c", "print('ok')"],
                cwd=Path(temp_dir),
                timeout_seconds=0,
            )

    def test_run_with_timeout_passes_clean_env_and_python_minus_s_in_hermetic_mode(self) -> None:
        process = FakeProcess(communicate_side_effect=[("ok\n", "")])
        process.returncode = 0
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('ok')"],
            cwd=Path("."),
            timeout_seconds=5,
            backend=backend,
            env={"PATH": "/bin", "PYTHONPATH": "/leak", "CUSTOM": "leak"},
            hermetic=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.args[:3], ["python", "-S", "-c"])
        self.assertEqual(backend.start_calls[0]["env"], {"PATH": "/bin", "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"})

    def test_signal_process_uses_terminate_on_windows_sigterm(self) -> None:
        process = mock.Mock()

        with mock.patch.object(command_runtime.os, "name", "nt"):
            signal_sent = command_runtime._signal_process(process, signal.SIGTERM)

        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()
        self.assertEqual(signal_sent, "terminate")

    def test_signal_process_uses_kill_on_windows_nonsigterm(self) -> None:
        process = mock.Mock()

        with mock.patch.object(command_runtime.os, "name", "nt"):
            signal_sent = command_runtime._signal_process(process, signal.SIGINT)

        process.kill.assert_called_once_with()
        process.terminate.assert_not_called()
        self.assertEqual(signal_sent, "kill")

    def test_signal_process_uses_killpg_on_posix(self) -> None:
        process = mock.Mock()
        process.pid = 321

        with (
            mock.patch.object(command_runtime.os, "name", "posix"),
            mock.patch.object(command_runtime.os, "killpg", create=True) as killpg,
        ):
            signal_sent = command_runtime._signal_process(process, signal.SIGTERM)

        killpg.assert_called_once_with(321, int(signal.SIGTERM))
        self.assertEqual(signal_sent, "sigterm")

    def test_terminate_timed_out_process_escalates_after_grace_timeout(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=2.0),
                subprocess.TimeoutExpired(cmd=["python"], timeout=2.0),
                ("late-stdout", "late-stderr"),
            ],
            poll_side_effect=[None],
        )
        backend = FakeProcessBackend(process)

        stdout, stderr = command_runtime._terminate_timed_out_process(
            process,
            grace_seconds=2.0,
            backend=backend,
        )

        self.assertEqual((stdout, stderr), ("late-stdout", "late-stderr"))
        self.assertEqual(
            backend.signal_calls,
            [
                (1, int(signal.SIGTERM)),
                (1, int(getattr(signal, "SIGKILL", signal.SIGTERM))),
            ],
        )

    def test_run_with_timeout_enables_start_new_session_on_posix(self) -> None:
        process = mock.Mock()
        process.communicate.return_value = ("ok\n", "")
        process.returncode = 0

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(command_runtime.os, "name", "posix"),
            mock.patch("ops.scripts.command_runtime.subprocess.Popen", return_value=process) as popen,
        ):
            result = command_runtime.run_with_timeout(
                ["python", "-c", "print('ok')"],
                cwd=Path(temp_dir),
                timeout_seconds=5,
            )

        self.assertEqual(result.termination_reason, "completed")
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(popen.call_args.kwargs["errors"], "replace")

    def test_run_with_timeout_disables_start_new_session_on_windows(self) -> None:
        process = mock.Mock()
        process.communicate.return_value = ("ok\n", "")
        process.returncode = 0

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(command_runtime.os, "name", "nt"),
            mock.patch("ops.scripts.command_runtime.subprocess.Popen", return_value=process) as popen,
        ):
            result = command_runtime.run_with_timeout(
                ["python", "-c", "print('ok')"],
                cwd=Path(temp_dir),
                timeout_seconds=5,
            )

        self.assertEqual(result.termination_reason, "completed")
        self.assertFalse(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(popen.call_args.kwargs["errors"], "replace")

    def test_run_with_timeout_rechecks_poll_before_signaling_timeout_race(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                ("race-stdout", ""),
            ],
            poll_side_effect=[0],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('race')"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertFalse(result.timed_out)
        self.assertEqual(result.signal_sent, "none")
        self.assertEqual(result.final_state_observed, "poll_before_signal")
        self.assertEqual(backend.signal_calls, [])

    def test_run_with_timeout_treats_finalize_poll_recovery_as_completed(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                subprocess.TimeoutExpired(cmd=["python"], timeout=0),
                ("race-stdout", ""),
            ],
            poll_side_effect=[None, None, 0],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('race')"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertFalse(result.timed_out)
        self.assertEqual(result.termination_reason, "completed")
        self.assertEqual(result.signal_sent, "none")
        self.assertEqual(result.final_state_observed, "poll_before_signal")
        self.assertEqual(backend.signal_calls, [])

    def test_run_with_timeout_drains_ready_eof_before_signal(self) -> None:
        process = CompletingOnDrainFakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                ("race-stdout", ""),
            ],
            poll_side_effect=[None, None],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('race')"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.termination_reason, "signal_race_recovered")
        self.assertEqual(result.signal_sent, "none")
        self.assertEqual(result.final_state_observed, "signal_race_recovered")
        self.assertEqual(backend.signal_calls, [])

    def test_run_with_timeout_records_term_only_drain_path(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                subprocess.TimeoutExpired(cmd=["python"], timeout=0),
                ("late-stdout", "late-stderr"),
            ],
            poll_side_effect=[None],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('late')"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertTrue(result.timed_out)
        self.assertEqual(result.termination_reason, "timeout_after_output")
        self.assertEqual(result.signal_sent, "sigterm")
        self.assertEqual(result.final_state_observed, "drain_after_signal")
        self.assertEqual(backend.signal_calls, [(1, int(signal.SIGTERM))])

    def test_run_with_timeout_records_poll_after_grace_when_process_exits_after_term(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                subprocess.TimeoutExpired(cmd=["python"], timeout=0),
                subprocess.TimeoutExpired(cmd=["python"], timeout=2.0),
                ("grace-stdout", ""),
            ],
            poll_side_effect=[None, None, None, 0],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('grace')"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertTrue(result.timed_out)
        self.assertEqual(result.termination_reason, "timeout_after_output")
        self.assertEqual(result.signal_sent, "sigterm")
        self.assertEqual(result.final_state_observed, "poll_after_grace")
        self.assertEqual(backend.signal_calls, [(1, int(signal.SIGTERM))])

    def test_run_with_timeout_escalates_to_kill_after_grace_timeout(self) -> None:
        process = FakeProcess(
            communicate_side_effect=[
                subprocess.TimeoutExpired(cmd=["python"], timeout=1),
                subprocess.TimeoutExpired(cmd=["python"], timeout=0),
                subprocess.TimeoutExpired(cmd=["python"], timeout=2.0),
                ("killed-stdout", "killed-stderr"),
            ],
            poll_side_effect=[None, None],
        )
        backend = FakeProcessBackend(process)

        result = run_with_timeout(
            ["python", "-c", "print('kill')"],
            cwd=Path("."),
            timeout_seconds=1,
            backend=backend,
        )

        self.assertTrue(result.timed_out)
        self.assertEqual(result.termination_reason, "timeout_after_output")
        self.assertEqual(result.signal_sent, "sigkill")
        self.assertEqual(result.final_state_observed, "drain_after_kill")
        self.assertEqual(
            backend.signal_calls,
            [
                (1, int(signal.SIGTERM)),
                (1, int(getattr(signal, "SIGKILL", signal.SIGTERM))),
            ],
        )


if __name__ == "__main__":
    unittest.main()
