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
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.mechanism.mechanism_review_runtime import (
        MECHANISM_REVIEW_SCHEMA,
        build_report,
    )
else:
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy

    from .mechanism_review_runtime import MECHANISM_REVIEW_SCHEMA, build_report


DEFAULT_OUT = "ops/reports/mechanism-review-candidates.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--out")
    ap.add_argument("--max-runs", type=int)
    ap.add_argument("--max-candidates", type=int)
    ap.add_argument("--policy-path")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    try:
        policy, policy_path = load_policy(vault, args.policy_path)
    except Exception as exc:  # broad-exception: cli_policy_load_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(3) from exc

    try:
        report = build_report(
            vault,
            policy,
            policy_path,
            max_runs=args.max_runs,
            max_candidates=args.max_candidates,
        )
        destination = write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=MECHANISM_REVIEW_SCHEMA,
                out_path=args.out,
                default_relative_path=DEFAULT_OUT,
                context="mechanism review report schema validation failed",
                trailing_newline=False,
            )
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(7) from exc
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8) from exc

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten_to={display_path(vault, destination)}")


if __name__ == "__main__":
    main()
