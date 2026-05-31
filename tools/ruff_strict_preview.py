from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_SELECT = "B,SIM,UP,I"
DEFAULT_TARGETS = "ops/scripts tests tools"


def parse_targets(value: str) -> list[str]:
    targets = [item.strip() for item in shlex.split(value) if item.strip()]
    if not targets:
        raise ValueError("strict Ruff preview must include at least one target")
    return targets


def build_ruff_command(
    select: str,
    targets: list[str],
    *,
    cache_dir: str | None = None,
) -> list[str]:
    if not targets:
        raise ValueError("strict Ruff preview target list must contain at least one target")
    command = [sys.executable, "-m", "ruff", "check", "--select", select]
    if cache_dir:
        command.extend(["--cache-dir", cache_dir])
    command.extend(targets)
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict Ruff preview on a target surface")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--select", default=DEFAULT_SELECT)
    parser.add_argument("--cache-dir", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    targets = parse_targets(str(args.targets))
    completed = subprocess.run(
        build_ruff_command(args.select, targets, cache_dir=args.cache_dir),
        cwd=vault,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
