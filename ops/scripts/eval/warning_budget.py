#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.eval.warning_budget_runtime import (
        WARNING_BUDGET_REPORT_SCHEMA,
        build_report,
    )
else:
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )

    from .warning_budget_runtime import WARNING_BUDGET_REPORT_SCHEMA, build_report


DEFAULT_OUT = "ops/reports/warning-budget-report.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--profile")
    parser.add_argument("--out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault)
    try:
        report = build_report(
            vault,
            args.policy,
            profile_name=args.profile,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(3) from exc
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(7) from exc

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=WARNING_BUDGET_REPORT_SCHEMA,
                out_path=args.out,
                default_relative_path=DEFAULT_OUT,
                context="warning budget report schema validation failed",
                trailing_newline=False,
            )
        )
    else:
        print(text)
    raise SystemExit(1 if report["status"] == "fail" else 0)


if __name__ == "__main__":
    main()
