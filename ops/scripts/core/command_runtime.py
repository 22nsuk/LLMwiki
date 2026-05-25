from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

SignalValue = int | signal.Signals
TIMEOUT_GRACE_SECONDS = 2.0
PosixKillpg = Callable[[int, int], None]
TIMEOUT_RECOVERY_STATES = {"poll_before_signal", "signal_race_recovered"}
TIMEOUT_TERMINATION_REASONS = {
    "execution_timeout",
    "timeout_after_output",
    "startup_timeout",
}
CommandHeartbeatCallback = Callable[["CommandHeartbeat"], None]


class _SyntheticKillSignal(int):
    """Sentinel used by FakeProcessBackend when SIGKILL is unavailable."""


@dataclass(frozen=True)
class CommandHeartbeat:
    args: list[str]
    heartbeat_index: int
    elapsed_seconds: float
    timeout_seconds: int
    quiet_seconds: int
    last_stdout_at: str = ""
    last_stderr_at: str = ""
    last_artifact_touch_at: str = ""
    observation_mode: str = "process_poll"


@dataclass
class _HeartbeatState:
    heartbeat_count: int = 0
    quiet_seconds: int = 0


@dataclass(frozen=True)
class TimedProcessResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    timeout_seconds: int
    termination_reason: str
    launch_succeeded: bool = True
    signal_sent: str = "none"
    final_state_observed: str = ""
    stdout_received: bool = False
    stderr_received: bool = False
    launch_latency_seconds: float = 0.0
    heartbeat_count: int = 0
    heartbeat_interval_seconds: int = 0
    quiet_seconds: int = 0
    last_stdout_at: str = ""
    last_stderr_at: str = ""
    last_artifact_touch_at: str = ""
    observation_mode: str = "communicate"


class ProcessHandle(Protocol):
    pid: int
    returncode: int | None

    def communicate(
        self,
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]: ...

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class ProcessBackend(Protocol):
    start_new_session: bool

    def start(
        self,
        argv: list[str],
        *,
        cwd: Path,
        input_text: str | None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle: ...

    def send_signal(self, process: ProcessHandle, sig: SignalValue) -> str: ...

    def kill_signal(self) -> SignalValue: ...


class PosixProcessBackend:
    start_new_session = True

    def start(
        self,
        argv: list[str],
        *,
        cwd: Path,
        input_text: str | None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle:
        return subprocess.Popen(
            argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=self.start_new_session,
        )

    def send_signal(self, process: ProcessHandle, sig: SignalValue) -> str:
        killpg = cast(PosixKillpg | None, getattr(os, "killpg", None))
        if killpg is None:
            return "none"
        try:
            killpg(process.pid, int(sig))
        except ProcessLookupError:
            return "none"
        return "sigterm" if int(sig) == int(signal.SIGTERM) else "sigkill"

    def kill_signal(self) -> SignalValue:
        return getattr(signal, "SIGKILL", signal.SIGTERM)


class WindowsProcessBackend:
    start_new_session = False

    def start(
        self,
        argv: list[str],
        *,
        cwd: Path,
        input_text: str | None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle:
        return subprocess.Popen(
            argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=self.start_new_session,
        )

    def send_signal(self, process: ProcessHandle, sig: SignalValue) -> str:
        try:
            if int(sig) == int(signal.SIGTERM):
                process.terminate()
                return "terminate"
            process.kill()
            return "kill"
        except ProcessLookupError:
            return "none"

    def kill_signal(self) -> SignalValue:
        return getattr(signal, "SIGKILL", signal.SIGTERM)


class FakeProcess:
    def __init__(
        self,
        *,
        pid: int = 1,
        communicate_side_effect: list[object] | None = None,
        poll_side_effect: list[int | None] | None = None,
    ) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.communicate_calls: list[dict[str, object]] = []
        self.terminate_calls = 0
        self.kill_calls = 0
        self._communicate_side_effect = list(communicate_side_effect or [])
        self._poll_side_effect = list(poll_side_effect or [])

    def communicate(
        self,
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        self.communicate_calls.append({"input": input, "timeout": timeout})
        if self._communicate_side_effect:
            next_value = self._communicate_side_effect.pop(0)
            if isinstance(next_value, BaseException):
                raise next_value
            if isinstance(next_value, tuple) and len(next_value) == 2:
                stdout, stderr = next_value
                return str(stdout), str(stderr)
            return str(next_value), ""
        return "", ""

    def poll(self) -> int | None:
        if self._poll_side_effect:
            next_value = self._poll_side_effect.pop(0)
            self.returncode = next_value
            return next_value
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


class FakeProcessBackend:
    def __init__(
        self,
        process: FakeProcess,
        *,
        start_new_session: bool = True,
        signal_labels: dict[int, str] | None = None,
    ) -> None:
        self.process = process
        self.start_new_session = start_new_session
        kill_signal = getattr(signal, "SIGKILL", None)
        self._kill_signal: SignalValue = (
            kill_signal if kill_signal is not None else _SyntheticKillSignal(int(signal.SIGTERM))
        )
        if signal_labels is None:
            self.signal_labels = {int(signal.SIGTERM): "sigterm"}
            if kill_signal is not None and int(kill_signal) != int(signal.SIGTERM):
                self.signal_labels[int(kill_signal)] = "sigkill"
        else:
            self.signal_labels = dict(signal_labels)
        self.start_calls: list[dict[str, object]] = []
        self.signal_calls: list[tuple[int, int]] = []

    def start(
        self,
        argv: list[str],
        *,
        cwd: Path,
        input_text: str | None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle:
        self.start_calls.append({"argv": list(argv), "cwd": cwd, "input_text": input_text, "env": env})
        return self.process

    def send_signal(self, process: ProcessHandle, sig: SignalValue) -> str:
        self.signal_calls.append((process.pid, int(sig)))
        if sig is self._kill_signal:
            return "sigkill"
        return self.signal_labels.get(int(sig), f"signal:{int(sig)}")

    def kill_signal(self) -> SignalValue:
        return self._kill_signal


def _default_backend() -> ProcessBackend:
    if os.name == "nt":
        return WindowsProcessBackend()
    return PosixProcessBackend()


def _poll_returncode(process: ProcessHandle) -> int | None:
    try:
        return process.poll()
    except ProcessLookupError:
        return process.returncode


def _normalize_output(value: object) -> str:
    if isinstance(value, str):
        return value
    return "" if value is None else str(value)


def _clean_subprocess_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = base_env or os.environ
    clean: dict[str, str] = {}
    for name in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP"):
        value = source.get(name)
        if value:
            clean[name] = value
    clean.update(
        {
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
        }
    )
    return clean


def _looks_like_python_executable(value: str) -> bool:
    name = Path(value).name.lower()
    return name in {"python", "python3", "py"} or name.startswith("python")


def _python_minus_s_command(argv_list: list[str]) -> list[str]:
    if not argv_list or not _looks_like_python_executable(argv_list[0]):
        return argv_list
    if "-S" in argv_list[1:]:
        return argv_list
    return [argv_list[0], "-S", *argv_list[1:]]


def _result_from_completed_process(
    *,
    argv_list: list[str],
    process: ProcessHandle,
    stdout: object,
    stderr: object,
    timeout_seconds: int,
    timed_out: bool,
    termination_reason: str,
    signal_sent: str,
    final_state_observed: str,
    launch_latency_seconds: float = 0.0,
    heartbeat_count: int = 0,
    heartbeat_interval_seconds: int = 0,
    quiet_seconds: int = 0,
    last_stdout_at: str = "",
    last_stderr_at: str = "",
    last_artifact_touch_at: str = "",
    observation_mode: str = "communicate",
) -> TimedProcessResult:
    normalized_stdout = _normalize_output(stdout)
    normalized_stderr = _normalize_output(stderr)
    normalized_quiet_seconds = quiet_seconds
    if normalized_quiet_seconds == 0 and timed_out and not normalized_stdout and not normalized_stderr:
        normalized_quiet_seconds = timeout_seconds
    return TimedProcessResult(
        args=argv_list,
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=normalized_stdout,
        stderr=normalized_stderr,
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
        termination_reason=termination_reason,
        launch_succeeded=True,
        signal_sent=signal_sent,
        final_state_observed=final_state_observed,
        stdout_received=stdout is not None,
        stderr_received=stderr is not None,
        launch_latency_seconds=launch_latency_seconds,
        heartbeat_count=heartbeat_count,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        quiet_seconds=normalized_quiet_seconds,
        last_stdout_at=last_stdout_at,
        last_stderr_at=last_stderr_at,
        last_artifact_touch_at=last_artifact_touch_at,
        observation_mode=observation_mode,
    )


def _communicate_with_optional_heartbeats(
    *,
    process: ProcessHandle,
    argv_list: list[str],
    input_text: str | None,
    timeout_seconds: int,
    heartbeat_interval_seconds: int | None,
    heartbeat_callback: CommandHeartbeatCallback | None,
    monotonic: Callable[[], float],
    heartbeat_state: _HeartbeatState,
) -> tuple[str, str]:
    if heartbeat_callback is None or heartbeat_interval_seconds is None:
        return process.communicate(input=input_text, timeout=timeout_seconds)

    start = monotonic()
    deadline = start + timeout_seconds
    next_heartbeat_at = start + heartbeat_interval_seconds
    pending_input = input_text
    while True:
        now = monotonic()
        remaining_seconds = deadline - now
        if remaining_seconds <= 0:
            raise subprocess.TimeoutExpired(cmd=argv_list, timeout=timeout_seconds)
        wait_seconds = min(remaining_seconds, max(0.0, next_heartbeat_at - now))
        if wait_seconds <= 0:
            wait_seconds = min(remaining_seconds, float(heartbeat_interval_seconds))
        try:
            stdout, stderr = process.communicate(
                input=pending_input,
                timeout=wait_seconds,
            )
            if not _normalize_output(stdout) and not _normalize_output(stderr):
                heartbeat_state.quiet_seconds = int(max(0.0, monotonic() - start))
            return stdout, stderr
        except subprocess.TimeoutExpired:
            pending_input = None
            now = monotonic()
            if now >= next_heartbeat_at:
                heartbeat_state.heartbeat_count += 1
                heartbeat_state.quiet_seconds = int(max(0.0, now - start))
                heartbeat_callback(
                    CommandHeartbeat(
                        args=argv_list,
                        heartbeat_index=heartbeat_state.heartbeat_count,
                        elapsed_seconds=now - start,
                        timeout_seconds=timeout_seconds,
                        quiet_seconds=heartbeat_state.quiet_seconds,
                    )
                )
                while next_heartbeat_at <= now:
                    next_heartbeat_at += heartbeat_interval_seconds
            if now >= deadline:
                raise


def _signal_process(
    process: ProcessHandle,
    sig: SignalValue,
    *,
    backend: ProcessBackend | None = None,
) -> str:
    active_backend = backend or _default_backend()
    return active_backend.send_signal(process, sig)


def _finalize_timed_out_process(
    process: ProcessHandle,
    *,
    backend: ProcessBackend,
    grace_seconds: float,
) -> tuple[str, str, str, str]:
    returncode = _poll_returncode(process)
    if returncode is not None:
        stdout, stderr = process.communicate()
        return stdout, stderr, "none", "poll_before_signal"

    try:
        stdout, stderr = process.communicate(timeout=0)
        return stdout, stderr, "none", "signal_race_recovered"
    except subprocess.TimeoutExpired:
        returncode = _poll_returncode(process)
        if returncode is not None:
            stdout, stderr = process.communicate()
            return stdout, stderr, "none", "poll_before_signal"

    signal_sent = backend.send_signal(process, signal.SIGTERM)
    try:
        stdout, stderr = process.communicate(timeout=grace_seconds)
        return stdout, stderr, signal_sent, "drain_after_signal"
    except subprocess.TimeoutExpired:
        returncode = _poll_returncode(process)
        if returncode is not None:
            stdout, stderr = process.communicate()
            return stdout, stderr, signal_sent, "poll_after_grace"
        kill_signal = backend.kill_signal()
        kill_sent = backend.send_signal(process, kill_signal)
        if kill_sent != "none":
            signal_sent = kill_sent
        stdout, stderr = process.communicate()
        return stdout, stderr, signal_sent, "drain_after_kill"


def _terminate_timed_out_process(
    process: ProcessHandle,
    *,
    grace_seconds: float,
    backend: ProcessBackend | None = None,
) -> tuple[str, str]:
    stdout, stderr, _signal_sent, _final_state = _finalize_timed_out_process(
        process,
        backend=backend or _default_backend(),
        grace_seconds=grace_seconds,
    )
    return stdout, stderr


def _timeout_termination_reason(
    *,
    timed_out: bool,
    final_state_observed: str,
    stdout: object,
    stderr: object,
    launch_latency_seconds: float,
    timeout_seconds: int,
) -> str:
    if not timed_out:
        if final_state_observed == "signal_race_recovered":
            return "signal_race_recovered"
        return "completed"
    if launch_latency_seconds >= timeout_seconds:
        return "startup_timeout"
    if _normalize_output(stdout) or _normalize_output(stderr):
        return "timeout_after_output"
    return "execution_timeout"


def run_with_timeout(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    input_text: str | None = None,
    backend: ProcessBackend | None = None,
    grace_seconds: float = TIMEOUT_GRACE_SECONDS,
    env: Mapping[str, str] | None = None,
    hermetic: bool = False,
    heartbeat_interval_seconds: int | None = None,
    heartbeat_callback: CommandHeartbeatCallback | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> TimedProcessResult:
    """Run a command with a timeout, measuring launch latency separately.

    Launch latency is captured from backend.start() and exposed in the
    result so that callers can distinguish slow process startup from
    actual execution time.  A separate timeout measurement start point is
    not yet implemented; instrumentation must show an anomaly before
    changing the timeout logic itself.
    """
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be >= 1")
    if heartbeat_interval_seconds is not None and heartbeat_interval_seconds < 1:
        raise ValueError("heartbeat_interval_seconds must be >= 1")

    argv_list = [str(item) for item in argv]
    observation_mode = "process_heartbeat" if heartbeat_callback is not None else "communicate"
    active_heartbeat_interval = heartbeat_interval_seconds
    if heartbeat_callback is not None and active_heartbeat_interval is None:
        active_heartbeat_interval = timeout_seconds
    heartbeat_state = _HeartbeatState()
    monotonic = monotonic_clock or time.perf_counter
    subprocess_env: Mapping[str, str] | None
    if hermetic:
        argv_list = _python_minus_s_command(argv_list)
        subprocess_env = _clean_subprocess_env(env)
    else:
        subprocess_env = env
    active_backend = backend or _default_backend()
    launch_start = monotonic()
    process = active_backend.start(
        argv_list,
        cwd=cwd,
        input_text=input_text,
        env=subprocess_env,
    )
    launch_latency_seconds = monotonic() - launch_start
    try:
        stdout, stderr = _communicate_with_optional_heartbeats(
            process=process,
            argv_list=argv_list,
            input_text=input_text,
            timeout_seconds=timeout_seconds,
            heartbeat_interval_seconds=active_heartbeat_interval,
            heartbeat_callback=heartbeat_callback,
            monotonic=monotonic,
            heartbeat_state=heartbeat_state,
        )
        return _result_from_completed_process(
            argv_list=argv_list,
            process=process,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=timeout_seconds,
            timed_out=False,
            termination_reason="completed",
            signal_sent="none",
            final_state_observed="communicate",
            launch_latency_seconds=launch_latency_seconds,
            heartbeat_count=heartbeat_state.heartbeat_count,
            heartbeat_interval_seconds=active_heartbeat_interval or 0,
            quiet_seconds=heartbeat_state.quiet_seconds,
            observation_mode=observation_mode,
        )
    except subprocess.TimeoutExpired:
        returncode = _poll_returncode(process)
        if returncode is not None:
            stdout, stderr = process.communicate()
            return _result_from_completed_process(
                argv_list=argv_list,
                process=process,
                stdout=stdout,
                stderr=stderr,
                timeout_seconds=timeout_seconds,
                timed_out=False,
                termination_reason="completed",
                signal_sent="none",
                final_state_observed="poll_before_signal",
                launch_latency_seconds=launch_latency_seconds,
                heartbeat_count=heartbeat_state.heartbeat_count,
                heartbeat_interval_seconds=active_heartbeat_interval or 0,
                quiet_seconds=heartbeat_state.quiet_seconds,
                observation_mode=observation_mode,
            )
        stdout, stderr, signal_sent, final_state_observed = _finalize_timed_out_process(
            process,
            backend=active_backend,
            grace_seconds=grace_seconds,
        )
        timed_out = final_state_observed not in TIMEOUT_RECOVERY_STATES
        termination_reason = _timeout_termination_reason(
            timed_out=timed_out,
            final_state_observed=final_state_observed,
            stdout=stdout,
            stderr=stderr,
            launch_latency_seconds=launch_latency_seconds,
            timeout_seconds=timeout_seconds,
        )
        return _result_from_completed_process(
            argv_list=argv_list,
            process=process,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=timeout_seconds,
            timed_out=timed_out,
            termination_reason=termination_reason,
            signal_sent=signal_sent,
            final_state_observed=final_state_observed,
            launch_latency_seconds=launch_latency_seconds,
            heartbeat_count=heartbeat_state.heartbeat_count,
            heartbeat_interval_seconds=active_heartbeat_interval or 0,
            quiet_seconds=heartbeat_state.quiet_seconds,
            observation_mode=observation_mode,
        )
