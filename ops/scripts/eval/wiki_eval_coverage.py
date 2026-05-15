#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
from ops.scripts.policy_runtime import load_policy
from .wiki_eval_coverage_runtime import WIKI_EVAL_COVERAGE_SCHEMA, build_report


DEFAULT_OUT = "ops/reports/wiki-eval-coverage-report.json"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--require-no-gaps", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    vault = Path(args.vault)
    policy, resolved_policy_path = load_policy(vault, args.policy)
    report = build_report(vault, policy, resolved_policy_path)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=WIKI_EVAL_COVERAGE_SCHEMA,
                out_path=args.out,
                default_relative_path=DEFAULT_OUT,
                context="wiki eval coverage report schema validation failed",
                trailing_newline=False,
            )
        )
    else:
        print(text)
    raise SystemExit(1 if args.require_no_gaps and report["review_candidates"] else 0)


if __name__ == "__main__":
    main()
