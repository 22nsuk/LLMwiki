#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.subagent_routing_runtime import print_report, run_selector
else:
    from .subagent_routing_runtime import print_report, run_selector


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--role", required=True)
    ap.add_argument("--primary-target", action="append", default=[])
    ap.add_argument("--supporting-target", action="append", default=[])
    ap.add_argument("--test-file", action="append", default=[])
    ap.add_argument("--manual-risk-flag", action="append", default=[])
    ap.add_argument("--requested-rung", type=int)
    ap.add_argument("--out")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report, destination = run_selector(
        vault=vault,
        policy_path=args.policy,
        role=args.role,
        primary_targets=args.primary_target,
        supporting_targets=args.supporting_target,
        test_files=args.test_file,
        manual_risk_flags=args.manual_risk_flag,
        requested_rung=args.requested_rung,
        out_path=args.out,
    )
    print_report(vault, report, destination)


if __name__ == "__main__":
    main()
