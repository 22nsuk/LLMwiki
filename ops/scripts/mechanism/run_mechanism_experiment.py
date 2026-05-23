#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.run_mechanism_experiment_runtime import (
        RunMechanismExperimentError,
        run_mechanism_experiment,
    )
else:
    from .run_mechanism_experiment_runtime import (
        RunMechanismExperimentError,
        run_mechanism_experiment,
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--primary-target", action="append", default=[])
    ap.add_argument("--supporting-target", action="append", default=[])
    ap.add_argument("--test-file", action="append", default=[])
    ap.add_argument("--proposal-id")
    ap.add_argument("--proposal-report")
    ap.add_argument("--scope-freeze")
    ap.add_argument("--routing-report", action="append", default=[])
    ap.add_argument("--executor-report", action="append", default=[])
    ap.add_argument("--log-summary")
    ap.add_argument("--mutation-command")
    ap.add_argument("--check-command")
    ap.add_argument("--require-signoff", action="store_true")
    ap.add_argument("--signoff-status", choices=["pending", "approved", "rejected", "not_required"])
    ap.add_argument("--signoff-by")
    ap.add_argument("--signoff-ts")
    ap.add_argument("--apply-mode", choices=["canary_only", "live"])
    ap.add_argument("--scaffold-only", action="store_true")
    ap.add_argument("--no-finalize", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    vault = Path(args.vault).resolve()
    try:
        result = run_mechanism_experiment(
            vault,
            run_id=args.run_id,
            policy_path=args.policy,
            primary_targets=args.primary_target,
            supporting_targets=args.supporting_target,
            test_files=args.test_file,
            log_summary=args.log_summary,
            mutation_command=args.mutation_command,
            check_command=args.check_command,
            require_signoff=args.require_signoff,
            signoff_status=args.signoff_status,
            signoff_by=args.signoff_by,
            signoff_ts=args.signoff_ts,
            apply_mode=args.apply_mode,
            finalize=not args.no_finalize,
            proposal_id=args.proposal_id,
            proposal_report_path=args.proposal_report,
            scaffold_only=args.scaffold_only,
            scope_freeze_path=args.scope_freeze,
            routing_report_paths=args.routing_report,
            executor_report_paths=args.executor_report,
        )
    except RunMechanismExperimentError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(exc.exit_code)
    except Exception as exc:  # pragma: no cover - broad-exception: cli_boundary
        print(str(exc), file=sys.stderr)
        raise SystemExit(8)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
