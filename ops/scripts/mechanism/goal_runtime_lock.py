from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LOCK_PATH = "build/goal-runs/goal-runtime.lock.json"
LOCK_KIND = "goal_runtime_workspace_lock"
PRODUCER = "ops.scripts.goal_runtime_lock"
LOCK_ACTIVE_EXIT_CODE = 75

ProcessIsRunning = Callable[[int], bool]
ProcessGroupIsRunning = Callable[[int], bool]
SignalPid = Callable[[int, int], None]
SignalPgid = Callable[[int, int], None]


class GoalRuntimeWorkspaceLockActive(RuntimeError):
    pass


@dataclass(frozen=True)
class GoalRuntimeWorkspaceLock:
    path: Path
    token: str


def _resolve_under_vault(vault: Path, rel_or_abs_path: str) -> Path:
    vault_root = vault.resolve()
    path = Path(rel_or_abs_path)
    resolved = path.resolve() if path.is_absolute() else (vault_root / path).resolve()
    try:
        resolved.relative_to(vault_root)
    except ValueError as exc:
        raise ValueError(f"goal runtime lock path must stay under vault: {resolved}") from exc
    return resolved


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _process_group_is_running(pgid: int) -> bool:
    if pgid <= 0 or os.name == "nt":
        return False
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    try:
        killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def process_group_id_for_pid(pid: int) -> int:
    getpgid = getattr(os, "getpgid", None)
    if getpgid is None or pid <= 0:
        return 0
    try:
        return int(getpgid(pid))
    except OSError:
        return 0


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _int_field(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _active_owner(
    payload: dict[str, Any],
    *,
    process_is_running: ProcessIsRunning,
    process_group_is_running: ProcessGroupIsRunning,
) -> dict[str, Any] | None:
    for field, owner_type, probe in (
        ("child_pgid", "child_process_group", process_group_is_running),
        ("child_pid", "child_process", process_is_running),
        ("pid", "runner_process", process_is_running),
    ):
        value = _int_field(payload, field)
        if value > 0 and probe(value):
            return {"type": owner_type, "field": field, "id": value}
    return None


def inspect_workspace_lock(
    vault: Path,
    *,
    lock_path: str = DEFAULT_LOCK_PATH,
    process_is_running: ProcessIsRunning = _process_is_running,
    process_group_is_running: ProcessGroupIsRunning = _process_group_is_running,
) -> dict[str, Any]:
    resolved = _resolve_under_vault(vault, lock_path)
    if not resolved.exists():
        return {
            "status": "missing",
            "active": False,
            "path": resolved.relative_to(vault.resolve()).as_posix(),
            "payload": {},
            "active_owner": None,
            "reason": "lock file is absent",
        }
    payload = _load_payload(resolved)
    if not payload:
        return {
            "status": "invalid",
            "active": True,
            "path": resolved.relative_to(vault.resolve()).as_posix(),
            "payload": {},
            "active_owner": None,
            "reason": "lock file is unreadable or not a JSON object",
        }
    owner = _active_owner(
        payload,
        process_is_running=process_is_running,
        process_group_is_running=process_group_is_running,
    )
    if owner is not None:
        return {
            "status": "active",
            "active": True,
            "path": resolved.relative_to(vault.resolve()).as_posix(),
            "payload": payload,
            "active_owner": owner,
            "reason": f"active {owner['type']} {owner['id']} owns the goal runtime workspace",
        }
    return {
        "status": "stale",
        "active": False,
        "path": resolved.relative_to(vault.resolve()).as_posix(),
        "payload": payload,
        "active_owner": None,
        "reason": "lock file exists but no recorded owner process is alive",
    }


def cleanup_stale_workspace_lock(vault: Path, *, lock_path: str = DEFAULT_LOCK_PATH) -> bool:
    resolved = _resolve_under_vault(vault, lock_path)
    status = inspect_workspace_lock(vault, lock_path=lock_path)
    if status["status"] != "stale":
        return False
    try:
        resolved.unlink()
    except FileNotFoundError:
        return False
    return True


def acquire_workspace_lock(
    vault: Path,
    *,
    lock_path: str = DEFAULT_LOCK_PATH,
    run_id: str,
    runtime_mode: str,
    started_at: str,
    command_argv: list[str],
) -> GoalRuntimeWorkspaceLock:
    resolved = _resolve_under_vault(vault, lock_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}:{run_id}:{started_at}"
    payload = {
        "artifact_kind": LOCK_KIND,
        "producer": PRODUCER,
        "run_id": run_id,
        "runtime_mode": runtime_mode,
        "pid": os.getpid(),
        "pgid": process_group_id_for_pid(os.getpid()),
        "child_pid": 0,
        "child_pgid": 0,
        "started_at": started_at,
        "command": " ".join(command_argv),
        "token": token,
    }
    while True:
        try:
            fd = os.open(resolved, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            status = inspect_workspace_lock(vault, lock_path=lock_path)
            if status["status"] == "stale":
                try:
                    resolved.unlink()
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
                else:
                    continue
            raise GoalRuntimeWorkspaceLockActive(
                f"goal runtime workspace already active: {status['reason']}; lock={resolved}"
            ) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        return GoalRuntimeWorkspaceLock(path=resolved, token=token)


def update_workspace_lock_child(
    lock: GoalRuntimeWorkspaceLock,
    *,
    child_pid: int,
    child_pgid: int,
) -> None:
    payload = _load_payload(lock.path)
    if payload.get("token") != lock.token:
        return
    payload["child_pid"] = child_pid
    payload["child_pgid"] = child_pgid
    lock.path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def release_workspace_lock(lock: GoalRuntimeWorkspaceLock) -> None:
    payload = _load_payload(lock.path)
    if payload.get("token") != lock.token:
        return
    try:
        lock.path.unlink()
    except FileNotFoundError:
        return


def stop_workspace_lock(
    vault: Path,
    *,
    lock_path: str = DEFAULT_LOCK_PATH,
    process_is_running: ProcessIsRunning = _process_is_running,
    process_group_is_running: ProcessGroupIsRunning = _process_group_is_running,
    signal_pid: SignalPid = os.kill,
    signal_pgid: SignalPgid | None = None,
) -> dict[str, Any]:
    resolved = _resolve_under_vault(vault, lock_path)
    status = inspect_workspace_lock(
        vault,
        lock_path=lock_path,
        process_is_running=process_is_running,
        process_group_is_running=process_group_is_running,
    )
    if status["status"] in {"missing", "stale"}:
        if status["status"] == "stale":
            with suppress(FileNotFoundError):
                resolved.unlink()
        return {
            "status": "not_running",
            "signaled": False,
            "lock": status,
            "reason": status["reason"],
        }
    if status["status"] == "invalid":
        return {
            "status": "blocked",
            "signaled": False,
            "lock": status,
            "reason": status["reason"],
        }
    owner = status.get("active_owner") or {}
    owner_id = int(owner.get("id", 0))
    owner_type = str(owner.get("type", ""))
    current_pid = os.getpid()
    current_pgid = process_group_id_for_pid(current_pid)
    if owner_type.endswith("process_group"):
        if owner_id == current_pgid:
            return {
                "status": "refused",
                "signaled": False,
                "lock": status,
                "reason": "refusing to signal the current process group",
            }
        pgid_sender = signal_pgid or getattr(os, "killpg", None)
        if pgid_sender is None:
            return {
                "status": "blocked",
                "signaled": False,
                "lock": status,
                "reason": "process group signaling is unavailable on this platform",
            }
        pgid_sender(owner_id, int(signal.SIGTERM))
    else:
        if owner_id == current_pid:
            return {
                "status": "refused",
                "signaled": False,
                "lock": status,
                "reason": "refusing to signal the current process",
            }
        signal_pid(owner_id, int(signal.SIGTERM))
    return {
        "status": "stop_requested",
        "signaled": True,
        "signal": "SIGTERM",
        "target": owner,
        "lock": status,
        "reason": f"sent SIGTERM to {owner_type} {owner_id}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or control the repository-wide goal runtime lock.")
    parser.add_argument("action", choices=("check", "status", "stop"))
    parser.add_argument("--vault", default=".")
    parser.add_argument("--lock-path", default=DEFAULT_LOCK_PATH)
    parser.add_argument("--cleanup-stale", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    if args.action == "status":
        status = inspect_workspace_lock(vault, lock_path=args.lock_path)
        print(json.dumps(status, ensure_ascii=False, indent=2) if args.json else status["reason"])
        return 0 if status["status"] != "invalid" else LOCK_ACTIVE_EXIT_CODE
    if args.action == "stop":
        result = stop_workspace_lock(vault, lock_path=args.lock_path)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["reason"])
        return 0 if result["status"] in {"not_running", "stop_requested"} else LOCK_ACTIVE_EXIT_CODE

    status = inspect_workspace_lock(vault, lock_path=args.lock_path)
    if status["status"] == "stale" and args.cleanup_stale:
        cleanup_stale_workspace_lock(vault, lock_path=args.lock_path)
        print(f"removed stale goal runtime lock: {status['path']}")
        return 0
    if status["active"]:
        print(status["reason"], file=sys.stderr)
        return LOCK_ACTIVE_EXIT_CODE
    print(status["reason"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
