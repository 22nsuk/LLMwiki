from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


DEFAULT_ALLOWLIST = "ops/ruff-strict-preview-allowlist.txt"
DEFAULT_SELECT = "B,SIM,UP,I"
DEFAULT_TARGETS = "ops/scripts tests tools"


def resolve_allowlist_path(vault: Path, allowlist_path: str) -> Path:
    path = Path(allowlist_path)
    if not path.is_absolute():
        path = vault / path
    return path.resolve()


def load_allowlist_targets(vault: Path, allowlist_path: str = DEFAULT_ALLOWLIST) -> list[str]:
    allowlist_file = resolve_allowlist_path(vault, allowlist_path)
    targets: list[str] = []
    for raw_line in allowlist_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.lstrip("\ufeff").split("#", 1)[0].strip()
        if not line:
            continue
        target_path = Path(line)
        resolved = target_path if target_path.is_absolute() else (vault / target_path)
        if not resolved.exists():
            raise FileNotFoundError(f"strict Ruff allowlist target does not exist: {line}")
        targets.append(line if not target_path.is_absolute() else str(resolved))
    return targets


def parse_targets(value: str) -> list[str]:
    targets = [item.strip() for item in shlex.split(value) if item.strip()]
    if not targets:
        raise ValueError("strict Ruff preview must include at least one target")
    return targets


def build_ruff_command(select: str, targets: list[str]) -> list[str]:
    if not targets:
        raise ValueError("strict Ruff preview target list must contain at least one target")
    return [sys.executable, "-m", "ruff", "check", "--select", select, *targets]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict Ruff preview on a target surface")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--allowlist", default=DEFAULT_ALLOWLIST)
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--select", default=DEFAULT_SELECT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    targets = parse_targets(str(args.targets))
    if not targets and args.allowlist:
        targets = load_allowlist_targets(vault, args.allowlist)
    completed = subprocess.run(build_ruff_command(args.select, targets), cwd=vault, check=False)
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
