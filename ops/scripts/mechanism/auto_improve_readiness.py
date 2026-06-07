#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import display_path, resolve_repo_output_path
    from ops.scripts.mechanism.auto_improve_readiness_runtime import (
        READINESS_REPORT_REL_PATH,
        REMEDIATION_BACKLOG_REPORT_REL_PATH,
        build_readiness_report,
        readiness_exit_code,
        write_readiness_report,
    )
else:
    from ops.scripts.core.output_runtime import display_path, resolve_repo_output_path

    from .auto_improve_readiness_runtime import (
        READINESS_REPORT_REL_PATH,
        REMEDIATION_BACKLOG_REPORT_REL_PATH,
        build_readiness_report,
        readiness_exit_code,
        write_readiness_report,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the auto-improve readiness preflight report")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=READINESS_REPORT_REL_PATH)
    parser.add_argument("--remediation-backlog", default=REMEDIATION_BACKLOG_REPORT_REL_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    out_path = resolve_repo_output_path(
        vault,
        args.out,
        default_relative_path=READINESS_REPORT_REL_PATH,
    ).as_posix()
    report = build_readiness_report(
        vault,
        policy_path=args.policy_path,
        remediation_backlog_path=args.remediation_backlog,
    )
    destination = write_readiness_report(vault, report, out_path)
    print(display_path(vault, destination))
    return readiness_exit_code(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
