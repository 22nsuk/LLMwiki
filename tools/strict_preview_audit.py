from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TARGETS = "ops/scripts tests tools"
DEFAULT_OUT = "tmp/strict-preview-audit.json"
DEFAULT_RUFF_SELECT = "B,SIM,UP,I"
DEFAULT_MYPY_FLAGS = (
    "--check-untyped-defs",
    "--disallow-untyped-defs",
    "--disallow-incomplete-defs",
)
FOUND_ERRORS_RE = re.compile(r"Found (?P<count>\d+) errors?(?: in (?P<files>\d+) files?)?")
MYPY_SUCCESS_RE = re.compile(r"Success: no issues found in (?P<files>\d+) source files")
RUFF_STAT_RE = re.compile(r"^\s*(?P<count>\d+)\s+(?P<rule>[A-Z]+\d+)\s+")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], Path], CommandResult]


def parse_targets(value: str) -> list[str]:
    targets = [item.strip() for item in shlex.split(value) if item.strip()]
    if not targets:
        raise ValueError("strict preview audit must include at least one target")
    return targets


def _combined_output(result: CommandResult) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _tail_lines(text: str, *, limit: int = 40) -> list[str]:
    return text.splitlines()[-limit:]


def parse_ruff_output(text: str) -> dict[str, Any]:
    rule_counts: dict[str, int] = {}
    for line in text.splitlines():
        match = RUFF_STAT_RE.match(line)
        if match:
            rule_counts[match.group("rule")] = int(match.group("count"))
    found = FOUND_ERRORS_RE.search(text)
    error_count = int(found.group("count")) if found else 0
    return {
        "error_count": error_count,
        "rule_counts": dict(sorted(rule_counts.items())),
    }


def parse_mypy_output(text: str) -> dict[str, int]:
    found = FOUND_ERRORS_RE.search(text)
    if found:
        return {
            "error_count": int(found.group("count")),
            "file_count": int(found.group("files") or 0),
        }
    success = MYPY_SUCCESS_RE.search(text)
    if success:
        return {"error_count": 0, "file_count": int(success.group("files"))}
    return {"error_count": 0, "file_count": 0}


def run_command(args: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def build_report(
    vault: Path,
    *,
    targets: Sequence[str],
    ruff_select: str,
    mypy_flags: Sequence[str],
    python_executable: str,
    command_runner: CommandRunner = run_command,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    target_list = list(targets)
    ruff_command = [
        python_executable,
        "-m",
        "ruff",
        "check",
        "--select",
        ruff_select,
        "--statistics",
        *target_list,
    ]
    mypy_command = [
        python_executable,
        "-m",
        "mypy",
        "--config-file",
        "pyproject.toml",
        *mypy_flags,
        *target_list,
    ]
    ruff_result = command_runner(ruff_command, resolved_vault)
    mypy_result = command_runner(mypy_command, resolved_vault)
    ruff_output = _combined_output(ruff_result)
    mypy_output = _combined_output(mypy_result)
    ruff = {
        "command": ruff_command,
        "returncode": ruff_result.returncode,
        **parse_ruff_output(ruff_output),
        "output_tail": _tail_lines(ruff_output),
    }
    mypy = {
        "command": mypy_command,
        "returncode": mypy_result.returncode,
        **parse_mypy_output(mypy_output),
        "output_tail": _tail_lines(mypy_output),
    }
    status = (
        "pass"
        if (
            ruff_result.returncode == 0
            and mypy_result.returncode == 0
            and ruff["error_count"] == 0
            and mypy["error_count"] == 0
        )
        else "attention"
    )
    return {
        "artifact_kind": "strict_preview_audit",
        "producer": "tools.strict_preview_audit",
        "status": status,
        "targets": target_list,
        "ruff_select": ruff_select,
        "mypy_flags": list(mypy_flags),
        "ruff": ruff,
        "mypy": mypy,
        "summary": {
            "ruff_error_count": ruff["error_count"],
            "mypy_error_count": mypy["error_count"],
            "total_error_count": ruff["error_count"] + mypy["error_count"],
        },
    }


def write_report(out_path: Path, report: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit strict Ruff and mypy preview debt across a target surface.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--ruff-select", default=DEFAULT_RUFF_SELECT)
    parser.add_argument(
        "--mypy-flags",
        default=" ".join(DEFAULT_MYPY_FLAGS),
        help="Shell-style mypy flag string used before the target list.",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--fail-on-attention", action="store_true")
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    command_runner: CommandRunner = run_command,
) -> int:
    args = parse_args(argv)
    vault = Path(args.vault)
    report = build_report(
        vault,
        targets=parse_targets(args.targets),
        ruff_select=str(args.ruff_select),
        mypy_flags=shlex.split(str(args.mypy_flags)),
        python_executable=str(args.python),
        command_runner=command_runner,
    )
    write_report(vault / str(args.out), report)
    print((vault / str(args.out)).as_posix())
    if args.fail_on_attention and report["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
